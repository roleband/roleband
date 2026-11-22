"""A pursuit's next steps: `steps.add`, `steps.edit`, `steps.done` and
`steps.undo`.

A pursuit holds any number of open next steps; `pursuits.get` lists them,
soonest first, with the ids these operations take. Each write goes through
`tracker.agents.pursuits`, the store the dashboard's step writes use, states
the pursuit's revision it read, and answers the pursuit as `pursuits.get`
does, with its new revision. A ticked step leaves the open steps and stays in
the pursuit's history; `steps.undo` opens it again. No operation deletes a
step: the person removes one in the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator
from pydantic.config import JsonDict
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.activity import Changed, FieldChange, Said
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape, ToolTier
from tracker.agents.operations.envelope import OperationError
from tracker.agents.operations.pursuits import (
    VIA,
    PursuedOpportunity,
    PursuitItem,
    no_pursuit,
    pursuit_item,
)
from tracker.agents.pursuits import (
    StepUpdate,
    StepWrite,
    add_step,
    lock_role_writes,
    refuse_null,
    step_words,
    update_step,
)
from tracker.agents.receipts import RevisionConflict
from tracker.db.models import Job, Pursuit, PursuitStep

_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")
_REVISION_READ = "The pursuit's revision you read (pursuits.get); 0 when the role has no pursuit yet."


class StepAddInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity the pursuit is about.")
    if_revision: int = Field(ge=0, description=f"{_REVISION_READ} A pursuit that moved since is not changed.")
    text: str = Field(min_length=1, max_length=2_000, json_schema_extra=_CONTENT, description="What to do.")
    due: AwareDatetime | None = Field(
        default=None, description="The day it is due by, with its UTC offset. Leave it out for a step with no day."
    )

    _has_words = field_validator("text")(step_words)


class StepInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity the pursuit is about.")
    step_id: int = Field(ge=1, description="The step's id, from the pursuit's steps (pursuits.get).")
    if_revision: int = Field(ge=1, description=f"{_REVISION_READ} A pursuit that moved since is not changed.")


class StepEditInput(StepInput):
    text: str | SkipJsonSchema[None] = Field(
        default=None, min_length=1, max_length=2_000, json_schema_extra=_CONTENT,
        description="The step's new words. Cannot be null.",
    )
    due: AwareDatetime | None = Field(
        default=None,
        description="The step's new day, with its UTC offset. null takes its day off; leave the field out to keep it.",
    )

    _no_null = field_validator("text", mode="before")(refuse_null)
    _has_words = field_validator("text")(step_words)

    @model_validator(mode="after")
    def _changes_something(self) -> StepEditInput:
        if not self.model_fields_set & {"text", "due"}:
            raise ValueError("name at least one field to change: text, due")
        return self


def _write_op(op_id: str, summary: str, input: type[BaseModel], examples: tuple[dict[str, Any], ...]) -> OperationDescriptor:
    return OperationDescriptor(
        id=op_id,
        summary=summary,
        input=input,
        result=PursuitItem,
        access="write",
        action_group="tracking_progress",
        idempotency="required_key",
        engine_effects=EngineEffects(state_write=True),
        tool_tiers=_EVERY_TIER,
        data_classes=("private_pursuit", "public_posting"),
        expects_revision=True,
        examples=examples,
    )


STEPS_ADD = _write_op(
    "steps.add",
    "Add a next step to a pursuit, with the day it is due by or none, against the revision read.",
    StepAddInput,
    (
        {"opportunity_id": 4821, "if_revision": 12, "text": "Send the portfolio", "due": "2026-12-01T09:00:00Z"},
        {"opportunity_id": 4821, "if_revision": 13, "text": "Ask Sam about the team"},
    ),
)
STEPS_EDIT = _write_op(
    "steps.edit",
    "Change a next step's words or day against the revision read. A day sent as null is taken off.",
    StepEditInput,
    ({"opportunity_id": 4821, "step_id": 7, "if_revision": 14, "due": "2026-12-03T09:00:00Z"},),
)
STEPS_DONE = _write_op(
    "steps.done",
    "Tick a next step done: it leaves the open steps and stays in the pursuit's history.",
    StepInput,
    ({"opportunity_id": 4821, "step_id": 7, "if_revision": 15},),
)
STEPS_UNDO = _write_op(
    "steps.undo",
    "Open a next step ticked done again.",
    StepInput,
    ({"opportunity_id": 4821, "step_id": 7, "if_revision": 16},),
)
OPERATIONS: tuple[OperationDescriptor, ...] = (STEPS_ADD, STEPS_EDIT, STEPS_DONE, STEPS_UNDO)


def _not_found(params: StepInput) -> OperationError:
    return OperationError(
        "not_found",
        "This pursuit has no step with this id. pursuits.get lists its steps.",
        details={"opportunity_id": params.opportunity_id, "step_id": params.step_id},
    )


async def _answer(session: AsyncSession, pursuit: Pursuit) -> PursuitItem:
    return await pursuit_item(session, pursuit, await session.get(Job, pursuit.job_id))


async def add(session: AsyncSession, params: StepAddInput, *, actor: Literal["agent"]) -> PursuitItem:
    try:
        pursuit, _ = await add_step(
            session, params.opportunity_id, StepWrite(text=params.text, due=params.due),
            actor=actor, expected_revision=params.if_revision, via=VIA,
        )
    except LookupError:
        raise OperationError(
            "not_found", "There is no opportunity with this id.", details={"opportunity_id": params.opportunity_id}
        ) from None
    except RevisionConflict as conflict:
        if conflict.current != 0:
            raise
        raise no_pursuit(params.opportunity_id, conflict.expected) from None
    return await _answer(session, pursuit)


async def change(
    session: AsyncSession, params: StepInput, *, actor: Literal["agent"],
    action: Literal["edit", "done", "undo"],
) -> PursuitItem:
    if action == "edit":
        update = StepUpdate(**params.model_dump(include={"text", "due"}, exclude_unset=True))
    else:
        update = StepUpdate(done=action == "done")
    try:
        pursuit, _ = await update_step(
            session, params.opportunity_id, params.step_id, update,
            actor=actor, expected_revision=params.if_revision, via=VIA,
        )
    except LookupError:
        raise _not_found(params) from None
    return await _answer(session, pursuit)


@dataclass(frozen=True)
class StepActivity:
    """What a step write lists on the Activity screen: the role, what was
    done to which step, and its words before and after."""

    opportunity_id: int
    action: Literal["add", "edit", "done", "undo"]
    step_id: int | None = None

    async def before(self, session: AsyncSession) -> dict[str, Any] | None:
        if self.step_id is None:
            return None
        await lock_role_writes(session, self.opportunity_id)
        step = await session.scalar(
            select(PursuitStep)
            .join(Pursuit, Pursuit.id == PursuitStep.pursuit_id)
            .where(PursuitStep.id == self.step_id, Pursuit.job_id == self.opportunity_id)
        )
        if step is None:
            return None
        return {"text": step.text, "due": step.due.isoformat() if step.due else None}

    def entry(self, before: Any, result: BaseModel) -> Changed:
        if not isinstance(result, PursuitItem):
            raise TypeError(f"a step write answers PursuitItem, not {type(result).__name__}")
        prior: dict[str, Any] = before or {}
        after: dict[str, Any] = {}
        if self.action == "add":
            # The new step is the open one the pursuit did not have before;
            # its id is the highest of them.
            newest = max(result.steps, key=lambda step: step.id, default=None)
            if newest is not None:
                after = {"text": newest.text, "due": newest.due.isoformat() if newest.due else None}
        else:
            # A ticked step leaves the open steps with its words unchanged, so
            # `done` records no field change. For the others the step is read
            # as the write left it; one that is not open (an edit of a ticked
            # step) is taken as it was.
            now = next((step for step in result.steps if step.id == self.step_id), None)
            after = (
                {"text": now.text, "due": now.due.isoformat() if now.due else None}
                if now is not None and self.action != "done"
                else dict(prior)
            )
        changes = tuple(
            FieldChange(field, prior.get(field), after.get(field))
            for field in ("text", "due")
            if prior.get(field) != after.get(field)
        )
        role = result.opportunity
        facts: dict[str, Any] = (
            {"title": role.title, "company": role.company} if isinstance(role, PursuedOpportunity) else {}
        )
        words = after.get("text") or prior.get("text") or ""
        at = f" on {facts['title']} at {facts['company']}" if facts else ""
        english = {
            "add": f"Added a next step{at}: {words}",
            "edit": f"Changed a next step{at}: {words}",
            "done": f"Ticked a next step done{at}: {words}",
            "undo": f"Opened a next step again{at}: {words}",
        }[self.action]
        return Changed(
            Said("pursuit.step", english, {**facts, "action": self.action, "step": words}),
            tuple(FieldChange(f"step_{change.field}", change.before, change.after) for change in changes),
        )

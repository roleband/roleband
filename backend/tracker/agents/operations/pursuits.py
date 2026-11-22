"""The person's progress on the roles they pursue: `pursuits.list` and
`pursuits.get` read it, `pursuits.save` and `pursuits.patch` change it.

All four go through `tracker.agents.pursuits`, the store the dashboard and
every pursuit writer share, and answer its `public_pursuit` fields, notes
included, with the pursuit's `revision`, which a write passes back.
A pursuit is addressed by its opportunity's id, never the pursuit row's, and
its record carries that id alone, as `opportunity_id`: an agent reading a
record finds no other id a command would take.

A patch reads its fields by presence: a field sent as null clears it, a field
left out is untouched. Stage and priority always have a value, so a null for
either is an input error rather than a clear.

A pursuit is the person's own record, so neither read hides one because its
company was later hidden: the Board's visibility rules decide what is offered,
not what the person already chose to pursue.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.config import JsonDict
from pydantic.experimental.missing_sentinel import MISSING
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.activity import Changed, FieldChange, Said
from tracker.agents.applications import pursuit_marks
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape, ToolTier
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.pursuits import (
    PursuitListKey,
    PursuitStage,
    PursuitUpdate,
    StepNeedsWords,
    list_pursuits,
    lock_role_writes,
    public_pursuit,
    upsert_pursuit,
)
from tracker.agents.receipts import RevisionConflict
from tracker.db.models import Job, Pursuit

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

#: The page size an omitted limit reads, and the most one page holds.
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
#: The cursor's own format; a cursor of another format is refused, never guessed at.
_CURSOR_FORMAT = 1


class PursuitState(Shape):
    """One pursuit's fields as every agent operation shows them."""

    #: The opportunity this pursuit is about: the id every pursuit operation takes.
    opportunity_id: int
    stage: PursuitStage = Field(json_schema_extra=_CODE)
    #: 5 Urgent, 4 High, 3 Medium, 2 Low, 1 No priority.
    priority: int = Field(ge=1, le=5)
    #: The person's own notes. Text an agent wrote here earlier reads back too.
    notes: str | None = Field(json_schema_extra=_CONTENT)
    next_action: str | None = Field(json_schema_extra=_CONTENT)
    next_action_due: datetime | None
    created_at: datetime
    updated_at: datetime
    #: Advances with every change to the pursuit, the dashboard's included. A
    #: write passes back the revision it read and is refused if it moved.
    revision: int = Field(ge=1)

    @model_validator(mode="before")
    @classmethod
    def _from_row_keys(cls, data: Any) -> Any:
        """A write's receipt keeps its result in the keys it was stored with,
        which may be the row's `id` and `job_id`; a same-key retry replays it
        in this shape all the same."""
        if isinstance(data, dict) and "job_id" in data and "opportunity_id" not in data:
            return agent_fields(data)
        return data


class PursuedOpportunity(Shape):
    title: str = Field(json_schema_extra=_CONTENT)
    company: str = Field(json_schema_extra=_IDENTIFIER)
    status: str = Field(json_schema_extra=_CODE)
    url: str = Field(json_schema_extra=_IDENTIFIER)


class PursuitRound(Shape):
    """An interview round, as the pipeline's card names it."""

    id: int
    label: str = Field(json_schema_extra=_CONTENT)
    scheduled_at: datetime
    all_day: bool
    format: Literal["video", "phone", "onsite"] | None = Field(json_schema_extra=_CODE)
    #: Where the round is held: a call's address, as the person entered it.
    link: str | None = Field(json_schema_extra=_IDENTIFIER)


class PursuitNextStep(Shape):
    """One next step the person owes: `steps.edit`, `steps.done` and
    `steps.undo` take its id."""

    id: int
    text: str = Field(json_schema_extra=_CONTENT)
    #: The day it is due by; none for a step with no day.
    due: datetime | None
    created_at: datetime
    #: When it was ticked done; none while it is open.
    done_at: datetime | None


class PursuitItem(PursuitState):
    #: Every open next step, soonest first; steps with no day last, in the
    #: order added. `next_action` and `next_action_due` are the first of them.
    steps: list[PursuitNextStep]
    #: The soonest round with no outcome, until twelve hours after it began.
    next_interview: PursuitRound | None
    #: The latest round that has taken place with no outcome given: a timed
    #: round once it began, an all-day round once its day is over. In the
    #: hours after it began it is also `next_interview`.
    awaiting_outcome: PursuitRound | None
    #: False until a priority is chosen for the pursuit: read its priority as
    #: no priority until then, whatever the stored number.
    priority_set: bool
    #: Absent when the person does not share postings with assistants.
    opportunity: PursuedOpportunity | MISSING = MISSING


class PursuitListInput(Shape):
    stage: PursuitStage | None = Field(default=None, description="Only pursuits at this stage.")
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Pursuits on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description=(
            "The next_cursor of the previous page, read with the same stage. It resumes after that "
            "page's last pursuit in the current order, with no snapshot: a pursuit re-prioritised "
            "during paging can be skipped or read twice, so read from the first page for a whole list."
        ),
    )


class PursuitList(Shape):
    #: Pursuits on this page; `meta.next_cursor` reads the next one.
    count: int = Field(ge=0)
    items: list[PursuitItem]


class PursuitGetInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity the pursuit is about.")


PURSUITS_LIST = OperationDescriptor(
    id="pursuits.list",
    summary="List the pursuits with their stage, priority, notes and next action, the most urgent first.",
    input=PursuitListInput,
    result=PursuitList,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit", "public_posting"),
    examples=({"stage": "applied", "limit": 20},),
)

PURSUITS_GET = OperationDescriptor(
    id="pursuits.get",
    summary="Read one pursuit, notes included, by the opportunity it is about.",
    input=PursuitGetInput,
    result=PursuitItem,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit", "public_posting"),
    examples=({"opportunity_id": 4821},),
)


#: What an agent write records as its way in, beside the actor, in the pursuit's event.
VIA = "agent_api"
#: The fields a patch can change; the rest of its input names the pursuit and the revision read.
PATCH_FIELDS = ("stage", "priority", "notes", "next_action", "next_action_due")
_REVISION_READ = "The revision you read (pursuits.get or pursuits.list); 0 when the role has no pursuit yet."


_Priority = Annotated[int, Field(ge=1, le=5)]


def _refuse_null(value: object) -> object:
    if value is None:
        raise ValueError("cannot be null; leave the field out to keep it")
    return value


class PursuitSaveInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity to save.")
    # `SkipJsonSchema[None]` keeps null out of the published schema: the
    # default stands for "not given", and an explicit null is refused below.
    priority: _Priority | SkipJsonSchema[None] = Field(
        default=None,
        description=(
            "5 Urgent, 4 High, 3 Medium, 2 Low, 1 No priority. A new pursuit has no priority chosen; "
            "an existing one keeps its own unless this is given."
        ),
    )
    if_revision: Annotated[int, Field(ge=0)] | SkipJsonSchema[None] = Field(
        default=None,
        description=f"{_REVISION_READ} Given, a pursuit that moved since is not changed (revision_conflict).",
    )

    _no_null = field_validator("priority", "if_revision", mode="before")(_refuse_null)


class PursuitPatchInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity the pursuit is about.")
    if_revision: int = Field(ge=0, description=f"{_REVISION_READ} A pursuit that moved since is not changed.")
    stage: PursuitStage | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=_CODE, description="The new stage. Cannot be null."
    )
    priority: _Priority | SkipJsonSchema[None] = Field(
        default=None, description="5 Urgent, 4 High, 3 Medium, 2 Low, 1 No priority. Cannot be null."
    )
    notes: str | None = Field(
        default=None, max_length=20_000, json_schema_extra=_CONTENT,
        description="Replaces the notes. null clears them; leave the field out to keep them.",
    )
    next_action: str | None = Field(
        default=None, max_length=2_000, json_schema_extra=_CONTENT,
        description="The next step. null clears it; leave the field out to keep it.",
    )
    next_action_due: AwareDatetime | None = Field(
        default=None,
        description=(
            "When the next step falls due, with its UTC offset. null clears it; leave the field out to keep it."
        ),
    )

    _no_null = field_validator("stage", "priority", mode="before")(_refuse_null)

    @model_validator(mode="after")
    def _changes_something(self) -> PursuitPatchInput:
        if not self.model_fields_set & set(PATCH_FIELDS):
            raise ValueError(f"name at least one field to change: {', '.join(PATCH_FIELDS)}")
        return self

    def update(self) -> PursuitUpdate:
        """The fields sent, nulls included; a field left out is not in it."""
        return PursuitUpdate(**self.model_dump(include=set(PATCH_FIELDS), exclude_unset=True))


PURSUITS_SAVE = OperationDescriptor(
    id="pursuits.save",
    summary=(
        "Save an opportunity. A new pursuit starts at saved with priority 3; an existing one keeps its "
        "stage and notes, and its priority unless one is given."
    ),
    input=PursuitSaveInput,
    result=PursuitItem,
    access="write",
    action_group="tracking_progress",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit", "public_posting"),
    examples=({"opportunity_id": 4821}, {"opportunity_id": 4821, "priority": 2, "if_revision": 0}),
)

PURSUITS_PATCH = OperationDescriptor(
    id="pursuits.patch",
    summary=(
        "Change a pursuit's stage, priority, notes or next action against the revision read. "
        "A field sent as null is cleared; a field left out is kept."
    ),
    input=PursuitPatchInput,
    result=PursuitItem,
    access="write",
    action_group="tracking_progress",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit", "public_posting"),
    expects_revision=True,
    examples=(
        {"opportunity_id": 4821, "if_revision": 12, "next_action": "Follow up", "next_action_due": "2026-12-01T09:00:00Z"},
        {"opportunity_id": 4821, "if_revision": 13, "next_action_due": None},
    ),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (PURSUITS_LIST, PURSUITS_GET, PURSUITS_SAVE, PURSUITS_PATCH)


class _CursorBody(BaseModel):
    """What a cursor binds: its workspace and stage, and the last row read."""

    f: int
    w: str
    s: str | None
    p: int
    u: datetime
    i: int


def encode_cursor(*, workspace_id: str, stage: str | None, last: dict[str, Any]) -> str:
    body = _CursorBody(
        f=_CURSOR_FORMAT, w=workspace_id, s=stage, p=last["priority"], u=last["updated_at"], i=last["id"]
    )
    return base64.urlsafe_b64encode(body.model_dump_json().encode()).decode().rstrip("=")


def decode_cursor(cursor: str, *, workspace_id: str, stage: str | None) -> PursuitListKey:
    """The row a cursor resumes after, or `invalid_input` when it is not one of
    this workspace's cursors for this stage."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        body = _CursorBody.model_validate_json(raw)
    except (binascii.Error, ValueError, ValidationError):
        raise _bad_cursor("malformed") from None
    if body.f != _CURSOR_FORMAT:
        raise _bad_cursor("malformed")
    if body.w != workspace_id:
        raise _bad_cursor("other_workspace")
    if body.s != stage:
        raise _bad_cursor("other_filters")
    return PursuitListKey(priority=body.p, updated_at=body.u, id=body.i)


def _bad_cursor(reason: str) -> OperationError:
    return OperationError(
        "invalid_input",
        "This cursor does not continue this list. Read the first page again without it.",
        details={"field": "cursor", "reason": reason},
    )


async def pursuit_page(
    session: AsyncSession, params: PursuitListInput, *, workspace_id: str, postings: bool = True
) -> tuple[PursuitList, str | None]:
    """One page, and the cursor of the next when there may be one. With
    `postings` false each pursuit's opportunity is left out."""
    after = (
        decode_cursor(params.cursor, workspace_id=workspace_id, stage=params.stage)
        if params.cursor is not None
        else None
    )
    # One row past the page says whether another page exists, so a last page
    # that is exactly full does not hand out a cursor to an empty one.
    rows = await list_pursuits(
        session, stage=params.stage, limit=params.limit + 1, after=after, with_revision=True
    )
    page, more = rows[: params.limit], len(rows) > params.limit
    next_cursor = (
        encode_cursor(workspace_id=workspace_id, stage=params.stage, last=page[-1]) if more and page else None
    )
    marks = await pursuit_marks(session, [row["id"] for row in page], now=datetime.now(UTC))
    items = [item_of({**agent_fields(row), **marks[row["id"]]}, postings=postings) for row in page]
    return PursuitList(count=len(items), items=items), next_cursor


async def pursuit_of(session: AsyncSession, opportunity_id: int, *, postings: bool = True) -> PursuitItem:
    row = (
        await session.execute(
            select(Pursuit, Job).join(Job, Job.id == Pursuit.job_id).where(Pursuit.job_id == opportunity_id)
        )
    ).first()
    if row is None:
        raise OperationError(
            "not_found",
            "There is no pursuit for this opportunity.",
            details={"opportunity_id": opportunity_id},
        )
    pursuit, job = row
    return await pursuit_item(session, pursuit, job, postings=postings)


def item_of(fields: dict[str, Any], *, postings: bool) -> PursuitItem:
    """A pursuit as an operation answers it: without its opportunity when
    the person does not share postings."""
    if not postings:
        fields = {key: value for key, value in fields.items() if key != "opportunity"}
    return PursuitItem.model_validate(fields)


def shown(item: PursuitItem, *, postings: bool) -> PursuitItem:
    """`item_of` for a write's answer, fresh or replayed from its receipt,
    which keeps the result whole."""
    return item if postings else item.model_copy(update={"opportunity": MISSING})


def agent_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """`public_pursuit`'s fields as an agent reads them: the opportunity's id
    as `opportunity_id`, and no row id, which no operation takes."""
    record = {key: value for key, value in fields.items() if key not in ("id", "job_id")}
    return {"opportunity_id": fields["job_id"], **record}


def state_of(pursuit: Pursuit, job: Job | None = None) -> dict[str, Any]:
    """A pursuit's agent fields and its revision, from one read of its row."""
    return agent_fields({**public_pursuit(pursuit, job), "revision": pursuit.revision})


async def pursuit_item(session: AsyncSession, pursuit: Pursuit, job: Job | None, *, postings: bool = True) -> PursuitItem:
    marks = await pursuit_marks(session, [pursuit.id], now=datetime.now(UTC))
    return item_of({**state_of(pursuit, job), **marks[pursuit.id]}, postings=postings)


def reread(opportunity_id: int) -> list[NextAction]:
    """What a refused write suggests: read the pursuit again."""
    return [NextAction(operation=PURSUITS_GET.id, arguments={"opportunity_id": opportunity_id})]


def no_pursuit(opportunity_id: int, expected_revision: int) -> OperationError:
    """The refusal of a write that states a revision above 0 for an
    opportunity with no pursuit. It is `not_found`, not a conflict: reading
    again finds nothing newer. The likely cause is a wrong id, so it points
    to the ids and never suggests creating a pursuit, which on a wrong id
    would be a write the person never asked for."""
    return OperationError(
        "not_found",
        "There is no pursuit for this opportunity, so its revision is 0. "
        "Check the id: pursuits.list names each pursuit's opportunity_id.",
        details={"opportunity_id": opportunity_id, "expected_revision": expected_revision, "current_revision": 0},
        next_actions=[NextAction(operation=PURSUITS_LIST.id, arguments={})],
    )


async def _write(
    session: AsyncSession, opportunity_id: int, update: PursuitUpdate, *, actor: Literal["agent"], expected_revision: int | None
) -> PursuitItem:
    try:
        pursuit = await upsert_pursuit(
            session, opportunity_id, update, actor=actor, expected_revision=expected_revision, via=VIA
        )
    except LookupError:
        raise OperationError(
            "not_found", "There is no opportunity with this id.", details={"opportunity_id": opportunity_id}
        ) from None
    except RevisionConflict as conflict:
        if conflict.current != 0:
            raise
        raise no_pursuit(opportunity_id, conflict.expected) from None
    except StepNeedsWords as refused:
        raise OperationError(
            "invalid_input", f"{refused}. Send next_action with it, or add a step with steps.add.",
            details={"field": "next_action", "reason": "missing"},
        ) from None
    job = await session.get(Job, opportunity_id)
    return await pursuit_item(session, pursuit, job)


async def save_pursuit(session: AsyncSession, params: PursuitSaveInput, *, actor: Literal["agent"]) -> PursuitItem:
    update = PursuitUpdate() if params.priority is None else PursuitUpdate(priority=params.priority)
    return await _write(
        session, params.opportunity_id, update, actor=actor, expected_revision=params.if_revision
    )


async def patch_pursuit(session: AsyncSession, params: PursuitPatchInput, *, actor: Literal["agent"]) -> PursuitItem:
    return await _write(
        session, params.opportunity_id, params.update(), actor=actor, expected_revision=params.if_revision
    )


@dataclass(frozen=True)
class PursuitActivity:
    """What a pursuit write lists on the Activity screen: the role it is
    about, and each field it changed with its value before and after.

    `before` reads the pursuit under the role's lock, which the write then
    takes again (the lock is the transaction's), so no other writer lands
    between the two reads."""

    opportunity_id: int
    saving: bool

    async def before(self, session: AsyncSession) -> dict[str, Any] | None:
        await lock_role_writes(session, self.opportunity_id)
        pursuit = await session.scalar(
            select(Pursuit).where(Pursuit.job_id == self.opportunity_id).execution_options(populate_existing=True)
        )
        if pursuit is None:
            return None
        return PursuitState.model_validate(state_of(pursuit)).model_dump(mode="json", include=set(PATCH_FIELDS))

    def entry(self, before: Any, result: BaseModel) -> Changed:
        if not isinstance(result, PursuitItem):
            raise TypeError(f"a pursuit write answers PursuitItem, not {type(result).__name__}")
        after = result.model_dump(mode="json", include=set(PATCH_FIELDS))
        prior: dict[str, Any] = before or {}
        changes = tuple(
            FieldChange(name, prior.get(name), after.get(name))
            for name in PATCH_FIELDS
            if prior.get(name) != after.get(name)
        )
        role = result.opportunity
        facts: dict[str, Any] = (
            {"title": role.title, "company": role.company} if isinstance(role, PursuedOpportunity) else {}
        )
        at = f" {facts['title']} at {facts['company']}" if facts else ""
        if self.saving:
            return Changed(Said("pursuit.saved", f"Saved{at}", facts), changes)
        if any(change.field == "stage" for change in changes):
            stage = after["stage"]
            return Changed(Said("pursuit.moved", f"Moved{at} to {stage}", {**facts, "stage": stage}), changes)
        return Changed(Said("pursuit.changed", f"Updated{at}", facts), changes)

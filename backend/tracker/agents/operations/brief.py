"""The brief for an assistant: what the person wants from a move.

`brief.get` reads it, `brief.patch` changes it part by part, and
`brief.history` lists its versions with who made each and why. Setup writes a
draft and makes it active once the person confirmed it; afterwards a change is
a new version (`tracker/picks/brief.py`).

A patch that carries `run` is the routine's, made with no person present. It
may change what the routine learns from reactions (`pulls`, `tradeoffs`,
`examples`, `proposed_rules`) and nothing else: any other part answers
`needs_the_person`. The engine cannot tell whether a person is present, so
this holds the routine to its contract and is no security boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from pydantic.config import JsonDict
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.activity import Changed, FieldChange, Said
from tracker.agents.operations.descriptor import (
    EngineEffects,
    NoInput,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.receipts import RevisionConflict
from tracker.db.models import PickBrief
from tracker.picks import brief as store
from tracker.picks import runs
from tracker.picks.brief import ID_PREFIX, PARTS, BriefBody, BriefError, Patch, RevisionMoved
from tracker.picks.lock import lock_picks
from tracker.picks.runs import RunError

_CODE: JsonDict = {"x-text": "code"}
_CONTENT: JsonDict = {"x-text": "content"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_TIERS: tuple[ToolTier, ...] = ("standard", "full")


class BriefGetInput(Shape):
    which: Literal["current", "active", "draft"] = Field(
        default="current",
        description="current (the draft when there is one, else the active brief), active, or draft.",
    )
    number: int | None = Field(default=None, ge=1, description="One version by its number, instead of `which`.")
    view: Literal["full", "summary", "schema"] = Field(
        default="full",
        description="summary leaves the parts out: the plain text and the item ids only. schema adds the JSON "
        "Schema every part of a patch is checked against.",
    )


class BriefView(Shape):
    #: False when there is no such brief; every other field is then null or empty.
    exists: bool
    version: int | None = None
    status: Literal["draft", "active", "superseded"] | None = Field(default=None, json_schema_extra=_CODE)
    #: The revision a patch of this brief names in `if_revision`; 0 when it does not exist.
    revision: int = 0
    summary: str | None = Field(default=None, json_schema_extra=_CONTENT)
    reason: str | None = Field(default=None, json_schema_extra=_CONTENT)
    made_by: Literal["person", "routine"] | None = Field(default=None, json_schema_extra=_CODE)
    saved_at: datetime | None = None
    #: The ids of the brief's rules, pulls, trade-offs and proposed rules, by part.
    ids: dict[str, list[str]] = Field(default_factory=dict)
    #: The parts that are saved, in the brief's own order.
    saved_parts: list[str] = Field(default_factory=list, json_schema_extra=_CODE)
    #: Every saved part; left out of the summary view.
    body: dict[str, Any] | None = None
    #: The JSON Schema of the parts, in the schema view only.
    parts_schema: dict[str, Any] | None = None


class BriefPatchInput(Shape):
    if_revision: int = Field(
        ge=0, description="The revision of the brief you read (brief.get); 0 when there is none yet.",
    )
    reason: str = Field(min_length=3, max_length=200, description="One line: why this change.")
    summary: str | None = Field(
        default=None, max_length=2000, description="The whole brief in plain words, at most fifteen lines.",
    )
    target: Literal["draft", "active"] | None = Field(
        default=None,
        description=(
            "draft (start or change the draft) or active (a new active version). Left out: the draft when "
            "there is one, else the active brief."
        ),
    )
    activate: bool = Field(default=False, description="Make the draft the active brief, once the person confirmed it.")
    run: str | None = Field(
        default=None, max_length=24,
        description="The open run this change belongs to. Only the routine gives it, and it may then change "
        "pulls, tradeoffs, examples and proposed_rules only.",
    )
    # Each part is checked against the brief's own schema when the change is
    # applied (`brief.get --view schema` answers it), so this input stays
    # short enough to describe.
    urgency: str | None = Field(default=None, description="not_looking, open, active or between_roles.")
    baseline: dict[str, Any] | None = Field(
        default=None, description="What they hold now: title, level, employer, pay, currency, place, work_mode, keep, missing.",
    )
    rules: list[dict[str, Any]] | None = Field(
        default=None, description="Hard rules: text, and check (a checkable form) or null when only reading can judge.",
    )
    pulls: list[dict[str, Any]] | None = Field(default=None, description="What attracts: text, weight 1 to 3, source.")
    tradeoffs: list[dict[str, Any]] | None = Field(default=None, description="What wins when two pulls conflict: text.")
    targets: dict[str, Any] | None = Field(default=None, description="companies, kinds and avoid, each a list.")
    direction: dict[str, Any] | None = Field(default=None, description="change (true for a new direction) and note.")
    examples: list[dict[str, Any]] | None = Field(
        default=None, description="Postings they reacted to: job, reaction (wanted, unwanted, close), reason.",
    )
    budget: int | None = Field(default=None, description="Picks a month.")
    gaps: list[str] | None = Field(default=None, description="What is not known.")
    calibrated: bool | None = None
    proposed_rules: list[dict[str, Any]] | None = Field(
        default=None, description="Hard rules the routine proposes for the person to decide: text, check, reason.",
    )


class BriefVersion(Shape):
    version: int
    status: Literal["draft", "active", "superseded"] = Field(json_schema_extra=_CODE)
    reason: str = Field(json_schema_extra=_CONTENT)
    made_by: Literal["person", "routine"] = Field(json_schema_extra=_CODE)
    host: str | None = Field(default=None, json_schema_extra=_CODE)
    saved_at: datetime


class BriefHistory(Shape):
    count: int = Field(ge=0)
    #: Newest first.
    versions: list[BriefVersion]


BRIEF_GET = OperationDescriptor(
    id="brief.get",
    summary="Read the person's brief: what they want from a move, with the revision a patch must name.",
    input=BriefGetInput,
    result=BriefView,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
    examples=({}, {"view": "summary"}, {"which": "active"}),
)

BRIEF_PATCH = OperationDescriptor(
    id="brief.patch",
    summary=(
        "Change parts of the brief: a part given replaces that part, a part left out stays. Changing the "
        "active brief makes a new version."
    ),
    input=BriefPatchInput,
    result=BriefView,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
    expects_revision=True,
    examples=(
        {"if_revision": 0, "reason": "Where they stand today.", "urgency": "not_looking",
         "baseline": {"title": "Senior Product Manager", "level": "senior", "pay": 210000}},
        {"if_revision": 4, "reason": "The person confirmed the brief.", "activate": True},
    ),
)

BRIEF_HISTORY = OperationDescriptor(
    id="brief.history",
    summary="List the brief's versions, newest first, with who made each and why.",
    input=NoInput,
    result=BriefHistory,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (BRIEF_GET, BRIEF_PATCH, BRIEF_HISTORY)


def view_of(row: PickBrief | None, *, summary: bool = False) -> BriefView:
    if row is None:
        return BriefView(exists=False)
    body = {part: value for part, value in row.body.items() if part in PARTS}
    return BriefView(
        exists=True, version=row.version,
        status=row.status,  # type: ignore[arg-type]
        revision=row.revision, summary=row.summary, reason=row.reason,
        made_by=row.made_by,  # type: ignore[arg-type]
        saved_at=row.created_at,
        ids={part: [item["id"] for item in body.get(part) or []] for part in ID_PREFIX if body.get(part)},
        saved_parts=[part for part in PARTS if part in body],
        body=None if summary else body,
    )


async def get(session: AsyncSession, params: BriefGetInput) -> BriefView:
    if params.number is not None:
        row = await store.version(session, params.number)
        if row is None:
            raise OperationError(
                "not_found", "The brief has no version by that number.",
                details={"number": params.number}, next_actions=[NextAction(operation=BRIEF_HISTORY.id)],
            )
    else:
        row = await {"current": store.current, "active": store.active, "draft": store.draft}[params.which](session)
    view = view_of(row, summary=params.view == "summary")
    if params.view == "schema":
        view.parts_schema = BriefBody.model_json_schema()
    return view


async def history(session: AsyncSession) -> BriefHistory:
    rows = await store.history(session)
    return BriefHistory(count=len(rows), versions=[
        BriefVersion(
            version=row.version,
            status=row.status,  # type: ignore[arg-type]
            reason=row.reason,
            made_by=row.made_by,  # type: ignore[arg-type]
            host=row.host, saved_at=row.created_at,
        )
        for row in rows
    ])


def refusal(error: BriefError) -> OperationError:
    """A brief change the engine refuses, as the caller reads it."""
    if error.code == "needs_the_person":
        return OperationError("needs_the_person", error.message, details=dict(error.details))
    if error.code == "no_brief":
        return OperationError(
            "not_found", error.message, details={"reason": error.code},
            next_actions=[NextAction(operation=BRIEF_GET.id)],
        )
    return OperationError("invalid_input", error.message, details={"reason": error.code, **error.details})


async def patch(session: AsyncSession, params: BriefPatchInput, *, host: str | None) -> BriefView:
    # The picks lock before the run's row, in the order `picks.decide` takes them.
    await lock_picks(session)
    if params.run is not None:
        try:
            await runs.open_run(session, params.run, datetime.now(UTC))
        except RunError as error:
            raise OperationError(
                "invalid_input", error.message, details={"field": "run", "reason": error.code},
            ) from None
    given = params.model_dump(mode="json", exclude_unset=True)
    try:
        row = await store.patch(session, Patch(
            parts={part: given[part] for part in PARTS if part in given},
            reason=" ".join(params.reason.split()), if_revision=params.if_revision, summary=params.summary,
            target=params.target, activate=params.activate, routine=params.run is not None, host=host,
        ))
    except RevisionMoved as moved:
        raise RevisionConflict(expected=moved.expected, current=moved.current) from None
    except ValidationError as error:
        # Location and kind only: the value can be anything the caller sent.
        raise OperationError(
            "invalid_input", "A part does not match the brief's schema; brief.get with view schema answers it.",
            details={"errors": [
                {"location": [str(part) for part in item.get("loc", ())], "type": str(item.get("type", ""))}
                for item in error.errors()
            ]},
            next_actions=[NextAction(operation=BRIEF_GET.id, arguments={"view": "schema"})],
        ) from None
    except BriefError as error:
        raise refusal(error) from None
    return view_of(row)


@dataclass(frozen=True)
class BriefActivity:
    """What a change of the brief lists on the Activity screen: the parts it
    named, and the brief's status before and after."""

    parts: tuple[str, ...]
    #: The row the change names, as the patch states it; None lets the engine
    #: choose as it does.
    target: str | None = None

    async def before(self, session: AsyncSession) -> str | None:
        """The status of the row the change writes, before it does: the draft
        when it names the draft or the engine would choose it, else the active brief."""
        await lock_picks(session)
        draft, active = await store.draft(session), await store.active(session)
        target = self.target or ("draft" if draft is not None or active is None else "active")
        row = draft if target == "draft" else active
        return row.status if row is not None else None

    def entry(self, before: object, result: BaseModel) -> Changed:
        if not isinstance(result, BriefView):
            raise TypeError(f"a brief change answers BriefView, not {type(result).__name__}")
        activated = result.status == "active" and before != "active"
        english = (
            f"Made your top picks brief active (version {result.version})" if activated
            else f"Changed your top picks brief (version {result.version})"
        )
        changes = (FieldChange("status", before, result.status),) if before != result.status else ()
        return Changed(
            Said("brief.changed", english, {
                "version": result.version, "status": result.status, "made_by": result.made_by,
                "parts": list(self.parts),
            }),
            changes,
        )

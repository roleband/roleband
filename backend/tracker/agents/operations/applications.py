"""`applications.board` and `applications.calendar`: the application pipeline
as the Pipeline tab reads it (`GET /api/applications` and
`GET /api/applications/calendar`).

Both call `tracker.agents.applications`, the reads those routes call, and
answer their cards and items field for field. The board is ordered by stage, in
the pipeline's order, then by job id, so a cursor can continue it; the calendar
keeps its own order, soonest first. A page ends at the tool tier's budget and
`next_cursor` continues it. Paging is live, not a snapshot.

The pipeline is the person's pursuits, the primary category of both reads, so
the switches refuse both when the person does not share it. A board card also
carries its posting's company, title, level and status: when the person does
not share postings those keys are absent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, get_args

from pydantic import AwareDatetime, Field, TypeAdapter
from pydantic.config import JsonDict
from pydantic.experimental.missing_sentinel import MISSING
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents import applications as pipeline
from tracker.agents.operations import cursor
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape, ToolTier
from tracker.agents.operations.envelope import OperationError
from tracker.agents.operations.offer import fitting, size_of
from tracker.agents.operations.search import PAGE_BUDGET_BYTES
from tracker.agents.pursuits import PursuitStage

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")
_STAGE_ORDER = {stage: index for index, stage in enumerate(get_args(PursuitStage))}

InterviewFormat = Literal["video", "phone", "onsite"]
InterviewOutcome = Literal["passed", "not_passed", "cancelled"]

# --- shapes: as `api/schemas/applications.py` answers them ------------------- #


class BoardNextInterview(Shape):
    id: int
    label: str = Field(json_schema_extra=_CONTENT)
    scheduled_at: datetime
    all_day: bool
    format: InterviewFormat | None = Field(json_schema_extra=_CODE)


class BoardCard(Shape):
    """One application as the board shows it, keyed by its opportunity's id."""

    job_id: int
    pursuit_id: int | None
    stage: PursuitStage = Field(json_schema_extra=_CODE)
    priority: int
    #: False for a role moved past Considering whose star was later taken away.
    starred: bool
    #: The posting's facts; the four are absent when the person does not share postings.
    company: str | MISSING = Field(default=MISSING, json_schema_extra=_IDENTIFIER)
    title: str | MISSING = Field(default=MISSING, json_schema_extra=_CONTENT)
    level_band: str | None | MISSING = Field(default=MISSING, json_schema_extra=_CODE)
    posting_status: str | MISSING = Field(default=MISSING, json_schema_extra=_CODE)
    next_action: str | None = Field(json_schema_extra=_CONTENT)
    next_action_due: datetime | None
    #: The soonest round with no outcome, until twelve hours after it began.
    next_interview: BoardNextInterview | None
    comment_count: int
    #: When the application entered its current stage.
    stage_since: datetime | None
    last_activity_at: datetime | None
    #: For an ended application, the stage it ended from.
    ended_at_stage: PursuitStage | None = Field(json_schema_extra=_CODE)


class BoardInput(Shape):
    stage: PursuitStage | None = Field(default=None, description="Only the applications at this stage.")
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page, read with the same stage.",
    )


class ApplicationBoard(Shape):
    #: Every application on the board with this stage filter, on this page or not.
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    #: By stage in the pipeline's order, then by job id.
    applications: list[BoardCard]


class CalendarInterviewEntry(Shape):
    kind: Literal["interview"] = Field(json_schema_extra=_CODE)
    job_id: int
    at: datetime
    interview_id: int
    label: str = Field(json_schema_extra=_CONTENT)
    all_day: bool
    format: InterviewFormat | None = Field(json_schema_extra=_CODE)
    outcome: InterviewOutcome | None = Field(json_schema_extra=_CODE)


class CalendarStepEntry(Shape):
    kind: Literal["step"] = Field(json_schema_extra=_CODE)
    job_id: int
    #: The day the step is due by.
    at: datetime
    step: str = Field(json_schema_extra=_CONTENT)


CalendarItem = Annotated[CalendarInterviewEntry | CalendarStepEntry, Field(discriminator="kind")]
_ITEMS: TypeAdapter[list[CalendarItem]] = TypeAdapter(list[CalendarItem])


class CalendarInput(Shape):
    start: AwareDatetime = Field(description="The span's first instant, with its offset.")
    end: AwareDatetime = Field(
        description=f"The instant the span stops before, with its offset; at most "
        f"{pipeline.CALENDAR_SPAN_MAX.days} days after start.",
    )
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page, read with the same span.",
    )


class ApplicationCalendar(Shape):
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    #: Every interview and dated next step in the span, soonest first. A
    #: cancelled interview and an ended application's step are left out.
    items: list[CalendarItem]


APPLICATIONS_BOARD = OperationDescriptor(
    id="applications.board",
    summary="List the application board: each application's stage, next step and next interview.",
    input=BoardInput,
    result=ApplicationBoard,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit", "public_posting"),
    examples=({"stage": "interviewing"},),
)

APPLICATIONS_CALENDAR = OperationDescriptor(
    id="applications.calendar",
    summary="List the interviews and dated next steps in a span of up to six weeks, soonest first.",
    input=CalendarInput,
    result=ApplicationCalendar,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit",),
    examples=({"start": "2026-11-16T00:00:00+01:00", "end": "2026-11-23T00:00:00+01:00"},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (APPLICATIONS_BOARD, APPLICATIONS_CALENDAR)


# --- reads ------------------------------------------------------------------- #


#: The card keys that belong to the posting rather than the pursuit.
_POSTING_KEYS = frozenset({"company", "title", "level_band", "posting_status"})


async def board(
    session: AsyncSession, params: BoardInput, *, workspace_id: str, postings: bool = True,
    now: datetime | None = None,
) -> tuple[ApplicationBoard, str | None, bool]:
    """The page, its next cursor, and whether the budget ended it early.
    With `postings` false each card leaves its posting's facts out."""
    request = cursor.fingerprint(APPLICATIONS_BOARD.id, workspace_id, {"stage": params.stage})
    offset = 0 if params.cursor is None else cursor.decode(params.cursor, request=request)[0]
    cards = [
        BoardCard.model_validate(card if postings else {k: v for k, v in card.items() if k not in _POSTING_KEYS})
        for card in await pipeline.board(session, now=now or datetime.now(UTC))
        if params.stage is None or card["stage"] == params.stage
    ]
    cards.sort(key=lambda card: (_STAGE_ORDER[card.stage], card.job_id))
    page = ApplicationBoard(total=len(cards), count=0, applications=[])
    rest = cards[offset:]
    page.applications = rest[:fitting(rest, PAGE_BUDGET_BYTES[params.tier] - size_of(page))]
    page.count = len(page.applications)
    end = offset + page.count
    next_cursor = cursor.encode(request=request, offset=end) if end < len(cards) else None
    return page, next_cursor, next_cursor is not None


async def calendar(
    session: AsyncSession, params: CalendarInput, *, workspace_id: str
) -> tuple[ApplicationCalendar, str | None, bool]:
    """The page, its next cursor, and whether the budget ended it early."""
    if params.end <= params.start:
        raise OperationError(
            "invalid_input", "end must come after start.", details={"field": "end", "reason": "before_start"}
        )
    if params.end - params.start > pipeline.CALENDAR_SPAN_MAX:
        raise OperationError(
            "invalid_input",
            f"A span covers at most {pipeline.CALENDAR_SPAN_MAX.days} days; read a longer one in parts.",
            details={"field": "end", "reason": "span_too_long"},
        )
    request = cursor.fingerprint(
        APPLICATIONS_CALENDAR.id, workspace_id,
        {"start": params.start.astimezone(UTC).isoformat(), "end": params.end.astimezone(UTC).isoformat()},
    )
    offset = 0 if params.cursor is None else cursor.decode(params.cursor, request=request)[0]
    items = _ITEMS.validate_python(await pipeline.calendar(session, start=params.start, end=params.end))
    page = ApplicationCalendar(total=len(items), count=0, items=[])
    rest = items[offset:]
    page.items = rest[:fitting(rest, PAGE_BUDGET_BYTES[params.tier] - size_of(page))]
    page.count = len(page.items)
    end = offset + page.count
    next_cursor = cursor.encode(request=request, offset=end) if end < len(items) else None
    return page, next_cursor, next_cursor is not None

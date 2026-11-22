"""Response contracts for the application pipeline's routes.

`GET /api/applications`, `GET /api/applications/{job_id}`, its activity, and the
comment, interview and next-step writes under `/api/jobs/{job_id}/pursuit/`. An
application is keyed by its job id: a star with no pursuit row is a card at
Considering whose `pursuit_id` is null.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from tracker.agents.pursuits import StepAction
from tracker.api.schemas.base import Built
from tracker.api.schemas.jobs import PursuitStage
from tracker.api.schemas.text_class import text

InterviewFormat = Literal["video", "phone", "onsite"]
InterviewOutcome = Literal["passed", "not_passed", "cancelled"]
Actor = Literal["user", "agent"]


class ApplicationCardInterview(Built):
    """A round as the card names it."""

    id: int
    label: str = Field(json_schema_extra=text("content"))
    scheduled_at: datetime
    all_day: bool
    format: InterviewFormat | None
    #: Where the round is held: a call's address, as the person entered it.
    link: str | None = Field(json_schema_extra=text("identifier"))


class ApplicationStep(Built):
    """One next step the person owes."""

    id: int
    text: str = Field(json_schema_extra=text("content"))
    #: The day it is due by; none for a step with no day.
    due: datetime | None
    created_at: datetime
    #: When it was ticked done; none while it is open.
    done_at: datetime | None


class ApplicationCard(Built):
    """One application as the board shows it."""

    job_id: int
    pursuit_id: int | None
    stage: PursuitStage
    #: 5 Urgent, 4 High, 3 Medium, 2 Low, 1 No priority.
    priority: int
    #: False until a priority is chosen: the role reads as having none, whatever
    #: the stored number.
    priority_set: bool
    #: False for a role moved past Considering whose star was later taken away.
    starred: bool
    company: str = Field(json_schema_extra=text("code"))
    title: str = Field(json_schema_extra=text("content"))
    level_band: str | None = Field(json_schema_extra=text("code"))
    posting_status: str = Field(json_schema_extra=text("code"))
    #: The first of `steps`, for a reader that shows one step.
    next_action: str | None = Field(json_schema_extra=text("content"))
    next_action_due: datetime | None
    #: Every open next step, soonest first; steps with no day last, in the order added.
    steps: list[ApplicationStep]
    #: The soonest round with no outcome, until twelve hours after it began.
    next_interview: ApplicationCardInterview | None
    #: The latest round that has taken place with no outcome given: a timed
    #: round once it began, an all-day round once its day is over. In the
    #: hours after it began it is also `next_interview`.
    awaiting_outcome: ApplicationCardInterview | None
    comment_count: int
    #: When the application entered its current stage.
    stage_since: datetime | None
    last_activity_at: datetime | None
    #: For an ended application, the stage it ended from.
    ended_at_stage: PursuitStage | None


class ApplicationBoardResponse(Built):
    """`GET /api/applications`: every application, in no particular order."""

    applications: list[ApplicationCard]


class ApplicationInterview(Built):
    id: int
    label: str = Field(json_schema_extra=text("content"))
    scheduled_at: datetime
    all_day: bool
    format: InterviewFormat | None
    link: str | None = Field(json_schema_extra=text("identifier"))
    outcome: InterviewOutcome | None
    notes: str | None = Field(json_schema_extra=text("content"))
    created_at: datetime
    updated_at: datetime


class StageReached(Built):
    stage: PursuitStage
    #: The latest time the application entered this stage.
    at: datetime


class ApplicationDetailResponse(Built):
    """`GET /api/applications/{job_id}`: interviews newest first, stages in the order reached."""

    application: ApplicationCard
    interviews: list[ApplicationInterview]
    stages_reached: list[StageReached]


class ApplicationComment(Built):
    kind: Literal["comment"] = "comment"
    id: int
    created_at: datetime
    actor: Actor
    source: str = Field(json_schema_extra=text("code"))
    body: str = Field(json_schema_extra=text("content"))
    edited_at: datetime | None


class EventStep(Built):
    id: int
    action: StepAction
    #: The step's words and day after the write; before it, for a removed step.
    text: str = Field(json_schema_extra=text("content"))
    due: datetime | None


class ApplicationEvent(Built):
    kind: Literal["event"] = "event"
    id: int
    created_at: datetime
    actor: Actor
    source: str = Field(json_schema_extra=text("code"))
    event_type: str = Field(json_schema_extra=text("code"))
    from_stage: PursuitStage | None
    to_stage: PursuitStage
    #: The fields this write changed, by name; `steps` when it wrote a next step.
    changed: list[str]
    #: The next step this write added, changed, ticked, opened again or removed.
    step: EventStep | None = None


ActivityItem = Annotated[ApplicationComment | ApplicationEvent, Field(discriminator="kind")]


class ApplicationActivityResponse(Built):
    """`GET /api/applications/{job_id}/activity`: newest first. Pass the
    number of items already read as `offset` for the page after it."""

    items: list[ActivityItem]


class ApplicationCommentResponse(Built):
    comment: ApplicationComment


class ApplicationInterviewResponse(Built):
    interview: ApplicationInterview


class ApplicationStepResponse(Built):
    step: ApplicationStep


class ApplicationDeleted(Built):
    id: int
    deleted: bool


class CalendarInterview(Built):
    kind: Literal["interview"] = "interview"
    job_id: int
    at: datetime
    interview_id: int
    label: str = Field(json_schema_extra=text("content"))
    all_day: bool
    format: InterviewFormat | None
    link: str | None = Field(json_schema_extra=text("identifier"))
    outcome: InterviewOutcome | None


class CalendarStep(Built):
    kind: Literal["step"] = "step"
    job_id: int
    step_id: int
    #: The day the step is due by.
    at: datetime
    step: str = Field(json_schema_extra=text("content"))


CalendarItem = Annotated[CalendarInterview | CalendarStep, Field(discriminator="kind")]


class ApplicationCalendarResponse(Built):
    """`GET /api/applications/calendar`: every interview and dated next step in
    the span, soonest first. A cancelled interview and an ended application's
    step are left out; an item names its application by job id."""

    items: list[CalendarItem]

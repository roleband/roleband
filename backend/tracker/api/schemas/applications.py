"""Response contracts for the application pipeline's routes.

`GET /api/applications`, `GET /api/applications/{job_id}`, its activity, and the
comment and interview writes under `/api/jobs/{job_id}/pursuit/`. An
application is keyed by its job id: a star with no pursuit row is a card at
Considering whose `pursuit_id` is null.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from tracker.api.schemas.base import Built
from tracker.api.schemas.jobs import PursuitStage
from tracker.api.schemas.text_class import text

InterviewFormat = Literal["video", "phone", "onsite"]
InterviewOutcome = Literal["passed", "not_passed", "cancelled"]
Actor = Literal["user", "agent"]


class ApplicationNextInterview(Built):
    id: int
    label: str = Field(json_schema_extra=text("content"))
    scheduled_at: datetime
    all_day: bool
    format: InterviewFormat | None


class ApplicationCard(Built):
    """One application as the board shows it."""

    job_id: int
    pursuit_id: int | None
    stage: PursuitStage
    priority: int
    #: False for a role moved past Considering whose star was later taken away.
    starred: bool
    company: str = Field(json_schema_extra=text("code"))
    title: str = Field(json_schema_extra=text("content"))
    level_band: str | None = Field(json_schema_extra=text("code"))
    posting_status: str = Field(json_schema_extra=text("code"))
    next_action: str | None = Field(json_schema_extra=text("content"))
    next_action_due: datetime | None
    #: The soonest round with no outcome, until twelve hours after it began.
    next_interview: ApplicationNextInterview | None
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


class ApplicationEvent(Built):
    kind: Literal["event"] = "event"
    id: int
    created_at: datetime
    actor: Actor
    source: str = Field(json_schema_extra=text("code"))
    event_type: str = Field(json_schema_extra=text("code"))
    from_stage: PursuitStage | None
    to_stage: PursuitStage
    #: The fields this write changed, by name.
    changed: list[str]


ActivityItem = Annotated[ApplicationComment | ApplicationEvent, Field(discriminator="kind")]


class ApplicationActivityResponse(Built):
    """`GET /api/applications/{job_id}/activity`: newest first. Pass the
    number of items already read as `offset` for the page after it."""

    items: list[ActivityItem]


class ApplicationCommentResponse(Built):
    comment: ApplicationComment


class ApplicationInterviewResponse(Built):
    interview: ApplicationInterview


class ApplicationDeleted(Built):
    id: int
    deleted: bool

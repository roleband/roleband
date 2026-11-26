"""Response shapes of the Top picks routes the dashboard reads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from tracker.api.schemas.base import Built
from tracker.api.schemas.text_class import text
from tracker.settings_store import DAILY_CAP_MAX


class PickReason(Built):
    """One reason of a pick: `opening` then `rest` reads as the sentence."""

    opening: str | None = Field(json_schema_extra=text("record"))
    rest: str = Field(json_schema_extra=text("record"))


class RemovedPick(Built):
    job_id: int
    title: str = Field(json_schema_extra=text("content"))
    company: str = Field(json_schema_extra=text("content"))
    company_slug: str = Field(json_schema_extra=text("identifier"))
    is_open: bool
    reasons: list[PickReason]
    #: Why the person removed it: a reason code, their own words, both or neither.
    reason: str | None = Field(json_schema_extra=text("code"))
    reason_text: str | None = Field(json_schema_extra=text("record"))
    removed_at: datetime
    judged_at: datetime


class RemovedPicksResponse(Built):
    """`GET /api/picks/removed`: the picks the person marked Not for me,
    newest verdict first. `DELETE /api/jobs/{job_id}/feedback` puts one back."""

    picks: list[RemovedPick]


class LastCheck(Built):
    """The newest closed run of the routine."""

    host: str | None = Field(json_schema_extra=text("code"))
    finished_at: datetime
    outcome: Literal["finished", "stopped", "abandoned"] = Field(json_schema_extra=text("code"))
    #: Why it stopped, in the assistant's words, when it did not finish.
    note: str | None = Field(json_schema_extra=text("record"))


class PicksStateResponse(Built):
    """`GET /api/picks/state`: what the rail and the Settings card read."""

    state: Literal["never_set_up", "on", "off"] = Field(json_schema_extra=text("code"))
    #: The assistant that runs the checks, and when it runs them, in its own words.
    routine_host: str | None = Field(json_schema_extra=text("code"))
    schedule: str | None = Field(json_schema_extra=text("record"))
    last_check: LastCheck | None
    #: What the person is looking for, in plain words; null while there is no active brief.
    brief_summary: str | None = Field(json_schema_extra=text("record"))
    #: A pick was made since the person last opened Top picks. Never a count.
    unseen_pick: bool
    #: Whether the checks are doing their job: `late` when roles have waited
    #: more than a day and a half with no check finished in that time.
    health: Literal["off", "healthy", "never_ran", "late", "stopped_early"] = Field(json_schema_extra=text("code"))
    #: Roles waiting to be read now.
    waiting: int
    #: Roles read in the last seven days, and those of them not picked.
    read_this_week: int
    passed_this_week: int
    #: What the routine host's own files say of its connection: `connected`,
    #: `outdated` (an older skill), `rule_missing` (it asks before each
    #: command) or `read_only`. Null when no host runs the routine, or the
    #: host is no longer connected.
    routine_host_connection: Literal["connected", "outdated", "rule_missing", "read_only"] | None = Field(
        json_schema_extra=text("code"),
    )
    #: The most roles read in a day, and the most it can be set to.
    daily_limit: int
    daily_limit_max: int


class PicksModeInput(BaseModel):
    """What the Settings card changes: either part, or both."""

    state: Literal["on", "off"] | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=DAILY_CAP_MAX)


class PicksRemovedResponse(Built):
    """`DELETE /api/picks/setup`: how much was deleted."""

    briefs: int
    readings: int
    documents: int
    #: Past verdicts whose reasons were cleared.
    verdicts: int

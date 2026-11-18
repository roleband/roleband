"""Response contract of the Activity screen's list (`/api/agent-activity`)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from tracker.api.schemas.base import Built
from tracker.api.schemas.text_class import text


class ActivityFieldChange(Built):
    """One field a change touched. A value is JSON as the record stored it;
    `before` is null for a field the record did not have yet."""

    field: str = Field(json_schema_extra=text("code"))
    before: Any
    after: Any


class ActivityEntry(Built):
    id: int
    occurred_at: datetime
    #: The operation's dotted id (`pursuits.patch`).
    operation: str = Field(json_schema_extra=text("identifier"))
    kind: Literal["read", "change", "refused"]
    #: The data categories it read; for a refusal, the one it asked for.
    categories: list[str] = Field(json_schema_extra=text("code"))
    action_group: str | None = Field(json_schema_extra=text("code"))
    refusal: str | None = Field(json_schema_extra=text("code"))
    #: The entry in English, as it was recorded: the fallback for a topic the
    #: client cannot word.
    summary: str = Field(json_schema_extra=text("record"))
    #: The facts the summary is said from: `topic` (a code) and its values,
    #: such as a role's `title` and `company`, a `count` or a `stage` slug.
    subject: dict[str, Any]
    changes: list[ActivityFieldChange]
    #: The app the call ran under; null on an entry recorded before calls named one.
    host: Literal["claude-code", "codex", "other"] | None


class ActivityPageResponse(Built):
    items: list[ActivityEntry]
    #: Reads the next, older page; null on the last one.
    next_cursor: str | None = Field(json_schema_extra=text("identifier"))

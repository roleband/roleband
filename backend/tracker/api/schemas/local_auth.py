"""Native browser handoff wire shapes."""

from __future__ import annotations

from pydantic import Field

from tracker.api.schemas.base import Built
from tracker.api.schemas.text_class import text


class BrowserTicket(Built):
    url: str = Field(json_schema_extra=text("identifier"))
    expires_in: int


class BrowserExchange(Built):
    ticket: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]{64}$", json_schema_extra=text("identifier"))


class BrowserSession(Built):
    key_id: str = Field(json_schema_extra=text("identifier"))
    secret: str = Field(json_schema_extra=text("identifier"))
    origin: str = Field(json_schema_extra=text("identifier"))

"""Request and response contract for view choices: how the person arranged
what the screens show. The store names the choices and holds each one's form
(`settings_store.VIEW_CHOICES`); the dashboard decides what a choice means."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from tracker.api.schemas.text_class import text


class ViewChoices(BaseModel):
    """Every choice the person has made, by name; a choice absent here shows
    the screen's own default."""

    choices: dict[str, JsonValue]


class ViewChoiceWrite(BaseModel):
    """One choice's new value."""

    model_config = ConfigDict(extra="forbid")

    value: JsonValue


class ViewChoice(BaseModel):
    """One choice as stored: duplicates dropped, in the order given."""

    name: str = Field(json_schema_extra=text("code"))
    value: JsonValue

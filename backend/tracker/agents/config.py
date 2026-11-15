"""Validated agent/MCP configuration persisted in `app_settings`.

The `agent_access` row holds the two switches the Settings screen shows and,
beside them, the person's choice for each data category
(`docs/decisions/0017-agent-access-open-by-default.md`). A category with no
choice stored reads as open. A row this model cannot read reads as every
switch off, so a bad write never opens access.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, StrictBool
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import DataClass
from tracker.db.models import AppSetting

AGENT_ACCESS_KEY = "agent_access"

#: Who may read a category: any model, models on this computer only, or none.
CategoryChoice = Literal["any_model", "local_only", "not_shared"]


class AgentAccessConfig(BaseModel):
    enabled: StrictBool = False
    allow_writes: StrictBool = False
    #: The person's choice per data category; a category left out is open.
    categories: dict[DataClass, CategoryChoice] = {}


async def get_agent_access(session: AsyncSession) -> AgentAccessConfig:
    row = await session.get(AppSetting, AGENT_ACCESS_KEY)
    return _read(row.value if row is not None else None)


def _read(value: object) -> AgentAccessConfig:
    if not isinstance(value, dict):
        return AgentAccessConfig()
    try:
        return AgentAccessConfig.model_validate(value)
    except ValueError:
        return AgentAccessConfig()


async def set_agent_access(
    session: AsyncSession, config: AgentAccessConfig
) -> AgentAccessConfig:
    """Store `config`. A payload that does not name `categories` keeps the
    stored choices, so the Settings screen's two switches never reset them.

    The row is locked from the read of the stored choices to the write, so a
    save of the switches alone cannot put back choices another save changed
    in between. The row is created first when there is none, so the first two
    saves serialize on it too. Answers the row as the engine reads it.
    """
    value = config.model_dump(mode="json")
    if "categories" not in config.model_fields_set:
        value["categories"] = await _locked_categories(session)
    stmt = insert(AppSetting).values(key=AGENT_ACCESS_KEY, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppSetting.key], set_={"value": value}
    )
    await session.execute(stmt)
    return _read(value)


async def _locked_categories(session: AsyncSession) -> object:
    """The stored choices as stored, with the row locked until the transaction
    ends. Choices the engine cannot read are kept as they are, so the row still
    reads as everything off: read as no choices, they would share every
    category the person had kept back."""
    await session.execute(
        insert(AppSetting)
        .values(key=AGENT_ACCESS_KEY, value=AgentAccessConfig().model_dump(mode="json"))
        .on_conflict_do_nothing(index_elements=[AppSetting.key])
    )
    stored = await session.scalar(
        select(AppSetting.value).where(AppSetting.key == AGENT_ACCESS_KEY).with_for_update()
    )
    return stored.get("categories", {}) if isinstance(stored, dict) else {}

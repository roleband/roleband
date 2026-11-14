"""`radar.summary`: how many roles are open and saved, and where the pursuits stand.

Every count comes from the query that owns it: open roles from the Board's
open-in-scope count over the companies on the Board, overdue follow-ups from the
notification clause, so this answer and the dashboard's cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import (
    EngineEffects,
    NoInput,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.pursuits import PursuitStage
from tracker.company_store import off_board_company_slugs
from tracker.db.models import Favorite, Pursuit
from tracker.db.queries.jobs import open_in_scope_count_stmt
from tracker.notifications.pursuit_due import overdue_pursuit_clause

_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")


class RadarSummary(Shape):
    #: Open, in-scope postings at the companies on the Board, one per place set.
    open_opportunities: int = Field(ge=0)
    saved_opportunities: int = Field(ge=0)
    #: Every pursuit, at any stage.
    active_pursuits: int = Field(ge=0)
    #: Pursuits whose next action fell due and is not done.
    overdue_next_actions: int = Field(ge=0)
    #: Only the stages that hold a pursuit.
    pursuits_by_stage: dict[PursuitStage, int]


RADAR_SUMMARY = OperationDescriptor(
    id="radar.summary",
    summary="Count the open and saved roles, the pursuits by stage and the follow-ups overdue.",
    input=NoInput,
    result=RadarSummary,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("market_statistic", "private_pursuit"),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (RADAR_SUMMARY,)


async def radar_summary(session: AsyncSession, *, now: datetime) -> RadarSummary:
    open_count = await session.scalar(open_in_scope_count_stmt(await off_board_company_slugs(session)))
    saved_count = await session.scalar(select(func.count(Favorite.id)))
    pursuit_count = await session.scalar(select(func.count(Pursuit.id)))
    overdue_count = await session.scalar(select(func.count(Pursuit.id)).where(overdue_pursuit_clause(now)))
    stages = (await session.execute(select(Pursuit.stage, func.count(Pursuit.id)).group_by(Pursuit.stage))).all()
    return RadarSummary(
        open_opportunities=open_count or 0,
        saved_opportunities=saved_count or 0,
        active_pursuits=pursuit_count or 0,
        overdue_next_actions=overdue_count or 0,
        pursuits_by_stage={stage: count for stage, count in stages},
    )

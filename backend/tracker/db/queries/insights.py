"""The scope an Insights view is narrowed to: which companies, which
disciplines. Applied on top of the roles Insights describes
(`jobs.insights_role_conds`).

Two companies sides: the Other companies set (followed through the wider-market
sweep, `company_directory.FOLLOWED_WITH_SET`) and every company the person
picked (the curated list, a sector, a careers link). The Other companies
can far outnumber the picked ones, so an unscoped ranking is a long tail; the scope is
how a tab is read for one side.

One object answers both query styles the statistics reads use: ORM conditions
(`conds`) and a raw-SQL fragment with its parameters (`sql`), so a raw read
cannot narrow differently from an ORM one.

A scope's history starts at the first read that saw a whole listing of one of
its companies (`history_since`): no opening before it can be dated
(`db/arrival.py`), so no window reaches back further.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.company_directory import FOLLOWED_WITH_SET
from tracker.connectors.recipes.outcome import SourceOutcome
from tracker.db.models import Job, ScrapeSourceRun, TrackedCompany

Side = Literal["all", "yours", "other"]
SIDES: tuple[Side, ...] = ("all", "yours", "other")


@dataclass(frozen=True)
class InsightsScope:
    side: Side = "all"
    families: tuple[str, ...] = ()
    #: The Other companies' slugs; resolved only when `side` needs them.
    other: frozenset[str] = frozenset()

    @property
    def narrowed(self) -> bool:
        return self.side != "all" or bool(self.families)

    def conds(self, company: Any = Job.company, family: Any = Job.family) -> list:
        """ORM conditions on a company and a family column (any table's)."""
        out: list = []
        if self.side == "other":
            out.append(company.in_(sorted(self.other)))
        elif self.side == "yours" and self.other:
            out.append(company.notin_(sorted(self.other)))
        if self.families:
            out.append(family.in_(self.families))
        return out

    def company_conds(self, company: Any) -> list:
        """The companies half alone, for a table with no family column."""
        return InsightsScope(self.side, (), self.other).conds(company=company)

    def sql(self, alias: str = "") -> tuple[str, dict[str, Any]]:
        """`(" AND ...", params)` for a raw-SQL read over `jobs` (`alias` = "j.")."""
        parts: list[str] = []
        params: dict[str, Any] = {}
        if self.side == "other":
            parts.append(f"{alias}company = ANY(cast(:scope_companies AS text[]))")
            params["scope_companies"] = sorted(self.other)
        elif self.side == "yours" and self.other:
            parts.append(f"{alias}company <> ALL(cast(:scope_companies AS text[]))")
            params["scope_companies"] = sorted(self.other)
        if self.families:
            parts.append(f"{alias}family = ANY(cast(:scope_families AS text[]))")
            params["scope_families"] = list(self.families)
        return "".join(f" AND {p}" for p in parts), params


async def resolve_insights_scope(
    session: AsyncSession, side: Side = "all", families: list[str] | None = None
) -> InsightsScope:
    other: frozenset[str] = frozenset()
    if side != "all":
        other = frozenset(
            (
                await session.scalars(
                    select(TrackedCompany.slug).where(TrackedCompany.source == FOLLOWED_WITH_SET)
                )
            ).all()
        )
    return InsightsScope(side=side, families=tuple(sorted(set(families or []))), other=other)


async def history_since(session: AsyncSession, scope: InsightsScope, hidden: list[str]) -> datetime | None:
    """When the history of the scope's companies starts: the start of the first
    read of one of them that saw its whole listing (`list_complete`, or a board
    proven `empty`), off-board companies aside, so what that read found is
    inside it. None before any such read. A partial read never starts it: what
    it missed may have been listed all along."""
    stmt = select(func.min(ScrapeSourceRun.started_at)).where(
        or_(ScrapeSourceRun.list_complete.is_(True), ScrapeSourceRun.outcome == SourceOutcome.EMPTY.value),
        *scope.company_conds(ScrapeSourceRun.company_slug),
    )
    if hidden:
        stmt = stmt.where(ScrapeSourceRun.company_slug.notin_(hidden))
    return await session.scalar(stmt)


def window_since(history: datetime | None, days: int, now: datetime) -> datetime | None:
    """The start of what a window of `days` covers (`days <= 0` is all time):
    the window's own start, or the history's when the history is shorter."""
    cutoff = None if days <= 0 else now - timedelta(days=days)
    if history is None or cutoff is None:
        return cutoff or history
    return max(cutoff, history)


def history_days(history: datetime | None, now: datetime) -> int:
    """Whole days of history at `now`."""
    return 0 if history is None else max(0, (now - history).days)

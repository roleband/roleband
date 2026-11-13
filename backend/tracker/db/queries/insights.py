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

A scope's history starts where one of its companies became known
(`history_since`): no opening before it can be dated (`db/arrival.py`), so no
window reaches back further.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.company_directory import FOLLOWED_WITH_SET
from tracker.connectors.recipes.outcome import SourceOutcome
from tracker.db.arrival import KNOWN_AFTER_PARTIAL_READS, PARTIAL_EVIDENCE
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
    """When the history of the scope's companies starts: the first read after
    which one of them was known, by the rule that dates a posting's arrival
    (`db/arrival.py`), off-board companies aside. That is a read that saw
    its whole listing (`list_complete`, or a board proven `empty`), or, for a
    source whose reads stop at our own ceilings, the second such read that
    kept postings. It starts at that read's start, so what the read found is
    inside it. None before any such read: until then no arrival is dated."""
    companies = [*scope.company_conds(ScrapeSourceRun.company_slug)]
    if hidden:
        companies.append(ScrapeSourceRun.company_slug.notin_(hidden))
    whole = select(func.min(ScrapeSourceRun.started_at)).where(
        or_(ScrapeSourceRun.list_complete.is_(True), ScrapeSourceRun.outcome == SourceOutcome.EMPTY.value),
        *companies,
    )
    partial = (
        select(
            ScrapeSourceRun.started_at,
            func.row_number()
            .over(partition_by=ScrapeSourceRun.company_slug, order_by=ScrapeSourceRun.finished_at)
            .label("n"),
        )
        .where(
            ScrapeSourceRun.outcome.in_([outcome.value for outcome in PARTIAL_EVIDENCE]),
            ScrapeSourceRun.kept > 0,
            *companies,
        )
        .subquery()
    )
    known = select(func.min(partial.c.started_at)).where(partial.c.n == KNOWN_AFTER_PARTIAL_READS)
    # `least` skips a NULL: either way of becoming known starts the history.
    return await session.scalar(select(func.least(whole.scalar_subquery(), known.scalar_subquery())))


def window_since(history: datetime | None, days: int, now: datetime) -> datetime | None:
    """The start of what a window of `days` covers (`days <= 0` is all time):
    the window's own start, or the history's when the history is shorter.
    None before the history starts: there is none for a window to cover."""
    if history is None:
        return None
    if days <= 0:
        return history
    return max(now - timedelta(days=days), history)


def history_days(history: datetime | None, now: datetime) -> int:
    """Whole days of history at `now`."""
    return 0 if history is None else max(0, (now - history).days)

"""The queue: the postings worth an assistant's judgment, as one query.

The queue is never stored. It is the Board's own open, visible set
(`db/queries/jobs.apply_job_filters`: open, in scope, at a followed company,
not marked Not for me, one row per place set), so a posting the Board would
not show is never judged, narrowed by what only this mode knows:

1. one posting per duplicate stack, the newest open one;
2. no posting whose case is closed: it, or another posting of its stack or
   place set, has a verdict for its current text (a trial takes every open
   one, judged or not);
3. no posting a checkable hard rule rules out.

A role that was already open when the mode was turned on is in the queue like
any other, so the first runs read the Board as it stands, a day's limit at a
time. The rest is ordered by fit, best first. Fit orders the work and never
cuts it: a low-fit posting is judged later, not dropped.

A newer brief does not reopen every case. It takes a second look at the picks
the person has not reacted to, at recent near misses, and at recent postings
passed as no better than what the person holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, not_, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from tracker.company_store import off_board_company_slugs
from tracker.db.models import Favorite, Job, JobFeedback, PickVerdict, Pursuit
from tracker.db.queries.jobs import apply_job_filters, listed_since
from tracker.lineage.counts import is_new_job_clause, place_set_member_in
from tracker.picks.brief import BriefBody, checkable_rules
from tracker.picks.rules import excludes, ruled_out
from tracker.platform.local_zone import local_zone
from tracker.search.fit import fit_expr
from tracker.semantic.intent import build_intent_vector
from tracker.settings_store import get_intent_embedding

#: How long a near miss, or a posting passed as no better, stays open to a
#: second look under a newer brief.
SECOND_LOOK_DAYS = 14
#: The days of arrivals the expected daily volume is read from.
VOLUME_DAYS = 21
#: The most postings a trial is handed.
TRIAL_CAP = 30

_PEER = aliased(Job)
_JUDGED = aliased(Job)


async def board_filters(session: AsyncSession) -> dict[str, Any]:
    """The Board's standing view of open roles, as `apply_job_filters` takes it."""
    return {"status": "open", "hidden": list(await off_board_company_slugs(session))}


def _reacted(job_id: Any) -> ColumnElement[bool]:
    return or_(
        job_id.in_(select(Favorite.job_id)),
        job_id.in_(select(Pursuit.job_id)),
        job_id.in_(select(JobFeedback.job_id)),
    )


def closed_cases(active_version: int, now: datetime) -> Select[Any]:
    """Ids of the postings whose current text has a verdict that stands.

    A verdict made under an older brief stops standing where that brief's
    change could turn the answer: see the module's last paragraph."""
    recent = now - timedelta(days=SECOND_LOOK_DAYS)
    second_look = and_(
        PickVerdict.brief_version < active_version,
        or_(
            and_(PickVerdict.verdict == "pick", not_(_reacted(PickVerdict.job_id))),
            and_(PickVerdict.verdict == "near_miss", PickVerdict.created_at >= recent),
            and_(
                PickVerdict.verdict == "pass", PickVerdict.pass_code == "not_better", _JUDGED.first_seen >= recent,
            ),
        ),
    )
    return (
        select(PickVerdict.job_id)
        .join(_JUDGED, _JUDGED.id == PickVerdict.job_id)
        .where(
            PickVerdict.trial.is_(False),
            PickVerdict.superseded_at.is_(None),
            PickVerdict.content_hash == func.coalesce(_JUDGED.content_hash, ""),
            not_(second_look),
        )
    )


def _newer_in_stack(filters: dict[str, Any]) -> ColumnElement[bool]:
    """Another posting of this one's duplicate stack that the Board shows is
    newer. A newer posting the Board does not show (marked Not for me, closed)
    never stands in for one it does."""
    on_board = apply_job_filters(select(Job.id), filters).correlate(None)
    return exists().where(
        Job.lineage_id.isnot(None),
        _PEER.lineage_id == Job.lineage_id,
        _PEER.id.in_(on_board),
        tuple_(func.coalesce(_PEER.lineage_seq, 0), _PEER.id) > tuple_(func.coalesce(Job.lineage_seq, 0), Job.id),
    )


def _case_closed(active_version: int, now: datetime) -> ColumnElement[bool]:
    closed = closed_cases(active_version, now)
    stack = aliased(Job)
    return or_(
        place_set_member_in(closed),
        exists().where(Job.lineage_id.isnot(None), stack.lineage_id == Job.lineage_id, stack.id.in_(closed)),
    )


def candidates(
    filters: dict[str, Any], *, trial: bool, active_version: int, now: datetime,
) -> Select[Any]:
    """The postings an assistant would be asked about before any hard rule:
    steps 1 and 2 of the module's list."""
    stmt = apply_job_filters(select(Job), filters).where(not_(_newer_in_stack(filters)))
    if trial:
        return stmt
    return stmt.where(not_(_case_closed(active_version, now)))


@dataclass(frozen=True)
class QueueCounts:
    #: Candidates no checkable rule rules out.
    waiting: int = 0
    ruled_out_by_rules: int = 0
    #: How many candidates each checkable rule rules out, by rule id. A posting
    #: two rules rule out counts under both.
    by_rule: dict[str, int] = field(default_factory=dict)
    #: Since when the longest-waiting candidate has waited for a judgment.
    oldest_waiting_since: datetime | None = None


async def counts(
    session: AsyncSession, stmt: Select[Any], body: BriefBody, *, since: datetime | None = None,
) -> QueueCounts:
    """What the rules of `body` leave of the candidates `stmt`, and what each
    removes. A role waits from when it was first seen, or from `since` (when
    the mode was turned on) if it was open before: a role open for months has
    not waited months for a judge that did not exist."""
    ids = stmt.with_only_columns(Job.id).subquery()
    rules = checkable_rules(body)
    out = ruled_out(body)
    waiting_from = func.greatest(Job.first_seen, since) if since is not None else Job.first_seen
    row = (await session.execute(
        select(
            func.count().filter(not_(out)),
            func.count().filter(out),
            func.min(waiting_from).filter(not_(out)),
            *(func.count().filter(excludes(rule)) for rule in rules),
        ).select_from(Job).where(Job.id.in_(select(ids.c.id)))
    )).one()
    return QueueCounts(
        waiting=row[0] or 0,
        ruled_out_by_rules=row[1] or 0,
        oldest_waiting_since=row[2],
        by_rule={str(rule.id): row[3 + index] or 0 for index, rule in enumerate(rules)},
    )


async def best_first(session: AsyncSession, stmt: Select[Any], body: BriefBody, *, limit: int) -> list[Job]:
    """The first `limit` candidates of `stmt` no rule of `body` rules out, best
    fit first. Without an intent to rank by, the newest listing comes first; a
    posting with no embedding is ranked last, never dropped."""
    if limit <= 0:
        return []
    kept = stmt.where(not_(ruled_out(body)))
    stored = await get_intent_embedding(session)
    intent = await build_intent_vector(session, stored["vector"] if stored else None)
    order = [fit_expr(intent).desc().nullslast()] if intent is not None else []
    return list((await session.scalars(kept.order_by(*order, listed_since().desc(), Job.id.desc()).limit(limit))).all())


@dataclass(frozen=True)
class RuleShare:
    rule: str
    #: The share of arrivals this rule alone rules out, from 0 to 1.
    removes_share: float


@dataclass(frozen=True)
class Volume:
    """How many postings a day the rules leave for the judge, read from recent arrivals."""

    #: The median over the days that had arrivals; 0 when none arrived.
    expected_per_day: int
    busiest_day: int
    by_rule: list[RuleShare]


async def volume(session: AsyncSession, body: BriefBody, *, now: datetime) -> Volume:
    """The roles that arrived on the Board in the last `VOLUME_DAYS` days,
    counted per local day under the checkable rules of `body`. A role counts
    on the day it was first seen, whether or not it is still open."""
    filters = {"hidden": list(await off_board_company_slugs(session))}
    since = now - timedelta(days=VOLUME_DAYS)
    arrivals = apply_job_filters(select(Job.id), filters).where(Job.first_seen >= since, is_new_job_clause())
    rules = checkable_rules(body)
    out = ruled_out(body)
    day = func.date(func.timezone(local_zone().key, Job.first_seen))
    rows = (await session.execute(
        select(
            day,
            func.count().filter(not_(out)),
            func.count(),
            *(func.count().filter(excludes(rule)) for rule in rules),
        ).select_from(Job).where(Job.id.in_(arrivals)).group_by(day)
    )).all()
    kept = [row[1] for row in rows]
    total = sum(row[2] for row in rows)
    return Volume(
        expected_per_day=round(median(kept)) if kept else 0,
        busiest_day=max(kept, default=0),
        by_rule=[
            RuleShare(str(rule.id), round(sum(row[3 + index] for row in rows) / total, 4) if total else 0.0)
            for index, rule in enumerate(rules)
        ],
    )

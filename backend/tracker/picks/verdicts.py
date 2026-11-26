"""An assistant's verdicts: what the engine accepts, and what it lists back.

A verdict is a `pick`, a `near_miss` or a `pass`. The engine holds each to its
form before saving it, item by item, so one refused verdict leaves the rest of
a batch alone:

| | Pick | Near miss | Pass |
|---|---|---|---|
| `reasons` | 2 to 4 | 1, the thing that failed | none |
| `against_baseline` | required, never `weaker` | required | none |
| `pass_code` | none | none | required |

A reason is one sentence in plain text, at most `REASON_MAX` characters, in two
fields: `opening`, the fact the sentence starts with, and `rest`, everything
after it, so `opening + rest` reads as the sentence. A reason with no opening
keeps the whole sentence in `rest`. Each reason names the item of the brief it
rests on.

A posting is judged once per text and brief (`uq_pick_verdict_case`): a second
verdict on the same case is refused, and a verdict on a new case supersedes
the one before.

Nothing here commits: the caller owns the transaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import Select, func, not_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from tracker.db.models import Favorite, Job, JobFeedback, PickRun, PickVerdict, Pursuit
from tracker.picks.brief import BriefBody, item_ids
from tracker.picks.rules import ruled_out
from tracker.picks.runs import queue_of

VerdictKind = Literal["pick", "near_miss", "pass"]
AgainstBaseline = Literal["better", "comparable", "weaker", "unknown"]
PassCode = Literal["hard_rule", "out_of_reach", "below_level", "not_better", "not_real", "off_direction", "other"]
#: Why one verdict of a batch is refused: the run's own state, then the form.
Refusal = Literal[
    "not_in_run", "brief_changed", "posting_changed", "already_judged", "incomplete", "too_many_reasons",
    "too_long", "not_plain_text", "unknown_brief_item", "weaker_than_baseline", "not_for_a_pass",
]
View = Literal["picks", "near_misses", "passed", "removed"]

#: The most characters of one reason, its opening and the rest together.
REASON_MAX = 140
NOTE_MAX = 200
PICK_REASONS = (2, 4)
NEAR_MISS_REASONS = (1, 1)

#: Markup a reason may not carry: it is shown as written.
_MARKUP = re.compile(r"`|\*\*|__|\]\(|<\s*/?\s*[A-Za-z][^>]*>|^\s*#|[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class ReasonIn:
    rest: str
    brief_item: str
    opening: str | None = None


@dataclass(frozen=True)
class VerdictIn:
    job: int
    verdict: VerdictKind
    reasons: tuple[ReasonIn, ...] = ()
    against_baseline: str | None = None
    pass_code: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Saved:
    """One item's outcome: saved, or refused with the code that says why."""

    job: int
    verdict: VerdictKind
    refusal: Refusal | None = None
    #: The stored reasons of a saved item.
    reasons: list[dict[str, Any]] = field(default_factory=list)

    @property
    def saved(self) -> bool:
        return self.refusal is None


def _words(value: str) -> str:
    return " ".join(value.split())


def clean_reason(reason: ReasonIn) -> dict[str, Any]:
    """The reason as stored. `rest` keeps one leading space when it had any, so
    `opening + rest` reads as the sentence was written."""
    opening = _words(reason.opening) if reason.opening is not None else None
    rest = _words(reason.rest)
    if opening and reason.rest[:1].isspace():
        rest = " " + rest
    return {"opening": opening or None, "rest": rest, "brief_item": reason.brief_item}


def sentence(reason: dict[str, Any]) -> str:
    return f"{reason.get('opening') or ''}{reason.get('rest') or ''}"


def refusal(item: VerdictIn, body: BriefBody) -> Refusal | None:
    """Why the form of `item` is refused, or None when it may be saved."""
    low, high = {"pick": PICK_REASONS, "near_miss": NEAR_MISS_REASONS, "pass": (0, 0)}[item.verdict]
    if item.verdict == "pass":
        if item.pass_code is None:
            return "incomplete"
        if item.reasons or item.against_baseline is not None:
            return "not_for_a_pass"
    else:
        if item.pass_code is not None:
            return "not_for_a_pass"
        if len(item.reasons) < low or item.against_baseline is None:
            return "incomplete"
        if len(item.reasons) > high:
            return "too_many_reasons"
    known = item_ids(body)
    for given in item.reasons:
        if _MARKUP.search(given.rest) or _MARKUP.search(given.opening or ""):
            return "not_plain_text"
        reason = clean_reason(given)
        if not reason["rest"].strip() or (given.opening is not None and not reason["opening"]):
            return "incomplete"
        if len(sentence(reason)) > REASON_MAX:
            return "too_long"
        if reason["brief_item"] not in known:
            return "unknown_brief_item"
    if item.note is not None and len(_words(item.note)) > NOTE_MAX:
        return "too_long"
    if item.verdict == "pick" and item.against_baseline == "weaker":
        return "weaker_than_baseline"
    return None


async def save(
    session: AsyncSession, run: PickRun, items: list[VerdictIn], *, body: BriefBody, active_version: int,
    now: datetime,
) -> list[Saved]:
    """Save each verdict of an open run the engine accepts, each in its own
    savepoint, and count them on the run. The caller holds the picks lock."""
    handed = queue_of(run)
    jobs = {
        job.id: job
        for job in (await session.scalars(select(Job).where(Job.id.in_([item.job for item in items])))).all()
    }
    out: list[Saved] = []
    for item in items:
        code = await _refusal_in_run(session, run, item, handed, jobs, body=body, active_version=active_version)
        if code is not None:
            out.append(Saved(item.job, item.verdict, refusal=code))
            continue
        reasons = [clean_reason(reason) for reason in item.reasons]
        async with session.begin_nested():
            earlier = (await session.scalars(
                select(PickVerdict).where(
                    PickVerdict.job_id == item.job, PickVerdict.trial == run.trial, PickVerdict.superseded_at.is_(None),
                )
            )).all()
            for row in earlier:
                row.superseded_at = now
            session.add(PickVerdict(
                job_id=item.job, content_hash=handed[item.job], brief_version=run.brief_version,
                verdict=item.verdict, reasons=reasons, against_baseline=item.against_baseline,
                pass_code=item.pass_code, note=_words(item.note) if item.note else None,
                run_id=run.id, trial=run.trial, created_at=now,
            ))
            await session.flush()
        out.append(Saved(item.job, item.verdict, reasons=reasons))
    tally: dict[str, int] = {
        kind: count for kind, count in (await session.execute(
            select(PickVerdict.verdict, func.count()).where(PickVerdict.run_id == run.id).group_by(PickVerdict.verdict)
        )).all()
    }
    run.counts = {
        **run.counts,
        "judged": sum(tally.values()),
        "picks": tally.get("pick", 0),
        "near_misses": tally.get("near_miss", 0),
    }
    await session.flush()
    return out


async def _refusal_in_run(
    session: AsyncSession, run: PickRun, item: VerdictIn, handed: dict[int, str], jobs: dict[int, Job], *,
    body: BriefBody, active_version: int,
) -> Refusal | None:
    job = jobs.get(item.job)
    if job is None or item.job not in handed:
        return "not_in_run"
    if run.brief_version != active_version:
        return "brief_changed"
    if (job.content_hash or "") != handed[item.job]:
        return "posting_changed"
    judged = await session.scalar(
        select(PickVerdict.id).where(
            PickVerdict.job_id == item.job, PickVerdict.content_hash == handed[item.job],
            PickVerdict.brief_version == run.brief_version, PickVerdict.trial == run.trial,
        )
    )
    if judged is not None:
        return "already_judged"
    return refusal(item, body)


@dataclass(frozen=True)
class Reaction:
    """What the person did with a role an assistant judged."""

    kind: Literal["saved", "pursued", "not_for_me"]
    at: datetime
    #: A Not for me's reason code and the person's own words, when given.
    reason: str | None = None
    reason_text: str | None = None


@dataclass(frozen=True)
class Listed:
    verdict: PickVerdict
    job: Job
    reaction: Reaction | None


async def reactions_of(session: AsyncSession, job_ids: list[int]) -> dict[int, Reaction]:
    """The person's standing reaction to each posting: Not for me, else a
    pursuit, else a save."""
    if not job_ids:
        return {}
    found: dict[int, Reaction] = {}
    for job_id, at in (await session.execute(
        select(Favorite.job_id, Favorite.created_at).where(Favorite.job_id.in_(job_ids))
    )).all():
        found[job_id] = Reaction("saved", at)
    for job_id, at in (await session.execute(
        select(Pursuit.job_id, Pursuit.created_at).where(Pursuit.job_id.in_(job_ids))
    )).all():
        found[job_id] = Reaction("pursued", at)
    for row in (await session.scalars(
        select(JobFeedback).where(JobFeedback.job_id.in_(job_ids), JobFeedback.verdict == "dismissed")
    )).all():
        found[row.job_id] = Reaction("not_for_me", row.created_at, row.reason, row.reason_text)
    return found


def _dismissed() -> Any:
    return select(JobFeedback.job_id).where(JobFeedback.verdict == "dismissed")


_PICKED = aliased(Job)


def standing_pick_ids(body: BriefBody, *, keep_removed: bool = False) -> Select[Any]:
    """Ids of the postings that are picks now: a pick that stands, on a
    posting no current hard rule of `body` rules out and, unless
    `keep_removed`, the person has not marked Not for me."""
    stmt = (
        select(PickVerdict.job_id)
        .join(_PICKED, _PICKED.id == PickVerdict.job_id)
        .where(
            PickVerdict.trial.is_(False), PickVerdict.superseded_at.is_(None), PickVerdict.verdict == "pick",
            not_(ruled_out(body, _PICKED)),
        )
    )
    return stmt if keep_removed else stmt.where(PickVerdict.job_id.notin_(_dismissed()))


def picked_at(entity: Any = Job) -> Any:
    """When the posting was picked: its standing pick's time, as a column to order by."""
    return (
        select(func.max(PickVerdict.created_at))
        .where(
            PickVerdict.job_id == entity.id, PickVerdict.trial.is_(False), PickVerdict.superseded_at.is_(None),
            PickVerdict.verdict == "pick",
        )
        .correlate(entity)
        .scalar_subquery()
    )


async def standing_picks_of(session: AsyncSession, job_ids: list[int]) -> dict[int, PickVerdict]:
    """The pick that stands on each of `job_ids` that has one."""
    if not job_ids:
        return {}
    rows = (await session.scalars(
        select(PickVerdict).where(
            PickVerdict.job_id.in_(job_ids), PickVerdict.trial.is_(False), PickVerdict.superseded_at.is_(None),
            PickVerdict.verdict == "pick",
        )
    )).all()
    return {row.job_id: row for row in rows}


@dataclass(frozen=True)
class Tally:
    #: Roles an assistant read, and those it did not pick.
    read: int
    passed_over: int


async def tally_since(session: AsyncSession, since: datetime) -> Tally:
    """How many roles were read since `since`, each once however often it was
    judged, and how many of them were never a pick in that time."""
    picked = func.bool_or(PickVerdict.verdict == "pick")
    per_role = (
        select(PickVerdict.job_id, picked.label("picked"))
        .where(PickVerdict.trial.is_(False), PickVerdict.created_at >= since)
        .group_by(PickVerdict.job_id)
        .subquery()
    )
    read, passed = (await session.execute(
        select(func.count(), func.count().filter(not_(per_role.c.picked))).select_from(per_role)
    )).one()
    return Tally(read=read or 0, passed_over=passed or 0)


async def passes_by_code(session: AsyncSession, since: datetime) -> dict[str, int]:
    """The roles passed since `since` on a verdict that stands, by why."""
    rows = (await session.execute(
        select(PickVerdict.pass_code, func.count(func.distinct(PickVerdict.job_id)))
        .where(
            PickVerdict.trial.is_(False), PickVerdict.superseded_at.is_(None),
            PickVerdict.verdict == "pass", PickVerdict.created_at >= since,
        )
        .group_by(PickVerdict.pass_code)
    )).all()
    return {str(code): count for code, count in rows}


async def listed(
    session: AsyncSession, view: View, *, body: BriefBody, since: datetime | None = None, limit: int = 200,
    keep_removed: bool = False,
) -> list[Listed]:
    """The verdicts that stand, newest first, for one view:

    - `picks`: picks the person has not removed and no current hard rule rules out;
    - `near_misses` and `passed`: those verdicts since `since`;
    - `removed`: picks the person marked Not for me.

    `keep_removed` lists the removed picks among the picks, for a reader that
    may not learn what the person dismissed.
    """
    stmt = (
        select(PickVerdict, Job)
        .join(Job, Job.id == PickVerdict.job_id)
        .where(PickVerdict.trial.is_(False), PickVerdict.superseded_at.is_(None))
    )
    if view == "picks":
        stmt = stmt.where(PickVerdict.verdict == "pick", not_(ruled_out(body)))
        if not keep_removed:
            stmt = stmt.where(Job.id.notin_(_dismissed()))
    elif view == "removed":
        stmt = stmt.where(PickVerdict.verdict == "pick", Job.id.in_(_dismissed()))
    else:
        stmt = stmt.where(PickVerdict.verdict == ("near_miss" if view == "near_misses" else "pass"))
    if since is not None and view in ("near_misses", "passed"):
        stmt = stmt.where(PickVerdict.created_at >= since)
    rows = (await session.execute(stmt.order_by(PickVerdict.created_at.desc(), PickVerdict.id.desc()).limit(limit))).all()
    reactions = await reactions_of(session, [job.id for _, job in rows])
    return [Listed(verdict, job, reactions.get(job.id)) for verdict, job in rows]


async def picks_since(session: AsyncSession, since: datetime) -> list[Listed]:
    """The picks made since `since` that stand, oldest first: what a month's
    budget is counted from, the removed ones included."""
    rows = (await session.execute(
        select(PickVerdict, Job)
        .join(Job, Job.id == PickVerdict.job_id)
        .where(
            PickVerdict.trial.is_(False), PickVerdict.superseded_at.is_(None), PickVerdict.verdict == "pick",
            PickVerdict.created_at >= since,
        )
        .order_by(PickVerdict.created_at, PickVerdict.id)
    )).all()
    reactions = await reactions_of(session, [job.id for _, job in rows])
    return [Listed(verdict, job, reactions.get(job.id)) for verdict, job in rows]


async def reacted_since(session: AsyncSession, since: datetime | None, *, limit: int = 100) -> list[Listed]:
    """Picks and near misses that stand and that the person reacted to after
    `since` (ever, when None), newest reaction first."""
    rows = (await session.execute(
        select(PickVerdict, Job)
        .join(Job, Job.id == PickVerdict.job_id)
        .where(
            PickVerdict.trial.is_(False), PickVerdict.superseded_at.is_(None),
            PickVerdict.verdict.in_(("pick", "near_miss")),
        )
    )).all()
    reactions = await reactions_of(session, [job.id for _, job in rows])
    reacted = [
        Listed(verdict, job, reactions[job.id]) for verdict, job in rows
        if job.id in reactions and (since is None or reactions[job.id].at > since)
    ]
    reacted.sort(key=lambda item: (item.reaction.at if item.reaction else since, item.job.id), reverse=True)
    return reacted[:limit]


async def unseen_pick(session: AsyncSession, *, body: BriefBody, last_opened_at: datetime | None) -> bool:
    """Whether a pick that stands, and that the person has not removed, was
    made after they last opened their picks. A yes or no, never a count."""
    newest = await listed(session, "picks", body=body, limit=1)
    return bool(newest) and (last_opened_at is None or newest[0].verdict.created_at > last_opened_at)


async def forget_reasons(session: AsyncSession, now: datetime) -> int:
    """Clear what every verdict says and end the ones that stand, and say how
    many verdicts that was. A reason or a note quotes the person's own facts
    (what they are paid, what they hold), so they go when the person removes
    their brief; a pick with nothing left to say is no longer a pick, and its
    role is judged afresh under whatever brief comes next. The rows stay, as
    the record that a role was read. Only the person's own Remove calls this."""
    cleared = await session.execute(
        update(PickVerdict).values(
            reasons=[], note=None, superseded_at=func.coalesce(PickVerdict.superseded_at, now),
        )
    )
    return cleared.rowcount or 0

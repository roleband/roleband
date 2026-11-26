"""Top picks in the feed: a role the person's assistant picked, and checks that fell behind.

**`top_pick`.** One row per posting an assistant picks outside a trial, keyed
by the posting (`source_type` "pick"), written by the `picks.decide` call that
saved the pick, in its transaction. A trial is a rehearsal of the brief and
rings nothing. A posting picked again, after its text or the brief changed,
already has its row, so it rings once; a replayed call runs no write at all.
One desktop banner per call names the first new pick and how many there are.

**`picks_stalled`.** The checks stopped doing their job while roles wait for
them. One row at most (`source_type` "picks"), reconciled like `coverage.py`:
each pass writes it while the stall lasts, refreshing its words in place
without ringing again (`created_at` and `read_at` are not refreshable), and
deletes it once the checks are back, the mode is off, or nothing waits. So one
stall is one notification and one banner, however many passes it lasts, and
the next stall rings anew.

A stall, from the routine's health (`picks.health`) with roles waiting:

| Health | A stall when |
|---|---|
| `late` | always |
| `stopped_early` | the run that ended early began after the mode was last turned on |
| `never_ran` | roles have waited longer than `LATE_AFTER`, as `late` measures it |

A run that ended early before a pause says nothing about the checks since the
person resumed them. Right after setup no run has finished yet, which is not a
stall until a role has waited as long as `late` allows.

Neither row repeats a pick's reasons or a run's note: both quote the person's
own facts, and Remove deletes them where they are stored.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import Job, JobFeedback, Notification, PickRun, PickVerdict
from tracker.db.queries.companies import display_names
from tracker.notifications import say as S
from tracker.notifications.channels import deliver
from tracker.notifications.desktop import post_after_commit
from tracker.notifications.events import ClassifiedNotif, _said
from tracker.notifications.render import company_namer
from tracker.osnotify import banner
from tracker.picks import brief as briefs
from tracker.picks import mode, runs
from tracker.picks.health import LATE_AFTER, Health
from tracker.platform.local_zone import local_zone
from tracker.settings_store import get_top_picks_settings

PICK_SOURCE = "pick"
STALL_SOURCE = "picks"
#: The stall row's key: there is at most one.
STALL_ID = 0

#: The banner's word for each kind of stall (`banner-picks-stalled`).
_BANNER_REASON = {"late": "late", "stopped_early": "stopped", "never_ran": "never"}


def classify_top_pick(company: str, title: str, *, names: Mapping[str, str] | None = None) -> ClassifiedNotif:
    return ClassifiedNotif(
        priority="high",
        category="top_pick",
        meta={"say": _said(S.say("notif-top-pick", company=company_namer(names)(company)), title)},
    )


@dataclass(frozen=True)
class Stall:
    """Why the checks fell behind, and what waits for them."""

    health: Health
    waiting: int
    #: The reader's calendar day a check last finished, if one ever did.
    last_check_on: date | None


def classify_picks_stalled(stall: Stall) -> ClassifiedNotif:
    waiting = S.say("notif-picks-waiting", count=stall.waiting)
    if stall.health == "late":
        title = S.say("notif-picks-late")
        body = [S.say("notif-picks-last-check", day=S.day(stall.last_check_on)), waiting] if stall.last_check_on else [waiting]
    elif stall.health == "stopped_early":
        title, body = S.say("notif-picks-stopped"), [waiting]
    else:
        title, body = S.say("notif-picks-never-ran"), [waiting]
    return ClassifiedNotif(
        priority="normal",
        category="picks_stalled",
        meta={"health": stall.health, "waiting": stall.waiting, "say": _said(title, *body)},
    )


def stall_of(
    health: Health, *, waiting: int, oldest_waiting_since: datetime | None, enabled_at: datetime | None,
    ended_early_run_began_at: datetime | None, now: datetime,
) -> bool:
    """Whether the routine's health is a stall the person hears about (the
    table in this module's docstring). `ended_early_run_began_at` is when the
    run health read as ended early began."""
    if waiting <= 0:
        return False
    if health == "late":
        return True
    if health == "stopped_early":
        return (
            enabled_at is None or ended_early_run_began_at is None or ended_early_run_began_at >= enabled_at
        )
    if health == "never_ran":
        return oldest_waiting_since is not None and now - oldest_waiting_since > LATE_AFTER
    return False


async def generate_top_pick_notifications(
    session: AsyncSession, run_id: str, *, names: dict[str, str] | None = None,
) -> int:
    """Write a `top_pick` row for each posting run `run_id` picked that has
    none yet, and ask for one banner naming the first. Returns rows written.

    Only a pick that stands, on a posting the person has not marked Not for
    me, rings. Nothing commits here: the `picks.decide` write does."""
    rows = (await session.execute(
        select(PickVerdict, Job)
        .join(Job, Job.id == PickVerdict.job_id)
        .where(
            PickVerdict.run_id == run_id, PickVerdict.trial.is_(False), PickVerdict.verdict == "pick",
            PickVerdict.superseded_at.is_(None),
            Job.id.not_in(select(JobFeedback.job_id).where(JobFeedback.verdict == "dismissed")),
        )
        .order_by(PickVerdict.id)
    )).all()
    if not rows:
        return 0
    if names is None:
        names = await display_names(session)
    fresh: list[Job] = []
    for verdict, job in rows:
        classified = classify_top_pick(job.company, job.title, names=names)
        created = await deliver(
            session,
            {
                "created_at": verdict.created_at,
                "priority": classified.priority,
                "category": classified.category,
                "title": classified.title,
                "body": classified.body,
                "job_id": job.id,
                "run_id": None,
                "source_type": PICK_SOURCE,
                "source_id": job.id,
                "meta": classified.meta or {},
            },
        )
        if created:
            fresh.append(job)
    if fresh:
        first = fresh[0]
        post_after_commit(
            session,
            banner("banner-top-pick-title", count=len(fresh)),
            banner("banner-top-pick-body", title=first.title, company=company_namer(names)(first.company)),
        )
    return len(fresh)


async def _stall(session: AsyncSession, now: datetime) -> Stall | None:
    settings = await get_top_picks_settings(session)
    if settings.state != "on":
        return None
    stands = await mode.standing(session, settings, await briefs.active(session), now)
    if stands.health not in ("late", "stopped_early", "never_ran") or stands.waiting <= 0:
        return None
    began: datetime | None = None
    if stands.health == "stopped_early":
        # The run health read: the newest, when it is open past the bound and
        # so reads as abandoned, else the newest closed one (`mode.standing`).
        read: PickRun | None = stands.newest
        if read is None or read.outcome is not None or runs.as_fact(read, now).outcome is None:
            read = await runs.newest_closed_routine_run(session)
        began = read.started_at if read is not None else None
    if not stall_of(
        stands.health, waiting=stands.waiting, oldest_waiting_since=stands.oldest_waiting_since,
        enabled_at=settings.enabled_at, ended_early_run_began_at=began, now=now,
    ):
        return None
    finished = await runs.last_finished(session)
    last_check_on = (
        finished.finished_at.astimezone(local_zone()).date()
        if finished is not None and finished.finished_at is not None else None
    )
    return Stall(stands.health, stands.waiting, last_check_on)


async def reconcile_picks_stalled(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Write, refresh or delete the stall row to match the checks now, and
    ask for a banner when the row is new. Returns rows written (0 or 1).
    Nothing commits here: the caller's transaction does."""
    now = now or datetime.now(UTC)
    stall = await _stall(session, now)
    if stall is None:
        await session.execute(
            delete(Notification).where(
                Notification.source_type == STALL_SOURCE, Notification.category == "picks_stalled",
            )
        )
        return 0
    classified = classify_picks_stalled(stall)
    created = await deliver(
        session,
        {
            "created_at": now,
            "priority": classified.priority,
            "category": classified.category,
            "title": classified.title,
            "body": classified.body,
            "job_id": None,
            "run_id": None,
            "source_type": STALL_SOURCE,
            "source_id": STALL_ID,
            "meta": classified.meta or {},
        },
        refresh=("title", "body", "meta", "priority"),
    )
    if created:
        post_after_commit(
            session,
            banner("banner-picks-stalled", reason=_BANNER_REASON[stall.health]),
            banner("banner-picks-waiting", count=stall.waiting),
        )
    return 1

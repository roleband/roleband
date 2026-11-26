"""The mode, as the person changes it in the app: on, off, opened, removed.

Turning the mode off pauses the checks: no run of the routine begins, and
everything saved is kept. Remove is the person taking back what they gave: the
stored CV, every reading of it, the brief, and what past verdicts say, since a
reason quotes their own facts. It leaves their saved roles, their Not for me
marks and the Board's own data where they are, and returns the mode to never
set up.

Nothing here commits: the caller owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import PickBrief, PickRun
from tracker.picks import background, queue, runs, verdicts
from tracker.picks import brief as briefs
from tracker.picks.health import Health, health
from tracker.picks.lock import lock_picks
from tracker.settings_store import (
    DAILY_CAP_DEFAULT,
    TopPicksSettings,
    get_top_picks_settings,
    update_top_picks_settings,
)


class BriefRequired(Exception):
    """The mode cannot be on without an active brief."""


@dataclass(frozen=True)
class Removed:
    briefs: int
    readings: int
    documents: int
    #: Verdicts whose reasons and notes were cleared.
    verdicts: int


async def change(
    session: AsyncSession, *, state: str | None = None, now: datetime, **also: object,
) -> TopPicksSettings:
    """Change the mode's settings: `state` on or off, and any other part named
    (the daily limit, the routine's host and schedule). A part left out stays.
    Turning the mode on from any other state records when: a role open before
    then has waited for a judgment only since then. Off deletes nothing. Raises `BriefRequired`
    for on without an active brief and ValueError for a limit out of range."""
    await lock_picks(session)
    before = await get_top_picks_settings(session)
    if state == "on" and await briefs.active(session) is None:
        raise BriefRequired
    changes: dict[str, object] = dict(also)
    if state is not None:
        changes["state"] = state
    if state == "on" and before.state != "on":
        changes["enabled_at"] = now
    return await update_top_picks_settings(session, **changes) if changes else before


async def mark_opened(session: AsyncSession, now: datetime) -> TopPicksSettings:
    """The person opened their picks: nothing made before `now` is unseen."""
    return await update_top_picks_settings(session, last_opened_at=now)


async def remove(session: AsyncSession, now: datetime, *, directory: Path | None = None) -> Removed:
    """Delete the stored CV, every reading and the brief, clear what past
    verdicts and runs say, close any run still open, and return the mode to
    never set up."""
    await lock_picks(session)
    await runs.forget_notes(session)
    await runs.close_open(session, now, note="Top picks was removed.")
    readings, documents = await background.remove_all(session, directory=directory)
    floor = max((await get_top_picks_settings(session)).brief_revision_floor, await briefs.highest_revision(session))
    removed = Removed(
        briefs=await briefs.remove_all(session), readings=readings, documents=documents,
        verdicts=await verdicts.forget_reasons(session, now),
    )
    await update_top_picks_settings(
        session, state="never_set_up", enabled_at=None, routine_host=None, schedule=None,
        daily_cap=DAILY_CAP_DEFAULT, last_opened_at=None, brief_revision_floor=floor,
    )
    return removed


@dataclass(frozen=True)
class Standing:
    """How the routine stands now."""

    health: Health
    #: Roles waiting for a judgment, and since when the longest has waited.
    waiting: int
    oldest_waiting_since: datetime | None
    #: The newest run of the routine, open or closed.
    newest: PickRun | None


async def standing(
    session: AsyncSession, settings: TopPicksSettings, active: PickBrief | None, now: datetime,
) -> Standing:
    """The routine's health and what waits for it. Nothing waits while the
    mode is not on or there is no active brief: nothing is being judged."""
    waiting = queue.QueueCounts()
    if settings.state == "on" and active is not None:
        waiting = await queue.counts(
            session,
            queue.candidates(
                await queue.board_filters(session), trial=False, active_version=active.version, now=now,
            ),
            briefs.body_of(active), since=settings.enabled_at,
        )
    newest = await runs.newest_routine_run(session)
    finished = await runs.last_finished(session)
    # Health reads the run that ended last, whichever started last. A run still
    # open says nothing of how the last one ended, unless it is overdue and so
    # reads as abandoned.
    fact = runs.as_fact(newest, now) if newest is not None else None
    if fact is not None and not (newest is not None and newest.outcome is None and fact.outcome is not None):
        closed = await runs.newest_closed_routine_run(session)
        fact = runs.as_fact(closed, now) if closed is not None else None
    return Standing(
        health=health(
            state=settings.state,
            newest=fact,
            last_finished_at=finished.finished_at if finished is not None else None,
            oldest_waiting_since=waiting.oldest_waiting_since, now=now,
        ),
        waiting=waiting.waiting, oldest_waiting_since=waiting.oldest_waiting_since, newest=newest,
    )

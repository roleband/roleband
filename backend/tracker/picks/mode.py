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

from tracker.picks import background, runs, verdicts
from tracker.picks import brief as briefs
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
    verdicts say, close any run still open, and return the mode to never set up."""
    await lock_picks(session)
    await runs.close_open(session, now, note="Top picks was removed.")
    readings, documents = await background.remove_all(session, directory=directory)
    removed = Removed(
        briefs=await briefs.remove_all(session), readings=readings, documents=documents,
        verdicts=await verdicts.forget_reasons(session, now),
    )
    await update_top_picks_settings(
        session, state="never_set_up", enabled_at=None, routine_host=None, schedule=None,
        daily_cap=DAILY_CAP_DEFAULT, last_opened_at=None,
    )
    return removed

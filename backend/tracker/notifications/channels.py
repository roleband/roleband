"""Delivery-channel seam: the notification dispatch point.

Today notifications have exactly one channel: the durable in-DB row that the
dashboard banner/notification center reads. This module owns that write and the
registry naming it, so a future channel (e.g. macOS push via `tracker.osnotify`)
has one place to register; it is not an abstraction layer, and nothing else in
the package should grow channel awareness.

Every writer dispatches through it. If `digest` and `pursuit_due` built their
own `insert`, a channel registered here would fire for run health and job
events and stay silent for the daily digest and pursuit reminders, the two
categories a push channel exists for.

The three writers differ for a real reason, and the seam keeps it. Run/job
notifications must NOT overwrite an existing row (re-running a pass must not
re-ring a notification the user has read), while the digest and pursuit rows
are live recomputations that must age in place: "2d overdue" becoming
"3d overdue" without re-ringing. That is the whole of `refresh`: the
columns a second write may update. Empty means do-nothing, which is the safe
default and what every caller that omits it gets.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import Notification

#: The uniqueness the feed is built on: one row per (source, category).
CONFLICT_KEY = ["source_type", "source_id", "category"]


async def _write_in_db(
    session: AsyncSession, values: dict, *, refresh: Sequence[str] = ()
) -> bool:
    """The durable row the dashboard reads. True when this write created it.

    A refreshed row is one Postgres updated, so its `xmax` names this
    transaction; a row it inserted has none. A conflict that does nothing
    returns no row at all. Two writers of the same key in flight at once wait
    on the row, so only one of them is told it is new."""

    stmt = insert(Notification).values(**values)
    if refresh:
        # `created_at` and `read_at` are deliberately never refreshable: the row
        # holds its place in the feed and its read state instead of jumping to
        # the top, unread, on every scrape.
        stmt = stmt.on_conflict_do_update(
            index_elements=CONFLICT_KEY,
            set_={column: stmt.excluded[column] for column in refresh},
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=CONFLICT_KEY)
    created = await session.scalar(stmt.returning(literal_column("xmax = 0")))
    return bool(created)


#: Dispatch point: channel name -> async writer taking (session, values, refresh).
CHANNELS = {"in_db": _write_in_db}


async def deliver(
    session: AsyncSession, values: dict, *, refresh: Sequence[str] = ()
) -> bool:
    """Send one notification through every registered channel, and say
    whether its durable row is new: a producer that rings outside the app
    (`desktop.post_after_commit`) rings only for a row this call created.

    Every notification in this package goes through here. That is the point: a
    channel added to `CHANNELS` fires for all of them, with no further wiring.
    """

    created = False
    for name, write in CHANNELS.items():
        wrote = await write(session, values, refresh=refresh)
        if name == "in_db":
            created = bool(wrote)
    return created

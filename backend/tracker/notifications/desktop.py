"""Desktop banners a producer rings, posted once the write that made its row commits.

A banner is the operating system's (`tracker.osnotify`) and cannot be taken
back. Posted before its transaction commits, a rollback would leave a banner
for a row that does not exist, and the next pass would ring it again. So a
producer asks for one here, and it is posted after the outermost commit, unless
a transaction that held the request rolled back first: a savepoint rolled back
takes the banners asked for inside it.

Posting runs on its own thread: `osnotify.notify` starts a process and waits
for it, and producers run on the engine's event loop.
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from tracker import osnotify

logger = logging.getLogger(__name__)

#: `Session.info` key of the banners waiting for the session's commit.
_PENDING = "tracker.notifications.desktop.pending"

_Pending = list[tuple[SessionTransaction | None, str, str]]


def _show(title: str, message: str) -> None:
    """Post one banner without waiting for it."""
    threading.Thread(target=osnotify.notify, args=(title, message), name="desktop-banner").start()


def post_after_commit(session: AsyncSession, title: str, message: str) -> None:
    """Post a banner once the session's current transaction commits."""
    sync = session.sync_session
    pending: _Pending | None = sync.info.get(_PENDING)
    if pending is None:
        pending = sync.info[_PENDING] = []
        event.listen(sync, "after_commit", _committed)
        event.listen(sync, "after_soft_rollback", _rolled_back)
        event.listen(sync, "after_transaction_end", _ended)
    pending.append((sync.get_nested_transaction() or sync.get_transaction(), title, message))


def _committed(session: Session) -> None:
    # A savepoint's release is a commit too; only the outermost one posts.
    # While a savepoint commits it is still the session's nested transaction.
    if session.in_nested_transaction():
        return
    pending: _Pending = session.info.get(_PENDING, [])
    posting = [(title, message) for _, title, message in pending]
    pending.clear()
    for title, message in posting:
        try:
            _show(title, message)
        except Exception:  # noqa: BLE001 - a banner never fails the write it reports
            logger.warning("could not post a desktop banner", exc_info=True)


def _rolled_back(session: Session, previous: SessionTransaction) -> None:
    pending: _Pending = session.info.get(_PENDING, [])
    pending[:] = [item for item in pending if not _inside(item[0], previous)]


def _ended(session: Session, transaction: SessionTransaction) -> None:
    # The outermost transaction ended. A commit posted its banners first
    # (`after_commit` runs before this); whatever is left never committed.
    if transaction.parent is None:
        session.info.get(_PENDING, []).clear()


def _inside(transaction: SessionTransaction | None, outer: SessionTransaction) -> bool:
    while transaction is not None:
        if transaction is outer:
            return True
        transaction = transaction.parent
    return False

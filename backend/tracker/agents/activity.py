"""The agent activity log: every read, change and refusal, for the person.

Each agent operation leaves one `agent_activity` row, listed newest first on
the Activity screen:

- a **change** is recorded by the write itself (`OperationContext.write`), in
  the transaction that commits the write, its audit event and its receipt, so
  a rolled-back write leaves no row and a row never claims a change that did
  not land. A replay of an earlier change changes nothing and is not listed
  again;
- a **read** is recorded once its answer is built, before it is sent, on a
  session of its own. A read whose row cannot be written is not answered;
- a **refusal** by the person's switches (`REFUSALS`) is recorded with the
  category it asked for. Other failures (bad input, a missing record, a
  revision conflict) answer nothing and are not listed.

A row says what happened as facts (`Said`): a topic the dashboard words in the
reader's language, the facts it is said from (a role's title, a count, a stage
slug), and the same sentence in English, which search matches and a reader
without the catalog sees.

Nothing here commits: a change's row joins the write's transaction, and the
caller of `record` owns the session it is given.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import DataClass, OperationDescriptor
from tracker.agents.operations.policy import CATEGORY_NAMES
from tracker.db.models import AgentActivity

ActivityKind = Literal["read", "change", "refused"]

#: The refusals the person's switches make. Each is listed; any other failure is not.
REFUSALS: frozenset[str] = frozenset({"access_disabled", "writes_disabled", "category_disabled"})

#: One page of the Activity screen.
PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Said:
    """What an entry says. `topic` is the key the dashboard words it by,
    `params` the facts it is said from, `english` the same sentence."""

    topic: str
    english: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def subject(self) -> dict[str, Any]:
        return {"topic": self.topic, **self.params}


@dataclass(frozen=True)
class FieldChange:
    """One field a change touched, as JSON values. `before` is None for a
    field the record did not have yet."""

    field: str
    before: Any
    after: Any

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "before": self.before, "after": self.after}


@dataclass(frozen=True)
class Changed:
    """What a write says about itself: the sentence and the fields it touched."""

    said: Said
    changes: tuple[FieldChange, ...] = ()


class WriteActivity(Protocol):
    """How one write describes itself. `before` runs inside the write's
    transaction, after its key's lock and before its domain write; it takes
    the domain lock itself when what it reads could move. `entry` sees what
    `before` read and the write's result."""

    async def before(self, session: AsyncSession) -> Any: ...

    def entry(self, before: Any, result: BaseModel) -> Changed: ...


@dataclass(frozen=True)
class Entry:
    kind: ActivityKind
    operation: str
    said: Said
    categories: tuple[str, ...] = ()
    changes: tuple[FieldChange, ...] = ()
    action_group: str | None = None
    refusal: str | None = None


def row_of(
    entry: Entry,
    *,
    principal_id: str,
    workspace_id: str | None,
    request_id: str | None,
    idempotency_key: str | None = None,
) -> AgentActivity:
    return AgentActivity(
        workspace_id=workspace_id,
        principal_id=principal_id,
        operation=entry.operation,
        request_id=request_id,
        kind=entry.kind,
        categories=list(entry.categories),
        action_group=entry.action_group,
        refusal=entry.refusal,
        summary=entry.said.english,
        subject=entry.said.subject(),
        changes=[change.as_dict() for change in entry.changes] if entry.kind == "change" else None,
        idempotency_key=idempotency_key,
    )


async def record(session: AsyncSession, row: AgentActivity) -> None:
    """Add `row` to the session's transaction and flush it. The caller commits."""
    session.add(row)
    await session.flush()


# --------------------------------------------------------------------------- #
# What an entry says
# --------------------------------------------------------------------------- #

#: Reads by the category they lead with. The handshake reads name none.
_READ_ENGLISH: dict[str, str] = {
    "public_posting": "Read postings",
    "market_statistic": "Read market statistics",
    "private_pursuit": "Read your saved roles and notes",
    "offer": "Read your offer",
    "candidate": "Read your candidate profile",
    "engine": "Checked the connection",
}


def count_of(data: BaseModel) -> int | None:
    """How many records an answer holds, when it is a list of them."""
    items = getattr(data, "items", None)
    if isinstance(items, list):
        return len(items)
    count = getattr(data, "count", None)
    return count if isinstance(count, int) and not isinstance(count, bool) else None


def read_said(descriptor: OperationDescriptor, *, count: int | None) -> Said:
    topic = descriptor.data_classes[0] if descriptor.data_classes else "engine"
    english = _READ_ENGLISH[topic]
    if topic == "public_posting" and count is not None:
        english = f"Read {count} posting{'' if count == 1 else 's'}"
    params: dict[str, Any] = {} if count is None else {"count": count}
    return Said(f"read.{topic}", english, params)


def refused_said(code: str, category: str | None) -> Said:
    if code == "category_disabled" and category in CATEGORY_NAMES:
        return Said("refused.category", f"Asked for {_your(category)}", {"category": category})
    if code == "writes_disabled":
        return Said("refused.writes", "Tried a change while changes were off")
    return Said("refused.access", "Asked while access was off")


def _your(category: str) -> str:
    name = CATEGORY_NAMES[category]  # type: ignore[index]
    return name if category in ("public_posting", "market_statistic") else f"your {name}"


def changed_said(descriptor: OperationDescriptor) -> Said:
    """The sentence of a write that does not describe itself."""
    return Said("change", f"Made a change ({descriptor.id})")


def read_entry(descriptor: OperationDescriptor, categories: Sequence[DataClass], *, count: int | None) -> Entry:
    return Entry("read", descriptor.id, read_said(descriptor, count=count), tuple(categories))


def refused_entry(operation: str, code: str, category: str | None) -> Entry:
    return Entry(
        "refused", operation, refused_said(code, category),
        (category,) if category in CATEGORY_NAMES else (), refusal=code,
    )


# --------------------------------------------------------------------------- #
# The Activity screen's pages
# --------------------------------------------------------------------------- #

KindFilter = Literal["all", "change", "read", "refused"]
_CURSOR_FORMAT = 1


class BadCursor(ValueError):
    """The cursor is not one this store made."""


@dataclass(frozen=True)
class ActivityQuery:
    q: str | None = None
    kind: KindFilter = "all"
    category: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    cursor: str | None = None
    limit: int = PAGE_SIZE


@dataclass(frozen=True)
class ActivityPage:
    rows: list[AgentActivity]
    next_cursor: str | None


def encode_cursor(row: AgentActivity) -> str:
    body = {"v": _CURSOR_FORMAT, "t": row.occurred_at.isoformat(), "id": row.id}
    return base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        body = json.loads(raw)
        if not isinstance(body, dict) or body.get("v") != _CURSOR_FORMAT:
            raise BadCursor("unknown cursor format")
        at = datetime.fromisoformat(body["t"])
        row_id = body["id"]
    except (binascii.Error, UnicodeDecodeError, ValueError, KeyError, TypeError) as error:
        raise BadCursor(str(error)) from None
    if at.tzinfo is None or not isinstance(row_id, int) or isinstance(row_id, bool):
        raise BadCursor("malformed cursor")
    return at, row_id


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def activity_page(session: AsyncSession, query: ActivityQuery) -> ActivityPage:
    """One page, newest first by `(occurred_at, id)`, after `query.cursor`.

    Keyset paging: a page resumes strictly after the previous page's last
    row, so rows recorded while the person pages never shift or repeat one.
    `q` matches the summary, the subject's facts and the operation, ignoring
    case; `category` keeps the rows that read (or asked for) it; `since` is
    inclusive and `until` exclusive.
    """
    conditions = []
    if query.kind != "all":
        conditions.append(AgentActivity.kind == query.kind)
    if query.category is not None:
        conditions.append(AgentActivity.categories.any(query.category))
    if query.since is not None:
        conditions.append(AgentActivity.occurred_at >= query.since)
    if query.until is not None:
        conditions.append(AgentActivity.occurred_at < query.until)
    needle = (query.q or "").strip()
    if needle:
        pattern = _like(needle)
        conditions.append(
            or_(
                AgentActivity.summary.ilike(pattern, escape="\\"),
                AgentActivity.operation.ilike(pattern, escape="\\"),
                AgentActivity.subject["title"].astext.ilike(pattern, escape="\\"),
                AgentActivity.subject["company"].astext.ilike(pattern, escape="\\"),
                AgentActivity.subject["recipe"].astext.ilike(pattern, escape="\\"),
            )
        )
    if query.cursor is not None:
        at, row_id = decode_cursor(query.cursor)
        conditions.append(
            or_(
                AgentActivity.occurred_at < at,
                and_(AgentActivity.occurred_at == at, AgentActivity.id < row_id),
            )
        )
    limit = max(1, min(query.limit, MAX_PAGE_SIZE))
    rows = list(
        (
            await session.scalars(
                select(AgentActivity)
                .where(*conditions)
                .order_by(AgentActivity.occurred_at.desc(), AgentActivity.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    return ActivityPage(rows, encode_cursor(rows[-1]) if more and rows else None)

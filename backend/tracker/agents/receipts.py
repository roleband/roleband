"""Command receipts: an agent write happens once, however often it is sent.

A write is keyed by `(workspace_id, principal_id, operation, idempotency_key)`.
`execute_once` runs one keyed write inside the caller's transaction, in this
order:

1. Serialize the key: a transaction-scoped advisory lock on it, taken before
   any domain lock, so two calls with one key run one after the other and the
   second sees the first's committed receipt.
2. Look the receipt up. The same normalized request (equal `input_hash`)
   replays the committed result, even when the resource has moved on since,
   so a client that lost the reply recovers it. Another request under the same
   key is an `IdempotencyConflict`, never a second write.
3. Only for a new execution, run the write. It takes its own domain lock and
   checks its preconditions there, a stated revision included
   (`RevisionConflict`).
4. Add the receipt to the same transaction. The caller commits the write, its
   audit event and the receipt together, so a rolled-back write leaves no
   receipt, and a receipt never claims a write that did not land.

Nothing here commits: the operation that calls it owns the transaction. Every
domain lock is taken after the key's lock, never before, in every write, so
two writes cannot wait on each other in opposite orders.

The principal is the engine's to name, never the caller's. Until assistants
have their own credentials every agent write acts as one principal,
`LEGACY_AGENT_PRINCIPAL`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import CommandReceipt
from tracker.platform.locks import advisory_xact_lock_pair

#: The one principal every agent write acts as until per-assistant credentials exist.
LEGACY_AGENT_PRINCIPAL = "agent"

#: The two-int lock namespace for one idempotency key (see `tracker/platform/locks.py`).
RECEIPT_LOCK_NAMESPACE = 91252


@dataclass(frozen=True)
class ReceiptKey:
    workspace_id: str
    principal_id: str
    operation: str
    idempotency_key: str

    def lock_key(self) -> int:
        """A signed 32-bit key for the advisory lock. Two keys that share it
        only wait for each other; they never share a receipt."""
        digest = hashlib.sha256(
            "\x1f".join((self.workspace_id, self.principal_id, self.operation, self.idempotency_key)).encode()
        ).digest()
        return int.from_bytes(digest[:4], "big", signed=True)


class IdempotencyConflict(Exception):
    """The key was already used for a different request."""

    def __init__(self, key: ReceiptKey) -> None:
        super().__init__("this idempotency key was used for a different request")
        self.key = key


class RevisionConflict(Exception):
    """The resource moved past the revision the caller read. Checked only when
    a write runs for the first time, never on a replay."""

    def __init__(self, *, expected: int, current: int) -> None:
        super().__init__(f"expected revision {expected}, found {current}")
        self.expected = expected
        self.current = current


def input_hash(operation: str, contract_version: str, normalized_input: dict[str, Any]) -> str:
    """The canonical hash of one request.

    `normalized_input` is the validated input with only the keys the caller
    gave (a missing field and an explicit null are different requests), its
    target ids and stated revision among them. Key order, whitespace and
    escaping do not change the hash; any value does.
    """
    canonical = json.dumps(
        {"operation": operation, "contract_version": contract_version, "input": normalized_input},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Executed:
    """A write's committed-to-be result, and whether it is a replay."""

    result: dict[str, Any]
    replayed: bool


async def lock_key(session: AsyncSession, key: ReceiptKey) -> None:
    await advisory_xact_lock_pair(session, RECEIPT_LOCK_NAMESPACE, key.lock_key())


async def find_receipt(session: AsyncSession, key: ReceiptKey) -> CommandReceipt | None:
    return await session.scalar(
        select(CommandReceipt).where(
            CommandReceipt.workspace_id == key.workspace_id,
            CommandReceipt.principal_id == key.principal_id,
            CommandReceipt.operation == key.operation,
            CommandReceipt.idempotency_key == key.idempotency_key,
        )
    )


def replay(receipt: CommandReceipt, request_hash: str) -> Executed:
    if receipt.input_hash != request_hash:
        raise IdempotencyConflict(
            ReceiptKey(receipt.workspace_id, receipt.principal_id, receipt.operation, receipt.idempotency_key)
        )
    return Executed(result=dict(receipt.result), replayed=True)


async def execute_once(
    session: AsyncSession,
    key: ReceiptKey,
    *,
    request_hash: str,
    contract_version: str,
    write: Callable[[], Awaitable[dict[str, Any]]],
) -> Executed:
    """Replay the receipt for `key`, or run `write` and record its result.

    `write` returns the operation's result as JSON-ready data; it may raise
    `RevisionConflict` or any domain error, and then no receipt is added. The
    caller commits on success and rolls back on any exception.
    """
    await lock_key(session, key)
    receipt = await find_receipt(session, key)
    if receipt is not None:
        return replay(receipt, request_hash)
    result = await write()
    session.add(
        CommandReceipt(
            workspace_id=key.workspace_id,
            principal_id=key.principal_id,
            operation=key.operation,
            idempotency_key=key.idempotency_key,
            input_hash=request_hash,
            contract_version=contract_version,
            result=result,
        )
    )
    await session.flush()
    return Executed(result=result, replayed=False)


async def forget(session: AsyncSession, operations: Collection[str]) -> int:
    """Delete every receipt of `operations` and say how many went.

    A receipt keeps its write's whole answer, so the receipt of a write that
    saved something about the person holds it too. When the person removes
    that, its receipts go with it: a retry under an old key then runs as a new
    write. Nothing else deletes a receipt."""
    if not operations:
        return 0
    removed = await session.execute(delete(CommandReceipt).where(CommandReceipt.operation.in_(list(operations))))
    return removed.rowcount or 0

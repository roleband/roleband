"""Sending a write: under one idempotency key, so a resend never writes twice.

When the caller gives no key the client makes one, sends every attempt of
this invocation under it, and returns it in `meta.idempotency_key`, on the
result and on a failure alike. A write that timed out may have committed: the
caller retries it with that key, which replays the committed outcome, and
never with a new one, which could write again.
"""

from __future__ import annotations

import re
import secrets
import time
from typing import Any

from tracker.cli import transport
from tracker.cli.contexts import Context
from tracker.cli.errors import ClientError

#: The header the engine reads a write's key from.
IDEMPOTENCY_KEY_HEADER = "X-RoleBand-Idempotency-Key"
#: The engine's rule for a key: an opaque token, no content.
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
#: Failures that leave a write unsent or its reply lost: resending it under
#: the same key is safe, since a write that did land replays.
_RESENDABLE = frozenset({"engine_unavailable", "transport_error"})
#: Attempts within one invocation, the first included.
ATTEMPTS = 3
_PAUSE_SECONDS = 0.25


def new_idempotency_key() -> str:
    return f"idk_{secrets.token_hex(16)}"


def send_write(
    context: Context,
    method: str,
    path: str,
    *,
    operation: str,
    body: dict[str, Any],
    deadline: float,
    request_id: str,
    user_agent: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """The engine's envelope for one write, sent under `idempotency_key` or a new one."""
    if idempotency_key is not None and not _KEY.fullmatch(idempotency_key):
        raise ClientError(
            "invalid_arguments",
            "An idempotency key is a token of 8 to 128 letters, digits and _.:-, starting with a letter or digit.",
        )
    key = idempotency_key or new_idempotency_key()
    attempt = 1
    while True:
        try:
            envelope = transport.send(
                context,
                method,
                path,
                operation=operation,
                deadline=deadline,
                request_id=request_id,
                user_agent=user_agent,
                body=body,
                headers={IDEMPOTENCY_KEY_HEADER: key},
            )
        except ClientError as error:
            error.idempotency_key = key
            error.details.update(
                {"operation": operation, "idempotency_key": key, "workspace_id": context.workspace_id}
            )
            pause = min(_PAUSE_SECONDS * attempt, deadline - time.monotonic())
            if error.code not in _RESENDABLE or attempt >= ATTEMPTS or pause <= 0:
                raise
            time.sleep(pause)
            attempt += 1
            continue
        meta = envelope["meta"]
        if meta.get("idempotency_key") is None:
            meta["idempotency_key"] = key
        return envelope

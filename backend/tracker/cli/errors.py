"""The client's own failures, and the envelope it prints for any outcome."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from tracker.agents.operations.outcomes import CONTRACT_VERSION, OUTCOMES, outcome

#: The operation named by a parse failure that names no command.
PARSE_OPERATION = "cli.parse"


class ClientError(Exception):
    """A failure the client answers itself, with a code from `OUTCOMES`."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        next_actions: list[dict[str, Any]] | None = None,
    ) -> None:
        if code not in OUTCOMES:
            raise ValueError(f"{code!r} is not an error code in outcomes.OUTCOMES")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.next_actions = next_actions or []
        #: The key a write was sent under, so a caller whose write timed out
        #: can retry it under the same key (`tracker/cli/writes.py`).
        self.idempotency_key: str | None = None


def new_request_id() -> str:
    return f"req_{secrets.token_hex(12)}"


def _meta(idempotency_key: str | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "next_cursor": None,
        "partial": False,
        "truncated": False,
        "data_classes": [],
    }
    if idempotency_key is not None:
        meta["idempotency_key"] = idempotency_key
    return meta


def success_envelope(operation: str, data: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    """A result the client answered itself, from bundled metadata: no engine
    was asked, so no workspace is named."""
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "workspace_id": None,
        "operation": operation,
        "ok": True,
        "data": data,
        "meta": _meta(),
        "warnings": [],
        "error": None,
    }


def error_envelope(
    operation: str, error: ClientError, *, request_id: str, workspace_id: str | None = None
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "workspace_id": workspace_id,
        "operation": operation,
        "ok": False,
        "data": None,
        "meta": _meta(error.idempotency_key),
        "warnings": [],
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": outcome(error.code).retryable,
            "details": error.details,
            "next_actions": error.next_actions,
        },
    }

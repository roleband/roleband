"""One request to the engine over loopback, answered as the engine's envelope.

`http.client` directly: it follows no redirect and consults no proxy, so a
request reaches the configured address or fails. A reply is accepted only as
an envelope of this contract's major version for the operation asked; anything
else (an older engine, another program on the port) is `contract_incompatible`,
except an engine that accepts only signed requests, which this client does not
make: that refusal is `transport_unverified`.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import threading
import time
from typing import Any
from urllib.parse import quote, urlencode

from tracker.agents.operations.outcomes import compatible
from tracker.cli.contexts import Context
from tracker.cli.errors import ClientError
from tracker.platform.agent_hosts import HOST_HEADER, running_host

PREFIX = "/api/agent/v1"
REQUEST_ID_HEADER = "X-RoleBand-Request-Id"
#: The bounded part of the deadline spent connecting.
CONNECT_SECONDS = 3.0
#: A reply larger than this is refused rather than buffered.
MAX_REPLY_BYTES = 16 * 1024 * 1024
#: The code an engine that accepts only signed requests refuses an unsigned one with.
_SIGNATURE_REQUIRED = "engine-locked"
_ENVELOPE_KEYS = {"contract_version", "request_id", "workspace_id", "operation", "ok", "data", "meta", "warnings", "error"}


def path_for(*segments: str, query: dict[str, str] | None = None) -> str:
    path = "/".join([PREFIX, *(quote(segment, safe="") for segment in segments)])
    return f"{path}?{urlencode(query)}" if query else path


def get(
    context: Context,
    path: str,
    *,
    operation: str,
    deadline: float,
    request_id: str,
    user_agent: str,
) -> dict[str, Any]:
    """The engine's envelope for `operation`, whether it succeeded or not."""
    return send(
        context, "GET", path, operation=operation, deadline=deadline, request_id=request_id, user_agent=user_agent
    )


def send(
    context: Context,
    method: str,
    path: str,
    *,
    operation: str,
    deadline: float,
    request_id: str,
    user_agent: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """`get` for any method, with an optional JSON object body and extra headers."""
    try:
        payload = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise ClientError(
            "invalid_arguments", "The input is not JSON: it holds a value JSON cannot carry, such as NaN."
        ) from None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ClientError("deadline_exceeded", "The deadline passed before the request was sent.")
    connection = http.client.HTTPConnection(context.host, context.port, timeout=min(CONNECT_SECONDS, remaining))
    try:
        try:
            connection.connect()
        except OSError as error:
            if isinstance(error, TimeoutError) and time.monotonic() >= deadline:
                raise _late(context, operation) from None
            raise ClientError(
                "engine_unavailable",
                f"No engine answers at context {context.name!r}. Open the app, or start the engine for this context.",
                details={"context": context.name, "url": context.url, "reason": type(error).__name__},
            ) from None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ClientError("deadline_exceeded", "The deadline passed while connecting.")
        assert connection.sock is not None
        sock = connection.sock
        sock.settimeout(remaining)
        # A socket timeout bounds each receive, not the whole exchange: a peer
        # that trickles bytes would outlast it. The watchdog ends the exchange
        # at the deadline itself.
        expired = threading.Event()
        watchdog = threading.Timer(remaining, _expire, args=(sock, expired))
        watchdog.daemon = True
        watchdog.start()
        try:
            connection.request(
                method,
                path,
                body=payload,
                headers={
                    **(headers or {}),
                    **({"Content-Type": "application/json"} if payload is not None else {}),
                    "Accept": "application/json",
                    "User-Agent": user_agent,
                    REQUEST_ID_HEADER: request_id,
                    # The host this command runs under, for the person's activity list.
                    **({HOST_HEADER: host} if (host := running_host(os.environ)) else {}),
                },
            )
            response = connection.getresponse()
            reply = response.read(MAX_REPLY_BYTES + 1)
        except (TimeoutError, http.client.HTTPException, OSError) as error:
            if expired.is_set() or isinstance(error, TimeoutError):
                raise _late(context, operation) from None
            raise ClientError(
                "transport_error",
                "The connection to the engine failed before a reply arrived.",
                details={"context": context.name, "reason": type(error).__name__},
            ) from None
        finally:
            watchdog.cancel()
        if expired.is_set():
            raise _late(context, operation)
    finally:
        connection.close()
    if len(reply) > MAX_REPLY_BYTES:
        raise ClientError("transport_error", "The engine's reply is larger than the client accepts.")
    return _envelope(reply, status=response.status, content_type=response.getheader("Content-Type", ""),
                     operation=operation, context=context)


def _expire(sock: socket.socket, expired: threading.Event) -> None:
    expired.set()
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _late(context: Context, operation: str) -> ClientError:
    return ClientError(
        "deadline_exceeded",
        "The engine did not answer before the deadline. Accepted work, if any, continues.",
        details={"context": context.name, "operation": operation},
    )


def _envelope(body: bytes, *, status: int, content_type: str, operation: str, context: Context) -> dict[str, Any]:
    incompatible = ClientError(
        "contract_incompatible",
        "The engine at this context does not answer this client's agent contract. Update the app or the client.",
        details={"http_status": status},
    )
    if not content_type.startswith("application/json"):
        raise incompatible
    try:
        envelope = json.loads(body)
    except ValueError:
        raise incompatible from None
    if status == 401 and _signature_required(envelope):
        raise ClientError(
            "transport_unverified",
            "The engine at this context accepts only signed requests, which this client does not make yet.",
            details={"context": context.name, "trust": "signed_local_http"},
        )
    if not isinstance(envelope, dict) or not set(envelope) >= _ENVELOPE_KEYS:
        raise incompatible
    if not compatible(envelope.get("contract_version")):
        incompatible.details["contract_version"] = envelope.get("contract_version")
        raise incompatible
    if (
        envelope.get("operation") != operation
        or not isinstance(envelope.get("ok"), bool)
        or not isinstance(envelope.get("request_id"), str)
        or not isinstance(envelope.get("workspace_id"), str | None)
        or not isinstance(envelope.get("meta"), dict)
        or not isinstance(envelope.get("warnings"), list)
    ):
        raise incompatible
    if envelope["ok"] is False and not _is_error(envelope.get("error")):
        raise incompatible
    return envelope


def _signature_required(reply: object) -> bool:
    detail = reply.get("detail") if isinstance(reply, dict) else None
    return isinstance(detail, dict) and detail.get("code") == _SIGNATURE_REQUIRED


def _is_error(error: object) -> bool:
    """Whether a failure carries every field the client reads from it."""
    return (
        isinstance(error, dict)
        and isinstance(error.get("code"), str)
        and isinstance(error.get("message"), str)
        and isinstance(error.get("retryable"), bool)
        and isinstance(error.get("details"), dict)
        and isinstance(error.get("next_actions"), list)
    )

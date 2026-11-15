"""The one response shape every operation answers with, success or failure.

`ok` true carries the operation's typed `data` and a null `error`; `ok` false
carries a null `data` and a typed `error` whose `code` is a key of
`outcomes.OUTCOMES`. `workspace_id` is null until the engine has identified
the workspace, and it is never filled in by the client.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

from tracker.agents.operations.descriptor import DataClass
from tracker.agents.operations.outcomes import CONTRACT_VERSION, OUTCOMES, outcome

_DIAGNOSTIC: JsonDict = {"x-text": "diagnostic"}
_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

def new_request_id() -> str:
    return f"req_{secrets.token_hex(12)}"


def request_id_or_new(supplied: str | None) -> str:
    """The caller's request id when it is a plain token, else a new one."""
    if supplied and _REQUEST_ID.fullmatch(supplied):
        return supplied
    return new_request_id()


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvelopeMeta(_Wire):
    observed_at: datetime
    next_cursor: str | None = Field(default=None, json_schema_extra=_IDENTIFIER)
    partial: bool = False
    truncated: bool = False
    data_classes: list[DataClass] = Field(default_factory=list)
    #: The key a write ran under, on its result and on its failure alike.
    idempotency_key: str | None = Field(default=None, json_schema_extra=_IDENTIFIER)
    #: True when a write's result is its committed receipt, answered again for
    #: a retry: it describes that write's outcome, not the resource as it is now.
    replayed: bool = False


class EnvelopeNotice(_Wire):
    """A structured warning: a stable code and English for logs."""

    code: str = Field(json_schema_extra=_CODE)
    message: str = Field(json_schema_extra=_DIAGNOSTIC)


class NextAction(_Wire):
    """A typed suggestion of an operation to call next. Never a shell string,
    and never a permission the caller did not already have."""

    operation: str = Field(json_schema_extra=_IDENTIFIER)
    arguments: dict[str, Any] = Field(default_factory=dict)


class EnvelopeError(_Wire):
    code: str = Field(json_schema_extra=_CODE)
    message: str = Field(json_schema_extra=_DIAGNOSTIC)
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[NextAction] = Field(default_factory=list)


class Envelope[T](_Wire):
    contract_version: str = Field(default=CONTRACT_VERSION, json_schema_extra=_IDENTIFIER)
    request_id: str = Field(json_schema_extra=_IDENTIFIER)
    workspace_id: str | None = Field(json_schema_extra=_IDENTIFIER)
    operation: str = Field(json_schema_extra=_IDENTIFIER)
    ok: bool
    data: T | None
    meta: EnvelopeMeta
    warnings: list[EnvelopeNotice] = Field(default_factory=list)
    error: EnvelopeError | None


class OperationError(Exception):
    """Raised by a handler or the shared route core; answered as an envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        next_actions: list[NextAction] | None = None,
    ) -> None:
        if code not in OUTCOMES:
            raise ValueError(f"{code!r} is not an error code in outcomes.OUTCOMES")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.next_actions = next_actions or []

    def body(self) -> EnvelopeError:
        return EnvelopeError(
            code=self.code,
            message=self.message,
            retryable=outcome(self.code).retryable,
            details=self.details,
            next_actions=self.next_actions,
        )


def now() -> datetime:
    return datetime.now(UTC)


def success(
    operation: str,
    data: BaseModel,
    *,
    request_id: str,
    workspace_id: str | None,
    data_classes: tuple[DataClass, ...] = (),
    warnings: list[EnvelopeNotice] | None = None,
    idempotency_key: str | None = None,
    replayed: bool = False,
) -> Envelope[Any]:
    return Envelope[Any](
        request_id=request_id,
        workspace_id=workspace_id,
        operation=operation,
        ok=True,
        data=data,
        meta=EnvelopeMeta(
            observed_at=now(), data_classes=list(data_classes), idempotency_key=idempotency_key, replayed=replayed
        ),
        warnings=warnings or [],
        error=None,
    )


def partial(
    operation: str,
    data: BaseModel,
    error: OperationError,
    *,
    request_id: str,
    workspace_id: str | None,
    data_classes: tuple[DataClass, ...] = (),
    warnings: list[EnvelopeNotice] | None = None,
    truncated: bool = False,
) -> Envelope[Any]:
    """A batch some of whose items failed: the one failure that carries `data`,
    the typed per-item outcomes. `ok` stays false, so a caller that checks one
    field never takes a partial result for a complete one. `truncated` marks
    a value in `data` that was cut to fit, as on a complete answer."""
    if error.code != "partial_result":
        raise ValueError(f"a partial batch answers partial_result, not {error.code!r}")
    return Envelope[Any](
        request_id=request_id,
        workspace_id=workspace_id,
        operation=operation,
        ok=False,
        data=data,
        meta=EnvelopeMeta(observed_at=now(), partial=True, truncated=truncated, data_classes=list(data_classes)),
        warnings=warnings or [],
        error=error.body(),
    )


def failure(
    operation: str,
    error: OperationError,
    *,
    request_id: str,
    workspace_id: str | None,
    idempotency_key: str | None = None,
) -> Envelope[Any]:
    return Envelope[Any](
        request_id=request_id,
        workspace_id=workspace_id,
        operation=operation,
        ok=False,
        data=None,
        meta=EnvelopeMeta(observed_at=now(), idempotency_key=idempotency_key),
        warnings=[],
        error=error.body(),
    )

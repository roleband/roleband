"""The shared core of every `/api/agent/v1/` route: policy, envelope, errors.

A route declares its operation and takes `Operation` as a dependency:

    @router.get(path, response_model=Envelope[Result], openapi_extra=operation_route(DESCRIPTOR))
    async def handler(op: Annotated[OperationContext, Depends(admitted(DESCRIPTOR))]) -> ...:
        return op.ok(Result(...))

`admitted` checks the person's agent switches before the handler runs and
names the workspace. `AgentRoute`, the router's route class, answers every
failure as an envelope with the code's HTTP status: a refusal, invalid input,
an `OperationError` from the handler, or an unexpected exception. No route
dispatches by name; each operation keeps its own reviewed route.

A write route takes its input from a JSON body and its idempotency key from
the `X-RoleBand-Idempotency-Key` header, and runs its domain write through
`OperationContext.write`:

    async def handler(op: Annotated[OperationContext, Depends(admitted(DESCRIPTOR))]) -> ...:
        payload = op.input_as(Patch)
        async def apply() -> Result:
            row = await domain_write(op.session, ..., actor=op.actor, expected_revision=payload.if_revision)
            return Result(...)
        return await op.write(apply)

`write` replays the committed receipt of an identical earlier request, refuses
another request under the same key, and otherwise runs `apply` and commits
the write, its audit event and its receipt together (`tracker/agents/receipts.py`).
The actor a write records comes from the principal, never from the input.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.config import AgentAccessConfig, get_agent_access
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.descriptor import DataClass, OperationDescriptor
from tracker.agents.operations.envelope import (
    Envelope,
    EnvelopeNotice,
    NextAction,
    OperationError,
    failure,
    partial,
    request_id_or_new,
    success,
)
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.policy import admit, shared
from tracker.agents.operations.workspace import get_workspace_id
from tracker.agents.receipts import (
    LEGACY_AGENT_PRINCIPAL,
    IdempotencyConflict,
    ReceiptKey,
    RevisionConflict,
    execute_once,
    input_hash,
)
from tracker.api.deps import SessionDep

log = logging.getLogger(__name__)

PREFIX = "/api/agent/v1"
#: The header a client may send its own request id in, echoed in the envelope.
REQUEST_ID_HEADER = "X-RoleBand-Request-Id"
#: The header a write's idempotency key travels in. It is never part of the
#: operation's input, so it never enters the request's hash.
IDEMPOTENCY_KEY_HEADER = "X-RoleBand-Idempotency-Key"
#: A key is an opaque token the client makes; it carries no content.
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
#: The methods whose JSON body is part of an operation's input.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
#: A body larger than this is refused before it is parsed.
MAX_BODY_BYTES = 1024 * 1024
_OPERATION_KEY = "x-operation"

#: This engine process's session id when no local discovery names one: it
#: changes with every start, and it is never the workspace id.
_PROCESS_SESSION = secrets.token_hex(16)

InputT = TypeVar("InputT", bound=BaseModel)


def operation_route(descriptor: OperationDescriptor) -> dict[str, Any]:
    """The route's `openapi_extra`: names its operation in the schema and to `AgentRoute`."""
    return {_OPERATION_KEY: descriptor.id}


def engine_session_id(request: Request) -> str:
    authority = getattr(request.app.state, "local_authority", None)
    return authority.instance if authority is not None else _PROCESS_SESSION


@dataclass(frozen=True)
class OperationContext:
    descriptor: OperationDescriptor
    request_id: str
    workspace_id: str
    input: BaseModel
    #: The switches that admitted this call, read once per request.
    switches: AgentAccessConfig
    #: The request's session; a write commits it through `write`.
    session: AsyncSession
    #: Who is calling, named by the engine. One legacy principal until
    #: assistants have credentials of their own.
    principal_id: str = LEGACY_AGENT_PRINCIPAL
    #: A write's key from `IDEMPOTENCY_KEY_HEADER`; None on a read.
    idempotency_key: str | None = None

    @property
    def actor(self) -> Literal["agent"]:
        """The actor a domain write records for this call: derived from the
        principal, so no input field can claim to be the person."""
        return "agent"

    def shares(self, category: DataClass) -> bool:
        """Whether this call may answer `category` (`policy.shared`)."""
        return shared(self.switches, category)

    @property
    def answered_classes(self) -> tuple[DataClass, ...]:
        """The declared categories this call's answer may hold: a category
        the person does not share is left out of the answer, and of its meta."""
        return tuple(category for category in self.descriptor.data_classes if self.shares(category))

    def input_as(self, model: type[InputT]) -> InputT:
        if not isinstance(self.input, model):
            raise TypeError(f"{self.descriptor.id} takes {type(self.input).__name__}, not {model.__name__}")
        return self.input

    def ok(self, data: BaseModel, *, warnings: list[EnvelopeNotice] | None = None) -> Envelope[Any]:
        return success(
            self.descriptor.id,
            data,
            request_id=self.request_id,
            workspace_id=self.workspace_id,
            data_classes=self.answered_classes,
            warnings=warnings,
        )

    def partial(
        self, data: BaseModel, error: OperationError, *, warnings: list[EnvelopeNotice] | None = None,
        truncated: bool = False,
    ) -> JSONResponse:
        """A batch answered in part: `partial_result` with the per-item outcomes
        in `data`, at the code's HTTP status."""
        envelope = partial(
            self.descriptor.id,
            data,
            error,
            request_id=self.request_id,
            workspace_id=self.workspace_id,
            data_classes=self.answered_classes,
            warnings=warnings,
            truncated=truncated,
        )
        return JSONResponse(envelope.model_dump(mode="json"), status_code=outcome(error.code).http_status)

    async def write(
        self,
        apply: Callable[[], Awaitable[BaseModel]],
        *,
        on_revision_conflict: list[NextAction] | None = None,
        shown: Callable[[Any], BaseModel] | None = None,
    ) -> Envelope[Any]:
        """Run one keyed write, or replay its receipt, and commit.

        The key is serialized and its receipt looked up first, so an identical
        retry replays the committed result even after the resource has moved
        on; only a new execution runs `apply`, which takes the domain lock and
        checks the revision the caller stated. The write, its audit event and
        the receipt commit together, and any failure rolls all three back.
        The receipt keeps the result whole; `shown`, when given, makes the
        answer, fresh or replayed, from it under this call's categories.
        """
        descriptor = self.descriptor
        if descriptor.access != "write" or descriptor.idempotency != "required_key" or self.idempotency_key is None:
            raise TypeError(f"{descriptor.id} is not a keyed write")
        key = ReceiptKey(self.workspace_id, self.principal_id, descriptor.id, self.idempotency_key)
        request_hash = input_hash(
            descriptor.id, descriptor.version, self.input.model_dump(mode="json", exclude_unset=True)
        )

        async def run() -> dict[str, Any]:
            result = await apply()
            if not isinstance(result, descriptor.result):
                raise TypeError(f"{descriptor.id} answers {descriptor.result.__name__}, not {type(result).__name__}")
            return result.model_dump(mode="json")

        try:
            executed = await execute_once(
                self.session, key, request_hash=request_hash, contract_version=descriptor.version, write=run
            )
            await self.session.commit()
        except IdempotencyConflict:
            await self.session.rollback()
            raise OperationError(
                "idempotency_conflict",
                "This idempotency key was already used for a different request. Use a new key for a new request.",
                details={"idempotency_key": self.idempotency_key},
            ) from None
        except RevisionConflict as conflict:
            await self.session.rollback()
            raise OperationError(
                "revision_conflict",
                "This record changed after you read it. Read it again and decide anew.",
                details={"expected_revision": conflict.expected, "current_revision": conflict.current},
                next_actions=on_revision_conflict,
            ) from None
        except BaseException:
            await self.session.rollback()
            raise
        result = descriptor.result.model_validate(executed.result)
        return success(
            descriptor.id,
            result if shown is None else shown(result),
            request_id=self.request_id,
            workspace_id=self.workspace_id,
            data_classes=self.answered_classes,
            idempotency_key=self.idempotency_key,
            replayed=executed.replayed,
        )


def admitted(descriptor: OperationDescriptor) -> Callable[..., Awaitable[OperationContext]]:
    """The dependency that admits one operation: switches, then workspace, then input.

    The switches come first, so a refused caller learns nothing about the
    workspace or whether its input was valid. The input is the descriptor's
    model, validated from the path, the query and, on POST, PUT and PATCH, a
    JSON object body: an unknown key is an error, and so is a key given twice.
    A keyed write also needs its idempotency key, checked before its input,
    so a request refused here never reaches a receipt.
    """
    lists = list_fields(descriptor)

    async def dependency(request: Request, session: SessionDep) -> OperationContext:
        switches = await get_agent_access(session)
        admit(descriptor, switches)
        workspace_id = await get_workspace_id(session)
        if workspace_id is None:
            raise OperationError("engine_not_ready", "The engine has not finished preparing the workspace.")
        request.state.agent_workspace_id = workspace_id
        key: str | None = None
        if descriptor.idempotency == "required_key":
            key = request.state.agent_idempotency_key
            if key is None:
                raise OperationError(
                    "invalid_input",
                    "A write needs an idempotency key: a token of 8 to 128 letters, digits and _.:-",
                    details={"header": IDEMPOTENCY_KEY_HEADER},
                )
        return OperationContext(
            descriptor,
            request.state.agent_request_id,
            workspace_id,
            await _input(descriptor, request, lists),
            switches,
            session,
            idempotency_key=key,
        )

    return dependency


def idempotency_key_of(request: Request) -> str | None:
    """The request's idempotency key when it is a well-formed token, else None."""
    supplied = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    return supplied if supplied and _IDEMPOTENCY_KEY.fullmatch(supplied) else None


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key is repeated")
    return dict(pairs)


async def _body(request: Request) -> dict[str, Any]:
    if request.method not in _BODY_METHODS:
        return {}
    too_large = OperationError("invalid_input", "The request body is larger than the engine accepts.")
    chunks: list[bytes] = []
    size = 0
    # Read in chunks and stop at the bound, so an oversized body is never held whole.
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise too_large
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        return {}
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_refuse_duplicate_keys)
    except (UnicodeDecodeError, ValueError):
        raise OperationError(
            "invalid_input", "The request body is not one JSON object with unique keys in UTF-8."
        ) from None
    if not isinstance(body, dict):
        raise OperationError("invalid_input", "The request body is not a JSON object.")
    return body


def list_fields(descriptor: OperationDescriptor) -> frozenset[str]:
    """The input fields that take a list. A query string cannot tell one value
    from a list of one, so these read every value given as a list, and the
    others refuse a key given more than once."""
    properties = descriptor.input.model_json_schema().get("properties", {})
    return frozenset(
        name for name, prop in properties.items()
        if prop.get("type") == "array" or any(option.get("type") == "array" for option in prop.get("anyOf", ()))
    )


async def _input(descriptor: OperationDescriptor, request: Request, lists: frozenset[str]) -> BaseModel:
    raw: dict[str, Any] = await _body(request)
    for key in request.query_params:
        if key in raw:
            raise OperationError("invalid_input", f"{key!r} is given twice.", details={"field": key})
        values = request.query_params.getlist(key)
        raw[key] = values if key in lists else values[0] if len(values) == 1 else values
    for key, value in request.path_params.items():
        if key in raw:
            raise OperationError("invalid_input", f"{key!r} is given twice.", details={"field": key})
        raw[key] = value
    try:
        return descriptor.input.model_validate(raw)
    except ValidationError as error:
        raise OperationError(
            "invalid_input", "The input does not match the operation's schema.",
            details=_validation_details(error),
        ) from None


def _validation_details(error: RequestValidationError | ValidationError) -> dict[str, Any]:
    # Location and kind only: the offending value can be anything the caller sent.
    return {
        "errors": [
            {"location": [str(part) for part in item.get("loc", ())], "type": str(item.get("type", ""))}
            for item in error.errors()
        ]
    }


def _parameters(descriptor: OperationDescriptor, path: str, *, body: bool = False) -> list[dict[str, Any]]:
    """The route's OpenAPI parameters, from the operation's input model: a field
    named in the path is a path parameter; every other field is a query
    parameter, or, on a route that takes a body, part of the body instead."""
    schema = descriptor.input.model_json_schema()
    properties = schema.get("properties", {})
    required = set(schema.get("required", ()))
    in_path = set(re.findall(r"{([^}:]+)}", path))
    if missing := in_path - set(properties):
        raise ValueError(f"{path} names {sorted(missing)}, which {descriptor.id}'s input does not")
    return [
        {
            "name": name,
            "in": "path" if name in in_path else "query",
            "required": name in in_path or name in required,
            "schema": {key: value for key, value in prop.items() if key != "description"},
            **({"description": prop["description"]} if "description" in prop else {}),
        }
        for name, prop in properties.items()
        if name in in_path or not body
    ]


def _inline(node: Any, definitions: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
    """`node` with every `#/$defs/` reference replaced by its definition, so a
    body schema stands alone in the route. A model that contains itself is
    described as an object at the point it recurs."""
    if isinstance(node, list):
        return [_inline(item, definitions, seen) for item in node]
    if not isinstance(node, dict):
        return node
    reference = node.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        name = reference.removeprefix("#/$defs/")
        if name in seen or name not in definitions:
            return {"type": "object"}
        rest = {key: value for key, value in node.items() if key != "$ref"}
        return {**_inline(definitions[name], definitions, seen | {name}), **_inline(rest, definitions, seen)}
    return {key: _inline(value, definitions, seen) for key, value in node.items() if key != "$defs"}


def _request_body(descriptor: OperationDescriptor, path: str) -> dict[str, Any]:
    """The OpenAPI body of a route that takes one: the input's fields outside
    the path, nested models inlined."""
    schema = descriptor.input.model_json_schema()
    in_path = set(re.findall(r"{([^}:]+)}", path))
    body = _inline(
        {
            **schema,
            "properties": {name: prop for name, prop in schema.get("properties", {}).items() if name not in in_path},
            "required": [name for name in schema.get("required", ()) if name not in in_path],
        },
        schema.get("$defs", {}),
    )
    return {"required": True, "content": {"application/json": {"schema": body}}}


class AgentRoute(APIRoute):
    """Answers every outcome of an agent route as an envelope."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        operation = (self.openapi_extra or {}).get(_OPERATION_KEY)
        descriptor = CATALOG.get(operation) if isinstance(operation, str) else None
        if descriptor is None or self.openapi_extra is None:
            raise ValueError(f"agent route {self.path} names no catalogued operation; pass operation_route(...)")
        takes_body = bool(self.methods & _BODY_METHODS)
        self.openapi_extra["parameters"] = _parameters(descriptor, self.path, body=takes_body)
        if takes_body:
            self.openapi_extra["requestBody"] = _request_body(descriptor, self.path)
        if descriptor.idempotency == "required_key":
            self.openapi_extra["parameters"].append(
                {"name": IDEMPOTENCY_KEY_HEADER, "in": "header", "required": True, "schema": {"type": "string"}}
            )
        operation = descriptor.id
        keyed = descriptor.idempotency == "required_key"

        async def answer(request: Request) -> Response:
            request.state.agent_request_id = request_id_or_new(request.headers.get(REQUEST_ID_HEADER))
            request.state.agent_workspace_id = None
            request.state.agent_idempotency_key = idempotency_key_of(request) if keyed else None
            try:
                return await handler(request)
            except OperationError as error:
                refused = error
            except RequestValidationError as error:
                refused = OperationError(
                    "invalid_input", "The input does not match the operation's schema.",
                    details=_validation_details(error),
                )
            except Exception:
                log.exception("agent operation %s failed", operation)
                refused = OperationError("internal_error", "The engine failed to answer this operation.")
            envelope = failure(
                operation,
                refused,
                request_id=request.state.agent_request_id,
                workspace_id=request.state.agent_workspace_id,
                idempotency_key=request.state.agent_idempotency_key,
            )
            return JSONResponse(envelope.model_dump(mode="json"), status_code=outcome(refused.code).http_status)

        return answer

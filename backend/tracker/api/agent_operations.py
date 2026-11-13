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
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

from tracker.agents.config import AgentAccessConfig, get_agent_access
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.descriptor import OperationDescriptor
from tracker.agents.operations.envelope import (
    Envelope,
    EnvelopeNotice,
    OperationError,
    failure,
    request_id_or_new,
    success,
)
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.policy import admit
from tracker.agents.operations.workspace import get_workspace_id
from tracker.api.deps import SessionDep

log = logging.getLogger(__name__)

PREFIX = "/api/agent/v1"
#: The header a client may send its own request id in, echoed in the envelope.
REQUEST_ID_HEADER = "X-RoleBand-Request-Id"
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
            data_classes=self.descriptor.data_classes,
            warnings=warnings,
        )


def admitted(descriptor: OperationDescriptor) -> Callable[..., Awaitable[OperationContext]]:
    """The dependency that admits one operation: switches, then workspace, then input.

    The switches come first, so a refused caller learns nothing about the
    workspace or whether its input was valid. The input is the descriptor's
    model, validated from the path and query: an unknown key is an error.
    """

    async def dependency(request: Request, session: SessionDep) -> OperationContext:
        switches = await get_agent_access(session)
        admit(descriptor, switches)
        workspace_id = await get_workspace_id(session)
        if workspace_id is None:
            raise OperationError("engine_not_ready", "The engine has not finished preparing the workspace.")
        request.state.agent_workspace_id = workspace_id
        return OperationContext(
            descriptor, request.state.agent_request_id, workspace_id, _input(descriptor, request), switches
        )

    return dependency


def _input(descriptor: OperationDescriptor, request: Request) -> BaseModel:
    raw: dict[str, Any] = {}
    for key in request.query_params:
        values = request.query_params.getlist(key)
        raw[key] = values[0] if len(values) == 1 else values
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


def _parameters(descriptor: OperationDescriptor, path: str) -> list[dict[str, Any]]:
    """The route's OpenAPI parameters, from the operation's input model: a field
    named in the path is a path parameter, every other field a query parameter."""
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
    ]


class AgentRoute(APIRoute):
    """Answers every outcome of an agent route as an envelope."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        operation = (self.openapi_extra or {}).get(_OPERATION_KEY)
        descriptor = CATALOG.get(operation) if isinstance(operation, str) else None
        if descriptor is None or self.openapi_extra is None:
            raise ValueError(f"agent route {self.path} names no catalogued operation; pass operation_route(...)")
        self.openapi_extra["parameters"] = _parameters(descriptor, self.path)
        operation = descriptor.id

        async def answer(request: Request) -> Response:
            request.state.agent_request_id = request_id_or_new(request.headers.get(REQUEST_ID_HEADER))
            request.state.agent_workspace_id = None
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
            )
            return JSONResponse(envelope.model_dump(mode="json"), status_code=outcome(refused.code).http_status)

        return answer

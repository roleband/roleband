"""The agent operations, one explicit route each, under `/api/agent/v1/`.

The `roleband` client is this router's caller. Each route names its operation's
descriptor (`tracker/agents/operations/`); the switches, the envelope and
error mapping are the shared core in `tracker/api/agent_operations.py`. A new
operation is a descriptor, its registration and one route here: never a route
that dispatches by name.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from tracker import __version__
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.envelope import Envelope, NextAction, OperationError
from tracker.agents.operations.meta import (
    CAPABILITIES,
    DESCRIBE,
    STATUS,
    AgentSwitchState,
    CapabilitiesInput,
    CapabilitiesResult,
    DescribeInput,
    EngineTrust,
    OperationDetail,
    OperationSummary,
    StatusResult,
)
from tracker.agents.operations.outcomes import CONTRACT_VERSION
from tracker.agents.operations.policy import availability
from tracker.api.agent_operations import (
    PREFIX,
    AgentRoute,
    OperationContext,
    admitted,
    engine_session_id,
    operation_route,
)

router = APIRouter(route_class=AgentRoute, tags=["agent"])


@router.get(f"{PREFIX}/status", response_model=Envelope[StatusResult], openapi_extra=operation_route(STATUS))
async def status(
    request: Request,
    op: Annotated[OperationContext, Depends(admitted(STATUS))],
) -> Envelope[Any]:
    switches = op.switches
    authority = getattr(request.app.state, "local_authority", None)
    return op.ok(
        StatusResult(
            workspace_id=op.workspace_id,
            engine_session_id=engine_session_id(request),
            engine_version=__version__,
            contract_version=CONTRACT_VERSION,
            trust=EngineTrust(mode="signed_local_http", verified=True)
            if authority is not None
            else EngineTrust(mode="local_loopback", verified=False),
            access=AgentSwitchState(enabled=switches.enabled, allow_writes=switches.allow_writes),
        )
    )


@router.get(
    f"{PREFIX}/capabilities",
    response_model=Envelope[CapabilitiesResult],
    openapi_extra=operation_route(CAPABILITIES),
)
async def capabilities(
    op: Annotated[OperationContext, Depends(admitted(CAPABILITIES))],
) -> Envelope[Any]:
    tier = op.input_as(CapabilitiesInput).tier
    return op.ok(
        CapabilitiesResult(
            contract_version=CONTRACT_VERSION,
            supported_contract_versions=[CONTRACT_VERSION],
            engine_version=__version__,
            metadata_source="engine",
            operations=[
                OperationSummary.model_validate(descriptor.summary_entry(availability(descriptor, op.switches)))
                for descriptor in CATALOG.in_tier(tier)
            ],
        )
    )


@router.get(
    f"{PREFIX}/operations/{{operation}}",
    response_model=Envelope[OperationDetail],
    openapi_extra=operation_route(DESCRIBE),
)
async def describe(
    op: Annotated[OperationContext, Depends(admitted(DESCRIBE))],
) -> Envelope[Any]:
    wanted = op.input_as(DescribeInput).operation
    descriptor = CATALOG.get(wanted)
    if descriptor is None:
        raise OperationError(
            "unknown_operation",
            "This engine offers no operation by that name.",
            details={"operation": wanted},
            next_actions=[NextAction(operation=CAPABILITIES.id, arguments={})],
        )
    return op.ok(
        OperationDetail.model_validate(descriptor.full_entry(availability(descriptor, op.switches), source="engine"))
    )

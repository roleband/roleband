"""The agent operations, one explicit route each, under `/api/agent/v1/`.

The `roleband` client is this router's caller. Each route names its operation's
descriptor (`tracker/agents/operations/`); the switches, the envelope and
error mapping are the shared core in `tracker/api/agent_operations.py`. A new
operation is a descriptor, its registration and one route here: never a route
that dispatches by name.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from tracker import __version__
from tracker.agents.operations import opportunities, pursuits, radar, recipes, search, vocabulary
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.envelope import Envelope, EnvelopeNotice, NextAction, OperationError
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
from tracker.api.deps import SessionDep, end_read

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


@router.get(
    f"{PREFIX}/radar/summary",
    response_model=Envelope[radar.RadarSummary],
    openapi_extra=operation_route(radar.RADAR_SUMMARY),
)
async def radar_summary(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(radar.RADAR_SUMMARY))],
) -> Envelope[Any]:
    return op.ok(await radar.radar_summary(session, now=datetime.now(UTC)))


@router.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}",
    response_model=Envelope[opportunities.OpportunityView],
    openapi_extra=operation_route(opportunities.OPPORTUNITIES_GET),
)
async def opportunity_get(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(opportunities.OPPORTUNITIES_GET))],
) -> Envelope[Any]:
    found = await opportunities.opportunity(session, op.input_as(opportunities.OpportunityGetInput))
    view = found.root
    if isinstance(view, opportunities.OpportunityDetail) and view.excerpt is not None:
        envelope = op.ok(found, warnings=[EnvelopeNotice(
            code="truncated",
            message="The description is longer than this tool tier's budget; this is an excerpt.",
        )])
        envelope.meta.truncated = True
        return envelope
    return op.ok(found)


@router.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/history",
    response_model=Envelope[opportunities.ListingHistory],
    openapi_extra=operation_route(opportunities.OPPORTUNITIES_HISTORY),
)
async def opportunity_history(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(opportunities.OPPORTUNITIES_HISTORY))],
) -> Envelope[Any]:
    wanted = op.input_as(opportunities.OpportunityHistoryInput).opportunity_id
    return op.ok(await opportunities.history(session, wanted))


@router.get(
    f"{PREFIX}/pursuits",
    response_model=Envelope[pursuits.PursuitList],
    openapi_extra=operation_route(pursuits.PURSUITS_LIST),
)
async def pursuit_list(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(pursuits.PURSUITS_LIST))],
) -> Envelope[Any]:
    page, next_cursor = await pursuits.pursuit_page(
        session, op.input_as(pursuits.PursuitListInput), workspace_id=op.workspace_id
    )
    envelope = op.ok(page)
    envelope.meta.next_cursor = next_cursor
    return envelope


@router.get(
    f"{PREFIX}/pursuits/{{opportunity_id}}",
    response_model=Envelope[pursuits.PursuitItem],
    openapi_extra=operation_route(pursuits.PURSUITS_GET),
)
async def pursuit_get(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(pursuits.PURSUITS_GET))],
) -> Envelope[Any]:
    wanted = op.input_as(pursuits.PursuitGetInput).opportunity_id
    return op.ok(await pursuits.pursuit_of(session, wanted))


@router.get(
    f"{PREFIX}/recipes/contract",
    response_model=Envelope[recipes.RecipeContract],
    openapi_extra=operation_route(recipes.RECIPES_CONTRACT_GET),
)
async def recipe_contract(
    op: Annotated[OperationContext, Depends(admitted(recipes.RECIPES_CONTRACT_GET))],
) -> Envelope[Any]:
    return op.ok(recipes.recipe_contract())


@router.get(
    f"{PREFIX}/sources/inspect",
    response_model=Envelope[recipes.SourceInspection],
    openapi_extra=operation_route(recipes.SOURCES_INSPECT),
)
async def source_inspect(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(recipes.SOURCES_INSPECT))],
) -> Envelope[Any]:
    params = op.input_as(recipes.SourceInspectInput)
    # Admission read the switches; the page is fetched outside a transaction.
    await end_read(session)
    return op.ok(await recipes.inspect_source(params))


@router.post(
    f"{PREFIX}/recipes/validate",
    response_model=Envelope[recipes.RecipeValidation],
    openapi_extra=operation_route(recipes.RECIPES_VALIDATE),
)
async def recipe_validate(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(recipes.RECIPES_VALIDATE))],
) -> Envelope[Any]:
    params = op.input_as(recipes.RecipeValidateInput)
    # Admission read the switches; the listing is read outside a transaction.
    await end_read(session)
    return op.ok(await recipes.validate_recipe(params))


@router.get(
    f"{PREFIX}/opportunities",
    response_model=Envelope[search.SearchPage],
    openapi_extra=operation_route(search.OPPORTUNITIES_SEARCH),
)
async def opportunity_search(
    op: Annotated[OperationContext, Depends(admitted(search.OPPORTUNITIES_SEARCH))],
) -> Envelope[Any]:
    answer = await search.search(op.session, op.input_as(search.SearchInput), workspace_id=op.workspace_id)
    warnings: list[EnvelopeNotice] = []
    if answer.shortened:
        warnings.append(EnvelopeNotice(
            code="page_shortened",
            message="This page stops before the limit to stay within the tool tier's budget; next_cursor continues.",
        ))
    if answer.ranking_truncated:
        warnings.append(EnvelopeNotice(
            code="ranking_truncated",
            message="More postings match than best match ranks, so paging does not reach them all; "
            "narrow the search or sort by another key.",
        ))
    if answer.row_cut:
        warnings.append(EnvelopeNotice(
            code="row_shortened",
            message="A row's text is longer than this tool tier's budget, so it is cut; opportunities.get gives it whole.",
        ))
    envelope = op.ok(answer.page, warnings=warnings or None)
    envelope.meta.next_cursor = answer.next_cursor
    envelope.meta.truncated = answer.ranking_truncated or answer.row_cut
    return envelope


@router.get(
    f"{PREFIX}/vocabulary",
    response_model=Envelope[vocabulary.VocabularyPage],
    openapi_extra=operation_route(vocabulary.VOCABULARY_LIST),
)
async def vocabulary_list(
    op: Annotated[OperationContext, Depends(admitted(vocabulary.VOCABULARY_LIST))],
) -> Envelope[Any]:
    page, next_cursor = await vocabulary.vocabulary_page(
        op.session, op.input_as(vocabulary.VocabularyListInput), workspace_id=op.workspace_id
    )
    envelope = op.ok(page)
    envelope.meta.next_cursor = next_cursor
    return envelope

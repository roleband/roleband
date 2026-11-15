"""The agent operations, one explicit route each, under `/api/agent/v1/`.

The `roleband` client is this router's caller. Each route names its operation's
descriptor (`tracker/agents/operations/`); the switches, the envelope and
error mapping are the shared core in `tracker/api/agent_operations.py`. A new
operation is a descriptor, its registration and one route here: never a route
that dispatches by name.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from tracker import __version__
from tracker.agents.operations import (
    applications,
    export,
    offer,
    opportunities,
    pursuits,
    radar,
    receipts,
    recipes,
    search,
    vocabulary,
)
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
from tracker.agents.operations.policy import availability, withheld
from tracker.api.agent_operations import (
    PREFIX,
    AgentRoute,
    OperationContext,
    admitted,
    engine_session_id,
    operation_route,
)
from tracker.api.deps import SessionDep, end_read
from tracker.api.routers import ops
from tracker.config import get_settings
from tracker.platform.paths import DATA_DIR

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
        # A partial id, such as a resource's name, names the operations under it.
        under = [entry.id for entry in CATALOG if entry.id.startswith(wanted)]
        raise OperationError(
            "unknown_operation",
            f"This engine offers no operation by that name; {len(under)} start with it." if under
            else "This engine offers no operation by that name.",
            details={"operation": wanted, "candidates": under},
            next_actions=[*(NextAction(operation=DESCRIBE.id, arguments={"operation": entry}) for entry in under),
                          NextAction(operation=CAPABILITIES.id, arguments={})],
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
    return op.ok(
        await radar.radar_summary(session, now=datetime.now(UTC), pursuits=op.shares("private_pursuit"))
    )


@router.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}",
    response_model=Envelope[opportunities.OpportunityView],
    openapi_extra=operation_route(opportunities.OPPORTUNITIES_GET),
)
async def opportunity_get(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(opportunities.OPPORTUNITIES_GET))],
) -> Envelope[Any]:
    found = await opportunities.opportunity(
        session, op.input_as(opportunities.OpportunityGetInput),
        withheld=withheld(opportunities.OPPORTUNITIES_GET, op.switches),
    )
    view = found.root
    if isinstance(view, opportunities.OpportunityDetail) and view.excerpt is not None:
        envelope = op.ok(found, warnings=[EnvelopeNotice(
            code="truncated",
            message="This detail is an excerpt; excerpt.continue_with names the calls that read the rest.",
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
    return op.ok(await opportunities.history(session, wanted, pursuits=op.shares("private_pursuit")))


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
        session, op.input_as(pursuits.PursuitListInput), workspace_id=op.workspace_id,
        postings=op.shares("public_posting"),
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
    return op.ok(await pursuits.pursuit_of(session, wanted, postings=op.shares("public_posting")))


@router.put(
    f"{PREFIX}/pursuits/{{opportunity_id}}",
    response_model=Envelope[pursuits.PursuitItem],
    openapi_extra=operation_route(pursuits.PURSUITS_SAVE),
)
async def pursuit_save(
    op: Annotated[OperationContext, Depends(admitted(pursuits.PURSUITS_SAVE))],
) -> Envelope[Any]:
    params = op.input_as(pursuits.PursuitSaveInput)
    return await op.write(
        lambda: pursuits.save_pursuit(op.session, params, actor=op.actor),
        on_revision_conflict=pursuits.reread(params.opportunity_id),
        shown=partial(pursuits.shown, postings=op.shares("public_posting")),
    )


@router.patch(
    f"{PREFIX}/pursuits/{{opportunity_id}}",
    response_model=Envelope[pursuits.PursuitItem],
    openapi_extra=operation_route(pursuits.PURSUITS_PATCH),
)
async def pursuit_patch(
    op: Annotated[OperationContext, Depends(admitted(pursuits.PURSUITS_PATCH))],
) -> Envelope[Any]:
    params = op.input_as(pursuits.PursuitPatchInput)
    return await op.write(
        lambda: pursuits.patch_pursuit(op.session, params, actor=op.actor),
        on_revision_conflict=pursuits.reread(params.opportunity_id),
        shown=partial(pursuits.shown, postings=op.shares("public_posting")),
    )


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


@router.post(
    f"{PREFIX}/recipes/drafts",
    response_model=Envelope[recipes.SavedDraft],
    openapi_extra=operation_route(recipes.RECIPES_DRAFT_SAVE),
)
async def recipe_draft_save(
    op: Annotated[OperationContext, Depends(admitted(recipes.RECIPES_DRAFT_SAVE))],
) -> Envelope[Any]:
    params = op.input_as(recipes.RecipeDraftSaveInput)
    return await op.write(lambda: recipes.save_draft(op.session, params))


@router.get(
    f"{PREFIX}/receipts",
    response_model=Envelope[receipts.Receipt],
    openapi_extra=operation_route(receipts.RECEIPTS_GET),
)
async def receipt_get(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(receipts.RECEIPTS_GET))],
) -> Envelope[Any]:
    params = op.input_as(receipts.ReceiptGetInput)
    descriptor = CATALOG.get(params.operation)
    if descriptor is None:
        raise OperationError(
            "unknown_operation",
            "This engine offers no operation by that name.",
            details={"operation": params.operation},
            next_actions=[NextAction(operation=CAPABILITIES.id, arguments={})],
        )
    return op.ok(
        await receipts.receipt_of(
            session, params, workspace_id=op.workspace_id, principal_id=op.principal_id,
            keyed=descriptor.idempotency == "required_key",
            withheld=[category for category in descriptor.data_classes if not op.shares(category)],
        )
    )


@router.get(
    f"{PREFIX}/opportunities",
    response_model=Envelope[search.SearchPage],
    openapi_extra=operation_route(search.OPPORTUNITIES_SEARCH),
)
async def opportunity_search(
    op: Annotated[OperationContext, Depends(admitted(search.OPPORTUNITIES_SEARCH))],
) -> Envelope[Any]:
    answer = await search.search(
        op.session, op.input_as(search.SearchInput), workspace_id=op.workspace_id,
        withheld=withheld(search.OPPORTUNITIES_SEARCH, op.switches),
    )
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


def _paged(op: OperationContext, page: Any, next_cursor: str | None, shortened: bool) -> Envelope[Any]:
    """A page of a list read; one the tier's budget ended early says so."""
    warnings = [EnvelopeNotice(
        code="page_shortened",
        message="This page stops at the tool tier's budget; next_cursor continues.",
    )] if shortened else None
    envelope = op.ok(page, warnings=warnings)
    envelope.meta.next_cursor = next_cursor
    return envelope


@router.get(
    f"{PREFIX}/offer",
    response_model=Envelope[offer.OfferRead],
    openapi_extra=operation_route(offer.OFFER_GET),
)
async def offer_get(
    op: Annotated[OperationContext, Depends(admitted(offer.OFFER_GET))],
) -> Envelope[Any]:
    return _paged(op, *await offer.offer_read(
        op.session, op.input_as(offer.OfferGetInput), workspace_id=op.workspace_id
    ))


@router.get(
    f"{PREFIX}/applications",
    response_model=Envelope[applications.ApplicationBoard],
    openapi_extra=operation_route(applications.APPLICATIONS_BOARD),
)
async def application_board(
    op: Annotated[OperationContext, Depends(admitted(applications.APPLICATIONS_BOARD))],
) -> Envelope[Any]:
    return _paged(op, *await applications.board(
        op.session, op.input_as(applications.BoardInput), workspace_id=op.workspace_id,
        postings=op.shares("public_posting"),
    ))


@router.get(
    f"{PREFIX}/applications/calendar",
    response_model=Envelope[applications.ApplicationCalendar],
    openapi_extra=operation_route(applications.APPLICATIONS_CALENDAR),
)
async def application_calendar(
    op: Annotated[OperationContext, Depends(admitted(applications.APPLICATIONS_CALENDAR))],
) -> Envelope[Any]:
    return _paged(op, *await applications.calendar(
        op.session, op.input_as(applications.CalendarInput), workspace_id=op.workspace_id
    ))


@router.get(
    f"{PREFIX}/doctor",
    response_model=Envelope[export.DoctorReport],
    openapi_extra=operation_route(export.DOCTOR),
)
async def doctor(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(export.DOCTOR))],
) -> Envelope[Any]:
    # The status the dashboard's badge reads, from its own route.
    status = await ops.status(session)
    report = export.doctor_report(
        status,
        settings=get_settings(),
        access=op.switches,
        engine_version=__version__,
        workspace=DATA_DIR,
        tier=op.input_as(export.DoctorInput).tier,
    )
    if report.continue_with:
        return op.ok(report, warnings=[EnvelopeNotice(
            code="page_shortened",
            message="The settings stop at the tool tier's budget; continue_with reads them all.",
        )])
    if report.settings_left_out:
        return op.ok(report, warnings=[EnvelopeNotice(
            code="page_shortened",
            message="Settings too long for the full tier are left out; settings_left_out names them.",
        )])
    return op.ok(report)


@router.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/context",
    response_model=Envelope[export.ContextExport],
    openapi_extra=operation_route(export.CONTEXT_EXPORT),
)
async def context_export(
    session: SessionDep,
    op: Annotated[OperationContext, Depends(admitted(export.CONTEXT_EXPORT))],
) -> Envelope[Any]:
    params = op.input_as(export.ContextExportInput)
    # Admission's read ends here, so the packet is read in a snapshot of its own.
    await end_read(session)
    await export.begin_snapshot(session)
    packet, manifest = await export.context_packet(
        session, params.opportunity_id, withheld=withheld(export.CONTEXT_EXPORT, op.switches)
    )
    export.same_packet(manifest, params)
    part = export.packet_part(
        packet, manifest, opportunity_id=params.opportunity_id, tier=params.tier, start=params.packet_from or 0
    )
    if part.continue_with:
        return op.ok(part, warnings=[EnvelopeNotice(
            code="page_shortened",
            message="The packet is longer than the tool tier's budget; continue_with reads the next part.",
        )])
    return op.ok(part)

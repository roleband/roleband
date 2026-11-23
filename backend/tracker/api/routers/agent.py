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
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from tracker import __version__
from tracker.agents.operations import (
    applications,
    changes,
    companies,
    duplicates,
    export,
    insights,
    offer,
    opportunities,
    pursuits,
    radar,
    receipts,
    recipes,
    relations,
    search,
    steps,
    vocabulary,
)
from tracker.agents.operations.catalog import CATALOG, resources
from tracker.agents.operations.envelope import Envelope, EnvelopeNotice, NextAction, OperationError
from tracker.agents.operations.index import capabilities_summary, describe_view
from tracker.agents.operations.meta import (
    CAPABILITIES,
    DESCRIBE,
    STATUS,
    AgentSwitchState,
    CapabilitiesInput,
    CapabilitiesResult,
    DescribeInput,
    EngineTrust,
    OperationSummary,
    OperationView,
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
from tracker.api.routers import ops, statistics
from tracker.api.routers import skills as skill_routes
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
    params = op.input_as(CapabilitiesInput)
    entries = [descriptor.summary_entry(availability(descriptor, op.switches)) for descriptor in CATALOG.in_tier(params.tier)]
    versions = {
        "contract_version": CONTRACT_VERSION,
        "supported_contract_versions": [CONTRACT_VERSION],
        "engine_version": __version__,
        "metadata_source": "engine",
    }
    if params.view == "full":
        listed: dict[str, Any] = {"view": "full", "operations": [OperationSummary.model_validate(entry) for entry in entries]}
    else:
        listed = capabilities_summary(entries, resources=resources(), availability_known=True, tier=params.tier)
    return op.ok(CapabilitiesResult.model_validate({**versions, **listed}))


@router.get(
    f"{PREFIX}/operations/{{operation}}",
    response_model=Envelope[OperationView],
    openapi_extra=operation_route(DESCRIBE),
)
async def describe(
    op: Annotated[OperationContext, Depends(admitted(DESCRIBE))],
) -> Envelope[Any]:
    params = op.input_as(DescribeInput)
    wanted = params.operation
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
    entry = descriptor.full_entry(availability(descriptor, op.switches), source="engine")
    return op.ok(OperationView.model_validate(describe_view(entry, params.view)))


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


# Before `/opportunities/{opportunity_id}`, which would otherwise take `get-many` for an id.
@router.get(
    f"{PREFIX}/opportunities/get-many",
    response_model=Envelope[opportunities.GetManyPage],
    openapi_extra=operation_route(opportunities.OPPORTUNITIES_GET_MANY),
)
async def opportunity_get_many(
    op: Annotated[OperationContext, Depends(admitted(opportunities.OPPORTUNITIES_GET_MANY))],
) -> Envelope[Any] | JSONResponse:
    params = op.input_as(opportunities.GetManyInput)
    answer = await opportunities.get_many(
        op.session, params, withheld=withheld(opportunities.OPPORTUNITIES_GET_MANY, op.switches),
    )
    if answer.page.not_found:
        return op.partial(
            answer.page, opportunities.missing_ids(answer.page, params.ids),
            warnings=_fitting(rows_left=answer.shortened, row_cut=answer.row_cut) or None, truncated=answer.row_cut,
        )
    return _fitted(op, answer.page, rows_left=answer.shortened, row_cut=answer.row_cut)


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
        described=pursuits.PursuitActivity(params.opportunity_id, saving=True),
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
        described=pursuits.PursuitActivity(params.opportunity_id, saving=False),
    )


@router.post(
    f"{PREFIX}/pursuits/{{opportunity_id}}/steps",
    response_model=Envelope[pursuits.PursuitItem],
    openapi_extra=operation_route(steps.STEPS_ADD),
)
async def step_add(
    op: Annotated[OperationContext, Depends(admitted(steps.STEPS_ADD))],
) -> Envelope[Any]:
    params = op.input_as(steps.StepAddInput)
    return await op.write(
        lambda: steps.add(op.session, params, actor=op.actor),
        on_revision_conflict=pursuits.reread(params.opportunity_id),
        shown=partial(pursuits.shown, postings=op.shares("public_posting")),
        described=steps.StepActivity(params.opportunity_id, "add"),
    )


async def _step_write(
    op: OperationContext, model: type[steps.StepInput], action: Literal["edit", "done", "undo"]
) -> Envelope[Any]:
    params = op.input_as(model)
    return await op.write(
        lambda: steps.change(op.session, params, actor=op.actor, action=action),
        on_revision_conflict=pursuits.reread(params.opportunity_id),
        shown=partial(pursuits.shown, postings=op.shares("public_posting")),
        described=steps.StepActivity(params.opportunity_id, action, params.step_id, steps.edited_fields(params)),
    )


@router.patch(
    f"{PREFIX}/pursuits/{{opportunity_id}}/steps/{{step_id}}",
    response_model=Envelope[pursuits.PursuitItem],
    openapi_extra=operation_route(steps.STEPS_EDIT),
)
async def step_edit(op: Annotated[OperationContext, Depends(admitted(steps.STEPS_EDIT))]) -> Envelope[Any]:
    return await _step_write(op, steps.StepEditInput, "edit")


@router.post(
    f"{PREFIX}/pursuits/{{opportunity_id}}/steps/{{step_id}}/done",
    response_model=Envelope[pursuits.PursuitItem],
    openapi_extra=operation_route(steps.STEPS_DONE),
)
async def step_done(op: Annotated[OperationContext, Depends(admitted(steps.STEPS_DONE))]) -> Envelope[Any]:
    return await _step_write(op, steps.StepInput, "done")


@router.post(
    f"{PREFIX}/pursuits/{{opportunity_id}}/steps/{{step_id}}/undo",
    response_model=Envelope[pursuits.PursuitItem],
    openapi_extra=operation_route(steps.STEPS_UNDO),
)
async def step_undo(op: Annotated[OperationContext, Depends(admitted(steps.STEPS_UNDO))]) -> Envelope[Any]:
    return await _step_write(op, steps.StepInput, "undo")


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
    return await op.write(lambda: recipes.save_draft(op.session, params), described=recipes.DraftActivity())


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
    receipt = await receipts.receipt_of(
        session, params, workspace_id=op.workspace_id, principal_id=op.principal_id,
        keyed=descriptor.idempotency == "required_key",
        withheld=[category for category in descriptor.data_classes if not op.shares(category)],
    )
    if descriptor.id == duplicates.DUPLICATES_DECIDE.id:
        result = await duplicates.visible_verdicts(
            session, duplicates.DuplicateVerdictsResult.model_validate(receipt.result),
            pursuits=op.shares("private_pursuit"),
        )
        receipt.result = result.model_dump(mode="json")
    return op.ok(receipt)


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


@router.get(
    f"{PREFIX}/changes",
    response_model=Envelope[changes.ChangesPage],
    openapi_extra=operation_route(changes.CHANGES_LIST),
)
async def change_list(
    op: Annotated[OperationContext, Depends(admitted(changes.CHANGES_LIST))],
) -> Envelope[Any]:
    answer = await changes.changes_page(
        op.session, op.input_as(changes.ChangesListInput),
        workspace_id=op.workspace_id, principal_id=op.principal_id, shared=frozenset(op.answered_classes),
    )
    warnings: list[EnvelopeNotice] = []
    if answer.shortened:
        warnings.append(EnvelopeNotice(
            code="page_shortened",
            message="This page stops before the limit to stay within the tool tier's budget; continue_with reads on.",
        ))
    return op.ok(answer.page, warnings=warnings or None)


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
    if report.settings_shortened or report.settings_left_out:
        return op.ok(report, warnings=[EnvelopeNotice(
            code="page_shortened",
            message=(
                "Settings too long for the full tier are shortened, and named in settings_shortened; "
                "any with no room at all are named in settings_left_out."
            ),
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


_ROWS_LEFT = EnvelopeNotice(
    code="page_shortened",
    message="Some postings did not fit the tool tier's budget; data.continue_with reads them.",
)
_ROW_SHORTENED = EnvelopeNotice(
    code="row_shortened",
    message="A row's text is longer than this tool tier's budget, so it is cut; opportunities.get gives it whole.",
)


def _fitting(*, rows_left: bool, row_cut: bool) -> list[EnvelopeNotice]:
    return [notice for notice, on in ((_ROWS_LEFT, rows_left), (_ROW_SHORTENED, row_cut)) if on]


def _fitted(op: OperationContext, data: Any, *, rows_left: bool, row_cut: bool) -> Envelope[Any]:
    envelope = op.ok(data, warnings=_fitting(rows_left=rows_left, row_cut=row_cut) or None)
    envelope.meta.truncated = row_cut
    return envelope


# --- Insights: each answer is the dashboard route's own, read through the operation's shape.


async def _insights(op: OperationContext, figures: insights.Figures) -> Envelope[Any]:
    answer = await insights.read(
        op.session, op.descriptor, op.input, workspace_id=op.workspace_id, figures=figures,
        withheld=withheld(op.descriptor, op.switches),
    )
    envelope = op.ok(answer.data, warnings=[EnvelopeNotice(
        code="page_shortened",
        message="This answer stops before its lists end to stay within the tool tier's budget; "
        "page.continue_with reads on.",
    )] if answer.shortened else None)
    envelope.meta.next_cursor = answer.next_cursor
    return envelope


@router.get(
    f"{PREFIX}/companies",
    response_model=Envelope[companies.CompanyPage],
    openapi_extra=operation_route(companies.COMPANIES_LIST),
)
async def company_list(
    op: Annotated[OperationContext, Depends(admitted(companies.COMPANIES_LIST))],
) -> Envelope[Any]:
    paged = await companies.company_page(
        op.session, op.input_as(companies.CompanyListInput), workspace_id=op.workspace_id,
    )
    return _paged(op, paged.data, paged.next_cursor, paged.shortened)


@router.get(
    f"{PREFIX}/companies/{{company}}",
    response_model=Envelope[companies.CompanyView],
    openapi_extra=operation_route(companies.COMPANIES_GET),
)
async def company_get(
    op: Annotated[OperationContext, Depends(admitted(companies.COMPANIES_GET))],
) -> Envelope[Any]:
    paged = await companies.company(
        op.session, op.input_as(companies.CompanyGetInput), workspace_id=op.workspace_id,
    )
    return _paged(op, paged.data, paged.next_cursor, paged.shortened)


@router.get(
    f"{PREFIX}/companies/{{company}}/facts",
    response_model=Envelope[companies.FactsPage],
    openapi_extra=operation_route(companies.COMPANIES_FACTS_LIST),
)
async def company_facts(
    op: Annotated[OperationContext, Depends(admitted(companies.COMPANIES_FACTS_LIST))],
) -> Envelope[Any]:
    paged = await companies.facts(
        op.session, op.input_as(companies.FactsListInput), workspace_id=op.workspace_id,
    )
    return _paged(op, paged.data, paged.next_cursor, paged.shortened)


@router.get(
    f"{PREFIX}/companies/{{company}}/prices",
    response_model=Envelope[companies.PricesPage],
    openapi_extra=operation_route(companies.COMPANIES_PRICES_GET),
)
async def company_prices(
    op: Annotated[OperationContext, Depends(admitted(companies.COMPANIES_PRICES_GET))],
) -> Envelope[Any]:
    paged = await companies.prices(
        op.session, op.input_as(companies.PricesInput), workspace_id=op.workspace_id,
    )
    return _paged(op, paged.data, paged.next_cursor, paged.shortened)


@router.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/similar",
    response_model=Envelope[relations.SimilarRoles],
    openapi_extra=operation_route(relations.OPPORTUNITIES_SIMILAR),
)
async def opportunity_similar(
    op: Annotated[OperationContext, Depends(admitted(relations.OPPORTUNITIES_SIMILAR))],
) -> Envelope[Any]:
    data, fitted = await relations.similar(
        op.session, op.input_as(relations.SimilarInput),
        withheld=withheld(relations.OPPORTUNITIES_SIMILAR, op.switches),
    )
    return _fitted(op, data, rows_left=bool(fitted.rest), row_cut=fitted.row_cut)


@router.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/duplicates",
    response_model=Envelope[relations.PostingDecks],
    openapi_extra=operation_route(relations.OPPORTUNITIES_DUPLICATES),
)
async def opportunity_duplicates(
    op: Annotated[OperationContext, Depends(admitted(relations.OPPORTUNITIES_DUPLICATES))],
) -> Envelope[Any]:
    data, fitted = await relations.decks(
        op.session, op.input_as(relations.RelationInput),
        withheld=withheld(relations.OPPORTUNITIES_DUPLICATES, op.switches),
    )
    return _fitted(op, data, rows_left=bool(fitted.rest), row_cut=fitted.row_cut)


@router.get(
    f"{PREFIX}/duplicates/queue",
    response_model=Envelope[duplicates.DuplicateQueue],
    openapi_extra=operation_route(duplicates.DUPLICATES_QUEUE),
)
async def duplicate_queue(
    op: Annotated[OperationContext, Depends(admitted(duplicates.DUPLICATES_QUEUE))],
) -> Envelope[Any]:
    page, next_cursor, shortened = await duplicates.queue(
        op.session, op.input_as(duplicates.DuplicateQueueInput), workspace_id=op.workspace_id,
        withheld=withheld(duplicates.DUPLICATES_QUEUE, op.switches),
    )
    return _paged(op, page, next_cursor, shortened)


@router.post(
    f"{PREFIX}/duplicates/verdicts",
    response_model=Envelope[duplicates.DuplicateVerdictsResult],
    openapi_extra=operation_route(duplicates.DUPLICATES_DECIDE),
)
async def duplicate_decide(
    op: Annotated[OperationContext, Depends(admitted(duplicates.DUPLICATES_DECIDE))],
) -> Envelope[Any]:
    params = op.input_as(duplicates.DuplicateVerdictsInput)
    decided = withheld(duplicates.DUPLICATES_DECIDE, op.switches)
    return await op.write(
        lambda: duplicates.decide(op.session, params, withheld=decided),
        on_replay=lambda result: duplicates.visible_verdicts(
            op.session, result, pursuits=op.shares("private_pursuit"),
        ),
        described=duplicates.DuplicateVerdictsActivity(),
    )


@router.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/reality",
    response_model=Envelope[relations.PostingVerdict],
    openapi_extra=operation_route(relations.OPPORTUNITIES_REALITY),
)
async def opportunity_reality(
    op: Annotated[OperationContext, Depends(admitted(relations.OPPORTUNITIES_REALITY))],
) -> Envelope[Any]:
    wanted = op.input_as(relations.RelationInput).opportunity_id
    return op.ok(await relations.reality(op.session, wanted, pursuits=op.shares("private_pursuit")))


@router.get(
    f"{PREFIX}/insights/overview",
    response_model=Envelope[insights.InsightsOverview],
    openapi_extra=operation_route(insights.INSIGHTS_OVERVIEW),
)
async def insights_overview(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_OVERVIEW))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_overview(
        session=session, hidden=hidden, scope=scope, days=params.days,
    ))


@router.get(
    f"{PREFIX}/insights/compensation",
    response_model=Envelope[insights.InsightsCompensation],
    openapi_extra=operation_route(insights.INSIGHTS_COMPENSATION),
)
async def insights_compensation(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_COMPENSATION))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_compensation(
        session=session, hidden=hidden, narrowed=scope,
    ))


@router.get(
    f"{PREFIX}/insights/pay-table",
    response_model=Envelope[insights.InsightsPayTable],
    openapi_extra=operation_route(insights.INSIGHTS_PAY_TABLE),
)
async def insights_pay_table(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_PAY_TABLE))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_pay_table(
        session=session, hidden=hidden, narrowed=scope, country=params.country, level=params.level,
        skill=params.skill,
    ))


@router.get(
    f"{PREFIX}/insights/trajectory",
    response_model=Envelope[insights.InsightsTrajectory],
    openapi_extra=operation_route(insights.INSIGHTS_TRAJECTORY),
)
async def insights_trajectory(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_TRAJECTORY))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_comp_trajectory(
        session=session, hidden=hidden,
    ))


@router.get(
    f"{PREFIX}/insights/offer-terms",
    response_model=Envelope[insights.InsightsOfferTerms],
    openapi_extra=operation_route(insights.INSIGHTS_OFFER_TERMS),
)
async def insights_offer_terms(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_OFFER_TERMS))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_offer_terms(
        session=session,
    ))


@router.get(
    f"{PREFIX}/insights/levels",
    response_model=Envelope[insights.InsightsLevels],
    openapi_extra=operation_route(insights.INSIGHTS_LEVELS),
)
async def insights_levels(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_LEVELS))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_levels())


@router.get(
    f"{PREFIX}/insights/pay-trends",
    response_model=Envelope[insights.InsightsPayTrends],
    openapi_extra=operation_route(insights.INSIGHTS_PAY_TRENDS),
)
async def insights_pay_trends(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_PAY_TRENDS))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_comp_trends(
        session=session, hidden=hidden, scope=scope, dim=params.dim, days=params.days
    ))


@router.get(
    f"{PREFIX}/insights/disclosure-trends",
    response_model=Envelope[insights.InsightsDisclosureTrends],
    openapi_extra=operation_route(insights.INSIGHTS_DISCLOSURE_TRENDS),
)
async def insights_disclosure_trends(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_DISCLOSURE_TRENDS))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_disclosure_trends(
        session=session, hidden=hidden, scope=scope, dim=params.dim, days=params.days
    ))


@router.get(
    f"{PREFIX}/insights/velocity",
    response_model=Envelope[insights.InsightsVelocity],
    openapi_extra=operation_route(insights.INSIGHTS_VELOCITY),
)
async def insights_velocity(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_VELOCITY))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_velocity(
        session=session, hidden=hidden, scope=scope, days=params.days,
    ))


@router.get(
    f"{PREFIX}/insights/history",
    response_model=Envelope[insights.InsightsHistory],
    openapi_extra=operation_route(insights.INSIGHTS_HISTORY),
)
async def insights_history(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_HISTORY))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.statistics_history(
        session=session, hidden=hidden, scope=scope,
    ))


@router.get(
    f"{PREFIX}/insights/demand",
    response_model=Envelope[insights.InsightsDemand],
    openapi_extra=operation_route(insights.INSIGHTS_DEMAND),
)
async def insights_demand(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_DEMAND))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: statistics.demand(
        session=session, hidden=hidden, scope=scope,
    ))


@router.get(
    f"{PREFIX}/insights/skills",
    response_model=Envelope[insights.InsightsSkills],
    openapi_extra=operation_route(insights.INSIGHTS_SKILLS),
)
async def insights_skills(
    op: Annotated[OperationContext, Depends(admitted(insights.INSIGHTS_SKILLS))],
) -> Envelope[Any]:
    return await _insights(op, lambda session, hidden, scope, params: skill_routes.skills_top(
        session=session, hidden=hidden, scope=scope, company=params.company or None,
        family=params.family or None, location_group=params.location or None, limit=params.limit,
    ))

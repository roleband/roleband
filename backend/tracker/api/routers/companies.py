"""Tracked companies (built-in + user-added) and resolved Company Profiles.

What every route here answers with is declared in `api/schemas/companies.py`:
the tracked-company routes, the company-profile routes and the company card.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from tracker.api import job_requests, scan_requests
from tracker.api.company_errors import company_error
from tracker.api.deps import OffBoardDep, SessionDep, end_read
from tracker.api.errors import ErrorCode, api_error
from tracker.api.schemas.companies import (
    BoardSearchResponse,
    CompanyCardResponse,
    CompanyClaimsResponse,
    CompanyDirectorySearchResponse,
    CompanyDirectoryStatus,
    CompanyDiscoveryResponse,
    CompanyListResponse,
    CompanyNamesResponse,
    CompanyOpenCountsResponse,
    CompanyPricesResponse,
    CompanyProfileDetailResponse,
    CompanyProfileFieldWrite,
    CompanyProfileListResponse,
    TrackedCompanyRow,
)
from tracker.api.schemas.text_class import text as text_class
from tracker.ats_detect import DetectedBoard
from tracker.board_relocate import check_address, find_moved_board
from tracker.board_resolve import board_answers, resolve_pasted_board
from tracker.company_directory import directory_company, directory_size, search_directory
from tracker.company_discovery import (
    COMPANY_DISCOVERY,
    build_company_discovery,
    company_direction,
)
from tracker.company_store import (
    CONSENT_TEXT_MAX,
    CompanyError,
    add_company,
    ensure_builtins,
    get_tracked_companies,
    is_builtin,
    off_board_company_slugs,
    record_board_move,
    record_consent,
    require_consent_to_follow,
    resolve_company,
    set_enabled,
    set_scan_on_schedule,
    set_visible,
    unfollowed_company_slugs,
)
from tracker.config import get_settings
from tracker.connectors import ADAPTER_REGISTRY
from tracker.db.models import (
    CompanyProfile,
    TrackedCompany,
)
from tracker.db.queries.companies import (
    display_names,
    last_read_titles,
    open_counts_by_company,
)
from tracker.notifications.coverage import generate_coverage_notifications
from tracker.platform.language_tags import LOCALE_TAG, is_locale_tag
from tracker.platform.safe_fetch import public_client
from tracker.profiles import prices as price_store
from tracker.profiles import read as profile_read
from tracker.profiles import store as profile_store
from tracker.profiles.seed import ensure_company_profile
from tracker.schema import BoardRegion
from tracker.scope.catalog import company_count_state
from tracker.source_policy import collection_access
from tracker.workflows.directory_sweep import directory_status, set_follow
from tracker.workflows.scheduler import queue_followed_reads

router = APIRouter()


class AgreementPayload(BaseModel):
    """The user's answer to a follow dialog: a walled company's consent, or a
    user-directed company's agreement and its "keep scanning" choice."""

    #: The dialog may contain pinned English within the selected language.
    locale: str = Field(default="en", pattern=LOCALE_TAG, max_length=35, json_schema_extra=text_class("code"))
    #: The dialog text the user confirmed, verbatim, so the record says what
    #: they agreed to rather than that they clicked something.
    text: str = Field(json_schema_extra=text_class("record"), min_length=1, max_length=CONSENT_TEXT_MAX)
    #: "Keep scanning": a user-directed company is then scanned on the regular
    #: schedule, not only when the user asks. Must stay true for a company that
    #: is only walled, which is scanned on schedule once consented.
    scan_on_schedule: bool = True

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str) -> str:
        if not is_locale_tag(value):
            raise ValueError("invalid consent locale")
        return value


class AddCompanyPayload(BaseModel):
    catalog_slug: str | None = None
    name: str | None = Field(None, json_schema_extra=text_class("content"))
    careers_url: str | None = None
    #: The answer to the follow dialog, for a company that needs one. Without
    #: it, such a company is refused with `consent-required`, whose `kind`
    #: (`walled` or `directed`) names the dialog to show before the retry.
    consent: AgreementPayload | None = None


class FindBoardPayload(BaseModel):
    #: An address the person gives. Absent: search from what RoleBand knows.
    careers_url: str | None = Field(default=None, max_length=2048)


class MoveBoardPayload(BaseModel):
    """A board `POST .../board/find` answered with; verified again on write."""

    adapter: str = Field(min_length=1, max_length=64)
    board_token: str = Field(min_length=1, max_length=512)
    board_region: BoardRegion | None = None


class EnabledPayload(BaseModel):
    # All optional so the switches can be toggled independently.
    enabled: bool | None = None
    visible: bool | None = None
    #: A user-directed company's "keep scanning" choice; refused for any other
    #: company and for one its user has not agreed to follow.
    scan_on_schedule: bool | None = None




class CompanyConsent(AgreementPayload):
    """The user's answer to one company's follow dialog, in a selection."""

    slug: str


class DirectoryFollowPayload(BaseModel):
    """Follow or unfollow every other company RoleBand can scan, as one decision."""

    following: bool


class CompanySelectionPayload(BaseModel):
    #: The companies the person switched on and off, and only those. The roster
    #: changes under the screen (the wider-market scan follows companies by
    #: itself), so a write that restated the whole roster would undo those.
    follow: list[str] = []
    unfollow: list[str] = []
    #: Agreements given in the dialog that produced this selection: one per
    #: walled or user-directed company the dialog covered. Starting to follow
    #: such a company without one (or a stored one) is refused.
    consents: list[CompanyConsent] = []


def _company_out(row: TrackedCompany, job_count: int) -> dict:
    return {
        "slug": row.slug,
        "display": row.display,
        "adapter": row.adapter,
        "board_token": row.board_token,
        "careers_url": row.careers_url,
        "status": row.status,
        "enabled": row.enabled,
        "visible": row.visible,
        "source": row.source,
        "builtin": is_builtin(row.slug),  # blocks deletion; every company is a row
        "job_count": job_count,
        "role_catalog_status": row.role_catalog_status,
        "role_catalog_scanned_at": row.role_catalog_scanned_at,
        "role_catalog_error": row.role_catalog_error,
        "detected_family": row.detected_family if row.status == "pending" else None,
        "pending_reason": row.pending_reason if row.status == "pending" else None,
    }


@router.get("/api/companies", response_model=CompanyListResponse)
async def list_companies(session: SessionDep) -> dict:
    """Every tracked company (built-in + user-added) with its tracking + visibility
    switches. Built-ins are ordinary rows (seeded at startup) flagged `builtin` so the
    UI hides Remove.

    A pure read, for the reason `/api/companies/discovery` gives below: startup,
    the pipeline and every mutating company route already reconcile built-ins,
    and a GET must not commit (`tests/test_api_get_is_read_only.py`)."""
    counts = await open_counts_by_company(session)
    return {
        "companies": [
            _company_out(row, counts.get(row.slug, 0))
            for row in await get_tracked_companies(session)
        ]
    }


@router.get("/api/companies/directory", response_model=CompanyDirectorySearchResponse)
async def companies_directory(session: SessionDep, q: str = Query("", max_length=64)) -> dict:
    """Search every other company RoleBand can scan, by name.

    Server-side because the set is thousands of companies: the register
    asks for the few that match what the user typed, never for the list.
    """
    hits, total = search_directory(q)
    tracked = {row.slug: row for row in await get_tracked_companies(session)}
    return {
        "size": directory_size(),
        "match_count": total,
        "matches": [
            {
                "slug": hit.slug,
                "display": hit.display,
                "named_by": hit.named_by,
                "tracked": hit.slug in tracked,
                "enabled": bool(hit.slug in tracked and tracked[hit.slug].enabled),
            }
            for hit in hits
        ],
    }


@router.get("/api/companies/directory/status", response_model=CompanyDirectoryStatus)
async def companies_directory_status(session: SessionDep) -> dict:
    """The whole set as the register draws it: its size, whether it is followed,
    and how far the background scan has read it. A pure read."""
    return await directory_status(session)


@router.put("/api/companies/directory/follow", response_model=CompanyDirectoryStatus)
async def follow_companies_directory(payload: DirectoryFollowPayload, session: SessionDep) -> dict:
    """Follow every other company RoleBand can scan, or stop.

    Following starts the background scan (`workflows.directory_sweep`), which
    follows each company it finds roles at. Stopping switches off exactly the
    companies the set brought in and remembers them, so following again brings
    back the same ones; a company followed by name is never touched.
    """
    await set_follow(session, payload.following, datetime.now(UTC))
    await session.commit()
    if payload.following:
        # Read now, not at the next look up to ten minutes away.
        await job_requests.ring_directory(session, requested_by="follow")
        await session.commit()
    return await directory_status(session)


@router.get("/api/companies/discovery", response_model=CompanyDiscoveryResponse)
async def companies_discovery(session: SessionDep) -> dict:
    """Job-seeker sectors merged with the user's current tracking state.

    The Company Explorer's first paint depends on this and nothing else, so it
    is a pure read: no `ensure_builtins()` upsert+commit (startup, the pipeline,
    and every mutating company route already reconcile built-ins — a GET that
    writes can queue behind a running scrape's row locks and hold the whole
    screen blank), and no `jobs` aggregate. Open-role counts arrive separately
    via `/api/companies/open-counts`.
    """
    tracked = {row.slug: row for row in await get_tracked_companies(session)}
    return build_company_discovery(tracked=tracked)


@router.get("/api/companies/open-counts", response_model=CompanyOpenCountsResponse)
async def companies_open_counts(session: SessionDep) -> dict:
    """Open in-scope role count per company slug.

    Split out of `/api/companies/discovery` so the roster renders immediately
    and each row fills its count in place. Companies with no open in-scope role
    are absent; the caller reads a missing slug as 0.

    Beside it, per followed company, what the Profile's count leaves out and
    how many of its roles no answer can keep, by reason, so each status
    shows where the company is.
    """
    state = await company_count_state(session, await off_board_company_slugs(session))
    return {
        "counts": await open_counts_by_company(session),
        "not_counted": state.not_counted,
        "unplaced": state.unplaced,
        "unsorted": state.unsorted,
        "last_read": state.last_read,
    }


@router.get("/api/companies/names", response_model=CompanyNamesResponse)
async def companies_names(session: SessionDep) -> dict:
    """Each company's name by slug: every catalog company, and every tracked
    one, whose stored name wins. The dashboard reads it once, before its first
    render, so every screen names a company the way the company does ("PwC",
    "CrowdStrike") rather than by its slug, including the level table's
    reference companies on an install that follows none of them. The
    directory's thousands of other companies are not in it."""
    names = {slug: company.display for slug, company in COMPANY_DISCOVERY.items()}
    names.update(await display_names(session))
    return {"names": names}


@router.put("/api/companies/selection", response_model=CompanyDiscoveryResponse)
async def update_company_selection(
    payload: CompanySelectionPayload,
    session: SessionDep,
) -> dict:
    """Atomically follow and unfollow the companies the person switched.

    A company the change does not name keeps its state. Missing discovery
    companies are registered first. Sources without an implemented adapter
    remain ``pending`` and therefore cannot be scraped yet; the selection
    records intent without overstating connector readiness. Unfollowed rows are
    paused rather than deleted, preserving their history.
    """
    await ensure_builtins(session)
    rows = await get_tracked_companies(session)
    tracked = {row.slug: row for row in rows}
    desired = set(payload.follow)
    dropped = set(payload.unfollow)
    if both := desired & dropped:
        raise api_error(400, ErrorCode.INVALID_INPUT,
                        f"followed and unfollowed at once: {', '.join(sorted(both))}")
    unknown = {
        slug for slug in desired - set(COMPANY_DISCOVERY) - set(tracked)
        if directory_company(slug) is None
    }
    if unknown:
        raise api_error(400, ErrorCode.INVALID_INPUT, f"unknown companies: {', '.join(sorted(unknown))}")

    # Validate every new entry before mutating the roster so a parked source
    # cannot leave a partially applied selection.
    fields_to_add: list[dict] = []
    for slug in sorted(desired - set(tracked)):
        try:
            fields_to_add.append(resolve_company(catalog_slug=slug))
        except CompanyError as exc:
            raise company_error(exc) from exc

    added: list[TrackedCompany] = []
    try:
        for fields in fields_to_add:
            row = await add_company(session, fields)
            tracked[row.slug] = row
            added.append(row)
        # Agreements first, then the transitions they unlock, all before the
        # commit, so a refused follow leaves nothing half-applied. A row this
        # request created starts out followed, so it is checked like a
        # transition: it is one.
        for consent in payload.consents:
            if consent.slug not in desired or consent.slug not in tracked:
                raise CompanyError(f"consent for '{consent.slug}', which this selection does not follow")
            record_consent(
                tracked[consent.slug], consent.text, locale=consent.locale,
                scan_on_schedule=consent.scan_on_schedule,
            )
        created = {row.slug for row in added}
        followed_now: list[str] = []
        for slug in sorted(desired):
            row = tracked[slug]
            if not row.enabled or slug in created:
                require_consent_to_follow(row)
            if not row.enabled:
                followed_now.append(slug)
            row.enabled = True
        for slug in dropped & set(tracked):
            tracked[slug].enabled = False
        for row in added:
            await ensure_company_profile(session, row.slug, row.display)
        await session.commit()
    except CompanyError as exc:
        await session.rollback()
        raise company_error(exc) from exc

    scrapeable = [row.slug for row in added if row.status == "active" and row.adapter]
    if scrapeable:
        await job_requests.ring_role_discovery(session, scrapeable, max_list=150, requested_by="add_company")
        await session.commit()
    started = [*added, *(tracked[slug] for slug in followed_now if slug in tracked)]
    agreed = [tracked[consent.slug] for consent in payload.consents]
    waiting = await _queue_directed_reads(session, [*started, *agreed])
    await _start_first_scans(session, started or agreed)

    tracked = {row.slug: row for row in await get_tracked_companies(session)}
    return {**build_company_discovery(tracked=tracked), "reads_waiting": waiting}


async def _queue_directed_reads(session, rows: list[TrackedCompany]) -> list[str]:
    """Queue the read the follow dialog's "Follow and scan" asked for, for each
    user-directed company among `rows`; the companies whose read could not be
    queued (their provider is paused or denied) are returned, so the screen can
    say the read waits. Every other company joins the first-scan drain on its
    own. Commits."""
    directed = list(dict.fromkeys(
        row.slug for row in rows
        if row.enabled and row.status == "active" and row.adapter and company_direction(row.slug, row)
    ))
    if not directed:
        return []
    queued = set(await queue_followed_reads(session, directed))
    return [slug for slug in directed if slug not in queued]


async def _start_first_scans(session, followed: list[TrackedCompany]) -> None:
    """Ask for a scan now for companies the user just followed.

    A company never scanned is due at once and joins one drain run;
    without this it waits for the next 600s tick. The dispatcher decides what
    is collectable (a user-directed company joins only through the read its
    dialog queued, `_queue_directed_reads`), so this only moves WHEN it looks. A request, so it joins one already
    queued and waits for a scan in flight, whose tick or the next picks the
    companies up. Commits.
    """
    if any(row.status == "active" and row.adapter for row in followed):
        await scan_requests.ring(session, requested_by=scan_requests.FIRST_SCAN)
        await session.commit()


@router.post("/api/companies", status_code=201, response_model=TrackedCompanyRow)
async def create_company(payload: AddCompanyPayload, session: SessionDep) -> dict:
    """Add a company from the catalog, or by careers URL (auto-detect ATS).

    URLs that aren't a board `detect_ats` collects are stored `pending`
    — visible in Settings but skipped by the pipeline until an adapter exists.

    A company is added followed, so a walled or user-directed one needs the
    answer to its follow dialog (`consent`): without it nothing is added and
    the refusal (`consent-required`) names the dialog, for a retry with it.
    """
    try:
        fields = resolve_company(
            name=payload.name,
            careers_url=payload.careers_url,
            catalog_slug=payload.catalog_slug,
        )
        # A URL no pattern names may still be a board its page names.
        fields = await resolve_pasted_board(fields)
        row = await add_company(session, fields)
        if payload.consent is not None:
            record_consent(
                row, payload.consent.text, locale=payload.consent.locale,
                scan_on_schedule=payload.consent.scan_on_schedule,
            )
        require_consent_to_follow(row)
        await session.commit()
        # A tracked company must be a /company profile from the moment it exists.
        await ensure_company_profile(session, row.slug, row.display)
        await session.commit()
    except CompanyError as exc:
        await session.rollback()
        raise company_error(exc) from exc
    await _queue_directed_reads(session, [row])
    await _start_first_scans(session, [row])
    if row.status == "active" and row.adapter:
        # Best-effort bootstrap, skipped when a discovery is already queued or
        # running. Safe to skip: the row is created
        # `role_catalog_status="pending"` and the next pipeline run refreshes
        # the catalog as it scans — the same reason discovery may abandon its
        # remaining companies when it yields the lock to a scrape.
        await job_requests.ring_role_discovery(session, [row.slug], max_list=150, requested_by="add_company")
        await session.commit()
    return _company_out(row, 0)


@router.patch("/api/companies/{slug}", response_model=TrackedCompanyRow)
async def update_company(slug: str, payload: EnabledPayload, session: SessionDep) -> dict:
    """Toggle a company's tracking (`enabled`), visibility (`visible`) and, for a
    user-directed company, whether it is scanned on the regular schedule
    (`scan_on_schedule`).

    Each field is optional and applied independently. Built-in and user-added
    companies are identical rows here — one code path, no special case.
    Turning `scan_on_schedule` on also queues a read, so the company joins the
    schedule read, not already stale.
    """
    if payload.enabled is None and payload.visible is None and payload.scan_on_schedule is None:
        raise api_error(
            400, ErrorCode.INVALID_INPUT, "provide 'enabled', 'visible' and/or 'scan_on_schedule'"
        )

    # A built-in may not have been seeded yet on a brand-new DB (e.g. before the
    # first startup ran); ensure its row exists so the toggle always has a target.
    if is_builtin(slug):
        await ensure_builtins(session)

    try:
        if payload.enabled is not None:
            row = await set_enabled(session, slug, payload.enabled)
        if payload.visible is not None:
            row = await set_visible(session, slug, payload.visible)
        if payload.scan_on_schedule is not None:
            row = await set_scan_on_schedule(session, slug, payload.scan_on_schedule)
        await session.commit()
        if payload.enabled is False:
            # An unfollowed company costs nobody coverage: its Coverage row
            # goes now, not at the next scan (the notice's own
            # "stop following" answer).
            await generate_coverage_notifications(session)
            await session.commit()
    except CompanyError as exc:
        await session.rollback()
        raise company_error(exc) from exc
    if payload.scan_on_schedule:
        await _queue_directed_reads(session, [row])
        await _start_first_scans(session, [row])
    counts = await open_counts_by_company(session)
    return _company_out(row, counts.get(slug, 0))


@router.post("/api/companies/{slug}/board/find", response_model=BoardSearchResponse)
async def find_company_board(slug: str, payload: FindBoardPayload, session: SessionDep) -> dict:
    """Where a company's careers page moved, verified, or null.

    With `careers_url`: the board behind the address the person gave. Without:
    the company's own careers page, then its name on the families keyed by a
    name, a guess counting only if its roles overlap what RoleBand last read
    there (`board_relocate`). Reads only; `PUT .../board` writes the move.
    """
    row = await session.get(TrackedCompany, slug)
    if row is None:
        raise api_error(404, ErrorCode.COMPANY_NOT_FOUND, f"'{slug}' is not a tracked company", slug=slug)
    known = await last_read_titles(session, slug)
    await end_read(session)
    async with public_client(user_agent=get_settings().scraper_user_agent) as client:
        if payload.careers_url:
            found = await check_address(
                payload.careers_url.strip(), slug=slug, adapter=row.adapter,
                board_token=row.board_token, known=known, client=client,
            )
        else:
            found = await find_moved_board(
                slug=slug, display=row.display or slug, adapter=row.adapter,
                board_token=row.board_token, careers_url=row.careers_url, known=known, client=client,
            )
    return {"candidate": asdict(found) if found is not None else None}


@router.put("/api/companies/{slug}/board", response_model=TrackedCompanyRow)
async def move_company_board(slug: str, payload: MoveBoardPayload, session: SessionDep) -> dict:
    """Point a company at the careers page it moved to.

    The board is verified again here, never trusted from the request: it must
    be one policy lets RoleBand read and it must answer on its family's own
    route (`board_answers`). The move retires the old binding and withholds
    closure from the new one (`company_store.record_board_move`); the
    company's Coverage notice is reconciled away and its first scan starts.
    """
    if payload.adapter not in ADAPTER_REGISTRY:
        raise api_error(400, ErrorCode.INVALID_INPUT, f"unknown adapter {payload.adapter!r}")
    if collection_access(payload.adapter, company=slug).denied:
        raise api_error(409, ErrorCode.CAREERS_PAGE_REFUSED, "RoleBand may not read that careers page")
    board = DetectedBoard(payload.adapter, payload.board_token, payload.board_region)
    async with public_client(user_agent=get_settings().scraper_user_agent) as client:
        if not await board_answers(board, client):
            raise api_error(409, ErrorCode.CAREERS_PAGE_UNREACHABLE, "That careers page isn't answering")
    try:
        await record_board_move(
            session, slug, adapter=payload.adapter, board_token=payload.board_token,
            board_region=payload.board_region.value if payload.board_region else None,
        )
        moved = await session.get(TrackedCompany, slug)
        if moved is not None and moved.enabled:
            # A followed company moved onto a user-directed source is followed
            # there only with its user's agreement, as a new follow would be.
            require_consent_to_follow(moved)
        await session.commit()
    except CompanyError as exc:
        await session.rollback()
        raise company_error(exc) from exc
    await generate_coverage_notifications(session)
    await session.commit()
    row = await session.get(TrackedCompany, slug)
    assert row is not None
    await _start_first_scans(session, [row])
    counts = await open_counts_by_company(session)
    return _company_out(row, counts.get(slug, 0))


# --- Company Profiles -------------------------------------------------------
# Values are RESOLVED from multi-source claims (profiles/resolve.py), so every
# field ships with its provenance: which source won, how fresh it is, and which
# other sources disagree. The UI renders that, rather than pretending we have a
# single authoritative feed.


@router.get("/api/company-profiles", response_model=CompanyProfileListResponse)
async def company_profiles_list(session: SessionDep, hidden: OffBoardDep) -> dict:
    """All company profiles + their data-health badge (the triage list)."""
    return await profile_read.profile_list(session, hidden)



@router.get("/api/company-profiles/{slug}", response_model=CompanyProfileDetailResponse)
async def company_profile(slug: str, session: SessionDep, hidden: OffBoardDep) -> dict:
    """One company: resolved identity w/ provenance, comp baseline, benefits."""
    found = await profile_read.profile_detail(session, slug, hidden)
    if found is None:
        raise api_error(404, ErrorCode.COMPANY_PROFILE_NOT_FOUND, "company profile not found")
    return found



class ProfileFieldUpdate(BaseModel):
    field: str
    value: object | None = None


@router.patch("/api/company-profiles/{slug}", response_model=CompanyProfileFieldWrite)
async def company_profile_set_manual(
    slug: str, body: ProfileFieldUpdate, session: SessionDep
) -> dict:
    """Pin a human value for one field. Outranks every source, now and on refresh."""
    if body.field not in profile_store.PROFILE_FIELDS:
        raise api_error(400, ErrorCode.INVALID_INPUT, f"unknown field: {body.field}")
    if await session.get(CompanyProfile, slug) is None:
        raise api_error(404, ErrorCode.COMPANY_PROFILE_NOT_FOUND, "company profile not found")
    try:
        health = await profile_store.set_manual(session, slug, body.field, body.value)
    except profile_store.AnsweredByPlugin as refused:
        raise api_error(409, ErrorCode.FIELD_ANSWERED_BY_PLUGIN, str(refused)) from None
    return {"slug": slug, "field": body.field, "health": health}


@router.delete(
    "/api/company-profiles/{slug}/manual/{field}", response_model=CompanyProfileFieldWrite
)
async def company_profile_clear_manual(
    slug: str, field: str, session: SessionDep
) -> dict:
    """Un-pin a field and fall back to source resolution."""
    if field not in profile_store.PROFILE_FIELDS:
        raise api_error(400, ErrorCode.INVALID_INPUT, f"unknown field: {field}")
    if await session.get(CompanyProfile, slug) is None:
        raise api_error(404, ErrorCode.COMPANY_PROFILE_NOT_FOUND, "company profile not found")
    health = await profile_store.clear_manual(session, slug, field)
    return {"slug": slug, "field": field, "health": health}


@router.get("/api/company-profiles/{slug}/claims", response_model=CompanyClaimsResponse)
async def company_claims(slug: str, session: SessionDep) -> dict:
    """Raw evidence: every claim every source has made. The audit trail behind a
    conflict badge — "what did we believe, when, and on whose word?"."""
    return {"slug": slug, "claims": await profile_read.profile_claims(session, slug)}


@router.get("/api/company-profiles/{slug}/prices", response_model=CompanyPricesResponse)
async def company_prices(
    slug: str, session: SessionDep, range: str = Query(profile_read.DEFAULT_PRICE_RANGE)
) -> dict:
    """Daily OHLC bars for one company's sparkline (`profiles.read.profile_prices`)."""
    if await session.get(CompanyProfile, slug) is None:
        raise api_error(404, ErrorCode.COMPANY_PROFILE_NOT_FOUND, "company profile not found")
    return await profile_read.profile_prices(session, slug, range, settings=get_settings())


@router.get("/api/companies/{slug}/card", response_model=CompanyCardResponse)
async def company_card(slug: str, session: SessionDep, hidden: OffBoardDep) -> dict:
    """Compact hover-card payload for a company chip on a job row: identity, latest
    price, and open-role count. Falls back to the raw slug when no profile exists so
    the card still renders (and still deep-links to the board)."""
    profile = await session.get(CompanyProfile, slug)
    open_roles = await profile_read.board_count(session, slug, hidden)
    price = (await price_store.latest_price_map(session, [slug])).get(slug)
    top_cities = [loc["city"] for loc in (await profile_read.company_locations(session, slug))[:3]]
    return {
        "slug": slug,
        "display_name": profile.display_name if profile else slug.replace("-", " ").title(),
        "logo_url": profile.logo_url if profile else None,
        "brand_color": profile.brand_color if profile else None,
        "ticker": profile.ticker if profile else None,
        "is_public": bool(profile.is_public) if profile else False,
        "has_profile": profile is not None,
        "open_roles": open_roles,
        "unfollowed": slug in await unfollowed_company_slugs(session),
        "top_cities": top_cities,
        "price": price["price"] if price else None,
        "change_pct": price["change_pct"] if price else None,
        "currency": price["currency"] if price else None,
        "price_as_of": price["as_of"] if price else None,
    }

"""The companies the person follows, as the Companies screen shows them.

`companies.list` is the screen's roster (`profiles.read.profile_list`): every
company profile off no Board, filtered as the screen filters it, by a name,
slug or ticker and by the review switch, and by sector and whether the level
atlas researched it, as the roster groups it. Rows run A to Z by name, as the
roster draws them, and page with a cursor.

`companies.get` is one company's profile (`profiles.read.profile_detail`) in
one of three views. `profile` holds its facts, the review worklist, pay, the
latest price and its busiest places; `benefits` and `locations` page through
those lists whole. Every fact names its source and that source's basis: the
employer or a filing states it, reports weighed together estimate it, it is
RoleBand's dataset, a seed or an inference, the person pinned it, or a plugin
answers it. An offer fact says whether the employer states it or it is
estimated, as the profile does.

`companies.facts.list` is every claim every source made about the company,
the evidence behind a conflict (`profiles.read.profile_claims`), and
`companies.prices.get` its daily price bars (`profiles.read.profile_prices`).

A company the person hid is not found here, as a posting there is not found
in `opportunities.get`. Unlike the screen, an unknown company is `not_found`
rather than an empty answer, so a misspelt slug is told apart from a company
with no claims or prices.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import Field, RootModel
from pydantic.config import JsonDict
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations import cursor
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape, ToolTier
from tracker.agents.operations.envelope import OperationError
from tracker.agents.operations.search import PAGE_BUDGET_BYTES
from tracker.company_discovery import SECTORS
from tracker.company_store import off_board_company_slugs
from tracker.config import get_settings
from tracker.db.models import CompanyProfile, TrackedCompany
from tracker.db.queries.companies import open_counts_by_company
from tracker.profiles import prices as price_store
from tracker.profiles import read as profile_read
from tracker.profiles.sources import SOURCES

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")
_ROWS = "One array per row, its values in the order `columns` names."

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
#: The most a company's profile view may take, by tool tier, in UTF-8 bytes of
#: its JSON: the budget of a single posting's detail view.
PROFILE_BUDGET_BYTES: dict[ToolTier, int] = {"small": 15_000, "standard": 40_000, "full": 40_000}
#: The places a profile view names: the busiest, by open roles.
PROFILE_PLACES = 10
#: The fields a cursor does not bind: a later page may change its size or tier.
_PAGING = frozenset({"cursor", "limit", "tier"})

_Slug = Annotated[str, Field(min_length=1, max_length=200)]
#: A fact's value, as the profile stores it: a flag, a number or text.
FactValue = str | int | float | bool | None
Basis = Literal["official", "estimated", "dataset", "seed", "inferred", "human", "plugin"]


def basis_of(source: str | None) -> Basis | None:
    """The kind of source a claim comes from (`profiles.sources`); a source
    RoleBand does not rank itself is a plugin's."""
    if source is None:
        return None
    known = SOURCES.get(source)
    return known.kind if known is not None else "plugin"  # type: ignore[return-value]


# --- companies.list ---------------------------------------------------------- #


class CompanyListInput(Shape):
    query: str | None = Field(
        default=None, min_length=1, max_length=200,
        description="Words a company's name, slug or ticker contains, as the Companies search box matches.",
    )
    sector: list[_Slug] = Field(
        default_factory=list, max_length=20, description="Sectors, by slug; repeat for more. Any one matches.",
    )
    researched: bool | None = Field(
        default=None, description="Only companies the level atlas researched (true), or only the others (false).",
    )
    needs_review: bool = Field(default=False, description="Only companies whose facts need a person's review.")
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Most rows on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page, read with the same filters.",
    )
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")


#: Each position of a row, in order.
COMPANY_COLUMNS: tuple[str, ...] = (
    "slug", "name", "ticker", "public", "sectors", "researched", "health", "headcount", "levels", "open_roles",
    "price", "change_pct", "currency", "price_as_of",
)

#: One company, positioned as `COMPANY_COLUMNS` names: its slug and name; its
#: ticker and whether it is listed; its sectors; whether the level atlas
#: researched it; its data health (`ok`, or what needs review); headcount;
#: how many levels of its pay ladder RoleBand holds; its open roles on the
#: Board; and its latest share price, the day's change in percent, the
#: currency and the market date of that price.
CompanyRow = tuple[
    str, str, str | None, bool | None, list[str], bool, str | None, int | None, int, int,
    float | None, float | None, str | None, date | None,
]


class CompanyPage(Shape):
    #: Companies matching on every page together.
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    #: Every sector a company can be filed under, in the screen's order.
    sectors: list[str] = Field(json_schema_extra=_CODE)
    columns: list[str] = Field(json_schema_extra=_CODE)
    rows: list[CompanyRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)


COMPANIES_LIST = OperationDescriptor(
    id="companies.list",
    summary="The companies the person follows, filtered as the Companies screen filters them; one page of rows.",
    input=CompanyListInput,
    result=CompanyPage,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("market_statistic",),
    examples=({"sector": ["fintech"], "limit": 10}, {"query": "NFLX"}),
)


# --- companies.get ----------------------------------------------------------- #


class CompanyGetInput(Shape):
    company: _Slug = Field(description="The company's slug, as companies.list returns it.")
    view: Literal["profile", "benefits", "locations"] = Field(
        default="profile", description="profile (facts, pay, price), or benefits or locations whole, a page at a time.",
    )
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="benefits and locations: most rows on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="benefits and locations: the next_cursor of the previous page.",
    )
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the answer.")


class FactConflict(Shape):
    """Another source asserting a materially different value."""

    value: FactValue = Field(json_schema_extra=_CONTENT)
    source: str = Field(json_schema_extra=_CODE)
    basis: Basis | None = Field(json_schema_extra=_CODE)
    observed_at: datetime | None


class ProfileFact(Shape):
    """A resolved fact and how far to trust it. An unasserted one has a null
    value and null provenance."""

    field: str = Field(json_schema_extra=_CODE)
    value: FactValue = Field(json_schema_extra=_CONTENT)
    #: The source whose claim won.
    source: str | None = Field(json_schema_extra=_CODE)
    basis: Basis | None = Field(json_schema_extra=_CODE)
    observed_at: datetime | None
    #: `fresh` or `stale`, by how long a claim about this field stays current.
    freshness: str | None = Field(json_schema_extra=_CODE)
    #: The person pinned this value; it outranks every source.
    pinned: bool
    #: The plugin answering this fact, or null: RoleBand's own data.
    answered_by: str | None = Field(json_schema_extra=_IDENTIFIER)
    conflicts: list[FactConflict]


class ReviewItem(Shape):
    """A fact the person is asked to confirm or correct, with the best-trusted value on offer."""

    field: str = Field(json_schema_extra=_CODE)
    #: `conflict`, `stale` or `missing`.
    reason: str = Field(json_schema_extra=_CODE)
    suggestion: FactValue = Field(json_schema_extra=_CONTENT)
    suggestion_source: str | None = Field(json_schema_extra=_CODE)


class PayRung(Shape):
    """One level of the company's pay ladder, in whole units of `currency` as
    its publisher stated them, never converted; shares are fractions."""

    level: str = Field(json_schema_extra=_CONTENT)
    band: str | None = Field(json_schema_extra=_CODE)
    currency: str = Field(json_schema_extra=_CODE)
    total_median: int | None
    base: int | None
    stock: int | None
    bonus: int | None
    base_share: float | None
    stock_share: float | None
    bonus_share: float | None
    source: str = Field(json_schema_extra=_CODE)
    source_url: str | None = Field(json_schema_extra=_IDENTIFIER)


class LevelBase(Shape):
    """RoleBand's own base pay for one band, in US dollars; a total only when
    base, bonus and stock are all known."""

    band: str = Field(json_schema_extra=_CODE)
    base_usd: int
    #: The bonus target as a share of base: 0 for a company that pays none,
    #: null when its policy is not known.
    bonus_ratio: float | None
    bonus_usd: int | None
    stock_usd: int | None
    total_usd: int | None
    #: Its base is below the band under it: thin or mixed evidence, shown as it is.
    below_lower: bool


class OfferFact(Shape):
    fact: str = Field(json_schema_extra=_CODE)
    #: A rule code, a yes or no, or whole US dollars; null when searched for and not found.
    value: str | int | bool | None = Field(json_schema_extra=_CODE)
    #: `employer` when the employer states it, `estimated` when weighed from reports.
    stated_by: Literal["employer", "estimated"] | None = Field(json_schema_extra=_CODE)


class OfferRules(Shape):
    """How the company builds an offer, from the level atlas."""

    verified_on: date | None
    facts: list[OfferFact]
    #: Facts the atlas searched for and did not find.
    unknown_fields: list[str] = Field(json_schema_extra=_CODE)


class Answering(Shape):
    """Who answers one part of the profile: RoleBand's data or one plugin."""

    plugin: str | None = Field(json_schema_extra=_IDENTIFIER)
    plugin_name: str | None = Field(json_schema_extra=_CONTENT)
    #: False when the plugin has not read this company yet; never RoleBand's data in its place.
    covered: bool


class Pay(Shape):
    #: The ladder the estimates read, highest total first.
    levels: list[PayRung]
    #: RoleBand's per-band base; empty while a pay plugin answers.
    level_base: list[LevelBase]
    #: Null when the level atlas has not researched the company.
    offer_policy: OfferRules | None
    notes: str | None = Field(json_schema_extra=_CONTENT)
    answered_by: Answering


class Quote(Shape):
    """The latest cached quote. `as_of` is a market date."""

    ticker: str = Field(json_schema_extra=_CODE)
    price: float
    currency: str = Field(json_schema_extra=_CODE)
    change_abs: float | None
    change_pct: float | None
    as_of: date


class Place(Shape):
    city: str = Field(json_schema_extra=_CONTENT)
    open_roles: int
    #: The country group the city falls in; null for a city no country claims.
    country: str | None = Field(json_schema_extra=_CODE)
    is_hq: bool


class CompanyProfileView(Shape):
    view: Literal["profile"] = Field(json_schema_extra=_CODE)
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    name: str = Field(json_schema_extra=_CONTENT)
    #: `ok`, or the worst of what needs review: `conflict`, `stale` or `missing`.
    health: str | None = Field(json_schema_extra=_CODE)
    facts: list[ProfileFact]
    needs_review: list[ReviewItem]
    pay: Pay
    #: Benefits on the `benefits` view; perks are never summed into a total.
    benefits: int
    benefits_answered_by: Answering
    #: Open roles as the Board counts them: 0 when the company is off the Board.
    open_roles: int
    #: A tracked company the person does not follow.
    unfollowed: bool
    #: The busiest places, by open roles; the `locations` view lists every one.
    places: list[Place]
    place_count: int
    #: Null for a private company or before the first quote.
    price: Quote | None
    #: The credit every plugin answering this profile requires.
    attribution: str | None = Field(json_schema_extra=_CONTENT)


#: Each position of a benefits row, in order.
BENEFIT_COLUMNS: tuple[str, ...] = (
    "category", "type", "name", "value_usd", "value_text", "description", "kind", "country", "reviewed", "mentions",
    "source",
)

#: One benefit, positioned as `BENEFIT_COLUMNS` names: its category and type
#: (taxonomy codes); a provider's own name where no type maps it; a per-perk
#: estimate in US dollars, never part of a total; its wording; a longer
#: description; whether it is a `dataset` record, the `employer`'s own words
#: or a `provider`'s row; the country it applies to (null is unknown, not
#: global); whether a person reviewed it; how many postings name it; and who
#: answers it.
BenefitRow = tuple[
    str, str | None, str | None, int | None, str | None, str | None, str, str | None, bool, int, str,
]

#: Each position of a locations row, in order.
PLACE_COLUMNS: tuple[str, ...] = ("city", "open_roles", "country", "is_hq")
PlaceRow = tuple[str, int, str | None, bool]


class CompanyBenefitsPage(Shape):
    view: Literal["benefits"] = Field(json_schema_extra=_CODE)
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    #: Sentences several benefits share, said once; on the first page only.
    notes: list[str] = Field(json_schema_extra=_CONTENT)
    answered_by: Answering
    columns: list[str] = Field(json_schema_extra=_CODE)
    rows: list[BenefitRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)


class CompanyLocationsPage(Shape):
    view: Literal["locations"] = Field(json_schema_extra=_CODE)
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    columns: list[str] = Field(json_schema_extra=_CODE)
    #: Busiest first, by open roles.
    rows: list[PlaceRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)


class CompanyView(RootModel[CompanyProfileView | CompanyBenefitsPage | CompanyLocationsPage]):
    """One company in the view the caller asked for; `view` names which."""

    root: CompanyProfileView | CompanyBenefitsPage | CompanyLocationsPage = Field(discriminator="view")


COMPANIES_GET = OperationDescriptor(
    id="companies.get",
    summary="One company's profile: facts with their source and basis, pay, price; or its benefits or places.",
    input=CompanyGetInput,
    result=CompanyView,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("market_statistic",),
    examples=({"company": "stripe"}, {"company": "stripe", "view": "benefits"}),
)


# --- companies.facts.list ---------------------------------------------------- #


class FactsListInput(Shape):
    company: _Slug = Field(description="The company's slug, as companies.list returns it.")
    field: str | None = Field(
        default=None, min_length=1, max_length=64, description="Only the claims about this fact, such as headcount.",
    )
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Most rows on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page, read with the same filters.",
    )
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")


CLAIM_COLUMNS: tuple[str, ...] = ("field", "value", "source", "basis", "rank", "observed_at")
#: One claim, positioned as `CLAIM_COLUMNS` names: the fact, the value the
#: source asserted, the source and its basis, its trust rank (higher wins a
#: disagreement) and when it was observed. Newest first within a fact.
ClaimRow = tuple[str, FactValue, str, Basis | None, int, datetime | None]


class FactsPage(Shape):
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    columns: list[str] = Field(json_schema_extra=_CODE)
    rows: list[ClaimRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)


COMPANIES_FACTS_LIST = OperationDescriptor(
    id="companies.facts.list",
    summary="Every claim every source made about a company's facts, with its basis and trust: the evidence behind a conflict.",
    input=FactsListInput,
    result=FactsPage,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("market_statistic",),
    examples=({"company": "stripe", "field": "headcount"},),
)


# --- companies.prices.get ---------------------------------------------------- #


PriceRange = Literal["1m", "3m", "6m", "1y"]


class PricesInput(Shape):
    company: _Slug = Field(description="The company's slug, as companies.list returns it.")
    range: PriceRange = Field(default="3m", description="How far back: 1m, 3m, 6m or 1y.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512, description="The next_cursor of the previous page.",
    )
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")


BAR_COLUMNS: tuple[str, ...] = ("date", "open", "high", "low", "close", "volume")
BarRow = tuple[str, float | None, float | None, float | None, float, int | None]


class PricesPage(Shape):
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    range: PriceRange = Field(json_schema_extra=_CODE)
    currency: str = Field(json_schema_extra=_CODE)
    latest: Quote | None
    #: Who to credit for the bars; null when there are none.
    attribution: str | None = Field(json_schema_extra=_CONTENT)
    #: A price key is set: an empty range waits for the next price read, not for the person.
    feed_configured: bool
    #: Daily bars in the range on every page together.
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    columns: list[str] = Field(json_schema_extra=_CODE)
    #: Oldest first.
    rows: list[BarRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)


COMPANIES_PRICES_GET = OperationDescriptor(
    id="companies.prices.get",
    summary="A listed company's daily share price bars over a range, with the latest quote.",
    input=PricesInput,
    result=PricesPage,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("market_statistic",),
    examples=({"company": "stripe", "range": "1y"},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (
    COMPANIES_LIST, COMPANIES_GET, COMPANIES_FACTS_LIST, COMPANIES_PRICES_GET,
)


# --- paging ------------------------------------------------------------------ #


@dataclass(frozen=True)
class Paged:
    """A page and what its envelope says about it."""

    data: Shape | CompanyView
    next_cursor: str | None
    #: The tier's budget ended the page before `limit` rows.
    shortened: bool = False


def _size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode())


def _start(operation: str, workspace_id: str, params: Shape, request: dict[str, Any]) -> tuple[str, int]:
    """The request's fingerprint and the position its cursor resumes at."""
    fingerprint = cursor.fingerprint(operation, workspace_id, request)
    given = getattr(params, "cursor", None)
    offset = cursor.decode(given, request=fingerprint)[0] if given is not None else 0
    return fingerprint, offset


def _page_rows(rows: list[Any], *, offset: int, limit: int, room: int) -> list[Any]:
    """The rows from `offset` that fit `limit` and `room` bytes; at least one,
    so paging always advances."""
    kept: list[Any] = []
    used = 0
    for row in rows[offset:offset + limit]:
        size = _size(row) + 1
        if kept and used + size > room:
            break
        kept.append(row)
        used += size
    if kept and _size(kept[0]) + 1 > room:
        raise OperationError(
            "invalid_input",
            "A row does not fit the tier's budget; ask with a larger tier.",
            details={"field": "tier", "reason": "over_budget", "budget_bytes": room},
        )
    return kept


def _finish(page: Shape, *, all_rows: list[Any], offset: int, limit: int, budget: int,
            fingerprint: str) -> Paged:
    """Fill `page` with the rows from `offset` that fit `budget` beside its header."""
    room = budget - _size(page.model_dump(mode="json"))
    kept = _page_rows(all_rows, offset=offset, limit=limit, room=room) if all_rows[offset:] else []
    page.count, page.rows = len(kept), kept  # type: ignore[attr-defined]
    end = offset + len(kept)
    return Paged(
        page,
        cursor.encode(request=fingerprint, offset=end) if end < len(all_rows) else None,
        shortened=len(kept) < min(limit, len(all_rows) - offset),
    )


# --- reads ------------------------------------------------------------------- #


def _not_found(company: str) -> OperationError:
    return OperationError("not_found", "There is no company with this slug.", details={"company": company})


async def _visible_profile(session: AsyncSession, company: str) -> CompanyProfile:
    """The company's profile, unless there is none or the person hid the company."""
    profile = await session.get(CompanyProfile, company)
    hidden = await session.scalar(
        select(exists().where(TrackedCompany.slug == company, TrackedCompany.visible.is_(False)))
    )
    if profile is None or hidden:
        raise _not_found(company)
    return profile


async def company_page(session: AsyncSession, params: CompanyListInput, *, workspace_id: str) -> Paged:
    known = {sector.slug for sector in SECTORS}
    if unknown := [value for value in params.sector if value not in known]:
        raise OperationError(
            "invalid_input", "A sector names none the Companies screen files companies under.",
            details={"field": "sector", "unknown": unknown, "accepted": [sector.slug for sector in SECTORS]},
        )
    fingerprint, offset = _start(
        COMPANIES_LIST.id, workspace_id, params, params.model_dump(mode="json", exclude=set(_PAGING)),
    )
    roster = await profile_read.profile_list(session, await off_board_company_slugs(session))
    counts = await open_counts_by_company(session)
    words = params.query.strip().lower() if params.query else ""
    wanted = set(params.sector)
    matching = [
        item for item in roster["items"]
        if (not words or any(words in (item[key] or "").lower() for key in ("display_name", "slug", "ticker")))
        and (not params.needs_review or item["data_health"] != "ok")
        and (not wanted or wanted & set(item["sectors"]))
        and (params.researched is None or item["in_dataset"] is params.researched)
    ]
    matching.sort(key=lambda item: (item["display_name"].casefold(), item["slug"]))
    rows: list[CompanyRow] = [
        (
            item["slug"], item["display_name"], item["ticker"], item["is_public"], item["sectors"],
            item["in_dataset"], item["data_health"], item["headcount"], item["mapped_levels"],
            counts.get(item["slug"], 0), item["price"], item["change_pct"], item["currency"],
            item["price_as_of"],
        )
        for item in matching
    ]
    page = CompanyPage(total=len(rows), count=0, sectors=roster["sectors"], columns=list(COMPANY_COLUMNS), rows=[])
    return _finish(page, all_rows=rows, offset=offset, limit=params.limit,
                   budget=PAGE_BUDGET_BYTES[params.tier], fingerprint=fingerprint)


def _answering(source: dict[str, Any]) -> Answering:
    return Answering(plugin=source["plugin"], plugin_name=source["plugin_name"], covered=source["covered"])


def _fact(name: str, entry: dict[str, Any]) -> ProfileFact:
    return ProfileFact(
        field=name, value=entry["value"], source=entry["source"],
        basis="plugin" if entry["answered_by"] and entry["source"] else basis_of(entry["source"]),
        observed_at=entry["observed_at"], freshness=entry["freshness"], pinned=entry["is_manual"],
        answered_by=entry["answered_by"],
        conflicts=[
            FactConflict(value=c.get("value"), source=c["source"], basis=basis_of(c["source"]),
                         observed_at=c.get("observed_at"))
            for c in entry["conflicts"]
        ],
    )


async def company(session: AsyncSession, params: CompanyGetInput, *, workspace_id: str) -> Paged:
    await _visible_profile(session, params.company)
    if params.view != "profile":
        return await _company_list_view(session, params, workspace_id=workspace_id)
    if params.cursor is not None:
        raise OperationError(
            "invalid_input", "The profile view is one answer; a cursor pages the benefits and locations views.",
            details={"field": "cursor", "reason": "list_views_only"},
        )
    hidden = await off_board_company_slugs(session)
    found = await profile_read.profile_detail(session, params.company, hidden)
    if found is None:
        raise _not_found(params.company)
    quote = (await price_store.latest_price_map(session, [params.company])).get(params.company)
    view = CompanyProfileView(
        view="profile",
        slug=found["slug"],
        name=found["display_name"],
        health=found["data_health"],
        facts=[_fact(name, entry) for name, entry in found["fields"].items()],
        needs_review=[
            ReviewItem(
                field=item["field"], reason=item["reason"],
                suggestion=item["suggestion"]["value"] if item["suggestion"] else None,
                suggestion_source=item["suggestion"]["source"] if item["suggestion"] else None,
            )
            for item in found["needs_review"]
        ],
        pay=Pay(
            levels=[
                PayRung(
                    level=r["level_label"], band=r["band"], currency=r["currency"], total_median=r["tc_median"],
                    base=r["base_amount"], stock=r["stock_amount"], bonus=r["bonus_amount"],
                    base_share=r["base_pct"], stock_share=r["stock_pct"], bonus_share=r["bonus_pct"],
                    source=r["source"], source_url=r["source_url"],
                )
                for r in found["comp_levels"]
            ],
            level_base=[LevelBase.model_validate(row) for row in found["level_base"]],
            offer_policy=OfferRules.model_validate(found["offer_policy"]) if found["offer_policy"] else None,
            notes=found["comp_notes"],
            answered_by=_answering(found["sources"]["pay"]),
        ),
        benefits=sum(len(group["items"]) for group in found["benefits"]),
        benefits_answered_by=_answering(found["sources"]["benefits"]),
        open_roles=found["open_roles"],
        unfollowed=found["unfollowed"],
        places=[_place(loc) for loc in found["locations"][:PROFILE_PLACES]],
        place_count=len(found["locations"]),
        price=Quote.model_validate(quote) if quote else None,
        attribution=found["attribution"],
    )
    budget = PROFILE_BUDGET_BYTES[params.tier]
    if (size := _size(view.model_dump(mode="json"))) > budget:
        raise OperationError(
            "invalid_input", "This company's profile does not fit the tier's budget; ask with a larger tier.",
            details={"field": "tier", "reason": "over_budget", "budget_bytes": budget, "full_bytes": size},
        )
    return Paged(CompanyView(view), None)


def _place(location: dict[str, Any]) -> Place:
    return Place(city=location["city"], open_roles=location["open_count"], country=location["country"],
                 is_hq=location["is_hq"])


async def _company_list_view(session: AsyncSession, params: CompanyGetInput, *, workspace_id: str) -> Paged:
    fingerprint, offset = _start(
        COMPANIES_GET.id, workspace_id, params, {"company": params.company, "view": params.view},
    )
    hidden = await off_board_company_slugs(session)
    found = await profile_read.profile_detail(session, params.company, hidden)
    if found is None:
        raise _not_found(params.company)
    budget = PAGE_BUDGET_BYTES[params.tier]
    if params.view == "locations":
        places: list[PlaceRow] = [
            (loc["city"], loc["open_count"], loc["country"], loc["is_hq"]) for loc in found["locations"]
        ]
        page: Shape = CompanyLocationsPage(view="locations", slug=found["slug"], total=len(places), count=0,
                                           columns=list(PLACE_COLUMNS), rows=[])
        paged = _finish(page, all_rows=places, offset=offset, limit=params.limit, budget=budget,
                        fingerprint=fingerprint)
    else:
        benefits: list[BenefitRow] = [
            (
                group["category"], item["benefit_type"], item["name"], item["value_usd"], item["value_text"],
                item["description"], item["kind"], item["country"], item["reviewed"], item["mentions"],
                item["provider"],
            )
            for group in found["benefits"] for item in group["items"]
        ]
        page = CompanyBenefitsPage(
            view="benefits", slug=found["slug"], total=len(benefits), count=0,
            notes=[note["text"] for note in found["benefit_notes"]] if offset == 0 else [],
            answered_by=_answering(found["sources"]["benefits"]), columns=list(BENEFIT_COLUMNS), rows=[],
        )
        paged = _finish(page, all_rows=benefits, offset=offset, limit=params.limit, budget=budget,
                        fingerprint=fingerprint)
    return Paged(CompanyView(paged.data), paged.next_cursor, shortened=paged.shortened)  # type: ignore[arg-type]


async def facts(session: AsyncSession, params: FactsListInput, *, workspace_id: str) -> Paged:
    await _visible_profile(session, params.company)
    fingerprint, offset = _start(
        COMPANIES_FACTS_LIST.id, workspace_id, params, params.model_dump(mode="json", exclude=set(_PAGING)),
    )
    claims = await profile_read.profile_claims(session, params.company)
    rows: list[ClaimRow] = [
        (c["field"], c["value"], c["source"], basis_of(c["source"]), c["rank"], c["observed_at"])
        for c in claims
        if params.field is None or c["field"] == params.field
    ]
    page = FactsPage(slug=params.company, total=len(rows), count=0, columns=list(CLAIM_COLUMNS), rows=[])
    return _finish(page, all_rows=rows, offset=offset, limit=params.limit,
                   budget=PAGE_BUDGET_BYTES[params.tier], fingerprint=fingerprint)


async def prices(session: AsyncSession, params: PricesInput, *, workspace_id: str) -> Paged:
    await _visible_profile(session, params.company)
    fingerprint, offset = _start(
        COMPANIES_PRICES_GET.id, workspace_id, params, {"company": params.company, "range": params.range},
    )
    found = await profile_read.profile_prices(session, params.company, params.range, settings=get_settings())
    bars: list[BarRow] = [
        (bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]) for bar in found["bars"]
    ]
    page = PricesPage(
        slug=params.company, range=found["range"], currency=found["currency"],
        latest=Quote.model_validate(found["latest"]) if found["latest"] else None,
        attribution=found["attribution"], feed_configured=found["feed_configured"],
        total=len(bars), count=0, columns=list(BAR_COLUMNS), rows=[],
    )
    # Every bar on one page when the tier holds them, a page at a time otherwise.
    return _finish(page, all_rows=bars, offset=offset, limit=len(bars) or 1,
                   budget=PAGE_BUDGET_BYTES[params.tier], fingerprint=fingerprint)

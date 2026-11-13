"""Response contracts for the statistics and demand routes.

`GET /api/stats`, the Statistics overview, compensation, stock trajectory, equity
validation, the comp and disclosure trends, the level guide, and `/api/demand`. The velocity route
declares its own models beside its handler.

- **Every shape here is one our code builds**, so every model forbids unknown
  keys, declared in the order the builders write them. A row that names its
  group before its figures (`{"company": ..., **summary}`) is built from a key
  mixin listed LAST among the bases: Pydantic collects the last base's fields
  first.
- **Numbers keep the type the builders give them.** Percentiles are linear
  interpolations and always floats, even over one value; counts, dollars and
  histogram edges are integers; shares and rates are rounded floats.
- **Literals where our code owns the vocabulary**: the trend dimensions each
  handler accepts, the part sources the Stock tab names, the pooled disclosure
  basis, and the `USD` the payloads state. Companies, level bands and families stay `str`: they are database strings.
- One key set per route, so no unions. A disclosure-trend point for a day a
  series has no cell is assembled with `date` last, and arrives with `date`
  first like every other point.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from tracker.api.schemas.base import Built
from tracker.api.schemas.plugins import ReferenceChangeView
from tracker.api.schemas.text_class import text

# Held to their sources by `tests/test_api_statistics_contract.py`.
CompTrendDim = Literal["overall", "company", "level", "family"]
DisclosureTrendDim = Literal["overall", "company", "level"]


class _CompanyKey(Built):
    company: str


class _LevelBandKey(Built):
    level_band: str


class _FamilyKey(Built):
    family: str


# --------------------------------------------------------------------------- #
# `GET /api/stats` and the overview
# --------------------------------------------------------------------------- #


class StatsResponse(Built):
    """The header counts. "Today" starts at the user's local midnight."""

    open_total: int
    #: The roles the Board lights as new (`queries.jobs.new_listing_clause`):
    #: listed in the last `NEW_LISTING_DAYS` days, whatever the field's name.
    new_today: int
    reposted_today: int
    closed_today: int
    saved_total: int
    review_pending: int
    notif_unread: int
    #: Unread high-priority notifications: the bell turns red while any are.
    notif_high_unread: int
    by_company: dict[str, int]


class OverviewKpis(Built):
    open_total: int
    #: Roles first seen in the window that were new when found, by the New
    #: rule at our first sighting (`db.queries.motion`); never reposts.
    new_count: int
    #: Roles first seen in the window that were already listed when found: a
    #: company's first read, or a posting the employer dated earlier
    #: (`db.queries.motion`). Never in `new_count`.
    already_listed_count: int
    closed_count: int
    companies: int
    saved_total: int


class OverviewSkill(Built):
    term: str
    category: str
    job_count: int


class StatisticsOverviewResponse(Built):
    """`GET /api/statistics/overview`. `days <= 0` is all-time. The one-line
    brief is the dashboard's, said from these facts."""

    days: int
    #: Where the figures start: the window's start, or the scope's history when
    #: that is shorter (`queries.insights.window_since`). None before the history starts.
    since: datetime | None
    kpis: OverviewKpis
    top_skills: list[OverviewSkill]


class InsightsHistoryResponse(Built):
    """`GET /api/statistics/history`: when the history of the scope's companies
    starts (`queries.insights.history_since`) and how many whole days it covers."""

    since: datetime | None
    days: int


# --------------------------------------------------------------------------- #
# Compensation
# --------------------------------------------------------------------------- #


class CompCoverage(Built):
    with_comp: int
    total_open: int
    pct: float


class CompSummary(Built):
    """`comp_stats._summary`: dollars at the ends, interpolated percentiles between."""

    count: int
    min: int
    max: int
    p25: float
    p50: float
    p75: float
    p90: float


class CompLevelSummary(CompSummary, _LevelBandKey):
    """`level_band` first, then the summary."""


class CompCompanySummary(CompSummary, _CompanyKey):
    """`company` first, then the summary."""


class CompFamilySummary(CompSummary, _FamilyKey):
    """`family` first, then the summary; the client names the family."""


class DisclosedBand(Built):
    """One distinct base range an employer posts at a level, with the roles on it."""

    company: str
    level_band: str
    low: int
    high: int
    reqs: int


class PostedLevel(_LevelBandKey):
    """One level's posted base pay in one country and currency
    (`comp_stats._level_figure`). Each distinct range votes once. Below the
    minimums `enough` is false and the figure fields are null; the counts say
    why."""

    ranges: int
    employers: int
    roles: int
    enough: bool
    #: The median low and the median high of the ranges.
    low: float | None
    high: float | None
    #: The middle half of the ranges' midpoints.
    mid_p25: float | None
    mid_p75: float | None


class PostedUnplaced(Built):
    """Roles whose level cannot be placed, and their distinct ranges: counted apart."""

    roles: int
    ranges: int


class PostedCountryExclusions(Built):
    """One country's roles with a posted range that its figure does not read,
    by reason. The reasons are `PostedExclusions`', less `no_country`."""

    not_base: int
    not_yearly: int
    implausible: int
    placed_by_pay: int


class PostedCountry(Built):
    """Posted base pay for the roles in one country, in its own currency."""

    #: ISO 3166-1 alpha-2.
    country: str
    #: The currency most of the country's ranges are posted in; null with no range.
    currency: str | None
    #: Distinct ranges at a placed level.
    ranges: int
    #: One of the person's places lies in this country.
    yours: bool
    levels: list[PostedLevel]
    not_placed: PostedUnplaced
    #: Roles whose range is in another currency, never converted.
    other_currency: int
    #: Every distinct range at a placed level, uncapped.
    bands: list[DisclosedBand]
    #: This country's roles with a posted range its figure does not read.
    excluded: PostedCountryExclusions


class PostedExclusions(Built):
    """Roles with a posted range that no country's figure reads, by reason."""

    #: The range is total pay, or does not say what it holds.
    not_base: int
    #: Stated per hour or month, or a period its size contradicts.
    not_yearly: int
    #: No salary at any size.
    implausible: int
    #: The role names places in several countries, or none we can place.
    no_country: int
    #: The role's level was read from this range.
    placed_by_pay: int
    #: Every role above that names several countries or none, whatever its
    #: reason, `no_country` included: no country's own counts hold it.
    without_country: int


class PostedPay(Built):
    """`comp_stats.build_posted_pay`: what employers post as yearly base pay,
    per country and level, and the levels the person picked."""

    min_employers: int
    min_ranges: int
    #: The country the tab opens on; null with no country to show.
    default_country: str | None
    countries: list[PostedCountry]
    excluded: PostedExclusions
    #: The person's levels, in seniority order.
    your_levels: list[str]


class DisclosureCounts(Built):
    """`rate` is `disclosed / checked`, null while nothing in the group is checked."""

    open: int
    checked: int
    disclosed: int
    rate: float | None


class DisclosureCompany(DisclosureCounts, _CompanyKey):
    """`company` first, then the counts."""


class DisclosureLevel(DisclosureCounts, _LevelBandKey):
    """`level_band` first (`""` when unclassified), then the counts."""


class DisclosureRates(Built):
    overall: DisclosureCounts
    by_company: list[DisclosureCompany]
    by_level: list[DisclosureLevel]


class BaseCoverage(Built):
    """How many open roles have an estimated base only, of all open ones."""

    with_base: int
    total_open: int


class BaseEstimates(Built):
    """Roles priced by their base alone (`comp_component = "base"`): no total exists,
    so they are summarised apart from the totals and never on their axis."""

    min_roles: int
    coverage: BaseCoverage
    overall: CompSummary | None
    by_level: list[CompLevelSummary]
    by_company: list[CompCompanySummary]
    by_family: list[CompFamilySummary]


class CompensationStatsResponse(Built):
    """`GET /api/statistics/compensation`: what employers post, beside the estimate.

    A snapshot of the roles open now: no window. The Window lens moves
    the trend routes beside it, never this population."""

    #: The fewest priced roles a level, company or discipline needs.
    min_roles: int
    coverage: CompCoverage
    overall: CompSummary | None
    by_level: list[CompLevelSummary]
    by_company: list[CompCompanySummary]
    by_family: list[CompFamilySummary]
    posted: PostedPay
    disclosure: DisclosureRates
    base_estimates: BaseEstimates
    currency: Literal["USD"]


# --------------------------------------------------------------------------- #
# Stock trajectory
# --------------------------------------------------------------------------- #


PartSource = Literal["posted", "company_rule", "measured", "estimated", "mixed"]
SetApartReason = Literal[
    "not_us_pay", "level_unplaced", "base_only", "basis_unclear", "hourly", "monthly",
    "period_unclear", "total_compensation", "plugin_without_split", "plugin_not_covered",
]


class PartSources(Built):
    """Where each part of a package comes from (`analytics.stock_trajectory`)."""

    base: PartSource
    bonus: PartSource
    equity: PartSource


class CompPackage(Built):
    """A median package: base, bonus and equity always sum to `median_tc`."""

    count: int
    median_tc: int
    base: int
    bonus: int
    equity: int
    equity_pct: float
    sources: PartSources


class TrajectoryPrivateCompany(CompPackage, _CompanyKey):
    """`company` first, then its package, its equity vehicle and the vesting it states."""

    equity_vehicle: str | None
    vesting: str | None


class TrajectoryPublicCompany(TrajectoryPrivateCompany):
    """A listed company also names its ticker."""

    ticker: str | None


class TrajectoryChoiceCompany(_CompanyKey):
    """A company where each person picks the cash and stock mix: a total, no split."""

    ticker: str | None
    count: int
    median_tc: int
    total_source: Literal["posted", "estimated", "mixed"]


class TrajectorySetApart(Built):
    """Roles with a pay figure the tab does not split, by reason."""

    reason: SetApartReason = Field(json_schema_extra=text("code"))
    count: int


class CompTrajectoryResponse(Built):
    """`GET /api/statistics/comp-trajectory`."""

    currency: Literal["USD"]
    overall: CompPackage | None
    public: list[TrajectoryPublicCompany]
    private: list[TrajectoryPrivateCompany]
    choice: list[TrajectoryChoiceCompany]
    set_apart: list[TrajectorySetApart]


class OfferQuote(Built):
    """The last quote the prices job stored, in US dollars, and its market date."""

    price: float
    as_of: str


class OfferTermsCompany(_CompanyKey):
    """What the offer calculator fills in for one company (`analytics.stock_trajectory.build_offer_terms`).
    A fact the company does not state is null, never a default."""

    listed: bool
    ticker: str | None
    equity_vehicle: str | None = Field(json_schema_extra=text("code"))
    #: Percent vesting each year, as the company states it; at most four years.
    vesting: list[float] | None
    vesting_stated_by: Literal["employer", "estimated"] | None
    bonus_rule: Literal["none", "pct_of_base"] | None
    sign_on_bridges_vesting: bool
    #: Only while a price key is saved, and only a quote already stored.
    quote: OfferQuote | None


class OfferTermsResponse(Built):
    """`GET /api/statistics/offer-terms`."""

    feed_configured: bool
    companies: list[OfferTermsCompany]


# --------------------------------------------------------------------------- #
# Trends
# --------------------------------------------------------------------------- #


class CompTrendPoint(Built):
    """One day of one series; every percentile null on a day the series has no values."""

    date: str
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None


class CompTrendSeries(Built):
    key: str
    count: int
    points: list[CompTrendPoint]


class CompTrendsResponse(Built):
    """`GET /api/statistics/comp-trends`: one aligned series per key over a shared axis."""

    dim: CompTrendDim
    days: int
    dates: list[str]
    series: list[CompTrendSeries]
    #: Reference switches inside the window: drawn as
    #: markers, so a step in the series reads as a change of sources.
    reference_changes: list[ReferenceChangeView]


class DisclosureTrendPoint(Built):
    date: str
    open: int
    checked: int
    disclosed: int
    rate: float | None
    bands: int
    reqs: int
    low_p50: float | None
    high_p50: float | None


class DisclosureTrendSeries(Built):
    key: str
    checked: int
    disclosed: int
    points: list[DisclosureTrendPoint]


class DisclosureCohort(Built):
    """The companies read on the window's first day, which the `cohort` series follows."""

    since: str
    companies: int


class DisclosureTrendsResponse(Built):
    """`GET /api/statistics/disclosure-trends`; band medians pool only `basis`.

    `cohort` is set when the company set changed inside the window: the series
    keyed `cohort` then follows only the companies of its first day."""

    dim: DisclosureTrendDim
    days: int
    basis: Literal["base"]
    dates: list[str]
    series: list[DisclosureTrendSeries]
    cohort: DisclosureCohort | None


# --------------------------------------------------------------------------- #
# `GET /api/demand`
# --------------------------------------------------------------------------- #


class HiringCompany(Built):
    """One company's open roles, a place set once, and its motion."""

    company: str
    open: int
    #: New by the Board's rule (`queries.jobs.new_listing_clause`).
    new: int
    #: Closed in the same 2 days as `new`.
    closed: int


class HiringCountry(Built):
    key: str
    open: int


class HiringRegion(Built):
    """Roles open in a region, each once (`analytics.hiring`)."""

    key: str
    open: int
    #: Of `open`, the roles that name only the region ("Remote - EMEA"), so no
    #: country in it: counted here, never in each country.
    region_wide: int
    countries: list[HiringCountry]


class DemandResponse(Built):
    """`GET /api/demand`, the Hiring tab: where roles are open now, by company and
    place, and the roles new and closed in the New rule's 2 days.

    Read live from the roles Insights describes, never by summing the
    `demand_metrics` rollup, whose slices count a posting once per place group."""

    open_total: int
    #: New by the Board's rule and in scope, not reposts, a place set once.
    new: int
    #: Closed in the same 2 days, a place set once.
    closed: int
    companies: list[HiringCompany]
    regions: list[HiringRegion]
    #: Roles whose places name nothing a region holds ("Remote", "Anywhere").
    unplaced: int
    #: Share of the open roles that the employer dated (`analytics.age_basis`).
    #: None when nothing is open.
    employer_dated_share: float | None


class LevelGuideEntry(Built):
    """One label of the level guide and every spelling of the rungs behind
    it, so a search finds a rung the label hides (66 inside "65–67")."""

    label: str = Field(json_schema_extra=text("content"))
    spellings: list[str] = Field(json_schema_extra=text("content"))


class LevelGuideCell(Built):
    """How one company names one level: one entry for every function, or one
    per track. Exactly one key is present (`response_model_exclude_unset`)."""

    company_wide: LevelGuideEntry | SkipJsonSchema[None] = None
    per_track: dict[str, LevelGuideEntry] | SkipJsonSchema[None] = None


class LevelGuideCompany(Built):
    slug: str
    #: The company's titles state no level beyond these (`Ladder.flat`): a
    #: level with no cell is unstated, not skipped.
    flat: bool
    levels: dict[str, LevelGuideCell]


class LevelGuideUnguided(Built):
    """A company the app names that has no level guide of its own."""

    slug: str
    #: The company whose ladder this one shares (Google DeepMind reads
    #: Google's); null when none does.
    same_as: str | None


class LevelGuideResponse(Built):
    """`GET /api/statistics/levels`: every reviewed ladder, A to Z by slug,
    and the catalog companies without one."""

    companies: list[LevelGuideCompany]
    unguided: list[LevelGuideUnguided]
    #: Track slug -> the levels a role of that track can hold, lowest first
    #: (a manager is never an intern), as the Profile rail gates them.
    tracks: dict[str, list[str]]

"""The Insights reads: one operation per Insights figure the dashboard shows.

Each operation answers what its dashboard route answers, from the same code:
the agent route calls the dashboard's own route function and this module
reads its answer through a typed shape that mirrors the route's response
field for field. Nothing here computes a statistic, so the two cannot drift
apart; a shape that falls out of step with its route fails validation, and
`tests/test_agent_insights.py` holds every pair equal.

Each answer carries its `coverage` beside the figures: which population they
describe, the scope the read was narrowed to, the window, how much history
the scope's companies have, and when the radar last read them. A local
sample is not the labour market, so no figure travels without them.

Filters are the route's own. The closed-vocabulary values (disciplines,
companies, places) are read strictly, as search reads them: a value that
names nothing fails with the lookup that lists the accepted ones, never an
empty answer.

An answer is bounded by the caller's tool tier. Past the tier's budget, the
operation's long lists (`InsightsRead.paged`) stop early: the answer's `page`
says which lists are partial and `continue_with` names the call that reads
on from there, so no item is cut or lost to the budget. Paging is live, not
a snapshot.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic.config import JsonDict
from pydantic.experimental.missing_sentinel import MISSING
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations import cursor, vocabulary
from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.analytics.posting_reality import NEW_LISTING_WINDOW
from tracker.company_store import OffBoardSlugs, off_board_company_slugs
from tracker.db.models import ScrapeSourceRun
from tracker.db.queries.insights import (
    InsightsScope,
    Side,
    history_days,
    history_since,
    resolve_insights_scope,
)
from tracker.platform.util import MAX_WINDOW_DAYS
from tracker.schema import LevelBand

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_DIAGNOSTIC: JsonDict = {"x-text": "diagnostic"}

_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")
_LARGER_TIERS: tuple[ToolTier, ...] = ("standard", "full")

#: The most an answer's data may take, by tool tier, in UTF-8 bytes of its
#: JSON: the budgets a posting's detail view has (6,000 tokens for the small
#: tier, 16,000 above it, at two and a half bytes a token).
BUDGET_BYTES: dict[ToolTier, int] = {"small": 15_000, "standard": 40_000, "full": 40_000}


# --- the coverage every answer carries ------------------------------------------ #

#: What the figures count. `open_roles`: the roles open now at the companies on
#: the Board, in the radar's scope, a place set once (`jobs.insights_role_conds`
#: and the Board's count). `daily_records`: the per-day pay and disclosure
#: records each scan writes. `source_reads`: the radar's reads of each
#: company's listing. `reference`: the pinned reference data, which reads no
#: postings.
Population = Literal["open_roles", "daily_records", "source_reads", "reference"]


class CoverageWindow(Shape):
    #: The days asked for; 0 is all the history there is.
    days: int = Field(ge=0)
    #: Where the figures start: the window's start, or the history's when that
    #: is shorter. Null before the history starts, when there is none to cover.
    since: datetime | None


class CoverageHistory(Shape):
    """How far back the scope's companies have been read whole: no arrival
    before `since` can be dated, so no window reaches further."""

    since: datetime | None
    days: int = Field(ge=0)


class InsightsCoverage(Shape):
    population: Population = Field(json_schema_extra=_CODE)
    #: The companies side, disciplines, companies and places the read was
    #: narrowed to; an empty list narrows nothing.
    side: Side = Field(json_schema_extra=_CODE)
    families: list[str] = Field(json_schema_extra=_CODE)
    companies: list[str] = Field(json_schema_extra=_IDENTIFIER)
    places: list[str] = Field(json_schema_extra=_CODE)
    #: Companies the person hid or does not follow, left out of every figure;
    #: null for reference data, which reads no postings.
    off_board_companies: int | None
    #: Null when the figures describe what is open now, with no window.
    window: CoverageWindow | None
    history: CoverageHistory | None
    #: When the radar last finished reading one of the scope's companies;
    #: null for reference data and before any read.
    last_read_at: datetime | None


class InsightsPage(Shape):
    """Present when this answer holds part of its lists: the tier's budget
    ended it, or it was asked for from a cursor. The lists are read as one
    sequence in the order `lists` names them; `offset` is where this answer
    starts in it."""

    lists: list[str] = Field(json_schema_extra=_CODE)
    offset: int = Field(ge=0)
    returned: int = Field(ge=0)
    total: int = Field(ge=0)
    tier: ToolTier = Field(json_schema_extra=_CODE)
    budget_bytes: int
    #: The call that reads on from where this answer stops; empty at the end.
    continue_with: list[NextAction] = Field(default_factory=list)


class _Answer(Shape):
    coverage: InsightsCoverage
    #: Null when every list is whole.
    page: InsightsPage | None = None


# --- inputs ------------------------------------------------------------------- #



class _Scoped(Shape):
    side: Side = Field(
        default="all",
        description="Which companies: all, yours (the ones you picked) or other (followed through the market sweep).",
    )
    family: list[str] = Field(
        default_factory=list, max_length=20,
        description="Narrow to these disciplines (role families); vocabulary.list kind=family lists them.",
    )


class _Paged(Shape):
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the answer.")
    cursor: str | None = Field(
        default=None, max_length=128, description="Read on from where an answer stopped, as its continue_with gives it."
    )


class OverviewInput(_Scoped):
    days: int = Field(default=30, ge=0, le=MAX_WINDOW_DAYS, description="The window in days; 0 is all time.")


class CompensationInput(_Scoped, _Paged):
    pass


class PayTableInput(_Scoped, _Paged):
    country: str = Field(pattern=r"^[A-Za-z]{2}$", description="An ISO 3166-1 alpha-2 country code.")
    level: LevelBand = Field(description="The level band to compare companies at.")
    skill: str | None = Field(
        default=None, max_length=128, description="Narrow the companies to roles naming this skill (its slug)."
    )


class UnscopedInput(_Paged):
    pass


class PayTrendsInput(_Scoped, _Paged):
    dim: Literal["overall", "company", "level", "family"] = Field(
        default="overall", description="One series overall, or one per company, level or discipline."
    )
    days: int = Field(default=90, ge=0, le=MAX_WINDOW_DAYS, description="The window in days; 0 is all history.")


class DisclosureTrendsInput(_Paged):
    side: Side = Field(default="all", description="Which companies: all, yours or other.")
    dim: Literal["overall", "company", "level"] = Field(
        default="overall", description="One series overall, or one per company or level."
    )
    days: int = Field(default=90, ge=0, le=MAX_WINDOW_DAYS, description="The window in days; 0 is all history.")


class VelocityInput(_Scoped, _Paged):
    days: int = Field(default=30, ge=0, le=MAX_WINDOW_DAYS, description="The window in days; 0 is all time.")


class HistoryInput(_Scoped):
    pass


class DemandInput(_Scoped, _Paged):
    pass


class SkillsInput(_Scoped, _Paged):
    company: list[str] = Field(
        default_factory=list, max_length=50, description="Narrow the slice to these companies."
    )
    location: list[str] = Field(
        default_factory=list, max_length=20,
        description="Narrow the slice to these places; vocabulary.list kind=location lists them.",
    )
    limit: int = Field(default=30, ge=1, le=200, description="How many skills to rank.")


# --- overview, history ---------------------------------------------------------- #


class InsightsOverviewKpis(Shape):
    open_total: int
    #: Roles first seen in the window that were new when found; never reposts.
    new_count: int
    #: Roles first seen in the window that were already listed when found.
    already_listed_count: int
    closed_count: int
    companies: int
    #: The roles the person saved: absent when they do not share their pursuits.
    saved_total: int | MISSING = MISSING


class InsightsOverviewSkill(Shape):
    term: str = Field(json_schema_extra=_CODE)
    category: str = Field(json_schema_extra=_CODE)
    job_count: int


class InsightsOverview(_Answer):
    days: int
    since: datetime | None
    kpis: InsightsOverviewKpis
    top_skills: list[InsightsOverviewSkill]


class InsightsHistory(_Answer):
    since: datetime | None
    days: int


# --- compensation --------------------------------------------------------------- #


class InsightsDisclosedBand(Shape):
    company: str = Field(json_schema_extra=_IDENTIFIER)
    level_band: str = Field(json_schema_extra=_CODE)
    low: int
    high: int
    reqs: int


class InsightsPostedLevel(Shape):
    """One level's posted yearly base pay in one country and currency. Below
    the minimums `enough` is false and the figures are null."""

    level_band: str = Field(json_schema_extra=_CODE)
    ranges: int
    employers: int
    roles: int
    enough: bool
    low: float | None
    high: float | None
    mid_p25: float | None
    mid_p75: float | None


class InsightsPostedUnplaced(Shape):
    roles: int
    ranges: int


class InsightsPostedCountryExclusions(Shape):
    not_base: int
    not_yearly: int
    implausible: int
    placed_by_pay: int


class InsightsPostedCountry(Shape):
    country: str = Field(json_schema_extra=_CODE)
    currency: str | None = Field(json_schema_extra=_CODE)
    ranges: int
    #: One of the person's places lies in this country.
    yours: bool
    levels: list[InsightsPostedLevel]
    not_placed: InsightsPostedUnplaced
    #: Roles whose range is in another currency, never converted.
    other_currency: int
    #: The distinct ranges at a placed level; paged by the tier's budget.
    bands: list[InsightsDisclosedBand]
    excluded: InsightsPostedCountryExclusions


class InsightsPostedExclusions(Shape):
    not_base: int
    not_yearly: int
    implausible: int
    no_country: int
    placed_by_pay: int
    without_country: int


class InsightsPostedPay(Shape):
    """What employers post as yearly base pay, per country and level: stated
    pay only, never an estimate."""

    min_employers: int
    min_ranges: int
    default_country: str | None = Field(json_schema_extra=_CODE)
    countries: list[InsightsPostedCountry]
    excluded: InsightsPostedExclusions
    your_levels: list[str] = Field(json_schema_extra=_CODE)


class InsightsDisclosureCounts(Shape):
    open: int
    checked: int
    disclosed: int
    rate: float | None


class InsightsDisclosureLevel(Shape):
    level_band: str = Field(json_schema_extra=_CODE)
    open: int
    checked: int
    disclosed: int
    rate: float | None


class InsightsDisclosureRates(Shape):
    overall: InsightsDisclosureCounts
    by_level: list[InsightsDisclosureLevel]


class InsightsCompensation(_Answer):
    posted: InsightsPostedPay
    disclosure: InsightsDisclosureRates


class InsightsPayTableRange(Shape):
    low: int
    high: int
    roles: int


class InsightsPayTableEstimate(Shape):
    """RoleBand's estimate of base salary: a span, never stated pay."""

    low: int
    high: int
    families: list[str] = Field(json_schema_extra=_CODE)


class InsightsPayTableTotal(Shape):
    """RoleBand's estimate of total compensation, as a span."""

    low: int
    high: int
    rung: str | None = Field(json_schema_extra=_CONTENT)


class InsightsPayTableEquity(Shape):
    vehicle: str | None = Field(json_schema_extra=_CODE)
    vesting: str | None = Field(json_schema_extra=_CONTENT)
    rule: Literal["none", "employee_election"] | None = Field(json_schema_extra=_CODE)


class InsightsPayTableRow(Shape):
    """One company hiring at the level in the country. `low`, `high` and
    `ranges` are what it posts; `estimate_base` and `estimate_total` are
    estimates, never stated pay."""

    company: str = Field(json_schema_extra=_IDENTIFIER)
    followed_as_set: bool
    open_roles: int
    posting: int
    checked: int
    currency: str | None = Field(json_schema_extra=_CODE)
    low: float | None
    high: float | None
    ranges: list[InsightsPayTableRange]
    other_currency: bool
    reason: (
        Literal["total", "unclear", "several_countries", "not_yearly", "placed_by_pay", "unread", "none"] | None
    ) = Field(json_schema_extra=_CODE)
    estimate_base: InsightsPayTableEstimate | None
    estimate_total: InsightsPayTableTotal | None
    equity: InsightsPayTableEquity | None


class InsightsPayTableUnplaced(Shape):
    company: str = Field(json_schema_extra=_IDENTIFIER)
    roles: int


class InsightsPayTableSkill(Shape):
    term: str = Field(json_schema_extra=_CODE)
    roles: int


class InsightsPayDiscipline(Shape):
    family: str = Field(json_schema_extra=_CODE)
    picked: bool
    ranges: int
    employers: int
    roles: int
    enough: bool
    low: float | None
    high: float | None
    mid_p25: float | None
    mid_p75: float | None
    top_share: float
    withheld: Literal["too_few", "one_employer"] | None = Field(json_schema_extra=_CODE)


class InsightsPayByDiscipline(Shape):
    min_employers: int
    min_ranges: int
    max_employer_share: float
    disciplines: list[InsightsPayDiscipline]


class InsightsPayTable(_Answer):
    country: str = Field(json_schema_extra=_CODE)
    level_band: str = Field(json_schema_extra=_CODE)
    currency: str | None = Field(json_schema_extra=_CODE)
    skill: str | None = Field(json_schema_extra=_CODE)
    #: Estimates exist for this country (US pay only).
    estimates: bool
    rows: list[InsightsPayTableRow]
    not_placed: list[InsightsPayTableUnplaced]
    skills: list[InsightsPayTableSkill]
    min_skill_roles: int
    by_discipline: InsightsPayByDiscipline


# --- trajectory and offer terms ----------------------------------------------- #

PartSource = Literal["posted", "company_rule", "measured", "estimated", "mixed"]


class InsightsPartSources(Shape):
    """Where each part of a package comes from: what a posting states, what
    the company's rule sets, what was measured, or an estimate."""

    base: PartSource = Field(json_schema_extra=_CODE)
    bonus: PartSource = Field(json_schema_extra=_CODE)
    equity: PartSource = Field(json_schema_extra=_CODE)


class InsightsCompPackage(Shape):
    count: int
    median_tc: int
    base: int
    bonus: int
    equity: int
    equity_pct: float
    sources: InsightsPartSources


class InsightsTrajectoryPrivateCompany(Shape):
    company: str = Field(json_schema_extra=_IDENTIFIER)
    count: int
    median_tc: int
    base: int
    bonus: int
    equity: int
    equity_pct: float
    sources: InsightsPartSources
    equity_vehicle: str | None = Field(json_schema_extra=_CODE)
    vesting: str | None = Field(json_schema_extra=_CONTENT)


class InsightsTrajectoryPublicCompany(InsightsTrajectoryPrivateCompany):
    ticker: str | None = Field(json_schema_extra=_IDENTIFIER)


class InsightsTrajectoryChoiceCompany(Shape):
    company: str = Field(json_schema_extra=_IDENTIFIER)
    ticker: str | None = Field(json_schema_extra=_IDENTIFIER)
    count: int
    median_tc: int
    total_source: Literal["posted", "estimated", "mixed"] = Field(json_schema_extra=_CODE)


class InsightsTrajectorySetApart(Shape):
    reason: Literal[
        "not_us_pay", "level_unplaced", "base_only", "basis_unclear", "hourly", "monthly",
        "period_unclear", "total_compensation", "plugin_without_split", "plugin_not_covered",
    ] = Field(json_schema_extra=_CODE)
    count: int


class InsightsTrajectory(_Answer):
    currency: Literal["USD"] = Field(json_schema_extra=_CODE)
    overall: InsightsCompPackage | None
    public: list[InsightsTrajectoryPublicCompany]
    private: list[InsightsTrajectoryPrivateCompany]
    choice: list[InsightsTrajectoryChoiceCompany]
    set_apart: list[InsightsTrajectorySetApart]


class InsightsOfferQuote(Shape):
    price: float
    as_of: str = Field(json_schema_extra=_IDENTIFIER)


class InsightsOfferTermsCompany(Shape):
    """The terms a company states for an offer; a term it does not state is null."""

    company: str = Field(json_schema_extra=_IDENTIFIER)
    listed: bool
    ticker: str | None = Field(json_schema_extra=_IDENTIFIER)
    equity_vehicle: str | None = Field(json_schema_extra=_CODE)
    vesting: list[float] | None
    vesting_stated_by: Literal["employer", "estimated"] | None = Field(json_schema_extra=_CODE)
    bonus_rule: Literal["pct_of_base", "none"] | None = Field(json_schema_extra=_CODE)
    sign_on_bridges_vesting: bool
    quote: InsightsOfferQuote | None


class InsightsOfferTerms(_Answer):
    feed_configured: bool
    companies: list[InsightsOfferTermsCompany]


# --- levels ---------------------------------------------------------------------- #


class InsightsLevelGuideEntry(Shape):
    label: str = Field(json_schema_extra=_CONTENT)
    spellings: list[str] = Field(json_schema_extra=_CONTENT)


class InsightsLevelGuideCell(Shape):
    """How one company names one level: one entry for every function
    (`company_wide`), or one per track (`per_track`); the other is null."""

    company_wide: InsightsLevelGuideEntry | None = None
    per_track: dict[str, InsightsLevelGuideEntry] | None = None


class InsightsLevelGuideCompany(Shape):
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    flat: bool
    levels: dict[str, InsightsLevelGuideCell]


class InsightsLevelGuideUnguided(Shape):
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    same_as: str | None = Field(json_schema_extra=_IDENTIFIER)


class InsightsLevels(_Answer):
    companies: list[InsightsLevelGuideCompany]
    unguided: list[InsightsLevelGuideUnguided]
    tracks: dict[str, list[str]]


# --- trends ----------------------------------------------------------------------- #


class InsightsPayTrendPoint(Shape):
    date: str = Field(json_schema_extra=_IDENTIFIER)
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None


class InsightsPayTrendSeries(Shape):
    key: str = Field(json_schema_extra=_CODE)
    count: int
    points: list[InsightsPayTrendPoint]


class InsightsReferenceChange(Shape):
    """A switch of the pay reference inside the window: a step in a series
    there is a change of sources, not of the market."""

    id: int
    at: datetime
    jobs: int
    moved: int
    gained: int
    lost: int
    companies: int


class InsightsPayTrends(_Answer):
    dim: Literal["overall", "company", "level", "family"] = Field(json_schema_extra=_CODE)
    days: int
    dates: list[str] = Field(json_schema_extra=_IDENTIFIER)
    series: list[InsightsPayTrendSeries]
    reference_changes: list[InsightsReferenceChange]


class InsightsDisclosureTrendPoint(Shape):
    date: str = Field(json_schema_extra=_IDENTIFIER)
    open: int
    checked: int
    disclosed: int
    rate: float | None
    bands: int
    reqs: int
    low_p50: float | None
    high_p50: float | None


class InsightsDisclosureTrendSeries(Shape):
    key: str = Field(json_schema_extra=_CODE)
    checked: int
    disclosed: int
    points: list[InsightsDisclosureTrendPoint]


class InsightsDisclosureCohort(Shape):
    since: str = Field(json_schema_extra=_IDENTIFIER)
    companies: int


class InsightsDisclosureTrends(_Answer):
    dim: Literal["overall", "company", "level"] = Field(json_schema_extra=_CODE)
    days: int
    basis: Literal["base"] = Field(json_schema_extra=_CODE)
    dates: list[str] = Field(json_schema_extra=_IDENTIFIER)
    series: list[InsightsDisclosureTrendSeries]
    cohort: InsightsDisclosureCohort | None


# --- velocity, demand, skills ------------------------------------------------------- #


class InsightsVelocityKpis(Shape):
    open_total: int
    opened: int
    closed: int
    reposted: int
    #: Roles first seen in the window that were already listed when found; never in `opened`.
    already_listed: int
    median_days_open: float | None
    #: Open roles whose start is unknown: outside `median_days_open` and `aging`.
    age_unknown: int
    employer_dated_share: float | None
    #: How long the roles that came down had been posted; not a time to hire.
    median_observed_listing_duration_days: float | None
    closed_sample: int
    closed_unknown: int
    closed_employer_dated_share: float | None


class InsightsVelocityAgingBand(Shape):
    lo: int
    hi: int | None
    count: int


class InsightsVelocityCompany(Shape):
    company: str = Field(json_schema_extra=_IDENTIFIER)
    open: int
    opened: int
    closed: int
    reposted: int
    median_days_open: float | None
    median_observed_listing_duration_days: float | None


class InsightsVelocity(_Answer):
    days: int
    since: datetime | None
    kpis: InsightsVelocityKpis
    aging: list[InsightsVelocityAgingBand]
    posted: list[InsightsVelocityAgingBand]
    by_company: list[InsightsVelocityCompany]


class InsightsHiringCompany(Shape):
    company: str = Field(json_schema_extra=_IDENTIFIER)
    open: int
    new: int
    closed: int


class InsightsHiringCountry(Shape):
    key: str = Field(json_schema_extra=_CODE)
    open: int


class InsightsHiringRegion(Shape):
    key: str = Field(json_schema_extra=_CODE)
    open: int
    #: Roles that name only the region, counted here and in no country.
    region_wide: int
    countries: list[InsightsHiringCountry]


class InsightsDemand(_Answer):
    open_total: int
    #: New by the Board's rule, not reposts, in the window `coverage` names.
    new: int
    #: Came down in the same window.
    closed: int
    companies: list[InsightsHiringCompany]
    regions: list[InsightsHiringRegion]
    unplaced: int
    employer_dated_share: float | None


class InsightsTopSkill(Shape):
    term: str = Field(json_schema_extra=_CODE)
    category: str = Field(json_schema_extra=_CODE)
    job_count: int
    share: float
    market_share: float
    lift: float | None
    distinctiveness: float


class InsightsSkills(_Answer):
    items: list[InsightsTopSkill]
    competencies: list[InsightsTopSkill]
    roles: int
    market_roles: int
    narrowed: bool


# --- the operations ---------------------------------------------------------------- #


def _descriptor(
    id: str, summary: str, input: type[BaseModel], result: type[BaseModel], *,
    tiers: tuple[ToolTier, ...] = _LARGER_TIERS, examples: tuple[dict[str, Any], ...] = (),
    data_classes: tuple[DataClass, ...] = ("market_statistic",),
) -> OperationDescriptor:
    return OperationDescriptor(
        id=id,
        summary=summary,
        input=input,
        result=result,
        access="read",
        idempotency="read",
        engine_effects=EngineEffects(),
        tool_tiers=tiers,
        data_classes=data_classes,
        examples=examples,
    )


INSIGHTS_OVERVIEW = _descriptor(
    "insights.overview",
    "Count the open roles, the roles that opened and came down in a window, and the skills most asked for.",
    OverviewInput, InsightsOverview, tiers=_EVERY_TIER, examples=({"days": 90},),
    # The count of saved roles is the person's own.
    data_classes=("market_statistic", "private_pursuit"),
)
INSIGHTS_COMPENSATION = _descriptor(
    "insights.compensation",
    "Show the yearly base pay employers post per country and level, and how many open roles state pay.",
    CompensationInput, InsightsCompensation, tiers=_EVERY_TIER, examples=({"side": "yours"},),
)
INSIGHTS_PAY_TABLE = _descriptor(
    "insights.pay_table",
    "Compare the companies hiring at one level in one country: the pay each posts, and estimates kept apart.",
    PayTableInput, InsightsPayTable, examples=({"country": "US", "level": "senior"},),
)
INSIGHTS_TRAJECTORY = _descriptor(
    "insights.trajectory",
    "Show each company's typical pay package split into base, bonus and equity, and where each part comes from.",
    UnscopedInput, InsightsTrajectory,
)
INSIGHTS_OFFER_TERMS = _descriptor(
    "insights.offer_terms",
    "List the offer terms companies state: equity vehicle, vesting, bonus rule and the last stored share price.",
    UnscopedInput, InsightsOfferTerms,
)
INSIGHTS_LEVELS = _descriptor(
    "insights.levels",
    "Show how each company names each level band, and which levels each track can hold.",
    UnscopedInput, InsightsLevels,
)
INSIGHTS_PAY_TRENDS = _descriptor(
    "insights.pay_trends",
    "Show estimated pay percentiles day by day, overall or per company, level or discipline.",
    PayTrendsInput, InsightsPayTrends, examples=({"dim": "level", "days": 30},),
)
INSIGHTS_DISCLOSURE_TRENDS = _descriptor(
    "insights.disclosure_trends",
    "Show day by day how many open roles state a pay range, and the median range they state.",
    DisclosureTrendsInput, InsightsDisclosureTrends, examples=({"dim": "company"},),
)
INSIGHTS_VELOCITY = _descriptor(
    "insights.velocity",
    "Show how many roles opened and came down in a window, and how long roles stay posted.",
    VelocityInput, InsightsVelocity, examples=({"days": 90},),
)
INSIGHTS_HISTORY = _descriptor(
    "insights.history",
    "Say how far back the radar has read the companies in scope, which bounds every window.",
    HistoryInput, InsightsHistory, tiers=_EVERY_TIER,
)
INSIGHTS_DEMAND = _descriptor(
    "insights.demand",
    "Show where roles are open now, by company and place, and which opened and came down in the last days.",
    DemandInput, InsightsDemand, tiers=_EVERY_TIER,
)
INSIGHTS_SKILLS = _descriptor(
    "insights.skills",
    "Rank the skills open roles ask for, in a slice against the whole market.",
    SkillsInput, InsightsSkills, tiers=_EVERY_TIER, examples=({"limit": 10},),
)

#: Where an answer's window comes from. `figures`: the `days` asked for and the
#: `since` the figures state. `axis`: the `days` asked for, starting at the
#: first day the series hold. `new_listing`: the New rule's window, which the
#: new and closed counts cover.
WindowSource = Literal["none", "figures", "axis", "new_listing"]


@dataclass(frozen=True)
class InsightsRead:
    descriptor: OperationDescriptor
    population: Population
    window: WindowSource = "none"
    #: The lists the tier's budget pages, as dotted paths into the answer; a
    #: `*` steps into every item of a list. They are read as one sequence in
    #: this order.
    paged: tuple[str, ...] = ()
    #: The figures that count the person's pursuits, as dotted paths to a key:
    #: left out when they do not share them.
    pursuits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.pursuits) != ("private_pursuit" in self.descriptor.data_classes):
            raise ValueError(f"{self.descriptor.id}: a read with pursuit figures declares private_pursuit")


READS: dict[str, InsightsRead] = {
    read.descriptor.id: read
    for read in (
        InsightsRead(INSIGHTS_OVERVIEW, "open_roles", "figures", pursuits=("kpis.saved_total",)),
        InsightsRead(INSIGHTS_COMPENSATION, "open_roles", paged=("posted.countries.*.bands",)),
        InsightsRead(INSIGHTS_PAY_TABLE, "open_roles", paged=("rows", "not_placed", "skills")),
        InsightsRead(INSIGHTS_TRAJECTORY, "open_roles", paged=("public", "private", "choice")),
        InsightsRead(INSIGHTS_OFFER_TERMS, "reference", paged=("companies",)),
        InsightsRead(INSIGHTS_LEVELS, "reference", paged=("companies", "unguided")),
        InsightsRead(INSIGHTS_PAY_TRENDS, "daily_records", "axis", paged=("series",)),
        InsightsRead(INSIGHTS_DISCLOSURE_TRENDS, "daily_records", "axis", paged=("series",)),
        InsightsRead(INSIGHTS_VELOCITY, "open_roles", "figures", paged=("by_company",)),
        InsightsRead(INSIGHTS_HISTORY, "source_reads"),
        InsightsRead(INSIGHTS_DEMAND, "open_roles", "new_listing", paged=("companies", "regions")),
        InsightsRead(INSIGHTS_SKILLS, "open_roles", paged=("items", "competencies")),
    )
}

OPERATIONS: tuple[OperationDescriptor, ...] = tuple(read.descriptor for read in READS.values())


# --- answering ------------------------------------------------------------------- #

#: The dashboard's figures for one read: the route's own function, given the
#: off-Board companies, the resolved scope and the operation's input.
Figures = Callable[[AsyncSession, OffBoardSlugs, InsightsScope, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class InsightsAnswer:
    data: BaseModel
    next_cursor: str | None
    #: True when the tier's budget ended the answer before its lists did.
    shortened: bool


#: The closed-vocabulary input fields and the vocabulary each is read against.
_STRICT: dict[str, vocabulary.Kind] = {"family": "family", "company": "company", "location": "location"}


async def read(
    session: AsyncSession,
    operation: OperationDescriptor,
    params: BaseModel,
    *,
    workspace_id: str,
    figures: Figures,
    withheld: Collection[DataClass] = (),
    now: datetime | None = None,
) -> InsightsAnswer:
    """Answer one Insights operation from the dashboard's figures, with their
    coverage, within the tier's budget, without the `withheld` categories."""
    spec = READS[operation.id]
    params = await _strict(session, params)
    hidden = await off_board_company_slugs(session)
    scope = await resolve_insights_scope(session, getattr(params, "side", "all"), getattr(params, "family", None))
    raw = await figures(session, hidden, scope, params)
    if "private_pursuit" in withheld:
        for path in spec.pursuits:
            *parents, key = path.split(".")
            node = raw
            for step in parents:
                node = node[step]
            del node[key]
    companies = getattr(params, "company", None) or []
    coverage = await _coverage(
        session, spec, raw, hidden, scope, _companies_read(scope, companies),
        now or datetime.now(UTC), companies=companies, places=getattr(params, "location", None) or [],
    )
    answer = operation.result.model_validate({**raw, "coverage": coverage})
    return fit(spec, answer, params, workspace_id=workspace_id)


async def _strict(session: AsyncSession, params: BaseModel) -> BaseModel:
    """`params` with each closed-vocabulary value as the slug it names; an
    unknown value refuses the read with the lookup that lists the accepted ones."""
    unknown: list[vocabulary.Unknown] = []
    resolved: dict[str, list[str]] = {}
    for name, kind in _STRICT.items():
        given = getattr(params, name, None)
        if given:
            resolved[name] = vocabulary.resolve(await vocabulary.load(session, kind), given, unknown)
    vocabulary.refuse_unknown(unknown)
    return params.model_copy(update=resolved) if resolved else params


async def _coverage(
    session: AsyncSession,
    spec: InsightsRead,
    raw: dict[str, Any],
    hidden: OffBoardSlugs,
    scope: InsightsScope,
    read: InsightsScope,
    now: datetime,
    *,
    companies: list[str],
    places: list[str],
) -> InsightsCoverage:
    """The coverage of an answer over `scope`, its history and last read taken
    over `read`: the scope's companies, or the ones the figures were narrowed to."""
    reference = spec.population == "reference"
    history: CoverageHistory | None = None
    last_read_at: datetime | None = None
    if not reference:
        since = await history_since(session, read, hidden)
        history = CoverageHistory(since=since, days=history_days(since, now))
        read_by = [*read.company_conds(ScrapeSourceRun.company_slug)]
        if hidden:
            read_by.append(ScrapeSourceRun.company_slug.notin_(hidden))
        last_read_at = await session.scalar(select(func.max(ScrapeSourceRun.finished_at)).where(*read_by))
    return InsightsCoverage(
        population=spec.population,
        side=scope.side,
        families=list(scope.families),
        companies=companies,
        places=places,
        off_board_companies=None if reference else len(hidden),
        window=_window(spec.window, raw, now, history.since if history is not None else None),
        history=history,
        last_read_at=last_read_at,
    )


def _companies_read(scope: InsightsScope, companies: list[str] | None) -> InsightsScope:
    """`scope`'s companies narrowed to `companies`, when the figures were."""
    if not companies:
        return scope
    chosen = frozenset(companies)
    if scope.side == "other":
        chosen &= scope.other
    elif scope.side == "yours":
        chosen -= scope.other
    return InsightsScope("other", (), chosen)


def _window(
    source: WindowSource, raw: dict[str, Any], now: datetime, history_since: datetime | None
) -> CoverageWindow | None:
    if source == "figures":
        return CoverageWindow(days=raw["days"], since=raw["since"])
    if source == "axis":
        dates = raw["dates"]
        first = datetime.fromisoformat(dates[0]).replace(tzinfo=UTC) if dates else None
        return CoverageWindow(days=raw["days"], since=first)
    if source == "new_listing":
        start = now - NEW_LISTING_WINDOW
        return CoverageWindow(
            days=NEW_LISTING_WINDOW.days, since=None if history_since is None else max(start, history_since)
        )
    return None


# --- the budget ------------------------------------------------------------------ #


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _lists(data: dict[str, Any], path: str) -> list[list[Any]]:
    """Every list `path` names in `data`, in order."""
    nodes: list[Any] = [data]
    for step in path.split("."):
        nodes = [item for node in nodes for item in node] if step == "*" else [node[step] for node in nodes]
    return nodes


def fit(spec: InsightsRead, answer: BaseModel, params: BaseModel, *, workspace_id: str) -> InsightsAnswer:
    """`answer` within its tier's budget, from the cursor's position on.

    The paged lists are emptied and refilled in order from the position, item
    by item, while the answer, with the page block that says where it stops,
    still fits. An answer that cannot hold one item is refused, never cut."""
    if not spec.paged or not isinstance(params, _Paged):
        return InsightsAnswer(answer, None, False)
    tier = params.tier
    budget = BUDGET_BYTES[tier]
    request = cursor.fingerprint(
        spec.descriptor.id, workspace_id, params.model_dump(mode="json", exclude={"tier", "cursor"})
    )
    offset = cursor.decode(params.cursor, request=request)[0] if params.cursor is not None else 0

    data = answer.model_dump(mode="json")
    if offset == 0 and _size(data) <= budget:
        # Whole, it needs no page block, so none is reserved for.
        return InsightsAnswer(answer, None, False)
    slots = [items for path in spec.paged for items in _lists(data, path)]
    sequence = [(slot, item) for slot, items in enumerate(slots) for item in items]
    for items in slots:
        items.clear()
    total = len(sequence)
    if offset > total:
        raise OperationError(
            "invalid_input",
            "This cursor reads past the end of the answer. Read it again without a cursor.",
            details={"field": "cursor", "reason": "past_end"},
        )

    def page(start: int, end: int) -> InsightsPage | None:
        if start == 0 and end == total:
            return None
        follow = (
            [NextAction(operation=spec.descriptor.id, arguments={
                **params.model_dump(mode="json", exclude_defaults=True, exclude={"cursor"}),
                "cursor": cursor.encode(request=request, offset=end),
            })]
            if end < total else []
        )
        return InsightsPage(
            lists=list(spec.paged), offset=start, returned=end - start, total=total,
            tier=tier, budget_bytes=budget, continue_with=follow,
        )

    def filled(end: int) -> int:
        """The answer's size holding the items from `offset` to `end` and the
        page block that says so; `data` is left holding them."""
        for items in slots:
            items.clear()
        for slot, item in sequence[offset:end]:
            slots[slot].append(item)
        data["page"] = None if (block := page(offset, end)) is None else block.model_dump(mode="json")
        return _size(data)

    # Each item costs at most its bytes and a comma, so this bound on a page's
    # size finds where it stops without rebuilding the answer at every item.
    empty = filled(offset) - _size(data["page"])
    reach = [0]
    for _, item in sequence[offset:]:
        reach.append(reach[-1] + _size(item) + 1)

    def bound(end: int) -> int:
        block = page(offset, end)
        return empty + reach[end - offset] + (
            _size(block.model_dump(mode="json")) if block is not None else 4
        )

    # The rest whole needs no cursor, so it may fit where a shorter page would
    # not; short of that, the most items whose page still fits.
    end = total
    if filled(total) > budget:
        # Short of the end, the bound grows with every item (the block's
        # cursor and counts never shrink), so the last end within the budget
        # is found by halving, with a cursor encoded per step, not per item.
        low, high = offset, total - 1
        while low < high:
            middle = (low + high + 1) // 2
            if bound(middle) <= budget:
                low = middle
            else:
                high = middle - 1
        end = low
        # The bound counts a comma the first item of each list does not take,
        # so the next page may still fit: measured, it decides.
        while end + 1 < total and filled(end + 1) <= budget:
            end += 1
        if (end == offset and offset < total) or filled(end) > budget:
            raise OperationError(
                "invalid_input",
                "This answer does not fit the tier's budget even one item at a time; "
                "narrow it (a shorter window, fewer series) or ask with a larger tier.",
                details={"field": "tier", "reason": "over_budget", "budget_bytes": budget},
            )
    fitted = spec.descriptor.result.model_validate(data)
    next_cursor = cursor.encode(request=request, offset=end) if end < total else None
    return InsightsAnswer(fitted, next_cursor, shortened=end < total)

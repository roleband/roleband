"""Statistics + demand surfaces: KPIs, compensation, trends, velocity, rollups.

Every route declares its response: velocity with the models beside its handler, the
others in `api/schemas/statistics.py`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import cache

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from tracker.analytics.age_basis import employer_dated_share, employer_dated_sql
from tracker.analytics.comp_stats import (
    build_comp_stats,
    build_disclosure_rates,
    build_posted_pay,
    level_order,
)
from tracker.analytics.comp_trends import (
    DISCLOSURE_BASIS,
    build_comp_trend_series,
    build_disclosure_trend_series,
)
from tracker.analytics.hiring import build_hiring_places
from tracker.analytics.posting_reality import NEW_LISTING_WINDOW
from tracker.analytics.stock_trajectory import (
    TrajectoryRole,
    build_comp_trajectory,
    build_offer_terms,
)
from tracker.analytics.velocity import build_velocity
from tracker.api.comp_packages import role_packages
from tracker.api.deps import InsightsScopeDep, OffBoardDep, SessionDep, WindowDays
from tracker.api.errors import ErrorCode, api_error
from tracker.api.schemas.statistics import (
    CompensationStatsResponse,
    CompTrajectoryResponse,
    CompTrendsResponse,
    DemandResponse,
    DisclosureTrendsResponse,
    InsightsHistoryResponse,
    LevelGuideResponse,
    OfferTermsResponse,
    StatisticsOverviewResponse,
    StatsResponse,
)
from tracker.comp_providers.base import OUR_PAY_COUNTRY
from tracker.company_discovery import COMPANY_DISCOVERY
from tracker.config import get_settings
from tracker.db.models import (
    CompanyProfile,
    CompSnapshot,
    DisclosureSnapshot,
    Favorite,
    Job,
    JobLifecycleEvent,
    JobLineageLink,
    JobPlaceSetMember,
    JobTwinLink,
    Notification,
    SkillConcept,
)
from tracker.db.queries import motion
from tracker.db.queries.insights import history_days, history_since, window_since
from tracker.db.queries.jobs import (
    board_count_stmt,
    exclude_hidden,
    facet_count_stmt,
    insights_role_conds,
    new_listing_clause,
    open_in_scope_count_stmt,
    pair_on_board,
    place_set_later_ids,
)
from tracker.db.queries.scope import level_key_expr
from tracker.db.queries.skills import top_skills as read_top_skills
from tracker.enrich.enricher import ESTIMATE_FIELDS
from tracker.levels.companies import COMPANIES
from tracker.levels.ladder import flat_guide, level_guide, lineage
from tracker.levels.pay import PAY_POLICIES
from tracker.platform.util import local_day_start_utc
from tracker.plugins.registry import PAY_LEVELS, reader_providers
from tracker.plugins.status import reference_changes
from tracker.profiles import prices as price_store
from tracker.schema import OUR_ESTIMATE_SOURCE
from tracker.settings_store import get_enabled_bands, get_enabled_locations
from tracker.skills.analytics import COMPETENCY_CATEGORIES
from tracker.taxonomy.locations import country_code, pay_country
from tracker.taxonomy.tracks import TRACKS, allowed_bands_for

router = APIRouter()


@router.get("/api/stats", response_model=StatsResponse)
async def stats(session: SessionDep, hidden: OffBoardDep) -> dict:
    today = local_day_start_utc()
    # The three chips open Board views (`/`, the New and Reposted lenses), so
    # each counts through the Board's own filter with the params that view
    # sends: dismissed roles, hidden companies and scope drop out exactly as
    # they do from the list. The New lens is the rule each row lights by
    # (`new_listing_clause`).
    board = {"status": "open", "hidden": hidden}
    open_total = await session.scalar(board_count_stmt(board))
    new_today = await session.scalar(board_count_stmt({**board, "new_today_only": True}))
    reposted_today = await session.scalar(board_count_stmt({**board, "repost_today_only": True}))
    # Lifecycle events have no company column; scope them to non-hidden jobs.
    visible_job_ids = exclude_hidden(select(Job.id).where(Job.in_scope.is_(True)), hidden)
    closed_today = await session.scalar(
        select(func.count())
        .select_from(JobLifecycleEvent)
        .where(
            JobLifecycleEvent.event_type == "closed",
            JobLifecycleEvent.created_at >= today,
            JobLifecycleEvent.job_id.in_(visible_job_ids),
        )
    )
    # Open roles per company, a place set once: the same count as
    # `open_total`, split.
    by_company = (await session.execute(facet_count_stmt(Job.company, hidden))).all()
    saved_total = await session.scalar(select(func.count()).select_from(Favorite))
    # The review queue's own count: the pairs it lists, so the
    # badge and the queue it opens cannot disagree.
    review_pending = await session.scalar(
        select(func.count())
        .select_from(JobLineageLink)
        .where(
            JobLineageLink.status == "pending",
            JobLineageLink.confidence == "suspected",
            pair_on_board(JobLineageLink.job_id, JobLineageLink.prior_job_id, hidden),
        )
    )
    twin_review_pending = await session.scalar(
        select(func.count())
        .select_from(JobTwinLink)
        .where(
            JobTwinLink.status == "pending",
            JobTwinLink.confidence == "suspected",
            pair_on_board(JobTwinLink.job_a_id, JobTwinLink.job_b_id, hidden),
        )
    )
    notif_unread = await session.scalar(
        select(func.count()).where(
            Notification.dismissed_at.is_(None),
            Notification.read_at.is_(None),
        )
    )
    notif_high_unread = await session.scalar(
        select(func.count()).where(
            Notification.dismissed_at.is_(None),
            Notification.read_at.is_(None),
            Notification.priority == "high",
        )
    )
    return {
        "open_total": open_total or 0,
        "new_today": new_today or 0,
        "reposted_today": reposted_today or 0,
        "closed_today": closed_today or 0,
        "saved_total": saved_total or 0,
        "review_pending": (review_pending or 0) + (twin_review_pending or 0),
        "notif_unread": notif_unread or 0,
        "notif_high_unread": notif_high_unread or 0,
        "by_company": {c: n for c, n in by_company},
    }


@router.get("/api/statistics/overview", response_model=StatisticsOverviewResponse)
async def statistics_overview(
    session: SessionDep, hidden: OffBoardDep, scope: InsightsScopeDep, days: WindowDays = 30
) -> dict:
    """Cockpit aggregate for the Statistics landing tab.

    KPI tiles, a short generated brief and the top skills, pulling from the demand
    and skills layers. `days<=0` means all-time. The opened and closed counters
    start at `since`: the window's start, or the scope's history when that is
    shorter, so nothing found before the history is counted.
    """
    now = datetime.now(UTC)
    history = await history_since(session, scope, hidden)
    since = window_since(history, days, now)
    # The counters start where the figures say they do; before any whole read
    # there is no history, and what a partial read found is no opening.
    cutoff = since if history is not None else now

    open_total = await session.scalar(open_in_scope_count_stmt(hidden, *scope.conds()))
    companies = await session.scalar(
        exclude_hidden(
            select(func.count(func.distinct(Job.company))).where(
                Job.status == "open", Job.in_scope.is_(True), *scope.conds()
            ), hidden
        )
    )
    saved_total = await session.scalar(select(func.count()).select_from(Favorite))

    # Pace's openings and roles that came down (`db.queries.motion`), so the
    # two tabs say one number.
    postings = await motion.load(session, scope, hidden)
    opened = motion.openings(postings, cutoff)
    went = motion.came_down(postings, cutoff)
    new_count = sum(1 for o in opened if o.kind == "opened")
    already_listed_count = sum(1 for o in opened if o.kind == "already_listed")
    closed_count = len(went)

    # Top skills (distinct open jobs with a displayable requirement),
    # industries excluded (a vertical is not a skill).
    top_skills = [
        {"term": s["term"], "category": s["category"], "job_count": s["job_count"]}
        # Competencies apart: the most-named concepts are process,
        # leadership or collaboration, which would lead every Overview.
        for s in await read_top_skills(
            session, hidden, limit=5,
            narrowed=[*scope.conds(), SkillConcept.category.notin_(COMPETENCY_CATEGORIES)],
        )
    ]

    return {
        "days": days,
        "since": since,
        "kpis": {
            "open_total": open_total or 0,
            "new_count": new_count,
            "already_listed_count": already_listed_count,
            "closed_count": closed_count,
            "companies": companies or 0,
            "saved_total": saved_total or 0,
        },
        "top_skills": top_skills,
    }


@router.get("/api/statistics/compensation", response_model=CompensationStatsResponse)
async def statistics_compensation(session: SessionDep, hidden: OffBoardDep, narrowed: InsightsScopeDep) -> dict:
    """Compensation across the roles open now: the roles Insights describes.

    The quantities in this payload must not be conflated:

    * `posted` carries the ranges employers print in their postings, as yearly
      *base salary* per country and level (see `build_posted_pay`), with the
      person's levels so the screen can open on them. It leads the tab.
    * `overall` / `by_level` / `by_company` / `by_family` aggregate
      `Job.comp_median`, an *imputed total-comp estimate*: a lookup keyed by
      company and level, not anything an employer said, and only for US
      postings. Base pay and total comp cannot share an axis, so the UI keeps
      them in separate panels.
    * `disclosure` is the *rate* — how many open roles state pay at all, overall
      and per company/level. Basis-independent, and denominated in roles the
      disclosure pass has actually read (see `build_disclosure_rates`).

    Coverage is reported so the UI can state how much of the open set is estimated.

    No window. Keeping roles FIRST SEEN in the last N days would change the
    population, not the period: most open postings are first seen recently, so
    a 30-day window is nearly all-time and a 7-day one a sample of whatever was
    onboarded that week. The trend routes carry time.
    """
    # One predicate for every query below: filtering only some of them would mix
    # populations and silently misreport the coverage percentage.
    scope = [*insights_role_conds(), *narrowed.conds()]
    if hidden:
        scope.append(Job.company.notin_(hidden))

    total_open = await session.scalar(select(func.count()).where(*scope))
    # Every grouping by level reads the level key, never the stored band: a role
    # whose level we cannot place is `unstated`, not the Mid its sort default
    # says or the Senior/Staff a role word guessed.
    level = level_key_expr(Job).label("level")
    # The estimate is drawn in US dollars, the currency `stats` names. An
    # estimate in another currency (a plugin pricing non-US rungs) is not on
    # that axis, so it counts as unpriced here: nothing is converted.
    in_usd = Job.comp_currency == "USD"
    rows = (
        await session.execute(
            select(Job.company, Job.level_band, Job.family, case((in_usd, Job.comp_median)).label("comp_median"),
                   level).where(*scope)
        )
    ).all()

    stats = build_comp_stats([(r.company, r.level, r.family, r.comp_median) for r in rows], total_open or 0)

    # Roles our dataset prices by their base alone have no total, so the block
    # above cannot hold them; they are reported apart and labelled, never on
    # the totals' axis.
    base_rows = (
        await session.execute(
            select(Job.company, level, Job.family, Job.comp_base_median).where(
                *scope, in_usd, Job.comp_component == "base", Job.comp_median.is_(None),
                Job.comp_base_median.isnot(None),
            )
        )
    ).all()
    base = build_comp_stats([tuple(r) for r in base_rows], total_open or 0)
    stats["base_estimates"] = {
        "min_roles": base["min_roles"],
        "coverage": {"with_base": base["coverage"]["with_comp"], "total_open": base["coverage"]["total_open"]},
        "overall": base["overall"],
        "by_level": base["by_level"],
        "by_company": base["by_company"],
        "by_family": base["by_family"],
    }

    # What employers post: yearly base ranges per country and level, every
    # range counted, kept apart from the estimate above.
    posted_rows = (
        await session.execute(
            select(
                Job.company,
                level,
                Job.level_basis,
                Job.disclosed_base_min,
                Job.disclosed_base_max,
                Job.disclosed_pay_basis,
                Job.disclosed_currency,
                Job.disclosed_pay_period,
                Job.location_groups,
            ).where(*scope, Job.disclosed_base_min.isnot(None), Job.disclosed_base_max.isnot(None))
        )
    ).all()
    your_countries = {code for code in map(country_code, await get_enabled_locations(session)) if code}
    stats["posted"] = {
        **build_posted_pay([tuple(r) for r in posted_rows], your_countries=your_countries),
        "your_levels": sorted(await get_enabled_bands(session), key=level_order),
    }

    # Disclosure rate. Its own scan, unfiltered by `disclosed_base_min`: the rate's
    # denominator is every *checked* open role, so the roles that disclosed nothing
    # are exactly the rows that matter and the bands query above excludes them.
    rate_rows = (
        await session.execute(
            select(
                Job.company,
                level,
                Job.structured_at,
                Job.disclosed_base_min,
                Job.disclosed_base_max,
                Job.disclosed_pay_basis,
            ).where(*scope)
        )
    ).all()
    stats["disclosure"] = build_disclosure_rates([tuple(r) for r in rate_rows])

    stats["currency"] = "USD"
    return stats


#: The job columns a role's package reads (`api.comp_packages.role_package`).
_PACKAGE_COLUMNS = (
    Job.id, Job.company, Job.level_band, Job.level_basis, Job.family, Job.location_groups,
    *(getattr(Job, name) for name in ESTIMATE_FIELDS),
    Job.structured_at, Job.disclosed_base_min, Job.disclosed_base_max, Job.disclosed_currency,
    Job.disclosed_pay_basis, Job.disclosed_pay_period, Job.disclosed_snippet,
    Job.disclosed_source, Job.disclosed_confidence, Job.disclosed_bonus_pct,
)


async def _identity_profiles(session: AsyncSession) -> dict[str, dict]:
    """Each company's resolved identity: listed, ticker and equity vehicle."""
    rows = (
        await session.execute(
            select(
                CompanyProfile.slug,
                CompanyProfile.is_public,
                CompanyProfile.ticker,
                CompanyProfile.equity_vehicle,
            )
        )
    ).all()
    return {
        r.slug: {"is_public": r.is_public, "ticker": r.ticker, "equity_vehicle": r.equity_vehicle}
        for r in rows
    }


@router.get("/api/statistics/comp-trajectory", response_model=CompTrajectoryResponse)
async def statistics_comp_trajectory(session: SessionDep, hidden: OffBoardDep) -> dict:
    """Each company's typical package for the Stock tab, from the packages Job
    detail shows, so a role reads the same on both screens.

    Companies split into public (equity tracks a listed ticker, so it flexes
    with the stock price), private, and those where each person picks the cash
    and stock mix. The UI applies a stock-price scenario to the equity part
    client-side. The roles `/api/statistics/compensation` describes: a place set once.
    """
    jobs = (
        await session.scalars(
            exclude_hidden(
                select(Job).options(load_only(*_PACKAGE_COLUMNS)).where(*insights_role_conds()),
                hidden,
            ).order_by(Job.id)
        )
    ).all()
    providers = await reader_providers(session)
    packages = await role_packages(session, jobs, providers)

    # Resolved identity beats the hardcoded PUBLIC_TICKERS table, which cannot
    # know about a company that listed later.
    profiles = await _identity_profiles(session)
    return build_comp_trajectory(
        (
            TrajectoryRole(
                company=job.company,
                band=job.level_band,
                package=package,
                us_pay=pay_country(job.location_groups) == OUR_PAY_COUNTRY,
            )
            for job, package in packages
        ),
        profiles=profiles,
    )


@router.get("/api/statistics/offer-terms", response_model=OfferTermsResponse)
async def statistics_offer_terms(session: SessionDep) -> dict:
    """The terms the Stock tab's offer calculator fills in when a company is
    picked: every company whose offer rules the atlas records, and every listed
    company. The calculator itself runs in the browser; nothing the person types
    is sent here.

    A stored quote rides along only while a price key is saved. This reads the
    quotes the prices job already stored and never asks the feed for one.
    """
    profiles = await _identity_profiles(session)
    feed_configured = (await price_store.api_key(session, get_settings()))[0] is not None
    companies = set(PAY_POLICIES) | {
        slug for slug, p in profiles.items() if p["is_public"] and p["ticker"]
    }
    quotes = await price_store.latest_price_map(session) if feed_configured else {}
    return {
        "feed_configured": feed_configured,
        "companies": build_offer_terms(companies, profiles=profiles, quotes=quotes),
    }


@cache
def _level_guide() -> dict:
    """The level guide is the pinned atlas and the code's catalog, both fixed
    for the life of the process, so it is built once."""
    guided = sorted(slug for slug, record in COMPANIES.items() if any(ladder.guide for ladder in record.ladders))
    known = set(guided)
    return {
        "companies": [{"slug": slug, "flat": flat_guide(slug), "levels": level_guide(slug)} for slug in guided],
        "unguided": [
            {"slug": slug, "same_as": next((up for up in lineage(slug)[1:] if up in known), None)}
            for slug in sorted(COMPANY_DISCOVERY) if slug not in known
        ],
        "tracks": {track.slug: allowed_bands_for(track.slug) for track in TRACKS},
    }


@router.get("/api/statistics/levels", response_model=LevelGuideResponse, response_model_exclude_unset=True)
async def statistics_levels() -> dict:
    """How every company with a reviewed ladder names each level, followed or
    not, for the Levels tab. Reference data: it reads no postings, so the
    Insights scope and window do not apply. Who is followed comes from
    `/api/companies/discovery`, which the screen already reads."""
    return _level_guide()


@router.get("/api/statistics/comp-trends", response_model=CompTrendsResponse)
async def statistics_comp_trends(
    session: SessionDep, hidden: OffBoardDep, scope: InsightsScopeDep, dim: str = "overall", days: WindowDays = 90
) -> dict:
    """Compensation percentiles over time from the `comp_snapshot` raw daily values.

    `dim` selects the grouping (`overall`/`company`/`level`/`family`); returns a
    shared sorted `dates` axis + one aligned `series` per key with `{date, p25, p50,
    p75, p90}` points (null-filled on days with no slice). `days<=0` = all history.

    Percentiles are recomputed here from the raw values of the *visible* companies,
    so hiding a company retroactively and exactly removes it from every point in the
    series (impossible from `comp_metrics`, whose stored percentiles can't be
    re-aggregated). History accrues one snapshot-set per pipeline run.
    """
    if dim not in ("overall", "company", "level", "family"):
        raise api_error(400, ErrorCode.INVALID_INPUT, "invalid dim")

    cutoff = None if days <= 0 else (
        datetime.now(UTC) - timedelta(days=days)
    ).replace(hour=0, minute=0, second=0, microsecond=0)

    # The series of the source answering pay: ours, or the plugin's
    # while it is selected; never a day written before sources were kept apart.
    shown = (await reader_providers(session)).source_for(PAY_LEVELS) or OUR_ESTIMATE_SOURCE
    stmt = select(CompSnapshot).where(CompSnapshot.source == shown)
    if cutoff is not None:
        stmt = stmt.where(CompSnapshot.metric_date >= cutoff)
    if hidden:
        stmt = stmt.where(CompSnapshot.company.notin_(hidden))
    stmt = stmt.where(*scope.conds(company=CompSnapshot.company, family=CompSnapshot.family))
    snapshots = (await session.scalars(stmt)).all()

    built = build_comp_trend_series(
        (
            (
                row.metric_date.date().isoformat(),
                row.company,
                row.level_band,
                row.family,
                row.comp_values,
            )
            for row in snapshots
        ),
        dim,
    )

    # Each series is its key; the client names it by `dim`.
    return {
        "dim": dim, "days": days, "dates": built["axis"], "series": built["series"],
        "reference_changes": await reference_changes(session, cutoff),
    }


@router.get("/api/statistics/disclosure-trends", response_model=DisclosureTrendsResponse)
async def statistics_disclosure_trends(
    session: SessionDep, hidden: OffBoardDep, scope: InsightsScopeDep, dim: str = "overall", days: WindowDays = 90
) -> dict:
    """Pay transparency over time from the `disclosure_snapshot` daily cells.

    `dim` selects the grouping (`overall`/`company`/`level`); returns a shared
    sorted `dates` axis + one aligned `series` per key. Each point carries both
    quantities the snapshot separates:

    * `rate` = `disclosed / checked` — the share of read open roles stating a pay
      band. Basis-independent; `open - checked` is reported so the UI can show the
      extraction backlog instead of counting it as employer silence.
    * `low_p50` / `high_p50` — the median published band, pooled strictly within
      `basis` (base salary). One vote per distinct band, since an employer hangs
      many reqs off one band.

    Counts are re-summed here from the raw cells rather than read as stored
    aggregates, so hiding a company retroactively and exactly removes it from
    every point in the series — the same property `comp-trends` relies on.
    """
    if dim not in ("overall", "company", "level"):
        raise api_error(400, ErrorCode.INVALID_INPUT, "invalid dim")

    cutoff = None if days <= 0 else (
        datetime.now(UTC) - timedelta(days=days)
    ).replace(hour=0, minute=0, second=0, microsecond=0)

    # Columns, not entities: the window holds a cell per company, level and
    # basis each day, and building an object per cell costs more than the query.
    stmt = select(
        DisclosureSnapshot.metric_date,
        DisclosureSnapshot.company,
        DisclosureSnapshot.level_band,
        DisclosureSnapshot.pay_basis,
        DisclosureSnapshot.roles,
        DisclosureSnapshot.checked,
        DisclosureSnapshot.bands,
    )
    if cutoff is not None:
        stmt = stmt.where(DisclosureSnapshot.metric_date >= cutoff)
    if hidden:
        stmt = stmt.where(DisclosureSnapshot.company.notin_(hidden))
    # The snapshot has no family column: the disciplines half of the scope
    # cannot apply, and the UI says so beside the chart.
    stmt = stmt.where(*scope.company_conds(DisclosureSnapshot.company))
    cells = (await session.execute(stmt)).all()

    built = build_disclosure_trend_series(
        ((metric_date.date().isoformat(), *cell) for metric_date, *cell in cells), dim
    )

    # Each series is its key ("cohort", "overall", a company or a level); the
    # client names it.
    series = built["series"]
    return {
        "dim": dim,
        "days": days,
        "basis": DISCLOSURE_BASIS,
        "dates": built["axis"],
        "series": series,
        "cohort": built["cohort"],
    }


class VelocityKpis(BaseModel):
    """Window totals."""

    open_total: int
    opened: int
    closed: int
    reposted: int
    #: Roles first seen in the window that were already listed when found: a
    #: company's first read, or a posting the employer dated earlier. Never in
    #: `opened`.
    already_listed: int
    median_days_open: float | None
    #: Open roles whose start is unknown (`analytics.age_basis`): outside
    #: `median_days_open` and `aging`, so `aging` plus this is `open_total`.
    age_unknown: int
    #: Share of the open roles behind `median_days_open` and `aging` that the
    #: employer dated (`analytics.age_basis`); None when there are none.
    employer_dated_share: float | None
    median_observed_listing_duration_days: float | None
    #: Roles that came down with a known time posted: `closed_sample` plus
    #: `closed_unknown` is `closed`.
    closed_sample: int
    closed_unknown: int
    #: The same share over the `closed_sample` roles behind the duration.
    closed_employer_dated_share: float | None


class VelocityAgingBand(BaseModel):
    """A fixed age band (`analytics.velocity.AGING_BANDS`); the client names it
    by `lo`."""

    lo: int
    hi: int | None
    count: int


class VelocityCompany(BaseModel):
    company: str
    open: int
    opened: int
    closed: int
    reposted: int
    median_days_open: float | None
    median_observed_listing_duration_days: float | None


class VelocityOut(BaseModel):
    days: int
    #: Where the figures start: the window's start, or the scope's history when
    #: that is shorter (`queries.insights.window_since`). None before any whole read.
    since: datetime | None
    kpis: VelocityKpis
    aging: list[VelocityAgingBand]
    #: How long the roles that came down in the window were posted, on the
    #: aging bands (never a time to hire).
    posted: list[VelocityAgingBand]
    by_company: list[VelocityCompany]


@router.get("/api/statistics/velocity", response_model=VelocityOut)
async def statistics_velocity(
    session: SessionDep, hidden: OffBoardDep, scope: InsightsScopeDep, days: WindowDays = 30
) -> dict:
    """Hiring-velocity motion over a time window (honors the period lens).

    The roles that opened and came down in the window, each once
    (`db.queries.motion`), the ages of the roles still open, and how long the
    roles that came down had been posted. `days<=0` means all-time. The
    duration needs a spread of roles that came down, so it accrues with
    history; the UI flags a thin sample.

    It is not a time to fill: it measures how long a posting was advertised,
    and a public board says nothing about whether anyone was hired.
    """
    now = datetime.now(UTC)
    history = await history_since(session, scope, hidden)
    since = window_since(history, days, now)
    # The counters start where the figures say they do; before any whole read
    # there is no history, and what a partial read found is no opening.
    cutoff = since if history is not None else now
    open_total = await session.scalar(open_in_scope_count_stmt(hidden, *scope.conds()))
    postings = await motion.load(session, scope, hidden)
    ages = motion.open_ages(postings, now)
    opened = motion.openings(postings, cutoff)
    went = motion.came_down(postings, cutoff)
    return {
        **build_velocity(
            [(a.company, a.days, a.employer_dated) for a in ages],
            [(o.company, o.kind) for o in opened],
            [(c.company, c.days, c.employer_dated) for c in went],
            open_total or 0,
            days,
        ),
        "since": since,
    }


@router.get("/api/statistics/history", response_model=InsightsHistoryResponse)
async def statistics_history(session: SessionDep, hidden: OffBoardDep, scope: InsightsScopeDep) -> dict:
    """How much history the scope's companies have: when it starts and how
    many whole days it covers. A window longer than it shows the same figures as
    all time, so the dashboard offers only the windows it covers."""
    since = await history_since(session, scope, hidden)
    return {"since": since, "days": history_days(since, datetime.now(UTC))}


@router.get("/api/demand", response_model=DemandResponse)
async def demand(session: SessionDep, hidden: OffBoardDep, scope: InsightsScopeDep) -> dict:
    """The Hiring tab: where the roles Insights describes are open now.

    Read live, a place set once, never by summing `demand_metrics`: a rollup
    slice counts a POSTING once per location group, nested and region-expanded,
    so a role listed at many places reads as hundreds. The rollup stays the longitudinal record its post pass writes."""
    # Every open, in-scope posting with its place set, so a set's role carries
    # the places of all its members (the Board's place facet) and
    # counts once.
    member_rows = (
        await session.execute(
            exclude_hidden(
                select(Job.id, Job.company, Job.locations, JobPlaceSetMember.set_id)
                .outerjoin(
                    JobPlaceSetMember,
                    (JobPlaceSetMember.job_id == Job.id) & (JobPlaceSetMember.status == "auto"),
                )
                .where(Job.status == "open", Job.in_scope.is_(True), *scope.conds()),
                hidden,
            )
        )
    ).all()
    roles: dict[tuple[str, int], tuple[str, list[str]]] = {}
    for job_id, company, locations, set_id in member_rows:
        key = ("set", set_id) if set_id is not None else ("job", job_id)
        roles.setdefault(key, (company, []))[1].extend(locations or [])
    open_by_company: dict[str, int] = {}
    for company, _ in roles.values():
        open_by_company[company] = open_by_company.get(company, 0) + 1

    # The motion over one period, the New rule's: roles new by the Board's rule
    # (not reposts) and roles that came down in the same 2 days, each once
    # (`db.queries.motion`), so the two numbers side by side describe one
    # stretch of time. Not for me stays in: Insights is the market.
    now = datetime.now(UTC)
    later = place_set_later_ids()
    new_rows = (
        await session.execute(
            exclude_hidden(
                select(Job.company, func.count()).where(
                    new_listing_clause(now=now),
                    Job.in_scope.is_(True),
                    Job.id.notin_(later),
                    *scope.conds(),
                ),
                hidden,
            ).group_by(Job.company)
        )
    ).all()
    new = dict(new_rows)
    closed = motion.per_company(motion.came_down(await motion.load(session, scope, hidden), now - NEW_LISTING_WINDOW))
    companies = sorted(
        (
            {
                "company": company,
                "open": open_by_company.get(company, 0),
                "new": int(new.get(company, 0)),
                "closed": int(closed.get(company, 0)),
            }
            for company in set(open_by_company) | set(new) | set(closed)
        ),
        key=lambda c: (-c["open"], -c["new"], c["company"]),
    )

    open_count, dated_count = (
        await session.execute(
            exclude_hidden(
                select(
                    func.count(),
                    func.count().filter(text(employer_dated_sql("jobs."))),
                ).select_from(Job).where(*insights_role_conds(), *scope.conds()),
                hidden,
            )
        )
    ).one()
    places = build_hiring_places(locations for _, locations in roles.values())
    return {
        "open_total": len(roles),
        "new": sum(new.values()),
        "closed": sum(closed.values()),
        "companies": companies,
        "regions": places["regions"],
        "unplaced": places["unplaced"],
        "employer_dated_share": employer_dated_share(dated_count, open_count),
    }

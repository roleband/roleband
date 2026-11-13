"""The statistics and demand routes' response contract.

`tracker/api/schemas/statistics.py` declares what `/api/stats`, the Statistics
overview, compensation, stock trajectory, both trends and
`/api/demand` send. These tests hold it to its sources:

1. **Vocabularies**: trend dimensions against what each handler accepts; part
   sources and set-apart reasons against `analytics`; the pooled basis.
2. **An empty radar**: every route answers its empty shape.
3. **Each route over real HTTP** against `tests/statistics_contract_seed.py`: the
   populations each counts (open, in scope, visible, inside the window), today's
   new and reposted roles kept apart, the estimate kept apart from printed bands,
   the rate denominated in roles read, packages that sum, series recomputed
   from visible raw values, and the demand lists.
4. **Hiding a company** removes it from every route.
5. **Drift**: a builder that adds, drops or mistypes a key fails the response.

`pin_statistics_clock` fixes "now" and the user's day start; `no_escape` guards
every test.
"""

from __future__ import annotations

from datetime import timedelta
from typing import get_args

import pytest
import pytest_asyncio
from fastapi.exceptions import ResponseValidationError
from pydantic import BaseModel
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_errors import said
from tests.factories import make_company
from tests.statistics_contract_seed import (
    DAY_START,
    NOW,
    SeededStatistics,
    _role,
    _skill,
    _stated,
    pin_statistics_clock,
    seed_statistics,
)
from tracker.analytics import comp_package, comp_trends, stock_trajectory
from tracker.analytics.comp_trends import DISCLOSURE_BASIS
from tracker.api.routers import statistics as router
from tracker.api.schemas import statistics as contract
from tracker.company_directory import FOLLOWED_WITH_SET
from tracker.db.models import (
    CompSnapshot,
    DisclosureSnapshot,
    Job,
    JobCompEstimate,
    JobFeedback,
    JobLifecycleEvent,
    JobPlaceSet,
    JobPlaceSetMember,
    ScrapeRun,
    SkillConcept,
    SkillDemandDaily,
    TrackedCompany,
)
from tracker.settings_store import set_enabled_bands, set_enabled_locations
from tracker.skills.analytics import compute_skill_demand

ROUTES = {
    "stats": "/api/stats",
    "overview": "/api/statistics/overview",
    "compensation": "/api/statistics/compensation",
    "trajectory": "/api/statistics/comp-trajectory",
    "comp_trends": "/api/statistics/comp-trends",
    "disclosure_trends": "/api/statistics/disclosure-trends",
    "demand": "/api/demand",
}
# Reference data, not roles: no scope, window or hidden company narrows it.
REFERENCE_ROUTES = {"offer_terms": "/api/statistics/offer-terms"}


@pytest_asyncio.fixture
async def clock(monkeypatch, no_escape):
    pin_statistics_clock(monkeypatch)


@pytest_asyncio.fixture
async def seeded(api_client, db_session, clock) -> SeededStatistics:
    return await seed_statistics(db_session)


def _fields(model) -> list[str]:
    return list(model.model_fields)


async def _get(api_client, path: str, status: int = 200) -> dict:
    response = await api_client.get(path)
    assert response.status_code == status, response.text
    return response.json()


def _day(days_before_today: int) -> str:
    return (DAY_START - timedelta(days=days_before_today)).date().isoformat()


# --------------------------------------------------------------------------- #
# 1. Vocabularies
# --------------------------------------------------------------------------- #


def test_each_literal_is_the_vocabulary_it_mirrors():
    assert set(get_args(contract.PartSource)) == {
        stock_trajectory.FROM_POSTED, stock_trajectory.FROM_COMPANY_RULE, stock_trajectory.FROM_MEASURED,
        stock_trajectory.FROM_ESTIMATED, stock_trajectory.FROM_MIXED,
    }
    # Every reason a package is not split, except the cash election, which has a row of its own.
    refusals = {v for k, v in vars(comp_package).items() if k.startswith("NO_SPLIT_")}
    assert set(get_args(contract.SetApartReason)) == (
        refusals - {comp_package.NO_SPLIT_EMPLOYEE_ELECTION} | {stock_trajectory.SET_APART_BASE_ONLY}
    )
    assert get_args(contract.DisclosureTrendsResponse.model_fields["basis"].annotation) == (DISCLOSURE_BASIS,)


def test_every_shape_forbids_a_key_its_model_does_not_name():
    built = [
        model for model in vars(contract).values()
        if isinstance(model, type) and issubclass(model, BaseModel) and model.__module__ == contract.__name__
    ]
    assert len(built) >= 40
    assert [m.__name__ for m in built if m.model_config.get("extra") != "forbid"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "dims", "refused"),
    [
        ("comp_trends", get_args(contract.CompTrendDim), "bogus"),
        ("disclosure_trends", get_args(contract.DisclosureTrendDim), "family"),
    ],
    ids=["comp", "disclosure"],
)
async def test_a_trend_accepts_exactly_its_dimensions(api_client, seeded, route, dims, refused):
    for dim in dims:
        assert (await _get(api_client, f"{ROUTES[route]}?dim={dim}"))["dim"] == dim
    assert said(await _get(api_client, f"{ROUTES[route]}?dim={refused}", status=400)) == {"detail": "invalid dim"}


# --------------------------------------------------------------------------- #
# 2. An empty radar
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_an_empty_radar_answers_every_shape_with_nothing_in_it(api_client, clock):
    assert await _get(api_client, ROUTES["stats"]) == {
        "open_total": 0, "new_today": 0, "reposted_today": 0, "closed_today": 0, "saved_total": 0,
        "review_pending": 0, "notif_unread": 0, "notif_high_unread": 0, "by_company": {},
    }
    overview = await _get(api_client, ROUTES["overview"])
    assert overview["top_skills"] == []
    compensation = await _get(api_client, ROUTES["compensation"])
    assert (compensation["overall"], compensation["coverage"]) == (None, {"with_comp": 0, "total_open": 0, "pct": 0.0})
    # No range: every country listed is one of the person's places, with nothing in it.
    assert all(c["ranges"] == 0 and c["yours"] and c["bands"] == [] for c in compensation["posted"]["countries"])
    assert compensation["disclosure"]["overall"] == {"open": 0, "checked": 0, "disclosed": 0, "rate": None}
    trajectory = await _get(api_client, ROUTES["trajectory"])
    assert (trajectory["overall"], trajectory["public"], trajectory["private"]) == (None, [], [])
    assert (await _get(api_client, ROUTES["comp_trends"]))["series"] == []
    assert (await _get(api_client, ROUTES["disclosure_trends"]))["dates"] == []
    assert await _get(api_client, ROUTES["demand"]) == {
        "open_total": 0, "new": 0, "closed": 0, "companies": [], "regions": [], "unplaced": 0,
        "employer_dated_share": None,
    }
    assert await _get(api_client, "/api/statistics/history") == {"since": None, "days": 0}


# --------------------------------------------------------------------------- #
# 3. Each route
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_header_counts_today_apart_from_reposts_and_counts_only_visible_open_roles(api_client, seeded):
    body = await _get(api_client, ROUTES["stats"])
    assert list(body) == _fields(contract.StatsResponse)
    assert body == {
        "open_total": 27,  # 21 google, 3 openai, 1 netflix, 2 stripe; the hidden, closed and out-of-scope never
        "new_today": 3,  # openai's original and both stripe roles; not the repost, the hidden role or older roles
        "reposted_today": 1,
        "closed_today": 1,
        "saved_total": 2,
        "review_pending": 2,  # the suspected repost and the suspected twin pair; not the auto link
        "notif_unread": 2,  # neither the read nor the dismissed one
        "notif_high_unread": 1,  # one high unread; the read and the dismissed high ones are not
        "by_company": {"google": 21, "netflix": 1, "openai": 3, "stripe": 2},
    }


@pytest.mark.asyncio
async def test_the_overview_scopes_openings_to_its_window_and_names_the_leaders(api_client, seeded):
    body = await _get(api_client, ROUTES["overview"])
    assert list(body) == _fields(contract.StatisticsOverviewResponse)
    assert body["kpis"] == {
        # Every original role first seen in the 30 days that was new when
        # found; `g-closed`, at the window's edge, carried an employer date 10
        # days older than our first sighting, so it was already listed.
        "open_total": 27, "new_count": 24, "already_listed_count": 1, "closed_count": 1, "companies": 4, "saved_total": 2,
    }
    # Skills from evidence-grounded requirements; an industry is never a skill.
    assert body["top_skills"] == [
        {"term": "python", "category": "language", "job_count": 17},
        {"term": "sql", "category": "language", "job_count": 3},
    ]
    # No role list: a role's age answers nothing on Overview
    # (docs/decisions/0004-insights-answers-a-question.md).
    assert "longest_open" not in body
    # The dashboard builds the brief from these facts
    # (`statistics/names.test.ts`); the response carries no English brief.
    assert "brief" not in body
    all_time = await _get(api_client, f"{ROUTES['overview']}?days=0")
    # `g-senior` joins; `o-old`, dated by its employer 75 days before we saw
    # it, was already listed; the repost is never new (as Pace and the header).
    assert (all_time["days"], all_time["kpis"]["new_count"], all_time["kpis"]["already_listed_count"]) == (0, 25, 2)


@pytest.mark.asyncio
async def test_compensation_keeps_the_estimate_apart_from_printed_bands_over_the_roles_open_now(api_client, seeded):
    body = await _get(api_client, ROUTES["compensation"])
    assert list(body) == _fields(contract.CompensationStatsResponse)
    # Every open role, whenever we first saw it: `g-senior` (60 days) and
    # `o-old` (45) are in. A window that kept only roles FIRST SEEN in it would
    # change the population, not the period. Stripe carries no estimate.
    assert body["coverage"] == {"with_comp": 25, "total_open": 27, "pct": 0.926}
    assert (body["overall"]["count"], body["overall"]["min"], body["overall"]["max"]) == (25, 380000, 907556)
    assert all(isinstance(body["overall"][p], float) for p in ("p25", "p50", "p75", "p90"))
    # A group needs `min_roles` priced roles: netflix (1) and openai (3)
    # must not rank first and second on one and three lookups.
    assert body["min_roles"] == 5
    assert [row["level_band"] for row in body["by_level"]] == ["senior", "staff"]
    assert [row["company"] for row in body["by_company"]] == ["google"]
    assert [row["family"] for row in body["by_family"]] == ["product_management"]
    assert all(row["count"] >= 5 for key in ("by_level", "by_company", "by_family") for row in body[key])
    assert all(list(row) == _fields(contract.CompFamilySummary) for row in body["by_family"])
    # No dollar premium per skill: an employer sets a range per level and
    # place, not per skill, so a premium would only name who asks for it.
    assert "by_skill" not in body and "histogram" not in body

    # One range per distinct print, with the roles on it; what is not yearly
    # base pay is counted, not dropped. `g-senior`'s range is in: it is open,
    # however long ago we first saw it.
    posted = body["posted"]
    us = next(c for c in posted["countries"] if c["country"] == "US")
    assert (posted["default_country"], us["currency"], us["ranges"]) == ("US", "USD", 3)
    assert us["bands"] == [
        {"company": "google", "level_band": "senior", "low": 200000, "high": 260000, "reqs": 1},
        {"company": "google", "level_band": "staff", "low": 250000, "high": 320000, "reqs": 2},
        {"company": "google", "level_band": "principal", "low": 340000, "high": 450000, "reqs": 1},
    ]
    # One employer is one ladder, not a market: every level is counted and none shows a figure.
    assert [(lv["level_band"], lv["ranges"], lv["employers"], lv["roles"], lv["enough"], lv["low"])
            for lv in us["levels"]] == [
        ("senior", 1, 1, 1, False, None), ("staff", 1, 1, 2, False, None), ("principal", 1, 1, 1, False, None),
    ]
    assert (posted["min_employers"], posted["min_ranges"]) == (5, 8)
    # The total and the unclear range are not base; the hourly one is pay, just
    # not yearly; only the placeholder is no salary.
    assert posted["excluded"] == {
        "not_base": 2, "not_yearly": 1, "implausible": 1, "no_country": 0, "placed_by_pay": 0, "without_country": 0,
    }
    assert list(posted) == _fields(contract.PostedPay)
    # The rate is denominated in roles the disclosure pass has read: `o-old` was never read.
    assert body["disclosure"]["overall"] == {"open": 27, "checked": 9, "disclosed": 8, "rate": 0.8889}
    rates = {row["company"]: row for row in body["disclosure"]["by_company"]}
    assert {c: (r["checked"], r["disclosed"], r["rate"]) for c, r in rates.items()} == {
        "google": (6, 6, 1.0), "openai": (1, 1, 1.0), "netflix": (1, 1, 1.0), "stripe": (1, 0, 0.0),
    }
    assert body["disclosure"]["by_company"][-1]["company"] == "stripe"
    assert body["currency"] == "USD"
    # The Window lens is not this route's: a stray `days` changes nothing.
    assert await _get(api_client, f"{ROUTES['compensation']}?days=7") == body


@pytest.mark.asyncio
async def test_posted_pay_opens_on_the_persons_levels_and_lists_their_countries(api_client, db_session, seeded):
    """The person's levels come in seniority order, whatever order they were
    saved in, and a country of theirs with no posted range is still listed, so
    the screen can say so rather than hide it."""
    await set_enabled_bands(db_session, ["director_plus", "principal"])
    await set_enabled_locations(db_session, ["silicon_valley", "sweden"])
    await db_session.commit()
    posted = (await _get(api_client, ROUTES["compensation"]))["posted"]
    assert posted["your_levels"] == ["principal", "director_plus"]
    assert [(c["country"], c["ranges"], c["yours"]) for c in posted["countries"]] == [("US", 3, True), ("SE", 0, True)]


@pytest.mark.asyncio
async def test_a_role_whose_level_we_cannot_place_never_counts_under_a_level_on_pay(api_client, db_session, seeded):
    # A bare title is stored at Mid for sorting and a role-word title
    # at the band its word guessed. Grouped by that band, bare
    # titles would make a "Mid-level" row of published pay above Senior.
    before = await _get(api_client, ROUTES["compensation"])
    bare = [
        _role("google", f"bare-{i}", level="mid", comp=640000, level_basis="none", title="Product Manager, Ads",
              **(_stated(260000, 350000) if i == 0 else {}))
        for i in range(5)
    ]
    guess = _role("google", "guess", level="senior", comp=640000, level_basis="unmapped",
                  title="Product Manager, Search", **_stated(180000, 295000))
    db_session.add_all([*bare, guess])
    await db_session.flush()
    # Our own estimate beside each job's copy: what the daily rollup reads.
    db_session.add_all([JobCompEstimate(job_id=job.id, source="roleband", comp_median=job.comp_median)
                        for job in (*bare, guess)])
    await db_session.commit()

    body = await _get(api_client, ROUTES["compensation"])
    # The estimate by level is unchanged: no Mid-level row of bare titles, no
    # Senior pulled by a guess, and no row restating a guessed lookup.
    assert body["by_level"] == before["by_level"]
    # Posted ranges at unplaced roles are counted apart, never inside a level.
    us, us_before = (next(c for c in b["posted"]["countries"] if c["country"] == "US") for b in (body, before))
    assert (us["bands"], us["levels"]) == (us_before["bands"], us_before["levels"])
    assert us["not_placed"] == {"roles": 2, "ranges": 2}
    # Rates keep each level separate and count unplaced roles once, in the last row.
    rates = body["disclosure"]["by_level"]
    assert rates[:-1] == before["disclosure"]["by_level"]
    assert rates[-1] == {"level_band": "unstated", "open": 6, "checked": 2, "disclosed": 2, "rate": 1.0}

    # The daily rollups the trends read store the same key.
    await comp_trends.compute_comp_metrics(db_session)
    await comp_trends.compute_disclosure_metrics(db_session)
    await db_session.commit()
    comp_keys = set((await db_session.scalars(select(CompSnapshot.level_band).where(
        CompSnapshot.company == "google", CompSnapshot.metric_date >= DAY_START))).all())
    cell_keys = set((await db_session.scalars(select(DisclosureSnapshot.level_band).where(
        DisclosureSnapshot.company == "google", DisclosureSnapshot.metric_date >= DAY_START))).all())
    assert "unstated" in comp_keys and "unstated" in cell_keys
    assert "mid" not in comp_keys | cell_keys


@pytest.mark.asyncio
async def test_pay_in_another_currency_stays_off_the_dollar_axes_and_is_counted(api_client, db_session, seeded):
    # The panel and both trends draw US dollars. A London role with a pound band
    # and a pound estimate clears every size floor, so only its currency keeps it
    # off those axes; it still counts as open, read and disclosed.
    before = await _get(api_client, ROUTES["compensation"])
    london = _role("google", "london", level="staff", comp=180000, comp_currency="GBP", locations=["London, UK"],
                   location_groups=["london"], **{**_stated(150000, 210000), "disclosed_currency": "GBP"})
    db_session.add(london)
    await db_session.flush()
    # The daily rollup reads each job's own estimate rows: one in pounds, one in dollars beside it.
    db_session.add_all([
        JobCompEstimate(job_id=london.id, source="roleband", comp_median=180000, comp_currency="GBP"),
        JobCompEstimate(job_id=seeded.ids["g-staff"], source="roleband", comp_median=594000),
    ])
    await db_session.commit()

    body = await _get(api_client, ROUTES["compensation"])
    assert body["overall"] == before["overall"]
    assert body["by_level"] == before["by_level"]
    assert body["coverage"]["with_comp"] == before["coverage"]["with_comp"]
    assert body["coverage"]["total_open"] == before["coverage"]["total_open"] + 1
    # Posted pay keeps the pound range in the UK, in pounds, and the US figures as they were.
    countries = {c["country"]: c for c in body["posted"]["countries"]}
    before_us = next(c for c in before["posted"]["countries"] if c["country"] == "US")
    assert countries["US"] == before_us
    assert (countries["GB"]["currency"], countries["GB"]["bands"]) == (
        "GBP", [{"company": "google", "level_band": "staff", "low": 150000, "high": 210000, "reqs": 1}],
    )
    assert body["disclosure"]["overall"]["disclosed"] == before["disclosure"]["overall"]["disclosed"] + 1

    await comp_trends.compute_comp_metrics(db_session)
    await comp_trends.compute_disclosure_metrics(db_session)
    await db_session.commit()
    values = (await db_session.scalars(select(CompSnapshot.comp_values).where(
        CompSnapshot.company == "google", CompSnapshot.level_band == "staff", CompSnapshot.metric_date >= DAY_START,
    ))).all()
    assert [v for vs in values for v in vs] == [594000]
    cell = (await db_session.scalars(select(DisclosureSnapshot).where(
        DisclosureSnapshot.company == "google", DisclosureSnapshot.level_band == "staff",
        DisclosureSnapshot.pay_basis == "base", DisclosureSnapshot.metric_date >= DAY_START,
    ))).one()
    assert cell.bands == [{"low": 250000, "high": 320000, "reqs": 2}]
    assert cell.roles == 3


@pytest.mark.asyncio
async def test_a_dollar_estimate_for_pay_outside_the_us_stays_off_the_us_estimate(api_client, db_session, seeded):
    # The estimate panels read "Estimate, US only". A plugin can price a
    # Toronto role, or one in two countries, in US dollars: the currency is
    # right and the country is not, so neither counts as priced.
    before = await _get(api_client, ROUTES["compensation"])
    db_session.add_all([
        _role("google", "toronto", level="staff", comp=900000, locations=["Toronto, ON, Canada"],
              location_groups=["canada"]),
        _role("google", "two-countries", level="staff", comp=900000, location_groups=["silicon_valley", "canada"]),
        _role("google", "toronto-base", level="staff", comp_component="base", comp_base_median=400000,
              location_groups=["canada"]),
    ])
    await db_session.commit()

    body = await _get(api_client, ROUTES["compensation"])
    assert (body["overall"], body["by_level"]) == (before["overall"], before["by_level"])
    assert body["coverage"]["with_comp"] == before["coverage"]["with_comp"]
    assert body["coverage"]["total_open"] == before["coverage"]["total_open"] + 3
    assert body["base_estimates"]["overall"] == before["base_estimates"]["overall"]
    assert body["base_estimates"]["coverage"]["with_base"] == before["base_estimates"]["coverage"]["with_base"]


@pytest.mark.asyncio
async def test_the_by_level_trends_show_printed_pay_for_unplaced_roles_but_never_their_estimate(
    api_client, db_session, seeded
):
    yesterday = DAY_START - timedelta(days=1)
    db_session.add_all([
        CompSnapshot(metric_date=yesterday, company="google", level_band="unstated", family="product_management",
                     comp_values=[640000, 640000], source="roleband"),
        DisclosureSnapshot(metric_date=yesterday, company="google", level_band="unstated", pay_basis="base",
                           roles=2, checked=2, bands=[{"low": 260000, "high": 350000, "reqs": 2}]),
    ])
    await db_session.commit()
    comp = await _get(api_client, f"{ROUTES['comp_trends']}?dim=level")
    assert "unstated" not in [s["key"] for s in comp["series"]]
    printed = await _get(api_client, f"{ROUTES['disclosure_trends']}?dim=level")
    [unplaced] = [s for s in printed["series"] if s["key"] == "unstated"]
    assert unplaced["points"][-1]["low_p50"] == 260000.0


@pytest.mark.asyncio
async def test_the_trajectory_reads_each_role_s_package_and_sets_apart_what_it_cannot_split(api_client, seeded):
    body = await _get(api_client, ROUTES["trajectory"])
    assert list(body) == _fields(contract.CompTrajectoryResponse)
    packages = [body["overall"], *body["public"], *body["private"]]
    assert all(p["base"] + p["bonus"] + p["equity"] == p["median_tc"] for p in packages)

    # Google: four posted base bands and fifteen estimates. The hourly band and
    # the $1-$2 placeholder are not split, and the closed role is not open.
    [google] = body["public"]
    assert list(google) == _fields(contract.TrajectoryPublicCompany)
    assert {k: google[k] for k in ("company", "ticker", "equity_vehicle", "vesting", "count")} == {
        "company": "google", "ticker": "GOOGL", "equity_vehicle": "rsu", "vesting": "38/32/20/10", "count": 19,
    }
    # The bonus is the posting's where it states one, the company's rule elsewhere.
    assert google["sources"] == {"base": "mixed", "bonus": "mixed", "equity": "estimated"}

    # OpenAI pays no bonus; its stated total is never split.
    [openai] = body["private"]
    assert list(openai) == _fields(contract.TrajectoryPrivateCompany)
    assert {k: openai[k] for k in ("company", "count", "bonus", "vesting")} == {
        "company": "openai", "count": 2, "bonus": 0, "vesting": "25/25/25/25",
    }
    assert openai["sources"] == {"base": "estimated", "bonus": "company_rule", "equity": "estimated"}

    # Netflix: each person picks the cash and stock mix, so a total and no split.
    assert body["choice"] == [
        {"company": "netflix", "ticker": "NFLX", "count": 1, "median_tc": 756250, "total_source": "estimated"},
    ]
    assert body["set_apart"] == [
        {"reason": "hourly", "count": 1},
        {"reason": "period_unclear", "count": 1},
        {"reason": "total_compensation", "count": 1},
    ]
    assert body["overall"]["count"] == 19


@pytest.mark.asyncio
async def test_offer_terms_carry_a_stored_quote_only_while_a_price_key_is_saved(api_client, db_session, seeded, monkeypatch):
    """The calculator reads quotes the prices job stored; without a key the
    price field stays the person's to type, whatever an old row holds."""
    from datetime import date
    from decimal import Decimal

    from tracker.db.models import CompanyPrice

    db_session.add(CompanyPrice(company_slug="google", ticker="GOOGL", price=Decimal("301.25"),
                                as_of=date(2026, 11, 6), source="tiingo"))
    await db_session.commit()
    key: list[str | None] = [None]

    async def api_key(session, settings):
        return key[0], "settings" if key[0] else None

    monkeypatch.setattr(router.price_store, "api_key", api_key)

    without = await _get(api_client, REFERENCE_ROUTES["offer_terms"])
    by_company = {row["company"]: row for row in without["companies"]}
    assert without["feed_configured"] is False
    assert by_company["google"]["quote"] is None
    # Every company the atlas records, followed or not, and every listed profile.
    assert {"amazon", "microsoft", "netflix", "google"} <= set(by_company)
    assert by_company["netflix"]["equity_vehicle"] == "cash_election"

    key[0] = "tk_test"
    with_key = await _get(api_client, REFERENCE_ROUTES["offer_terms"])
    google = {row["company"]: row for row in with_key["companies"]}["google"]
    assert with_key["feed_configured"] is True
    assert google["quote"] == {"price": 301.25, "as_of": "2026-11-06"}
    assert (google["listed"], google["ticker"]) == (True, "GOOGL")


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_key", ["g-staff", "g-senior", "g-fleet-03", "o-repost"])
async def test_a_role_reads_the_same_package_on_job_detail_and_the_stock_tab(api_client, seeded, db_session, seed_key):
    """One role alone at its company: the tab's row is that role's package, part
    for part, as Job detail shows it."""
    job_id = seeded.ids[seed_key]
    target = await db_session.get(Job, job_id)
    company = target.company
    others = (await db_session.scalars(select(Job).where(Job.company == company, Job.id != job_id))).all()
    for other in others:
        other.status = "closed"
    await db_session.commit()

    detail = (await _get(api_client, f"/api/jobs/{job_id}"))["comp_package"]
    parts = {c["kind"]: (c["low"] + c["high"]) / 2 for c in detail["components"]}
    body = await _get(api_client, ROUTES["trajectory"])
    [row] = [r for r in body["public"] + body["private"] if r["company"] == company]
    assert row["count"] == 1
    assert row["base"] == pytest.approx(parts["base"], abs=1)
    assert row["bonus"] == pytest.approx(parts.get("bonus", 0), abs=1)
    assert row["equity"] == pytest.approx(parts.get("equity", 0), abs=1)
    assert row["median_tc"] == pytest.approx((detail["total"]["low"] + detail["total"]["high"]) / 2, abs=1)


@pytest.mark.asyncio
async def test_comp_trends_recompute_percentiles_from_visible_raw_values_inside_the_window(api_client, seeded):
    body = await _get(api_client, ROUTES["comp_trends"])
    assert list(body) == _fields(contract.CompTrendsResponse)
    assert (body["dim"], body["days"], body["dates"]) == ("overall", 90, [_day(2), _day(1)])
    [market] = body["series"]
    assert (market["key"], market["count"]) == ("", 7)
    # Two raw values on the older day, seven on the newer: exact percentiles, never re-aggregated.
    assert [p["p50"] for p in market["points"]] == [635000.0, 594000.0]

    by_company = await _get(api_client, f"{ROUTES['comp_trends']}?dim=company")
    assert [s["key"] for s in by_company["series"]] == ["netflix", "openai", "google"]
    netflix = by_company["series"][0]
    assert netflix["points"][0] == {"date": _day(2), "p25": None, "p50": None, "p75": None, "p90": None}

    by_family = await _get(api_client, f"{ROUTES['comp_trends']}?dim=family")
    assert [s["key"] for s in by_family["series"]] == ["engineering_management", "product_management"]
    assert (await _get(api_client, f"{ROUTES['comp_trends']}?days=0"))["dates"] == [_day(120), _day(2), _day(1)]


@pytest.mark.asyncio
async def test_disclosure_trends_rate_every_basis_and_pool_bands_within_one(api_client, seeded):
    body = await _get(api_client, ROUTES["disclosure_trends"])
    assert list(body) == _fields(contract.DisclosureTrendsResponse)
    assert (body["basis"], body["dates"]) == ("base", [_day(2), _day(1)])
    market, cohort = body["series"]
    assert market["points"][1] == {
        "date": _day(1), "open": 21, "checked": 5, "disclosed": 4, "rate": 0.8,
        "bands": 2, "reqs": 3, "low_p50": 225000.0, "high_p50": 290000.0,
    }
    # Netflix and stripe were first read yesterday, so the market line moved with
    # the company set; the cohort line follows google alone.
    assert body["cohort"] == {"since": _day(2), "companies": 1}
    assert cohort["key"] == "cohort"
    assert [p["rate"] for p in cohort["points"]] == [1.0, 1.0]
    assert cohort["points"][1]["checked"] == 3

    by_company = await _get(api_client, f"{ROUTES['disclosure_trends']}?dim=company")
    assert [s["key"] for s in by_company["series"]] == ["google", "netflix", "stripe"]
    netflix = by_company["series"][1]
    # A day the series has no cell: nothing checked, no rate, and `date` first like every point.
    assert list(netflix["points"][0]) == _fields(contract.DisclosureTrendPoint)
    assert netflix["points"][0] == {
        "date": _day(2), "open": 0, "checked": 0, "disclosed": 0, "rate": None,
        "bands": 0, "reqs": 0, "low_p50": None, "high_p50": None,
    }
    # An unclear band is disclosed but never pooled.
    assert (netflix["points"][1]["disclosed"], netflix["points"][1]["bands"]) == (1, 0)


@pytest.mark.asyncio
async def test_the_disclosure_trends_read_their_cells_as_columns(api_client, db_session, seeded):
    """The window holds a cell per company, level and basis each day, and an
    object per cell costs the request more than its query. Reading the seeded
    cells as entities is the control: the probe sees those loads."""
    loaded: list[DisclosureSnapshot] = []

    def record(target, _context):
        loaded.append(target)

    event.listen(DisclosureSnapshot, "load", record)
    try:
        for dim in get_args(contract.DisclosureTrendDim):
            assert (await _get(api_client, f"{ROUTES['disclosure_trends']}?dim={dim}"))["series"]
        assert loaded == []
        async with AsyncSession(db_session.bind) as fresh:
            assert (await fresh.scalars(select(DisclosureSnapshot))).all()
        assert loaded
    finally:
        event.remove(DisclosureSnapshot, "load", record)


async def _add_a_place_set_and_an_other_company(db_session, seeded: SeededStatistics) -> dict[str, int]:
    """One stripe role listed at three places (a place set), each posting
    opened today; stripe followed through the Other companies set; and an opening
    today on the out-of-scope `o-out`. Returns the set members' ids."""
    members = {
        key: _role("stripe", key, level="senior", days_open=0, locations=locations, location_groups=[])
        for key, locations in (
            ("pm-emea", ["Remote - EMEA"]), ("pm-london", ["London, UK"]), ("pm-berlin", ["Berlin, Germany"]),
        )
    }
    db_session.add_all(members.values())
    db_session.add(make_company("stripe", "Stripe", source=FOLLOWED_WITH_SET))
    await db_session.flush()
    place_set = JobPlaceSet(company="stripe", title="product manager", text_hash="0" * 32, size=3,
                            places=["Remote - EMEA", "London, UK", "Berlin, Germany"], rule_version="t1")
    db_session.add(place_set)
    await db_session.flush()
    for i, job in enumerate(members.values()):
        job.first_seen = NOW - timedelta(minutes=30 - i)  # pm-emea is the set's first member
        db_session.add(JobPlaceSetMember(job_id=job.id, set_id=place_set.id, status="auto"))
        db_session.add(JobLifecycleEvent(job_id=job.id, event_type="opened", detail={}, created_at=NOW - timedelta(minutes=20)))
    db_session.add(JobLifecycleEvent(job_id=seeded.ids["o-out"], event_type="opened", detail={},
                                     created_at=NOW - timedelta(minutes=10)))
    await db_session.commit()
    return {key: job.id for key, job in members.items()}


@pytest.mark.asyncio
async def test_hiring_counts_each_role_once_by_company_and_by_place(api_client, db_session, seeded):
    """Hiring counts a place set as one role, without summing per-location
    posting slices. A place that names only a region counts as region-wide,
    never once per country."""
    await _add_a_place_set_and_an_other_company(db_session, seeded)
    body = await _get(api_client, ROUTES["demand"])
    assert list(body) == _fields(contract.DemandResponse)
    assert (body["open_total"], body["new"], body["closed"], body["unplaced"]) == (28, 4, 1, 0)
    # The set is one stripe role (2 + 1, never 2 + 3) and one new role; the
    # out-of-scope opening and the hidden company's count nowhere.
    assert [(c["company"], c["open"], c["new"], c["closed"]) for c in body["companies"]] == [
        ("google", 21, 0, 1),
        ("stripe", 3, 3, 0),
        ("openai", 3, 1, 0),
        ("netflix", 1, 0, 0),
    ]
    assert sum(c["open"] for c in body["companies"]) == body["open_total"]
    regions = {r["key"]: r for r in body["regions"]}
    assert [r["key"] for r in body["regions"]] == ["north_america", "africa", "europe", "middle_east"]
    assert regions["north_america"] == {
        "key": "north_america", "open": 27, "region_wide": 0, "countries": [{"key": "united_states", "open": 27}],
    }
    # Named in Europe (London, Berlin), so not Europe-wide; EMEA reaches Africa and
    # the Middle East only as a whole, so it is in no country there.
    assert regions["europe"] == {
        "key": "europe", "open": 1, "region_wide": 0,
        "countries": [{"key": "germany", "open": 1}, {"key": "uk", "open": 1}],
    }
    assert regions["africa"] == {"key": "africa", "open": 1, "region_wide": 1, "countries": []}
    assert regions["middle_east"] == {"key": "middle_east", "open": 1, "region_wide": 1, "countries": []}

    # Two of the 28 open roles are dated by their employer; the hidden,
    # out-of-scope and closed rows are dated too and must not count.
    assert body["employer_dated_share"] == 2 / 28
    # Hiring lists no roles: a role's age, reposts or updates answer no question
    # a person acts on (docs/decisions/0004-insights-answers-a-question.md).
    assert not {"longest_open", "listed_over_a_year", "most_reposted", "most_updated_open"} & set(body)

@pytest.mark.asyncio
async def test_hiring_counts_new_and_closed_over_the_same_two_days(api_client, db_session, seeded):
    """A company's "+new −closed" is one stretch of time, the New rule's: a
    role that came down yesterday counts as closed, one that came down four
    days ago does not, as a role listed four days ago is not new."""
    for key, ago in (("closed-yesterday", 1), ("closed-earlier", 4)):
        job = _role("netflix", key, days_open=30, status="closed", closed_at=NOW - timedelta(days=ago))
        db_session.add(job)
        await db_session.flush()
        db_session.add(JobLifecycleEvent(job_id=job.id, event_type="closed", detail={},
                                         created_at=NOW - timedelta(days=ago)))
    await db_session.commit()
    body = await _get(api_client, ROUTES["demand"])
    assert body["closed"] == 2  # `g-closed`, an hour ago, and closed-yesterday
    assert [(c["company"], c["new"], c["closed"]) for c in body["companies"] if c["company"] == "netflix"] == [
        ("netflix", 0, 1),
    ]
    assert sum(c["closed"] for c in body["companies"]) == body["closed"]


@pytest.mark.asyncio
async def test_every_insights_tab_describes_one_set_of_roles(api_client, db_session, seeded):
    """Counting a place set once on Overview, every posting on Pace's ages and
    Pay, every place membership on Hiring and roles out of scope in Pace's
    openings gives five numbers for "open". Every tab reads one rule, so each
    headline is the same number."""
    await _add_a_place_set_and_an_other_company(db_session, seeded)
    overview = await _get(api_client, ROUTES["overview"])
    velocity = await _get(api_client, "/api/statistics/velocity?days=30")
    compensation = await _get(api_client, ROUTES["compensation"])
    hiring = await _get(api_client, ROUTES["demand"])
    headlines = {
        "overview": overview["kpis"]["open_total"],
        "pace": velocity["kpis"]["open_total"],
        "pace age bands": sum(band["count"] for band in velocity["aging"]),
        "pay": compensation["coverage"]["total_open"],
        "hiring": hiring["open_total"],
    }
    assert headlines == dict.fromkeys(headlines, 28)
    # Pace's openings: the 24 seeded original roles first seen in the window
    # and new when found, and the set once; never the out-of-scope opening, the
    # set's other two members, `g-closed` (already listed when found) or the
    # repost. Overview's counts are the same numbers.
    assert (velocity["kpis"]["opened"], velocity["kpis"]["reposted"]) == (25, 1)
    assert overview["kpis"]["new_count"] == velocity["kpis"]["opened"]
    assert overview["kpis"]["already_listed_count"] == velocity["kpis"]["already_listed"] == 1
    assert overview["kpis"]["closed_count"] == velocity["kpis"]["closed"] == 1



@pytest.mark.asyncio
async def test_a_role_listed_in_three_places_counts_once_in_every_skills_read_and_daily_rollup(
    api_client, db_session, seeded,
):
    """The three stripe postings of one role each name Python, carry the same
    estimate and print the same band. Every read that counts skills and every
    daily rollup counts that role once, as the headlines do, so a company that
    lists one role in twenty cities does not weigh twenty times."""
    members = await _add_a_place_set_and_an_other_company(db_session, seeded)
    python = (await db_session.scalars(select(SkillConcept).where(SkillConcept.slug == "python"))).one()
    for job_id in members.values():
        job = await db_session.get(Job, job_id)
        for field, value in _stated(180000, 240000).items():
            setattr(job, field, value)
        job.comp_median = 300000
        db_session.add_all([_skill(job, python), JobCompEstimate(job_id=job_id, source="roleband", comp_median=300000)])
    await db_session.commit()

    # Stripe is the one Other company: its side holds the set once.
    pay = await _get(api_client, f"{ROUTES['compensation']}?side=other")
    assert pay["coverage"]["total_open"] == 3  # s-senior, s-unread and the set
    skills = await _get(api_client, "/api/skills/top?side=other")
    assert [(s["term"], s["job_count"]) for s in skills["items"]] == [("python", 1)]
    assert skills["roles"] == 1
    overview = await _get(api_client, f"{ROUTES['overview']}?side=other")
    assert [(s["term"], s["job_count"]) for s in overview["top_skills"]] == [("python", 1)]

    # A place filter reaches a set through any member: London and Berlin are
    # later members than the set's first (EMEA), and each place, or both,
    # counts the role once.
    for key, groups in (("pm-emea", ["emea"]), ("pm-london", ["uk"]), ("pm-berlin", ["germany"])):
        (await db_session.get(Job, members[key])).location_groups = groups
    await db_session.commit()
    for places in ("uk", "germany", "uk&location_group=germany"):
        placed = await _get(api_client, f"/api/skills/top?side=other&location_group={places}")
        assert ([(s["term"], s["job_count"]) for s in placed["items"]], placed["roles"]) == ([("python", 1)], 1), places
    nowhere = await _get(api_client, "/api/skills/top?side=other&location_group=france")
    assert (nowhere["items"], nowhere["roles"]) == ([], 0)

    await compute_skill_demand(db_session)
    await comp_trends.compute_comp_metrics(db_session)
    await comp_trends.compute_disclosure_metrics(db_session)
    await db_session.commit()
    demand = (await db_session.scalars(select(SkillDemandDaily.job_count).where(
        SkillDemandDaily.company == "stripe", SkillDemandDaily.metric_date >= DAY_START))).all()
    assert demand == [1]
    values = (await db_session.scalars(select(CompSnapshot.comp_values).where(
        CompSnapshot.company == "stripe", CompSnapshot.metric_date >= DAY_START))).all()
    assert [v for vs in values for v in vs] == [300000]
    cells = (await db_session.scalars(select(DisclosureSnapshot).where(
        DisclosureSnapshot.company == "stripe", DisclosureSnapshot.metric_date >= DAY_START))).all()
    # A day's open count is the Compensation tab's, and the band is one role's.
    assert sum(c.roles for c in cells) == pay["coverage"]["total_open"]
    assert [c.bands for c in cells if c.pay_basis == "base"] == [[{"low": 180000, "high": 240000, "reqs": 1}]]


@pytest.mark.asyncio
async def test_a_role_listed_in_several_places_keeps_its_estimate_through_the_posting_that_has_one(
    db_session, seeded,
):
    """The set's first posting (EMEA) has a dollar estimate with no value and
    London's is in pounds; Berlin's is in dollars. The daily pay record keeps
    the role's one dollar value: a posting without one never stands for the
    role."""
    members = await _add_a_place_set_and_an_other_company(db_session, seeded)
    db_session.add_all([
        JobCompEstimate(job_id=members["pm-emea"], source="roleband", comp_median=None),
        JobCompEstimate(job_id=members["pm-london"], source="roleband", comp_median=150000, comp_currency="GBP"),
        JobCompEstimate(job_id=members["pm-berlin"], source="roleband", comp_median=300000),
    ])
    await db_session.commit()
    await comp_trends.compute_comp_metrics(db_session)
    await db_session.commit()
    values = (await db_session.scalars(select(CompSnapshot.comp_values).where(
        CompSnapshot.company == "stripe", CompSnapshot.metric_date >= DAY_START))).all()
    assert [v for vs in values for v in vs] == [300000]

@pytest.mark.asyncio
async def test_the_pay_tab_and_the_daily_pay_record_read_a_role_through_the_same_posting(
    api_client, db_session, seeded,
):
    """A Stripe role listed in Austin first, with no estimate, and in New York,
    with $250K. The tab and the daily record both read it through New York; with
    the plain first-member rule the tab would read Austin and count no pay."""
    austin = _role("stripe", "pm-austin", level="senior", days_open=0, locations=["Austin, TX"],
                   location_groups=["austin"])
    nyc = _role("stripe", "pm-nyc", level="senior", comp=250000, days_open=0, locations=["New York, NY"],
                location_groups=["new_york"])
    db_session.add_all([austin, nyc])
    await db_session.flush()
    place_set = JobPlaceSet(company="stripe", title="product manager", text_hash="1" * 32, size=2,
                            places=["Austin, TX", "New York, NY"], rule_version="t1")
    db_session.add(place_set)
    await db_session.flush()
    for i, job in enumerate((austin, nyc)):
        job.first_seen = NOW - timedelta(minutes=30 - i)
        db_session.add(JobPlaceSetMember(job_id=job.id, set_id=place_set.id, status="auto"))
    db_session.add_all([
        JobCompEstimate(job_id=austin.id, source="roleband", comp_median=None),
        JobCompEstimate(job_id=nyc.id, source="roleband", comp_median=250000),
    ])
    await db_session.commit()

    await comp_trends.compute_comp_metrics(db_session)
    await db_session.commit()
    recorded = (await db_session.scalars(select(CompSnapshot.comp_values).where(
        CompSnapshot.company == "stripe", CompSnapshot.metric_date >= DAY_START))).all()
    assert [v for vs in recorded for v in vs] == [250000]

    body = await _get(api_client, ROUTES["compensation"])
    # The seed's Stripe roles carry no estimate: the one priced role is this one.
    assert body["coverage"]["with_comp"] == 26
    assert body["coverage"]["total_open"] == 28
    assert body["overall"]["count"] == 26 and body["overall"]["min"] == 250000


async def _place_set(db_session, jobs: list, digit: str) -> None:
    """One role listed at each of `jobs`' places, the first listed first."""
    db_session.add_all(jobs)
    await db_session.flush()
    place_set = JobPlaceSet(company=jobs[0].company, title="product manager", text_hash=digit * 32, size=len(jobs),
                            places=[job.locations[0] for job in jobs], rule_version="t1")
    db_session.add(place_set)
    await db_session.flush()
    for i, job in enumerate(jobs):
        job.first_seen = NOW - timedelta(minutes=30 - i)
        db_session.add(JobPlaceSetMember(job_id=job.id, set_id=place_set.id, status="auto"))


@pytest.mark.asyncio
async def test_a_role_priced_by_its_base_counts_once_and_never_beside_its_total(api_client, db_session, seeded):
    """A role at two places priced by base alone is one base role. A role whose
    first place is priced by base and whose second has a total is a total, and
    not also a base role."""
    before = (await _get(api_client, ROUTES["compensation"]))["base_estimates"]["coverage"]["with_base"]

    def base_only(key: str, place: str, group: str, base: int):
        return _role("netflix", key, level="senior", days_open=0, locations=[place], location_groups=[group],
                     comp_component="base", comp_base_median=base)

    await _place_set(db_session, [base_only("pm-austin", "Austin, TX", "austin", 180000),
                                  base_only("pm-nyc", "New York, NY", "new_york", 200000)], "2")
    await _place_set(db_session, [
        base_only("em-austin", "Austin, TX", "austin", 210000),
        _role("netflix", "em-nyc", level="senior", comp=330000, days_open=0, locations=["New York, NY"],
              location_groups=["new_york"]),
    ], "3")
    await db_session.commit()

    body = await _get(api_client, ROUTES["compensation"])
    assert body["base_estimates"]["coverage"]["with_base"] == before + 1
    assert body["overall"]["min"] == 330000 and body["coverage"]["with_comp"] == 26


async def _onboard_a_company(db_session) -> dict[str, int]:
    """`acme` arrives today: its FIRST run finds three roles its board was already
    listing (one dated by its employer 200 days ago, one 20 days ago, one
    undated), and a later run finds one that opened while we watched."""
    first, later = ScrapeRun(started_at=NOW - timedelta(hours=4), status="ok"), ScrapeRun(
        started_at=NOW - timedelta(hours=2), status="ok")
    db_session.add_all([first, later])
    await db_session.flush()
    found = {
        "acme-dated": _role("acme", "dated", days_open=0, first_posted_at=NOW - timedelta(days=200),
                            arrival="first_read"),
        "acme-recent": _role("acme", "recent", days_open=0, first_posted_at=NOW - timedelta(days=20),
                             arrival="first_read"),
        "acme-undated": _role("acme", "undated", days_open=0, arrival="first_read"),
        "acme-new": _role("acme", "new", days_open=0),
    }
    db_session.add_all(found.values())
    await db_session.flush()
    for key, job in found.items():
        run = later if key == "acme-new" else first
        job.first_seen = run.started_at
        db_session.add(JobLifecycleEvent(job_id=job.id, run_id=run.id, event_type="opened", detail={},
                                         created_at=run.started_at))
    await db_session.commit()
    return {key: job.id for key, job in found.items()}


@pytest.mark.asyncio
async def test_a_scope_narrows_every_tab_to_one_side_and_its_two_sides_add_up(api_client, db_session, seeded):
    """The Other companies can hold most open roles across most of the
    companies, so every unscoped ranking is their long tail. A scope
    (`?side=` and `?family=`) narrows every tab alike; Your companies and Other
    companies partition All, and a discipline narrows the same way."""
    await _add_a_place_set_and_an_other_company(db_session, seeded)  # stripe: the one Other company

    async def headlines(query: str) -> dict:
        overview = await _get(api_client, f"{ROUTES['overview']}?{query}")
        velocity = await _get(api_client, f"/api/statistics/velocity?days=30&{query}")
        pay = await _get(api_client, f"{ROUTES['compensation']}?{query}")
        hiring = await _get(api_client, f"{ROUTES['demand']}?{query}")
        return {
            "overview": overview["kpis"]["open_total"], "pace": velocity["kpis"]["open_total"],
            "pace bands": sum(b["count"] for b in velocity["aging"]), "pay": pay["coverage"]["total_open"],
            "hiring": hiring["open_total"], "companies": sorted(c["company"] for c in hiring["companies"]),
        }

    every, yours, other = [await headlines(q) for q in ("side=all", "side=yours", "side=other")]
    assert other == {
        "overview": 3, "pace": 3, "pace bands": 3, "pay": 3, "hiring": 3, "companies": ["stripe"],
    }  # s-senior, s-unread and the place set once
    assert {k: v for k, v in yours.items() if k != "companies"} == dict.fromkeys(
        ["overview", "pace", "pace bands", "pay", "hiring"], 25
    )
    assert "stripe" not in yours["companies"]
    for key in ("overview", "pace", "pay", "hiring"):
        assert yours[key] + other[key] == every[key] == 28, key

    # A discipline: the two engineering-management roles (`o-original`, `o-old`).
    em = await headlines("family=engineering_management")
    assert {k: v for k, v in em.items() if k != "companies"} == dict.fromkeys(
        ["overview", "pace", "pace bands", "pay", "hiring"], 2
    )
    assert em["companies"] == ["openai"]

    # The skills reads narrow the same way: stripe names no skill.
    assert (await _get(api_client, "/api/skills/top?side=other"))["items"] == []
    assert [i["term"] for i in (await _get(api_client, "/api/skills/top?side=yours"))["items"]] == ["python", "sql"]
    assert await _get(api_client, f"{ROUTES['overview']}?side=everyone", status=422)


@pytest.mark.asyncio
async def test_a_company_first_scan_opens_only_what_its_employer_dated_new_and_ages_from_its_listed_date(
    api_client, db_session, seeded,
):
    """A first scan reads a board that was already listing, so every posting on
    it is stored at once. Counted as opened, a set of companies arriving at
    once would swamp the month's openings, so a first scan's find opens only
    when its employer dated it within the New window; aged by our first
    sighting its postings would all read "under a week". Its undated find has
    no knowable age."""
    await _onboard_a_company(db_session)
    overview = await _get(api_client, ROUTES["overview"])
    # acme-new opened; the first read's three and `g-closed` were already listed.
    assert (overview["kpis"]["new_count"], overview["kpis"]["already_listed_count"]) == (25, 4)

    velocity = await _get(api_client, "/api/statistics/velocity?days=30")
    assert (velocity["kpis"]["opened"], velocity["kpis"]["already_listed"]) == (25, 4)
    assert not {"net", "updated"} & set(velocity["kpis"])
    bands = {band["lo"]: band["count"] for band in velocity["aging"]}
    # acme-dated starts at its employer's date, 200 days ago, not at this morning;
    # acme-recent at 20 days; the watched opening at today. The undated find is
    # counted beside the bands, never as "under a week". A watched role starts
    # at its employer's date too: `o-old`, seen 45 days ago, was dated 120.
    assert bands[90] == 2  # 3 months and more: acme-dated and o-old
    assert bands[14] == 1  # 2 to 4 weeks
    assert velocity["kpis"]["age_unknown"] == 1
    assert sum(bands.values()) + velocity["kpis"]["age_unknown"] == velocity["kpis"]["open_total"]

    hiring = await _get(api_client, ROUTES["demand"])
    assert hiring["new"] == 4  # the seed's three and acme-new, never the first scan's three
    assert [(c["company"], c["new"]) for c in hiring["companies"] if c["company"] == "acme"] == [("acme", 1)]


@pytest.mark.asyncio
async def test_velocity_states_the_employer_dated_share_of_each_age_sample(api_client, seeded):
    """Each of Pace's age samples says how much of it the employer dated: the open roles behind the median and the bands (2 of 27
    visible, in scope), and the closed postings behind how long postings stay up
    (`g-closed`, dated). Hidden and out-of-scope rows never count."""
    kpis = (await _get(api_client, "/api/statistics/velocity?days=0"))["kpis"]
    assert kpis["employer_dated_share"] == 2 / 27
    assert (kpis["closed_sample"], kpis["closed_employer_dated_share"]) == (1, 1.0)


@pytest.mark.asyncio
async def test_each_header_chip_counts_the_board_view_it_opens(api_client, db_session, seeded):
    """The chips are links to Board views, so a chip and its list are one
    number: `open_total` never counts roles marked Not for me, which the Board
    hides. Marking one plain role, one of today's new roles and today's repost moves
    every chip with its list."""
    for key in ("g-senior", "s-senior", "o-repost"):
        db_session.add(JobFeedback(job_id=seeded.ids[key], verdict="dismissed"))
    await db_session.commit()

    body = await _get(api_client, ROUTES["stats"])
    lenses = {"open_total": "", "new_today": "&new_today_only=true", "reposted_today": "&repost_today_only=true"}
    board = {
        chip: (await _get(api_client, f"/api/jobs?status=open&limit=1{query}"))["total"]
        for chip, query in lenses.items()
    }
    assert {chip: body[chip] for chip in lenses} == board
    assert board == {"open_total": 24, "new_today": 2, "reposted_today": 0}, (
        "27, 3 and 1 before the marks: each marked role leaves its own chip"
    )


# --------------------------------------------------------------------------- #
# 4. Hiding a company
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_hiding_a_company_removes_it_from_every_route(api_client, db_session, seeded):
    for path in ROUTES.values():
        assert "hidden-co" not in (await api_client.get(path)).text, path
    assert "google" in (await api_client.get(ROUTES["stats"])).text

    db_session.add(make_company("google", "Google", visible=False))
    await db_session.commit()
    for path in [*ROUTES.values(), f"{ROUTES['comp_trends']}?dim=company", f"{ROUTES['disclosure_trends']}?dim=company"]:
        assert "google" not in (await api_client.get(path)).text, path
    assert (await _get(api_client, ROUTES["stats"]))["open_total"] == 6


@pytest.mark.asyncio
async def test_a_company_the_user_stopped_following_leaves_every_route_and_keeps_its_rows(
    api_client, db_session, seeded
):
    """The Board and every count read the companies the user follows.
    Unfollowing leaves `visible` true, so a route reading `visible` alone keeps
    the company's postings on the Board unverified, since nothing scans a
    company nobody follows. The rows are
    kept, untouched; following again brings them back in the same request."""
    db_session.add(make_company("google", "Google", enabled=False))
    await db_session.commit()
    for path in [*ROUTES.values(), f"{ROUTES['comp_trends']}?dim=company", f"{ROUTES['disclosure_trends']}?dim=company"]:
        assert "google" not in (await api_client.get(path)).text, path
    assert (await _get(api_client, ROUTES["stats"]))["open_total"] == 6
    # Nothing is deleted, closed or rewritten.
    google = (await db_session.scalars(select(Job).where(Job.company == "google"))).all()
    assert len(google) == 22 and sum(job.status == "open" for job in google) == 21

    # Following again (google is walled, so the follow itself goes through its
    # consent dialog; the row it writes is this). No scan runs in between.
    google_row = await db_session.get(TrackedCompany, "google")
    google_row.enabled = True
    await db_session.commit()
    assert (await _get(api_client, ROUTES["stats"]))["open_total"] == 27
    assert "google" in (await api_client.get(ROUTES["stats"])).text


# --------------------------------------------------------------------------- #
# 5. Drift
# --------------------------------------------------------------------------- #


def _adding(real):
    def drifted(*args, **kwargs):
        return {**real(*args, **kwargs), "unmodelled": True}

    return drifted


def _each_country_without_bands(real):
    def drifted(*args, **kwargs):
        body = real(*args, **kwargs)
        return {**body, "countries": [{k: v for k, v in c.items() if k != "bands"} for c in body["countries"]]}

    return drifted


def _each_row_adding(real):
    def drifted(*args, **kwargs):
        return [{**row, "drift": 1} for row in real(*args, **kwargs)]

    return drifted


def _series_without_count(real):
    def drifted(*args, **kwargs):
        body = real(*args, **kwargs)
        return {**body, "series": [{k: v for k, v in s.items() if k != "count"} for s in body["series"]]}

    return drifted


def _points_with_an_extra_key(real):
    def drifted(*args, **kwargs):
        body = real(*args, **kwargs)
        return {**body, "series": [{**s, "points": [{**p, "median": None} for p in s["points"]]} for s in body["series"]]}

    return drifted


def _each_region_adding(real):
    def drifted(*args, **kwargs):
        body = real(*args, **kwargs)
        return {**body, "regions": [{**r, "drift": 1} for r in body["regions"]]}

    return drifted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "drift", "route"),
    [
        ("build_comp_stats", _adding, "compensation"),
        ("build_posted_pay", _each_country_without_bands, "compensation"),
        ("build_comp_trajectory", _adding, "trajectory"),
        ("build_offer_terms", _each_row_adding, "offer_terms"),
        ("build_comp_trend_series", _series_without_count, "comp_trends"),
        ("build_disclosure_trend_series", _points_with_an_extra_key, "disclosure_trends"),
        ("build_hiring_places", _each_region_adding, "demand"),
    ],
    # No builder here writes English: the dashboard names families, so there is
    # no name left to drift.
    ids=["comp_stats_key_added", "posted_bands_dropped", "trajectory_key_added", "offer_terms_key_added",
         "trend_count_dropped", "disclosure_point_key_added", "demand_region_key_added"],
)
async def test_a_builder_that_drifts_fails_the_response(api_client, seeded, monkeypatch, name, drift, route):
    monkeypatch.setattr(router, name, drift(getattr(router, name)))
    with pytest.raises(ResponseValidationError):
        await api_client.get({**ROUTES, **REFERENCE_ROUTES}[route])

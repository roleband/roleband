"""Each Insights operation answers what its dashboard route answers.

Both sides run over real ASGI against one scratch database seeded by
`scripts.seed_synthetic`, with the records the Insights screens read beside
it: whole listing reads for a history, skills the postings name, and two days
of the daily pay and disclosure records. Each operation's figures must equal
its route's JSON exactly; its `coverage` and `page` are the operation's own.

Every equality has a negative control: the same comparison fails against the
route's answer to another filter, or after the data under it changed, so an
operation that ignored a filter, or answered from a copy of the figures,
would not pass.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy import func, select, update

from scripts.seed_synthetic import seed
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations import cursor, insights
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.insights import BUDGET_BYTES, READS, fit
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.analytics.comp_trends import compute_comp_metrics, compute_disclosure_metrics
from tracker.analytics.posting_reality import NEW_LISTING_WINDOW
from tracker.api.agent_operations import PREFIX
from tracker.api.routers.statistics import VelocityOut
from tracker.api.schemas.skills import TopSkillsResponse
from tracker.api.schemas.statistics import (
    CompensationStatsResponse,
    CompTrajectoryResponse,
    CompTrendsResponse,
    DemandResponse,
    DisclosureTrendsResponse,
    InsightsHistoryResponse,
    LevelGuideResponse,
    OfferTermsResponse,
    PayTableResponse,
    StatisticsOverviewResponse,
)
from tracker.db.models import (
    CompanyProfile,
    CompSnapshot,
    DisclosureSnapshot,
    Job,
    JobSkill,
    ScrapeSourceRun,
    SkillConcept,
    TrackedCompany,
)

pytestmark = pytest.mark.usefixtures("no_escape")

_SKILLS = (("python", "language"), ("kubernetes", "platform"), ("sql", "language"))


@pytest_asyncio.fixture
async def workspace(db_session, scratch_scope):
    """The seeded workspace with agent reads on, and the records Insights reads."""
    session = db_session
    await seed(session, 12, seed_value=1, derived=False, agent_tasks=True)
    # Whole listing reads three weeks ago: the scope's history starts there.
    started = datetime.now(UTC) - timedelta(days=21)
    await session.execute(
        update(ScrapeSourceRun).values(
            list_complete=True, started_at=started, finished_at=started + timedelta(minutes=1)
        )
    )
    # Ranges stated on most open roles, as the disclosure pass records them.
    await session.execute(
        update(Job).where(Job.status == "open", Job.id % 4 != 0).values(
            disclosed_base_min=100_000 + (Job.id % 7) * 10_000, disclosed_base_max=150_000 + (Job.id % 7) * 10_000,
            disclosed_pay_basis="base", disclosed_currency="USD", disclosed_pay_period="year", structured_at=started,
        )
    )
    await session.execute(update(Job).where(Job.status == "open", Job.id % 4 == 0).values(structured_at=started))
    # Skills the open roles name, each on a different share of them.
    jobs = list((await session.scalars(select(Job.id).where(Job.status == "open").order_by(Job.id))).all())
    for position, (slug, category) in enumerate(_SKILLS):
        concept = SkillConcept(
            slug=slug, display=slug.title(), facet="skill", category=category, description=slug,
            status="active", taxonomy_version="t",
        )
        session.add(concept)
        await session.flush()
        for job_id in jobs[position::position + 1]:
            session.add(JobSkill(
                job_id=job_id, concept_id=concept.id, importance_score=80, importance_band="core",
                confidence="high", modality="required", content_hash="h", extractor_version="e",
                taxonomy_version="t",
            ))
    # Two days of the daily records: yesterday's, moved back a day, then today's.
    await compute_comp_metrics(session)
    await compute_disclosure_metrics(session)
    for table in (CompSnapshot, DisclosureSnapshot):
        await session.execute(update(table).values(metric_date=table.metric_date - timedelta(days=1)))
    await compute_comp_metrics(session)
    await compute_disclosure_metrics(session)
    await set_agent_access(session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(session)
    await session.commit()
    return session


async def _family(session) -> str:
    """The discipline most open roles hold, so narrowing to it changes the figures."""
    return await session.scalar(
        select(Job.family).where(Job.status == "open", Job.family.isnot(None))
        .group_by(Job.family).order_by(func.count().desc(), Job.family).limit(1)
    )


async def _company(session) -> str:
    return await session.scalar(
        select(Job.company).where(Job.status == "open").group_by(Job.company)
        .order_by(func.count().desc(), Job.company).limit(1)
    )


async def _agent(api_client, path: str, **params) -> tuple[Any, dict]:
    response = await api_client.get(f"{PREFIX}/insights/{path}", params=params)
    return response, response.json()


async def _route(api_client, path: str, **params) -> dict:
    response = await api_client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _data(body: dict) -> dict:
    assert body["ok"] is True, body["error"]
    return body["data"]


def _figures(data: dict) -> dict:
    """An answer's figures: what is left once its coverage and page are set aside."""
    return {key: value for key, value in data.items() if key not in ("coverage", "page")}


def _assert_same_figures(ours: dict, theirs: dict, case: Any) -> None:
    """Equal figures. A window shorter than the history starts at "now", which
    two calls read a moment apart, so that start may differ by a moment."""
    if ours.get("since") != theirs.get("since") and None not in (ours.get("since"), theirs.get("since")):
        apart = datetime.fromisoformat(ours["since"]) - datetime.fromisoformat(theirs["since"])
        assert abs(apart) < timedelta(seconds=5), case
        ours, theirs = {**ours, "since": None}, {**theirs, "since": None}
    assert ours == theirs, case


def _cells_as_the_route_says_them(guide: dict) -> dict:
    """The level guide's cells say one of two keys, so the route leaves the
    other out and the operation's shape says it is null."""
    return {**guide, "companies": [
        {**company, "levels": {
            band: {key: value for key, value in cell.items() if value is not None}
            for band, cell in company["levels"].items()
        }}
        for company in guide["companies"]
    ]}


# --------------------------------------------------------------------------- #
# Parity: each operation, its route, the same filters.
# --------------------------------------------------------------------------- #

#: operation id -> (agent path, dashboard route), and the filters each case
#: sends, as the operation names them and as the route does.
ROUTES = {
    "insights.overview": ("overview", "/api/statistics/overview"),
    "insights.compensation": ("compensation", "/api/statistics/compensation"),
    "insights.pay_table": ("pay-table", "/api/statistics/pay-table"),
    "insights.trajectory": ("trajectory", "/api/statistics/comp-trajectory"),
    "insights.offer_terms": ("offer-terms", "/api/statistics/offer-terms"),
    "insights.levels": ("levels", "/api/statistics/levels"),
    "insights.pay_trends": ("pay-trends", "/api/statistics/comp-trends"),
    "insights.disclosure_trends": ("disclosure-trends", "/api/statistics/disclosure-trends"),
    "insights.velocity": ("velocity", "/api/statistics/velocity"),
    "insights.history": ("history", "/api/statistics/history"),
    "insights.demand": ("demand", "/api/demand"),
    "insights.skills": ("skills", "/api/skills/top"),
}


def _route_params(operation: str, params: dict) -> dict:
    """The operation's filters as the dashboard route spells them."""
    renamed = {"location": "location_group"}
    return {
        renamed.get(key, key): value for key, value in params.items() if key not in ("tier", "cursor")
    }


async def _cases(session) -> list[tuple[str, dict]]:
    family = await _family(session)
    company = await _company(session)
    return [
        ("insights.overview", {}),
        ("insights.overview", {"days": 7, "family": [family]}),
        ("insights.compensation", {"tier": "full"}),
        ("insights.compensation", {"tier": "full", "family": [family]}),
        ("insights.pay_table", {"tier": "full", "country": "US", "level": "senior"}),
        ("insights.trajectory", {"tier": "full"}),
        ("insights.offer_terms", {"tier": "full"}),
        ("insights.pay_trends", {"tier": "full"}),
        ("insights.pay_trends", {"tier": "full", "dim": "company", "days": 30}),
        ("insights.pay_trends", {"tier": "full", "dim": "family", "family": [family]}),
        ("insights.disclosure_trends", {"tier": "full"}),
        ("insights.disclosure_trends", {"tier": "full", "dim": "level", "side": "yours"}),
        ("insights.velocity", {"tier": "full"}),
        ("insights.velocity", {"tier": "full", "days": 0, "family": [family]}),
        ("insights.history", {}),
        ("insights.demand", {"tier": "full"}),
        ("insights.skills", {"tier": "full"}),
        ("insights.skills", {"tier": "full", "company": [company], "limit": 2}),
    ]


@pytest.mark.asyncio
async def test_every_operation_answers_its_routes_figures(api_client, workspace):
    cases = await _cases(workspace)
    assert {operation for operation, _ in cases} | {"insights.levels"} == set(READS)
    for operation, params in cases:
        agent_path, route_path = ROUTES[operation]
        expected = await _route(api_client, route_path, **_route_params(operation, params))

        response, body = await _agent(api_client, agent_path, **params)

        assert response.status_code == 200, (operation, body)
        data = _data(body)
        assert data["page"] is None, operation
        _assert_same_figures(_figures(data), expected, (operation, params))
        assert body["meta"]["data_classes"] == ["market_statistic"]


@pytest.mark.asyncio
async def test_the_level_guide_is_the_routes(api_client, workspace):
    expected = await _route(api_client, "/api/statistics/levels")

    pages = await _every_page(api_client, "levels", tier="full")

    merged = _figures(pages[0])
    for page in pages[1:]:
        merged["companies"] += page["companies"]
        merged["unguided"] += page["unguided"]
    assert _cells_as_the_route_says_them(merged) == expected
    assert len(expected["companies"]) > 20
    # Negative control: a guide one company short is not the route's.
    assert _cells_as_the_route_says_them({**merged, "companies": merged["companies"][:-1]}) != expected


@pytest.mark.asyncio
async def test_the_seeded_figures_are_not_empty(api_client, workspace):
    """The equalities above compare figures the seed fills, not two zeros."""
    overview = await _route(api_client, "/api/statistics/overview")
    assert overview["kpis"]["open_total"] > 0 and overview["kpis"]["new_count"] > 0
    assert len(overview["top_skills"]) == len(_SKILLS)
    compensation = await _route(api_client, "/api/statistics/compensation")
    assert compensation["disclosure"]["overall"]["open"] > 0
    assert any(country["bands"] for country in compensation["posted"]["countries"])
    pay_table = await _route(api_client, "/api/statistics/pay-table", country="US", level="senior")
    assert pay_table["rows"]
    trends = await _route(api_client, "/api/statistics/comp-trends", dim="company")
    assert len(trends["dates"]) == 2 and len(trends["series"]) > 1
    disclosure = await _route(api_client, "/api/statistics/disclosure-trends")
    assert len(disclosure["dates"]) == 2
    velocity = await _route(api_client, "/api/statistics/velocity")
    assert velocity["kpis"]["opened"] > 0 and velocity["by_company"]
    history = await _route(api_client, "/api/statistics/history")
    assert history["days"] >= 20
    demand = await _route(api_client, "/api/demand")
    assert demand["companies"] and demand["regions"]
    skills = await _route(api_client, "/api/skills/top")
    assert [item["term"] for item in skills["items"]] == ["python", "kubernetes", "sql"]
    trajectory = await _route(api_client, "/api/statistics/comp-trajectory")
    assert trajectory["overall"] is not None


# --------------------------------------------------------------------------- #
# Negative controls: the comparison fails when the figures differ.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_filter_the_route_was_not_given_is_not_its_answer(api_client, workspace):
    family = await _family(workspace)
    for operation, params, changed in [
        ("insights.overview", {}, {"family": [family]}),
        ("insights.compensation", {"tier": "full"}, {"family": [family]}),
        ("insights.pay_table", {"tier": "full", "country": "US", "level": "senior"}, {"level": "mid"}),
        ("insights.pay_trends", {"tier": "full"}, {"dim": "company"}),
        ("insights.disclosure_trends", {"tier": "full"}, {"dim": "level"}),
        ("insights.velocity", {"tier": "full"}, {"family": [family]}),
        ("insights.demand", {"tier": "full"}, {"family": [family]}),
        ("insights.skills", {"tier": "full"}, {"limit": 1}),
    ]:
        agent_path, route_path = ROUTES[operation]
        expected = await _route(api_client, route_path, **_route_params(operation, params))

        _, body = await _agent(api_client, agent_path, **{**params, **changed})

        assert _figures(_data(body)) != expected, (operation, changed)


@pytest.mark.asyncio
async def test_a_hidden_company_changes_both_answers_alike(api_client, workspace):
    before = {
        operation: _figures(_data((await _agent(api_client, ROUTES[operation][0], tier="full"))[1]))
        for operation in ("insights.trajectory", "insights.demand", "insights.velocity")
    }
    company = await _company(workspace)
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == company).values(visible=False))
    await workspace.commit()

    for operation, answer in before.items():
        agent_path, route_path = ROUTES[operation]
        expected = await _route(api_client, route_path)
        _, body = await _agent(api_client, agent_path, tier="full")
        assert answer != expected, operation
        assert _figures(_data(body)) == expected, operation
        assert _data(body)["coverage"]["off_board_companies"] >= 1


@pytest.mark.asyncio
async def test_a_company_that_lists_changes_both_offer_terms_alike(api_client, workspace):
    before = _figures(_data((await _agent(api_client, "offer-terms", tier="full"))[1]))
    company = await _company(workspace)
    workspace.add(CompanyProfile(slug=company, display_name=company, is_public=True, ticker="SYNQ"))
    await workspace.commit()

    expected = await _route(api_client, "/api/statistics/offer-terms")
    _, body = await _agent(api_client, "offer-terms", tier="full")

    assert before != expected
    assert _figures(_data(body)) == expected
    assert any(row["company"] == company and row["ticker"] == "SYNQ" for row in expected["companies"])


# --------------------------------------------------------------------------- #
# Coverage: population, window and freshness beside the figures.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_every_answer_states_its_population_window_and_freshness(api_client, workspace):
    family = await _family(workspace)
    _, body = await _agent(api_client, "overview", days=7, family=family)
    coverage = _data(body)["coverage"]
    assert coverage["population"] == "open_roles"
    assert coverage["families"] == [family] and coverage["side"] == "all"
    assert coverage["window"]["days"] == 7
    assert coverage["window"]["since"] == _data(body)["since"]
    assert coverage["history"]["days"] >= 20
    assert coverage["last_read_at"] is not None

    trends = _data((await _agent(api_client, "pay-trends", tier="full"))[1])
    assert trends["coverage"]["population"] == "daily_records"
    assert trends["coverage"]["window"]["since"].startswith(trends["dates"][0])

    compensation = _data((await _agent(api_client, "compensation", tier="full"))[1])
    assert compensation["coverage"]["window"] is None

    levels = _data((await _agent(api_client, "levels", tier="full"))[1])
    assert levels["coverage"]["population"] == "reference"
    assert levels["coverage"]["history"] is None and levels["coverage"]["last_read_at"] is None

    demand = _data((await _agent(api_client, "demand", tier="full"))[1])
    assert demand["coverage"]["window"]["days"] >= 1


@pytest.mark.asyncio
async def test_figures_narrowed_to_a_company_state_that_companys_history_and_last_read(api_client, workspace):
    company = await _company(workspace)
    now = datetime.now(UTC)
    # The chosen company was read whole ten days ago and last two days ago;
    # every other company three weeks ago and an hour ago.
    await workspace.execute(update(ScrapeSourceRun).values(finished_at=now - timedelta(hours=1)))
    await workspace.execute(
        update(ScrapeSourceRun).where(ScrapeSourceRun.company_slug == company)
        .values(started_at=now - timedelta(days=10), finished_at=now - timedelta(days=2))
    )
    await workspace.commit()

    narrowed = _data((await _agent(api_client, "skills", company=company))[1])["coverage"]
    everyone = _data((await _agent(api_client, "skills"))[1])["coverage"]

    assert abs(datetime.fromisoformat(narrowed["last_read_at"]) - (now - timedelta(days=2))) < timedelta(minutes=1)
    assert narrowed["history"]["days"] == 10
    # The same read over the whole scope reports the others' later read and longer history.
    assert abs(datetime.fromisoformat(everyone["last_read_at"]) - (now - timedelta(hours=1))) < timedelta(minutes=1)
    assert everyone["history"]["days"] >= 20


@pytest.mark.asyncio
async def test_the_new_listing_window_starts_no_earlier_than_the_history(api_client, workspace):
    long_history = _data((await _agent(api_client, "demand", tier="full"))[1])["coverage"]
    assert datetime.fromisoformat(long_history["window"]["since"]) > datetime.fromisoformat(
        long_history["history"]["since"]
    )
    assert long_history["window"]["days"] == NEW_LISTING_WINDOW.days

    # Read whole only since yesterday: the window cannot reach past that read.
    yesterday = datetime.now(UTC) - timedelta(days=1)
    await workspace.execute(update(ScrapeSourceRun).values(started_at=yesterday))
    await workspace.commit()
    short_history = _data((await _agent(api_client, "demand", tier="full"))[1])["coverage"]
    assert short_history["window"]["since"] == short_history["history"]["since"]

    # No whole read at all: no arrival is dated, so the window has no start.
    await workspace.execute(update(ScrapeSourceRun).values(list_complete=False))
    await workspace.commit()
    no_history = _data((await _agent(api_client, "demand", tier="full"))[1])["coverage"]
    assert no_history["history"]["since"] is None and no_history["window"]["since"] is None


# --------------------------------------------------------------------------- #
# Strict filters, and the switch that refuses.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_an_unknown_discipline_is_refused_with_its_lookup(api_client, workspace):
    response, body = await _agent(api_client, "overview", family="not-a-discipline")

    assert body["ok"] is False and body["error"]["code"] == "invalid_input"
    assert response.status_code == outcome("invalid_input").http_status
    assert body["error"]["details"]["unknown"] == [{"filter": "family", "value": "not-a-discipline"}]
    assert body["error"]["next_actions"] == [{"operation": "vocabulary.list", "arguments": {"kind": "family"}}]


@pytest.mark.asyncio
async def test_a_discipline_by_its_name_reads_as_its_slug(api_client, workspace):
    family = await _family(workspace)
    _, by_slug = await _agent(api_client, "overview", family=family)
    _, by_name = await _agent(api_client, "overview", family=family.replace("_", " ").upper())

    assert _figures(_data(by_name)) == _figures(_data(by_slug))
    assert _data(by_name)["coverage"]["families"] == [family]


@pytest.mark.asyncio
async def test_every_insights_read_is_refused_while_agent_access_is_off(api_client, workspace):
    await set_agent_access(workspace, AgentAccessConfig(enabled=False, allow_writes=False))
    await workspace.commit()

    for agent_path, _ in ROUTES.values():
        params = {"country": "US", "level": "senior"} if agent_path == "pay-table" else {}
        response, body = await _agent(api_client, agent_path, **params)
        assert body["ok"] is False and body["data"] is None
        assert body["error"]["code"] == "access_disabled"
        assert response.status_code == outcome("access_disabled").http_status


# --------------------------------------------------------------------------- #
# The tier's budget: pages that stop early and read on, nothing lost.
# --------------------------------------------------------------------------- #


async def _every_page(api_client, path: str, **params) -> list[dict]:
    pages: list[dict] = []
    while True:
        _, body = await _agent(api_client, path, **params)
        data = _data(body)
        pages.append(data)
        page = data["page"]
        if page is None or not page["continue_with"]:
            assert body["meta"]["next_cursor"] is None
            return pages
        assert body["meta"]["next_cursor"] == page["continue_with"][0]["arguments"]["cursor"]
        assert [warning["code"] for warning in body["warnings"]] == ["page_shortened"]
        follow = page["continue_with"][0]
        assert follow["operation"] == f"insights.{path.replace('-', '_')}"
        params = follow["arguments"]


@pytest.mark.asyncio
async def test_an_answer_past_the_small_budget_pages_with_continue_with(api_client, workspace):
    whole = _data((await _agent(api_client, "offer-terms", tier="full"))[1])
    assert len(json.dumps(whole["companies"])) > BUDGET_BYTES["small"]

    pages = await _every_page(api_client, "offer-terms")

    assert len(pages) > 1
    for data in pages:
        assert len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()) <= BUDGET_BYTES["small"]
        assert data["page"]["tier"] == "small" and data["page"]["total"] == len(whole["companies"])
    offsets = [data["page"]["offset"] for data in pages]
    assert offsets == sorted(offsets) and offsets[0] == 0
    # Read on to the end, the pages hold every company once, in order.
    assert [row for data in pages for row in data["companies"]] == whole["companies"]
    assert {key: value for key, value in pages[-1].items() if key not in ("companies", "page")} == {
        key: value for key, value in whole.items() if key not in ("companies", "page")
    }


@pytest.mark.asyncio
async def test_a_nested_list_pages_inside_whole_items(api_client, workspace, monkeypatch):
    whole = _data((await _agent(api_client, "compensation", tier="full"))[1])
    bands = [band for country in whole["posted"]["countries"] for band in country["bands"]]
    assert len(bands) > 2
    spec = READS["insights.compensation"]
    answer = insights.InsightsCompensation.model_validate(whole)
    # The largest budget that cannot hold every band: the answer pages them.
    first = None
    for room in range(len(json.dumps(whole, separators=(",", ":"))), 0, -40):
        monkeypatch.setitem(insights.BUDGET_BYTES, "small", room)
        first = fit(spec, answer, insights.CompensationInput(), workspace_id="w")
        if first.shortened:
            break
    assert first is not None and first.shortened and first.next_cursor is not None

    kept = first.data.model_dump(mode="json")
    # Every country stays whole but for its bands, which stop where the budget does.
    assert [country["country"] for country in kept["posted"]["countries"]] == [
        country["country"] for country in whole["posted"]["countries"]
    ]
    assert [country["levels"] for country in kept["posted"]["countries"]] == [
        country["levels"] for country in whole["posted"]["countries"]
    ]
    assert [band for country in kept["posted"]["countries"] for band in country["bands"]] == bands[
        :kept["page"]["returned"]
    ]
    assert 0 < kept["page"]["returned"] < len(bands) == kept["page"]["total"]
    assert kept["page"]["lists"] == ["posted.countries.*.bands"]


@pytest.mark.asyncio
async def test_a_cursor_from_another_request_is_refused(api_client, workspace):
    _, body = await _agent(api_client, "offer-terms")
    next_cursor = body["meta"]["next_cursor"]
    assert next_cursor is not None

    response, refused = await _agent(api_client, "levels", cursor=next_cursor)

    assert refused["ok"] is False and refused["error"]["code"] == "invalid_input"
    assert refused["error"]["details"] == {"field": "cursor", "reason": "other_request"}


def test_an_item_larger_than_the_budget_is_refused_not_cut():
    spec = READS["insights.offer_terms"]
    row = {
        "company": "x" * (BUDGET_BYTES["small"] + 10), "listed": False, "ticker": None, "equity_vehicle": None,
        "vesting": None, "vesting_stated_by": None, "bonus_rule": None, "sign_on_bridges_vesting": False,
        "quote": None,
    }
    answer = insights.InsightsOfferTerms.model_validate({
        "feed_configured": False, "companies": [row],
        "coverage": {
            "population": "reference", "side": "all", "families": [], "off_board_companies": None,
            "window": None, "history": None, "last_read_at": None,
        },
    })

    with pytest.raises(insights.OperationError) as refused:
        fit(spec, answer, insights.UnscopedInput(), workspace_id="w")

    assert refused.value.code == "invalid_input"
    assert refused.value.details["reason"] == "over_budget"
    assert fit(spec, answer, insights.UnscopedInput(tier="full"), workspace_id="w").next_cursor is None


def test_an_answer_that_fits_whole_is_not_paged(monkeypatch):
    spec = READS["insights.offer_terms"]
    rows = [{
        "company": f"company-{index}", "listed": False, "ticker": None, "equity_vehicle": None, "vesting": None,
        "vesting_stated_by": None, "bonus_rule": None, "sign_on_bridges_vesting": False, "quote": None,
    } for index in range(3)]
    answer = insights.InsightsOfferTerms.model_validate({
        "feed_configured": False, "companies": rows,
        "coverage": {
            "population": "reference", "side": "all", "families": [], "off_board_companies": None,
            "window": None, "history": None, "last_read_at": None,
        },
    })
    whole = len(json.dumps(answer.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).encode())

    # A budget the whole answer meets exactly, with no room for a page block.
    monkeypatch.setitem(insights.BUDGET_BYTES, "small", whole)
    exact = fit(spec, answer, insights.UnscopedInput(), workspace_id="w")
    assert not exact.shortened and exact.next_cursor is None
    assert exact.data.model_dump(mode="json")["companies"] == rows

    # A byte less, and it pages.
    monkeypatch.setitem(insights.BUDGET_BYTES, "small", whole - 1)
    short = fit(spec, answer, insights.UnscopedInput(), workspace_id="w")
    assert short.shortened and short.next_cursor is not None


def _offer_terms(count: int) -> BaseModel:
    """`count` companies, each larger than a page block, so a page can hold one."""
    return insights.InsightsOfferTerms.model_validate({
        "feed_configured": False,
        "companies": [{
            "company": f"company-{index}-" + "x" * 500, "listed": False, "ticker": None, "equity_vehicle": None,
            "vesting": None, "vesting_stated_by": None, "bonus_rule": None, "sign_on_bridges_vesting": False,
            "quote": None,
        } for index in range(count)],
        "coverage": {
            "population": "reference", "side": "all", "families": [], "off_board_companies": None,
            "window": None, "history": None, "last_read_at": None,
        },
    })


def _bytes(answer: BaseModel) -> int:
    return len(json.dumps(answer.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).encode())


def test_the_last_page_needs_no_room_for_a_cursor(monkeypatch):
    spec = READS["insights.offer_terms"]
    answer = _offer_terms(2)
    monkeypatch.setitem(insights.BUDGET_BYTES, "small", _bytes(answer) - 1)
    first = fit(spec, answer, insights.UnscopedInput(), workspace_id="w")
    assert first.next_cursor is not None and first.data.model_dump()["page"]["returned"] == 1
    rest = insights.UnscopedInput(cursor=first.next_cursor)

    # The smallest budget that reads the last page: with no room held for a
    # cursor it does not need, the page fills that budget to the byte.
    smallest = None
    for budget in range(_bytes(answer), 0, -1):
        monkeypatch.setitem(insights.BUDGET_BYTES, "small", budget)
        try:
            read = fit(spec, answer, rest, workspace_id="w")
        except insights.OperationError:
            break
        smallest = (budget, read)
    assert smallest is not None
    budget, read = smallest

    assert _bytes(read.data) == budget
    assert not read.shortened and read.next_cursor is None
    assert read.data.model_dump()["page"]["returned"] == 1 and read.data.model_dump()["page"]["continue_with"] == []


def test_no_page_at_any_budget_or_position_exceeds_its_budget(monkeypatch):
    spec = READS["insights.offer_terms"]
    answer = _offer_terms(5)
    whole = _bytes(answer)
    for budget in range(40, whole + 200, 7):
        monkeypatch.setitem(insights.BUDGET_BYTES, "small", budget)
        params = insights.UnscopedInput()
        seen: list[str] = []
        while True:
            try:
                read = fit(spec, answer, params, workspace_id="w")
            except insights.OperationError as refused:
                assert refused.details["reason"] == "over_budget", budget
                break
            assert _bytes(read.data) <= budget, (budget, params.cursor)
            seen += [row.company for row in read.data.companies]
            if read.next_cursor is None:
                assert seen == [f"company-{index}-" + "x" * 500 for index in range(5)], budget
                break
            params = insights.UnscopedInput(cursor=read.next_cursor)

    # A cursor at the end of a list that shrank since: the empty page still
    # carries its page block, and that block counts against the budget.
    request = cursor.fingerprint(
        spec.descriptor.id, "w", insights.UnscopedInput().model_dump(mode="json", exclude={"tier", "cursor"})
    )
    at_end = insights.UnscopedInput(cursor=cursor.encode(request=request, offset=5))
    for budget in range(40, whole + 200, 7):
        monkeypatch.setitem(insights.BUDGET_BYTES, "small", budget)
        try:
            read = fit(spec, answer, at_end, workspace_id="w")
        except insights.OperationError as refused:
            assert refused.details["reason"] == "over_budget", budget
            continue
        assert _bytes(read.data) <= budget, budget
        assert read.data.companies == [] and read.next_cursor is None


# --------------------------------------------------------------------------- #
# Shapes: each operation's figures are its route's response, field for field.
# --------------------------------------------------------------------------- #

#: operation id -> the dashboard route's response model.
RESPONSES: dict[str, type[BaseModel]] = {
    "insights.overview": StatisticsOverviewResponse,
    "insights.compensation": CompensationStatsResponse,
    "insights.pay_table": PayTableResponse,
    "insights.trajectory": CompTrajectoryResponse,
    "insights.offer_terms": OfferTermsResponse,
    "insights.levels": LevelGuideResponse,
    "insights.pay_trends": CompTrendsResponse,
    "insights.disclosure_trends": DisclosureTrendsResponse,
    "insights.velocity": VelocityOut,
    "insights.history": InsightsHistoryResponse,
    "insights.demand": DemandResponse,
    "insights.skills": TopSkillsResponse,
}


def _outline(node: Any, defs: dict[str, Any]) -> Any:
    """A schema reduced to what a value can be: property names, types, enums
    and the shapes nested in them; titles, text classes and descriptions aside."""
    if isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str):
            return _outline(defs[reference.removeprefix("#/$defs/")], defs)
        kept = {}
        for key in ("type", "enum", "const", "properties", "items", "anyOf", "additionalProperties", "required"):
            if key in node:
                value = node[key]
                if key == "properties":
                    kept[key] = {name: _outline(prop, defs) for name, prop in value.items()}
                elif key == "anyOf":
                    kept[key] = sorted((_outline(option, defs) for option in value), key=json.dumps)
                elif key == "required":
                    kept[key] = sorted(value)
                elif key == "additionalProperties" and value is False:
                    continue
                else:
                    kept[key] = _outline(value, defs)
        return kept
    return node


def _figures_outline(model: type[BaseModel], *, own: tuple[str, ...] = ()) -> Any:
    schema = model.model_json_schema()
    outline = _outline(schema, schema.get("$defs", {}))
    for name in own:
        outline["properties"].pop(name, None)
        outline["required"] = [field for field in outline.get("required", []) if field != name]
    return outline


@pytest.mark.parametrize("operation", sorted(RESPONSES))
def test_each_operation_reads_its_routes_response_field_for_field(operation):
    descriptor = CATALOG.get(operation)
    assert descriptor is not None and descriptor.result is READS[operation].descriptor.result
    ours = _figures_outline(descriptor.result, own=("coverage", "page"))
    theirs = _figures_outline(RESPONSES[operation])
    if operation == "insights.levels":
        # The route leaves out a cell's unused key; the operation says null.
        cell = ours["properties"]["companies"]["items"]["properties"]["levels"]["additionalProperties"]
        cell["properties"] = {
            name: next(option for option in prop["anyOf"] if option != {"type": "null"})
            for name, prop in cell["properties"].items()
        }
    assert ours == theirs


def test_a_shape_that_drops_a_field_is_caught():
    ours = _figures_outline(insights.InsightsDemand, own=("coverage", "page"))
    ours["properties"].pop("unplaced")

    assert ours != _figures_outline(DemandResponse)


def test_every_route_the_ledger_gives_an_insights_operation_is_one():
    rows = json.loads((Path(__file__).parent / "fixtures" / "agent_coverage_ledger.json").read_text())["rows"]
    named = {row["operation"] for row in rows if str(row.get("operation", "")).startswith("insights.")}
    assert named == set(READS)


def test_no_two_response_models_share_a_name_in_the_schema():
    """A model named like another module's is published under a mangled name,
    which breaks the dashboard's types that name the first one."""
    from tracker.api.app import app

    mangled = [name for name in app.openapi()["components"]["schemas"] if "__" in name]

    assert mangled == []

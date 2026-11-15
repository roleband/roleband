"""Each company read answers what the Companies screen's route answers.

The workspace is `scripts.seed_synthetic`'s, with the company-profile contract's
profiles on top (`tests/company_profiles_contract_seed.py`): a profile whose
facts are all fresh, one with a conflict, a stale fact and a missing one, one
the person pinned a fact on, a hidden company, prices and open roles. Each
operation runs over real ASGI beside the dashboard route it shares a service
with (`profiles.read`), and the comparison is field by field, so a value
either side drops, renames or computes differently fails it.

The deliberate differences are asserted as differences: a hidden company and
an unknown slug are `not_found` here, where the screen answers both.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from scripts.seed_synthetic import seed
from tests.company_profiles_contract_seed import (
    PLUGIN,
    TODAY,
    install_plugin,
    pin_profile_clock,
    seed_company_profiles,
)
from tests.factories import make_company
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.companies import (
    COMPANIES_FACTS_LIST,
    COMPANIES_GET,
    COMPANIES_LIST,
    COMPANIES_PRICES_GET,
    COMPANY_COLUMNS,
    PROFILE_PLACES,
)
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.search import PAGE_BUDGET_BYTES
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import PREFIX
from tracker.db.models import CompanyProfile, TrackedCompany
from tracker.prices.provider import FIXTURE_SOURCE, Bar
from tracker.profiles import prices as price_store

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

#: Each operation with its smallest successful call.
READS = {
    COMPANIES_LIST.id: "/companies",
    COMPANIES_GET.id: "/companies/google",
    COMPANIES_FACTS_LIST.id: "/companies/google/facts",
    COMPANIES_PRICES_GET.id: "/companies/google/prices",
}

#: The seeded profiles the person follows.
FOLLOWED = ("google", "reddit", "anthropic")


def _moment(value: str | None) -> datetime | None:
    """A timestamp as either side spells it (`Z` or `+00:00`)."""
    return datetime.fromisoformat(value) if value else None


@pytest_asyncio.fixture
async def workspace(db_session, api_client, monkeypatch):
    """The synthetic workspace with the profiles on top and agent reads on."""
    pin_profile_clock(monkeypatch)
    await seed(db_session, 8, seed_value=1, derived=False, agent_tasks=True)
    await db_session.commit()
    await seed_company_profiles(db_session)
    # Each seeded profile is a company the person follows, so it is on the roster
    # and hiding it is a switch on its register row.
    tracked = set((await db_session.execute(
        select(TrackedCompany.slug).where(TrackedCompany.slug.in_(FOLLOWED))
    )).scalars())
    db_session.add_all(make_company(slug, slug.title()) for slug in FOLLOWED if slug not in tracked)
    await db_session.execute(
        update(TrackedCompany).where(TrackedCompany.slug.in_(FOLLOWED)).values(enabled=True, status="active")
    )
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    return db_session


async def _agent(api_client, path: str, **params):
    response = await api_client.get(f"{PREFIX}{path}", params=params)
    return response, response.json()


async def _screen(api_client, path: str, **params) -> dict:
    response = await api_client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _data(body: dict) -> dict:
    assert body["ok"] is True, body["error"]
    return body["data"]


def _error(response, body: dict, code: str, exit_status: int) -> None:
    assert body["ok"] is False and body["data"] is None
    assert body["error"]["code"] == code
    assert outcome(code).exit_status == exit_status
    assert response.status_code == outcome(code).http_status


def _bytes(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


async def _every_row(api_client, path: str, **params) -> tuple[list, list[dict]]:
    """Every row of a paged read, following next_cursor, and each page's body."""
    rows: list = []
    bodies: list[dict] = []
    cursor = None
    while True:
        _, body = await _agent(api_client, path, **params, **({"cursor": cursor} if cursor else {}))
        rows.extend(_data(body)["rows"])
        bodies.append(body)
        cursor = body["meta"]["next_cursor"]
        if cursor is None:
            return rows, bodies
        assert len(bodies) < 100


def _as_row(item: dict, open_roles: int) -> list:
    """A roster item as `companies.list` positions it."""
    return [
        item["slug"], item["display_name"], item["ticker"], item["is_public"], item["sectors"], item["in_dataset"],
        item["data_health"], item["headcount"], item["mapped_levels"], open_roles, item["price"],
        item["change_pct"], item["currency"], item["price_as_of"],
    ]


# --------------------------------------------------------------------------- #
# companies.list  <-  GET /api/company-profiles (+ /api/companies/open-counts)
# --------------------------------------------------------------------------- #


async def test_the_list_is_the_screens_roster_a_to_z(api_client, workspace):
    roster = await _screen(api_client, "/api/company-profiles")
    counts = (await _screen(api_client, "/api/companies/open-counts"))["counts"]
    expected = sorted(
        (_as_row(item, counts.get(item["slug"], 0)) for item in roster["items"]),
        key=lambda row: (row[1].casefold(), row[0]),
    )

    rows, bodies = await _every_row(api_client, "/companies", limit=100)

    assert rows == expected
    data = _data(bodies[0])
    assert data["columns"] == list(COMPANY_COLUMNS)
    assert data["total"] == len(expected) and data["sectors"] == roster["sectors"]
    # The seeded roster is not trivial: priced, researched and reviewed companies are in it.
    by_slug = {row[0]: row for row in rows}
    assert by_slug["google"][10] == 213.95 and by_slug["google"][9] >= 4
    assert by_slug["reddit"][6] != "ok"
    assert "hidden-co" not in by_slug
    assert bodies[0]["meta"]["data_classes"] == ["market_statistic"]


async def test_each_filter_narrows_as_the_screen_does(api_client, workspace):
    roster = (await _screen(api_client, "/api/company-profiles"))["items"]

    async def slugs(**params) -> list[str]:
        rows, _ = await _every_row(api_client, "/companies", limit=100, **params)
        return [row[0] for row in rows]

    everyone = await slugs()
    # The search box: name, slug or ticker, case-blind.
    assert await slugs(query="rddt") == ["reddit"]
    assert await slugs(query="Goo") == ["google"]
    # The review switch: every company whose health is not ok, and only those.
    review = await slugs(needs_review="true")
    assert review and set(review) == {item["slug"] for item in roster if item["data_health"] != "ok"}
    assert set(review) < set(everyone)
    # Researched and sector, as the roster groups them.
    researched = await slugs(researched="true")
    assert set(researched) == {item["slug"] for item in roster if item["in_dataset"]}
    assert set(await slugs(researched="false")) == set(everyone) - set(researched)
    faang = await slugs(sector="faang")
    assert faang and set(faang) == {item["slug"] for item in roster if "faang" in item["sectors"]}
    both = await slugs(sector=["faang", "ai"])
    assert set(both) == {item["slug"] for item in roster if {"faang", "ai"} & set(item["sectors"])}


async def test_an_unknown_sector_is_refused_with_the_accepted_ones(api_client, workspace):
    response, body = await _agent(api_client, "/companies", sector=["faang", "fanng"])

    _error(response, body, "invalid_input", 2)
    assert body["error"]["details"]["unknown"] == ["fanng"]
    assert "faang" in body["error"]["details"]["accepted"]


async def test_pages_read_every_company_once_and_a_cursor_binds_its_filters(api_client, workspace):
    whole, _ = await _every_row(api_client, "/companies", limit=100)
    assert len(whole) >= 3

    paged, bodies = await _every_row(api_client, "/companies", limit=2)

    assert paged == whole
    assert len(bodies) == -(-len(whole) // 2)
    cursor = bodies[0]["meta"]["next_cursor"]
    response, body = await _agent(api_client, "/companies", limit=2, cursor=cursor, query="goo")
    _error(response, body, "invalid_input", 2)
    assert body["error"]["details"] == {"field": "cursor", "reason": "other_request"}


async def test_a_page_stays_within_the_small_budget_and_says_it_stopped_early(api_client, workspace):
    # Enough long-named companies to fill a small page before its limit.
    workspace.add_all(
        CompanyProfile(slug=f"long-{n:03}", display_name=f"Long {n:03} " + "x" * 110) for n in range(60)
    )
    await workspace.commit()

    rows, bodies = await _every_row(api_client, "/companies", limit=100)

    first = bodies[0]
    assert [w["code"] for w in first["warnings"]] == ["page_shortened"]
    assert _data(first)["count"] < _data(first)["total"] <= 100
    for body in bodies:
        assert _bytes(_data(body)) <= PAGE_BUDGET_BYTES["small"]
    assert len(rows) == _data(first)["total"]
    assert len({row[0] for row in rows}) == len(rows)


# --------------------------------------------------------------------------- #
# companies.get  <-  GET /api/company-profiles/{slug}
# --------------------------------------------------------------------------- #


_BASIS = {"blueprint": "seed", "roleband": "dataset", "reported": "estimated", "sec_edgar": "official",
          "manual": "human"}


@pytest.mark.parametrize("slug", ["google", "reddit", "anthropic"])
async def test_the_profile_view_is_the_screens_profile(api_client, workspace, slug):
    screen = await _screen(api_client, f"/api/company-profiles/{slug}")

    _, body = await _agent(api_client, f"/companies/{slug}")

    data = _data(body)
    assert data["view"] == "profile" and data["slug"] == slug and data["name"] == screen["display_name"]
    assert data["health"] == screen["data_health"]
    # Every fact, in the screen's order, with the provenance it shows.
    assert [fact["field"] for fact in data["facts"]] == list(screen["fields"])
    for fact in data["facts"]:
        shown = screen["fields"][fact["field"]]
        assert (fact["value"], fact["source"], _moment(fact["observed_at"]), fact["freshness"], fact["pinned"]) == (
            shown["value"], shown["source"], _moment(shown["observed_at"]), shown["freshness"], shown["is_manual"],
        ), fact["field"]
        assert fact["basis"] == (_BASIS[shown["source"]] if shown["source"] else None)
        assert [(c["value"], c["source"]) for c in fact["conflicts"]] == [
            (c["value"], c["source"]) for c in shown["conflicts"]
        ]
    assert [(item["field"], item["reason"]) for item in data["needs_review"]] == [
        (item["field"], item["reason"]) for item in screen["needs_review"]
    ]
    # Pay, as the screen lists it.
    assert [(r["level"], r["band"], r["total_median"], r["base"], r["stock"], r["bonus"], r["source"])
            for r in data["pay"]["levels"]] == [
        (r["level_label"], r["band"], r["tc_median"], r["base_amount"], r["stock_amount"], r["bonus_amount"],
         r["source"])
        for r in screen["comp_levels"]
    ]
    assert data["pay"]["level_base"] == screen["level_base"]
    assert data["pay"]["offer_policy"] == screen["offer_policy"]
    assert data["pay"]["notes"] == screen["comp_notes"]
    assert data["benefits"] == sum(len(group["items"]) for group in screen["benefits"])
    assert (data["open_roles"], data["unfollowed"]) == (screen["open_roles"], screen["unfollowed"])
    assert data["place_count"] == len(screen["locations"])
    assert [(p["city"], p["open_roles"], p["country"], p["is_hq"]) for p in data["places"]] == [
        (loc["city"], loc["open_count"], loc["country"], loc["is_hq"]) for loc in screen["locations"][:PROFILE_PLACES]
    ]
    prices = await _screen(api_client, f"/api/company-profiles/{slug}/prices")
    assert data["price"] == prices["latest"]


async def test_the_profile_tells_stated_from_estimated_and_the_persons_pin(api_client, workspace):
    google = {f["field"]: f for f in _data((await _agent(api_client, "/companies/google"))[1])["facts"]}
    anthropic = {f["field"]: f for f in _data((await _agent(api_client, "/companies/anthropic"))[1])["facts"]}
    reddit = _data((await _agent(api_client, "/companies/reddit"))[1])

    assert (google["headcount"]["value"], google["headcount"]["basis"]) == (182502, "estimated")
    assert google["hq_city"]["basis"] == "dataset"
    assert (anthropic["headcount"]["value"], anthropic["headcount"]["basis"]) == (1100, "human")
    assert anthropic["headcount"]["pinned"] is True
    # A filing against a report: the conflict names both sides' basis.
    ticker = next(f for f in reddit["facts"] if f["field"] == "ticker")
    assert ticker["basis"] == "official"
    assert [c["basis"] for c in ticker["conflicts"]] == ["estimated"]
    assert {item["reason"] for item in reddit["needs_review"]} == {"conflict", "stale", "missing"}
    # An offer fact says who states it.
    offer = _data((await _agent(api_client, "/companies/google"))[1])["pay"]["offer_policy"]
    assert offer is None or {fact["stated_by"] for fact in offer["facts"]} <= {"employer", "estimated", None}


async def test_a_plugins_fact_is_named_as_the_plugins(api_client, workspace):
    await install_plugin(workspace)
    screen = await _screen(api_client, "/api/company-profiles/google")

    data = _data((await _agent(api_client, "/companies/google"))[1])

    headcount = next(f for f in data["facts"] if f["field"] == "headcount")
    assert headcount["value"] == screen["fields"]["headcount"]["value"] == 180000
    assert (headcount["basis"], headcount["answered_by"]) == ("plugin", PLUGIN)
    assert data["pay"]["answered_by"]["plugin"] == PLUGIN
    assert data["attribution"] == screen["attribution"]


@pytest.mark.parametrize("view", ["benefits", "locations"])
async def test_the_list_views_page_the_screens_lists_whole(api_client, workspace, view):
    screen = await _screen(api_client, "/api/company-profiles/google")
    if view == "benefits":
        expected = [
            [group["category"], item["benefit_type"], item["name"], item["value_usd"], item["value_text"],
             item["description"], item["kind"], item["country"], item["reviewed"], item["mentions"], item["provider"]]
            for group in screen["benefits"] for item in group["items"]
        ]
    else:
        expected = [[loc["city"], loc["open_count"], loc["country"], loc["is_hq"]] for loc in screen["locations"]]
    assert expected

    rows, bodies = await _every_row(api_client, "/companies/google", view=view, limit=1)

    assert rows == expected
    assert len(bodies) == len(expected)
    assert all(_data(body)["view"] == view and _data(body)["total"] == len(expected) for body in bodies)


async def test_a_cursor_does_not_page_the_profile_view(api_client, workspace):
    _, first = await _agent(api_client, "/companies/google", view="locations", limit=1)
    cursor = first["meta"]["next_cursor"]
    assert cursor

    response, body = await _agent(api_client, "/companies/google", cursor=cursor)
    _error(response, body, "invalid_input", 2)
    # Nor does one cursor read another view.
    response, body = await _agent(api_client, "/companies/google", view="benefits", cursor=cursor)
    _error(response, body, "invalid_input", 2)


# --------------------------------------------------------------------------- #
# companies.facts.list  <-  GET /api/company-profiles/{slug}/claims
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", ["google", "reddit", "anthropic"])
async def test_the_claims_are_the_screens_claims(api_client, workspace, slug):
    claims = (await _screen(api_client, f"/api/company-profiles/{slug}/claims"))["claims"]
    assert claims

    rows, _ = await _every_row(api_client, f"/companies/{slug}/facts", limit=100)

    assert rows == [
        [c["field"], c["value"], c["source"], _BASIS.get(c["source"], "plugin"), c["rank"], c["observed_at"]]
        for c in claims
    ]
    headcount, _ = await _every_row(api_client, f"/companies/{slug}/facts", field="headcount")
    assert headcount == [row for row in rows if row[0] == "headcount"]


# --------------------------------------------------------------------------- #
# companies.prices.get  <-  GET /api/company-profiles/{slug}/prices
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("price_range", ["1m", "3m", "6m", "1y"])
async def test_the_bars_are_the_screens_bars_for_each_range(api_client, workspace, price_range):
    screen = await _screen(api_client, "/api/company-profiles/google/prices", range=price_range)

    _, body = await _agent(api_client, "/companies/google/prices", range=price_range)

    data = _data(body)
    assert data["rows"] == [[b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"]] for b in screen["bars"]]
    assert (data["range"], data["currency"], data["latest"], data["attribution"], data["feed_configured"]) == (
        screen["range"], screen["currency"], screen["latest"], screen["attribution"], screen["feed_configured"],
    )
    assert body["meta"]["next_cursor"] is None


async def test_a_range_the_screen_reads_as_its_default_is_refused_here(api_client, workspace):
    assert (await _screen(api_client, "/api/company-profiles/google/prices", range="5y"))["range"] == "3m"

    response, body = await _agent(api_client, "/companies/google/prices", range="5y")

    _error(response, body, "invalid_input", 2)


async def test_a_year_of_bars_pages_within_the_small_budget(api_client, workspace):
    await price_store.upsert_history(
        workspace, "google",
        [Bar(TODAY - timedelta(days=day), 200.0 + day, 201.5, 198.25, 200.5 + day, 1_000_000 + day)
         for day in range(3, 360)],
        FIXTURE_SOURCE,
    )
    await workspace.commit()
    screen = await _screen(api_client, "/api/company-profiles/google/prices", range="1y")
    assert len(screen["bars"]) > 300

    rows, bodies = await _every_row(api_client, "/companies/google/prices", range="1y")

    assert rows == [[b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"]] for b in screen["bars"]]
    assert len(bodies) > 1
    assert all(_bytes(_data(body)) <= PAGE_BUDGET_BYTES["small"] for body in bodies)
    assert [w["code"] for w in bodies[0]["warnings"]] == ["page_shortened"]


# --------------------------------------------------------------------------- #
# What every company read shares
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ["/companies/nobody", "/companies/nobody/facts", "/companies/nobody/prices"])
async def test_an_unknown_company_is_not_found_where_the_screen_answers_empty(api_client, workspace, path):
    assert (await _screen(api_client, "/api/company-profiles/nobody/claims"))["claims"] == []

    response, body = await _agent(api_client, path)

    _error(response, body, "not_found", 5)
    assert body["error"]["details"] == {"company": "nobody"}


@pytest.mark.parametrize("path", ["/companies/hidden-co", "/companies/hidden-co/facts", "/companies/hidden-co/prices"])
async def test_a_company_the_person_hid_is_not_found_though_the_screen_opens_it(api_client, workspace, path):
    assert (await _screen(api_client, "/api/company-profiles/hidden-co"))["slug"] == "hidden-co"

    response, body = await _agent(api_client, path)

    _error(response, body, "not_found", 5)


async def test_hiding_a_company_takes_it_off_the_list_and_out_of_reach(api_client, workspace):
    before = [row[0] for row in (await _every_row(api_client, "/companies", limit=100))[0]]
    assert "reddit" in before
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == "reddit").values(visible=False))
    await workspace.commit()

    after = [row[0] for row in (await _every_row(api_client, "/companies", limit=100))[0]]

    assert after == [slug for slug in before if slug != "reddit"]
    response, body = await _agent(api_client, "/companies/reddit")
    _error(response, body, "not_found", 5)


async def test_opt_out_refuses_every_company_read(api_client, workspace):
    await set_agent_access(workspace, AgentAccessConfig(enabled=False, allow_writes=False))
    await workspace.commit()

    for operation, path in READS.items():
        response, body = await _agent(api_client, path)
        _error(response, body, "access_disabled", 4)
        assert body["operation"] == operation and body["workspace_id"] is None


async def test_every_company_read_answers_when_on_and_refuses_an_unknown_key(api_client, workspace):
    for operation, path in READS.items():
        response, body = await _agent(api_client, path)
        assert response.status_code == 200 and body["operation"] == operation, body

        response, body = await _agent(api_client, path, verbose="1")
        _error(response, body, "invalid_input", 2)

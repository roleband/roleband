"""What the read operations answer for a small board whose every row is known.

`test_agent_search.py` holds search to the Board over a seeded corpus. Here the
board is four postings, a hidden company and a pursuit or two, so each
assertion names the exact rows it expects: what is in scope, how each sort and
filter narrows, how a place is read, how old a posting is, what pay the
employer stated, which counts the radar summary gives and how a pursuit list
is ordered. Real Postgres, through the agent router over ASGI: a visibility
join, an array overlap and a NULLS LAST sort cannot be judged against a fake
session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

import tracker.agents.operations.search as search_ops
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import PREFIX
from tracker.company_store import off_board_company_slugs
from tracker.db.models import Favorite, Job, JobFeedback, Pursuit, TrackedCompany
from tracker.db.queries.jobs import open_in_scope_count_stmt
from tracker.enrich.classify import location_slugs_for
from tracker.notifications.pursuit_due import overdue_pursuit_clause
from tracker.settings_store import set_enabled_locations

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _job(
    job_id: int,
    company: str = "openai",
    *,
    title: str = "Staff Product Manager",
    comp_median: int | None = 600_000,
    first_seen: datetime | None = None,
    in_scope: bool = True,
    status: str = "open",
    structured: bool = False,
    locations: list[str] | None = None,
) -> Job:
    return Job(
        id=job_id,
        company=company,
        req_id=f"r{job_id}",
        dedupe_key=f"{company}:r{job_id}",
        title=title,
        url=f"https://careers.example.test/{job_id}",
        locations=["San Francisco, CA"],
        location_groups=locations or ["silicon_valley"],
        workplace_type="hybrid",
        level_band="staff",
        family="product_management",
        track="product_program",
        department="Product",
        team="Platform",
        description_text="Own the roadmap for inference platform products.",
        description_sections=[{"key": "about", "title": "About", "content": "Own the roadmap."}],
        status=status,
        in_scope=in_scope,
        comp_low=500_000,
        comp_median=comp_median,
        comp_high=700_000,
        comp_currency="USD",
        comp_provenance="model",
        disclosed_base_min=300_000 if structured else None,
        disclosed_base_max=360_000 if structured else None,
        disclosed_currency="USD" if structured else None,
        disclosed_pay_basis="base" if structured else None,
        disclosed_pay_period="year" if structured else None,
        disclosed_snippet="$300,000 - $360,000" if structured else None,
        structured_at=NOW if structured else None,
        first_seen=first_seen or NOW - timedelta(days=10),
        last_seen=NOW,
    )


def _company(slug: str, *, visible: bool = True) -> TrackedCompany:
    return TrackedCompany(
        slug=slug, display=slug.title(), adapter="greenhouse", status="active",
        enabled=True, visible=visible, source="catalog",
    )


@pytest_asyncio.fixture
async def session(db_session, scratch_scope, monkeypatch):
    """Agent reads on, the workspace made, and no embedding model loaded."""

    async def no_vector(_text: str) -> list[float]:
        return []

    monkeypatch.setattr(search_ops, "embed_query", no_vector)
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    return db_session


async def _seed_board(session) -> dict[str, int]:
    """Five postings: two visible, in scope and open; one at a hidden company;
    one out of scope; one closed."""
    session.add_all([_company("openai"), _company("anthropic"), _company("shadow", visible=False)])
    jobs = {
        "newest": _job(1, "openai", first_seen=NOW - timedelta(days=1), comp_median=400_000),
        "richest": _job(2, "anthropic", first_seen=NOW - timedelta(days=30), comp_median=900_000),
        "hidden_company": _job(3, "shadow"),
        "out_of_scope": _job(4, "openai", in_scope=False),
        "closed": _job(5, "openai", status="closed"),
    }
    session.add_all(jobs.values())
    await session.commit()
    return {name: job.id for name, job in jobs.items()}


async def _get(api_client, path: str, **params):
    response = await api_client.get(f"{PREFIX}{path}", params=params)
    return response, response.json()


async def _ids(api_client, **params) -> list[int]:
    response, body = await _get(api_client, "/opportunities", **params)
    assert body["ok"] is True, body["error"]
    assert response.status_code == 200
    return [row[0] for row in body["data"]["rows"]]


async def _detail(api_client, job_id: int) -> dict:
    _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="full")
    assert body["ok"] is True, body["error"]
    return body["data"]


async def _summary(api_client, job_id: int) -> dict:
    _, body = await _get(api_client, f"/opportunities/{job_id}")
    assert body["ok"] is True, body["error"]
    return body["data"]


# --------------------------------------------------------------------------- #
# Search: what is listed, in what order
# --------------------------------------------------------------------------- #


async def test_search_lists_only_visible_in_scope_open_postings(api_client, session):
    ids = await _seed_board(session)

    listed = await _ids(api_client)

    assert listed == [ids["newest"], ids["richest"]]
    for left_out in ("hidden_company", "out_of_scope", "closed"):
        assert ids[left_out] not in listed


@pytest.mark.parametrize(
    ("sort", "order", "expected"),
    [
        ("newest", "desc", ["newest", "richest"]),
        ("newest", "asc", ["richest", "newest"]),
        ("estimated_pay", "desc", ["richest", "newest"]),
        ("estimated_pay", "asc", ["newest", "richest"]),
    ],
)
async def test_each_sort_orders_the_board_the_way_it_is_named(api_client, session, sort, order, expected):
    ids = await _seed_board(session)

    assert await _ids(api_client, sort=sort, order=order) == [ids[name] for name in expected]


async def test_rows_that_tie_on_the_sort_key_break_by_id_descending(api_client, session):
    session.add(_company("openai"))
    same = NOW - timedelta(days=3)
    session.add_all([_job(n, "openai", first_seen=same) for n in (11, 12, 13)])
    await session.commit()

    assert await _ids(api_client) == [13, 12, 11]
    assert await _ids(api_client, order="asc") == [13, 12, 11], "the tie-break does not follow the direction"
    assert await _ids(api_client, limit=2) == [13, 12]


@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_a_posting_without_an_estimate_sorts_last_on_estimated_pay(api_client, session, order):
    session.add(_company("openai"))
    session.add_all([_job(21, "openai", comp_median=None), _job(22, "openai", comp_median=100_000)])
    await session.commit()

    assert await _ids(api_client, sort="estimated_pay", order=order) == [22, 21]


async def test_saved_only_narrows_to_saved_postings_and_marks_them(api_client, session):
    ids = await _seed_board(session)
    session.add(Favorite(job_id=ids["richest"]))
    await session.commit()

    _, body = await _get(api_client, "/opportunities", saved_only="true")

    page = body["data"]
    assert [row[0] for row in page["rows"]] == [ids["richest"]]
    assert page["rows"][0][page["columns"].index("pursuit")] == "saved"


async def test_saved_only_keeps_a_role_the_reader_hid_or_dismissed(api_client, session):
    """A saved role stays reachable after the reader dismisses it or hides its
    company, as on Saved; the ordinary board still answers neither of them."""
    ids = await _seed_board(session)
    session.add_all([
        Favorite(job_id=ids["richest"]),
        Favorite(job_id=ids["hidden_company"]),
        JobFeedback(job_id=ids["richest"], verdict="dismissed", created_at=NOW),
    ])
    await session.commit()

    assert set(await _ids(api_client, saved_only="true")) == {ids["richest"], ids["hidden_company"]}
    assert await _ids(api_client) == [ids["newest"]]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"query": "product manager"}, ["newest", "richest"]),
        ({"query": "quantum"}, []),
        ({"company": ["anthropic"]}, ["richest"]),
        ({"company": ["anthropic", "openai"]}, ["newest", "richest"]),
        ({"family": ["product_management"]}, ["newest", "richest"]),
        ({"family": ["software_engineering"]}, []),
        ({"location": ["silicon_valley"]}, ["newest", "richest"]),
        ({"location": ["new_york"]}, []),
        ({"minimum_estimated_pay": 500_000}, ["richest"]),
        ({"company": ["anthropic"], "minimum_estimated_pay": 1_000_000}, []),
    ],
    ids=[
        "text_matches_title", "text_matches_nothing", "one_company", "either_company", "family",
        "other_family", "location_overlap", "other_location", "pay_floor", "filters_are_anded",
    ],
)
async def test_each_filter_narrows_to_exactly_the_rows_it_names(api_client, session, filters, expected):
    ids = await _seed_board(session)

    found = await _ids(api_client, **filters)

    assert sorted(found) == sorted(ids[name] for name in expected)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"family": ["Product Management"]}, ["newest", "richest"]),
        ({"family": ["product-management"]}, ["newest", "richest"]),
        ({"company": ["OpenAI"]}, ["newest"]),
        ({"location": ["Silicon Valley"]}, ["newest", "richest"]),
        ({"location": ["NEW YORK"]}, []),
    ],
    ids=["family_by_name", "family_hyphenated", "company_by_name", "location_by_name", "known_location_true_zero"],
)
async def test_a_persons_spelling_resolves_to_the_slug(api_client, session, filters, expected):
    """Case, spaces and hyphens are spelling, not meaning. A known value that
    matches no posting still narrows to zero: that zero is true."""
    ids = await _seed_board(session)

    response, body = await _get(api_client, "/opportunities", **filters)

    assert body["ok"] is True, body["error"]
    assert sorted(row[0] for row in body["data"]["rows"]) == sorted(ids[name] for name in expected)


async def test_a_company_search_is_told_apart_from_an_unknown_company(api_client, session):
    ids = await _seed_board(session)

    known = await _ids(api_client, company=["anthropic"])
    response, unknown = await _get(api_client, "/opportunities", company=["anthropic", "Initech"])

    assert known == [ids["richest"]]
    assert unknown["ok"] is False and unknown["error"]["code"] == "invalid_input"
    assert unknown["error"]["details"]["unknown"] == [{"filter": "company", "value": "Initech"}]


async def _seed_places(session) -> dict[str, int]:
    """Three postings tagged the way enrichment tags them: Seattle (its
    GeoNames city under the Pacific Northwest), Redmond (the same metro, no
    Seattle) and Seoul."""
    session.add_all([_company("openai"), _company("anthropic")])
    places = {"seattle": "Seattle, WA, USA", "redmond": "Redmond, WA, USA", "seoul": "Seoul, South Korea"}
    jobs = {}
    for n, (name, place) in enumerate(places.items(), start=41):
        job = _job(n, "openai" if n % 2 else "anthropic", locations=location_slugs_for([place]))
        job.locations = [place]
        jobs[name] = job
    session.add_all(jobs.values())
    await session.commit()
    return {name: job.id for name, job in jobs.items()}


@pytest.mark.parametrize(
    ("value", "tracked_city", "expected"),
    [
        ("Seattle", False, ["seattle", "redmond"]),
        pytest.param(
            "Seattle", True, ["seattle"],
            marks=pytest.mark.xfail(
                strict=True,
                reason="a tracked city and the metro holding it share the name, so the lookup refuses both",
            ),
        ),
        ("USA", False, ["seattle", "redmond"]),
        ("Korea", False, ["seoul"]),
        ("Bay Area", False, []),
    ],
    ids=["city_as_its_metro", "tracked_city", "country_alias", "short_country_name", "metro_place_true_zero"],
)
async def test_a_place_resolves_the_way_the_search_box_and_the_board_read_it(
    api_client, session, value, tracked_city, expected
):
    """A city the person tracks is the city; any other is the metro that holds
    it. Slugs and display names alone would refuse "USA" or "Bay Area"."""
    ids = await _seed_places(session)
    seattle = next(s for s in location_slugs_for(["Seattle, WA, USA"]) if s.startswith("city_"))
    if tracked_city:
        await set_enabled_locations(session, ["united_states", "pacific_northwest", seattle])
        await session.commit()

    found = await _ids(api_client, location=[value])

    assert sorted(found) == sorted(ids[name] for name in expected)


async def test_listed_within_days_counts_the_age_each_row_shows(api_client, session):
    """The window reads the listing age: the earlier of the employer's date
    and the first sighting. A posting the employer re-stamped today is still as
    old as RoleBand's first sighting of it."""
    ids = await _seed_board(session)
    real_now = datetime.now(UTC)
    for name, days in (("newest", 2), ("richest", 30)):
        job = await session.get(Job, ids[name])
        job.first_seen = real_now - timedelta(days=days)
        job.posted_at = real_now
    await session.commit()

    assert await _ids(api_client, listed_within_days=7) == [ids["newest"]]
    assert sorted(await _ids(api_client, listed_within_days=60)) == sorted([ids["newest"], ids["richest"]])
    for window in (0, 100_000):
        response, body = await _get(api_client, "/opportunities", listed_within_days=window)
        assert body["ok"] is False and body["error"]["code"] == "invalid_input", window
        assert [e["location"] for e in body["error"]["details"]["errors"]] == [["listed_within_days"]]


# --------------------------------------------------------------------------- #
# One opportunity
# --------------------------------------------------------------------------- #


async def test_the_full_text_is_in_the_detail_and_not_in_a_search_row(api_client, session):
    ids = await _seed_board(session)
    text = {"department", "team", "description", "description_sections"}

    detail = await _detail(api_client, ids["newest"])
    summary = await _summary(api_client, ids["newest"])
    _, body = await _get(api_client, "/opportunities")

    assert text <= set(detail) and detail["listed_days"] is not None
    assert not text & set(summary)
    assert not text & set(body["data"]["columns"])
    assert "Own the roadmap for inference platform products." in detail["description"]


async def test_the_age_an_agent_reads_is_the_age_the_board_shows(api_client, session):
    """One listing age, from the earlier of the employer's date and the first
    sighting. A posting the employer dated 164 days ago is not 2 days old,
    though `newest` orders by first sighting."""
    session.add(_company("openai"))
    real_now = datetime.now(UTC)
    employer_dated = _job(51, "openai", first_seen=real_now - timedelta(days=2, hours=1))
    employer_dated.posted_at = employer_dated.first_posted_at = real_now - timedelta(days=164, hours=1)
    watched = _job(52, "openai", first_seen=real_now - timedelta(days=30, hours=1))
    watched.posted_at = watched.first_posted_at = real_now - timedelta(days=30, hours=1)
    session.add_all([employer_dated, watched])
    await session.commit()

    _, body = await _get(api_client, "/opportunities", sort="age", order="desc")
    page = body["data"]
    days = {row[0]: row[page["columns"].index("listed_days")] for row in page["rows"]}
    youngest_first = await _ids(api_client, sort="age", order="asc")
    by_sighting = await _ids(api_client, sort="newest")
    detail = await _detail(api_client, 51)
    sighted = await _detail(api_client, 52)

    assert days == {51: 164, 52: 30}
    assert [row[0] for row in page["rows"]] == [51, 52]
    assert youngest_first == [52, 51], "the age sort follows the age shown, not the sighting"
    assert by_sighting == [51, 52], "newest is the order RoleBand first saw them"
    assert (detail["listed_days"], detail["listed_basis"]) == (164, "employer")
    assert sighted["listed_basis"] == "sighting"
    assert "days_open" not in detail, "one age per posting, not a second clock beside it"


async def test_the_history_is_the_one_the_history_route_answers(api_client, session):
    session.add(_company("openai"))
    real_now = datetime.now(UTC)
    job = _job(61, "openai", first_seen=real_now - timedelta(days=20, hours=1))
    job.posted_at = real_now - timedelta(days=5)
    job.first_posted_at = real_now - timedelta(days=90, hours=1)
    session.add(job)
    await session.commit()

    _, body = await _get(api_client, "/opportunities/61/history")
    route = (await api_client.get("/api/jobs/61/history")).json()

    answer = body["data"]
    assert answer["headline"]["days"] == 90 and answer["headline"]["basis"] == "employer"
    assert [e["kind"] for e in answer["events"]] == [e["kind"] for e in route["events"]]
    assert answer["events"], "an empty history would agree with an empty route"
    assert set(route) == {"headline", "role", "events", "unconfirmed"}
    assert set(route) <= set(answer)


async def test_employer_stated_pay_is_absent_until_the_posting_was_parsed(api_client, session):
    """An unparsed posting has no pay block at all; an empty one would read as
    "the employer disclosed nothing", a different claim."""
    session.add(_company("openai"))
    session.add_all([_job(31, "openai"), _job(32, "openai", structured=True)])
    await session.commit()

    unparsed = await _summary(api_client, 31)
    parsed = await _summary(api_client, 32)

    assert unparsed["employer_stated_pay"] is None
    assert parsed["employer_stated_pay"]["low"] == 300_000
    assert parsed["employer_stated_pay"]["snippet"] == "$300,000 - $360,000"
    assert parsed["employer_stated_pay"]["basis"] == "base"
    assert unparsed["estimated_total_comp"]["provenance"] == "model"


async def test_a_checked_posting_that_states_no_pay_has_no_period(api_client, session):
    """With no stated amount the period guard has nothing to check, so an
    absent band makes no period claim; an hourly-sized amount stored as yearly
    is still served as a contradiction."""
    session.add(_company("openai"))
    silent = _job(33, "openai")
    silent.structured_at = NOW
    rate_stored_yearly = _job(34, "openai", structured=True)
    rate_stored_yearly.disclosed_base_min, rate_stored_yearly.disclosed_base_max = 104, 120
    session.add_all([silent, rate_stored_yearly])
    await session.commit()

    stated = (await _summary(api_client, 33))["employer_stated_pay"]
    assert stated["low"] is None and stated["period"] is None
    assert (await _summary(api_client, 34))["employer_stated_pay"]["period"] == "unclear"


async def test_a_base_only_estimate_is_a_base_never_an_empty_total(api_client, session):
    session.add(_company("openai"))
    base_only = _job(41, "openai", comp_median=None)
    base_only.comp_component, base_only.comp_provider = "base", "builtin"
    base_only.comp_low = base_only.comp_high = None
    base_only.comp_base_low, base_only.comp_base_median, base_only.comp_base_high = 255_000, 300_000, 345_000
    total = _job(42, "openai")
    total.comp_component = "total"
    session.add_all([base_only, total])
    await session.commit()

    got = await _summary(api_client, 41)
    priced = await _summary(api_client, 42)

    assert got["estimated_total_comp"] is None
    assert got["estimate_component"] == "base"
    assert got["estimated_base"] == {
        "low": 255_000, "median": 300_000, "high": 345_000, "currency": "USD", "provider": "builtin", "as_of": None,
    }
    assert priced["estimate_component"] == "total" and priced["estimated_total_comp"]["median"] == 600_000
    assert priced["estimated_base"] is None


# --------------------------------------------------------------------------- #
# Pursuits, read
# --------------------------------------------------------------------------- #


async def _seed_pursuits(session) -> dict[str, int]:
    ids = await _seed_board(session)
    session.add_all([
        Pursuit(job_id=ids["newest"], stage="applied", priority=2, updated_at=NOW),
        Pursuit(job_id=ids["richest"], stage="offer", priority=4, updated_at=NOW),
    ])
    await session.commit()
    return ids


async def test_pursuits_are_listed_by_priority_then_recency(api_client, session):
    ids = await _seed_pursuits(session)

    _, body = await _get(api_client, "/pursuits")

    items = body["data"]["items"]
    assert [item["opportunity_id"] for item in items] == [ids["richest"], ids["newest"]]
    assert body["data"]["count"] == 2
    assert items[0]["opportunity"]["company"] == "anthropic"


async def test_pursuits_of_equal_priority_list_the_more_recently_updated_first(api_client, session):
    ids = await _seed_board(session)
    session.add_all([
        Pursuit(job_id=ids["newest"], stage="applied", priority=2, updated_at=NOW - timedelta(days=3)),
        Pursuit(job_id=ids["richest"], stage="applied", priority=2, updated_at=NOW),
    ])
    await session.commit()

    _, body = await _get(api_client, "/pursuits")

    assert [item["opportunity_id"] for item in body["data"]["items"]] == [ids["richest"], ids["newest"]]


async def test_a_stage_filter_answers_only_that_stage(api_client, session):
    ids = await _seed_pursuits(session)

    _, applied = await _get(api_client, "/pursuits", stage="applied")
    _, withdrawn = await _get(api_client, "/pursuits", stage="withdrawn")

    assert [item["opportunity_id"] for item in applied["data"]["items"]] == [ids["newest"]]
    assert withdrawn["ok"] is True and withdrawn["data"]["items"] == []


@pytest.mark.parametrize(("limit", "expected"), [(1, 1), (2, 2), (500, 2)])
async def test_the_pursuit_limit_caps_the_page_it_answers(api_client, session, limit, expected):
    await _seed_pursuits(session)

    _, body = await _get(api_client, "/pursuits", limit=limit)

    if limit > 100:
        assert body["ok"] is False and body["error"]["code"] == "invalid_input", "no silent clamp"
    else:
        assert len(body["data"]["items"]) == expected
    _, rejected = await _get(api_client, "/pursuits", limit=0)
    assert rejected["ok"] is False and rejected["error"]["code"] == "invalid_input"


# --------------------------------------------------------------------------- #
# The radar summary
# --------------------------------------------------------------------------- #


async def _summary_counts(api_client) -> dict:
    _, body = await _get(api_client, "/radar/summary")
    assert body["ok"] is True, body["error"]
    return body["data"]


async def test_the_radar_summary_counts_what_each_of_its_names_says(api_client, session):
    ids = await _seed_pursuits(session)
    session.add(Favorite(job_id=ids["newest"]))
    await session.commit()

    summary = await _summary_counts(api_client)

    assert summary["open_opportunities"] == 2, "visible and in scope only"
    assert summary["saved_opportunities"] == 1
    assert summary["active_pursuits"] == 2
    assert summary["pursuits_by_stage"] == {"applied": 1, "offer": 1}


async def test_an_empty_radar_answers_zeros_rather_than_nulls(api_client, session):
    assert await _summary_counts(api_client) == {
        "open_opportunities": 0,
        "saved_opportunities": 0,
        "active_pursuits": 0,
        "overdue_next_actions": 0,
        "pursuits_by_stage": {},
    }


async def test_the_open_count_is_the_count_the_dashboard_shows(api_client, session):
    """A posting whose company has no roster row is kept by an exclusion and
    dropped by a join; the summary counts it as the dashboard does."""
    await _seed_board(session)
    session.add(_job(70, "unlisted"))
    await session.commit()

    shown = await session.scalar(open_in_scope_count_stmt(await off_board_company_slugs(session)))

    assert (await _summary_counts(api_client))["open_opportunities"] == shown == 3


async def test_an_overdue_offer_follow_up_is_owed_like_any_other(api_client, session):
    """An outstanding offer is where a missed follow-up costs most, so it is
    counted; a follow-up due later is not; a done pursuit is not."""
    ids = await _seed_board(session)
    session.add_all([
        Pursuit(job_id=ids["newest"], stage="offer", priority=1,
                next_action="Reply to the offer", next_action_due=NOW - timedelta(days=2), updated_at=NOW),
        Pursuit(job_id=ids["richest"], stage="applied", priority=2,
                next_action="Follow up", next_action_due=datetime.now(UTC) + timedelta(days=5), updated_at=NOW),
        Pursuit(job_id=ids["hidden_company"], stage="withdrawn", priority=2,
                next_action="Say thanks", next_action_due=NOW - timedelta(days=9), updated_at=NOW),
    ])
    await session.commit()

    owed = await session.scalar(select(func.count(Pursuit.id)).where(overdue_pursuit_clause(datetime.now(UTC))))

    assert (await _summary_counts(api_client))["overdue_next_actions"] == owed == 1

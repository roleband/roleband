"""`opportunities.search` and `vocabulary.list` over the agent router.

Search is held to the Board: the same filters list the same rows as
`/api/jobs`, each sort gives the Board's order, and paging with the cursor
reads every row once. A filter value is read strictly: an unknown one fails
with the lookup to run, never an empty page. A page stays within its tool
tier's budget, and when rows outgrow it the page stops early and the cursor
continues, so no row is cut or lost. Vocabulary counts are the Board's
filter counts, and every value it lists is one search accepts.

The routes run over real ASGI on a scratch database seeded by
`scripts.seed_synthetic`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, update

import tracker.agents.operations.search as search_ops
import tracker.api.routers.jobs as jobs_router
import tracker.search.best_match as best_match
from scripts.seed_synthetic import seed, task_req_id
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations import cursor, vocabulary
from tracker.agents.operations.envelope import OperationError
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.search import PAGE_BUDGET_BYTES, SearchPage
from tracker.agents.operations.vocabulary import VocabularyPage
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.agents.pursuits import PursuitUpdate, ensure_favorite, upsert_pursuit
from tracker.api.agent_operations import PREFIX
from tracker.db.models import Job, TrackedCompany

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

#: The small tier's whole reply, in bytes: 2,000 tokens at 2.5 bytes a token.
SMALL_REPLY_BYTES = 5_000
_READ = datetime(2026, 11, 1, tzinfo=UTC)


async def _no_query_vector(_text: str) -> list[float]:
    return []


@pytest_asyncio.fixture
async def workspace(db_session, scratch_scope, monkeypatch):
    """The seeded workspace with agent reads on. Neither side loads the
    embedding model: both rank text lexically, so their orders compare."""
    monkeypatch.setattr(search_ops, "embed_query", _no_query_vector)
    monkeypatch.setattr(jobs_router, "embed_query", _no_query_vector)
    await seed(db_session, 40, seed_value=1, derived=False, agent_tasks=True)
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    return db_session


async def _search(api_client, **params):
    response = await api_client.get(f"{PREFIX}/opportunities", params=params)
    return response, response.json()


def _page(body: dict) -> dict:
    assert body["ok"] is True, body["error"]
    SearchPage.model_validate(body["data"])
    return body["data"]


def _error(response, body: dict, code: str = "invalid_input") -> dict:
    assert body["ok"] is False and body["data"] is None
    assert body["error"]["code"] == code
    assert response.status_code == outcome(code).http_status
    return body["error"]


async def _board_ids(api_client, **params) -> list[int]:
    """The rows the Board lists for `params`, in its order."""
    response = await api_client.get("/api/jobs", params={"limit": 500, **params})
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def _every_page(api_client, **params) -> list[int]:
    ids: list[int] = []
    cursor = None
    for _ in range(50):
        _, body = await _search(api_client, **params, **({"cursor": cursor} if cursor else {}))
        page = _page(body)
        ids += [row[0] for row in page["rows"]]
        cursor = body["meta"]["next_cursor"]
        if cursor is None:
            return ids
    raise AssertionError("the cursor never ended")


# --------------------------------------------------------------------------- #
# The Board's rows, the Board's order
# --------------------------------------------------------------------------- #


async def test_the_filters_list_the_rows_the_board_lists(api_client, workspace):
    _, body = await _search(api_client, family="product_management", location=["new_york", "Seattle"])
    page = _page(body)
    places = page["filters"]["location"]
    assert places[0] == "new_york" and len(places) == 2

    board = await _board_ids(api_client, family="product_management", location_group=places, sort="first_seen")
    assert len(board) >= 3, "the seed must give this filter rows, or equality proves nothing"
    assert [row[0] for row in page["rows"]] == board[:20]
    assert page["total"] == len(board)
    assert page["sort"] == "newest" and page["order"] == "desc"
    assert page["columns"][0] == "id"


async def test_names_people_use_read_as_the_values_they_name(api_client, workspace):
    _, by_slug = await _search(api_client, family="product_management", location="new_york")
    _, by_name = await _search(api_client, family="Product Management", location="NEW YORK")

    assert _page(by_name)["rows"] == _page(by_slug)["rows"]
    assert _page(by_name)["filters"] == {"family": ["product_management"], "location": ["new_york"]}


@pytest.mark.parametrize(
    ("sort", "order", "key"),
    [
        ("newest", "desc", "first_seen"),
        ("age", "asc", "days_open"),
        ("pay", "desc", "base_pay"),
        ("estimated_pay", "desc", "comp_median"),
        ("level", "desc", "level_band"),
        ("company", "asc", "company"),
        ("title", "asc", "title"),
        ("location", "asc", "location"),
    ],
)
async def test_each_sort_is_the_boards_order(api_client, workspace, sort, order, key):
    board = await _board_ids(api_client, sort=key, order=order)

    assert await _every_page(api_client, sort=sort, order=order, limit=7) == board


async def test_a_query_with_best_match_is_the_boards_best_match(api_client, workspace):
    board = await _board_ids(api_client, q="product manager", sort="relevance", limit=20)
    assert board, "the query must match seeded rows"

    _, body = await _search(api_client, query="product manager")
    page = _page(body)

    assert page["sort"] == "best_match" and page["order"] is None
    assert [row[0] for row in page["rows"]] == board[:20]


@pytest.mark.parametrize("pool", [2, None], ids=["capped", "uncapped"])
async def test_a_ranking_the_board_cuts_short_is_flagged(api_client, workspace, monkeypatch, pool):
    """Broken rule caught: best match dropped the ranking's truncation, so the
    last page ended as if every match had been listed."""
    if pool is not None:
        from tracker.config import get_settings

        monkeypatch.setattr(get_settings(), "search_candidate_pool", pool)
        monkeypatch.setattr(get_settings(), "search_candidate_pool_max", pool)
    response = await api_client.get("/api/jobs", params={"q": "product manager", "sort": "relevance", "limit": 20})
    cut = response.json()["ranking_truncated"]
    assert cut is (pool is not None), {k: response.json()[k] for k in ("matched", "query_kind", "total")}

    _, body = await _search(api_client, query="product manager")
    _page(body)
    assert body["meta"]["truncated"] is cut
    assert ("ranking_truncated" in [warning["code"] for warning in body["warnings"]]) is cut


async def test_an_exact_title_match_comes_first_and_pages_into_the_related_ones(api_client, workspace):
    title = (await workspace.scalar(select(Job.title).where(Job.req_id == task_req_id("STATED"))))
    _, first = await _search(api_client, query=title, limit=1)
    page = _page(first)
    assert page["rows"][0][1] == title

    ids = await _every_page(api_client, query=title, limit=1)
    assert ids[0] == page["rows"][0][0]
    assert len(ids) == len(set(ids)) == page["total"]


async def test_best_match_never_sends_the_query_to_a_model(api_client, workspace, monkeypatch):
    asked: list[bool] = []
    original = best_match.resolve_query

    async def recording(text, *, egress_allowed, companies):
        asked.append(egress_allowed)
        return await original(text, egress_allowed=False, companies=companies)

    monkeypatch.setattr(best_match, "resolve_query", recording)
    monkeypatch.setattr(best_match, "get_ai_egress_enabled", lambda _session: _true())
    monkeypatch.setattr(best_match, "get_settings", lambda: _Settings())

    await _search(api_client, query="product manager")
    await api_client.get("/api/jobs", params={"q": "product manager", "sort": "relevance"})

    # The agent's search parses on this computer; the Board, for the same settings, would ask the model.
    assert asked == [False, True]


async def _true() -> bool:
    return True


class _Settings:
    search_llm_enabled = True
    search_semantic_enabled = False


async def test_paging_reads_every_row_once(api_client, workspace):
    board = await _board_ids(api_client, sort="first_seen")
    assert len(board) > 25

    assert await _every_page(api_client, limit=9) == board


# --------------------------------------------------------------------------- #
# Strict values
# --------------------------------------------------------------------------- #


async def test_an_unknown_value_fails_with_the_lookup_to_run_and_searches_nothing(api_client, workspace):
    response, body = await _search(api_client, family="product_management", location=["New York", "Seatle"])

    error = _error(response, body)
    assert outcome(error["code"]).exit_status == 2
    assert error["details"]["reason"] == "unknown_value"
    assert error["details"]["unknown"] == [{"filter": "location", "value": "Seatle"}]
    assert error["next_actions"] == [{"operation": "vocabulary.list", "arguments": {"kind": "location"}}]
    assert "Seatle" in error["message"]


async def test_every_unknown_value_is_named_with_its_own_lookup(api_client, workspace):
    response, body = await _search(api_client, company="Initech", level_band=["senior", "Wizard"])

    error = _error(response, body)
    assert error["details"]["unknown"] == [
        {"filter": "company", "value": "Initech"}, {"filter": "level_band", "value": "Wizard"},
    ]
    assert [action["arguments"]["kind"] for action in error["next_actions"]] == ["company", "level_band"]


async def test_nothing_fuzzier_than_spelling_is_matched(api_client, workspace):
    # "Product Manager" is a person's word for the family, not its name.
    response, body = await _search(api_client, family="Product Manager")
    assert _error(response, body)["details"]["unknown"] == [{"filter": "family", "value": "Product Manager"}]


async def test_a_known_value_with_no_rows_is_a_true_zero(api_client, workspace):
    _, listed = await _vocabulary(api_client, kind="location", limit=500)
    empty = next(entry["value"] for entry in listed["data"]["items"] if entry["open_roles"] == 0)

    _, body = await _search(api_client, location=empty)
    page = _page(body)
    assert page["total"] == 0 and page["rows"] == [] and body["meta"]["next_cursor"] is None


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"base_pay_min": 300_000, "base_pay_max": 100_000}, None),
        ({"limit": 101}, "limit"),
        ({"listed_within_days": 0}, "listed_within_days"),
        ({"sort": "relevance"}, "sort"),
        ({"keyword": "x"}, "keyword"),
    ],
)
async def test_input_outside_the_schema_is_refused(api_client, workspace, params, field):
    response, body = await _search(api_client, **params)
    error = _error(response, body)
    if field is not None:
        assert [item["location"] for item in error["details"]["errors"]] == [[field]]


# --------------------------------------------------------------------------- #
# Cursors
# --------------------------------------------------------------------------- #


async def test_a_cursor_continues_only_the_search_it_came_from(api_client, workspace):
    _, body = await _search(api_client, family="product_management", limit=2)
    cursor = body["meta"]["next_cursor"]
    assert cursor

    response, other = await _search(api_client, family="software_engineering", limit=2, cursor=cursor)
    assert _error(response, other)["details"] == {"field": "cursor", "reason": "other_request"}
    response, resorted = await _search(api_client, family="product_management", sort="title", cursor=cursor)
    assert _error(response, resorted)["details"]["reason"] == "other_request"

    # A later page may change its size and tier, not its filters.
    _, resized = await _search(api_client, family="product_management", limit=5, tier="standard", cursor=cursor)
    assert _page(resized)["rows"]

    response, garbage = await _search(api_client, family="product_management", cursor="not-a-cursor")
    assert _error(response, garbage)["details"]["reason"] == "malformed"


def test_a_cursor_is_bound_to_its_workspace():
    request = {"family": ["product_management"]}
    here = cursor.fingerprint("opportunities.search", "ws_" + "a" * 32, request)
    elsewhere = cursor.fingerprint("opportunities.search", "ws_" + "b" * 32, request)
    assert here != elsewhere
    with pytest.raises(OperationError) as refused:
        cursor.decode(cursor.encode(request=elsewhere, offset=20), request=here)
    assert refused.value.details == {"field": "cursor", "reason": "other_request"}
    assert cursor.decode(cursor.encode(request=here, offset=20, carried=3), request=here) == (20, 3)


# --------------------------------------------------------------------------- #
# The row and the budget
# --------------------------------------------------------------------------- #


async def _state_pay_everywhere(session) -> None:
    """Every posting states a band: the widest a row gets."""
    await session.execute(update(Job).values(
        structured_at=datetime.now(UTC), disclosed_base_min=212_000, disclosed_base_max=264_500,
        disclosed_currency="USD", disclosed_pay_period="year", disclosed_pay_basis="base",
    ))
    await session.commit()


async def test_a_default_page_of_full_rows_fits_the_small_tier(api_client, workspace):
    await _state_pay_everywhere(workspace)
    places = ["San Francisco, CA", "New York, NY", "Seattle, WA", "Austin, TX", "Remote, United States"]
    await workspace.execute(update(Job).values(locations=places))
    await workspace.commit()

    response, body = await _search(api_client, sort="estimated_pay")
    page = _page(body)

    assert page["count"] == 20, "the default page is 20 rows"
    assert len(response.content) <= SMALL_REPLY_BYTES
    assert body["warnings"] == []
    row = dict(zip(page["columns"], page["rows"][0], strict=True))
    # Both pay figures, kept apart, and no description.
    assert row["stated_pay"] == "212000-264500 USD/year base"
    assert row["estimated_pay"].endswith((" USD total", " USD base"))
    assert row["location"] == places[0] and row["more_locations"] == 4
    assert "description" not in json.dumps(page)


async def test_rows_that_outgrow_the_budget_end_the_page_and_the_cursor_carries_on(api_client, workspace):
    board = await _board_ids(api_client, sort="first_seen")
    await workspace.execute(update(Job).values(title=Job.title + " " + "x" * 400))
    await workspace.commit()

    response, body = await _search(api_client)
    page = _page(body)

    assert 1 <= page["count"] < 20
    assert sum(len(json.dumps(row, separators=(",", ":"))) + 1 for row in page["rows"]) <= PAGE_BUDGET_BYTES["small"]
    assert [warning["code"] for warning in body["warnings"]] == ["page_shortened"]
    assert body["meta"]["truncated"] is False, "no row was cut"
    # Every row is still read, once, by following the cursor.
    assert await _every_page(api_client) == board
    _, wide = await _search(api_client, tier="full")
    assert _page(wide)["count"] == 20


async def test_a_wide_filter_set_still_fits_the_reply(api_client, workspace):
    """Broken rule caught: the rows had the whole budget, so the filters a page
    echoes pushed a small-tier reply past it."""
    await workspace.execute(update(Job).values(title=Job.title + " " + "x" * 400))
    await workspace.commit()
    wide = {}
    for kind in ("company", "family", "level_band", "track", "domain"):
        _, listed = await _vocabulary(api_client, kind=kind, limit=500)
        wide[kind] = [entry["value"] for entry in listed["data"]["items"]][:50]
    _, narrow = await _search(api_client)
    response, body = await _search(api_client, **wide)
    page = _page(body)
    filters = len(json.dumps(page["filters"], separators=(",", ":")))
    assert filters > 1_000, "the request must echo a wide filter set"
    assert len(response.content) <= SMALL_REPLY_BYTES
    assert 1 <= page["count"] < _page(narrow)["count"]


async def test_best_match_without_a_query_ignores_order(api_client, workspace):
    _, falling = await _search(api_client, sort="best_match", order="desc", limit=40)
    _, rising = await _search(api_client, sort="best_match", order="asc", limit=40)
    assert [row[0] for row in _page(rising)["rows"]] == [row[0] for row in _page(falling)["rows"]]
    assert _page(rising)["order"] is None


async def test_a_row_carries_the_persons_own_marks(api_client, workspace):
    saved_id = await workspace.scalar(select(Job.id).where(Job.req_id == task_req_id("ESTONLY")))
    await ensure_favorite(workspace, saved_id)
    await workspace.commit()

    _, body = await _search(api_client, saved_only="true")
    page = _page(body)
    marks = {row[0]: row[page["columns"].index("pursuit")] for row in page["rows"]}

    assert marks[saved_id] == "saved"
    interviewing = await workspace.scalar(select(Job.id).where(Job.req_id == task_req_id("INTERVIEW")))
    assert marks[interviewing] == "interviewing"


async def test_a_hidden_company_is_off_the_search_unless_saved(api_client, workspace):
    stated = await workspace.get(Job, await workspace.scalar(select(Job.id).where(Job.req_id == task_req_id("STATED"))))
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == stated.company).values(visible=False))
    await workspace.commit()

    _, body = await _search(api_client, company=stated.company)
    assert _page(body)["total"] == 0

    await upsert_pursuit(workspace, stated.id, PursuitUpdate(stage="saved"), actor="user")
    await workspace.commit()
    _, saved = await _search(api_client, company=stated.company, saved_only="true")
    assert [row[0] for row in _page(saved)["rows"]] == [stated.id]


@pytest.mark.parametrize(
    ("fields", "stated"),
    [
        ({}, None),
        ({"structured_at": _READ}, "none"),
        ({"structured_at": _READ, "disclosed_base_min": 150000, "disclosed_currency": "GBP",
          "disclosed_pay_period": "year", "disclosed_pay_basis": "base"}, "150000+ GBP/year base"),
        ({"structured_at": _READ, "disclosed_base_max": 95, "disclosed_currency": "USD",
          "disclosed_pay_period": "hour"}, "up to 95 USD/hour"),
        ({"structured_at": _READ, "disclosed_base_min": 180000, "disclosed_base_max": 220000}, "180000-220000 /year"),
    ],
    ids=["not-read", "states-none", "low-only", "high-only-hourly", "period-from-the-amount"],
)
def test_the_stated_band_reads_as_the_posting_states_it(fields, stated):
    assert search_ops.stated_pay(Job(**fields)) == stated


@pytest.mark.parametrize(
    ("fields", "estimate"),
    [
        ({}, None),
        ({"comp_median": 301234.6, "comp_currency": "USD", "comp_component": "total"}, "301235 USD total"),
        ({"comp_component": "base", "comp_base_median": 180000, "comp_currency": "EUR"}, "180000 EUR base"),
        # A base estimate on a posting priced by its total is not offered as the total.
        ({"comp_component": "total", "comp_base_median": 180000, "comp_currency": "USD"}, None),
    ],
)
def test_the_estimate_names_what_it_prices(fields, estimate):
    assert search_ops.estimated_pay(Job(**fields)) == estimate


# --------------------------------------------------------------------------- #
# vocabulary.list
# --------------------------------------------------------------------------- #


async def _vocabulary(api_client, **params):
    response = await api_client.get(f"{PREFIX}/vocabulary", params=params)
    return response, response.json()


@pytest.mark.parametrize(
    ("kind", "facet"),
    [("location", "location_group"), ("company", "company"), ("family", "family"), ("level_band", "level_band"),
     ("workplace_type", "workplace_type"), ("domain", "domain"), ("track", "track")],
)
async def test_the_counts_are_the_boards_filter_counts(api_client, workspace, kind, facet):
    facets = (await api_client.get("/api/facets")).json()
    counts = facets["counts"][facet]
    assert counts, f"the seed gives no {facet} counts"

    _, body = await _vocabulary(api_client, kind=kind, limit=500)
    assert body["ok"] is True, body["error"]
    VocabularyPage.model_validate(body["data"])
    counted = {entry["value"]: entry["open_roles"] for entry in body["data"]["items"]}

    # Each listed value counts what the Board counts for it.
    assert {value: count for value, count in counted.items() if count} == {
        value: count for value, count in counts.items() if count and value in counted
    }
    # Every option the Board's filter offers is a value here, with its count.
    offered = facets["location_groups"] if kind == "location" else facets.get(f"{facet}s", counts)
    for value in offered:
        assert counted.get(value) == counts.get(value, 0), value


async def test_locations_carry_the_names_people_use_and_filter_by_contains(api_client, workspace):
    _, body = await _vocabulary(api_client, kind="location", contains="usa")
    entries = {entry["value"]: entry for entry in body["data"]["items"]}

    assert "united_states" in entries
    assert "usa" in entries["united_states"]["also"]
    assert all(
        "usa" in vocabulary.normalize(" ".join([entry["value"], entry["name"] or "", *entry["also"]]))
        for entry in body["data"]["items"]
    )


async def test_a_vocabulary_page_continues_by_cursor_and_ends(api_client, workspace):
    _, first = await _vocabulary(api_client, kind="family", limit=3)
    seen = [entry["value"] for entry in first["data"]["items"]]
    cursor = first["meta"]["next_cursor"]
    while cursor:
        _, body = await _vocabulary(api_client, kind="family", limit=3, cursor=cursor)
        seen += [entry["value"] for entry in body["data"]["items"]]
        cursor = body["meta"]["next_cursor"]
    assert sorted(seen) == sorted(set(seen))
    assert len(seen) == first["data"]["total"]

    response, other = await _vocabulary(api_client, kind="track", cursor=first["meta"]["next_cursor"])
    assert _error(response, other)["details"]["reason"] == "other_request"


async def test_an_unknown_kind_is_refused(api_client, workspace):
    response, body = await _vocabulary(api_client, kind="salary")
    assert [item["location"] for item in _error(response, body)["details"]["errors"]] == [["kind"]]


@pytest.mark.parametrize("kind", vocabulary.KINDS)
async def test_every_value_and_name_the_vocabulary_lists_is_one_search_accepts(api_client, workspace, kind):
    _, body = await _vocabulary(api_client, kind=kind, limit=500)
    entries = body["data"]["items"]
    assert entries
    known = await vocabulary.load(workspace, kind)
    shared = [vocabulary.normalize(entry["name"]) for entry in entries if entry["name"]]
    for entry in entries:
        name = entry["name"]
        accepted = [name] if name and shared.count(vocabulary.normalize(name)) == 1 else []
        for spelling in [entry["value"], *accepted, *entry["also"]]:
            assert known.value_of(spelling) == entry["value"], (kind, spelling)
    # One search with a listed value is accepted, not refused as unknown.
    _, searched = await _search(api_client, **{kind: entries[0]["value"]})
    assert searched["ok"] is True, searched["error"]


def test_a_name_two_values_share_names_neither():
    """Broken rule caught: the first company to claim a shared display name
    kept it, so a search by that name narrowed to one of two companies."""
    known = vocabulary.Vocabulary.of(
        "company", [("example-one", "Example"), ("example-two", "Example"), ("acme", "Acme"), ("acme", "ACME Corp")]
    )
    assert known.value_of("Example") is None
    assert known.value_of("example one") == "example-one"
    assert known.value_of("Example-Two") == "example-two"
    assert known.value_of("acme corp") == "acme"
    assert known.also == {"example-one": [], "example-two": [], "acme": ["ACME Corp"]}
    # A value's own spelling wins over another value's name.
    shadowed = vocabulary.Vocabulary.of("company", [("stripe", "Stripe"), ("payments", "stripe")])
    assert shadowed.value_of("stripe") == "stripe"


async def test_a_shared_company_name_is_refused_and_its_slugs_still_search(api_client, workspace):
    first, second = (await workspace.scalars(select(TrackedCompany).order_by(TrackedCompany.slug).limit(2))).all()
    await workspace.execute(
        update(TrackedCompany).where(TrackedCompany.slug.in_([first.slug, second.slug])).values(display="Twin Labs")
    )
    await workspace.commit()
    response, body = await _search(api_client, company="Twin Labs")
    error = _error(response, body)
    assert error["details"]["unknown"] == [{"filter": "company", "value": "Twin Labs"}]
    _, both = await _search(api_client, company=[first.slug, second.slug], limit=100)
    assert _page(both)["filters"]["company"] == [first.slug, second.slug]
    _, listed = await _vocabulary(api_client, kind="company", contains="twin labs", limit=500)
    assert {entry["value"] for entry in listed["data"]["items"]} == {first.slug, second.slug}

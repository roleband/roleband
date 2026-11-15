"""The posting reads beside `opportunities.get` answer what the posting screen's routes answer.

`opportunities.get_many` has no route of its own: its rows are search's rows,
so it is held to `opportunities.search` over the same postings. The relation
reads are held to the routes the posting screen draws its decks from
(`/similar`, `/lineage`, `/twins`, `/place-set`) and to the standing-posting
verdict `/api/jobs/{id}` carries. The workspace is `scripts.seed_synthetic`'s
with the lineage contract's stacks and twins (`tests/lineage_contract_seed.py`)
and a place set built by `rebuild_place_sets` on top.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from scripts.seed_synthetic import seed
from tests.factories import make_company
from tests.lineage_contract_seed import seed_lineage_contract
from tests.place_set_rows import place_set_job, unit_vector
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.opportunities import GET_MANY_MAX_IDS, read_rest
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.search import COLUMNS, PAGE_BUDGET_BYTES
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import PREFIX
from tracker.db.models import Favorite, Job, TrackedCompany
from tracker.lineage.place_sets import rebuild_place_sets

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]


@pytest_asyncio.fixture
async def workspace(db_session, api_client):
    """The synthetic workspace with lineage stacks, twins and a place set, agent reads on."""
    await seed(db_session, 8, seed_value=1, derived=False, agent_tasks=True)
    await db_session.commit()
    lineage = await seed_lineage_contract(db_session, local_model=False)
    for n, city in enumerate(("London", "Bristol", "St Albans"), start=1):
        await place_set_job(db_session, n, city)
    await rebuild_place_sets(db_session)
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    return db_session, lineage


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
    assert body["ok"] is False
    assert body["error"]["code"] == code
    assert outcome(code).exit_status == exit_status
    assert response.status_code == outcome(code).http_status


def _bytes(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


async def _search_rows(api_client) -> dict[int, list]:
    """Every posting search answers, as its row, by id."""
    rows: dict[int, list] = {}
    cursor = None
    while True:
        _, body = await _agent(api_client, "/opportunities", limit=100, tier="full",
                               **({"cursor": cursor} if cursor else {}))
        rows.update({row[0]: row for row in _data(body)["rows"]})
        cursor = body["meta"]["next_cursor"]
        if cursor is None:
            return rows


async def _ids(session) -> list[int]:
    return list((await session.scalars(select(Job.id).order_by(Job.id))).all())


def _unknown(ids: list[int], n: int = 1) -> list[int]:
    return [max(ids) + 1_000 + i for i in range(n)]


# --------------------------------------------------------------------------- #
# opportunities.get_many  <-  opportunities.search's rows
# --------------------------------------------------------------------------- #


async def test_get_many_answers_searchs_rows_in_the_order_asked(api_client, workspace):
    searched = await _search_rows(api_client)
    asked = list(reversed(list(searched)))[:12]
    assert len(asked) == 12

    _, body = await _agent(api_client, "/opportunities/get-many", ids=asked, tier="full")

    data = _data(body)
    assert data["columns"] == list(COLUMNS)
    assert data["rows"] == [searched[job_id] for job_id in asked]
    assert (data["count"], data["not_found"], data["continue_with"]) == (12, [], [])
    assert body["meta"]["partial"] is False


async def test_get_many_reads_a_posting_search_leaves_out(api_client, workspace):
    session, _ = workspace
    closed = (await session.scalars(select(Job.id).where(Job.status == "closed").limit(1))).one()
    assert closed not in await _search_rows(api_client)

    _, body = await _agent(api_client, "/opportunities/get-many", ids=[closed])

    assert [row[0] for row in _data(body)["rows"]] == [closed]


async def test_get_many_names_each_id_once(api_client, workspace):
    searched = await _search_rows(api_client)
    first, second = list(searched)[:2]

    _, body = await _agent(api_client, "/opportunities/get-many", ids=[first, second, first])

    assert [row[0] for row in _data(body)["rows"]] == [first, second]


async def test_more_ids_than_the_bound_are_refused_never_cut(api_client, workspace):
    ids = list(range(1, GET_MANY_MAX_IDS + 2))
    assert len(ids) == GET_MANY_MAX_IDS + 1

    response, body = await _agent(api_client, "/opportunities/get-many", ids=ids)

    _error(response, body, "invalid_input", 2)
    assert body["data"] is None
    assert [(e["location"], e["type"]) for e in body["error"]["details"]["errors"]] == [(["ids"], "too_long")]
    # The bound itself is accepted.
    response, body = await _agent(api_client, "/opportunities/get-many", ids=ids[:GET_MANY_MAX_IDS], tier="full")
    assert response.status_code in (200, 207), body


async def test_some_unknown_ids_answer_the_rest_as_a_partial_result(api_client, workspace):
    session, _ = workspace
    searched = await _search_rows(api_client)
    known = list(searched)[:3]
    unknown = _unknown(await _ids(session), 2)

    response, body = await _agent(api_client, "/opportunities/get-many", ids=[unknown[0], *known, unknown[1]])

    _error(response, body, "partial_result", 9)
    assert body["meta"]["partial"] is True
    assert body["data"]["rows"] == [searched[job_id] for job_id in known]
    assert body["data"]["not_found"] == unknown
    assert body["error"]["details"] == {"asked": 5, "not_found": 2}


async def test_only_unknown_ids_are_not_found(api_client, workspace):
    session, _ = workspace
    unknown = _unknown(await _ids(session), 2)

    response, body = await _agent(api_client, "/opportunities/get-many", ids=unknown)

    _error(response, body, "not_found", 5)
    assert body["data"] is None
    assert body["error"]["details"] == {"opportunity_ids": unknown}


async def test_a_small_tier_leaves_the_rest_to_continue_with_and_reads_each_once(api_client, workspace):
    session, _ = workspace
    asked = (await _ids(session))[:GET_MANY_MAX_IDS]
    assert len(asked) > 20
    whole = _data((await _agent(api_client, "/opportunities/get-many", ids=asked, tier="full"))[1])
    assert whole["continue_with"] == [] and len(whole["rows"]) == len(asked)

    read: list[list] = []
    _, body = await _agent(api_client, "/opportunities/get-many", ids=asked)
    assert [w["code"] for w in body["warnings"]] == ["page_shortened"]
    while True:
        data = _data(body)
        assert _bytes(data) <= PAGE_BUDGET_BYTES["small"]
        read.extend(data["rows"])
        if not data["continue_with"]:
            break
        (call,) = data["continue_with"]
        assert call["operation"] == "opportunities.get_many"
        _, body = await _agent(api_client, "/opportunities/get-many", **call["arguments"])

    assert read == whole["rows"]


async def test_a_partial_answer_says_a_row_was_cut(api_client, workspace):
    session, lineage = workspace
    await session.execute(update(Job).where(Job.id == lineage.solo).values(title="Staff Engineer " + "x" * 6_000))
    await session.commit()
    (unknown,) = _unknown(await _ids(session))

    response, body = await _agent(api_client, "/opportunities/get-many", ids=[lineage.solo, unknown])

    _error(response, body, "partial_result", 9)
    assert body["meta"]["truncated"] is True
    assert [w["code"] for w in body["warnings"]] == ["row_shortened"]
    assert _bytes(body["data"]) <= PAGE_BUDGET_BYTES["small"]


async def test_the_rest_is_read_in_calls_the_bound_admits():
    jobs = [Job(id=n) for n in range(1, 2 * GET_MANY_MAX_IDS + 51)]

    calls = read_rest(jobs, "standard")

    assert [len(call.arguments["ids"]) for call in calls] == [GET_MANY_MAX_IDS, GET_MANY_MAX_IDS, 50]
    assert [i for call in calls for i in call.arguments["ids"]] == [job.id for job in jobs]
    assert {call.arguments["tier"] for call in calls} == {"standard"}
    assert read_rest([], "small") == []


async def test_a_posting_at_a_hidden_company_is_not_found_unless_saved(api_client, workspace):
    session, lineage = workspace
    await _hide(session, "acme")

    response, body = await _agent(api_client, "/opportunities/get-many", ids=[lineage.other_company])

    _error(response, body, "not_found", 5)


# --------------------------------------------------------------------------- #
# opportunities.similar  <-  GET /api/jobs/{id}/similar
# --------------------------------------------------------------------------- #


async def _embedded_neighbours(session) -> int:
    """A posting with neighbours at its own company and at others, by embedding."""
    subject = await place_set_job(session, 40, "Leeds", title="Controls Analytics Lead", company="aecom")
    for n, (company, dim) in enumerate([("aecom", 0), ("jacobs", 0), ("arup", 1), ("arup", 0)], start=41):
        job = await place_set_job(session, n, "Leeds", title=f"Analytics Lead {n}", company=company)
        vec = unit_vector(dim)
        vec[0] = 1.0
        job.embedding = vec
    await session.commit()
    return subject.id


@pytest.mark.parametrize("scope", ["within", "cross", "all"])
async def test_similar_is_the_screens_neighbours_in_its_order(api_client, workspace, scope):
    session, _ = workspace
    subject = await _embedded_neighbours(session)
    screen = await _screen(api_client, f"/api/jobs/{subject}/similar", scope=scope)
    assert screen["items"]

    _, body = await _agent(api_client, f"/opportunities/{subject}/similar", scope=scope, tier="full")

    data = _data(body)
    assert data["similar"] == [[item["id"], item["score"]] for item in screen["items"]]
    assert [row[0] for row in data["rows"]] == [item["id"] for item in screen["items"]]
    assert data["continue_with"] == []


async def test_similar_keeps_hidden_companies_out_before_the_limit(api_client, workspace):
    session, _ = workspace
    subject = await _embedded_neighbours(session)
    await _hide(session, "jacobs")
    screen = await _screen(api_client, f"/api/jobs/{subject}/similar", scope="cross", limit=1)

    _, body = await _agent(api_client, f"/opportunities/{subject}/similar", scope="cross", limit=1)

    assert [pair[0] for pair in _data(body)["similar"]] == [item["id"] for item in screen["items"]]
    assert len(screen["items"]) == 1
    hidden = set((await session.scalars(select(Job.id).where(Job.company == "jacobs"))).all())
    assert not {pair[0] for pair in _data(body)["similar"]} & hidden


# --------------------------------------------------------------------------- #
# opportunities.duplicates  <-  /lineage, /twins, /place-set
# --------------------------------------------------------------------------- #


def _link(screen_link: dict | None) -> dict | None:
    if screen_link is None:
        return None
    return {
        "relation": screen_link["relation"], "method": screen_link["method"],
        "confidence": screen_link["confidence"], "status": screen_link["status"],
        "decision": screen_link["decision"], "score": screen_link["score"], "gap_days": screen_link["gap_days"],
        "reasons": [{"code": said["code"], "params": said["params"]} for said in screen_link["said"]],
    }


def _moment(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


async def _decks(api_client, job_id: int) -> dict:
    _, body = await _agent(api_client, f"/opportunities/{job_id}/duplicates", tier="full")
    return _data(body)


async def test_the_repost_stack_is_the_screens_stack(api_client, workspace):
    _, lineage = workspace
    for job_id in (lineage.original, lineage.repost, lineage.duplicate):
        screen = await _screen(api_client, f"/api/jobs/{job_id}/lineage")
        assert screen["size"] == 3

        reposts = (await _decks(api_client, job_id))["reposts"]

        assert (reposts["lineage_id"], reposts["size"], reposts["open_members"]) == (
            screen["lineage_id"], screen["size"], screen["open_members"],
        )
        assert _moment(reposts["first_seen"]) == _moment(screen["first_seen"])
        assert [
            (m["opportunity_id"], m["seq"], m["role"], m["link"]) for m in reposts["members"]
        ] == [
            (m["job"]["id"], m["seq"], m["role"], _link(m["link"])) for m in screen["members"]
        ]
        # The stack is stacked, never merged: every member stays its own posting.
        assert len({m["opportunity_id"] for m in reposts["members"]}) == 3


async def test_the_twin_deck_is_the_screens_twins(api_client, workspace):
    _, lineage = workspace
    for job_id in (lineage.twin_left, lineage.twin_hub, lineage.twin_spoke):
        screen = await _screen(api_client, f"/api/jobs/{job_id}/twins")
        assert screen["size"] > 1

        twins = (await _decks(api_client, job_id))["twins"]

        assert (twins["size"], twins["direct_count"]) == (screen["size"], screen["direct_count"])
        assert [(m["opportunity_id"], m["direct"], m["link"]) for m in twins["members"]] == [
            (m["job"]["id"], m["direct"], _link(m["link"])) for m in screen["members"]
        ]


async def test_the_place_set_is_the_screens_place_set(api_client, workspace):
    session, _ = workspace
    london = (await session.scalars(select(Job.id).where(Job.req_id == "744000127400001"))).one()
    screen = (await _screen(api_client, f"/api/jobs/{london}/place-set"))["place_set"]
    assert screen and screen["size"] == 3

    found = (await _decks(api_client, london))["place_set"]

    assert (found["size"], found["places"], found["employer_label"], found["rule_version"]) == (
        screen["size"], screen["places"], screen["employer_label"], screen["rule_version"],
    )
    assert [(m["opportunity_id"], m["is_this"], m["relation"], m["same_place"]) for m in found["members"]] == [
        (m["job"]["id"], m["is_this"], m["relation"], m["same_place"]) for m in screen["members"]
    ]


async def test_a_posting_alone_has_no_deck_and_its_own_row(api_client, workspace):
    _, lineage = workspace
    assert (await _screen(api_client, f"/api/jobs/{lineage.solo}/lineage"))["members"] == []
    assert (await _screen(api_client, f"/api/jobs/{lineage.solo}/twins"))["size"] == 1
    assert (await _screen(api_client, f"/api/jobs/{lineage.solo}/place-set"))["place_set"] is None

    data = await _decks(api_client, lineage.solo)

    assert (data["reposts"], data["twins"], data["place_set"]) == (None, None, None)
    assert [row[0] for row in data["rows"]] == [lineage.solo]


async def test_each_posting_a_deck_names_has_one_row_the_subject_first(api_client, workspace):
    _, lineage = workspace

    data = await _decks(api_client, lineage.repost)

    named = [m["opportunity_id"] for m in data["reposts"]["members"]]
    if data["twins"]:
        named += [m["opportunity_id"] for m in data["twins"]["members"]]
    ids = [row[0] for row in data["rows"]]
    assert ids[0] == lineage.repost
    assert len(ids) == len(set(ids)) and set(ids) == set(named) | {lineage.repost}


async def test_a_small_tier_leaves_deck_rows_to_continue_with(api_client, workspace):
    _, lineage = workspace
    whole = await _decks(api_client, lineage.repost)

    _, body = await _agent(api_client, f"/opportunities/{lineage.repost}/duplicates", tier="small")

    data = _data(body)
    rows = list(data["rows"])
    for call in data["continue_with"]:
        _, more = await _agent(api_client, "/opportunities/get-many", **call["arguments"])
        rows.extend(_data(more)["rows"])
    assert [row[0] for row in rows] == [row[0] for row in whole["rows"]]
    assert data["reposts"] == whole["reposts"]


async def test_a_saved_posting_at_a_hidden_company_names_none_of_its_hidden_siblings(api_client, workspace):
    session, lineage = workspace
    london = (await session.scalars(select(Job.id).where(Job.req_id == "744000127400001"))).one()
    session.add_all([Favorite(job_id=lineage.repost), Favorite(job_id=london)])
    await session.commit()
    await _hide(session, "google")
    await _hide(session, "aecom")
    hidden = set((await session.scalars(
        select(Job.id).where(Job.company.in_(["google", "aecom"]), Job.id.not_in([lineage.repost, london]))
    )).all())
    assert {lineage.original, lineage.duplicate} <= hidden

    for subject in (lineage.repost, london):
        _, body = await _agent(api_client, f"/opportunities/{subject}/duplicates", tier="full")

        data = _data(body)
        assert [row[0] for row in data["rows"]] == [subject]
        named = {row[0] for row in data["rows"]}
        for kind in ("reposts", "twins", "place_set"):
            named |= {m["opportunity_id"] for m in (data[kind] or {}).get("members", [])}
        named |= {i for call in data["continue_with"] for i in call["arguments"]["ids"]}
        assert named == {subject}, subject
    reposts = (await _decks(api_client, lineage.repost))["reposts"]
    assert ([m["opportunity_id"] for m in reposts["members"]], reposts["size"]) == ([lineage.repost], 1)
    assert (await _decks(api_client, london))["place_set"] is None


# --------------------------------------------------------------------------- #
# opportunities.reality  <-  posting_reality in GET /api/jobs/{id}
# --------------------------------------------------------------------------- #


async def test_the_verdict_is_the_screens_for_every_posting(api_client, workspace):
    session, _ = workspace
    ids = await _ids(session)
    verdicts = set()

    for job_id in ids:
        screen = (await _screen(api_client, f"/api/jobs/{job_id}")).get("posting_reality")

        _, body = await _agent(api_client, f"/opportunities/{job_id}/reality")

        data = _data(body)
        if screen is None:
            assert (data["verdict"], data["criteria"]) == (None, []), job_id
            continue
        assert data["verdict"] == screen["level"], job_id
        assert data["criteria_total"] == screen["criteria_total"]
        assert sorted(c["key"] for c in data["criteria"] if c["met"]) == sorted(screen["met"]), job_id
        verdicts.add(data["verdict"])
    # Open postings were compared, not only closed ones without a verdict.
    assert verdicts


async def test_a_long_standing_relisted_posting_is_possible_with_its_criteria(api_client, workspace):
    session, _ = workspace
    now = datetime.now(UTC)
    job = await place_set_job(session, 60, "Leeds", title="Standing Role", company="aecom")
    job.first_seen = now - timedelta(days=200)
    job.posted_at = now - timedelta(days=2)
    await session.commit()
    screen = (await _screen(api_client, f"/api/jobs/{job.id}"))["posting_reality"]

    _, body = await _agent(api_client, f"/opportunities/{job.id}/reality")

    data = _data(body)
    assert data["verdict"] == screen["level"] == "possible"
    met = {c["key"]: c for c in data["criteria"]}
    assert sorted(key for key, c in met.items() if c["met"]) == sorted(screen["met"])
    assert met["long_open"]["met"] and met["long_open"]["observed"] >= 200 > met["long_open"]["threshold"]
    assert met["redated"]["met"] and met["redated"]["observed"] == 198
    assert (met["long_open"]["unit"], met["relisted"]["unit"]) == ("days", "listings")
    assert data["counted_from"] == "posting" and data["status"] == "open"


async def test_a_closed_posting_has_no_verdict(api_client, workspace):
    session, lineage = workspace
    assert (await _screen(api_client, f"/api/jobs/{lineage.original}")).get("posting_reality") is None

    data = _data((await _agent(api_client, f"/opportunities/{lineage.original}/reality"))[1])

    assert (data["status"], data["verdict"], data["criteria"]) == ("closed", None, [])


# --------------------------------------------------------------------------- #
# What every relation read shares
# --------------------------------------------------------------------------- #


async def _hide(session, slug: str) -> None:
    tracked = (await session.scalars(select(TrackedCompany.slug).where(TrackedCompany.slug == slug))).first()
    if tracked is None:
        session.add(make_company(slug, slug.title()))
        await session.flush()
    await session.execute(update(TrackedCompany).where(TrackedCompany.slug == slug).values(visible=False))
    await session.commit()


RELATIONS = ("similar", "duplicates", "reality")


@pytest.mark.parametrize("relation", RELATIONS)
async def test_an_unknown_posting_is_not_found(api_client, workspace, relation):
    session, _ = workspace
    (unknown,) = _unknown(await _ids(session))

    response, body = await _agent(api_client, f"/opportunities/{unknown}/{relation}")

    _error(response, body, "not_found", 5)


@pytest.mark.parametrize("relation", RELATIONS)
async def test_a_posting_at_a_hidden_company_is_not_found(api_client, workspace, relation):
    session, lineage = workspace
    response, body = await _agent(api_client, f"/opportunities/{lineage.other_company}/{relation}")
    assert response.status_code == 200, body
    await _hide(session, "acme")

    response, body = await _agent(api_client, f"/opportunities/{lineage.other_company}/{relation}")

    _error(response, body, "not_found", 5)


async def test_opt_out_refuses_every_posting_read(api_client, workspace):
    session, lineage = workspace
    await set_agent_access(session, AgentAccessConfig(enabled=False, allow_writes=False))
    await session.commit()

    for operation, path, params in (
        ("opportunities.get_many", "/opportunities/get-many", {"ids": [lineage.solo]}),
        ("opportunities.similar", f"/opportunities/{lineage.solo}/similar", {}),
        ("opportunities.duplicates", f"/opportunities/{lineage.solo}/duplicates", {}),
        ("opportunities.reality", f"/opportunities/{lineage.solo}/reality", {}),
    ):
        response, body = await _agent(api_client, path, **params)
        _error(response, body, "access_disabled", 4)
        assert body["operation"] == operation and body["data"] is None

"""Each read operation answers what the MCP tool it replaces answers.

Both sides run against one scratch database seeded by `scripts.seed_synthetic`
(its corpus postings and pursuits included): the MCP tool bodies through
`session_scope`, the operations through the agent router over real ASGI. A
tool's answer is read through the operation's own result model, which refuses
an unknown key and needs every declared one, so the comparison fails on a field
either side adds, drops or spells differently, not only on a value.

Every deliberate difference the parity checklist names for these tools is
asserted here as a difference: views and the bounded detail, not-found codes,
a company the person hid, cursor paging, the single-pursuit read and the
network effects the recipe reads declare.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, update

import tracker.agents.operations.recipes as recipe_ops
import tracker.mcp.server as server
from scripts.seed_synthetic import seed, task_req_id
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.opportunities import (
    DETAIL_BUDGET_BYTES,
    OPPORTUNITIES_GET,
    OPPORTUNITIES_HISTORY,
    ListingHistory,
    OpportunityDetail,
)
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.pursuits import PURSUITS_GET, PURSUITS_LIST, PursuitItem
from tracker.agents.operations.radar import RADAR_SUMMARY, RadarSummary
from tracker.agents.operations.recipes import (
    RECIPES_CONTRACT_GET,
    RECIPES_VALIDATE,
    SOURCES_INSPECT,
    RecipeContract,
    RecipeValidation,
    SourceInspection,
)
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.agents.pursuits import PursuitUpdate, ensure_favorite, upsert_pursuit
from tracker.api.agent_operations import PREFIX
from tracker.db.models import Favorite, Job, JobCompEstimate, Pursuit, TrackedCompany
from tracker.platform.safe_fetch import BlockedDestination
from tracker.workflows.recipe_preview import RecipeCheck

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

#: Each operation this file covers, with its smallest successful call.
READS = {
    RADAR_SUMMARY.id: ("GET", "/radar/summary", None),
    OPPORTUNITIES_GET.id: ("GET", "/opportunities/{id}", None),
    OPPORTUNITIES_HISTORY.id: ("GET", "/opportunities/{id}/history", None),
    PURSUITS_LIST.id: ("GET", "/pursuits", None),
    PURSUITS_GET.id: ("GET", "/pursuits/{id}", None),
    RECIPES_CONTRACT_GET.id: ("GET", "/recipes/contract", None),
    SOURCES_INSPECT.id: ("GET", "/sources/inspect", {"url": "https://example.com/careers"}),
    RECIPES_VALIDATE.id: ("POST", "/recipes/validate", {"document": {"id": "x"}}),
}


@pytest_asyncio.fixture
async def workspace(db_session, scratch_scope):
    """The seeded workspace with agent reads on."""
    await seed(db_session, 8, seed_value=1, derived=False, agent_tasks=True)
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    return db_session


async def _job_id(session, key: str) -> int:
    return await session.scalar(select(Job.id).where(Job.req_id == task_req_id(key)))


async def _get(api_client, path: str, **params):
    response = await api_client.get(f"{PREFIX}{path}", params=params)
    return response, response.json()


def _data(body: dict) -> dict:
    assert body["ok"] is True, body["error"]
    return body["data"]


def _error(response, body: dict, code: str, exit_status: int) -> None:
    assert body["ok"] is False and body["data"] is None
    assert body["error"]["code"] == code
    assert outcome(code).exit_status == exit_status
    assert response.status_code == outcome(code).http_status


# --------------------------------------------------------------------------- #
# radar.summary  <-  get_radar_summary
# --------------------------------------------------------------------------- #


async def test_radar_summary_answers_the_tools_counts(api_client, workspace):
    expected = RadarSummary.model_validate(await server.get_radar_summary()).model_dump(mode="json")

    response, body = await _get(api_client, "/radar/summary")

    assert response.status_code == 200
    assert _data(body) == expected
    # The seeded corpus is not empty, so equal counts are not two zeros.
    assert expected["active_pursuits"] == 4 and expected["overdue_next_actions"] == 2
    assert expected["open_opportunities"] > 0
    assert body["meta"]["data_classes"] == ["market_statistic", "private_pursuit"]


async def test_radar_summary_follows_a_hidden_company_as_the_tool_does(api_client, workspace):
    before = _data((await _get(api_client, "/radar/summary"))[1])["open_opportunities"]
    # A company with a role on the Board, so hiding it changes the count.
    company = (await server.search_opportunities())["items"][0]["company"]
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == company).values(visible=False))
    await workspace.commit()

    after = _data((await _get(api_client, "/radar/summary"))[1])

    assert after == RadarSummary.model_validate(await server.get_radar_summary()).model_dump(mode="json")
    assert after["open_opportunities"] < before


# --------------------------------------------------------------------------- #
# opportunities.get  <-  get_opportunity
# --------------------------------------------------------------------------- #


async def _visible_ids(session) -> list[int]:
    return list((await session.scalars(select(Job.id).order_by(Job.id))).all())


async def test_the_detail_view_answers_the_tools_posting_for_every_seeded_role(api_client, workspace):
    ids = await _visible_ids(workspace)
    assert len(ids) > 8

    revisions = await _revisions(workspace)
    for job_id in ids:
        tool = await server.get_opportunity(job_id)
        expected = OpportunityDetail.model_validate(
            {**tool, "view": "detail", "excerpt": None, "pursuit": _with_revision(tool["pursuit"], revisions)}
        )
        _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="full")
        assert _data(body) == expected.model_dump(mode="json"), job_id
        assert body["meta"]["truncated"] is False


async def test_stated_pay_and_estimates_stay_apart_as_the_tool_keeps_them(api_client, workspace):
    stated = await _job_id(workspace, "SAVED")
    await workspace.execute(
        update(Job).where(Job.id == stated).values(
            disclosed_base_min=212_000, disclosed_base_max=264_500, disclosed_currency="USD",
            disclosed_pay_basis="base", disclosed_pay_period="year", disclosed_snippet="$212,000 - $264,500",
            structured_at=datetime.now(UTC), comp_median=None, comp_low=None, comp_high=None,
        )
    )
    await workspace.commit()

    data = _data((await _get(api_client, f"/opportunities/{stated}"))[1])

    assert data["employer_stated_pay"]["low"] == 212_000
    assert data["estimated_total_comp"] is None
    tool = await server.get_opportunity(stated)
    assert data["employer_stated_pay"] == {**tool["employer_stated_pay"]}
    assert data["estimated_total_comp"] == tool["estimated_total_comp"]


async def test_the_summary_view_is_the_detail_less_its_text(api_client, workspace):
    job_id = await _job_id(workspace, "FOLLOWUP")
    detail = _data((await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="full"))[1])

    response, body = await _get(api_client, f"/opportunities/{job_id}")

    summary = _data(body)
    text_keys = {"department", "team", "description", "description_sections", "excerpt"}
    assert summary["view"] == "summary"
    assert summary == {**{k: v for k, v in detail.items() if k not in text_keys}, "view": "summary"}
    assert "description" not in json.dumps(summary)
    # The pursuit rides along, as on the tool.
    assert summary["pursuit"]["stage"] == "applied"


async def test_the_evidence_view_names_each_date_and_each_pay_source(api_client, workspace):
    job_id = await _job_id(workspace, "INTERVIEW")
    # The employer re-dated the posting: its current date moved, its first did not.
    first, current = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 20, tzinfo=UTC)
    await workspace.execute(update(Job).where(Job.id == job_id).values(first_posted_at=first, posted_at=current))
    job = await workspace.get(Job, job_id)
    # A plugin's estimate beside RoleBand's own: two sources, never mixed.
    workspace.add(JobCompEstimate(
        job_id=job_id, source="plugin.pay", comp_median=300_000, comp_currency="USD",
        sources=[{"provider": "static", "median": 300_000, "low": 250_000, "high": 350_000,
                  "currency": "USD", "source": "levels"}],
    ))
    await workspace.commit()
    stored = (await workspace.scalars(
        select(JobCompEstimate).where(JobCompEstimate.job_id == job_id).order_by(JobCompEstimate.source)
    )).all()

    data = _data((await _get(api_client, f"/opportunities/{job_id}", view="evidence"))[1])

    assert data["view"] == "evidence"
    dates = data["evidence"]["dates"]
    assert datetime.fromisoformat(dates["employer_published_at"]) == current
    assert datetime.fromisoformat(dates["employer_first_published_at"]) == first
    assert datetime.fromisoformat(dates["first_seen"]) == job.first_seen
    assert datetime.fromisoformat(dates["last_seen"]) == job.last_seen
    assert dates["closed_at"] is None
    sources = data["evidence"]["estimate_sources"]
    assert [s["source"] for s in sources] == [row.source for row in stored] == ["plugin.pay", "roleband"]
    assert sources[0]["answers"] == [
        {"provider": "static", "median": 300_000, "low": 250_000, "high": 350_000,
         "currency": "USD", "source": "levels"}
    ]
    assert len(sources[1]["answers"]) == len(stored[1].sources)
    assert "description" not in data
    # The facts are the summary's.
    summary = _data((await _get(api_client, f"/opportunities/{job_id}"))[1])
    assert {k: v for k, v in data.items() if k not in {"view", "evidence"}} == {
        k: v for k, v in summary.items() if k != "view"
    }


async def test_an_unknown_opportunity_is_not_found_with_exit_five(api_client, workspace):
    with pytest.raises(LookupError):
        await server.get_opportunity(999_999)
    for path in ("/opportunities/999999", "/opportunities/999999/history"):
        response, body = await _get(api_client, path)
        _error(response, body, "not_found", 5)
        assert body["error"]["details"] == {"opportunity_id": 999_999}


async def test_an_id_that_is_not_a_positive_integer_is_invalid_input(api_client, workspace):
    for path in ("/opportunities/abc", "/opportunities/0", "/pursuits/-1"):
        response, body = await _get(api_client, path)
        _error(response, body, "invalid_input", 2)


async def test_a_posting_at_a_company_the_person_hid_is_not_returned_unless_they_chose_it(api_client, workspace):
    job_id = (
        await workspace.scalars(
            select(Job.id).where(Job.id.notin_(select(Favorite.job_id)), Job.id.notin_(select(Pursuit.job_id)))
        )
    ).first()
    company = (await workspace.get(Job, job_id)).company
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == company).values(visible=False))
    await workspace.commit()

    # The tool answers it regardless: the deliberate difference.
    assert (await server.get_opportunity(job_id))["id"] == job_id
    for path in (f"/opportunities/{job_id}", f"/opportunities/{job_id}/history"):
        response, body = await _get(api_client, path)
        _error(response, body, "not_found", 5)
        # Told apart from a missing posting by nothing.
        assert body["error"]["details"] == {"opportunity_id": job_id}

    # Saved, it is the person's choice again and opens, as it does from Saved.
    await ensure_favorite(workspace, job_id)
    await workspace.commit()
    assert _data((await _get(api_client, f"/opportunities/{job_id}"))[1])["id"] == job_id
    assert _data((await _get(api_client, f"/opportunities/{job_id}/history"))[1])["headline"]


async def test_an_unfollowed_company_is_not_hidden(api_client, workspace):
    job_id = await _job_id(workspace, "RESEARCH")
    company = (await workspace.get(Job, job_id)).company
    await workspace.execute(update(Pursuit).where(Pursuit.job_id == job_id).values(stage="saved"))
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == company).values(enabled=False))
    await workspace.commit()

    assert _data((await _get(api_client, f"/opportunities/{job_id}"))[1])["id"] == job_id


# --- the bounded detail view


_SENTENCE = 'Ship "the platform" — résumé reviews, 東京 & 5\\6 rollouts\n'


async def _with_description(session, key: str, text: str, sections: int) -> tuple[int, str]:
    job_id = await _job_id(session, key)
    rows = [{"key": f"s{n}", "title": f"Part {n}", "content": text[:2_000]} for n in range(sections)]
    await session.execute(
        update(Job).where(Job.id == job_id).values(description_text=text, description_sections=rows)
    )
    await session.commit()
    return job_id, text


def _bytes(data: dict) -> int:
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode())


async def test_a_detail_past_the_small_budget_is_a_typed_excerpt_never_cut_json(api_client, workspace):
    job_id, text = await _with_description(workspace, "FOLLOWUP", _SENTENCE * 1_500, sections=4)
    assert _bytes({"d": text}) > DETAIL_BUDGET_BYTES["small"] * 4

    response, body = await _get(api_client, f"/opportunities/{job_id}", view="detail")

    assert response.status_code == 200
    data = _data(body)
    excerpt = data["excerpt"]
    assert excerpt["truncated"] is True and excerpt["tier"] == "small"
    assert excerpt["budget_bytes"] == DETAIL_BUDGET_BYTES["small"]
    assert excerpt["description_chars"] == len(text) and excerpt["omitted_sections"] == 4
    assert excerpt["full_bytes"] > excerpt["budget_bytes"]
    assert _bytes(data) <= DETAIL_BUDGET_BYTES["small"]
    # Most of the budget is text, and the text is the description's own start,
    # cut at a word.
    assert len(data["description"]) == excerpt["kept_chars"] > len(text) // 20
    assert text.startswith(data["description"])
    assert text[len(data["description"])] in " \n"
    assert data["description_sections"] == []
    assert body["meta"]["truncated"] is True
    assert [w["code"] for w in body["warnings"]] == ["truncated"]
    # The rest of the posting is whole.
    assert data["title"] == (await server.get_opportunity(job_id))["title"]


async def test_notes_too_long_for_the_budget_are_cut_too_and_read_whole_elsewhere(api_client, workspace):
    job_id, text = await _with_description(workspace, "FOLLOWUP", _SENTENCE * 300, sections=1)
    notes = "Recruiter said: \"call back\" — résumé v2 sent\n" * 440
    assert len(notes) <= 20_000 and _bytes({"n": notes}) > DETAIL_BUDGET_BYTES["small"]
    await workspace.execute(update(Pursuit).where(Pursuit.job_id == job_id).values(notes=notes))
    await workspace.commit()

    response, body = await _get(api_client, f"/opportunities/{job_id}", view="detail")

    assert response.status_code == 200
    data = _data(body)
    assert _bytes(data) <= DETAIL_BUDGET_BYTES["small"]
    excerpt = data["excerpt"]
    assert excerpt["notes_chars"] == len(notes)
    kept = data["pursuit"]["notes"]
    assert len(kept) == excerpt["kept_notes_chars"] < len(notes)
    assert notes.startswith(kept) and len(kept) > len(notes) // 2
    # Notes are the person's: the description goes first, all of it.
    assert data["description"] == "" and excerpt["kept_chars"] == 0
    # Read whole where the pursuit is the subject.
    whole = _data((await _get(api_client, f"/pursuits/{job_id}"))[1])
    assert whole["notes"] == notes


async def test_notes_that_fit_are_kept_whole_while_the_description_is_cut(api_client, workspace):
    job_id, text = await _with_description(workspace, "FOLLOWUP", _SENTENCE * 1_500, sections=0)
    await workspace.execute(update(Pursuit).where(Pursuit.job_id == job_id).values(notes="Follow up Tuesday."))
    await workspace.commit()

    data = _data((await _get(api_client, f"/opportunities/{job_id}", view="detail"))[1])

    assert data["pursuit"]["notes"] == "Follow up Tuesday."
    assert data["excerpt"]["notes_chars"] == data["excerpt"]["kept_notes_chars"] == len("Follow up Tuesday.")
    assert 0 < data["excerpt"]["kept_chars"] < len(text)


async def test_a_larger_tier_takes_the_whole_description(api_client, workspace):
    job_id, text = await _with_description(workspace, "FOLLOWUP", _SENTENCE * 300, sections=2)
    small = _data((await _get(api_client, f"/opportunities/{job_id}", view="detail"))[1])
    assert small["excerpt"] is not None

    _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="standard")

    data = _data(body)
    assert data["excerpt"] is None and data["description"] == text
    assert len(data["description_sections"]) == 2
    assert body["meta"]["truncated"] is False and body["warnings"] == []


async def test_a_detail_within_budget_is_whole_and_unmarked(api_client, workspace):
    job_id = await _job_id(workspace, "INTERVIEW")

    _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail")

    data = _data(body)
    assert data["excerpt"] is None
    assert data["description"] == (await server.get_opportunity(job_id))["description"]


# --------------------------------------------------------------------------- #
# opportunities.history  <-  listing_history
# --------------------------------------------------------------------------- #


async def test_history_answers_the_tools_history_for_every_seeded_role(api_client, workspace):
    for job_id in await _visible_ids(workspace):
        expected = ListingHistory.model_validate(await server.listing_history(job_id)).model_dump(mode="json")
        _, body = await _get(api_client, f"/opportunities/{job_id}/history")
        assert _data(body) == expected, job_id
        assert expected["events"], "a posting has at least its first sighting"


# --------------------------------------------------------------------------- #
# pursuits.list and pursuits.get  <-  get_pursuits
# --------------------------------------------------------------------------- #


async def _revisions(session) -> dict[int, int]:
    """Each pursuit's revision by its opportunity, which no MCP answer carries."""
    session.expire_all()
    return dict((await session.execute(select(Pursuit.job_id, Pursuit.revision))).all())


def _with_revision(pursuit: dict | None, revisions: dict[int, int]) -> dict | None:
    return None if pursuit is None else {**pursuit, "revision": revisions[pursuit["job_id"]]}


def _items(tool: dict, revisions: dict[int, int]) -> list[dict]:
    return [
        PursuitItem.model_validate(_with_revision(item, revisions)).model_dump(mode="json")
        for item in tool["items"]
    ]


async def test_pursuits_list_answers_the_tools_pursuits_for_each_stage(api_client, workspace):
    for stage in (None, "applied", "saved", "researching", "interviewing", "offer"):
        params = {"stage": stage} if stage else {}
        tool = await server.get_pursuits(**params)
        _, body = await _get(api_client, "/pursuits", **params)
        data = _data(body)
        assert data == {"count": tool["count"], "items": _items(tool, await _revisions(workspace))}, stage
        assert body["meta"]["next_cursor"] is None
    assert (await server.get_pursuits())["count"] == 4


async def test_pursuit_notes_are_read_back(api_client, workspace):
    items = _data((await _get(api_client, "/pursuits"))[1])["items"]
    assert {item["notes"] for item in items} >= {"Onsite loop booked: four rounds, one of them system design."}


async def _many_pursuits(session) -> None:
    """Every seeded posting pursued, several at one priority, so the order's ties matter."""
    for job_id in await _visible_ids(session):
        await upsert_pursuit(session, job_id, PursuitUpdate(priority=3), actor="user")
    await session.commit()


async def test_cursor_pages_read_every_pursuit_once_in_the_tools_order(api_client, workspace):
    await _many_pursuits(workspace)
    tool = await server.get_pursuits(limit=100)
    assert tool["count"] > 8

    seen: list[dict] = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        _, body = await _get(api_client, "/pursuits", **params)
        data = _data(body)
        seen.extend(data["items"])
        pages += 1
        cursor = body["meta"]["next_cursor"]
        if cursor is None:
            break
        assert data["count"] == 3

    assert seen == _items(tool, await _revisions(workspace))
    assert pages == -(-tool["count"] // 3)


async def test_a_full_last_page_hands_out_no_cursor(api_client, workspace):
    _, body = await _get(api_client, "/pursuits", limit=4)
    assert _data(body)["count"] == 4
    assert body["meta"]["next_cursor"] is None


async def test_a_cursor_is_refused_with_other_filters_another_workspace_or_garbled(api_client, workspace):
    await _many_pursuits(workspace)
    _, first = await _get(api_client, "/pursuits", limit=2)
    cursor = first["meta"]["next_cursor"]
    assert cursor

    response, body = await _get(api_client, "/pursuits", limit=2, cursor=cursor, stage="applied")
    _error(response, body, "invalid_input", 2)
    assert body["error"]["details"] == {"field": "cursor", "reason": "other_filters"}

    raw = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    forged = base64.urlsafe_b64encode(json.dumps({**raw, "w": "ws_" + "0" * 32}).encode()).decode()
    response, body = await _get(api_client, "/pursuits", limit=2, cursor=forged)
    _error(response, body, "invalid_input", 2)
    assert body["error"]["details"]["reason"] == "other_workspace"

    for garbled in ("not-a-cursor", cursor[:-4], base64.urlsafe_b64encode(b"[1,2]").decode()):
        response, body = await _get(api_client, "/pursuits", cursor=garbled)
        _error(response, body, "invalid_input", 2)


async def test_a_limit_outside_the_declared_range_is_an_input_error(api_client, workspace):
    # The tool clamps it; the operation names the range instead.
    assert (await server.get_pursuits(limit=500))["count"] == 4
    for limit in (0, 101):
        response, body = await _get(api_client, "/pursuits", limit=limit)
        _error(response, body, "invalid_input", 2)


async def test_pursuits_get_reads_one_pursuit_by_its_opportunity(api_client, workspace):
    listed = _items(await server.get_pursuits(), await _revisions(workspace))
    for item in listed:
        _, body = await _get(api_client, f"/pursuits/{item['job_id']}")
        assert _data(body) == item
        assert body["meta"]["data_classes"] == ["private_pursuit", "public_posting"]


async def test_each_pursuit_carries_the_revision_a_dashboard_write_advances(api_client, workspace):
    job_id = await _job_id(workspace, "SAVED")
    before = _data((await _get(api_client, f"/pursuits/{job_id}"))[1])
    assert all("revision" not in item for item in (await server.get_pursuits())["items"])
    assert before["revision"] >= 1

    await upsert_pursuit(workspace, job_id, PursuitUpdate(notes="Spoke to Sam."), actor="user")
    await workspace.commit()

    after = _data((await _get(api_client, f"/pursuits/{job_id}"))[1])
    assert after["notes"] == "Spoke to Sam."
    assert after["revision"] == before["revision"] + 1
    listed = {item["job_id"]: item for item in _data((await _get(api_client, "/pursuits"))[1])["items"]}
    assert listed[job_id]["revision"] == after["revision"]
    opportunity = _data((await _get(api_client, f"/opportunities/{job_id}"))[1])
    assert opportunity["pursuit"]["revision"] == after["revision"]


async def test_pursuits_get_of_a_role_without_a_pursuit_is_not_found(api_client, workspace):
    unpursued = (await workspace.scalars(select(Job.id).where(Job.id.notin_(select(Pursuit.job_id))))).first()
    for job_id in (unpursued, 999_999):
        response, body = await _get(api_client, f"/pursuits/{job_id}")
        _error(response, body, "not_found", 5)
        assert body["error"]["details"] == {"opportunity_id": job_id}


async def test_a_pursuit_at_a_hidden_company_is_still_the_persons(api_client, workspace):
    job_id = await _job_id(workspace, "INTERVIEW")
    company = (await workspace.get(Job, job_id)).company
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == company).values(visible=False))
    await workspace.commit()

    assert _data((await _get(api_client, f"/pursuits/{job_id}"))[1])["job_id"] == job_id
    assert job_id in {item["job_id"] for item in _data((await _get(api_client, "/pursuits"))[1])["items"]}


# --------------------------------------------------------------------------- #
# The recipe reads  <-  get_recipe_contract, inspect_source, validate_recipe
# --------------------------------------------------------------------------- #


async def test_the_recipe_contract_is_the_tools(api_client, workspace):
    expected = RecipeContract.model_validate(await server.get_recipe_contract()).model_dump(mode="json", by_alias=True)

    _, body = await _get(api_client, "/recipes/contract")

    assert _data(body) == expected
    assert set(_data(body)) == {"schema", "transports", "transforms", "rules"}
    assert _data(body)["schema"]["type"] == "object"


class _Page:
    final_url = "https://jobs.example.com/careers"
    status = 200
    truncated = False
    text = (
        "<html><body><script>alert(1)</script><h1>Careers</h1>"
        + "".join(f'<a class="job" href="/j/{n}">Role {n}</a>' for n in range(30))
        + "<p>" + "word " * 5_000 + "</p></body></html>"
    )


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


@pytest.fixture
def fake_page(monkeypatch):
    """One public page in place of the network, for the tool and the operation alike."""
    fetched: list[str] = []

    async def fetch(_client, url, *, max_bytes):
        fetched.append(url)
        if "169.254" in url:
            raise BlockedDestination("non-public address")
        return _Page()

    for module in (server, recipe_ops):
        monkeypatch.setattr(module, "fetch_public", fetch)
        monkeypatch.setattr(module, "public_client", lambda **_: _Client())
    return fetched


@pytest.mark.parametrize("selector", [None, "a.job", "h1"])
async def test_source_inspection_answers_the_tools_inspection(api_client, workspace, fake_page, selector):
    url = "https://jobs.example.com/careers"
    params = {"url": url, **({"selector": selector} if selector else {})}
    expected = SourceInspection.model_validate(await server.inspect_source(url, selector)).model_dump(mode="json")

    _, body = await _get(api_client, "/sources/inspect", **params)

    data = _data(body)
    assert data == expected
    assert "alert(1)" not in data["content"]
    if selector == "a.job":
        assert data["matches"] == 20
    if selector is None:
        assert data["content_truncated"] is True and len(data["content"]) == 12_000
    assert fake_page == [url, url]


async def test_a_blocked_address_is_an_input_error_not_a_crash(api_client, workspace, fake_page):
    with pytest.raises(BlockedDestination):
        await server.inspect_source("http://169.254.169.254/")

    response, body = await _get(api_client, "/sources/inspect", url="http://169.254.169.254/")

    _error(response, body, "invalid_input", 2)
    assert body["error"]["details"] == {"field": "url", "reason": "blocked_destination"}


@pytest.fixture
def fake_preview(monkeypatch):
    seen: list[dict] = []

    async def preview(document):
        seen.append(document)
        if document.get("id") == "broken":
            return RecipeCheck(problems=["match.domains is required"])
        return RecipeCheck(
            jobs=[{"title": "Role 1", "url": "https://jobs.example.com/j/1"}], found=1, pages=1,
            robots={"allowed": True, "url": "https://jobs.example.com/robots.txt"},
        )

    for module in (server, recipe_ops):
        monkeypatch.setattr(module, "preview_document", preview)
    return seen


@pytest.mark.parametrize("recipe_id", ["acme", "broken"])
async def test_recipe_validation_answers_the_tools_validation(api_client, workspace, fake_preview, recipe_id):
    document = {"id": recipe_id, "version": 1, "nested": {"list": [1, "two", None]}}
    expected = RecipeValidation.model_validate(await server.validate_recipe(document)).model_dump(mode="json")

    response = await api_client.post(f"{PREFIX}/recipes/validate", json={"document": document})

    assert response.status_code == 200
    assert _data(response.json()) == expected
    assert expected["compiles"] is (recipe_id == "acme")
    # The document arrived whole.
    assert fake_preview == [document, document]


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[1, 2]", b'{"document": {}, "extra": 1}', b'{"document": "a string"}', b"{}"],
    ids=["not-json", "not-an-object", "unknown-key", "not-a-document", "no-document"],
)
async def test_a_validation_body_that_is_not_one_document_is_an_input_error(api_client, workspace, fake_preview, body):
    response = await api_client.post(
        f"{PREFIX}/recipes/validate", content=body, headers={"content-type": "application/json"}
    )
    _error(response, response.json(), "invalid_input", 2)
    assert fake_preview == []


# --------------------------------------------------------------------------- #
# What every one of these reads shares
# --------------------------------------------------------------------------- #


async def _call(api_client, operation: str, job_id: int, *, extra: dict | None = None):
    method, path, given = READS[operation]
    url = f"{PREFIX}{path.replace('{id}', str(job_id))}"
    if method == "POST":
        return await api_client.post(url, params=extra or {}, json=given)
    return await api_client.get(url, params={**(given or {}), **(extra or {})})


async def test_opt_out_refuses_every_read_and_names_no_workspace(api_client, workspace, fake_page, fake_preview):
    job_id = await _job_id(workspace, "INTERVIEW")
    await set_agent_access(workspace, AgentAccessConfig(enabled=False, allow_writes=True))
    await workspace.commit()

    for operation in READS:
        response = await _call(api_client, operation, job_id)
        body = response.json()
        _error(response, body, "access_disabled", 4)
        assert body["operation"] == operation and body["workspace_id"] is None
    # Refused before anything was fetched or previewed.
    assert fake_page == [] and fake_preview == []

    # The tools refuse too, under the same switch.
    with pytest.raises(PermissionError):
        await server.get_pursuits()


async def test_every_read_answers_when_on_and_refuses_an_unknown_key(api_client, workspace, fake_page, fake_preview):
    job_id = await _job_id(workspace, "INTERVIEW")

    for operation in READS:
        response = await _call(api_client, operation, job_id)
        assert response.status_code == 200, (operation, response.json())
        assert response.json()["operation"] == operation

        response = await _call(api_client, operation, job_id, extra={"verbose": "1"})
        _error(response, response.json(), "invalid_input", 2)

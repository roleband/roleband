"""The agent reads answer what their owners hold.

Run against one scratch database seeded by `scripts.seed_synthetic` (its
corpus postings and pursuits included), through the agent router over real
ASGI. Each answer is held to an independent owner: the stored rows, the
dashboard route that answers the same question (`/api/stats`,
`/api/jobs/{id}/history`), or the recipe module's own constants, never to the
operation's own output.

Also held here: views and the bounded detail, not-found codes, a company the
person hid, cursor paging, the single-pursuit read, the network effects the
recipe reads declare, and what every read shares under the access switch.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

import tracker.agents.operations.recipes as recipe_ops
from scripts.seed_synthetic import seed, task_req_id
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.opportunities import (
    DETAIL_BUDGET_BYTES,
    OPPORTUNITIES_GET,
    OPPORTUNITIES_HISTORY,
    ListingHistory,
)
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.pursuits import PURSUITS_GET, PURSUITS_LIST
from tracker.agents.operations.radar import RADAR_SUMMARY
from tracker.agents.operations.recipes import (
    RECIPES_CONTRACT_GET,
    RECIPES_VALIDATE,
    SOURCES_INSPECT,
)
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.agents.pursuits import PursuitUpdate, ensure_favorite, upsert_pursuit
from tracker.api.agent_operations import PREFIX
from tracker.connectors.recipes import RECIPE_V1_SCHEMA, TRANSFORM_NAMES, TRANSPORT_MODES
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
# radar.summary
# --------------------------------------------------------------------------- #


async def test_radar_summary_counts_what_the_board_and_the_pursuits_hold(api_client, workspace):
    stats = (await api_client.get("/api/stats")).json()

    response, body = await _get(api_client, "/radar/summary")

    assert response.status_code == 200
    data = _data(body)
    # The open count is the Board's own, and the seeded pursuits are four, two overdue.
    assert data["open_opportunities"] == stats["open_total"] > 0
    assert data["active_pursuits"] == 4 and data["overdue_next_actions"] == 2
    assert data["saved_opportunities"] == await workspace.scalar(select(func.count()).select_from(Favorite))
    stored = dict((await workspace.execute(select(Pursuit.stage, func.count()).group_by(Pursuit.stage))).all())
    assert data["pursuits_by_stage"] == stored and sum(stored.values()) == 4
    assert body["meta"]["data_classes"] == ["market_statistic", "private_pursuit"]


async def test_radar_summary_follows_a_hidden_company_as_the_board_does(api_client, workspace):
    before = _data((await _get(api_client, "/radar/summary"))[1])["open_opportunities"]
    # A company with a role on the Board, so hiding it changes the count.
    company = (await api_client.get("/api/jobs?limit=1")).json()["items"][0]["company"]
    await workspace.execute(update(TrackedCompany).where(TrackedCompany.slug == company).values(visible=False))
    await workspace.commit()

    after = _data((await _get(api_client, "/radar/summary"))[1])["open_opportunities"]

    assert after == (await api_client.get("/api/stats")).json()["open_total"]
    assert after < before


# --------------------------------------------------------------------------- #
# opportunities.get
# --------------------------------------------------------------------------- #


async def _visible_ids(session) -> list[int]:
    return list((await session.scalars(select(Job.id).order_by(Job.id))).all())


async def _stored_posting(session, job_id: int) -> dict:
    """What the rows say the detail view must answer for a posting."""
    session.expire_all()
    job = await session.get(Job, job_id)
    pursuit = await session.scalar(select(Pursuit).where(Pursuit.job_id == job_id))
    saved = await session.scalar(select(Favorite.id).where(Favorite.job_id == job_id)) is not None
    return {
        "id": job.id, "company": job.company, "title": job.title, "url": job.url,
        "locations": list(job.locations or []), "workplace_type": job.workplace_type,
        "level_band": job.level_band, "family": job.family, "track": job.track, "status": job.status,
        "department": job.department, "team": job.team,
        "description": job.description_text or "",
        "description_sections": list(job.description_sections or []),
        "saved": saved,
        "pursuit": None if pursuit is None else {
            "opportunity_id": job_id, "stage": pursuit.stage, "priority": pursuit.priority,
            "notes": pursuit.notes, "next_action": pursuit.next_action, "revision": pursuit.revision,
        },
    }


async def test_the_detail_view_answers_the_stored_posting_for_every_seeded_role(api_client, workspace):
    ids = await _visible_ids(workspace)
    assert len(ids) > 8
    pursued = 0

    for job_id in ids:
        expected = await _stored_posting(workspace, job_id)
        _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="full")
        data = _data(body)
        assert {key: data[key] for key in expected if key != "pursuit"} == {
            key: value for key, value in expected.items() if key != "pursuit"
        }, job_id
        stated = expected["pursuit"]
        if stated is None:
            assert data["pursuit"] is None, job_id
        else:
            pursued += 1
            assert {key: data["pursuit"][key] for key in stated} == stated, job_id
        assert data["view"] == "detail" and data["excerpt"] is None
        assert body["meta"]["truncated"] is False
    # A role with a pursuit and one without are both read, so a pursuit
    # attached to the wrong role or to every role would fail.
    assert 0 < pursued < len(ids)


async def test_stated_pay_and_estimates_stay_apart(api_client, workspace):
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

    assert data["employer_stated_pay"] == {
        "low": 212_000, "high": 264_500, "currency": "USD", "basis": "base", "period": "year",
        "snippet": "$212,000 - $264,500",
    }
    # The stated band never fills the estimate.
    assert data["estimated_total_comp"] is None

    # And an estimate never fills the stated band.
    await workspace.execute(
        update(Job).where(Job.id == stated).values(
            disclosed_base_min=None, disclosed_base_max=None, disclosed_snippet=None,
            comp_low=150_000, comp_median=180_000, comp_high=210_000,
        )
    )
    await workspace.commit()
    data = _data((await _get(api_client, f"/opportunities/{stated}"))[1])
    assert data["estimated_total_comp"]["median"] == 180_000
    assert data["employer_stated_pay"] is None or data["employer_stated_pay"]["low"] is None


async def test_the_summary_view_is_the_detail_less_its_text(api_client, workspace):
    job_id = await _job_id(workspace, "FOLLOWUP")
    detail = _data((await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="full"))[1])

    response, body = await _get(api_client, f"/opportunities/{job_id}")

    summary = _data(body)
    text_keys = {"department", "team", "description", "description_sections", "excerpt"}
    assert summary["view"] == "summary"
    # Less its text, and with the one call that reads it.
    assert summary["continue_with"] == [
        {"operation": "opportunities.get", "arguments": {"opportunity_id": job_id, "view": "detail", "tier": "small"}}
    ]
    assert {k: v for k, v in summary.items() if k != "continue_with"} == {
        **{k: v for k, v in detail.items() if k not in text_keys}, "view": "summary",
    }
    assert "description" not in json.dumps(summary)
    # The pursuit rides along.
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
        k: v for k, v in summary.items() if k not in {"view", "continue_with"}
    }


async def test_an_unknown_opportunity_is_not_found_with_exit_five(api_client, workspace):
    # The dashboard's posting route agrees that there is no such posting.
    assert (await api_client.get("/api/jobs/999999")).status_code == 404
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
    assert data["title"] == await workspace.scalar(select(Job.title).where(Job.id == job_id))


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


async def test_a_posting_too_large_even_without_its_text_is_refused_not_answered_past_budget(
    api_client, workspace,
):
    job_id = await _job_id(workspace, "FOLLOWUP")
    title = "Staff engineer " * 1_100
    assert _bytes({"t": title}) > DETAIL_BUDGET_BYTES["small"]
    await workspace.execute(update(Job).where(Job.id == job_id).values(title=title))
    await workspace.commit()

    response, body = await _get(api_client, f"/opportunities/{job_id}", view="detail")

    _error(response, body, "invalid_input", 2)
    details = body["error"]["details"]
    assert details["field"] == "tier" and details["reason"] == "over_budget"
    assert details["budget_bytes"] == DETAIL_BUDGET_BYTES["small"] < details["full_bytes"]
    # A larger tier holds it whole.
    _, whole = await _get(api_client, f"/opportunities/{job_id}", view="detail", tier="standard")
    assert _data(whole)["title"] == title and _data(whole)["excerpt"] is None


async def test_notes_that_fit_are_kept_whole_while_the_description_is_cut(api_client, workspace):
    job_id, text = await _with_description(workspace, "FOLLOWUP", _SENTENCE * 1_500, sections=0)
    await workspace.execute(update(Pursuit).where(Pursuit.job_id == job_id).values(notes="Follow up Tuesday."))
    await workspace.commit()

    data = _data((await _get(api_client, f"/opportunities/{job_id}", view="detail"))[1])

    assert data["pursuit"]["notes"] == "Follow up Tuesday."
    assert data["excerpt"]["notes_chars"] == data["excerpt"]["kept_notes_chars"] == len("Follow up Tuesday.")
    assert 0 < data["excerpt"]["kept_chars"] < len(text)


async def _follow(api_client, action: dict) -> dict:
    """Make the call an excerpt names, as an agent would."""
    assert action["operation"] == "opportunities.get"
    arguments = dict(action["arguments"])
    job_id = arguments.pop("opportunity_id")
    response, body = await _get(api_client, f"/opportunities/{job_id}", **arguments)
    assert response.status_code == 200, body
    return body


async def test_following_continue_with_reads_the_whole_description_a_page_at_a_time(api_client, workspace):
    job_id, text = await _with_description(workspace, "FOLLOWUP", _SENTENCE * 1_500, sections=3)

    _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail")
    pages = [_data(body)]
    while (calls := [c for c in pages[-1]["excerpt"]["continue_with"] if c["operation"] == "opportunities.get"]):
        assert len(calls) == 1 and len(pages) < 20
        assert calls[0]["arguments"] == {
            "opportunity_id": job_id, "view": "detail", "tier": "small",
            "description_from": pages[-1]["excerpt"]["description_from"] + pages[-1]["excerpt"]["kept_chars"],
        }
        pages.append(_data(await _follow(api_client, calls[0])))

    assert len(pages) > 3
    assert "".join(page["description"] for page in pages) == text
    for page in pages:
        assert _bytes(page) <= DETAIL_BUDGET_BYTES["small"]
        assert page["excerpt"]["truncated"] is True and page["description_sections"] == []
        assert page["excerpt"]["description_chars"] == len(text)
    # The last page names no more description; a later page leaves the
    # pursuit's notes out, so it names them whole instead.
    notes = await workspace.scalar(select(Pursuit.notes).where(Pursuit.job_id == job_id))
    assert notes
    assert pages[-1]["excerpt"]["continue_with"] == [
        {"operation": "pursuits.get", "arguments": {"opportunity_id": job_id}}
    ]
    assert all(page["pursuit"]["notes"] == "" for page in pages[1:])


async def test_cut_notes_are_named_for_pursuits_get_and_left_out_of_later_pages(api_client, workspace):
    job_id, text = await _with_description(workspace, "FOLLOWUP", _SENTENCE * 600, sections=0)
    notes = "Recruiter said: \"call back\" — résumé v2 sent\n" * 440
    await workspace.execute(update(Pursuit).where(Pursuit.job_id == job_id).values(notes=notes))
    await workspace.commit()

    first = _data((await _get(api_client, f"/opportunities/{job_id}", view="detail"))[1])

    assert first["description"] == "" and first["excerpt"]["kept_notes_chars"] < len(notes)
    assert first["excerpt"]["continue_with"] == [
        {"operation": "opportunities.get",
         "arguments": {"opportunity_id": job_id, "view": "detail", "tier": "small", "description_from": 0}},
        {"operation": "pursuits.get", "arguments": {"opportunity_id": job_id}},
    ]
    # Read from a point, the page is the description's: the notes are left out
    # and named, so the description advances even though the notes never fit.
    second = _data(await _follow(api_client, first["excerpt"]["continue_with"][0]))
    assert second["pursuit"]["notes"] == "" and second["excerpt"]["kept_notes_chars"] == 0
    assert second["excerpt"]["notes_chars"] == len(notes)
    assert text.startswith(second["description"]) and second["excerpt"]["kept_chars"] > 0
    assert {"operation": "pursuits.get", "arguments": {"opportunity_id": job_id}} in second["excerpt"]["continue_with"]
    assert _data((await _get(api_client, f"/pursuits/{job_id}"))[1])["notes"] == notes


async def test_a_read_from_the_start_of_a_detail_that_fits_is_the_whole_view(api_client, workspace):
    job_id, _ = await _with_description(workspace, "INTERVIEW", "Lead the payments team.", sections=2)
    await workspace.execute(update(Pursuit).where(Pursuit.job_id == job_id).values(notes="Ask about on-call."))
    await workspace.commit()
    whole = _data((await _get(api_client, f"/opportunities/{job_id}", view="detail"))[1])
    assert whole["excerpt"] is None and len(whole["description_sections"]) == 2
    assert whole["pursuit"]["notes"] == "Ask about on-call."

    _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail", description_from=0)

    assert _data(body) == whole
    assert body["meta"]["truncated"] is False and body["warnings"] == []


async def test_a_long_run_of_whitespace_is_read_through_not_refused(api_client, workspace):
    text = "Intro" + " " * 50_000 + "End"
    job_id, _ = await _with_description(workspace, "FOLLOWUP", text, sections=0)

    _, body = await _get(api_client, f"/opportunities/{job_id}", view="detail")
    pages = [_data(body)]
    while (calls := [c for c in pages[-1]["excerpt"]["continue_with"] if c["operation"] == "opportunities.get"]):
        assert len(pages) < 20
        pages.append(_data(await _follow(api_client, calls[0])))

    assert len(pages) > 2
    assert "".join(page["description"] for page in pages) == text
    assert all(_bytes(page) <= DETAIL_BUDGET_BYTES["small"] for page in pages)


@pytest.mark.parametrize(
    ("params", "reason"),
    [({"view": "summary", "description_from": 5}, "detail_only"),
     ({"view": "evidence", "description_from": 0}, "detail_only"),
     ({"view": "detail", "description_from": 10_000_000}, "past_end")],
)
async def test_a_description_point_outside_a_detail_or_its_text_is_an_input_error(
    api_client, workspace, params, reason,
):
    job_id = await _job_id(workspace, "INTERVIEW")

    response, body = await _get(api_client, f"/opportunities/{job_id}", **params)

    _error(response, body, "invalid_input", 2)
    assert body["error"]["details"]["field"] == "description_from"
    assert body["error"]["details"]["reason"] == reason


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
    assert data["description"] == await workspace.scalar(select(Job.description_text).where(Job.id == job_id))


# --------------------------------------------------------------------------- #
# opportunities.history
# --------------------------------------------------------------------------- #


async def test_history_is_the_dashboards_history_for_every_seeded_role(api_client, workspace):
    for job_id in await _visible_ids(workspace):
        route = await api_client.get(f"/api/jobs/{job_id}/history")
        assert route.status_code == 200, route.text
        expected = ListingHistory.model_validate(route.json()).model_dump(mode="json")
        _, body = await _get(api_client, f"/opportunities/{job_id}/history")
        assert _data(body) == expected, job_id
        assert expected["events"], "a posting has at least its first sighting"


# --------------------------------------------------------------------------- #
# pursuits.list and pursuits.get
# --------------------------------------------------------------------------- #

#: The fields of a pursuit the rows state, as an operation answers them.
_PURSUIT_FIELDS = ("stage", "priority", "notes", "next_action", "revision")


async def _stored_pursuits(session, stage: str | None = None) -> list[dict]:
    """The pursuits as the rows hold them, in the order the list promises:
    the most urgent first, the latest change first within one, then by row."""
    session.expire_all()
    stmt = select(Pursuit).order_by(Pursuit.priority.desc(), Pursuit.updated_at.desc(), Pursuit.id.asc())
    if stage:
        stmt = stmt.where(Pursuit.stage == stage)
    return [
        {"opportunity_id": row.job_id, **{field: getattr(row, field) for field in _PURSUIT_FIELDS}}
        for row in (await session.scalars(stmt)).all()
    ]


def _stated(item: dict) -> dict:
    return {key: item[key] for key in ("opportunity_id", *_PURSUIT_FIELDS)}


async def test_pursuits_list_answers_the_stored_pursuits_for_each_stage(api_client, workspace):
    everything = await _stored_pursuits(workspace)
    assert len(everything) == 4
    for stage in (None, "applied", "saved", "researching", "interviewing", "offer"):
        params = {"stage": stage} if stage else {}
        expected = await _stored_pursuits(workspace, stage)
        _, body = await _get(api_client, "/pursuits", **params)
        data = _data(body)
        assert data["count"] == len(expected), stage
        assert [_stated(item) for item in data["items"]] == expected, stage
        assert body["meta"]["next_cursor"] is None
        assert all(item["stage"] == stage for item in data["items"] if stage)
    # A stage filter narrows: some stage holds fewer than all of them.
    narrowed = [len(await _stored_pursuits(workspace, st)) for st in ("applied", "saved")]
    assert min(narrowed) < len(everything)


async def test_pursuit_notes_are_read_back(api_client, workspace):
    items = _data((await _get(api_client, "/pursuits"))[1])["items"]
    assert {item["notes"] for item in items} >= {"Onsite loop booked: four rounds, one of them system design."}


async def _many_pursuits(session) -> None:
    """Every seeded posting pursued, several at one priority, so the order's ties matter."""
    for job_id in await _visible_ids(session):
        await upsert_pursuit(session, job_id, PursuitUpdate(priority=3), actor="user")
    await session.commit()


async def test_cursor_pages_read_every_pursuit_once_in_the_stored_order(api_client, workspace):
    await _many_pursuits(workspace)
    expected = await _stored_pursuits(workspace)
    assert len(expected) > 8

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

    assert [_stated(item) for item in seen] == expected
    assert pages == -(-len(expected) // 3)


async def test_a_cursor_reads_the_list_as_it_stands_and_the_first_page_reads_it_whole(api_client, workspace):
    """A cursor resumes after the last row's place in the order, with no
    snapshot: a pursuit re-prioritised ahead of it during paging is not seen
    by the later pages, and a read from the first page sees it."""
    await _many_pursuits(workspace)
    _, first = await _get(api_client, "/pursuits", limit=3)
    cursor = first["meta"]["next_cursor"]
    rest_before = _data((await _get(api_client, "/pursuits", limit=100, cursor=cursor))[1])["items"]
    moved = rest_before[-1]["opportunity_id"]
    highest = max(item["priority"] for item in _data(first)["items"])
    await workspace.execute(update(Pursuit).where(Pursuit.job_id == moved).values(priority=highest + 1))
    await workspace.commit()

    rest_after = _data((await _get(api_client, "/pursuits", limit=100, cursor=cursor))[1])["items"]
    restarted = _data((await _get(api_client, "/pursuits", limit=100))[1])["items"]

    assert moved not in [item["opportunity_id"] for item in rest_after]
    assert restarted[0]["opportunity_id"] == moved
    assert len(restarted) == len(_data(first)["items"]) + len(rest_before)


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
    assert _data((await _get(api_client, "/pursuits", limit=100))[1])["count"] == 4
    for limit in (0, 101, 500):
        response, body = await _get(api_client, "/pursuits", limit=limit)
        _error(response, body, "invalid_input", 2)


async def test_pursuits_get_reads_one_pursuit_by_its_opportunity(api_client, workspace):
    for stored in await _stored_pursuits(workspace):
        _, body = await _get(api_client, f"/pursuits/{stored['opportunity_id']}")
        assert _stated(_data(body)) == stored
        assert body["meta"]["data_classes"] == ["private_pursuit", "public_posting"]


async def test_each_pursuit_carries_the_revision_a_dashboard_write_advances(api_client, workspace):
    job_id = await _job_id(workspace, "SAVED")
    before = _data((await _get(api_client, f"/pursuits/{job_id}"))[1])
    assert before["revision"] == await workspace.scalar(select(Pursuit.revision).where(Pursuit.job_id == job_id))
    assert before["revision"] >= 1

    await upsert_pursuit(workspace, job_id, PursuitUpdate(notes="Spoke to Sam."), actor="user")
    await workspace.commit()

    after = _data((await _get(api_client, f"/pursuits/{job_id}"))[1])
    assert after["notes"] == "Spoke to Sam."
    assert after["revision"] == before["revision"] + 1
    listed = {item["opportunity_id"]: item for item in _data((await _get(api_client, "/pursuits"))[1])["items"]}
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

    assert _data((await _get(api_client, f"/pursuits/{job_id}"))[1])["opportunity_id"] == job_id
    assert job_id in {item["opportunity_id"] for item in _data((await _get(api_client, "/pursuits"))[1])["items"]}


# --------------------------------------------------------------------------- #
# The recipe reads
# --------------------------------------------------------------------------- #


async def test_the_recipe_contract_is_the_recipe_modules_own(api_client, workspace):
    _, body = await _get(api_client, "/recipes/contract")

    data = _data(body)
    assert set(data) == {"schema", "transports", "transforms", "rules"}
    assert data["schema"] == json.loads(json.dumps(RECIPE_V1_SCHEMA))
    assert data["transports"] == list(TRANSPORT_MODES) and data["transports"]
    assert data["transforms"] == list(TRANSFORM_NAMES) and data["transforms"]
    assert data["schema"]["type"] == "object"
    assert any("CSS selectors only" in rule for rule in data["rules"])


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
    """One public page in place of the network."""
    fetched: list[str] = []

    async def fetch(_client, url, *, max_bytes):
        fetched.append(url)
        if "169.254" in url:
            raise BlockedDestination("non-public address")
        if "slow" in url:
            raise httpx.ReadTimeout("no answer")
        return _Page()

    monkeypatch.setattr(recipe_ops, "fetch_public", fetch)
    monkeypatch.setattr(recipe_ops, "public_client", lambda **_: _Client())
    return fetched


@pytest.mark.parametrize(("selector", "matches"), [(None, None), ("a.job", 20), ("h1", 1), ("table", 0)])
async def test_source_inspection_reads_the_page_as_the_selector_asks(
    api_client, workspace, fake_page, selector, matches
):
    url = "https://jobs.example.com/careers"
    params = {"url": url, **({"selector": selector} if selector else {})}

    _, body = await _get(api_client, "/sources/inspect", **params)

    data = _data(body)
    assert (data["url"], data["status"], data["truncated"]) == (url, 200, False)
    assert data["matches"] == matches
    assert "alert(1)" not in data["content"]
    if selector is None:
        # The page's text, cut at 12,000 characters and marked.
        assert data["content"].startswith("Careers") and "<a" not in data["content"]
        assert data["content_truncated"] is True and len(data["content"]) == 12_000
    elif selector == "a.job":
        # The first twenty of thirty elements, as sanitized HTML.
        assert 'href="/j/19"' in data["content"] and 'href="/j/20"' not in data["content"]
    elif selector == "h1":
        assert "Careers" in data["content"] and "Role" not in data["content"]
    else:
        assert data["content"] == ""
    assert fake_page == [url]


async def test_a_blocked_address_is_an_input_error_not_a_crash(api_client, workspace, fake_page):
    response, body = await _get(api_client, "/sources/inspect", url="http://169.254.169.254/")

    _error(response, body, "invalid_input", 2)
    assert body["error"]["details"] == {"field": "url", "reason": "blocked_destination"}


async def test_a_page_that_does_not_answer_is_a_deadline_not_a_crash(api_client, workspace, fake_page):
    response, body = await _get(api_client, "/sources/inspect", url="https://slow.example.com/careers")

    _error(response, body, "deadline_exceeded", 8)
    assert body["error"]["retryable"] is True
    # A page that answers on the same route is not mistaken for one that did not.
    assert _data((await _get(api_client, "/sources/inspect", url="https://jobs.example.com/careers"))[1])


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

    monkeypatch.setattr(recipe_ops, "preview_document", preview)
    return seen


@pytest.mark.parametrize("recipe_id", ["acme", "broken"])
async def test_recipe_validation_reports_what_the_preview_found(api_client, workspace, fake_preview, recipe_id):
    document = {"id": recipe_id, "version": 1, "nested": {"list": [1, "two", None]}}

    response = await api_client.post(f"{PREFIX}/recipes/validate", json={"document": document})

    assert response.status_code == 200
    data = _data(response.json())
    if recipe_id == "acme":
        assert data["compiles"] is True and data["problems"] == []
        assert (data["found"], data["pages"]) == (1, 1)
        assert data["jobs"] == [{"title": "Role 1", "url": "https://jobs.example.com/j/1"}]
        assert data["robots"]["allowed"] is True
    else:
        assert data["compiles"] is False and data["problems"] == ["match.domains is required"]
        assert (data["found"], data["jobs"]) == (0, [])
    # The document arrived whole.
    assert fake_preview == [document]


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


async def test_every_read_answers_when_on_and_refuses_an_unknown_key(api_client, workspace, fake_page, fake_preview):
    job_id = await _job_id(workspace, "INTERVIEW")

    for operation in READS:
        response = await _call(api_client, operation, job_id)
        assert response.status_code == 200, (operation, response.json())
        assert response.json()["operation"] == operation

        response = await _call(api_client, operation, job_id, extra={"verbose": "1"})
        _error(response, response.json(), "invalid_input", 2)

"""An assistant tidies duplicate postings: the queue it reads and the verdicts it records.

The workspace is one followed company with four pending pairs, one of each
kind the queue orders: a twin pair touching a role the person saved, a
suspected repost pair the Board still shows twice, and two automatic repost
pairs the detector stacked, one weaker than the other. Verdicts go through
the agent route; the person's own go through the Review queue's routes, and
every read-back opens a fresh session.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.factories import make_company
from tests.lineage_rows import duplicate_proposal, lineage_job, seed_rows, twin_proposal
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.duplicates import MAX_VERDICTS
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.search import COLUMNS
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, PREFIX
from tracker.db.models import AgentActivity, Favorite, Job, JobLineageLink, JobTwinLink

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

KEY = "idk_" + "d" * 32
OTHER_KEY = "idk_" + "e" * 32
OLDER_TEXT = "Lead the inference platform team.\n\nWork from our Mesa site."
NEWER_TEXT = "Lead the inference platform team.\n\nWork from our Avondale site, with travel."


def _job(key: str, days: int, text: str = "Lead the inference platform team."):
    job = lineage_job(key, days)
    job.description_text = text
    job.description_sections = []
    return job


@pytest_asyncio.fixture
async def pairs(db_session, scratch_scope) -> dict[str, Any]:
    """Four pending pairs at a followed company, the newer posting of the twin
    pair saved, and agent reads and writes on."""
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    db_session.add(make_company("google", "Google"))
    jobs = await seed_rows(
        db_session,
        _job("a1", 0, OLDER_TEXT), _job("a2", 20, NEWER_TEXT),
        _job("b1", 1), _job("b2", 21),
        _job("c1", 2), _job("c2", 3),
        _job("d1", 4), _job("d2", 24),
    )
    a1, a2, b1, b2, c1, c2, d1, d2 = jobs
    db_session.add(Favorite(job_id=c2.id))
    shown_twice, strong_stack, yours, weak_stack = await seed_rows(
        db_session,
        duplicate_proposal(a1, a2, relation="repost", score=0.97),
        duplicate_proposal(b1, b2, relation="repost", confidence="auto", score=0.99),
        twin_proposal(c1, c2, score=0.9),
        duplicate_proposal(d1, d2, relation="repost", confidence="auto", score=0.91),
    )
    return {
        "jobs": jobs,
        "shown_twice": shown_twice.id,
        "strong_stack": strong_stack.id,
        "yours": yours.id,
        "weak_stack": weak_stack.id,
    }


def _fresh(db_session) -> AsyncSession:
    return async_sessionmaker(db_session.bind, expire_on_commit=False)()


async def _queue(api_client, **params):
    response = await api_client.get(f"{PREFIX}/duplicates/queue", params=params)
    return response, response.json()


async def _decide(api_client, verdicts: list[dict[str, Any]], *, key: str = KEY):
    response = await api_client.post(
        f"{PREFIX}/duplicates/verdicts", json={"verdicts": verdicts}, headers={IDEMPOTENCY_KEY_HEADER: key},
    )
    return response, response.json()


def _data(response, body: dict) -> dict:
    assert response.status_code == 200 and body["ok"] is True, body
    return body["data"]


def _refused(response, body: dict, code: str) -> dict:
    assert body["ok"] is False, body
    assert body["error"]["code"] == code, body["error"]
    assert response.status_code == outcome(code).http_status
    return body["error"]


def _verdict(pair: str, verdict: str, reason: str = "Same site and pay; the first closed before the second.") -> dict:
    return {"pair": pair, "verdict": verdict, "reason": reason}


async def _lineage(db_session, link_id: int) -> JobLineageLink:
    async with _fresh(db_session) as session:
        link = await session.get(JobLineageLink, link_id)
        assert link is not None
        return link


async def _twin_of(db_session, left: int, right: int) -> JobTwinLink | None:
    a, b = sorted((left, right))
    async with _fresh(db_session) as session:
        return await session.scalar(select(JobTwinLink).where(JobTwinLink.job_a_id == a, JobTwinLink.job_b_id == b))


async def _person_verdict(api_client, kind: str, link_id: int, verdict: str) -> dict:
    path = f"/api/lineage/links/{link_id}/review" if kind == "lineage" else f"/api/twins/links/{link_id}/review"
    response = await api_client.post(path, json={"verdict": verdict})
    assert response.status_code == 200, response.text
    return response.json()


async def _changes(db_session) -> list[AgentActivity]:
    async with _fresh(db_session) as session:
        return list((await session.scalars(
            select(AgentActivity).where(AgentActivity.kind == "change").order_by(AgentActivity.id)
        )).all())


# --- the queue --------------------------------------------------------------- #


async def test_the_queue_puts_the_persons_roles_first_then_pairs_shown_twice_then_the_weakest_stack(
    api_client, pairs,
):
    page = _data(*await _queue(api_client, tier="full"))
    assert [pair["pair"] for pair in page["pairs"]] == [
        f"twin-{pairs['yours']}",
        f"lineage-{pairs['shown_twice']}",
        f"lineage-{pairs['weak_stack']}",
        f"lineage-{pairs['strong_stack']}",
    ]
    assert [pair["step"] for pair in page["pairs"]] == ["yours", "shown_twice", "stacked", "stacked"]
    assert [pair["proposed"] for pair in page["pairs"]] == ["two_openings", "same_opening", "same_opening",
                                                            "same_opening"]
    assert page["total"] == 4


async def test_each_pair_carries_both_postings_and_the_text_only_one_of_them_has(api_client, pairs):
    a1, a2 = pairs["jobs"][:2]
    page = _data(*await _queue(api_client, tier="full"))
    pair = next(item for item in page["pairs"] if item["pair"] == f"lineage-{pairs['shown_twice']}")
    assert (pair["older"], pair["newer"]) == (a1.id, a2.id)
    assert {a1.id, a2.id} <= {row[0] for row in page["rows"]}
    assert [passage["text"] for passage in pair["text"]["only_in_older"]] == ["Work from our Mesa site."]
    assert [passage["text"] for passage in pair["text"]["only_in_newer"]] == [
        "Work from our Avondale site, with travel."
    ]
    assert pair["text"]["comparable"] is True


async def test_mine_keeps_only_pairs_with_a_role_the_person_saved(api_client, pairs):
    page = _data(*await _queue(api_client, mine=True))
    assert [pair["pair"] for pair in page["pairs"]] == [f"twin-{pairs['yours']}"]


async def test_a_small_page_continues_where_it_stopped_and_reads_every_pair_once(api_client, pairs):
    seen: list[str] = []
    params: dict[str, Any] = {"limit": 1}
    for _ in range(4):
        response, body = await _queue(api_client, **params)
        page = _data(response, body)
        seen += [pair["pair"] for pair in page["pairs"]]
        params = {"limit": 1, "cursor": body["meta"]["next_cursor"]}
    assert body["meta"]["next_cursor"] is None
    assert len(seen) == len(set(seen)) == 4


async def test_deciding_a_page_before_reading_the_next_skips_no_pair(api_client, pairs):
    """The agent's own loop: read a page, decide it, follow the cursor. The
    decided pairs leave the queue, and the next page still starts after them."""
    response, body = await _queue(api_client, limit=2, tier="full")
    first = [pair["pair"] for pair in _data(response, body)["pairs"]]
    _data(*await _decide(api_client, [_verdict(pair, "different_roles", "Different teams.") for pair in first]))
    response, body = await _queue(api_client, limit=2, tier="full", cursor=body["meta"]["next_cursor"])
    assert [pair["pair"] for pair in _data(response, body)["pairs"]] == [
        f"lineage-{pairs['weak_stack']}", f"lineage-{pairs['strong_stack']}",
    ]


async def test_among_the_persons_roles_suspected_pairs_lead_and_automatic_ones_run_weakest_first(
    db_session, api_client, pairs,
):
    *_, b2, _, _, _, d2 = pairs["jobs"]
    db_session.add_all([Favorite(job_id=b2.id), Favorite(job_id=d2.id)])
    await db_session.commit()
    page = _data(*await _queue(api_client, mine=True, tier="full"))
    assert [pair["pair"] for pair in page["pairs"]] == [
        f"twin-{pairs['yours']}", f"lineage-{pairs['weak_stack']}", f"lineage-{pairs['strong_stack']}",
    ]


async def test_without_shared_pursuits_no_pair_is_the_persons_and_mine_is_refused(db_session, api_client, pairs):
    await set_agent_access(db_session, AgentAccessConfig(
        enabled=True, allow_writes=True, categories={"private_pursuit": "not_shared"},
    ))
    await db_session.commit()
    page = _data(*await _queue(api_client, tier="full"))
    assert "yours" not in {pair["step"] for pair in page["pairs"]}
    assert "pursuit" not in page["columns"]
    _refused(*await _queue(api_client, mine=True), "category_disabled")


async def test_queue_rows_leave_out_the_estimate_and_pursuit_columns_of_a_category_off(
    db_session, api_client, pairs,
):
    page = _data(*await _queue(api_client))
    assert page["columns"] == list(COLUMNS)
    await set_agent_access(db_session, AgentAccessConfig(
        enabled=True, allow_writes=True,
        categories={"market_statistic": "not_shared", "private_pursuit": "not_shared"},
    ))
    await db_session.commit()
    page = _data(*await _queue(api_client))
    assert "estimated_pay" not in page["columns"] and "pursuit" not in page["columns"]
    assert all(len(row) == len(page["columns"]) for row in page["rows"])


# --- verdicts ---------------------------------------------------------------- #


async def test_a_verdict_is_marked_as_the_assistants_with_its_reason_in_the_review_queue(
    db_session, api_client, pairs,
):
    link_id = pairs["shown_twice"]
    data = _data(*await _decide(api_client, [_verdict(f"lineage-{link_id}", "same_opening")]))
    assert data["decided"] == 1 and data["results"][0]["after"] == "confirmed"
    link = await _lineage(db_session, link_id)
    assert (link.status, link.decided_by) == ("confirmed", "agent")
    assert link.decision_note == "Same site and pay; the first closed before the second."
    response = await api_client.get(
        "/api/lineage/review", params={"status": "reviewed", "confidence": "", "decided_by": "agent"},
    )
    (item,) = response.json()["items"]
    assert item["link"]["id"] == link_id
    assert item["link"]["decided_by"] == "agent"
    assert item["link"]["decision_note"] == link.decision_note
    mine = await api_client.get(
        "/api/lineage/review", params={"status": "reviewed", "confidence": "", "decided_by": "person"},
    )
    assert mine.json()["items"] == []


async def test_a_decided_pair_leaves_the_queue_and_two_openings_makes_the_twin(db_session, api_client, pairs):
    b1, b2 = pairs["jobs"][2:4]
    link_id = pairs["strong_stack"]
    _data(*await _decide(api_client, [_verdict(f"lineage-{link_id}", "two_openings", "Both open at once.")]))
    link = await _lineage(db_session, link_id)
    assert (link.status, link.decided_by) == ("rejected", "agent")
    twin = await _twin_of(db_session, b1.id, b2.id)
    assert twin is not None and (twin.status, twin.decided_by) == ("confirmed", "agent")
    page = _data(*await _queue(api_client, tier="full"))
    assert f"lineage-{link_id}" not in {pair["pair"] for pair in page["pairs"]}


async def test_the_person_takes_an_assistants_verdict_back_and_its_twin_goes_with_it(
    db_session, api_client, pairs,
):
    b1, b2 = pairs["jobs"][2:4]
    link_id = pairs["strong_stack"]
    _data(*await _decide(api_client, [_verdict(f"lineage-{link_id}", "two_openings", "Both open at once.")]))
    await _person_verdict(api_client, "lineage", link_id, "pending")
    link = await _lineage(db_session, link_id)
    assert (link.status, link.decided_by, link.decision_note) == ("pending", None, None)
    assert await _twin_of(db_session, b1.id, b2.id) is None
    assert link.evidence["decision_history"][-1]["decided_by"] == "agent"


async def test_unsure_leaves_the_pair_pending_with_the_note_and_out_of_the_queue(db_session, api_client, pairs):
    link_id = pairs["weak_stack"]
    data = _data(*await _decide(api_client, [_verdict(f"lineage-{link_id}", "unsure", "The team names differ.")]))
    assert (data["decided"], data["left_for_person"]) == (0, 1)
    link = await _lineage(db_session, link_id)
    assert (link.status, link.decided_by, link.decision_note) == ("pending", None, "The team names differ.")
    page = _data(*await _queue(api_client, tier="full"))
    assert f"lineage-{link_id}" not in {pair["pair"] for pair in page["pairs"]}
    response = await api_client.get("/api/lineage/review", params={"confidence": "auto"})
    noted = [item for item in response.json()["items"] if item["link"]["id"] == link_id]
    assert noted and noted[0]["link"]["decision_note"] == "The team names differ."


async def test_unsure_on_a_pair_it_had_decided_takes_the_stack_apart(db_session, api_client, pairs):
    a1, a2 = pairs["jobs"][:2]
    pair = f"lineage-{pairs['shown_twice']}"

    async def lineages() -> tuple[int | None, int | None]:
        async with _fresh(db_session) as session:
            older, newer = (await session.get(Job, a1.id)), (await session.get(Job, a2.id))
            assert older is not None and newer is not None
            return older.lineage_id, newer.lineage_id

    _data(*await _decide(api_client, [_verdict(pair, "same_opening")]))
    stacked = await lineages()
    assert stacked[0] is not None and stacked[0] == stacked[1]
    _data(*await _decide(api_client, [_verdict(pair, "unsure", "Second look: the sites differ.")], key=OTHER_KEY))
    older, newer = await lineages()
    assert older is None or older != newer


async def test_the_person_filter_lists_no_pending_pair(api_client, pairs):
    response = await api_client.get("/api/lineage/review", params={"confidence": "", "decided_by": "person"})
    assert response.status_code == 200 and response.json()["items"] == []
    response = await api_client.get("/api/twins/review", params={"decided_by": "person"})
    assert response.status_code == 200 and response.json()["items"] == []


async def test_a_pair_the_person_decided_is_refused_and_the_rest_of_the_batch_goes_ahead(
    db_session, api_client, pairs,
):
    decided, other = pairs["shown_twice"], pairs["weak_stack"]
    await _person_verdict(api_client, "lineage", decided, "rejected")
    data = _data(*await _decide(api_client, [
        _verdict(f"lineage-{decided}", "same_opening"),
        _verdict(f"lineage-{other}", "same_opening"),
    ]))
    assert [(item["outcome"], item["refusal"]) for item in data["results"]] == [
        ("refused", "decided_by_person"), ("decided", None),
    ]
    link = await _lineage(db_session, decided)
    assert (link.status, link.decided_by) == ("rejected", "person")
    assert (await _lineage(db_session, other)).status == "confirmed"


async def test_a_verdict_that_would_undo_the_persons_twin_on_the_same_pair_is_refused(
    db_session, api_client, pairs,
):
    a1, a2 = pairs["jobs"][:2]
    (twin,) = await seed_rows(db_session, twin_proposal(a1, a2, status="confirmed"))
    data = _data(*await _decide(api_client, [_verdict(f"lineage-{pairs['shown_twice']}", "same_opening")]))
    assert data["results"][0]["refusal"] == "decided_by_person"
    after = await _twin_of(db_session, a1.id, a2.id)
    assert after is not None and after.status == "confirmed"
    assert (await _lineage(db_session, pairs["shown_twice"])).status == "pending"


async def test_an_assistant_may_change_its_own_verdict(db_session, api_client, pairs):
    link_id = pairs["shown_twice"]
    _data(*await _decide(api_client, [_verdict(f"lineage-{link_id}", "same_opening")]))
    _data(*await _decide(api_client, [_verdict(f"lineage-{link_id}", "different_roles", "Other team.")],
                         key=OTHER_KEY))
    link = await _lineage(db_session, link_id)
    assert (link.status, link.decided_by, link.decision_note) == ("rejected", "agent", "Other team.")


async def test_the_persons_verdict_is_recorded_as_theirs_and_a_legacy_one_reads_as_theirs(
    db_session, api_client, pairs,
):
    await _person_verdict(api_client, "twin", pairs["yours"], "confirmed")
    async with _fresh(db_session) as session:
        twin = await session.get(JobTwinLink, pairs["yours"])
        assert twin is not None and twin.decided_by == "person"
    a1, a2 = pairs["jobs"][:2]
    async with _fresh(db_session) as session:
        link = await session.get(JobLineageLink, pairs["shown_twice"])
        assert link is not None
        link.status, link.decided_by = "confirmed", None
        await session.commit()
    response = await api_client.get("/api/lineage/review", params={"status": "reviewed", "confidence": ""})
    legacy = next(item for item in response.json()["items"] if item["link"]["id"] == pairs["shown_twice"])
    assert legacy["link"]["decided_by"] == "person"
    assert {a1.id, a2.id} == {legacy["job"]["id"], legacy["prior"]["id"]}


async def test_a_verdict_lists_one_change_on_activity_and_a_replay_lists_nothing(db_session, api_client, pairs):
    verdicts = [
        _verdict(f"lineage-{pairs['shown_twice']}", "same_opening"),
        _verdict(f"lineage-{pairs['weak_stack']}", "unsure", "Thin evidence."),
    ]
    first = _data(*await _decide(api_client, verdicts))
    response, body = await _decide(api_client, verdicts)
    assert _data(response, body) == first and body["meta"]["replayed"] is True
    (change,) = await _changes(db_session)
    assert change.operation == "duplicates.decide"
    assert change.action_group == "tuning_radar"
    assert change.subject == {"topic": "duplicates.decided", "decided": 1, "left": 1}
    assert change.summary == "Decided 1 duplicate pair, left 1 for you"
    assert {item["field"]: item["after"] for item in change.changes} == {
        f"lineage-{pairs['shown_twice']}": "confirmed", f"lineage-{pairs['weak_stack']}": "left_for_you",
    }


async def test_an_unknown_pair_is_refused_on_its_own(api_client, pairs):
    data = _data(*await _decide(api_client, [
        _verdict("lineage-999999", "same_opening"), _verdict(f"twin-{pairs['yours']}", "two_openings"),
    ]))
    assert [(item["outcome"], item["refusal"]) for item in data["results"]] == [
        ("refused", "not_found"), ("decided", None),
    ]


async def test_verdicts_are_refused_while_the_person_keeps_radar_changes_off(db_session, api_client, pairs):
    await set_agent_access(db_session, AgentAccessConfig(
        enabled=True, allow_writes=True, groups={"tuning_radar": "off"},
    ))
    await db_session.commit()
    error = _refused(*await _decide(api_client, [_verdict(f"lineage-{pairs['shown_twice']}", "same_opening")]),
                     "writes_disabled")
    assert "tuning_radar" in str(error)
    assert (await _lineage(db_session, pairs["shown_twice"])).status == "pending"


@pytest.mark.parametrize("verdicts", [
    [{"pair": "lineage-x", "verdict": "same_opening", "reason": "Same site."}],
    [{"pair": "lineage-1", "verdict": "merge", "reason": "Same site."}],
    [{"pair": "lineage-1", "verdict": "same_opening", "reason": "  "}],
    [{"pair": "lineage-1", "verdict": "same_opening", "reason": "Same."},
     {"pair": "lineage-1", "verdict": "unsure", "reason": "Not sure."}],
    [{"pair": f"lineage-{n}", "verdict": "same_opening", "reason": "Same."} for n in range(1, MAX_VERDICTS + 2)],
    [],
])
async def test_a_malformed_batch_is_refused_whole(db_session, api_client, pairs, verdicts):
    _refused(*await _decide(api_client, verdicts), "invalid_input")
    assert await _changes(db_session) == []

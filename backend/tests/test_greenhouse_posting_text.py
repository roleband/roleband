"""A Greenhouse posting stored with no text is read alone, from its board.

The listing inlines every posting's text, so a scan never asks for one posting.
A posting rebuilt from storage (one admitted from the posting inventory, which
keeps no text) is read from the single-posting route, when a person opens it
and by the description backfill.

Only the network is mocked (an httpx MockTransport inside the real Greenhouse
adapter, caught where the adapter builds its client). The answer is a posting
as the single-posting route serves it, reduced to what the read uses: a
numeric `id` and escaped HTML `content` with its pay-transparency block.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tests.factories import make_job
from tracker.config import get_settings
from tracker.connectors import build_adapter as real_build_adapter
from tracker.db.models import Job, TrackedCompany
from tracker.schema import RawJob

FIXTURES = Path(__file__).parent / "fixtures"
POSTING = json.loads((FIXTURES / "greenhouse_posting" / "anthropic_text.json").read_text(encoding="utf-8"))
POSTING_ID = str(POSTING["id"])
#: A sentence of the posting's own body, which only a read of it can store.
LEAD = "You will own revenue recognition, month-end close and reporting"
LISTED = json.loads((FIXTURES / "listings" / "greenhouse" / "page1.json").read_text(encoding="utf-8"))["jobs"][0]


@pytest.fixture
def board(monkeypatch, no_escape):
    """The Greenhouse board API, answering with `board.status` and `board.body`
    and counting requests."""
    state = type("Board", (), {"status": 200, "body": POSTING, "requests": []})()

    async def handler(request):
        state.requests.append(request)
        if state.status == 200:
            return httpx.Response(200, json=state.body)
        return httpx.Response(state.status, json={"status": state.status, "error": "Job not found"})

    # Opening an adapter (`async with`) builds its client here, so this is the
    # one place a request can be caught before it leaves.
    monkeypatch.setattr(
        "tracker.connectors.listing.base.make_tier_client",
        lambda *a, **k: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    # No pacing wait between the test's requests. The pacer itself is real.
    monkeypatch.setattr(get_settings(), "scraper_min_delay_seconds", 0)
    # Each test starts with the state a fresh API process has.
    from tracker.api.app import app

    monkeypatch.delattr(app.state, "text_reads", raising=False)
    return state


def _stored(req_id: str = POSTING_ID, company: str = "anthropic") -> RawJob:
    """The posting as `posting_text.stored_posting` rebuilds it: no text."""
    return RawJob(company=company, req_id=req_id, title=POSTING["title"], url="", description_complete=False)


async def _seed(db_session) -> int:
    db_session.add(TrackedCompany(slug="anthropic", display="Anthropic", adapter="greenhouse",
                                  board_token="anthropic", status="active", enabled=True))
    job = make_job(POSTING_ID, company="anthropic", title=POSTING["title"])
    db_session.add(job)
    await db_session.commit()
    return job.id


@pytest.mark.asyncio
async def test_a_scan_never_asks_for_one_posting(board):
    """A listing row is the whole posting: hydrating it sends nothing."""
    listed = RawJob(company="anthropic", req_id=str(LISTED["id"]), title=LISTED["title"],
                    url=LISTED["absolute_url"], description_html=LISTED["content"], detail_payload=LISTED)
    async with real_build_adapter("anthropic", "greenhouse", "anthropic") as adapter:
        await adapter.hydrate(listed)

    assert board.requests == []
    assert listed.description_html == LISTED["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("company", "token"), [("anthropic", "anthropic"), ("acme", "acme-careers")])
async def test_a_stored_posting_is_read_from_its_own_board_alone(board, company, token):
    """The board token, not the company slug, names the board, and the text read
    asks for no form and no pay: those are the posting page's to ask."""
    stored = _stored(company=company)
    async with real_build_adapter(company, "greenhouse", token) as adapter:
        await adapter.hydrate(stored)

    (request,) = board.requests
    assert request.url.host == "boards-api.greenhouse.io"
    assert request.url.path == f"/v1/boards/{token}/jobs/{POSTING_ID}"
    assert dict(request.url.params) == {}
    assert stored.description_complete is True
    assert stored.description_html == POSTING["content"]
    assert stored.detail_payload == POSTING


@pytest.mark.asyncio
async def test_an_answer_for_another_posting_is_not_stored(board):
    board.body = {**POSTING, "id": POSTING["id"] + 1}
    stored = _stored()
    async with real_build_adapter("anthropic", "greenhouse", "anthropic") as adapter:
        await adapter.hydrate(stored)
        notes = [alert["message"] for alert in adapter.drift.alerts]

    assert stored.description_html is None and stored.description_complete is False
    assert stored.detail_payload is None
    assert notes == ["posting payload is not the posting asked for"]


@pytest.mark.asyncio
async def test_a_posting_gone_from_the_board_stores_nothing(board):
    board.status = 404
    stored = _stored()
    async with real_build_adapter("anthropic", "greenhouse", "anthropic") as adapter:
        await adapter.hydrate(stored)
        alerts = adapter.drift.alerts

    assert len(board.requests) == 1  # a 404 is an answer, never retried
    assert stored.description_html is None and stored.description_complete is False
    assert [(a["message"], a["status"]) for a in alerts] == [("non-200 posting", 404)]


@pytest.mark.asyncio
async def test_opening_a_stored_greenhouse_posting_reads_its_text(api_client, db_session, board):
    job_id = await _seed(db_session)

    detail = (await api_client.get(f"/api/jobs/{job_id}")).json()
    assert detail["description_readable"] is True
    assert board.requests == []  # the detail read never waits on the source

    response = await api_client.post(f"/api/jobs/{job_id}/description")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "read"
    assert LEAD in body["description_text"]
    # Structured as a scan structures a Greenhouse posting: its own headings,
    # and the pay-transparency block as a section of its own.
    titles = [section["title"] for section in body["description_sections"]]
    assert "About the role" in titles and "Key responsibilities" in titles
    assert "Compensation" in titles
    (request,) = board.requests
    assert request.url.path == f"/v1/boards/anthropic/jobs/{POSTING_ID}"

    row = await db_session.get(Job, job_id, populate_existing=True)
    assert LEAD in row.description_text
    assert row.description_fetched_at is not None


@pytest.mark.asyncio
async def test_the_description_backfill_reaches_greenhouse_too(db_session, board):
    from tracker.workflows.post_passes import backfill_missing_descriptions

    job_id = await _seed(db_session)

    assert await backfill_missing_descriptions(db_session, limit=5) == [job_id]
    row = await db_session.get(Job, job_id, populate_existing=True)
    assert LEAD in row.description_text


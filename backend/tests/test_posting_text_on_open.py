"""Opening a posting with no text reads its text once, after the page is shown.

Only the network is mocked (an httpx MockTransport inside the real Lever
adapter, caught where the adapter builds its client). The company register,
the source policy, the route, the read, the storage and the detail flag are the
real code over the scratch database. The posting the source answers is one of
the Lever contract fixture's, so the text is a real posting's shape.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.factories import make_job
from tracker.config import get_settings
from tracker.connectors import build_adapter as real_build_adapter
from tracker.content import content_fingerprint
from tracker.db.models import Job, TrackedCompany
from tracker.source_review import source_wall
from tracker.workflows import posting_text

LEVER_PAGE = json.loads(
    (Path(__file__).parent / "fixtures" / "listings" / "lever" / "page1.json").read_text(encoding="utf-8")
)
POSTING = LEVER_PAGE[0]
POSTING_ID = POSTING["id"]
#: A sentence of the posting's own body, which only a read of it can store.
LEAD = "Spotify is seeking a highly analytical and motivated Analyst"


@pytest.fixture
def lever(monkeypatch):
    """The Lever API, answering with `lever.status` and counting requests.

    `lever.during` runs inside the request, while the source "answers": the
    moment a concurrent scan could commit, or a held transaction would show.
    """
    state = type("Lever", (), {"status": 200, "body": POSTING, "requests": [], "during": None, "built": []})()

    async def handler(request):
        state.requests.append(request)
        if state.during is not None:
            await state.during()
        if state.status == 200:
            return httpx.Response(200, json=state.body)
        return httpx.Response(state.status, json={"ok": False, "error": "Document not found"})

    def build(*args, **kwargs):
        state.built.append(kwargs)
        return real_build_adapter(*args, **kwargs)

    # Opening an adapter (`async with`) builds its client here, so this is the
    # one place a request can be caught before it leaves.
    monkeypatch.setattr(
        "tracker.connectors.listing.base.make_tier_client",
        lambda *a, **k: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(posting_text, "build_adapter", build)
    # No pacing wait between the test's requests. The pacer itself is real.
    monkeypatch.setattr(get_settings(), "scraper_min_delay_seconds", 0)
    # Each test starts with the state a fresh API process has.
    from tracker.api.app import app

    monkeypatch.delattr(app.state, "text_reads", raising=False)
    return state


async def _company(db_session, slug: str = "spotify", **over) -> None:
    row = {"slug": slug, "display": slug.title(), "adapter": "lever", "board_token": "spotify",
           "status": "active", "enabled": True}
    row.update(over)
    db_session.add(TrackedCompany(**row))
    await db_session.commit()


async def _seed(db_session, key: str = POSTING_ID, *, company: bool = True, slug: str = "spotify", **over) -> int:
    """A posting stored with no text, as the posting inventory admits one."""
    if company:
        await _company(db_session, slug)
    over.setdefault("title", POSTING["text"])
    job = make_job(key, company=slug, **over)
    db_session.add(job)
    await db_session.commit()
    return job.id


async def _readable(api_client, job_id: int) -> bool:
    return (await api_client.get(f"/api/jobs/{job_id}")).json()["description_readable"]


async def _open(api_client, job_id: int, *, retry: bool = False) -> dict:
    suffix = "?retry=true" if retry else ""
    response = await api_client.post(f"/api/jobs/{job_id}/description{suffix}")
    assert response.status_code == 200, response.text
    return response.json()


NOTHING = {"description_text": None, "description_sections": []}


@pytest.mark.asyncio
async def test_opening_a_posting_with_no_text_reads_it_once(api_client, db_session, lever):
    job_id = await _seed(db_session)

    detail = (await api_client.get(f"/api/jobs/{job_id}")).json()
    assert detail["description_text"] is None
    assert detail["description_readable"] is True
    assert lever.requests == []  # the detail read never waits on the source

    first = await _open(api_client, job_id)
    assert first["outcome"] == "read"
    assert LEAD in first["description_text"]
    # Structured as a scan structures the same posting: its own lists.
    titles = [section["title"] for section in first["description_sections"]]
    assert "What You'll Do" in titles and "Who You Are" in titles
    (request,) = lever.requests
    assert request.url.host == "api.lever.co"
    assert request.url.path == f"/v0/postings/spotify/{POSTING_ID}"
    assert request.url.params["mode"] == "json"

    again = await _open(api_client, job_id)
    assert again == {**first, "outcome": "already_read"}
    assert len(lever.requests) == 1  # a repeat answers from storage

    detail = (await api_client.get(f"/api/jobs/{job_id}")).json()
    assert detail["description_text"] == first["description_text"]
    assert detail["description_sections"] == first["description_sections"]
    assert detail["description_readable"] is False


@pytest.mark.asyncio
async def test_a_text_read_on_open_is_indexed_and_fingerprinted_at_once(api_client, db_session, lever):
    """The post-passes reach a row a run touches; this one no run touched.
    What a search and the content-gated passes read is written with the text."""
    job_id = await _seed(db_session)

    assert (await _open(api_client, job_id))["outcome"] == "read"

    row = await db_session.get(Job, job_id, populate_existing=True)
    assert row.description_fetched_at is not None
    assert row.content_hash == content_fingerprint(row.title, row.description_text)
    assert row.content_changed_at is not None
    # A word only the posting's body states, never its title.
    indexed = await db_session.scalar(
        text("SELECT search_vector @@ plainto_tsquery('english', 'royalties') FROM jobs WHERE id = :id"),
        {"id": job_id},
    )
    assert indexed is True


@pytest.mark.asyncio
async def test_a_failed_read_stores_nothing_and_is_not_repeated_until_asked(
    api_client, db_session, lever, monkeypatch
):
    lever.status = 503
    job_id = await _seed(db_session)

    assert await _open(api_client, job_id) == {"outcome": "failed", **NOTHING}
    # One retry for a read someone is waiting on, not the run's four.
    assert len(lever.requests) == 2
    assert (await db_session.get(Job, job_id, populate_existing=True)).description_text is None

    # Another open in the cool-down answers from memory: nothing is sent.
    assert await _open(api_client, job_id) == {"outcome": "failed", **NOTHING}
    assert len(lever.requests) == 2

    # Asked again on purpose, it reads at once.
    lever.status = 200
    assert (await _open(api_client, job_id, retry=True))["outcome"] == "read"
    assert len(lever.requests) == 3


@pytest.mark.asyncio
async def test_the_cool_down_ends(api_client, db_session, lever, monkeypatch):
    lever.status = 404  # gone on the board, still open in our records
    job_id = await _seed(db_session)

    assert (await _open(api_client, job_id))["outcome"] == "failed"
    assert len(lever.requests) == 1  # a 404 is an answer, never retried

    later = time.monotonic() + posting_text.ON_OPEN_COOL_DOWN_SECONDS + 1
    monkeypatch.setattr(posting_text, "_cool_down_clock", lambda: later)
    assert (await _open(api_client, job_id))["outcome"] == "failed"
    assert len(lever.requests) == 2


def test_a_long_lived_process_keeps_only_cool_downs_that_have_not_ended(monkeypatch):
    reads = posting_text.OpenTextReads()
    now = [1_000.0]
    monkeypatch.setattr(posting_text, "_cool_down_clock", lambda: now[0])

    reads._remember_none(1)
    now[0] += posting_text.ON_OPEN_COOL_DOWN_SECONDS + 1
    reads._remember_none(2)

    assert set(reads._found_none) == {2}


@pytest.mark.asyncio
async def test_a_source_that_does_not_answer_is_a_failure_within_the_deadline(
    api_client, db_session, lever, monkeypatch
):
    monkeypatch.setattr(posting_text, "ON_OPEN_DEADLINE_SECONDS", 0.3)
    job_id = await _seed(db_session)

    async def never():
        await asyncio.sleep(30)

    lever.during = never
    started = time.monotonic()
    assert await _open(api_client, job_id) == {"outcome": "failed", **NOTHING}
    assert time.monotonic() - started < 5


@pytest.mark.asyncio
async def test_two_opens_at_once_send_one_request(api_client, db_session, lever):
    job_id = await _seed(db_session)

    async def slow_source():
        await asyncio.sleep(0.2)

    lever.during = slow_source
    first, second = await asyncio.gather(_open(api_client, job_id), _open(api_client, job_id))

    assert len(lever.requests) == 1
    assert {first["outcome"], second["outcome"]} == {"read", "already_read"}
    assert first["description_text"] == second["description_text"]


@pytest.mark.asyncio
async def test_the_wait_behind_another_reader_counts_against_the_deadline(
    api_client, db_session, lever, monkeypatch
):
    """Try again sent while the first read still holds the posting answers
    once its own deadline passes, while that read still runs, and asks the
    source nothing: the page never waits on another open's read."""
    job_id = await _seed(db_session)
    lever.status = 404  # one request, not retried, then no text
    in_flight, let_go = asyncio.Event(), asyncio.Event()

    async def held_source():
        in_flight.set()
        await let_go.wait()

    lever.during = held_source
    first = asyncio.create_task(_open(api_client, job_id))
    await in_flight.wait()
    # The retry's deadline has passed by the time it waits for the posting.
    monkeypatch.setattr(posting_text, "ON_OPEN_DEADLINE_SECONDS", 0)
    # Only bounds a regression that waits for the first read: it would hang.
    again = await asyncio.wait_for(_open(api_client, job_id, retry=True), timeout=10)

    assert again == {"outcome": "failed", **NOTHING}
    assert not first.done()
    assert len(lever.requests) == 1
    let_go.set()
    assert await first == {"outcome": "failed", **NOTHING}
    assert len(lever.requests) == 1


@pytest.mark.asyncio
async def test_two_first_opens_build_one_reader(api_client, lever, monkeypatch):
    """The process holds one `OpenTextReads` however its first opens
    interleave: two would each let a read of the same posting through."""
    built = []
    real_init = posting_text.OpenTextReads.__init__

    def slow_init(self):
        built.append(self)
        time.sleep(0.2)  # the window between finding none and storing one
        real_init(self)

    monkeypatch.setattr(posting_text.OpenTextReads, "__init__", slow_init)
    answers = await asyncio.gather(
        api_client.post("/api/jobs/999998/description"), api_client.post("/api/jobs/999999/description")
    )

    assert [answer.status_code for answer in answers] == [404, 404]
    assert len(built) == 1


@pytest.mark.asyncio
async def test_text_another_writer_stored_meanwhile_stays(api_client, db_session, lever):
    """A scan that writes the posting's text while the open waits keeps it:
    the open only fills a gap."""
    job_id = await _seed(db_session)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    idle: list[int] = []

    async def a_scan_commits():
        async with factory() as other:
            idle.append(await other.scalar(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND state = 'idle in transaction'"
            )))
            await other.execute(update(Job).where(Job.id == job_id).values(description_text="The scan's text."))
            await other.commit()

    lever.during = a_scan_commits
    result = await _open(api_client, job_id)

    assert idle == [0]  # no connection waits in a transaction on the source
    assert result["outcome"] == "already_read"
    assert result["description_text"] == "The scan's text."
    assert (await db_session.get(Job, job_id, populate_existing=True)).description_text == "The scan's text."


@pytest.mark.asyncio
async def test_a_failed_read_answers_with_text_a_scan_stored_meanwhile(api_client, db_session, lever):
    """The source failed this open, but a scan gave the posting its text
    while it waited: the person is shown that text, not a failure."""
    lever.status = 503
    job_id = await _seed(db_session)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def a_scan_commits():
        async with factory() as other:
            await other.execute(update(Job).where(Job.id == job_id).values(description_text="The scan's text."))
            await other.commit()

    lever.during = a_scan_commits
    result = await _open(api_client, job_id)

    assert (result["outcome"], result["description_text"]) == ("already_read", "The scan's text.")


@pytest.mark.asyncio
async def test_the_fill_holds_the_row_until_it_commits(db_session, lever):
    """A scan that writes the text after the fill checked the row waits for the
    fill's commit, then writes over it; it never lands in between to be lost."""
    from sqlalchemy.exc import DBAPIError

    from tracker.db.repo import fill_blank_description

    job_id = await _seed(db_session)
    row = await db_session.get(Job, job_id)
    assert await fill_blank_description(db_session, job_id, posting_text.stored_posting(row), "Read on open.")

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as scan:
        await scan.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock"):
            await scan.execute(update(Job).where(Job.id == job_id).values(description_text="The scan's text."))
        await scan.rollback()
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("company", [
    {"enabled": False},  # followed once, switched off: no scan reads it either
    {"status": "pending"},
    {"adapter": "ashby"},  # a source whose listing carries the text: nothing reads one posting
])
async def test_a_company_we_do_not_collect_is_never_asked(api_client, db_session, lever, company):
    await _company(db_session, **company)
    job_id = await _seed(db_session, company=False)

    assert await _readable(api_client, job_id) is False
    assert await _open(api_client, job_id) == {"outcome": "not_available", **NOTHING}
    assert lever.requests == []


@pytest.mark.asyncio
async def test_a_posting_another_source_listed_is_never_asked(api_client, db_session, lever):
    """Its id means nothing to the company's own source."""
    job_id = await _seed(db_session, source_facts={"provider": "greenhouse", "posting_id": "6150563004"})

    assert await _readable(api_client, job_id) is False
    assert (await _open(api_client, job_id))["outcome"] == "not_available"
    assert lever.requests == []


@pytest.mark.asyncio
async def test_a_walled_company_is_read_only_with_the_users_consent(api_client, db_session, lever):
    # google is walled by its own robots file (the register's `google` row); a
    # company's declared provider keeps its wall whatever connector reads it.
    job_id = await _seed(db_session, slug="google")

    assert await _readable(api_client, job_id) is False
    assert (await _open(api_client, job_id))["outcome"] == "not_available"
    assert lever.requests == []

    fingerprint = source_wall("lever", company="google").wall_fingerprint
    await db_session.execute(
        update(TrackedCompany).where(TrackedCompany.slug == "google").values(consent_fingerprint=fingerprint)
    )
    await db_session.commit()

    assert await _readable(api_client, job_id) is True
    assert (await _open(api_client, job_id))["outcome"] == "read"


@pytest.mark.asyncio
async def test_a_closed_posting_is_not_read(api_client, db_session, lever):
    job_id = await _seed(db_session, status="closed")

    assert await _readable(api_client, job_id) is False
    assert (await _open(api_client, job_id))["outcome"] == "not_available"
    assert lever.requests == []


@pytest.mark.asyncio
async def test_a_posting_with_text_is_never_asked(api_client, db_session, lever):
    job_id = await _seed(db_session, description_text="Already here.")

    assert await _readable(api_client, job_id) is False
    result = await _open(api_client, job_id)
    assert (result["outcome"], result["description_text"]) == ("already_read", "Already here.")
    assert lever.requests == []


@pytest.mark.asyncio
async def test_an_unknown_posting_is_a_404(api_client, lever):
    assert (await api_client.post("/api/jobs/999999/description")).status_code == 404


@pytest.mark.asyncio
async def test_a_scan_never_asks_for_one_posting(lever):
    """A listing row is the whole posting: hydrating it sends nothing, so the
    single-posting route costs a scan no request."""
    from tracker.schema import RawJob

    listed = RawJob(company="spotify", req_id=POSTING_ID, title=POSTING["text"], url=POSTING["hostedUrl"],
                    description_html=POSTING["description"], detail_payload=POSTING)
    async with real_build_adapter("spotify", "lever", "spotify") as adapter:
        await adapter.hydrate(listed)

    assert lever.requests == []
    assert listed.description_html == POSTING["description"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("region", "host"), [(None, "api.lever.co"), ("eu", "api.eu.lever.co")])
async def test_one_posting_is_read_from_its_tenants_own_host(lever, region, host):
    from tracker.schema import RawJob

    stored = RawJob(company="spotify", req_id=POSTING_ID, title=POSTING["text"], url="",
                    description_complete=False)
    async with real_build_adapter("spotify", "lever", "spotify", board_region=region) as adapter:
        await adapter.hydrate(stored)

    (request,) = lever.requests
    assert request.url.host == host
    assert stored.description_complete is True
    assert stored.detail_payload == POSTING


@pytest.mark.asyncio
async def test_an_answer_for_another_posting_is_not_stored(lever):
    from tracker.schema import RawJob

    lever.body = LEVER_PAGE[1]
    stored = RawJob(company="spotify", req_id=POSTING_ID, title=POSTING["text"], url="",
                    description_complete=False)
    async with real_build_adapter("spotify", "lever", "spotify") as adapter:
        await adapter.hydrate(stored)
        notes = [alert["message"] for alert in adapter.drift.alerts]

    assert stored.description_html is None and stored.description_complete is False
    assert notes == ["posting payload is not the posting asked for"]


@pytest.mark.asyncio
async def test_the_description_backfill_reaches_lever_too(db_session, lever):
    """The background drain fills the same blanks between opens: Lever reads a
    posting alone now, so its blanks join the queue."""
    from tracker.workflows.post_passes import backfill_missing_descriptions

    job_id = await _seed(db_session)

    assert await backfill_missing_descriptions(db_session, limit=5) == [job_id]
    row = await db_session.get(Job, job_id, populate_existing=True)
    assert LEAD in row.description_text

"""Opened and came down count the same roles, each once, on one clock
(`db.queries.motion`): Overview, Pace and Hiring are asked, never the module
alone.

Closures go through the writers (`repo.record_absence`, `repo.close_missing`),
so the first miss each event records is the one the pipeline writes. Place
sets and lineages are rebuilt by their own passes after the closures, so a
closed posting is in no stored set, as in a real run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from tests.factories import make_company, make_job, record_whole_read
from tests.lineage_rows import lineage_link
from tests.place_set_rows import place_set_job
from tracker.config import get_settings
from tracker.db import repo
from tracker.db.models import Job, JobLifecycleEvent, JobPlaceSetMember, ScrapeRun
from tracker.lineage import place_sets
from tracker.lineage.detect import rebuild_lineage_projection
from tracker.lineage.place_sets import rebuild_place_sets

pytestmark = pytest.mark.asyncio

NOW = datetime.now(UTC).replace(microsecond=0)


async def _follow(session, *companies: str) -> None:
    """Follow `companies`, each read whole long before any posting here."""
    session.add_all(make_company(slug, slug.title()) for slug in companies)
    await session.flush()
    for slug in companies:
        await record_whole_read(session, slug, NOW - timedelta(days=365))
    await session.commit()


async def _close(session, monkeypatch, jobs: list[Job], *, first_miss: datetime, closed: datetime) -> None:
    """Two complete reads that miss `jobs`, at `first_miss` and at `closed`."""
    gap = timedelta(hours=get_settings().closure_second_miss_min_hours)
    existing = {job.dedupe_key: job for job in jobs}
    ids = frozenset(job.id for job in jobs)
    repo.record_absence(existing, set(), speaks_for=ids, now=first_miss, min_gap=gap)
    tally = repo.record_absence(existing, set(), speaks_for=ids, now=closed, min_gap=gap)
    assert tally.second_miss == ids
    run = ScrapeRun(status="ok", started_at=closed, per_source={}, drift_alerts=[])
    session.add(run)
    await session.flush()
    monkeypatch.setattr(repo, "_now", lambda: closed)
    await repo.close_missing(session, run, jobs[0].company, set(), existing, closable_job_ids=ids)
    await session.commit()


async def _reopen(session, monkeypatch, job: Job, at: datetime) -> None:
    """What the writer does when a read lists a closed `job` again (the
    reopen in `repo`'s upsert): open, no closing, a `reopened` event."""
    run = ScrapeRun(status="ok", started_at=at, per_source={}, drift_alerts=[])
    session.add(run)
    await session.flush()
    monkeypatch.setattr(repo, "_now", lambda: at)
    job.status, job.closed_at = "open", None
    repo._add_event(session, run, job, "reopened", {})
    await session.commit()


async def _rebuild(session) -> None:
    await rebuild_lineage_projection(session)
    await session.commit()
    await rebuild_place_sets(session)


async def _motion(api_client, days: int = 30) -> dict:
    """Overview's and Pace's counts, which must agree, and Pace's kpis."""
    overview = (await api_client.get(f"/api/statistics/overview?days={days}")).json()["kpis"]
    pace = (await api_client.get(f"/api/statistics/velocity?days={days}")).json()
    kpis = pace["kpis"]
    assert (overview["new_count"], overview["already_listed_count"], overview["closed_count"]) == (
        kpis["opened"], kpis["already_listed"], kpis["closed"],
    )
    assert sum(b["count"] for b in pace["aging"]) + kpis["age_unknown"] == kpis["open_total"]
    return pace


# --------------------------------------------------------------------------- #
# Opened: the New rule at our first sighting
# --------------------------------------------------------------------------- #


async def test_a_role_is_opened_when_it_was_new_when_found(api_client, db_session, monkeypatch):
    """Each role first seen 5 days ago, at a company already read unless
    noted. Opened: undated, dated a day before we saw it, dated after we saw
    it, a first read's find dated the day before, and an unclassified row.
    Already listed: dated 30 days before we saw it, and a first read's finds
    dated a month back, undated, or dated after the read. Every role first
    seen in the window lands in exactly one bucket."""
    await _follow(db_session, "google")
    seen = NOW - timedelta(days=5)
    cases = {
        "watched-undated": ({"arrival": "new"}, "opened"),
        "watched-day-before": ({"arrival": "new", "posted_at": seen - timedelta(days=1)}, "opened"),
        "watched-dated-later": ({"arrival": "new", "posted_at": seen + timedelta(days=1)}, "opened"),
        "unclassified": ({"arrival": None}, "opened"),
        "first-read-day-before": ({"arrival": "first_read", "posted_at": seen - timedelta(days=1)}, "opened"),
        "watched-month-back": ({"arrival": "new", "posted_at": seen - timedelta(days=30)}, "already_listed"),
        "first-read-month-back": ({"arrival": "first_read", "posted_at": seen - timedelta(days=30)}, "already_listed"),
        "first-read-undated": ({"arrival": "first_read"}, "already_listed"),
        "first-read-dated-later": ({"arrival": "first_read", "posted_at": seen + timedelta(days=1)}, "already_listed"),
    }
    db_session.add_all(
        make_job(key, first_seen=seen, last_seen=NOW, **fields) for key, (fields, _) in cases.items()
    )
    db_session.add(make_job("before-the-window", first_seen=NOW - timedelta(days=40), last_seen=NOW, arrival="new"))
    await db_session.commit()

    kpis = (await _motion(api_client))["kpis"]
    expected = [kind for _, kind in cases.values()]
    assert (kpis["opened"], kpis["already_listed"], kpis["reposted"]) == (
        expected.count("opened"), expected.count("already_listed"), 0,
    )
    assert kpis["opened"] + kpis["already_listed"] + kpis["reposted"] == len(cases)
    # The first read's undated find and the one dated after the read have no
    # knowable start; every other role has one.
    assert kpis["age_unknown"] == 2


async def test_a_role_that_opened_and_came_down_in_the_window_is_still_an_opening(
    api_client, db_session, monkeypatch,
):
    await _follow(db_session, "google")
    job = make_job("brief", first_seen=NOW - timedelta(days=3), last_seen=NOW - timedelta(days=2), arrival="new")
    db_session.add(job)
    await db_session.commit()
    await _close(db_session, monkeypatch, [job], first_miss=NOW - timedelta(days=2), closed=NOW - timedelta(days=1))
    kpis = (await _motion(api_client, days=7))["kpis"]
    assert (kpis["opened"], kpis["closed"]) == (1, 1)


# --------------------------------------------------------------------------- #
# Came down: roles, once, dated when they went
# --------------------------------------------------------------------------- #


async def test_a_role_closed_reopened_and_closed_came_down_once(api_client, db_session, monkeypatch):
    await _follow(db_session, "google")
    job = make_job("again", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="new")
    db_session.add(job)
    await db_session.commit()
    await _close(db_session, monkeypatch, [job], first_miss=NOW - timedelta(days=10), closed=NOW - timedelta(days=9))
    await _reopen(db_session, monkeypatch, job, NOW - timedelta(days=6))
    await _close(db_session, monkeypatch, [job], first_miss=NOW - timedelta(days=3), closed=NOW - timedelta(days=2))
    closings = await db_session.scalar(
        select(JobLifecycleEvent.id).where(JobLifecycleEvent.event_type == "closed").limit(1).offset(1)
    )
    assert closings is not None, "two closures were written: this case must count them once"
    kpis = (await _motion(api_client))["kpis"]
    assert kpis["closed"] == 1
    # Its time posted runs from its first sighting 20 days ago to its last closing.
    assert kpis["closed_sample"] == 1


async def test_a_role_that_came_back_did_not_come_down(api_client, db_session, monkeypatch):
    await _follow(db_session, "google")
    job = make_job("back", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="new")
    db_session.add(job)
    await db_session.commit()
    await _close(db_session, monkeypatch, [job], first_miss=NOW - timedelta(days=4), closed=NOW - timedelta(days=3))
    await _reopen(db_session, monkeypatch, job, NOW - timedelta(days=1))
    assert (await _motion(api_client))["kpis"]["closed"] == 0
    hiring = (await api_client.get("/api/demand")).json()
    assert hiring["closed"] == 0


async def test_a_role_listed_in_three_places_came_down_once_and_opened_once(api_client, db_session, monkeypatch):
    """The rebuild drops closed postings from their set, so the set cannot
    answer; the note the closing wrote does. While one place is still listed,
    the role has not come down, and its opening stays one."""
    await _follow(db_session, "aecom")
    london, leeds, bristol = [await place_set_job(db_session, n, city) for n, city in enumerate(("London", "Leeds", "Bristol"))]
    await db_session.commit()
    await _rebuild(db_session)
    assert await db_session.scalar(select(JobPlaceSetMember.set_id).where(JobPlaceSetMember.job_id == london.id))

    gone = NOW - timedelta(hours=26)
    await _close(db_session, monkeypatch, [london, leeds], first_miss=gone, closed=NOW - timedelta(hours=2))
    await _rebuild(db_session)
    assert await db_session.scalar(select(JobPlaceSetMember.job_id).where(JobPlaceSetMember.job_id == london.id)) is None
    kpis = (await _motion(api_client))["kpis"]
    assert (kpis["opened"], kpis["closed"], kpis["open_total"]) == (1, 0, 1)
    assert (await api_client.get("/api/demand")).json()["closed"] == 0

    await _close(db_session, monkeypatch, [bristol], first_miss=gone, closed=NOW - timedelta(hours=1))
    await _rebuild(db_session)
    kpis = (await _motion(api_client))["kpis"]
    assert (kpis["opened"], kpis["closed"], kpis["open_total"]) == (1, 1, 0)
    assert (await api_client.get("/api/demand")).json()["closed"] == 1


async def _closing_note(session, job: Job) -> dict:
    return await session.scalar(
        select(JobLifecycleEvent.detail).where(JobLifecycleEvent.job_id == job.id, JobLifecycleEvent.event_type == "closed")
    )


async def _set_of(session, job: Job):
    return await session.scalar(select(JobPlaceSetMember.set_id).where(JobPlaceSetMember.job_id == job.id))


async def test_a_closing_records_the_postings_that_stay_and_those_that_close_with_it(
    api_client, db_session, monkeypatch,
):
    """One role at three places closes at London first: its note names Leeds
    and Bristol, which stay. Leeds and Bristol then close in one read, each
    naming the other. A posting with no place set names nobody."""
    await _follow(db_session, "aecom")
    london, leeds, bristol = [await place_set_job(db_session, n, city) for n, city in enumerate(("London", "Leeds", "Bristol"))]
    single = make_job("single", company="aecom", first_seen=NOW - timedelta(days=4), last_seen=NOW, arrival="new")
    db_session.add(single)
    await db_session.commit()
    await _rebuild(db_session)

    gone = NOW - timedelta(hours=26)
    await _close(db_session, monkeypatch, [london], first_miss=gone, closed=NOW - timedelta(hours=3))
    assert await _closing_note(db_session, london) == {
        "basis": "absent_from_complete_listing", "first_missed_at": gone.isoformat(),
        "listed_with": sorted([leeds.id, bristol.id]), "closed_with": [],
    }
    await _close(db_session, monkeypatch, [leeds, bristol, single], first_miss=gone, closed=NOW - timedelta(hours=2))
    notes = {job.id: await _closing_note(db_session, job) for job in (leeds, bristol, single)}
    assert [(n["listed_with"], n["closed_with"]) for n in notes.values()] == [
        ([], [bristol.id]), ([], [leeds.id]), ([], []),
    ]
    await _rebuild(db_session)

    kpis = (await _motion(api_client))["kpis"]
    assert (kpis["opened"], kpis["closed"], kpis["open_total"]) == (2, 2, 0)
    assert (await api_client.get("/api/demand")).json()["closed"] == 2


@pytest.mark.parametrize("together", [True, False], ids=["closed-together", "first-place-first"])
async def test_a_role_opens_when_its_first_place_was_seen_whichever_place_closes(
    api_client, db_session, monkeypatch, together,
):
    """London was seen 10 days ago, Leeds, the same role, 5 days ago: the role
    did not open in the last 7 days. It still did not when its places close,
    together or London first, and it came down once, when the last one went."""
    await _follow(db_session, "aecom")
    london, leeds = [await place_set_job(db_session, n, city) for n, city in enumerate(("London", "Leeds"))]
    london.first_seen, leeds.first_seen = NOW - timedelta(days=10), NOW - timedelta(days=5)
    await db_session.commit()
    await _rebuild(db_session)
    assert await _set_of(db_session, london) == await _set_of(db_session, leeds) is not None
    assert ((await _motion(api_client, days=7))["kpis"]["opened"], (await _motion(api_client, days=0))["kpis"]["opened"]) == (0, 1)

    gone = NOW - timedelta(hours=30)
    if not together:
        await _close(db_session, monkeypatch, [london], first_miss=gone, closed=NOW - timedelta(hours=4))
        await _rebuild(db_session)
        kpis = (await _motion(api_client, days=7))["kpis"]
        assert (kpis["opened"], kpis["closed"], kpis["open_total"]) == (0, 0, 1)
    await _close(db_session, monkeypatch, [london, leeds] if together else [leeds], first_miss=gone, closed=NOW - timedelta(hours=2))
    await _rebuild(db_session)
    kpis = (await _motion(api_client, days=7))["kpis"]
    assert (kpis["opened"], kpis["closed"], kpis["open_total"]) == (0, 1, 0)
    assert (await _motion(api_client, days=0))["kpis"]["opened"] == 1


async def test_a_role_relisted_at_its_place_keeps_its_opening(api_client, db_session, monkeypatch):
    """The role in London, seen 10 days ago, listed again there 3 days ago:
    one role, already open before the last 7 days. When the first listing
    closes, the role neither opened nor came down."""
    await _follow(db_session, "aecom")
    first, again = [await place_set_job(db_session, n, "London") for n in (0, 1)]
    first.first_seen, again.first_seen = NOW - timedelta(days=10), NOW - timedelta(days=3)
    await db_session.commit()
    await _rebuild(db_session)
    assert await _set_of(db_session, first) == await _set_of(db_session, again) is not None
    assert (await _motion(api_client, days=7))["kpis"]["opened"] == 0

    await _close(db_session, monkeypatch, [first], first_miss=NOW - timedelta(hours=30), closed=NOW - timedelta(hours=2))
    await _rebuild(db_session)
    kpis = (await _motion(api_client, days=7))["kpis"]
    assert (kpis["opened"], kpis["closed"], kpis["open_total"]) == (0, 0, 1)
    assert (await _motion(api_client, days=0))["kpis"]["opened"] == 1


async def test_a_place_out_of_scope_keeps_no_in_scope_role_listed(api_client, db_session, monkeypatch):
    """The role in Manchester, in scope, and in London, a place the person no
    longer follows. Manchester closes while London stays: in the person's
    scope the role came down, and its opening stays."""
    await _follow(db_session, "aecom")
    manchester, london = [await place_set_job(db_session, n, city) for n, city in enumerate(("Manchester", "London"))]
    london.in_scope = False
    await db_session.commit()
    await _rebuild(db_session)
    assert await _set_of(db_session, manchester) == await _set_of(db_session, london) is not None

    await _close(db_session, monkeypatch, [manchester], first_miss=NOW - timedelta(hours=30), closed=NOW - timedelta(hours=2))
    assert (await _closing_note(db_session, manchester))["listed_with"] == [london.id]
    await _rebuild(db_session)
    kpis = (await _motion(api_client))["kpis"]
    assert (kpis["opened"], kpis["closed"], kpis["open_total"]) == (1, 1, 0)
    assert (await api_client.get("/api/demand")).json()["closed"] == 1


async def test_a_closing_from_before_the_notes_counts_its_posting_alone(api_client, db_session, monkeypatch):
    """Two places of one role closed by a scan that recorded no ids: nothing
    says they were one role, so each counts once, as each was a posting."""
    await _follow(db_session, "aecom")
    london, leeds = [await place_set_job(db_session, n, city) for n, city in enumerate(("London", "Leeds"))]
    went = NOW - timedelta(days=2)
    for job in (london, leeds):
        job.status, job.closed_at = "closed", went
        db_session.add(JobLifecycleEvent(job_id=job.id, event_type="closed", detail={"basis": "absent_from_complete_listing"}, created_at=went))
    await db_session.commit()
    await _rebuild(db_session)
    kpis = (await _motion(api_client))["kpis"]
    assert (kpis["opened"], kpis["closed"]) == (2, 2)


async def test_a_failed_role_note_never_holds_a_closure_back(api_client, db_session, monkeypatch):
    """The place-set read fails in the database while a scan closes a
    posting: the posting still closes, with no ids, and counts alone."""
    await _follow(db_session, "aecom")
    job = await place_set_job(db_session, 0, "London")
    await db_session.commit()

    async def failing(session, *args, **kwargs):
        await session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(place_sets, "place_set_groups", failing)
    await _close(db_session, monkeypatch, [job], first_miss=NOW - timedelta(hours=30), closed=NOW - timedelta(hours=2))
    await db_session.refresh(job)
    assert job.status == "closed"
    assert "listed_with" not in await _closing_note(db_session, job)
    assert (await _motion(api_client))["kpis"]["closed"] == 1


async def test_a_role_that_came_down_with_an_unknown_start_is_counted_beside_the_bands(
    api_client, db_session, monkeypatch,
):
    """Found on a company's first scan with no date from the employer, then
    closed: it came down, with no time posted to band."""
    await _follow(db_session, "google")
    found = make_job("found", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="first_read")
    db_session.add(found)
    await db_session.commit()
    await _close(db_session, monkeypatch, [found], first_miss=NOW - timedelta(hours=30), closed=NOW - timedelta(hours=2))
    pace = await _motion(api_client)
    kpis = pace["kpis"]
    assert (kpis["closed"], kpis["closed_sample"], kpis["closed_unknown"]) == (1, 0, 1)
    assert sum(b["count"] for b in pace["posted"]) == 0


async def test_a_closing_counts_when_the_scan_confirms_it(api_client, db_session, monkeypatch):
    """First missed 8 days ago and confirmed closed 6 days ago: inside a 7-day
    window, and posted for the 14 days from its first sighting to that
    confirmation. A posting missed once, 30 hours ago, is still open."""
    await _follow(db_session, "google")
    late = make_job("late", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="new")
    pending = make_job("pending", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="new")
    db_session.add_all([late, pending])
    await db_session.commit()
    await _close(db_session, monkeypatch, [late], first_miss=NOW - timedelta(days=8), closed=NOW - timedelta(days=6))
    event = await db_session.scalar(select(JobLifecycleEvent).where(JobLifecycleEvent.job_id == late.id))
    assert event is not None and "first_missed_at" in event.detail
    gap = timedelta(hours=get_settings().closure_second_miss_min_hours)
    repo.record_absence({pending.dedupe_key: pending}, set(), speaks_for=frozenset({pending.id}), now=NOW - timedelta(hours=30), min_gap=gap)
    await db_session.commit()

    pace = await _motion(api_client, days=7)
    assert (pace["kpis"]["closed"], pace["kpis"]["open_total"]) == (1, 1)
    assert {b["lo"]: b["count"] for b in pace["posted"]}[14] == 1


async def test_hiring_counts_the_roles_confirmed_closed_in_its_two_days_once(api_client, db_session, monkeypatch):
    """Hiring's two days: a role confirmed closed 4 days ago is outside; one
    first missed 30 hours ago and confirmed 2 hours ago is inside."""
    await _follow(db_session, "google")
    older = make_job("older", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="new")
    recent = make_job("recent", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="new")
    db_session.add_all([older, recent])
    await db_session.commit()
    await _close(db_session, monkeypatch, [older], first_miss=NOW - timedelta(days=5), closed=NOW - timedelta(days=4))
    await _close(db_session, monkeypatch, [recent], first_miss=NOW - timedelta(hours=30), closed=NOW - timedelta(hours=2))
    hiring = (await api_client.get("/api/demand")).json()
    assert hiring["closed"] == 1
    assert [(c["company"], c["closed"]) for c in hiring["companies"]] == [("google", 1)]


# --------------------------------------------------------------------------- #
# Lineages: one role, one clock
# --------------------------------------------------------------------------- #


async def test_a_repost_continues_its_role_and_ages_from_the_earliest_posting(api_client, db_session, monkeypatch):
    """The original, dated by its employer 60 days before we saw it, came
    down; its repost is open. The role has not come down, the repost is not an
    opening (and the original was already listed when found), and the open
    role is as old as the original's employer date, so its age is the
    employer's though the repost carries no date."""
    await _follow(db_session, "google")
    original = make_job("original", first_seen=NOW - timedelta(days=20), last_seen=NOW - timedelta(days=12),
                        arrival="new", posted_at=NOW - timedelta(days=80))
    repost = make_job("repost", first_seen=NOW - timedelta(days=10), last_seen=NOW, arrival="new")
    db_session.add_all([original, repost])
    await db_session.commit()
    await _close(db_session, monkeypatch, [original], first_miss=NOW - timedelta(days=12), closed=NOW - timedelta(days=11))
    db_session.add(lineage_link(repost, original, "repost"))
    await db_session.commit()
    await _rebuild(db_session)

    pace = await _motion(api_client)
    kpis = pace["kpis"]
    assert (kpis["opened"], kpis["already_listed"], kpis["reposted"], kpis["closed"]) == (0, 1, 1, 0)
    assert {b["lo"]: b["count"] for b in pace["aging"]}[60] == 1  # 80 days: 2 to 3 months
    assert kpis["employer_dated_share"] == 1.0
    assert (await api_client.get("/api/demand")).json()["closed"] == 0


async def test_a_lineage_went_when_its_last_posting_went(api_client, db_session, monkeypatch):
    """Two postings of one role, listed at once (a duplicate); the earlier one
    stayed up longer. The role went when that one went, 2 days ago: inside a
    3-day window, though the later posting went 5 days ago."""
    await _follow(db_session, "google")
    earlier = make_job("earlier", first_seen=NOW - timedelta(days=20), last_seen=NOW, arrival="new")
    later = make_job("later", first_seen=NOW - timedelta(days=19), last_seen=NOW, arrival="new")
    db_session.add_all([earlier, later])
    await db_session.commit()
    db_session.add(lineage_link(later, earlier, "duplicate"))
    await db_session.commit()
    await _rebuild(db_session)
    await _close(db_session, monkeypatch, [later], first_miss=NOW - timedelta(days=5), closed=NOW - timedelta(days=4))
    await _close(db_session, monkeypatch, [earlier], first_miss=NOW - timedelta(days=2), closed=NOW - timedelta(days=1))
    await _rebuild(db_session)
    assert (await _motion(api_client, days=3))["kpis"]["closed"] == 1
    assert (await _motion(api_client, days=30))["kpis"]["closed"] == 1

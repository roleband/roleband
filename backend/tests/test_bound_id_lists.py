"""No read sends the database a list of ids that grows with the data.

A list fetched into Python and bound back (`= ANY(:ids)`) crosses the wire
twice, and once Postgres plans a prepared statement generically it searches
the array row by row, so the cost grows with ids times rows. The rules these
reads need (a place set's later members, the new-listing rule) run inside the
statement instead. The seed holds more ids of each kind than a bound
list may carry, so a read that binds one fails here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.dialects import postgresql

from tests.factories import make_company, make_job, record_whole_read
from tracker.analytics.demand import compute_demand_metrics
from tracker.db.models import Job, JobLifecycleEvent, JobPlaceSet, JobPlaceSetMember, ScrapeRun
from tracker.db.queries.jobs import open_in_scope_count_stmt, structured_conds
from tracker.lineage.counts import place_set_later

#: More ids of each kind than a bound list may carry.
MANY = 600
#: The longest list one statement may bind.
LONGEST_BOUND_LIST = 500

READS = (
    "/api/stats",
    "/api/statistics/overview",
    "/api/statistics/velocity?days=30",
    "/api/statistics/velocity?days=0",
    "/api/demand",
    "/api/jobs?status=open&new_today_only=true&limit=20",
    "/api/facets",
)


#: Roles that opened and came down long before any window a read shows.
HISTORY = 10 * MANY


async def _history(db_session, now: datetime) -> None:
    """HISTORY postings at `veteran`, read whole for over a year, each first
    seen 200 to 365 days ago and closed 100 days later, with the events a
    closing writes: every second one closed in the same read as the next."""
    await record_whole_read(db_session, "veteran", now - timedelta(days=400))
    db_session.add_all(
        make_job(
            f"history-{i}", company="veteran", status="closed", arrival="new",
            first_seen=now - timedelta(days=365 - i // 2 % 165), last_seen=now - timedelta(days=266 - i // 2 % 165),
            closed_at=now - timedelta(days=265 - i // 2 % 165),
        )
        for i in range(HISTORY)
    )
    await db_session.flush()
    await db_session.execute(text("""
        INSERT INTO job_lifecycle_events (job_id, event_type, detail, created_at)
        SELECT id, 'opened', '{}'::jsonb, first_seen FROM jobs WHERE company = 'veteran'
        UNION ALL
        SELECT id, 'closed',
               jsonb_build_object(
                   'basis', 'absent_from_complete_listing', 'listed_with', '[]'::jsonb,
                   'closed_with', jsonb_build_array(CASE WHEN n % 2 = 1 THEN after ELSE before END)),
               closed_at
        FROM (
            SELECT id, closed_at, row_number() OVER w AS n, lead(id) OVER w AS after, lag(id) OVER w AS before
            FROM jobs WHERE company = 'veteran' WINDOW w AS (ORDER BY id)
        ) closings
    """))


async def _seed(db_session, *, analyze: bool = True, history: bool = True) -> None:
    """acme's first scan finds MANY roles its board was already listing; a later
    run finds one role listed at MANY + 1 places, a place set with MANY later
    members. Before them, a year of HISTORY roles at another company opened
    and came down, each closing with its note."""
    now = datetime.now(UTC)
    if history:
        await _history(db_session, now)
    first = ScrapeRun(started_at=now - timedelta(hours=4), status="ok")
    later = ScrapeRun(started_at=now - timedelta(hours=2), status="ok")
    db_session.add_all([make_company("acme", "Acme"), first, later])
    await db_session.flush()
    await record_whole_read(db_session, "acme", first.started_at)
    finds = [
        make_job(f"find-{i}", company="acme", first_seen=first.started_at, arrival="first_read")
        for i in range(MANY)
    ]
    places = [
        make_job(f"place-{i}", company="acme", first_seen=later.started_at + timedelta(seconds=i), arrival="new")
        for i in range(MANY + 1)
    ]
    place_set = JobPlaceSet(company="acme", title="staff product manager", text_hash="0" * 32,
                            size=len(places), places=[], rule_version="t1")
    db_session.add_all([*finds, *places, place_set])
    await db_session.flush()
    for run, jobs in ((first, finds), (later, places)):
        db_session.add_all(
            JobLifecycleEvent(job_id=job.id, run_id=run.id, event_type="opened", detail={},
                              created_at=run.started_at)
            for job in jobs
        )
    db_session.add_all(JobPlaceSetMember(job_id=job.id, set_id=place_set.id, status="auto") for job in places)
    await db_session.commit()
    if analyze:
        # Statistics for the rows, as a database holding them has, so each read
        # here is measured on the plan it gets in use.
        await db_session.execute(text("ANALYZE jobs, job_place_set_member, job_place_set, job_lifecycle_events"))


@pytest.mark.asyncio
async def test_no_read_binds_a_list_of_ids_that_grows_with_the_data(api_client, db_session):
    await _seed(db_session)
    longest: dict[str, int] = {}
    reading = [""]

    def record(conn, cursor, statement, parameters, context, executemany):
        longest.setdefault(reading[0], 0)
        for row in parameters if executemany else [parameters]:
            values = row.values() if isinstance(row, dict) else row or ()
            for value in values:
                if isinstance(value, list | tuple):
                    longest[reading[0]] = max(longest[reading[0]], len(value))

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        for path in READS:
            reading[0] = path
            response = await api_client.get(path)
            assert response.status_code == 200, (path, response.text)
        reading[0] = "demand post-pass"
        await compute_demand_metrics(db_session)
        await db_session.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert set(longest) == {*READS, "demand post-pass"}, "every read must reach the listener, or this proves nothing"
    assert {read: n for read, n in longest.items() if n > LONGEST_BOUND_LIST} == {}


@pytest.mark.asyncio
async def test_pace_and_overview_keep_their_rules_at_volume(api_client, db_session):
    """The same seed through the rules themselves: the first scan's finds are
    never openings and have no knowable age, and the place set opens once and
    is open once."""
    await _seed(db_session)
    velocity = (await api_client.get("/api/statistics/velocity?days=30")).json()
    kpis = velocity["kpis"]
    assert (kpis["opened"], kpis["already_listed"], kpis["open_total"]) == (1, MANY, MANY + 1)
    assert sum(band["count"] for band in velocity["aging"]) + kpis["age_unknown"] == kpis["open_total"]
    assert kpis["age_unknown"] == MANY  # the first scan's undated finds
    overview = (await api_client.get("/api/statistics/overview?days=30")).json()["kpis"]
    assert (overview["new_count"], overview["already_listed_count"]) == (1, MANY)


#: The reads whose window ends now and whose figures all fit in it. Overview
#: and Pace with a window; Hiring's two days.
WINDOWED_READS = (
    "/api/statistics/overview?days=30",
    "/api/statistics/velocity?days=30",
    "/api/demand",
)


async def _postings_read(api_client, db_session) -> dict[str, int]:
    """The posting rows each windowed read reads: every statement it sends,
    run again under `EXPLAIN (ANALYZE)`."""
    sent: dict[str, list[tuple[str, object]]] = {}
    reading = [""]

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            sent.setdefault(reading[0], []).append((statement, parameters))

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        for path in WINDOWED_READS:
            reading[0] = path
            response = await api_client.get(path)
            assert response.status_code == 200, (path, response.text)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert set(sent) == set(WINDOWED_READS), "every read must reach the listener, or this proves nothing"

    read: dict[str, int] = {}
    connection = await db_session.connection()
    for path, statements in sent.items():
        for statement, parameters in statements:
            plan = await connection.exec_driver_sql(f"EXPLAIN (ANALYZE, FORMAT JSON) {statement}", parameters)
            read[path] = read.get(path, 0) + _rows_read(plan.scalar_one()[0]["Plan"]).get("jobs", 0)
    await db_session.rollback()
    return read


@pytest.mark.asyncio
async def test_a_windowed_read_never_reads_the_history_it_does_not_show(api_client, db_session):
    """The same reads before and after a year of HISTORY roles that opened
    and came down long before any window: a window's read reads the roles it
    shows and the open ones, so the history adds next to nothing, and a read
    does not grow with every month an install runs."""
    await _seed(db_session, history=False)
    without = await _postings_read(api_client, db_session)
    await _history(db_session, datetime.now(UTC))
    await db_session.commit()
    await db_session.execute(text("ANALYZE jobs, job_lifecycle_events"))
    with_history = await _postings_read(api_client, db_session)
    grew = {path: with_history[path] - without[path] for path in WINDOWED_READS}
    # A plan chosen on the new statistics may probe the open postings once
    # more by id; a read of the history would add every one of its postings.
    assert all(n < HISTORY // 4 for n in grew.values()), (grew, without)


def _rows_read(plan: dict) -> dict[str, int]:
    """Rows each table was read for over a whole `EXPLAIN (ANALYZE)` run: a
    scan's rows per loop, those it returned and those its filter dropped,
    times its loops, summed by relation."""
    out: dict[str, int] = {}
    if "Relation Name" in plan:
        name = plan["Relation Name"]
        per_loop = (
            plan["Actual Rows"]
            + plan.get("Rows Removed by Filter", 0)
            + plan.get("Rows Removed by Index Recheck", 0)
        )
        out[name] = out.get(name, 0) + per_loop * plan["Actual Loops"]
    for child in plan.get("Plans", []):
        for name, rows in _rows_read(child).items():
            out[name] = out.get(name, 0) + rows
    return out


def test_a_read_counts_the_rows_a_filter_dropped_on_every_loop():
    """A scan that returns one row a loop but reads every posting to find it
    is a whole pass per loop."""
    scan = {"Relation Name": "jobs", "Actual Rows": 1, "Rows Removed by Filter": 1200, "Actual Loops": 1201}
    plan = {"Node Type": "Nested Loop", "Actual Rows": 1201, "Actual Loops": 1, "Plans": [scan]}
    assert _rows_read(plan) == {"jobs": 1201 * 1201}


@pytest.mark.asyncio
async def test_the_rule_reads_only_the_postings_in_a_set_however_long_the_history(db_session):
    """Statistics taken when the members were most of the postings let the
    planner join the members to every posting. The rule reads each member's
    posting by its id, so postings in no set are never read for it."""
    await _seed(db_session)
    db_session.add_all(make_job(f"history-{i}", company="acme", status="closed") for i in range(10 * MANY))
    await db_session.commit()
    sql = place_set_later().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    plan = (await db_session.execute(text(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}"))).scalar_one()[0]["Plan"]
    assert len((await db_session.scalars(place_set_later())).all()) == MANY
    assert _rows_read(plan).get("jobs", 0) <= MANY + 1, _rows_read(plan)


@pytest.mark.asyncio
async def test_a_place_set_shows_once_in_one_pass_whatever_the_statistics_say(db_session):
    """Statistics taken while the tables were empty (a fresh install before its
    first scan) leave the planner free to check each open posting against
    every other for an earlier member of its set: quadratic in open postings.
    The rule finds a set's later members once per statement, so each count
    reads the members and the postings a few times over, never once per
    posting, and still shows the set once."""
    await db_session.execute(text("ANALYZE jobs, job_place_set_member, job_place_set"))
    await db_session.commit()
    await _seed(db_session, analyze=False)
    postings, members = MANY + MANY + 1, MANY + 1
    board = select(func.count()).select_from(Job).where(*structured_conds({"status": "open", "hidden": []}))
    for name, stmt in (("open count", open_in_scope_count_stmt()), ("Board", board)):
        assert await db_session.scalar(stmt) == MANY + 1, name
        sql = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        plan = (await db_session.execute(text(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}"))).scalar_one()[0]["Plan"]
        read = _rows_read(plan)
        assert read.get("job_place_set_member", 0) <= 3 * members, (name, read)
        assert read.get("jobs", 0) <= 3 * postings, (name, read)

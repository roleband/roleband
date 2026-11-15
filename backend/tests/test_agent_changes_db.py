"""`changes.list` reads each change once, in commit order, from what is recorded.

The subject is the feed (`tracker/agents/operations/changes.py`) behind its
route, over real ASGI on the scratch database. Changes are written as the
writers write them: rows inserted in their own transactions, the position
columns left to their defaults. The commit-order test runs two writers at once
and holds one open across a read; a naive reader that remembers the highest
id it saw runs the same steps beside it and loses the late commit, which is
what makes the test able to fail.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.factories import make_company, make_job
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.changes import (
    CHANGES_LIST,
    KINDS,
    ChangesListInput,
    changes_page,
)
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.agents.receipts import LEGACY_AGENT_PRINCIPAL
from tracker.api.agent_operations import PREFIX
from tracker.db.models import (
    Job,
    JobLifecycleEvent,
    PluginInstall,
    PluginRun,
    Pursuit,
    ScrapeRun,
    ScrapeSourceRun,
    SourceBinding,
    WorkspaceIdentity,
)

pytestmark = pytest.mark.asyncio

T = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def feed(db_session) -> AsyncIterator[AsyncSession]:
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(db_session)
    await db_session.commit()
    yield db_session


def _factory(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_session.bind, expire_on_commit=False)


async def _posting(db_session: AsyncSession, req_id: str, *, company: str = "acme", **over: Any) -> int:
    async with _factory(db_session)() as session:
        job = make_job(req_id, company=company, **over)
        session.add(job)
        await session.commit()
        return job.id


async def _event(db_session: AsyncSession, job_id: int, event_type: str, detail: dict | None = None) -> int:
    """One lifecycle event in its own committed transaction, as a writer leaves it."""
    async with _factory(db_session)() as session:
        event = JobLifecycleEvent(job_id=job_id, event_type=event_type, detail=detail or {})
        session.add(event)
        await session.commit()
        return event.id


async def _get(api_client, **params) -> tuple[int, dict]:
    response = await api_client.get(f"{PREFIX}/changes", params=params)
    return response.status_code, response.json()


async def _page(api_client, **params) -> dict:
    status, body = await _get(api_client, **params)
    assert status == 200 and body["ok"] is True, body
    return body


async def _drain(api_client, **params) -> tuple[list[dict], str]:
    """Every event from a position to the read's frontier, following continue_with."""
    events: list[dict] = []
    while True:
        data = (await _page(api_client, **params))["data"]
        events.extend(data["events"])
        if data["caught_up"]:
            assert data["continue_with"] == []
            return events, data["next_since"]
        [action] = data["continue_with"]
        assert action["operation"] == CHANGES_LIST.id
        params = action["arguments"]


async def _start(api_client, **params) -> str:
    """A position after everything already recorded, for a read of these kinds."""
    _, since = await _drain(api_client, **params)
    return since


def _band(low: int, high: int) -> dict:
    return {"min": low, "max": high, "currency": "USD", "period": "year"}


# --------------------------------------------------------------------------- #
# Kinds
# --------------------------------------------------------------------------- #


async def _source_run(db_session, binding_id: int, outcome_: str, *, scan_mode: str = "reconcile") -> int:
    async with _factory(db_session)() as session:
        run = ScrapeRun(status="ok", started_at=T, per_source={}, drift_alerts=[])
        session.add(run)
        await session.flush()
        row = ScrapeSourceRun(
            run_id=run.id, binding_id=binding_id, company_slug="acme", provider_key="greenhouse:acme",
            scan_mode=scan_mode, outcome=outcome_, started_at=T, finished_at=T + timedelta(minutes=1),
        )
        session.add(row)
        await session.commit()
        return row.id


async def _binding(db_session) -> int:
    async with _factory(db_session)() as session:
        if await session.get(type(make_company("acme", "Acme")), "acme") is None:
            session.add(make_company("acme", "Acme"))
            await session.flush()
        binding = SourceBinding(company_slug="acme", connector_kind="greenhouse", connector_id="acme")
        session.add(binding)
        await session.commit()
        return binding.id


async def test_each_kind_appears_once_from_a_seeded_change_with_how_it_is_known(api_client, feed):
    opened = await _posting(feed, "opened")
    closed = await _posting(feed, "closed")
    reopened = await _posting(feed, "reopened")
    repost = await _posting(feed, "repost", lineage_role="repost")
    paid = await _posting(feed, "paid")
    pursued = await _posting(feed, "pursued")
    binding = await _binding(feed)
    await _source_run(feed, binding, "ok")
    since = await _start(api_client)

    await _event(feed, opened, "opened")
    await _event(feed, closed, "closed", {"note": "gone from the listing"})
    await _event(feed, reopened, "reopened")
    await _event(feed, repost, "opened")
    await _event(feed, paid, "changed", {"disclosed_base": {"from": _band(150_000, 180_000), "to": _band(160_000, 200_000)}})
    # A change of another field is not a stated-pay change.
    await _event(feed, paid, "changed", {"title": {"from": "a", "to": "b"}})
    await _source_run(feed, binding, "failed")
    async with _factory(feed)() as session:
        due_at = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
        session.add(Pursuit(job_id=pursued, stage="applied", next_action="Write back", next_action_due=due_at))
        await session.commit()

    events, _ = await _drain(api_client, since=since)
    by_kind = {event["kind"]: event for event in events}
    assert sorted(event["kind"] for event in events) == sorted(
        ["new", "closed", "reopened", "reposted", "stated_pay_changed", "source_health", "pursuit_due"]
    )
    assert {kind: event["basis"] for kind, event in by_kind.items()} == {
        "new": "recorded", "closed": "recorded", "reopened": "recorded", "stated_pay_changed": "recorded",
        "reposted": "derived", "source_health": "derived", "pursuit_due": "derived",
    }
    assert by_kind["new"]["opportunity_id"] == opened
    assert by_kind["closed"]["opportunity_id"] == closed
    assert by_kind["reopened"]["opportunity_id"] == reopened
    assert by_kind["reposted"]["opportunity_id"] == repost
    assert by_kind["stated_pay_changed"]["opportunity_id"] == paid
    assert by_kind["stated_pay_changed"]["pay"] == {
        "before": {"low": 150_000, "high": 180_000, "currency": "USD", "period": "year"},
        "after": {"low": 160_000, "high": 200_000, "currency": "USD", "period": "year"},
    }
    assert by_kind["source_health"]["source"] == {
        "state": "failing", "previous_state": "healthy", "outcome": "failed", "provider": "greenhouse:acme",
    }
    assert by_kind["pursuit_due"]["opportunity_id"] == pursued
    assert len({event["sequence"] for event in events}) == len(events)


async def test_an_unavailable_kind_is_reported_as_such_and_never_inferred(api_client, feed):
    async with _factory(feed)() as session:
        session.add(PluginInstall(
            plugin_id="example.board", name="Example", version="1.0.0", source_dir="/plugins/example",
            code_sha="c" * 64, manifest_sha="m" * 64, manifest={}, fingerprint="f" * 64,
        ))
        await session.flush()
        session.add(PluginRun(plugin_id="example.board", job="sync", trigger="schedule", fingerprint="f" * 64,
                              outcome="error", ended_at=T))
        await session.commit()

    data = (await _page(api_client, kinds=["plugin_source_health"]))["data"]
    assert data["events"] == []
    assert data["unavailable"] == [{"kind": "plugin_source_health", "reason": "no_ordered_record"}]
    # Every read that asks for all kinds names it too.
    assert (await _page(api_client))["data"]["unavailable"] == [
        {"kind": "plugin_source_health", "reason": "no_ordered_record"}
    ]
    # A read of recorded kinds only does not mention it.
    assert (await _page(api_client, kinds=["new"]))["data"]["unavailable"] == []


async def test_an_opening_reads_as_a_repost_once_its_lineage_says_so(api_client, feed):
    job = await _posting(feed, "later-repost")
    since = await _start(api_client)
    await _event(feed, job, "opened")
    async with _factory(feed)() as session:
        await session.execute(update(Job).where(Job.id == job).values(lineage_role="repost"))
        await session.commit()
    [event], _ = await _drain(api_client, since=since)
    assert (event["kind"], event["basis"]) == ("reposted", "derived")
    assert (await _page(api_client, kinds=["new"]))["data"]["events"] == []


async def test_source_health_reports_each_move_between_states_and_nothing_else(api_client, feed):
    binding = await _binding(feed)
    since = await _start(api_client, kinds=["source_health"])
    for result in ("ok", "lossy", "unattempted", "degraded", "failed", "blocked", "ok"):
        await _source_run(feed, binding, result)
    # A rebind shadow is a test of a candidate recipe, not the source's health.
    await _source_run(feed, binding, "failed", scan_mode="shadow")
    events, _ = await _drain(api_client, since=since, kinds=["source_health"])
    # ok then lossy are both healthy: no move. unattempted says nothing. blocked stays failing.
    assert [(e["source"]["previous_state"], e["source"]["state"], e["source"]["outcome"]) for e in events] == [
        ("healthy", "degraded", "degraded"), ("degraded", "failing", "failed"), ("failing", "healthy", "ok"),
    ]


async def test_a_first_run_reports_only_when_it_is_not_healthy(api_client, feed):
    healthy, failing = await _binding(feed), await _binding(feed)
    since = await _start(api_client, kinds=["source_health"])
    await _source_run(feed, healthy, "ok")
    await _source_run(feed, failing, "blocked")
    events, _ = await _drain(api_client, since=since, kinds=["source_health"])
    assert [(e["source"]["previous_state"], e["source"]["state"]) for e in events] == [(None, "failing")]


async def test_a_posting_at_a_company_the_person_does_not_follow_is_left_out(api_client, feed):
    async with _factory(feed)() as session:
        session.add_all([make_company("shown", "Shown"), make_company("hidden", "Hidden", visible=False),
                         make_company("dropped", "Dropped", enabled=False)])
        await session.commit()
    shown = await _posting(feed, "s", company="shown")
    hidden = await _posting(feed, "h", company="hidden")
    dropped = await _posting(feed, "d", company="dropped")
    since = await _start(api_client)
    for job in (shown, hidden, dropped):
        await _event(feed, job, "opened")
    events, _ = await _drain(api_client, since=since)
    assert [event["opportunity_id"] for event in events] == [shown]


async def test_a_pursuit_due_time_that_passes_is_reported_once_and_a_terminal_one_never(api_client, feed):
    owed, done, later = [await _posting(feed, k) for k in ("owed", "done", "later")]
    since = await _start(api_client, kinds=["pursuit_due"])
    async with _factory(feed)() as session:
        now = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
        session.add_all([
            Pursuit(job_id=owed, stage="interviewing", next_action="Thank-you note", next_action_due=now),
            Pursuit(job_id=done, stage="rejected", next_action="Nothing", next_action_due=now),
            Pursuit(job_id=later, stage="applied", next_action="Chase", next_action_due=now + timedelta(days=3)),
        ])
        await session.commit()
    events, since = await _drain(api_client, since=since, kinds=["pursuit_due"])
    assert [(e["kind"], e["opportunity_id"]) for e in events] == [("pursuit_due", owed)]
    assert (await _drain(api_client, since=since, kinds=["pursuit_due"]))[0] == []


async def test_a_start_time_still_ahead_keeps_earlier_due_times_out_of_later_windows(api_client, feed):
    owed = await _posting(feed, "ahead")
    async with _factory(feed)() as session:
        now = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
    first, since = await _drain(api_client, kinds=["pursuit_due"], start_time=(now + timedelta(hours=1)).isoformat())
    assert first == []
    async with _factory(feed)() as session:
        # Due after the first window ended, and before start_time.
        due = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
        session.add(Pursuit(job_id=owed, stage="applied", next_action="Chase", next_action_due=due))
        await session.commit()
    assert (await _drain(api_client, since=since, kinds=["pursuit_due"]))[0] == []


async def _share_pursuits(db_session: AsyncSession, choice: str) -> None:
    async with _factory(db_session)() as session:
        await set_agent_access(session, AgentAccessConfig(
            enabled=True, allow_writes=False, categories={"private_pursuit": choice}))
        await session.commit()


async def test_pursuit_changes_are_absent_while_the_person_does_not_share_pursuits(api_client, feed):
    pursued = await _posting(feed, "private")
    opened = await _posting(feed, "public")
    since = await _start(api_client)
    await _event(feed, opened, "opened")
    async with _factory(feed)() as session:
        session.add(Pursuit(job_id=pursued, stage="applied", next_action="x",
                            next_action_due=(await session.execute(text("SELECT clock_timestamp()"))).scalar_one()))
        await session.commit()

    await _share_pursuits(feed, "not_shared")
    status, body = await _get(api_client, since=since)
    assert status == 200 and [event["kind"] for event in body["data"]["events"]] == ["new"]
    # Absent, not masked: nothing in the answer says a pursuit exists or was left out.
    assert "pursuit" not in json.dumps(body)
    # Asked for by name, the kind is refused as a search filter is.
    status, body = await _get(api_client, kinds=["pursuit_due"])
    assert status == outcome("category_disabled").http_status
    assert body["error"]["code"] == "category_disabled"
    assert body["error"]["details"]["field"] == "kinds"

    await _share_pursuits(feed, "any_model")
    events, _ = await _drain(api_client, since=since)
    assert sorted(event["kind"] for event in events) == ["new", "pursuit_due"]


# --------------------------------------------------------------------------- #
# Commit order
# --------------------------------------------------------------------------- #


async def _naive_read(db_session, after_id: int) -> list[int]:
    """The cursor this feed must not be: every event id above the last one seen."""
    async with _factory(db_session)() as session:
        return list((await session.scalars(
            select(JobLifecycleEvent.id).where(JobLifecycleEvent.id > after_id).order_by(JobLifecycleEvent.id)
        )).all())


async def test_a_writer_that_commits_after_a_read_past_its_id_still_appears_exactly_once(api_client, feed):
    early, late = await _posting(feed, "early"), await _posting(feed, "late")
    since = await _start(api_client)
    naive_after = max(await _naive_read(feed, 0), default=0)

    slow = _factory(feed)()
    try:
        # The slow writer takes the lower id and a transaction id first, and stays open.
        held = JobLifecycleEvent(job_id=early, event_type="opened", detail={})
        slow.add(held)
        await slow.flush()
        quick_id = await _event(feed, late, "opened")
        assert held.id < quick_id

        # A read now: the quick writer's event is committed, but a transaction
        # below it is still open, so the feed holds it back.
        data = (await _page(api_client, since=since))["data"]
        assert data["events"] == [] and data["caught_up"] is True
        since = data["next_since"]
        seen = await _naive_read(feed, naive_after)
        assert seen == [quick_id]
        naive_after = seen[-1]

        await slow.commit()
    finally:
        await slow.close()

    events, since = await _drain(api_client, since=since)
    assert [event["sequence"] for event in events] == [f"job_event:{held.id}", f"job_event:{quick_id}"]
    assert (await _drain(api_client, since=since))[0] == []
    # The naive reader passed the slow writer's id before it committed and never sees it.
    assert await _naive_read(feed, naive_after) == []


async def test_a_writer_that_rolls_back_leaves_no_event_and_does_not_hold_the_feed(api_client, feed):
    job = await _posting(feed, "rolled")
    since = await _start(api_client)
    async with _factory(feed)() as session:
        session.add(JobLifecycleEvent(job_id=job, event_type="opened", detail={}))
        await session.flush()
        await session.rollback()
    kept = await _event(feed, job, "closed")
    events, _ = await _drain(api_client, since=since)
    assert [event["sequence"] for event in events] == [f"job_event:{kept}"]


async def test_a_page_the_budget_shortens_continues_with_no_event_lost_or_repeated(api_client, feed):
    job = await _posting(feed, "busy")
    since = await _start(api_client)
    written = [await _event(feed, job, "closed" if i % 2 else "reopened", {"note": "n" * 40}) for i in range(60)]

    status, body = await _get(api_client, since=since, limit=100, tier="small")
    assert status == 200
    data = body["data"]
    assert 0 < data["count"] < 60 and data["caught_up"] is False
    assert [w["code"] for w in body["warnings"]] == ["page_shortened"]
    assert len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()) <= 4_100

    events, _ = await _drain(api_client, since=since, limit=100, tier="small")
    assert [event["sequence"] for event in events] == [f"job_event:{i}" for i in written]


async def test_a_full_page_with_more_waiting_continues_and_says_so(api_client, feed):
    job = await _posting(feed, "three")
    since = await _start(api_client)
    for _ in range(3):
        await _event(feed, job, "closed")
    status, body = await _get(api_client, since=since, limit=2)
    assert body["data"]["count"] == 2 and body["data"]["caught_up"] is False
    assert body["warnings"] == []
    [action] = body["data"]["continue_with"]
    rest = (await _page(api_client, **action["arguments"]))["data"]
    assert rest["count"] == 1 and rest["caught_up"] is True


# --------------------------------------------------------------------------- #
# Where a read starts
# --------------------------------------------------------------------------- #


async def test_start_time_skips_what_was_recorded_before_it(api_client, feed):
    job = await _posting(feed, "timed")
    before = await _event(feed, job, "opened")
    async with _factory(feed)() as session:
        cut = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
    after = await _event(feed, job, "closed")
    events, _ = await _drain(api_client, start_time=cut.isoformat())
    assert [event["sequence"] for event in events] == [f"job_event:{after}"]
    assert before < after


async def test_rows_from_before_the_feed_or_another_cluster_come_first_and_only_from_the_start(api_client, feed):
    job = await _posting(feed, "old")
    unpositioned = await _event(feed, job, "opened")
    restored = await _event(feed, job, "closed")
    async with _factory(feed)() as session:
        await session.execute(update(JobLifecycleEvent).where(JobLifecycleEvent.id == unpositioned)
                              .values(change_xact=None, change_cluster=None))
        # A row restored from another cluster: its transaction id is far past this cluster's.
        await session.execute(text(
            "UPDATE job_lifecycle_events SET change_xact = '9000000000'::xid8, change_cluster = 42 WHERE id = :id"
        ), {"id": restored})
        await session.commit()
    current = await _event(feed, job, "reopened")

    events, since = await _drain(api_client, limit=1)
    assert [event["sequence"] for event in events] == [
        f"job_event:{unpositioned}", f"job_event:{restored}", f"job_event:{current}",
    ]
    later = await _event(feed, job, "closed")
    assert [event["sequence"] for event in (await _drain(api_client, since=since))[0]] == [f"job_event:{later}"]


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def _rewrite(token: str, **changes: Any) -> str:
    body = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    body.update(changes)
    return base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")


async def _refused(api_client, reason: str, **params) -> dict:
    status, body = await _get(api_client, **params)
    assert body["ok"] is False and body["error"]["code"] == "invalid_input", body
    assert status == outcome("invalid_input").http_status
    assert body["error"]["details"] == {"field": "since", "reason": reason}
    [hint] = body["error"]["next_actions"]
    assert hint["operation"] == CHANGES_LIST.id
    return hint["arguments"]


async def test_every_kind_named_continues_a_read_that_named_none(api_client, feed):
    """The same selection, left out or written out in any order, is one set of filters."""
    since = await _start(api_client)
    for kinds in (list(KINDS), list(reversed(KINDS))):
        assert (await _page(api_client, since=since, kinds=kinds))["data"]["caught_up"] is True
    named = await _start(api_client, kinds=list(reversed(KINDS)))
    assert (await _page(api_client, since=named))["data"]["caught_up"] is True


async def test_a_since_that_cannot_continue_is_refused_with_a_lookup_never_reset(api_client, feed):
    job = await _posting(feed, "refusals")
    since = await _start(api_client)
    await _event(feed, job, "opened")

    assert await _refused(api_client, "malformed", since="not-a-position") == {}
    assert await _refused(api_client, "other_filters", since=since, kinds=["closed"]) != {}
    # The cluster that gave it is gone: a restore into a new one.
    hint = await _refused(api_client, "expired", since=_rewrite(since, c="1"))
    assert datetime.fromisoformat(hint["start_time"]) <= datetime.now(UTC)
    assert await _refused(api_client, "malformed", since=_rewrite(since, lo=10**15)) == {}
    # A window that ends past the snapshot, or before it starts, is not one a read gave.
    lo = json.loads(base64.urlsafe_b64decode(since + "=" * (-len(since) % 4)))["lo"]
    assert await _refused(api_client, "malformed", since=_rewrite(since, hi=10**15, th=0)) == {}
    assert await _refused(api_client, "malformed", since=_rewrite(since, hi=lo - 1, th=0)) == {}

    async with _factory(feed)() as session:
        await session.execute(update(WorkspaceIdentity).values(workspace_id="ws_" + "0" * 32))
        await session.commit()
    assert await _refused(api_client, "other_workspace", since=since) == {}


async def test_a_since_given_to_one_assistant_is_refused_to_another(feed):
    async with _factory(feed)() as session:
        workspace = await ensure_workspace_id(session)
        given = await changes_page(session, ChangesListInput(), workspace_id=workspace, principal_id="agent")
        with pytest.raises(Exception) as refused:
            await changes_page(
                session, ChangesListInput(since=given.page.next_since), workspace_id=workspace,
                principal_id="assistant_two",
            )
    assert getattr(refused.value, "details", None) == {"field": "since", "reason": "other_principal"}


async def test_since_and_start_time_together_are_an_input_error(api_client, feed):
    since = await _start(api_client)
    status, body = await _get(api_client, since=since, start_time=T.isoformat())
    assert body["error"]["code"] == "invalid_input" and status == 422


async def test_every_kind_is_either_known_or_named_unavailable():
    from tracker.agents.operations.changes import KIND_BASIS, UNAVAILABLE

    assert set(KIND_BASIS) | set(UNAVAILABLE) == set(KINDS)
    assert not set(KIND_BASIS) & set(UNAVAILABLE)


async def test_a_session_list_read_earlier_in_the_same_transaction_does_not_hide_a_writer(feed):
    """Postgres keeps the session listing it read for the rest of a transaction.
    A read whose transaction looked at it before a writer began must still
    see that writer open."""
    early, late = await _posting(feed, "cached-early"), await _posting(feed, "cached-late")
    async with _factory(feed)() as reader:
        workspace = await ensure_workspace_id(reader)
        since = (await changes_page(reader, ChangesListInput(), workspace_id=workspace,
                                    principal_id=LEGACY_AGENT_PRINCIPAL)).page.next_since
        await reader.commit()
        await reader.execute(text("SELECT count(*) FROM pg_stat_activity"))
        slow = _factory(feed)()
        try:
            held = JobLifecycleEvent(job_id=early, event_type="opened", detail={})
            slow.add(held)
            await slow.flush()
            quick = await _event(feed, late, "opened")
            page = (await changes_page(reader, ChangesListInput(since=since), workspace_id=workspace,
                                       principal_id=LEGACY_AGENT_PRINCIPAL)).page
            assert page.events == []
            await slow.commit()
        finally:
            await slow.close()
        await reader.commit()
        rest = (await changes_page(reader, ChangesListInput(since=page.next_since), workspace_id=workspace,
                                   principal_id=LEGACY_AGENT_PRINCIPAL)).page
    assert [event.sequence for event in rest.events] == [f"job_event:{held.id}", f"job_event:{quick}"]


async def test_a_filtered_read_follows_its_own_continue_with_page_by_page(api_client, feed):
    job = await _posting(feed, "filtered")
    since = await _start(api_client, kinds=["closed"])
    closings = []
    for _ in range(3):
        closings.append(await _event(feed, job, "closed"))
        await _event(feed, job, "reopened")
    events, _ = await _drain(api_client, since=since, kinds=["closed"], limit=1)
    assert [event["sequence"] for event in events] == [f"job_event:{i}" for i in closings]


async def test_start_time_still_bounds_a_row_whose_transaction_commits_after_the_first_window(api_client, feed):
    job = await _posting(feed, "late-but-old")
    slow = _factory(feed)()
    try:
        # The transaction's time is when it began, before the read's start_time.
        held = JobLifecycleEvent(job_id=job, event_type="opened", detail={})
        slow.add(held)
        await slow.flush()
        async with _factory(feed)() as session:
            cut = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
        after = await _event(feed, job, "closed")
        first, since = await _drain(api_client, start_time=cut.isoformat())
        assert first == []
        await slow.commit()
    finally:
        await slow.close()
    events, _ = await _drain(api_client, since=since)
    assert [event["sequence"] for event in events] == [f"job_event:{after}"]


async def test_a_position_with_a_time_no_datetime_can_hold_is_refused_as_malformed(api_client, feed):
    since = await _start(api_client)
    for forged in (_rewrite(since, tl=10**30), _rewrite(since, st=-(10**30)), _rewrite(since, a=[2, 10**30, 2, 1]),
                   _rewrite(since, hi=5, th=10**30, a=[1, -1, 0, 1])):
        assert await _refused(api_client, "malformed", since=forged) == {}


async def test_a_window_never_opens_below_where_its_position_starts(api_client, feed):
    """The frontier a read finds can be lower than the position it continues
    (a role that cannot see every session reads the cluster's), and a window
    that moved back would answer its rows again."""
    job = await _posting(feed, "behind")
    slow = _factory(feed)()
    try:
        slow.add(JobLifecycleEvent(job_id=job, event_type="opened", detail={}))
        await slow.flush()
        # A later commit moves the snapshot's end past the open transaction,
        # so the frontier (that transaction) is below the position's start.
        await _event(feed, job, "closed")
        async with _factory(feed)() as session:
            xmax = int((await session.execute(text("SELECT pg_snapshot_xmax(pg_current_snapshot())"))).scalar_one())
        since = _rewrite(await _start(api_client), lo=xmax)
        data = (await _page(api_client, since=since))["data"]
        assert data["events"] == [] and data["caught_up"] is True
        following = json.loads(base64.urlsafe_b64decode(data["next_since"] + "=" * (-len(data["next_since"]) % 4)))
        assert following["lo"] == xmax
        await slow.commit()
    finally:
        await slow.close()

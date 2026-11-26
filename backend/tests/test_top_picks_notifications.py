"""Top picks in the feed and on the desktop: a pick rings once, a stall rings once
per episode, and the daily digest is quiet while the mode is on.

Real Postgres and the real agent routes: a pick rings in the `picks.decide`
write that saved it, so the replay, the trial and the transaction are the
engine's own. Banners are recorded by the `desktop_banners` fixture, posted
only once their write commits.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from tests import test_agent_picks_db as engine
from tests.test_agent_picks_db import _begin, _data, _decide, _fresh, _key, _pick, _write
from tests.test_notification_store import NOW, TODAY, _event, _job, _run
from tracker.db.models import Favorite, Job, Notification, PickRun
from tracker.notifications import (
    generate_daily_digest,
    generate_notifications,
    reconcile_picks_stalled,
)
from tracker.notifications.desktop import post_after_commit
from tracker.notifications.top_picks import stall_of
from tracker.picks import background as background_store
from tracker.picks.health import LATE_AFTER
from tracker.platform.local_zone import local_zone
from tracker.settings_store import update_top_picks_settings

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

#: The engine tests' workspace: two followed companies, four open roles (one
#: ruled out by the brief's pay floor), an active brief, and the mode on for
#: three days.
workspace = engine.workspace


async def _rows(db_session, category: str) -> list[Notification]:
    async with _fresh(db_session) as session:
        return list((await session.scalars(
            select(Notification).where(Notification.category == category).order_by(Notification.id)
        )).all())


def _two_picks_and_a_pass(jobs: dict[str, int]) -> list[dict]:
    """Staff and Principal picked, Lead passed, in that order."""
    return [
        _pick(jobs["staff"]),
        _pick(jobs["principal"]),
        {"job": jobs["lead"], "verdict": "pass", "pass_code": "not_better"},
    ]


# --------------------------------------------------------------------------- #
# A pick
# --------------------------------------------------------------------------- #


async def test_each_pick_rings_once_and_its_call_posts_one_banner_naming_the_first(
    api_client, db_session, workspace, desktop_banners,
):
    jobs = workspace["jobs"]
    run = await _begin(api_client)

    decided = _data(*await _decide(api_client, run, _two_picks_and_a_pass(jobs)))

    assert decided["picks"] == 2
    rows = await _rows(db_session, "top_pick")
    # One row per picked posting, opened by it; the pass rings nothing.
    assert sorted(row.job_id for row in rows) == sorted([jobs["staff"], jobs["principal"]])
    assert {(row.source_type, row.source_id) for row in rows} == {("pick", jobs["staff"]), ("pick", jobs["principal"])}
    staff = next(row for row in rows if row.job_id == jobs["staff"])
    assert (staff.title, staff.body, staff.priority) == ("New top pick at Google", "Staff Product Manager, Pricing", "high")
    assert staff.meta["say"]["title"] == {"k": "notif-top-pick", "p": {"company": "Google"}}
    # One banner for the call, not one per pick: the count, and the first pick by name.
    assert desktop_banners == [("2 new top picks", "Staff Product Manager, Pricing at Google")]


async def test_a_replay_rings_nothing_and_a_posting_picked_again_keeps_its_one_notification(
    api_client, db_session, workspace, desktop_banners,
):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    key = _key()
    await _decide(api_client, run, [_pick(jobs["staff"])], key=key)
    assert desktop_banners == [("New top pick", "Staff Product Manager, Pricing at Google")]

    # The same call again under its key: the receipt answers, and nothing runs.
    response, body = await _decide(api_client, run, [_pick(jobs["staff"])], key=key)
    assert body["meta"]["replayed"] is True, body
    # Under a new key it is a case already judged, refused and saved nowhere.
    again = _data(*await _decide(api_client, run, [_pick(jobs["staff"])]))
    assert again["results"][0]["refusal"] == "already_judged"
    assert len(await _rows(db_session, "top_pick")) == 1
    assert len(desktop_banners) == 1

    # The posting's text changes, it is judged afresh and picked again: still
    # one notification for the posting, and no banner for a pick it already had.
    async with _fresh(db_session) as session:
        await session.execute(update(Job).where(Job.id == jobs["staff"]).values(content_hash="h-staff-2"))
        await session.commit()
    second = await _begin(api_client)
    assert jobs["staff"] in {posting["job"] for posting in second["batch"]}
    repicked = _data(*await _decide(api_client, second, [_pick(jobs["staff"]), _pick(jobs["principal"])]))
    assert repicked["picks"] == 2
    rows = await _rows(db_session, "top_pick")
    assert sorted(row.job_id for row in rows) == sorted([jobs["staff"], jobs["principal"]])
    # The second call's banner counts only what was new: Principal.
    assert desktop_banners[1:] == [("New top pick", "Principal Product Manager, Risk at Stripe")]


async def test_a_trials_picks_ring_nothing_and_the_routines_pick_of_the_same_role_does(
    api_client, db_session, workspace, desktop_banners,
):
    jobs = workspace["jobs"]
    trial = await _begin(api_client, trial=True)
    saved = _data(*await _decide(api_client, trial, [_pick(jobs["staff"])]))
    assert saved["picks"] == 1

    assert await _rows(db_session, "top_pick") == []
    assert desktop_banners == []

    routine = await _begin(api_client)
    _data(*await _decide(api_client, routine, [_pick(jobs["staff"])]))
    assert [row.job_id for row in await _rows(db_session, "top_pick")] == [jobs["staff"]]
    assert len(desktop_banners) == 1


async def test_a_pick_on_a_role_the_person_already_marked_not_for_me_rings_nothing(
    api_client, db_session, workspace, desktop_banners,
):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    # Marked Not for me on the Radar while the run was reading.
    response = await api_client.put(f"/api/jobs/{jobs['staff']}/feedback", json={"verdict": "dismissed"})
    assert response.status_code == 200, response.text

    _data(*await _decide(api_client, run, [_pick(jobs["staff"]), _pick(jobs["principal"])]))

    assert [row.job_id for row in await _rows(db_session, "top_pick")] == [jobs["principal"]]
    assert desktop_banners == [("New top pick", "Principal Product Manager, Risk at Stripe")]


# --------------------------------------------------------------------------- #
# A stall
# --------------------------------------------------------------------------- #


async def _routine_run(
    session: AsyncSession, *, began: datetime, ended: datetime | None, outcome: str | None, note: str | None = None,
) -> None:
    run_id = f"run_{int(began.timestamp() * 1000):x}"[:24]
    session.add(PickRun(
        id=run_id, host="claude-code", trial=False, brief_version=1, started_at=began, finished_at=ended,
        outcome=outcome, note=note, queue=[], counts={},
    ))
    await session.commit()


async def _reconcile(db_session, now: datetime) -> None:
    async with _fresh(db_session) as session:
        await reconcile_picks_stalled(session, now=now)
        await session.commit()


async def test_a_stall_rings_once_while_it_lasts_and_again_after_the_checks_caught_up(
    db_session, workspace, desktop_banners,
):
    """The roles were first seen five hours before `now` and the mode has been
    on for three days; no check has finished."""
    start = workspace["now"]

    # Right after setup no check has finished, which is not yet a stall.
    await _reconcile(db_session, start + timedelta(hours=1))
    assert await _rows(db_session, "picks_stalled") == []

    # A day and a half on, the roles have waited too long: one row, one banner.
    await _reconcile(db_session, start + timedelta(days=2))
    [first] = await _rows(db_session, "picks_stalled")
    assert (first.title, first.body) == ("No top picks check has run yet", "3 roles are waiting to be read.")
    assert desktop_banners == [("No top picks check has run yet", "3 roles are waiting to be read.")]

    # Every later check while it lasts refreshes the row in place, read state
    # kept, and rings nothing.
    async with _fresh(db_session) as session:
        await session.execute(update(Notification).where(Notification.id == first.id).values(read_at=start))
        await session.commit()
    await _reconcile(db_session, start + timedelta(days=2, hours=6))
    await _reconcile(db_session, start + timedelta(days=2, hours=12))
    [same] = await _rows(db_session, "picks_stalled")
    assert (same.id, same.created_at, same.read_at) == (first.id, first.created_at, start)
    assert len(desktop_banners) == 1

    # A check finishes: the stall is over and its row goes.
    caught_up = start + timedelta(days=2, hours=13)
    async with _fresh(db_session) as session:
        await _routine_run(session, began=caught_up - timedelta(minutes=20), ended=caught_up, outcome="finished")
    await _reconcile(db_session, caught_up)
    assert await _rows(db_session, "picks_stalled") == []

    # The roles still wait and no check comes for a day and a half: a new
    # stall, a new unread row and a new banner.
    await _reconcile(db_session, caught_up + LATE_AFTER + timedelta(hours=1))
    [late] = await _rows(db_session, "picks_stalled")
    assert late.read_at is None and late.id != first.id
    day = caught_up.astimezone(local_zone()).date()
    assert (late.title, late.body) == (
        "Top picks checks are late",
        f"The last check finished on {day.day} {day:%b}. 3 roles are waiting to be read.",
    )
    assert desktop_banners[1:] == [("Top picks checks are late", "3 roles are waiting to be read.")]


async def test_a_check_that_stopped_early_rings_but_one_from_before_a_pause_does_not_after_resuming(
    db_session, workspace, desktop_banners,
):
    start = workspace["now"]
    async with _fresh(db_session) as session:
        await _routine_run(
            session, began=start - timedelta(hours=2), ended=start - timedelta(hours=1), outcome="stopped",
            note="The usage limit was reached.",
        )
    await _reconcile(db_session, start)
    [stopped] = await _rows(db_session, "picks_stalled")
    assert stopped.title == "The last top picks check stopped early"
    # The run's note is the assistant's words about the person: not repeated here.
    assert "usage limit" not in f"{stopped.title} {stopped.body} {stopped.meta}"
    assert desktop_banners == [("A top picks check stopped early", "3 roles are waiting to be read.")]

    # Paused: the checks are not expected, so the row goes.
    async with _fresh(db_session) as session:
        await update_top_picks_settings(session, state="off")
        await session.commit()
    await _reconcile(db_session, start + timedelta(minutes=5))
    assert await _rows(db_session, "picks_stalled") == []

    # Resumed: the run that stopped before the pause says nothing about the
    # checks since, so nothing rings until a check after the resume stops.
    resumed = start + timedelta(minutes=10)
    async with _fresh(db_session) as session:
        await update_top_picks_settings(session, state="on", enabled_at=resumed)
        await session.commit()
    await _reconcile(db_session, resumed + timedelta(minutes=5))
    assert await _rows(db_session, "picks_stalled") == []
    async with _fresh(db_session) as session:
        await _routine_run(
            session, began=resumed + timedelta(minutes=20), ended=resumed + timedelta(minutes=30), outcome="stopped",
            note="Stopped.",
        )
    await _reconcile(db_session, resumed + timedelta(minutes=40))
    assert len(await _rows(db_session, "picks_stalled")) == 1
    assert len(desktop_banners) == 2


async def test_finishing_a_run_says_at_once_that_it_stopped_early(api_client, db_session, workspace, desktop_banners):
    run = await _begin(api_client)

    _data(*await _write(api_client, "POST", "/picks/runs/finish",
                        {"run": run["run"], "outcome": "stopped", "note": "The usage limit was reached."}))

    [row] = await _rows(db_session, "picks_stalled")
    assert row.meta["health"] == "stopped_early" and row.meta["waiting"] == 3
    assert desktop_banners == [("A top picks check stopped early", "3 roles are waiting to be read.")]

    # The next run judges what waited and finishes: the stall is over at once.
    again = await _begin(api_client)
    _data(*await _decide(api_client, again, [
        {"job": posting["job"], "verdict": "pass", "pass_code": "not_better"} for posting in again["batch"]
    ]))
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": again["run"], "outcome": "finished"}))
    assert await _rows(db_session, "picks_stalled") == []


async def test_pausing_or_removing_top_picks_takes_a_stalls_row_away_at_once(
    api_client, db_session, workspace, desktop_banners, tmp_path, monkeypatch,
):
    """Through the assistant or in the app, with no scan in between."""
    # Remove empties the documents folder: this test's own, not the machine's.
    monkeypatch.setattr(background_store, "documents_dir", lambda: tmp_path)

    async def a_check_stops() -> None:
        run = await _begin(api_client)
        _data(*await _write(api_client, "POST", "/picks/runs/finish",
                            {"run": run["run"], "outcome": "stopped", "note": "Stopped."}))
        assert len(await _rows(db_session, "picks_stalled")) == 1

    await a_check_stops()
    _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "off"}))
    assert await _rows(db_session, "picks_stalled") == []
    # Resumed: the stop from before the pause rings nothing.
    _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "on"}))
    assert await _rows(db_session, "picks_stalled") == []

    await a_check_stops()
    paused = await api_client.put("/api/picks/mode", json={"state": "off"})
    assert paused.status_code == 200, paused.text
    assert await _rows(db_session, "picks_stalled") == []
    resumed = await api_client.put("/api/picks/mode", json={"state": "on"})
    assert resumed.status_code == 200, resumed.text
    assert await _rows(db_session, "picks_stalled") == []

    await a_check_stops()
    removed = await api_client.delete("/api/picks/setup")
    assert removed.status_code == 200, removed.text
    assert await _rows(db_session, "picks_stalled") == []
    # One banner per stall, none for a switch.
    assert len(desktop_banners) == 3


async def test_a_scan_is_the_heartbeat_that_notices_a_stall(db_session, workspace, desktop_banners):
    async with _fresh(db_session) as session:
        run = await _run(session)
        await generate_notifications(session, run, include_run=False)
        await session.commit()
    # The roles have waited five hours: not a stall yet.
    assert await _rows(db_session, "picks_stalled") == []

    # They have waited since the mode was turned on, three days ago, and no check came.
    async with _fresh(db_session) as session:
        await session.execute(
            update(Job).where(Job.id.in_(workspace["jobs"].values()))
            .values(first_seen=workspace["now"] - timedelta(days=4))
        )
        run = await _run(session)
        await generate_notifications(session, run, include_run=False)
        await session.commit()
    assert [row.title for row in await _rows(db_session, "picks_stalled")] == ["No top picks check has run yet"]
    assert len(desktop_banners) == 1


@pytest.mark.parametrize(
    ("health", "waiting", "waited", "began_after_on", "stalled"),
    [
        ("late", 4, LATE_AFTER + timedelta(hours=1), True, True),
        ("late", 0, LATE_AFTER + timedelta(hours=1), True, False),
        ("never_ran", 4, LATE_AFTER + timedelta(minutes=1), True, True),
        ("never_ran", 4, LATE_AFTER - timedelta(minutes=1), True, False),
        ("stopped_early", 4, timedelta(hours=1), True, True),
        ("stopped_early", 4, timedelta(hours=1), False, False),
        ("stopped_early", 0, timedelta(hours=1), True, False),
        ("healthy", 4, LATE_AFTER * 3, True, False),
        ("off", 4, LATE_AFTER * 3, True, False),
    ],
)
async def test_a_stall_is_a_health_that_leaves_roles_waiting_on_checks_that_should_have_run(
    health, waiting, waited, began_after_on, stalled,
):
    now = datetime(2026, 11, 26, 12, tzinfo=UTC)
    enabled_at = now - timedelta(days=10)
    began = enabled_at + timedelta(hours=1) if began_after_on else enabled_at - timedelta(hours=1)
    assert stall_of(
        health, waiting=waiting, oldest_waiting_since=now - waited, enabled_at=enabled_at,
        ended_early_run_began_at=began, now=now,
    ) is stalled


# --------------------------------------------------------------------------- #
# A banner waits for its commit
# --------------------------------------------------------------------------- #


async def test_a_banner_is_posted_only_once_its_transaction_commits(db_session, desktop_banners):
    async with _fresh(db_session) as session:
        await session.execute(text("SELECT 1"))
        post_after_commit(session, "rolled back", "never shown")
        await session.rollback()

        await session.execute(text("SELECT 1"))
        post_after_commit(session, "kept", "shown")
        async with session.begin_nested():
            post_after_commit(session, "kept inside", "shown")
        with pytest.raises(RuntimeError):
            async with session.begin_nested():
                post_after_commit(session, "savepoint rolled back", "never shown")
                raise RuntimeError
        assert desktop_banners == []
        await session.commit()

        await session.execute(text("SELECT 1"))
        post_after_commit(session, "next transaction", "shown")
        await session.commit()

    assert desktop_banners == [("kept", "shown"), ("kept inside", "shown"), ("next transaction", "shown")]


# --------------------------------------------------------------------------- #
# The daily digest
# --------------------------------------------------------------------------- #


async def test_no_daily_digest_is_written_while_top_picks_is_on_and_saved_roles_still_ring(db_session):
    run = await _run(db_session)
    new_role = await _job(db_session, company="stripe", title="Head of Product")
    await _event(db_session, run, new_role, "opened")
    saved = await _job(db_session, title="Saved PM")
    db_session.add(Favorite(job_id=saved.id))
    await db_session.flush()
    await _event(db_session, run, saved, "closed")
    await update_top_picks_settings(db_session, state="on", enabled_at=NOW)

    await generate_notifications(db_session, run, include_run=False)

    categories = [row.category for row in (await db_session.scalars(select(Notification))).all()]
    assert "daily_digest" not in categories
    assert "closed" in categories
    assert await generate_daily_digest(db_session, set(), day=TODAY) == 0

    # Paused, the digest is written again.
    await update_top_picks_settings(db_session, state="off")
    assert await generate_daily_digest(db_session, set(), day=TODAY) == 1
    digest = await db_session.scalar(select(Notification).where(Notification.category == "daily_digest"))
    assert digest is not None and digest.meta["count"] == 1

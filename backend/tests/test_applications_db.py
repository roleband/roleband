"""The application pipeline through its real routes, on real Postgres.

A star is a card at Considering with no pursuit row behind it; past
Considering the star cannot be taken away; comments and interviews hang off
the pursuit and are reached only through their own role's routes; the feed
runs newest first and pages backwards.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest
from sqlalchemy import delete, insert, select

from tracker.agents import pursuits as store
from tracker.agents.operations import pursuits as agent_pursuits
from tracker.api.schemas import applications as contract
from tracker.db.models import (
    OWES_NOTHING,
    Favorite,
    Job,
    Pursuit,
    PursuitComment,
    PursuitEvent,
    PursuitInterview,
)

pytestmark = pytest.mark.asyncio


async def _job(db_session, req: str = "r1") -> Job:
    now = datetime.now(UTC)
    job = Job(
        company="openai", req_id=req, dedupe_key=f"openai:{req}", title=f"Staff PM {req}",
        url=f"https://careers.example.test/{req}", level_band="staff", status="open",
        first_seen=now - timedelta(days=5), last_seen=now, in_scope=True,
    )
    db_session.add(job)
    await db_session.commit()
    return job


async def _board(api_client) -> dict[int, dict]:
    response = await api_client.get("/api/applications")
    assert response.status_code == 200, response.text
    return {card["job_id"]: card for card in response.json()["applications"]}


async def _move(api_client, job_id: int, stage: str, **fields) -> None:
    response = await api_client.put(f"/api/jobs/{job_id}/pursuit", json={"stage": stage, **fields})
    assert response.status_code == 200, response.text


async def _comment(api_client, job_id: int, body: str) -> dict:
    response = await api_client.post(f"/api/jobs/{job_id}/pursuit/comments", json={"body": body})
    assert response.status_code == 200, response.text
    return response.json()["comment"]


def _iso(moment: datetime) -> str:
    return moment.isoformat()


# --- the board -------------------------------------------------------------------


async def test_a_star_alone_is_a_considering_card_with_no_pursuit(api_client, db_session):
    starred, plain = await _job(db_session, "r1"), await _job(db_session, "r2")
    assert (await api_client.put(f"/api/jobs/{starred.id}/favorite")).status_code == 200

    board = await _board(api_client)

    assert set(board) == {starred.id}
    card = board[starred.id]
    assert card["stage"] == "saved" and card["pursuit_id"] is None and card["starred"] is True
    assert card["priority"] == 3 and card["comment_count"] == 0 and card["stage_since"] is not None
    assert plain.id not in board


async def test_unstarring_at_considering_takes_the_card_off_and_restarring_brings_its_notes_back(
    api_client, db_session
):
    job = await _job(db_session)
    await api_client.put(f"/api/jobs/{job.id}/favorite")
    await _comment(api_client, job.id, "Read their blog post")

    assert (await api_client.delete(f"/api/jobs/{job.id}/favorite")).status_code == 200
    assert job.id not in await _board(api_client)

    await api_client.put(f"/api/jobs/{job.id}/favorite")
    assert (await _board(api_client))[job.id]["comment_count"] == 1


async def test_the_star_stays_on_a_role_past_considering(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "applied")

    response = await api_client.delete(f"/api/jobs/{job.id}/favorite")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "application-under-way"
    assert response.json()["detail"]["params"] == {"stage": "applied"}
    assert await db_session.scalar(select(Favorite.id).where(Favorite.job_id == job.id)) is not None


async def test_a_role_past_considering_with_no_star_stays_on_the_board(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "interviewing")
    # A star removed before the rule existed, or by hand.
    await db_session.execute(delete(Favorite).where(Favorite.job_id == job.id))
    await db_session.commit()

    card = (await _board(api_client))[job.id]

    assert card["stage"] == "interviewing" and card["starred"] is False


async def test_stage_since_moves_with_the_stage_and_not_with_other_writes(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "applied")
    pursuit_id = await db_session.scalar(select(Pursuit.id).where(Pursuit.job_id == job.id))
    moved_at = datetime.now(UTC) - timedelta(days=4)
    await db_session.execute(
        PursuitEvent.__table__.update()
        .where(PursuitEvent.pursuit_id == pursuit_id)
        .values(created_at=moved_at)
    )
    await db_session.commit()

    response = await api_client.put(f"/api/jobs/{job.id}/pursuit", json={"notes": "Recruiter is Sam"})
    assert response.status_code == 200, response.text
    card = (await _board(api_client))[job.id]

    assert datetime.fromisoformat(card["stage_since"]) == moved_at
    assert datetime.fromisoformat(card["last_activity_at"]) > moved_at


@pytest.mark.parametrize("ending", ["withdrawn", "rejected", "role_closed", "accepted", "declined"])
async def test_an_ended_card_says_the_stage_it_ended_from(api_client, db_session, ending):
    job = await _job(db_session)
    await _move(api_client, job.id, "interviewing")
    await api_client.put(f"/api/jobs/{job.id}/pursuit", json={"priority": 5})
    await _move(api_client, job.id, ending)

    card = (await _board(api_client))[job.id]

    assert card["stage"] == ending and card["ended_at_stage"] == "interviewing"


async def test_an_ending_changed_to_another_ending_keeps_the_stage_it_ended_from(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "offer")
    await _move(api_client, job.id, "declined")
    await _move(api_client, job.id, "accepted")

    card = (await _board(api_client))[job.id]

    assert card["stage"] == "accepted" and card["ended_at_stage"] == "offer"


async def test_a_reopened_application_that_ends_again_names_the_stage_it_left_last(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "applied")
    await _move(api_client, job.id, "rejected")
    await _move(api_client, job.id, "interviewing")
    await _move(api_client, job.id, "withdrawn")

    assert (await _board(api_client))[job.id]["ended_at_stage"] == "interviewing"


async def test_a_moving_card_names_no_ending(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "researching")
    await _move(api_client, job.id, "applied")

    assert (await _board(api_client))[job.id]["ended_at_stage"] is None


async def test_the_next_interview_is_the_soonest_round_still_waiting_for_its_outcome(
    api_client, db_session
):
    job = await _job(db_session)
    now = datetime.now(UTC)
    rounds = [
        ("Ran last week", now - timedelta(days=7), None),
        ("Ran this morning, passed", now - timedelta(hours=3), "passed"),
        ("Technical round", now + timedelta(days=9), None),
        ("Hiring manager", now + timedelta(days=2), None),
    ]
    for label, at, outcome in rounds:
        response = await api_client.post(
            f"/api/jobs/{job.id}/pursuit/interviews",
            json={"label": label, "scheduled_at": _iso(at), "outcome": outcome, "format": "video"},
        )
        assert response.status_code == 200, response.text

    card = (await _board(api_client))[job.id]

    assert card["next_interview"]["label"] == "Hiring manager"
    assert card["next_interview"]["format"] == "video"


async def test_a_round_that_ran_this_morning_without_an_outcome_is_still_next(api_client, db_session):
    job = await _job(db_session)
    await api_client.post(
        f"/api/jobs/{job.id}/pursuit/interviews",
        json={"label": "Screen", "scheduled_at": _iso(datetime.now(UTC) - timedelta(hours=3))},
    )

    assert (await _board(api_client))[job.id]["next_interview"]["label"] == "Screen"


async def test_an_all_day_round_is_next_through_its_whole_day(api_client, db_session):
    # Stored at its day's local midnight: fourteen hours on, it is that day's
    # afternoon, past a timed round's grace.
    started = datetime.now(UTC) - timedelta(hours=14)
    all_day = await _job(db_session)
    await _interview(api_client, all_day.id, "On site", started, all_day=True)
    timed = await _job(db_session, "r2")
    await _interview(api_client, timed.id, "Screen", started)
    over = await _job(db_session, "r3")
    await _interview(api_client, over.id, "Yesterday", started - timedelta(hours=11), all_day=True)

    board = await _board(api_client)

    assert board[all_day.id]["next_interview"]["label"] == "On site"
    assert board[timed.id]["next_interview"] is None
    assert board[over.id]["next_interview"] is None


async def test_the_round_awaiting_its_outcome_is_the_latest_one_that_took_place_without_one(
    api_client, db_session
):
    job = await _job(db_session)
    now = datetime.now(UTC)
    await _interview(api_client, job.id, "Phone screen", now - timedelta(days=9))
    await _interview(api_client, job.id, "Hiring manager", now - timedelta(days=3))
    await _interview(api_client, job.id, "Ran, passed", now - timedelta(days=2), outcome="passed")
    await _interview(api_client, job.id, "Called off", now - timedelta(days=1), outcome="cancelled")
    await _interview(api_client, job.id, "Technical round", now + timedelta(days=2))
    answered = await _job(db_session, "r2")
    await _interview(api_client, answered.id, "Screen", now - timedelta(days=3), outcome="not_passed")
    await _interview(api_client, answered.id, "Onsite", now + timedelta(days=4))

    board = await _board(api_client)

    assert board[job.id]["awaiting_outcome"]["label"] == "Hiring manager"
    assert board[job.id]["next_interview"]["label"] == "Technical round"
    # Every round that took place has its outcome, and one still to come asks nothing.
    assert board[answered.id]["awaiting_outcome"] is None


async def test_a_round_that_began_awaits_its_outcome_while_it_is_still_next(api_client, db_session):
    job = await _job(db_session)
    await _interview(api_client, job.id, "Screen", datetime.now(UTC) - timedelta(hours=3))

    card = (await _board(api_client))[job.id]

    assert card["next_interview"]["label"] == "Screen"
    assert card["awaiting_outcome"]["label"] == "Screen"


async def test_an_all_day_round_awaits_its_outcome_once_its_day_is_over(api_client, db_session):
    started = datetime.now(UTC) - timedelta(hours=14)
    today = await _job(db_session)
    await _interview(api_client, today.id, "On site", started, all_day=True)
    over = await _job(db_session, "r2")
    await _interview(api_client, over.id, "Yesterday", started - timedelta(hours=11), all_day=True)

    board = await _board(api_client)

    assert board[today.id]["awaiting_outcome"] is None
    assert board[over.id]["awaiting_outcome"]["label"] == "Yesterday"


async def test_a_card_and_the_calendar_carry_the_rounds_link(api_client, db_session):
    job = await _job(db_session)
    now = datetime.now(UTC)
    link = "https://meet.example.test/abc-defg"
    await _interview(api_client, job.id, "Ran", now - timedelta(days=1), link=link)
    await _interview(api_client, job.id, "Hiring manager", now + timedelta(days=1), link=link)
    await _interview(api_client, job.id, "On site", now + timedelta(days=3), format="onsite")

    card = (await _board(api_client))[job.id]
    items = await _calendar(api_client, now - timedelta(days=2), now + timedelta(days=4))

    assert card["next_interview"]["link"] == link
    assert card["awaiting_outcome"]["link"] == link
    assert [(i["label"], i["link"]) for i in items] == [("Ran", link), ("Hiring manager", link), ("On site", None)]


async def test_the_agents_pursuit_reads_name_the_rounds_the_card_does(api_client, db_session):
    job = await _job(db_session)
    quiet = await _job(db_session, "r2")
    now = datetime.now(UTC)
    link = "https://meet.example.test/abc-defg"
    await _move(api_client, job.id, "interviewing")
    await _move(api_client, quiet.id, "applied")
    await _interview(api_client, job.id, "Hiring manager", now - timedelta(days=2))
    await _interview(api_client, job.id, "Technical round", now + timedelta(days=3), link=link)

    one = await agent_pursuits.pursuit_of(db_session, job.id)
    page, _ = await agent_pursuits.pursuit_page(
        db_session, agent_pursuits.PursuitListInput(), workspace_id="test"
    )
    card = (await _board(api_client))[job.id]

    listed = {item.opportunity_id: item for item in page.items}
    for item in (one, listed[job.id]):
        assert item.next_interview is not None and item.awaiting_outcome is not None
        assert item.next_interview.model_dump(mode="json") == card["next_interview"]
        assert item.awaiting_outcome.model_dump(mode="json") == card["awaiting_outcome"]
        assert item.next_interview.link == link
    assert listed[quiet.id].next_interview is None and listed[quiet.id].awaiting_outcome is None


# --- priority ----------------------------------------------------------------------

async def test_a_role_has_no_priority_until_one_is_chosen(api_client, db_session):
    starred = await _job(db_session)
    pursued = await _job(db_session, "r2")
    db_session.add(Favorite(job_id=starred.id))
    await db_session.commit()
    # Writes that name no priority leave the role without one, at the stored default.
    await _move(api_client, pursued.id, "applied", notes="Sent the form")

    board = await _board(api_client)
    assert board[starred.id]["priority_set"] is False
    assert board[pursued.id]["priority"] == 3 and board[pursued.id]["priority_set"] is False


async def test_choosing_medium_on_a_role_at_the_default_is_a_choice(api_client, db_session):
    job = await _job(db_session)
    other = await _job(db_session, "r2")
    await _move(api_client, job.id, "applied")
    await _move(api_client, other.id, "applied")
    await _move(api_client, job.id, "applied", priority=3)
    # Naming the stage it is already at changes nothing; naming the priority does.
    await _move(api_client, other.id, "applied")

    board = await _board(api_client)
    assert board[job.id]["priority"] == 3 and board[job.id]["priority_set"] is True
    assert board[other.id]["priority_set"] is False
    pursuit = await db_session.scalar(select(Pursuit).where(Pursuit.job_id == job.id))
    events = (await db_session.scalars(
        select(PursuitEvent).where(PursuitEvent.pursuit_id == pursuit.id).order_by(PursuitEvent.id)
    )).all()
    assert [e.detail["changed"] for e in events] == [["stage"], ["priority"]]
    assert events[-1].detail["before"] == {"priority": 3} and events[-1].detail["after"] == {"priority": 3}

    # Chosen once, an unchanged priority is not recorded again.
    await _move(api_client, job.id, "applied", priority=3)
    count = len((await db_session.scalars(select(PursuitEvent).where(PursuitEvent.pursuit_id == pursuit.id))).all())
    assert count == 2


async def test_the_agents_read_the_priority_choice_the_card_does_and_list_the_most_urgent_first(
    api_client, db_session
):
    low = await _job(db_session)
    urgent = await _job(db_session, "r2")
    unset = await _job(db_session, "r3")
    await _move(api_client, low.id, "applied", priority=2)
    await _move(api_client, urgent.id, "applied", priority=5)
    await _move(api_client, unset.id, "applied")

    page, _ = await agent_pursuits.pursuit_page(
        db_session, agent_pursuits.PursuitListInput(), workspace_id="test"
    )
    # As the List sorts them: no priority last, below a chosen Low.
    assert [item.opportunity_id for item in page.items] == [urgent.id, low.id, unset.id]
    assert {item.opportunity_id: item.priority_set for item in page.items} == {urgent.id: True, unset.id: False, low.id: True}
    assert (await agent_pursuits.pursuit_of(db_session, unset.id)).priority_set is False


async def _row(api_client, job_id: int) -> dict:
    response = await api_client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_posting_names_the_stage_its_role_is_at_on_the_board(api_client, db_session):
    starred, applied, unstarred, gone, plain = (
        await _job(db_session, "r1"), await _job(db_session, "r2"), await _job(db_session, "r3"),
        await _job(db_session, "r4"), await _job(db_session, "r5"),
    )
    await api_client.put(f"/api/jobs/{starred.id}/favorite")
    await _move(api_client, applied.id, "applied")
    await _move(api_client, unstarred.id, "interviewing")
    # A star removed before the rule existed, or by hand: still on the board.
    await db_session.execute(delete(Favorite).where(Favorite.job_id == unstarred.id))
    await db_session.commit()
    # A pursuit at Considering whose star was taken away is off the board.
    await api_client.put(f"/api/jobs/{gone.id}/favorite")
    await _comment(api_client, gone.id, "Read their blog post")
    await api_client.delete(f"/api/jobs/{gone.id}/favorite")

    stages = {job.id: (await _row(api_client, job.id))["pipeline_stage"]
              for job in (starred, applied, unstarred, gone, plain)}
    board = await _board(api_client)

    assert stages == {starred.id: "saved", applied.id: "applied", unstarred.id: "interviewing",
                      gone.id: None, plain.id: None}
    # The same roles, at the same stages, as the board.
    assert {job_id: card["stage"] for job_id, card in board.items()} == {
        job_id: stage for job_id, stage in stages.items() if stage is not None
    }


# --- the calendar -----------------------------------------------------------------


async def _interview(api_client, job_id: int, label: str, at: datetime, **fields) -> None:
    response = await api_client.post(
        f"/api/jobs/{job_id}/pursuit/interviews",
        json={"label": label, "scheduled_at": _iso(at), **fields},
    )
    assert response.status_code == 200, response.text


async def _calendar(api_client, start: datetime, end: datetime) -> list[dict]:
    response = await api_client.get(
        "/api/applications/calendar", params={"start": _iso(start), "end": _iso(end)}
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_the_calendar_holds_every_round_in_its_span_soonest_first_with_the_next_step(
    api_client, db_session
):
    job = await _job(db_session)
    now = datetime.now(UTC)
    await _move(api_client, job.id, "interviewing", next_action="Send references",
                next_action_due=_iso(now + timedelta(days=3)))
    await _interview(api_client, job.id, "Ran, passed", now - timedelta(days=2), outcome="passed")
    await _interview(api_client, job.id, "Hiring manager", now + timedelta(days=1))
    await _interview(api_client, job.id, "Onsite", now + timedelta(days=5), format="onsite")
    await _interview(api_client, job.id, "Called off", now + timedelta(days=4), outcome="cancelled")
    await _interview(api_client, job.id, "Past the span", now + timedelta(days=20))

    items = await _calendar(api_client, now - timedelta(days=7), now + timedelta(days=7))

    # Every round the board would not call next is here too: one already run,
    # and the second of two still to come. A cancelled round is not.
    assert [(i["kind"], i.get("label") or i.get("step")) for i in items] == [
        ("interview", "Ran, passed"),
        ("interview", "Hiring manager"),
        ("step", "Send references"),
        ("interview", "Onsite"),
    ]
    assert all(i["job_id"] == job.id for i in items)
    assert items[0]["outcome"] == "passed" and items[3]["format"] == "onsite"


async def test_the_span_includes_its_start_and_stops_before_its_end(api_client, db_session):
    job = await _job(db_session)
    at = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
    await _move(api_client, job.id, "applied")
    await _interview(api_client, job.id, "Screen", at)

    assert [i["label"] for i in await _calendar(api_client, at, at + timedelta(days=1))] == ["Screen"]
    assert await _calendar(api_client, at - timedelta(days=1), at) == []


@pytest.mark.parametrize("ending", ["declined", "withdrawn", "rejected", "role_closed"])
async def test_an_ended_application_keeps_its_rounds_but_owes_no_step(api_client, db_session, ending):
    job = await _job(db_session)
    now = datetime.now(UTC)
    await _move(api_client, job.id, "interviewing", next_action="Chase feedback",
                next_action_due=_iso(now + timedelta(days=1)))
    await _interview(api_client, job.id, "Final round", now - timedelta(days=1), outcome="not_passed")
    await _move(api_client, job.id, ending)

    items = await _calendar(api_client, now - timedelta(days=7), now + timedelta(days=7))

    assert [(i["kind"], i.get("label")) for i in items] == [("interview", "Final round")]


async def test_an_accepted_offer_still_owes_its_step(api_client, db_session):
    job = await _job(db_session)
    now = datetime.now(UTC)
    await _move(api_client, job.id, "accepted", next_action="Sign the contract",
                next_action_due=_iso(now + timedelta(days=2)))

    items = await _calendar(api_client, now, now + timedelta(days=7))

    assert [i.get("step") for i in items] == ["Sign the contract"]


async def test_a_role_off_the_board_has_nothing_on_the_calendar(api_client, db_session):
    job = await _job(db_session)
    now = datetime.now(UTC)
    await api_client.put(f"/api/jobs/{job.id}/favorite")
    await _interview(api_client, job.id, "Coffee chat", now + timedelta(days=1))
    assert len(await _calendar(api_client, now, now + timedelta(days=7))) == 1

    # Unstarred at Considering: off the board, so off the calendar too.
    assert (await api_client.delete(f"/api/jobs/{job.id}/favorite")).status_code == 200

    assert await _calendar(api_client, now, now + timedelta(days=7)) == []


async def test_the_steps_left_off_are_the_ones_the_reminders_stop_for():
    assert OWES_NOTHING == {"declined", "withdrawn", "rejected", "role_closed"}
    assert "offer" not in OWES_NOTHING and "accepted" not in OWES_NOTHING


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-11-09T00:00:00+00:00", "2026-11-09T00:00:00+00:00"),
        ("2026-11-10T00:00:00+00:00", "2026-11-09T00:00:00+00:00"),
        ("2026-11-01T00:00:00+00:00", "2026-12-14T00:00:00+00:00"),
        ("2026-11-01T00:00:00", "2026-11-08T00:00:00"),
        ("next monday", "2026-11-08T00:00:00+00:00"),
    ],
    ids=["empty", "backwards", "longer-than-six-weeks", "no-zone", "not-a-date"],
)
async def test_a_span_that_is_not_one_is_refused(api_client, start, end):
    response = await api_client.get("/api/applications/calendar", params={"start": start, "end": end})

    assert response.status_code == 422, response.text


async def test_six_weeks_is_the_longest_span(api_client):
    start = datetime(2026, 10, 26, tzinfo=UTC)
    response = await api_client.get(
        "/api/applications/calendar",
        params={"start": _iso(start), "end": _iso(start + timedelta(days=42))},
    )

    assert response.status_code == 200, response.text


async def test_six_weeks_across_a_clock_going_back_is_read(api_client):
    # A November grid in New York: 26 October to 7 December, local midnight to
    # local midnight, with daylight saving ending on 1 November inside it.
    response = await api_client.get(
        "/api/applications/calendar",
        params={"start": "2026-10-26T00:00:00-04:00", "end": "2026-12-07T00:00:00-05:00"},
    )

    assert response.status_code == 200, response.text


async def test_a_span_past_six_weeks_and_a_clock_change_is_refused(api_client):
    start = datetime(2026, 10, 26, tzinfo=UTC)
    response = await api_client.get(
        "/api/applications/calendar",
        params={"start": _iso(start), "end": _iso(start + timedelta(days=42, hours=1, seconds=1))},
    )

    assert response.status_code == 422, response.text


# --- comments ---------------------------------------------------------------------


async def test_a_first_comment_on_a_star_gives_it_a_pursuit_at_considering(api_client, db_session):
    job = await _job(db_session)
    await api_client.put(f"/api/jobs/{job.id}/favorite")

    comment = await _comment(api_client, job.id, "Ask about on-call")

    assert comment["actor"] == "user" and comment["edited_at"] is None and comment["kind"] == "comment"
    card = (await _board(api_client))[job.id]
    assert card["pursuit_id"] is not None and card["stage"] == "saved" and card["comment_count"] == 1


async def test_editing_a_comment_marks_it_edited_and_an_unchanged_save_does_not(api_client, db_session):
    job = await _job(db_session)
    comment = await _comment(api_client, job.id, "Recruiter call went well")
    url = f"/api/jobs/{job.id}/pursuit/comments/{comment['id']}"

    same = await api_client.put(url, json={"body": "Recruiter call went well"})
    assert same.status_code == 200 and same.json()["comment"]["edited_at"] is None

    edited = await api_client.put(url, json={"body": "Recruiter call went very well"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["comment"]["body"] == "Recruiter call went very well"
    assert edited.json()["comment"]["edited_at"] is not None


async def test_a_blank_comment_is_refused(api_client, db_session):
    job = await _job(db_session)

    response = await api_client.post(f"/api/jobs/{job.id}/pursuit/comments", json={"body": "   \n"})

    assert response.status_code == 422
    assert await db_session.scalar(select(PursuitComment.id)) is None


async def test_a_comment_is_reached_only_through_its_own_role(api_client, db_session):
    mine, other = await _job(db_session, "r1"), await _job(db_session, "r2")
    comment = await _comment(api_client, mine.id, "Mine")
    await _comment(api_client, other.id, "Other")

    edit = await api_client.put(f"/api/jobs/{other.id}/pursuit/comments/{comment['id']}", json={"body": "x"})
    gone = await api_client.delete(f"/api/jobs/{other.id}/pursuit/comments/{comment['id']}")

    assert edit.status_code == 404 and edit.json()["detail"]["code"] == "comment-not-found"
    assert gone.status_code == 404
    assert await db_session.scalar(select(PursuitComment.body).where(PursuitComment.id == comment["id"])) == "Mine"


async def test_an_agents_comment_cannot_be_edited_or_deleted_by_the_user(api_client, db_session):
    job = await _job(db_session)
    written = await store.add_comment(db_session, job.id, store.CommentWrite(body="From the agent"), actor="agent")
    await db_session.commit()
    comment_id = written.id
    url = f"/api/jobs/{job.id}/pursuit/comments/{comment_id}"

    edit = await api_client.put(url, json={"body": "Rewritten"})
    gone = await api_client.delete(url)

    assert edit.status_code == 403 and edit.json()["detail"]["code"] == "comment-not-yours"
    assert gone.status_code == 403
    db_session.expire_all()
    assert await db_session.scalar(select(PursuitComment.body).where(PursuitComment.id == comment_id)) == "From the agent"


async def test_deleting_a_comment_removes_it_from_the_count(api_client, db_session):
    job = await _job(db_session)
    first = await _comment(api_client, job.id, "One")
    await _comment(api_client, job.id, "Two")

    response = await api_client.delete(f"/api/jobs/{job.id}/pursuit/comments/{first['id']}")

    assert response.status_code == 200 and response.json() == {"id": first["id"], "deleted": True}
    assert (await _board(api_client))[job.id]["comment_count"] == 1


async def test_commenting_on_an_unknown_role_is_not_found(api_client, db_session):
    response = await api_client.post("/api/jobs/999999/pursuit/comments", json={"body": "Hello"})

    assert response.status_code == 404 and response.json()["detail"]["code"] == "job-not-found"


# --- interviews -------------------------------------------------------------------


async def test_an_interview_records_its_outcome_and_keeps_what_the_patch_leaves_out(api_client, db_session):
    job = await _job(db_session)
    at = datetime.now(UTC) + timedelta(days=3)
    created = await api_client.post(
        f"/api/jobs/{job.id}/pursuit/interviews",
        json={"label": "Technical round", "scheduled_at": _iso(at), "format": "video",
              "link": "https://meet.example.test/abc"},
    )
    assert created.status_code == 200, created.text
    interview = created.json()["interview"]
    url = f"/api/jobs/{job.id}/pursuit/interviews/{interview['id']}"

    patched = await api_client.patch(url, json={"outcome": "passed", "link": None})

    assert patched.status_code == 200, patched.text
    body = patched.json()["interview"]
    assert body["outcome"] == "passed" and body["link"] is None
    assert body["label"] == "Technical round" and body["format"] == "video"
    assert datetime.fromisoformat(body["scheduled_at"]) == at


@pytest.mark.parametrize("field", ["label", "scheduled_at", "all_day"])
async def test_an_interview_refuses_a_null_for_what_it_cannot_lose(api_client, db_session, field):
    job = await _job(db_session)
    created = await api_client.post(
        f"/api/jobs/{job.id}/pursuit/interviews",
        json={"label": "Screen", "scheduled_at": _iso(datetime.now(UTC))},
    )
    interview_id = created.json()["interview"]["id"]

    response = await api_client.patch(f"/api/jobs/{job.id}/pursuit/interviews/{interview_id}", json={field: None})

    assert response.status_code == 422


async def test_an_interview_is_reached_only_through_its_own_role(api_client, db_session):
    mine, other = await _job(db_session, "r1"), await _job(db_session, "r2")
    await api_client.put(f"/api/jobs/{other.id}/favorite")
    created = await api_client.post(
        f"/api/jobs/{mine.id}/pursuit/interviews",
        json={"label": "Screen", "scheduled_at": _iso(datetime.now(UTC))},
    )
    interview_id = created.json()["interview"]["id"]

    patch = await api_client.patch(f"/api/jobs/{other.id}/pursuit/interviews/{interview_id}", json={"outcome": "passed"})
    gone = await api_client.delete(f"/api/jobs/{other.id}/pursuit/interviews/{interview_id}")

    assert patch.status_code == 404 and patch.json()["detail"]["code"] == "interview-not-found"
    assert gone.status_code == 404
    assert await db_session.scalar(select(PursuitInterview.outcome).where(PursuitInterview.id == interview_id)) is None


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "intent://scan/#Intent;scheme=zxing;end",
        "zoommtg://zoom.us/join?confno=1",
        "zoom.us/j/123",
        "https://",
        "",
    ],
)
async def test_an_interview_link_that_is_not_a_web_address_is_refused(api_client, db_session, link):
    job = await _job(db_session)
    url = f"/api/jobs/{job.id}/pursuit/interviews"
    created = await api_client.post(url, json={"label": "Screen", "scheduled_at": _iso(datetime.now(UTC))})
    interview_id = created.json()["interview"]["id"]

    added = await api_client.post(url, json={"label": "Screen", "scheduled_at": _iso(datetime.now(UTC)), "link": link})
    patched = await api_client.patch(f"{url}/{interview_id}", json={"link": link})

    assert added.status_code == 422 and patched.status_code == 422
    assert (await db_session.scalars(select(PursuitInterview.link))).all() == [None]


async def test_an_interview_link_keeps_a_web_address_without_its_surrounding_space(api_client, db_session):
    job = await _job(db_session)

    response = await api_client.post(
        f"/api/jobs/{job.id}/pursuit/interviews",
        json={"label": "Screen", "scheduled_at": _iso(datetime.now(UTC)), "link": "  HTTPS://meet.example.test/abc \n"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["interview"]["link"] == "HTTPS://meet.example.test/abc"


async def test_an_unknown_interview_format_is_refused(api_client, db_session):
    job = await _job(db_session)

    response = await api_client.post(
        f"/api/jobs/{job.id}/pursuit/interviews",
        json={"label": "Screen", "scheduled_at": _iso(datetime.now(UTC)), "format": "carrier pigeon"},
    )

    assert response.status_code == 422


# --- one application and its activity --------------------------------------------


async def test_an_application_lists_interviews_newest_first_and_when_each_stage_was_reached(
    api_client, db_session
):
    job = await _job(db_session)
    await api_client.put(f"/api/jobs/{job.id}/favorite")
    await _move(api_client, job.id, "applied")
    await _move(api_client, job.id, "interviewing")
    now = datetime.now(UTC)
    for label, days in (("Screen", -6), ("Technical", 3)):
        await api_client.post(
            f"/api/jobs/{job.id}/pursuit/interviews",
            json={"label": label, "scheduled_at": _iso(now + timedelta(days=days))},
        )

    response = await api_client.get(f"/api/applications/{job.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application"]["stage"] == "interviewing"
    assert [i["label"] for i in body["interviews"]] == ["Technical", "Screen"]
    assert [r["stage"] for r in body["stages_reached"]] == ["saved", "applied", "interviewing"]


async def test_a_stage_left_and_returned_to_shows_its_return(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "applied")
    first_applied = (await api_client.get(f"/api/applications/{job.id}")).json()["stages_reached"]
    await _move(api_client, job.id, "interviewing")
    await _move(api_client, job.id, "applied")

    reached = {r["stage"]: r["at"] for r in (await api_client.get(f"/api/applications/{job.id}")).json()["stages_reached"]}

    assert reached["applied"] > next(r["at"] for r in first_applied if r["stage"] == "applied")
    assert reached["applied"] > reached["interviewing"]


async def test_a_role_off_the_board_has_no_application_and_no_activity(api_client, db_session):
    job = await _job(db_session)

    detail = await api_client.get(f"/api/applications/{job.id}")
    feed = await api_client.get(f"/api/applications/{job.id}/activity")

    assert detail.status_code == 404 and detail.json()["detail"]["code"] == "application-not-found"
    assert feed.status_code == 404


async def test_an_unstarred_role_at_considering_hides_its_feed_as_the_board_hides_its_card(
    api_client, db_session
):
    job = await _job(db_session)
    await api_client.put(f"/api/jobs/{job.id}/favorite")
    await _comment(api_client, job.id, "Read their blog post")
    await api_client.delete(f"/api/jobs/{job.id}/favorite")

    detail = await api_client.get(f"/api/applications/{job.id}")
    feed = await api_client.get(f"/api/applications/{job.id}/activity")

    assert detail.status_code == 404
    assert feed.status_code == 404 and feed.json()["detail"]["code"] == "application-not-found"

    await api_client.put(f"/api/jobs/{job.id}/favorite")
    items = (await api_client.get(f"/api/applications/{job.id}/activity")).json()["items"]
    assert "comment" in [item["kind"] for item in items]


async def test_a_star_with_nothing_written_has_an_empty_feed(api_client, db_session):
    job = await _job(db_session)
    await api_client.put(f"/api/jobs/{job.id}/favorite")

    response = await api_client.get(f"/api/applications/{job.id}/activity")

    assert response.status_code == 200 and response.json() == {"items": []}


async def test_the_feed_runs_newest_first_and_pages_backwards(api_client, db_session):
    job = await _job(db_session)
    await _move(api_client, job.id, "researching")
    await _comment(api_client, job.id, "Read their blog")
    await _move(api_client, job.id, "applied")
    await _comment(api_client, job.id, "Sent the form")
    # Spread the rows a minute apart so the order is the story, not the clock's.
    pursuit_id = await db_session.scalar(select(Pursuit.id).where(Pursuit.job_id == job.id))
    base = datetime.now(UTC) - timedelta(hours=1)
    events = (await db_session.scalars(select(PursuitEvent).where(PursuitEvent.pursuit_id == pursuit_id).order_by(PursuitEvent.id))).all()
    comments = (await db_session.scalars(select(PursuitComment).where(PursuitComment.pursuit_id == pursuit_id).order_by(PursuitComment.id))).all()
    story = [events[0], comments[0], events[1], comments[1]]
    for minute, row in enumerate(story):
        row.created_at = base + timedelta(minutes=minute)
    await db_session.commit()

    first = (await api_client.get(f"/api/applications/{job.id}/activity", params={"limit": 2})).json()["items"]
    rest = (
        await api_client.get(f"/api/applications/{job.id}/activity", params={"limit": 2, "offset": 2})
    ).json()["items"]

    said = [(i["kind"], i.get("body") or i["to_stage"]) for i in first + rest]
    assert said == [
        ("comment", "Sent the form"),
        ("event", "applied"),
        ("comment", "Read their blog"),
        ("event", "researching"),
    ]
    assert first[1]["from_stage"] == "researching" and first[1]["changed"] == ["stage"]
    assert rest[1]["event_type"] == "created" and rest[1]["source"] == "app"


async def test_a_long_history_reads_whole_and_its_oldest_comment_stays_editable(api_client, db_session):
    """An application with far more entries than any one screen holds: the
    read without a limit returns every one, so the first comment ever written
    is on the page and can still be edited and deleted."""
    job = await _job(db_session)
    oldest = await _comment(api_client, job.id, "The very first note")
    pursuit_id = await db_session.scalar(select(Pursuit.id).where(Pursuit.job_id == job.id))
    start = datetime.now(UTC) - timedelta(days=400)
    await db_session.execute(
        PursuitComment.__table__.update().where(PursuitComment.id == oldest["id"]).values(created_at=start)
    )
    db_session.add_all(
        PursuitComment(pursuit_id=pursuit_id, actor="user", body=f"Note {n}", created_at=start + timedelta(days=1, hours=n))
        for n in range(240)
    )
    db_session.add_all(
        PursuitEvent(
            pursuit_id=pursuit_id, actor="user", event_type="updated", from_stage="saved", to_stage="saved",
            detail={"changed": ["priority"]}, created_at=start + timedelta(days=1, hours=n, minutes=30),
        )
        for n in range(240)
    )
    await db_session.commit()

    response = await api_client.get(f"/api/applications/{job.id}/activity")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    created = 1  # the pursuit's own created event, written with the first comment
    assert len(items) == 1 + 240 + 240 + created
    assert [i["id"] for i in items if i["kind"] == "comment"][-1] == oldest["id"]

    edited = await api_client.put(
        f"/api/jobs/{job.id}/pursuit/comments/{oldest['id']}", json={"body": "The very first note, revised"}
    )
    assert edited.status_code == 200, edited.text
    deleted = await api_client.delete(f"/api/jobs/{job.id}/pursuit/comments/{oldest['id']}")
    assert deleted.status_code == 200, deleted.text
    after = (await api_client.get(f"/api/applications/{job.id}/activity")).json()["items"]
    assert oldest["id"] not in [i["id"] for i in after if i["kind"] == "comment"]


async def test_a_history_with_more_entries_than_one_statement_binds_reads_whole(api_client, db_session):
    """asyncpg binds at most 32,767 parameters per statement; a whole history
    holding more comments than that still reads, every one of them."""
    job = await _job(db_session)
    await _comment(api_client, job.id, "One")
    pursuit_id = await db_session.scalar(select(Pursuit.id).where(Pursuit.job_id == job.id))
    start = datetime.now(UTC) - timedelta(days=400)
    many = 32_800
    await db_session.execute(
        insert(PursuitComment),
        [
            {"pursuit_id": pursuit_id, "actor": "user", "body": f"Note {n}", "created_at": start + timedelta(minutes=n)}
            for n in range(many)
        ],
    )
    await db_session.commit()

    response = await api_client.get(f"/api/applications/{job.id}/activity")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1 + many + 1  # the comment, the notes, the created event
    assert items[-1]["body"] == "Note 0"


async def test_a_slice_larger_than_any_page_is_honoured(api_client, db_session):
    """A slice asks for exactly what it names, however far past any page size
    the feed was ever cut to."""
    job = await _job(db_session)
    await _comment(api_client, job.id, "One")
    pursuit_id = await db_session.scalar(select(Pursuit.id).where(Pursuit.job_id == job.id))
    start = datetime.now(UTC) - timedelta(days=30)
    db_session.add_all(
        PursuitComment(pursuit_id=pursuit_id, actor="user", body=f"Note {n}", created_at=start + timedelta(hours=n))
        for n in range(300)
    )
    await db_session.commit()

    sliced = await api_client.get(f"/api/applications/{job.id}/activity", params={"limit": 250})
    beyond = await api_client.get(f"/api/applications/{job.id}/activity", params={"limit": 5000})

    assert sliced.status_code == 200, sliced.text
    assert len(sliced.json()["items"]) == 250
    assert beyond.status_code == 200, beyond.text
    assert len(beyond.json()["items"]) == 1 + 300 + 1  # the comment, the notes, the created event


async def test_a_page_that_ends_inside_rows_written_together_loses_none_of_them(api_client, db_session):
    """Rows one transaction writes share its `now()`: a first comment writes the
    pursuit's created event and the comment at one instant. Paging one item at
    a time still reads every row once, in the feed's order."""
    job = await _job(db_session)
    await _comment(api_client, job.id, "First thought")
    await _move(api_client, job.id, "researching")
    await _comment(api_client, job.id, "Second thought")
    pursuit_id = await db_session.scalar(select(Pursuit.id).where(Pursuit.job_id == job.id))
    together = datetime.now(UTC) - timedelta(hours=1)
    for model in (PursuitEvent, PursuitComment):
        for row in (await db_session.scalars(select(model).where(model.pursuit_id == pursuit_id))).all():
            row.created_at = together
    await db_session.commit()

    whole = (await api_client.get(f"/api/applications/{job.id}/activity")).json()["items"]
    paged = []
    for offset in range(len(whole) + 1):
        response = await api_client.get(f"/api/applications/{job.id}/activity", params={"limit": 1, "offset": offset})
        assert response.status_code == 200, response.text
        paged += response.json()["items"]

    # At one instant, comments come before changes, and the later row first.
    assert [(i["kind"], i.get("body") or i["to_stage"]) for i in whole] == [
        ("comment", "Second thought"),
        ("comment", "First thought"),
        ("event", "researching"),
        ("event", "saved"),
    ]
    assert [(i["kind"], i["id"]) for i in paged] == [(i["kind"], i["id"]) for i in whole]


# --- contracts --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("published", "written", "column", "constraint"),
    [
        (contract.InterviewFormat, store.InterviewFormat, "format", "ck_pursuit_interview_format"),
        (contract.InterviewOutcome, store.InterviewOutcome, "outcome", "ck_pursuit_interview_outcome"),
    ],
)
async def test_interview_values_are_the_ones_the_table_admits(published, written, column, constraint):
    [check] = [c for c in PursuitInterview.__table__.constraints if c.name == constraint]
    admitted = set(re.findall(r"'([^']+)'", str(check.sqltext)))
    assert set(get_args(published)) == set(get_args(written)) == admitted


@pytest.mark.parametrize(
    ("starred", "stage", "shown"),
    [
        (True, None, "saved"),
        (False, "applied", "applied"),
        (False, "saved", None),
        (True, "saved", "saved"),
        (True, "interviewing", "interviewing"),
    ],
    ids=["star-only", "pursuit-past-considering", "pursuit-at-considering-unstarred", "both-considering", "both-moved"],
)
async def test_a_rows_pipeline_stage_follows_the_boards_star_and_pursuit_rule(db_session, starred, stage, shown):
    from tracker.db.queries.jobs import row_context

    job = await _job(db_session)
    other = await _job(db_session, "r2")
    if starred:
        db_session.add(Favorite(job_id=job.id))
    if stage is not None:
        db_session.add(Pursuit(job_id=job.id, stage=stage))
    # A neighbour that is neither, and one that is both, must not leak in.
    db_session.add_all([Favorite(job_id=other.id), Pursuit(job_id=other.id, stage="offer")])
    await db_session.flush()

    context = await row_context(db_session, [job], standing=False)

    assert context["pipeline_stages"] == ({} if shown is None else {job.id: shown})
    assert context["favorite_ids"] == ({job.id} if starred else set())

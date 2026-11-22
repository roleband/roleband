"""The role's notes as the dashboard writes them: a save names the text it
started from, and notes written meanwhile are never written over unseen."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from tracker.agents import pursuits as store
from tracker.db.models import Job, Pursuit, PursuitEvent

pytestmark = pytest.mark.asyncio


async def _job(db_session, req: str = "n1") -> int:
    now = datetime.now(UTC)
    job = Job(
        company="openai", req_id=req, dedupe_key=f"openai:{req}", title=f"Staff PM {req}",
        url=f"https://careers.example.test/{req}", level_band="staff", status="open",
        first_seen=now - timedelta(days=5), last_seen=now, in_scope=True,
    )
    db_session.add(job)
    await db_session.commit()
    return job.id


async def _save(api_client, job_id: int, notes: str | None, was: str | None):
    body: dict[str, object] = {"notes": notes}
    if was is not None:
        body["notes_was"] = was
    return await api_client.put(f"/api/jobs/{job_id}/pursuit", json=body)


async def _stored(db_session, job_id: int) -> str | None:
    db_session.expire_all()
    return await db_session.scalar(select(Pursuit.notes).where(Pursuit.job_id == job_id))


async def _events(db_session, job_id: int) -> int:
    return await db_session.scalar(
        select(func.count()).select_from(PursuitEvent).join(Pursuit).where(Pursuit.job_id == job_id)
    )


async def test_a_save_from_the_stored_notes_writes_them(api_client, db_session):
    job_id = await _job(db_session)
    first = await _save(api_client, job_id, "Recruiter is Sam", was="")
    assert first.status_code == 200, first.text
    second = await _save(api_client, job_id, "Recruiter is Sam\n\nPanel on Friday", was="Recruiter is Sam")
    assert second.status_code == 200, second.text
    assert await _stored(db_session, job_id) == "Recruiter is Sam\n\nPanel on Friday"


async def test_a_save_from_notes_changed_since_is_refused_with_the_notes_as_they_are(api_client, db_session):
    job_id = await _job(db_session)
    assert (await _save(api_client, job_id, "Recruiter is Sam", was="")).status_code == 200
    # The person's assistant adds a line while the page still holds the first.
    await store.upsert_pursuit(
        db_session, job_id, store.PursuitUpdate(notes="Recruiter is Sam\n\nComp band: 210-240k"), actor="agent",
    )
    await db_session.commit()
    events = await _events(db_session, job_id)

    response = await _save(api_client, job_id, "Recruiter is Sam\n\nAsk about the team", was="Recruiter is Sam")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "notes-moved"
    assert detail["params"]["current"] == "Recruiter is Sam\n\nComp band: 210-240k"
    # Nothing written, nothing recorded: the assistant's line stands.
    assert await _stored(db_session, job_id) == "Recruiter is Sam\n\nComp band: 210-240k"
    assert await _events(db_session, job_id) == events


async def test_notes_started_from_none_are_refused_once_there_are_notes(api_client, db_session):
    job_id = await _job(db_session)
    await store.upsert_pursuit(db_session, job_id, store.PursuitUpdate(notes="Written elsewhere"), actor="agent")
    await db_session.commit()

    response = await _save(api_client, job_id, "Mine", was="")

    assert response.status_code == 409
    assert response.json()["detail"]["params"]["current"] == "Written elsewhere"


async def test_clearing_the_notes_is_checked_too_and_cleared_notes_read_as_none(api_client, db_session):
    job_id = await _job(db_session)
    assert (await _save(api_client, job_id, "Recruiter is Sam", was="")).status_code == 200
    assert (await _save(api_client, job_id, None, was="Recruiter is Sam")).status_code == 200
    assert await _stored(db_session, job_id) is None
    # Started from no notes, a new page is written: cleared notes are "".
    assert (await _save(api_client, job_id, "Fresh start", was="")).status_code == 200


async def test_a_write_that_names_no_starting_text_is_last_writer_wins(api_client, db_session):
    job_id = await _job(db_session)
    await store.upsert_pursuit(db_session, job_id, store.PursuitUpdate(notes="Written elsewhere"), actor="agent")
    await db_session.commit()

    response = await _save(api_client, job_id, "Mine", was=None)

    assert response.status_code == 200, response.text
    assert await _stored(db_session, job_id) == "Mine"


async def test_a_write_without_notes_ignores_the_starting_text(api_client, db_session):
    job_id = await _job(db_session)
    await store.upsert_pursuit(db_session, job_id, store.PursuitUpdate(notes="Written elsewhere"), actor="agent")
    await db_session.commit()

    response = await api_client.put(f"/api/jobs/{job_id}/pursuit", json={"priority": 5, "notes_was": "stale"})

    assert response.status_code == 200, response.text
    assert await _stored(db_session, job_id) == "Written elsewhere"


# --- one entry per writing session --------------------------------------------


async def _notes_events(db_session, job_id: int) -> list[PursuitEvent]:
    db_session.expire_all()
    rows = await db_session.scalars(
        select(PursuitEvent).join(Pursuit).where(Pursuit.job_id == job_id).order_by(PursuitEvent.id)
    )
    return [event for event in rows if "notes" in event.detail.get("changed", [])]


async def _activity(api_client, job_id: int) -> list[dict]:
    response = await api_client.get(f"/api/applications/{job_id}/activity")
    assert response.status_code == 200, response.text
    return [item for item in response.json()["items"] if "notes" in item.get("changed", [])]


async def _age(db_session, job_id: int, minutes: int) -> None:
    """Moves every event of the role this many minutes into the past."""
    pursuit_id = await db_session.scalar(select(Pursuit.id).where(Pursuit.job_id == job_id))
    await db_session.execute(
        PursuitEvent.__table__.update()
        .where(PursuitEvent.pursuit_id == pursuit_id)
        .values(created_at=PursuitEvent.created_at - timedelta(minutes=minutes))
    )
    await db_session.commit()


async def _type(api_client, job_id: int, *versions: str, was: str = "") -> str:
    """Saves each version in turn, as the page does at each pause in typing."""
    for text in versions:
        response = await _save(api_client, job_id, text, was=was)
        assert response.status_code == 200, response.text
        was = text
    return was


async def test_the_saves_of_one_writing_session_are_one_entry_in_history_keeping_one_copy(api_client, db_session):
    job_id = await _job(db_session)
    await _type(api_client, job_id, "Recruiter")
    await _age(db_session, job_id, 30)
    await _type(api_client, job_id, "Recruiter is Sam", "Recruiter is Sam\n\nPanel", "Recruiter is Sam\n\nPanel on Friday", was="Recruiter")

    first, *rest = (await _notes_events(db_session, job_id))[1:]
    # The session's first save keeps what it replaced; the saves after it
    # name the session and keep no copy of the notes.
    assert first.detail["before"]["notes"] == "Recruiter"
    assert [event.detail.get("session") for event in rest] == [first.id, first.id]
    assert all("notes" not in event.detail["before"] and "notes" not in event.detail["after"] for event in rest)
    # History: one entry for the earlier session and one for this one, dated
    # at its last save.
    entries = await _activity(api_client, job_id)
    assert [entry["id"] for entry in entries] == [first.id, (await _notes_events(db_session, job_id))[0].id]
    assert datetime.fromisoformat(entries[0]["created_at"]) == max(event.created_at for event in [first, *rest])
    # Each save is still a write: the revision moves with every one.
    db_session.expire_all()
    assert await db_session.scalar(select(Pursuit.revision).where(Pursuit.job_id == job_id)) == 4


async def test_a_pause_longer_than_the_gap_starts_a_new_entry_that_keeps_the_last_sessions_text(api_client, db_session):
    job_id = await _job(db_session)
    was = await _type(api_client, job_id, "Recruiter", "Recruiter is Sam")
    await _age(db_session, job_id, int(store.NOTES_SESSION_GAP.total_seconds() // 60) + 1)
    await _type(api_client, job_id, "Recruiter is Sam\n\nPanel on Friday", was=was)

    events = await _notes_events(db_session, job_id)
    assert "session" not in events[-1].detail
    # The new session's first save keeps the text the last one ended with.
    assert events[-1].detail["before"]["notes"] == "Recruiter is Sam"
    assert len(await _activity(api_client, job_id)) == 2


async def test_a_pause_inside_the_gap_carries_the_session_on(api_client, db_session):
    job_id = await _job(db_session)
    was = await _type(api_client, job_id, "Recruiter", "Recruiter is Sam")
    await _age(db_session, job_id, int(store.NOTES_SESSION_GAP.total_seconds() // 60) - 1)
    await _type(api_client, job_id, "Recruiter is Sam Lee", was=was)

    assert len(await _activity(api_client, job_id)) == 1


async def test_the_assistants_write_between_two_saves_is_its_own_entry_and_keeps_both_versions(api_client, db_session):
    job_id = await _job(db_session)
    await _type(api_client, job_id, "Recruiter", "Recruiter is Sam")
    await store.upsert_pursuit(
        db_session, job_id, store.PursuitUpdate(notes="Recruiter is Sam\n\nComp band: 210-240k"), actor="agent",
    )
    await db_session.commit()
    await _type(api_client, job_id, "Recruiter is Sam\n\nComp band: 210-240k\n\nAsk about the team", was="Recruiter is Sam\n\nComp band: 210-240k")

    events = await _notes_events(db_session, job_id)
    agent, after_agent = events[-2], events[-1]
    assert agent.actor == "agent" and "session" not in agent.detail
    assert agent.detail["before"]["notes"] == "Recruiter is Sam"
    assert agent.detail["after"]["notes"] == "Recruiter is Sam\n\nComp band: 210-240k"
    # The person's next save starts a session of its own, over the assistant's text.
    assert "session" not in after_agent.detail
    assert after_agent.detail["before"]["notes"] == "Recruiter is Sam\n\nComp band: 210-240k"
    assert len(await _activity(api_client, job_id)) == 3


async def test_the_assistants_saves_in_a_row_are_each_an_entry(api_client, db_session):
    job_id = await _job(db_session)
    for text in ("Recruiter is Sam", "Recruiter is Sam Lee"):
        await store.upsert_pursuit(db_session, job_id, store.PursuitUpdate(notes=text), actor="agent")
        await db_session.commit()

    events = await _notes_events(db_session, job_id)
    assert all("session" not in event.detail for event in events)
    assert events[-1].detail["before"]["notes"] == "Recruiter is Sam"


# --- earlier versions -----------------------------------------------------------


async def _versions(api_client, job_id: int) -> list[dict]:
    response = await api_client.get(f"/api/applications/{job_id}/notes/versions")
    assert response.status_code == 200, response.text
    return response.json()["versions"]


async def test_the_earlier_versions_are_what_each_writing_session_left_newest_first(api_client, db_session):
    job_id = await _job(db_session)
    was = await _type(api_client, job_id, "Recruiter", "Recruiter is Sam")
    await _age(db_session, job_id, 60)
    was = await _type(api_client, job_id, "Recruiter is Sam\n\nPanel", "Recruiter is Sam\n\nPanel on Friday", was=was)
    await _age(db_session, job_id, 60)
    await store.upsert_pursuit(db_session, job_id, store.PursuitUpdate(notes="Comp band: 210-240k"), actor="agent")
    await db_session.commit()

    versions = await _versions(api_client, job_id)

    # Newest first; the notes as they are now ("Comp band") are not listed,
    # nor the saves inside a session ("Recruiter", "...Panel").
    assert [(v["actor"], v["text"]) for v in versions] == [
        ("user", "Recruiter is Sam\n\nPanel on Friday"),
        ("user", "Recruiter is Sam"),
    ]
    # Each is dated at its session's last save.
    assert datetime.fromisoformat(versions[0]["at"]) > datetime.fromisoformat(versions[1]["at"])


async def test_a_version_put_back_is_a_new_write_and_the_notes_it_replaced_become_a_version(api_client, db_session):
    job_id = await _job(db_session)
    await _type(api_client, job_id, "Recruiter is Sam")
    await _age(db_session, job_id, 60)
    await store.upsert_pursuit(db_session, job_id, store.PursuitUpdate(notes="Overwritten"), actor="agent")
    await db_session.commit()
    earlier = (await _versions(api_client, job_id))[0]["text"]

    restored = await _save(api_client, job_id, earlier, was="Overwritten")

    assert restored.status_code == 200, restored.text
    assert await _stored(db_session, job_id) == "Recruiter is Sam"
    assert "Overwritten" in [v["text"] for v in await _versions(api_client, job_id)]


async def test_a_role_with_notes_written_once_has_no_earlier_version(api_client, db_session):
    job_id = await _job(db_session)
    await _type(api_client, job_id, "Recruiter", "Recruiter is Sam")
    assert await _versions(api_client, job_id) == []


async def test_a_role_not_on_the_board_has_no_versions_to_read(api_client, db_session):
    job_id = await _job(db_session)
    response = await api_client.get(f"/api/applications/{job_id}/notes/versions")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "application-not-found"

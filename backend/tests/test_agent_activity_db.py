"""Every agent read, change and refusal is listed, and the Activity list pages it.

Driven over the real app (`api_client`) on the scratch database: the agent
routes write the rows, `/api/agent-activity` reads them. A change's row is
part of the write's transaction, so the rollback cases assert what is left
behind, not only the status.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tracker.agents import activity
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api import agent_operations
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, PREFIX
from tracker.db.models import AgentActivity, CommandReceipt, Job, Pursuit

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

KEY = "idk_" + "a" * 32
OTHER_KEY = "idk_" + "b" * 32


@pytest_asyncio.fixture
async def role(db_session) -> int:
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    job = Job(
        company="contoso", req_id="r1", dedupe_key="contoso:r1", title="Design Lead",
        url="https://careers.example.test/r1", status="open", level_band="staff",
    )
    db_session.add(job)
    await db_session.commit()
    return job.id


def _fresh(db_session) -> AsyncSession:
    return async_sessionmaker(db_session.bind, expire_on_commit=False)()


async def _rows(db_session) -> list[AgentActivity]:
    async with _fresh(db_session) as session:
        return list((await session.scalars(select(AgentActivity).order_by(AgentActivity.id))).all())


async def _count(db_session, model) -> int:
    async with _fresh(db_session) as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _access(db_session, **config: Any) -> None:
    async with _fresh(db_session) as session:
        await set_agent_access(session, AgentAccessConfig(**config))
        await session.commit()


async def _save(api_client, role: int, *, key: str = KEY, body: dict[str, Any] | None = None):
    return await api_client.put(
        f"{PREFIX}/pursuits/{role}", json=body or {}, headers={IDEMPOTENCY_KEY_HEADER: key}
    )


async def _patch(api_client, role: int, body: dict[str, Any], *, key: str = OTHER_KEY):
    return await api_client.patch(f"{PREFIX}/pursuits/{role}", json=body, headers={IDEMPOTENCY_KEY_HEADER: key})


# --------------------------------------------------------------------------- #
# Changes: in the write's own transaction
# --------------------------------------------------------------------------- #


async def test_a_save_lists_its_change_with_each_field_before_and_after(api_client, db_session, role):
    response = await _save(api_client, role)
    assert response.status_code == 200, response.text

    (row,) = await _rows(db_session)
    assert row.kind == "change"
    assert row.operation == "pursuits.save"
    assert row.subject == {"topic": "pursuit.saved", "title": "Design Lead", "company": "contoso"}
    assert row.summary == "Saved Design Lead at contoso"
    assert sorted(row.categories) == ["private_pursuit", "public_posting"]
    assert row.idempotency_key == KEY
    assert row.request_id == response.json()["request_id"]
    # A new pursuit had none of its fields before.
    assert {(c["field"], c["before"], c["after"]) for c in row.changes} == {("stage", None, "saved"), ("priority", None, 3)}
    # The group of changes the operation belongs to, as the person switches it.
    assert row.action_group == "tracking_progress" and row.refusal is None


async def test_a_patch_lists_only_the_fields_it_changed(api_client, db_session, role):
    assert (await _save(api_client, role)).status_code == 200
    response = await _patch(api_client, role, {"if_revision": 1, "stage": "interviewing", "priority": 3})
    assert response.status_code == 200, response.text

    moved = (await _rows(db_session))[-1]
    assert moved.operation == "pursuits.patch"
    assert moved.subject == {
        "topic": "pursuit.moved", "title": "Design Lead", "company": "contoso", "stage": "interviewing",
    }
    # Priority was sent at the value it had, so it is not a change.
    assert moved.changes == [{"field": "stage", "before": "saved", "after": "interviewing"}]

    notes = await _patch(api_client, role, {"if_revision": 2, "notes": "Portfolio review"}, key="idk_" + "c" * 32)
    assert notes.status_code == 200, notes.text
    noted = (await _rows(db_session))[-1]
    assert noted.subject["topic"] == "pursuit.changed"
    assert noted.changes == [{"field": "notes", "before": None, "after": "Portfolio review"}]


async def test_a_replayed_write_lists_nothing_again(api_client, db_session, role):
    assert (await _save(api_client, role)).status_code == 200
    replay = await _save(api_client, role)
    assert replay.status_code == 200
    assert replay.json()["meta"]["replayed"] is True
    rows = await _rows(db_session)
    # One change, and the replay is not a read either.
    assert [(row.kind, row.operation) for row in rows] == [("change", "pursuits.save")]


async def test_a_rolled_back_write_leaves_no_activity(api_client, db_session, role, monkeypatch):
    """The receipt fails after the write and its activity row were flushed:
    the transaction rolls back all three. A row committed on its own would
    survive here."""
    flushed: list[str] = []
    record = activity.record

    async def watched(session, row):
        await record(session, row)
        flushed.append(row.operation)

    monkeypatch.setattr(activity, "record", watched)
    # A hash the receipt's check refuses, so its insert fails at flush.
    monkeypatch.setattr(agent_operations, "input_hash", lambda *_: "not a hash")

    response = await _save(api_client, role)
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "internal_error"
    assert flushed == ["pursuits.save"]
    assert await _rows(db_session) == []
    assert await _count(db_session, Pursuit) == 0
    assert await _count(db_session, CommandReceipt) == 0


async def test_a_write_refused_before_it_runs_lists_no_change(api_client, db_session, role):
    assert (await _save(api_client, role)).status_code == 200
    stale = await _patch(api_client, role, {"if_revision": 7, "stage": "applied"})
    assert stale.json()["error"]["code"] == "revision_conflict"
    assert [row.kind for row in await _rows(db_session)] == ["change"]


# --------------------------------------------------------------------------- #
# Reads and refusals
# --------------------------------------------------------------------------- #


async def test_a_read_lists_what_it_answered_with_its_count(api_client, db_session, role):
    assert (await _save(api_client, role)).status_code == 200
    response = await api_client.get(f"{PREFIX}/pursuits")
    assert response.status_code == 200, response.text

    read = (await _rows(db_session))[-1]
    assert (read.kind, read.operation) == ("read", "pursuits.list")
    assert read.subject == {"topic": "read.private_pursuit", "count": 1}
    assert sorted(read.categories) == ["private_pursuit", "public_posting"]
    assert read.changes is None


async def test_a_read_lists_only_the_categories_it_was_allowed(api_client, db_session, role):
    await _access(db_session, enabled=True, allow_writes=True, categories={"public_posting": "not_shared"})
    response = await api_client.get(f"{PREFIX}/pursuits")
    assert response.status_code == 200, response.text
    (read,) = await _rows(db_session)
    assert read.categories == ["private_pursuit"]


async def test_a_refused_read_is_listed_with_the_category_it_asked_for(api_client, db_session, role):
    await _access(db_session, enabled=True, allow_writes=True, categories={"offer": "not_shared"})
    response = await api_client.get(f"{PREFIX}/offer")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "category_disabled"

    (row,) = await _rows(db_session)
    assert (row.kind, row.operation, row.refusal) == ("refused", "offer.get", "category_disabled")
    assert row.categories == ["offer"]
    assert row.subject == {"topic": "refused.category", "category": "offer"}
    assert row.summary == "Asked for your offer"


async def test_refusals_by_the_switches_are_listed_too(api_client, db_session, role):
    await _access(db_session, enabled=True, allow_writes=False)
    write = await _save(api_client, role)
    assert write.json()["error"]["code"] == "writes_disabled"
    await _access(db_session, enabled=False)
    status = await api_client.get(f"{PREFIX}/status")
    assert status.json()["error"]["code"] == "access_disabled"

    rows = await _rows(db_session)
    assert [(row.kind, row.operation, row.refusal, row.subject["topic"]) for row in rows] == [
        ("refused", "pursuits.save", "writes_disabled", "refused.writes"),
        ("refused", "status", "access_disabled", "refused.access"),
    ]
    assert await _count(db_session, Pursuit) == 0


async def test_a_change_the_person_holds_back_is_listed_with_its_group(api_client, db_session, role):
    await _access(db_session, enabled=True, allow_writes=True, groups={"tracking_progress": "off"})
    write = await _save(api_client, role)
    assert write.json()["error"]["code"] == "writes_disabled"

    (row,) = await _rows(db_session)
    assert (row.kind, row.operation, row.refusal) == ("refused", "pursuits.save", "writes_disabled")
    assert row.action_group == "tracking_progress"
    assert await _count(db_session, Pursuit) == 0


async def test_a_read_or_refusal_is_listed_after_the_request_lets_go_of_its_connection(
    api_client, db_session, role, monkeypatch
):
    # The row is written on a session of its own; the request's session must
    # have ended its transaction by then, so one call holds one connection.
    from tracker.api.app import app
    from tracker.api.deps import get_session

    handed: list[AsyncSession] = []
    inner = app.dependency_overrides[get_session]

    async def tracked():
        async for session in inner():
            handed.append(session)
            yield session

    app.dependency_overrides[get_session] = tracked
    held: list[bool] = []
    record = activity.record

    async def spy(session: AsyncSession, row: AgentActivity) -> None:
        held.append(handed[0].in_transaction())
        await record(session, row)

    monkeypatch.setattr(activity, "record", spy)

    assert (await api_client.get(f"{PREFIX}/pursuits")).status_code == 200
    handed.clear()
    await _access(db_session, enabled=True, allow_writes=True, categories={"offer": "not_shared"})
    assert (await api_client.get(f"{PREFIX}/offer")).status_code == 403
    assert held == [False, False]
    assert [row.kind for row in await _rows(db_session)] == ["read", "refused"]


async def test_other_failures_are_not_listed(api_client, db_session, role):
    missing = await api_client.get(f"{PREFIX}/pursuits/{role + 999}")
    assert missing.json()["error"]["code"] == "not_found"
    invalid = await api_client.get(f"{PREFIX}/pursuits", params={"limit": 0})
    assert invalid.json()["error"]["code"] == "invalid_input"
    assert await _rows(db_session) == []


async def test_a_read_the_log_cannot_hold_is_not_answered(api_client, db_session, role, monkeypatch):
    async def broken(session, row):
        raise RuntimeError("the log is unavailable")

    monkeypatch.setattr(activity, "record", broken)
    response = await api_client.get(f"{PREFIX}/pursuits")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body.get("data") is None


# --------------------------------------------------------------------------- #
# The Activity list
# --------------------------------------------------------------------------- #

NOW = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)


def _row(n: int, *, at: datetime, kind: str = "read", categories: tuple[str, ...] = ("public_posting",),
         title: str | None = None, summary: str | None = None) -> AgentActivity:
    subject: dict[str, Any] = {"topic": f"read.{categories[0]}" if categories else "read.engine"}
    if title is not None:
        subject["title"] = title
    return AgentActivity(
        occurred_at=at, principal_id="agent", operation="opportunities.search", kind=kind,
        categories=list(categories), refusal="category_disabled" if kind == "refused" else None,
        summary=summary or f"Read postings {n}", subject=subject,
        changes=[] if kind == "change" else None,
    )


async def _seed(db_session, rows: list[AgentActivity]) -> None:
    async with _fresh(db_session) as session:
        session.add_all(rows)
        await session.commit()


async def _list(api_client, **params: Any) -> dict[str, Any]:
    response = await api_client.get("/api/agent-activity", params={k: v for k, v in params.items() if v is not None})
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_list_pages_newest_first_by_keyset_without_gaps_or_repeats(api_client, db_session):
    # Ties on the timestamp are broken by id, so a page boundary inside a tie loses nothing.
    rows = [_row(n, at=NOW - timedelta(minutes=n // 3)) for n in range(120)]
    await _seed(db_session, rows)

    first = await _list(api_client)
    assert len(first["items"]) == 50 and first["next_cursor"]
    # A row recorded after the first page does not shift the next one.
    await _seed(db_session, [_row(999, at=NOW + timedelta(hours=1))])
    second = await _list(api_client, cursor=first["next_cursor"])
    third = await _list(api_client, cursor=second["next_cursor"])
    assert len(second["items"]) == 50 and len(third["items"]) == 20
    assert third["next_cursor"] is None

    seen = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert len(seen) == len(set(seen)) == 120
    keys = [
        (datetime.fromisoformat(item["occurred_at"]), item["id"])
        for page in (first, second, third) for item in page["items"]
    ]
    assert keys == sorted(keys, reverse=True)
    # And the new row leads the list read from the top again.
    assert (await _list(api_client))["items"][0]["summary"] == "Read postings 999"


async def test_the_list_filters_by_kind_category_and_dates(api_client, db_session):
    await _seed(db_session, [
        _row(1, at=NOW - timedelta(days=1), kind="change", categories=("private_pursuit", "public_posting")),
        _row(2, at=NOW - timedelta(days=2), kind="read", categories=("market_statistic",)),
        _row(3, at=NOW - timedelta(days=3), kind="refused", categories=("offer",)),
        _row(4, at=NOW - timedelta(days=40), kind="read", categories=("public_posting",)),
    ])

    def summaries(page: dict[str, Any]) -> list[str]:
        return [item["summary"] for item in page["items"]]

    assert summaries(await _list(api_client, kind="change")) == ["Read postings 1"]
    assert summaries(await _list(api_client, kind="refused")) == ["Read postings 3"]
    assert summaries(await _list(api_client, kind="read")) == ["Read postings 2", "Read postings 4"]
    assert summaries(await _list(api_client, category="public_posting")) == ["Read postings 1", "Read postings 4"]
    assert summaries(await _list(api_client, category="offer")) == ["Read postings 3"]
    # `since` is inclusive, `until` exclusive.
    since = (NOW - timedelta(days=3)).isoformat()
    until = (NOW - timedelta(days=1)).isoformat()
    assert summaries(await _list(api_client, since=since, until=until)) == ["Read postings 2", "Read postings 3"]
    assert summaries(await _list(api_client, kind="read", since=(NOW - timedelta(days=30)).isoformat())) == [
        "Read postings 2"
    ]


async def test_search_matches_the_summary_and_the_role_ignoring_case(api_client, db_session):
    await _seed(db_session, [
        _row(1, at=NOW, title="Design Lead", summary="Moved Design Lead at contoso to interviewing"),
        _row(2, at=NOW - timedelta(minutes=1), title="Staff PM", summary="Saved Staff PM at northwind"),
        _row(3, at=NOW - timedelta(minutes=2), summary="Read 100% of postings"),
    ])

    def summaries(page: dict[str, Any]) -> list[str]:
        return [item["summary"] for item in page["items"]]

    assert summaries(await _list(api_client, q="design lead")) == ["Moved Design Lead at contoso to interviewing"]
    assert summaries(await _list(api_client, q="NORTHWIND")) == ["Saved Staff PM at northwind"]
    # A wildcard is matched as itself.
    assert summaries(await _list(api_client, q="100%")) == ["Read 100% of postings"]
    assert summaries(await _list(api_client, q="%")) == ["Read 100% of postings"]
    assert summaries(await _list(api_client, q="search")) == summaries(await _list(api_client))


async def test_the_list_refuses_a_cursor_it_did_not_make(api_client, db_session):
    for cursor in ("not-a-cursor", "eyJ2IjoyLCJ0IjoiMjAyNiIsImlkIjoxfQ"):
        response = await api_client.get("/api/agent-activity", params={"cursor": cursor})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid-input"


async def test_the_list_carries_a_change_with_its_fields(api_client, db_session, role):
    assert (await _save(api_client, role)).status_code == 200
    (item,) = (await _list(api_client))["items"]
    assert item["kind"] == "change"
    assert item["operation"] == "pursuits.save"
    assert item["subject"]["title"] == "Design Lead"
    assert {change["field"] for change in item["changes"]} == {"stage", "priority"}


async def test_one_entry_is_read_by_its_id_whatever_page_it_is_on(api_client, db_session):
    await _seed(db_session, [_row(n, at=NOW - timedelta(minutes=n)) for n in range(60)])
    first = await _list(api_client)
    on_page = {item["id"] for item in first["items"]}
    older = (await _list(api_client, cursor=first["next_cursor"]))["items"][-1]
    assert older["id"] not in on_page

    response = await api_client.get(f"/api/agent-activity/{older['id']}")
    assert response.status_code == 200, response.text
    assert response.json() == older


async def test_an_entry_that_is_not_in_the_log_is_not_found(api_client, db_session):
    await _seed(db_session, [_row(1, at=NOW)])
    (only,) = (await _list(api_client))["items"]
    missing = await api_client.get(f"/api/agent-activity/{only['id'] + 1}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "activity-entry-not-found"
    for bad in ("0", "-1", "abc", str(2**63)):
        assert (await api_client.get(f"/api/agent-activity/{bad}")).status_code == 422, bad

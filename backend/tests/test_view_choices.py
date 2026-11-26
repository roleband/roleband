"""How the person arranged the screens is kept in the database, one row per
choice, so a cleared browser or another browser shows the same screens."""

from __future__ import annotations

import pytest

from tracker.settings_store import (
    MAX_DISMISSED,
    VIEW_CHOICE_PREFIX,
    get_view_choices,
    set_setting_dict,
)

URL = "/api/settings/view-choices"
LAYOUT = {"hidden": ["activity"], "order": ["notes", "interviews", "next", "activity"]}


async def saved(api_client) -> dict:
    response = await api_client.get(URL)
    assert response.status_code == 200, response.text
    return response.json()["choices"]


@pytest.mark.asyncio
async def test_nothing_arranged_reads_as_no_choices(api_client):
    assert await saved(api_client) == {}


@pytest.mark.asyncio
async def test_each_choice_saved_is_read_back_and_leaves_the_others_as_they_were(api_client):
    writes = {
        "workspace.interviewing": LAYOUT,
        "pipeline.board-hidden": ["decided", "closed"],
        "pipeline.list-layout": {"hidden": ["pay"], "order": ["pay", "role", "location", "level", "posting", "saved", "next", "priority", "activity"]},
        "pipeline.crossings-dismissed": ["101:closed:2026-11-20T10:00:00Z"],
        "posting.similar-folded": True,
        "sidebar.duplicates": True,
        "sidebar.insights": False,
        "insights.view": "advanced",
        "filters.board": {"companies": ["openai", "stripe"], "remote": True, "base_min": 250000},
        "filters.notifications:params": {"status": ["unread"]},
        # A screen that forgets its filters says so, apart from one left with none.
        "filters.companies": None,
        "filters.companies:open": {},
    }
    for name, value in writes.items():
        response = await api_client.put(f"{URL}/{name}", json={"value": value})
        assert response.status_code == 200, response.text
        assert response.json() == {"name": name, "value": value}
    assert await saved(api_client) == writes

    # Saved again, a choice holds only its latest value; the others stay.
    again = await api_client.put(f"{URL}/workspace.interviewing", json={"value": {"hidden": [], "order": ["next"]}})
    assert again.status_code == 200, again.text
    assert await saved(api_client) == {**writes, "workspace.interviewing": {"hidden": [], "order": ["next"]}}


@pytest.mark.asyncio
async def test_a_name_given_twice_is_kept_once_in_its_first_place(api_client):
    response = await api_client.put(f"{URL}/workspace.offer", json={"value": {"hidden": ["notes", "notes"], "order": ["next", "notes", "next", "activity"]}})
    assert response.json()["value"] == {"hidden": ["notes"], "order": ["next", "notes", "activity"]}
    columns = await api_client.put(f"{URL}/pipeline.board-hidden", json={"value": ["closed", "saved", "closed"]})
    assert columns.json()["value"] == ["closed", "saved"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("workspace.archived", LAYOUT),
        ("theme", "dark"),
        ("filters.radar", {}),
        ("workspace.interviewing", {"hidden": ["calendar"], "order": []}),
        ("workspace.interviewing", {"hidden": []}),
        ("workspace.interviewing", {"hidden": [], "order": [], "extra": 1}),
        ("workspace.interviewing", {"hidden": "notes", "order": []}),
        ("pipeline.board-hidden", ["archive"]),
        ("pipeline.board-hidden", "closed"),
        ("pipeline.list-layout", {"hidden": ["salary"], "order": []}),
        ("pipeline.crossings-dismissed", ["ok", 3]),
        ("pipeline.crossings-dismissed", ["x" * 121]),
        ("pipeline.crossings-dismissed", [f"{n}:closed" for n in range(MAX_DISMISSED + 1)]),
        ("posting.similar-folded", "yes"),
        ("sidebar.duplicates", "on"),
        ("sidebar.notifications", True),
        ("insights.view", "expert"),
        ("filters.board", ["openai"]),
        ("filters.board", {"companies": ["x" * 100] * 200}),
    ],
)
async def test_an_unknown_name_or_a_value_that_does_not_fit_is_refused_and_the_saved_one_stays(api_client, name, value):
    kept = {"workspace.interviewing": LAYOUT, "pipeline.board-hidden": ["closed"], "filters.board": {"remote": True}}
    for kept_name, kept_value in kept.items():
        assert (await api_client.put(f"{URL}/{kept_name}", json={"value": kept_value})).status_code == 200
    refused = await api_client.put(f"{URL}/{name}", json={"value": value})
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "invalid-input"
    assert await saved(api_client) == kept


@pytest.mark.asyncio
async def test_a_body_without_a_value_is_refused(api_client):
    assert (await api_client.put(f"{URL}/posting.similar-folded", json={})).status_code == 422
    assert (await api_client.put(f"{URL}/posting.similar-folded", json={"value": True, "extra": 1})).status_code == 422


@pytest.mark.asyncio
async def test_a_stored_row_that_no_longer_fits_never_reaches_the_dashboard(db_session):
    await set_setting_dict(db_session, VIEW_CHOICE_PREFIX + "workspace.applied", {"value": {"hidden": "notes", "order": ["next", "<b>", "notes", 3]}})
    await set_setting_dict(db_session, VIEW_CHOICE_PREFIX + "pipeline.board-hidden", {"value": ["closed", "archive"]})
    await set_setting_dict(db_session, VIEW_CHOICE_PREFIX + "posting.similar-folded", {"value": "yes"})
    await set_setting_dict(db_session, VIEW_CHOICE_PREFIX + "workspace.archived", {"value": {"hidden": [], "order": ["notes"]}})
    await set_setting_dict(db_session, VIEW_CHOICE_PREFIX + "filters.board", {"stored": "without a value key"})
    await set_setting_dict(db_session, "view_choice_extra", {"value": True})
    assert await get_view_choices(db_session) == {
        "pipeline.board-hidden": ["closed"],
        "workspace.applied": {"hidden": [], "order": ["next", "notes"]},
    }


@pytest.mark.asyncio
async def test_the_top_picks_screen_keeps_filters_of_its_own_apart_from_the_radars(api_client):
    radar = {"companies": ["openai"], "remote": True}
    picks = {"companies": ["stripe"], "level_band": ["principal"]}
    assert (await api_client.put(f"{URL}/filters.board", json={"value": radar})).status_code == 200

    saved_filters = await api_client.put(f"{URL}/filters.top-picks", json={"value": picks})
    saved_open = await api_client.put(f"{URL}/filters.top-picks:open", json={"value": {"company": True}})

    assert (saved_filters.status_code, saved_open.status_code) == (200, 200), saved_filters.text
    # A reload reads them back, and the Radar's own are as they were.
    assert await saved(api_client) == {
        "filters.board": radar, "filters.top-picks": picks, "filters.top-picks:open": {"company": True},
    }
    # A name no screen has is still refused, and saves nothing.
    for unknown in ("filters.top-picks:closed", "filters.top_picks", "filters.picks"):
        refused = await api_client.put(f"{URL}/{unknown}", json={"value": {}})
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "invalid-input"
    assert set(await saved(api_client)) == {"filters.board", "filters.top-picks", "filters.top-picks:open"}

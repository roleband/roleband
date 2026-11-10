"""The person's own offer over HTTP, against real Postgres.

`/api/profile/offer` keeps the offer the Stock tab's guided questions build,
and `/api/profile/offer/valuations/{company}` the private-company valuations
the offer and the private table read. Both stay on this computer: the routes
are never counted for usage sharing, a refused value stores nothing, and a
stored value the current shape cannot read comes back as nothing rather than
as other figures.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.api_errors import code_of
from tracker.api.usage_counter import ACTIONS, NOT_COUNTED
from tracker.settings_store import set_setting_dict
from tracker.user_profile import offer as store

pytestmark = pytest.mark.asyncio

AMAZON = {
    "inputs": {
        "company": "amazon", "listed": True, "base": 200000, "bonus_pct": 0, "vehicle": "rsu",
        "grant_unit": "dollars", "grant": 400000, "strike": None, "price": None, "vesting": None,
        "sign_on": [100000, 80000],
    },
    "answered": ["company", "base", "stock", "vesting", "sign_on"],
    "started_from": None,
}
ANTHROPIC = {"unit": "per_share", "grant_at": 50, "test_at": 75, "share_count": None}


async def _send(client, method: str, path: str, body: dict | None = None, status: int = 200) -> dict:
    response = await client.request(method, path, json=body)
    assert response.status_code == status, response.text
    return response.json()


def _without_time(body: dict) -> dict:
    """The response with each `saved_at` checked as a time and set aside."""
    offer = body["offer"]
    if offer is not None:
        datetime.fromisoformat(offer.pop("saved_at"))
    for valuation in body["valuations"].values():
        datetime.fromisoformat(valuation.pop("saved_at"))
    return body


async def test_with_nothing_entered_the_offer_reads_empty(api_client):
    assert await _send(api_client, "GET", "/api/profile/offer") == {"offer": None, "valuations": {}}


async def test_an_offer_is_kept_as_entered_and_read_back_on_the_next_visit(api_client):
    saved = _without_time(await _send(api_client, "PUT", "/api/profile/offer", AMAZON))
    assert saved == {"offer": AMAZON, "valuations": {}}
    assert _without_time(await _send(api_client, "GET", "/api/profile/offer")) == saved

    # The next save replaces it whole, and an answer given twice counts once.
    again = {**AMAZON, "answered": ["company", "base", "base"], "started_from": {"company": "amazon", "title": None}}
    body = _without_time(await _send(api_client, "PUT", "/api/profile/offer", again))
    assert body["offer"]["answered"] == ["company", "base"]
    assert body["offer"]["started_from"] == {"company": "amazon", "title": None}


async def test_clearing_the_offer_keeps_the_valuations_the_private_table_reads(api_client):
    await _send(api_client, "PUT", "/api/profile/offer", AMAZON)
    await _send(api_client, "PUT", "/api/profile/offer/valuations/anthropic", ANTHROPIC)
    body = _without_time(await _send(api_client, "DELETE", "/api/profile/offer"))
    assert body == {"offer": None, "valuations": {"anthropic": ANTHROPIC}}


async def test_valuations_are_kept_per_company_and_forgotten_one_at_a_time(api_client):
    openai = {"unit": "company", "grant_at": 300e9, "test_at": 500e9, "share_count": 2e9}
    await _send(api_client, "PUT", "/api/profile/offer/valuations/anthropic", ANTHROPIC)
    body = _without_time(await _send(api_client, "PUT", "/api/profile/offer/valuations/openai", openai))
    assert body["valuations"] == {"anthropic": ANTHROPIC, "openai": openai}

    changed = {**ANTHROPIC, "test_at": 120}
    body = _without_time(await _send(api_client, "PUT", "/api/profile/offer/valuations/anthropic", changed))
    assert body["valuations"]["anthropic"] == changed

    await _send(api_client, "DELETE", "/api/profile/offer/valuations/anthropic")
    body = _without_time(await _send(api_client, "DELETE", "/api/profile/offer/valuations/openai"))
    assert body["valuations"] == {}
    # Forgetting one never kept is no error.
    await _send(api_client, "DELETE", "/api/profile/offer/valuations/stripe")


@pytest.mark.parametrize(
    "change",
    [
        {"base": -1},
        {"grant": 1e13},
        {"vesting": [25, 25, 25, 25, 25]},
        {"vesting": [101, None]},
        {"sign_on": [100000]},
        {"vehicle": "warrants"},
        {"company": "Amazon"},
        {"surprise": 1},
    ],
    ids=["negative", "too-large", "five-years", "over-100-percent", "one-sign-on", "unknown-vehicle",
         "not-a-slug", "unknown-key"],
)
async def test_a_value_the_offer_cannot_hold_is_refused_and_stores_nothing(api_client, change):
    body = {**AMAZON, "inputs": {**AMAZON["inputs"], **change}}
    await _send(api_client, "PUT", "/api/profile/offer", body, status=422)
    assert (await _send(api_client, "GET", "/api/profile/offer"))["offer"] is None


async def test_a_valuation_for_a_name_that_is_not_a_company_slug_is_refused(api_client):
    await _send(api_client, "PUT", "/api/profile/offer/valuations/Anthropic", ANTHROPIC, status=422)
    await _send(api_client, "PUT", "/api/profile/offer/valuations/anthropic", {**ANTHROPIC, "unit": "dollars"}, status=422)
    assert (await _send(api_client, "GET", "/api/profile/offer"))["valuations"] == {}


async def test_a_stored_value_the_shape_cannot_read_comes_back_as_nothing(api_client, db_session):
    await set_setting_dict(db_session, store.OFFER_KEY, {"inputs": {"base": "lots"}, "saved_at": "2026-11-10T00:00:00Z"})
    await set_setting_dict(db_session, store.VALUATIONS_KEY, {
        "anthropic": {**ANTHROPIC, "saved_at": "2026-11-10T00:00:00Z"},
        "openai": {"unit": "per_share", "grant_at": -5},
    })
    await db_session.commit()
    body = _without_time(await _send(api_client, "GET", "/api/profile/offer"))
    assert body == {"offer": None, "valuations": {"anthropic": ANTHROPIC}}


async def test_a_new_company_past_the_cap_is_refused_while_a_kept_one_still_changes(api_client, monkeypatch):
    monkeypatch.setattr(store, "MAX_VALUATIONS", 2)
    for company in ("anthropic", "openai"):
        await _send(api_client, "PUT", f"/api/profile/offer/valuations/{company}", ANTHROPIC)
    refused = await _send(api_client, "PUT", "/api/profile/offer/valuations/stripe", ANTHROPIC, status=422)
    assert code_of(refused) == "invalid-input"
    await _send(api_client, "PUT", "/api/profile/offer/valuations/openai", {**ANTHROPIC, "test_at": 90})
    body = await _send(api_client, "GET", "/api/profile/offer")
    assert sorted(body["valuations"]) == ["anthropic", "openai"]


async def test_no_offer_route_is_ever_a_usage_action():
    routes = [
        ("PUT", "/api/profile/offer"),
        ("DELETE", "/api/profile/offer"),
        ("PUT", "/api/profile/offer/valuations/{company}"),
        ("DELETE", "/api/profile/offer/valuations/{company}"),
    ]
    assert [r for r in routes if r in ACTIONS] == []
    assert all(r in NOT_COUNTED for r in routes)

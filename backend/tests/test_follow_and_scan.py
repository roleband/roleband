"""Following a company on a user-directed source is one decision: the follow
dialog's single answer follows it, records the user's agreement and its "keep
scanning" choice, and asks for its read at once.

`source_policy.direction_wait` is the one rule behind every reader of "is this
company scanned without its user asking"; the tests here hold the readers to it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from tracker.api.routers import companies as companies_router
from tracker.company_discovery import build_company_discovery, has_consented
from tracker.company_store import CompanyError, record_consent
from tracker.config import Settings
from tracker.db.models import (
    ProviderPressureState,
    SourceBinding,
    SyncScheduleState,
    TrackedCompany,
)
from tracker.source_policy import (
    ON_REQUEST,
    USER_DIRECTED,
    collection_access,
    direction_wait,
    scanned_automatically,
)
from tracker.source_review import SOURCE_REVIEWS
from tracker.workflows.schedule_status import waits_for_user

pytestmark = pytest.mark.usefixtures("no_escape")

WORKDAY = SOURCE_REVIEWS["workday"]
AGREED = WORKDAY.directed_fingerprint
WALL = SOURCE_REVIEWS["google"].wall_fingerprint
TEXT = "Workday companies are read when you ask. Keep scanning these companies: on."


@pytest.fixture(autouse=True)
def started(monkeypatch) -> dict[str, list]:
    """What the routes start: role discovery (never spawned here) and scan rings."""
    calls: dict[str, list] = {"role_discovery": [], "scans": []}

    async def role_discovery(_session, slugs, *, max_list, requested_by):
        calls["role_discovery"].append(list(slugs))
        return True

    real_ring = companies_router.scan_requests.ring

    async def ring(session, *, requested_by):
        calls["scans"].append(requested_by)
        await real_ring(session, requested_by=requested_by)

    monkeypatch.setattr(companies_router.job_requests, "ring_role_discovery", role_discovery)
    monkeypatch.setattr(companies_router.scan_requests, "ring", ring)
    return calls


def _nvidia(*, enabled: bool, consent: str | None = None, keep: bool = False) -> TrackedCompany:
    """NVIDIA as a stored row: a built-in on Workday, not on the curated list."""
    return TrackedCompany(
        slug="nvidia", display="NVIDIA", adapter="workday", board_token=None, status="active",
        enabled=enabled, visible=True, source="builtin", consent_fingerprint=consent,
        scan_on_schedule=keep,
    )


async def _queued(db_session) -> set[str]:
    """Companies whose binding carries a manual request: a read asked for now."""
    rows = await db_session.execute(
        select(SourceBinding.company_slug)
        .join(SyncScheduleState, SyncScheduleState.binding_id == SourceBinding.id)
        .where(SyncScheduleState.manual_requested_at.is_not(None))
    )
    return set(rows.scalars())


async def _row(db_session, slug: str) -> TrackedCompany | None:
    db_session.expire_all()
    return await db_session.get(TrackedCompany, slug)


def _discovered(body: dict, slug: str) -> dict:
    return next(c for c in body["companies"] if c["slug"] == slug)


# --------------------------------------------------------------------------- #
# One rule, every reader
# --------------------------------------------------------------------------- #

# (provider collected through, company, walled, directed). nvidia through
# `google` is both: its declared provider is Workday and the route it presents
# is walled, the case a recipe makes.
SOURCES = [
    ("greenhouse", "stripe", False, False),
    ("google", "google", True, False),
    ("workday", "nvidia", False, True),
    ("google", "nvidia", True, True),
]


@pytest.mark.parametrize(("provider", "company", "walled", "directed"), SOURCES)
@pytest.mark.parametrize("consent", [None, WALL, AGREED], ids=["none", "wall", "directed"])
@pytest.mark.parametrize("keep", [False, True], ids=["on-request", "keep-scanning"])
@pytest.mark.parametrize("denied", [False, True], ids=["allowed", "denied"])
def test_every_reader_answers_with_the_one_rule(provider, company, walled, directed, consent, keep, denied):
    settings = Settings(sync_policy_denied_providers=frozenset({provider}) if denied else frozenset())
    wall_open = not walled or consent == WALL
    direction_open = not directed or (consent is not None and keep)
    expected_wait = None if direction_open else (USER_DIRECTED if consent is None else ON_REQUEST)

    assert direction_wait(provider, company, consent, keep) == expected_wait
    assert scanned_automatically(provider, company, consent, scan_on_schedule=keep, settings=settings) == (
        not denied and wall_open and direction_open
    )
    # The roster's rule; an operator's deny holds the provider apart from it
    # (`BLOCKED_PROVIDER_STATES`), so it is asked with the provider allowed.
    target = {"adapter": provider, "consent": consent, "scan_on_schedule": keep}
    waits = waits_for_user(company, target, settings=Settings(), manual_requested=False)
    assert waits == ("walled" if not wall_open else expected_wait)
    # A manual request admits everything but a wall without its consent.
    asked = waits_for_user(company, target, settings=Settings(), manual_requested=True)
    assert asked == (None if wall_open else "walled")


def test_an_agreement_to_a_directed_source_never_unlocks_a_wall():
    """nvidia presented through the walled route: an agreement that showed no
    wall leaves the wall, and the wall's fetch tier, shut."""
    shut = collection_access("google", company="nvidia", consent=AGREED)
    assert shut.walled and shut.denied
    opened = collection_access("google", company="nvidia", consent=WALL)
    assert not opened.denied and opened.tier == SOURCE_REVIEWS["google"].fetch_tier
    google = TrackedCompany(slug="google", display="Google", adapter="google", consent_fingerprint=AGREED)
    assert not has_consented("google", google)


def test_the_agreement_records_the_rule_shown_and_the_choice():
    row = _nvidia(enabled=False)
    record_consent(row, TEXT, locale="en", scan_on_schedule=False, now=datetime(2026, 11, 9, tzinfo=UTC))
    assert (row.consent_fingerprint, row.scan_on_schedule, row.consent_text) == (AGREED, False, TEXT)
    assert has_consented("nvidia", row)

    google = TrackedCompany(slug="google", display="Google", adapter="google", enabled=False)
    with pytest.raises(CompanyError):
        record_consent(google, "x", scan_on_schedule=False)  # a wall has no "read on request"
    stripe = TrackedCompany(slug="stripe", display="Stripe", adapter="greenhouse", enabled=False)
    with pytest.raises(CompanyError):
        record_consent(stripe, "x")  # nothing to agree to


def test_discovery_says_a_company_is_directed_and_what_was_chosen():
    state = build_company_discovery(tracked={"nvidia": _nvidia(enabled=True, consent=AGREED, keep=True)})
    nvidia = _discovered(state, "nvidia")
    assert (nvidia["directed"], nvidia["consented"], nvidia["scan_on_schedule"], nvidia["wall"]) == (
        True, True, True, None,
    )
    adobe = _discovered(state, "adobe")
    assert (adobe["directed"], adobe["consented"], adobe["scan_on_schedule"]) == (True, False, False)
    assert _discovered(state, "stripe")["directed"] is False


# --------------------------------------------------------------------------- #
# Following: one answer, one request
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["adobe", "nvidia"], ids=["created-by-the-follow", "stored-unfollowed"])
async def test_a_directed_company_is_never_followed_without_the_agreement(db_session, api_client, started, slug):
    """adobe has no row until followed (a catalog company is created already
    followed); nvidia has a stored, unfollowed one. Both are refused alike."""
    db_session.add(_nvidia(enabled=False))
    await db_session.commit()

    refused = await api_client.put("/api/companies/selection", json={"follow": [slug]})

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["params"] == {"kind": "directed", "company": slug}
    row = await _row(db_session, slug)
    assert row is None or (row.enabled is False and row.consented_at is None), "a refusal applies nothing"
    assert started == {"role_discovery": [], "scans": []}, "and starts nothing"


@pytest.mark.asyncio
async def test_a_walled_company_the_follow_would_create_needs_its_consent_too(db_session, api_client):
    """google-deepmind has no stored row: the follow creates it already
    followed, which once skipped the consent check."""
    refused = await api_client.put("/api/companies/selection", json={"follow": ["google-deepmind"]})
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["params"] == {"kind": "walled", "company": "google-deepmind"}
    assert await _row(db_session, "google-deepmind") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [True, False], ids=["keep-scanning", "on-request"])
async def test_follow_and_scan_follows_agrees_and_asks_for_the_read_at_once(db_session, api_client, started, keep):
    applied = await api_client.put("/api/companies/selection", json={
        "follow": ["adobe"],
        "consents": [{"slug": "adobe", "text": TEXT, "scan_on_schedule": keep}],
    })

    assert applied.status_code == 200, applied.text
    adobe = _discovered(applied.json(), "adobe")
    assert (adobe["enabled"], adobe["consented"], adobe["scan_on_schedule"]) == (True, True, keep)
    assert applied.json()["reads_waiting"] == []
    row = await _row(db_session, "adobe")
    assert row is not None and (row.consent_fingerprint, row.consent_text) == (AGREED, TEXT)
    assert await _queued(db_session) == {"adobe"}, "the dialog's answer is the user asking for this read"
    assert started["scans"], "and the scan is asked for now, not at the next tick"
    assert started["role_discovery"] == [["adobe"]]

    target = {"adapter": "workday", "consent": AGREED, "scan_on_schedule": keep}
    after_its_read = waits_for_user("adobe", target, settings=Settings(), manual_requested=False)
    assert after_its_read == (None if keep else ON_REQUEST)


@pytest.mark.asyncio
async def test_a_bulk_follow_needs_every_agreement_and_queues_only_the_directed(db_session, api_client):
    db_session.add(_nvidia(enabled=False))
    await db_session.commit()
    follow = ["stripe", "google-deepmind", "nvidia"]
    wall_only = [{"slug": "google-deepmind", "text": "Its careers site limits automated collection."}]

    refused = await api_client.put("/api/companies/selection", json={"follow": follow, "consents": wall_only})
    assert refused.status_code == 409
    assert refused.json()["detail"]["params"]["kind"] == "directed"
    assert await _row(db_session, "stripe") is None, "nothing of a refused selection is applied"

    agreed = [*wall_only, {"slug": "nvidia", "text": TEXT, "scan_on_schedule": True}]
    applied = await api_client.put("/api/companies/selection", json={"follow": follow, "consents": agreed})
    assert applied.status_code == 200, applied.text
    assert all(_discovered(applied.json(), slug)["enabled"] for slug in follow)
    assert await _queued(db_session) == {"nvidia"}, "the others join the first-scan drain on their own"


@pytest.mark.asyncio
async def test_a_company_followed_before_the_dialog_stays_and_waits_until_agreed(db_session, api_client):
    db_session.add(_nvidia(enabled=True))
    await db_session.commit()

    other = await api_client.put("/api/companies/selection", json={"follow": ["stripe"]})
    assert other.status_code == 200, "an unrelated change never fails on it"
    nvidia = _discovered(other.json(), "nvidia")
    assert (nvidia["enabled"], nvidia["consented"]) == (True, False)
    assert await _queued(db_session) == set()
    target = {"adapter": "workday", "consent": None, "scan_on_schedule": False}
    assert waits_for_user("nvidia", target, settings=Settings(), manual_requested=False) == USER_DIRECTED

    # Its row's Scan opens the dialog; the answer is sent with the follow.
    agreed = await api_client.put("/api/companies/selection", json={
        "follow": ["nvidia"], "consents": [{"slug": "nvidia", "text": TEXT}],
    })
    assert agreed.status_code == 200, agreed.text
    assert _discovered(agreed.json(), "nvidia")["consented"]
    assert await _queued(db_session) == {"nvidia"}


@pytest.mark.asyncio
async def test_following_again_asks_nothing_and_reads_at_once(db_session, api_client):
    db_session.add(_nvidia(enabled=True, consent=AGREED, keep=False))
    await db_session.commit()
    assert (await api_client.put("/api/companies/selection", json={"unfollow": ["nvidia"]})).status_code == 200
    row = await _row(db_session, "nvidia")
    assert row is not None and row.consent_fingerprint == AGREED, "unfollowing keeps the agreement"

    again = await api_client.put("/api/companies/selection", json={"follow": ["nvidia"]})

    assert again.status_code == 200, again.text
    assert await _queued(db_session) == {"nvidia"}


@pytest.mark.asyncio
async def test_a_paused_provider_says_the_read_waits(db_session, api_client):
    db_session.add(ProviderPressureState(pressure_key="workday", state="paused"))
    await db_session.commit()

    applied = await api_client.put("/api/companies/selection", json={
        "follow": ["adobe"], "consents": [{"slug": "adobe", "text": TEXT}],
    })

    assert applied.status_code == 200, applied.text
    assert _discovered(applied.json(), "adobe")["enabled"], "the follow is saved"
    assert applied.json()["reads_waiting"] == ["adobe"]
    assert await _queued(db_session) == set()


# --------------------------------------------------------------------------- #
# The other ways in
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_adding_a_directed_company_needs_the_agreement(db_session, api_client, started):
    refused = await api_client.post("/api/companies", json={"catalog_slug": "salesforce"})
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["params"] == {"kind": "directed", "company": "salesforce"}
    assert await _row(db_session, "salesforce") is None
    assert started["role_discovery"] == [], "nothing is read without the agreement"

    added = await api_client.post("/api/companies", json={
        "catalog_slug": "salesforce", "consent": {"text": TEXT, "scan_on_schedule": False},
    })
    assert added.status_code == 201, added.text
    row = await _row(db_session, "salesforce")
    assert row is not None and (row.enabled, row.consent_fingerprint, row.scan_on_schedule) == (True, AGREED, False)
    assert await _queued(db_session) == {"salesforce"}
    assert started["role_discovery"] == [["salesforce"]]


@pytest.mark.asyncio
async def test_keep_scanning_is_a_directed_companys_choice_once_agreed(db_session, api_client):
    db_session.add_all([
        _nvidia(enabled=True),
        TrackedCompany(slug="stripe", display="Stripe", adapter="greenhouse", board_token="stripe",
                       status="active", enabled=True, visible=True, source="catalog"),
    ])
    await db_session.commit()

    plain = await api_client.patch("/api/companies/stripe", json={"scan_on_schedule": True})
    assert plain.status_code == 400, "a company not on a user-directed source has no such choice"
    unagreed = await api_client.patch("/api/companies/nvidia", json={"scan_on_schedule": True})
    assert unagreed.status_code == 409, "the choice is part of the agreement"
    assert unagreed.json()["detail"]["params"]["kind"] == "directed"

    row = await _row(db_session, "nvidia")
    assert row is not None
    row.consent_fingerprint = AGREED
    await db_session.commit()
    on = await api_client.patch("/api/companies/nvidia", json={"scan_on_schedule": True})
    assert on.status_code == 200, on.text
    row = await _row(db_session, "nvidia")
    assert row is not None and row.scan_on_schedule is True
    assert await _queued(db_session) == {"nvidia"}, "turned on, it joins the schedule read, not already stale"

    off = await api_client.patch("/api/companies/nvidia", json={"scan_on_schedule": False})
    assert off.status_code == 200
    assert (await _row(db_session, "nvidia")).scan_on_schedule is False


@pytest.mark.asyncio
async def test_the_switch_cannot_follow_a_directed_company_without_the_dialog(db_session, api_client):
    db_session.add(_nvidia(enabled=False))
    await db_session.commit()
    response = await api_client.patch("/api/companies/nvidia", json={"enabled": True})
    assert response.status_code == 409
    assert response.json()["detail"]["params"]["kind"] == "directed"


@pytest.mark.asyncio
async def test_moving_a_followed_company_onto_a_directed_source_needs_the_agreement(
    db_session, api_client, monkeypatch
):
    async def answers(_board, _client) -> bool:
        return True

    monkeypatch.setattr(companies_router, "board_answers", answers)
    db_session.add(TrackedCompany(slug="acme", display="Acme", adapter="greenhouse", board_token="acme",
                                  status="active", enabled=True, visible=True, source="url"))
    await db_session.commit()

    moved = await api_client.put("/api/companies/acme/board", json={
        "adapter": "workday", "board_token": "acme.wd1.myworkdayjobs.com|External",
    })

    assert moved.status_code == 409, moved.text
    assert moved.json()["detail"]["params"] == {"kind": "directed", "company": "acme"}
    row = await _row(db_session, "acme")
    assert row is not None and row.adapter == "greenhouse", "a refused move leaves the company where it was"


@pytest.mark.asyncio
async def test_queueing_followed_reads_of_nobody_queues_nobody(scratch_scope):
    from tracker.workflows.scheduler import queue_followed_reads

    async with scratch_scope() as session:
        assert await queue_followed_reads(session, []) == []
        assert await queue_followed_reads(session, ["stripe", "apple"]) == [], "only directed companies"
    async with scratch_scope() as session:
        assert (await session.scalars(
            select(SyncScheduleState).where(SyncScheduleState.manual_requested_at.is_not(None))
        )).first() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [True, False], ids=["keep-scanning", "on-request"])
async def test_a_scope_save_queues_a_directed_company_only_when_it_keeps_scanning(scratch_scope, keep):
    from tracker.workflows.scheduler import queue_promoted_reconciliation

    async with scratch_scope() as session:
        session.add(_nvidia(enabled=True, consent=AGREED, keep=keep))
        await session.commit()
        queued = await queue_promoted_reconciliation(session, ["nvidia"])
    assert queued == (["nvidia"] if keep else [])


@pytest.mark.asyncio
async def test_the_directory_sweep_reads_no_directed_company(monkeypatch):
    """The directory holds no Workday board today; a fake entry proves the
    sweep would refuse one before asking anything of its host."""
    from tracker.company_directory import DirectoryCompany
    from tracker.connectors import ADAPTER_REGISTRY
    from tracker.platform.breaker import BreakerPool
    from tracker.platform.ratelimit import RateLimiterPool
    from tracker.workflows import directory_sweep

    built: list[str] = []

    class Refusing(ADAPTER_REGISTRY["workday"]):
        async def __aenter__(self):
            built.append("opened")
            raise AssertionError("the sweep opened a Workday board")

    monkeypatch.setitem(ADAPTER_REGISTRY, "workday", Refusing)
    entry = DirectoryCompany(slug="acme-wd", display="Acme", named_by="board", adapter="workday",
                             board_token="acme.wd1.myworkdayjobs.com|External", board_region=None, rank=0)

    check = await directory_sweep.check_company(
        entry, None, limiter_pool=RateLimiterPool(), breaker_pool=BreakerPool(),  # type: ignore[arg-type]
        stall_seconds=60, budget_seconds=60,
    )

    assert (check.outcome, check.scanned, built) == (directory_sweep.REFUSED, 0, [])
    assert "user's direction" in (check.error or "")


@pytest.mark.asyncio
async def test_role_discovery_reads_no_directed_company_before_its_agreement(db_session, scratch_scope, monkeypatch):
    """A company followed before the follow dialog asked is counted only once
    its user scans it or agrees; "Count now" never opens its board first."""
    from tracker.workflows import discover_roles

    opened: list[str] = []

    def refusing(slug, *args, **kwargs):
        opened.append(slug)
        raise AssertionError(f"role discovery opened {slug}")

    monkeypatch.setattr(discover_roles, "build_adapter", refusing)
    monkeypatch.setattr(discover_roles, "_YIELD_WINDOW_SECONDS", 0)
    db_session.add(_nvidia(enabled=True))
    await db_session.commit()

    result = await discover_roles.discover(companies=["nvidia"])

    skipped = result["companies"]["nvidia"]
    assert (skipped["status"], skipped["scanned"], opened) == ("unattempted", 0, [])
    assert "agreement" in skipped["policy_reason"]

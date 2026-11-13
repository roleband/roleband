"""The synthetic seeder's safety properties, held to the code.

`scripts/seed_synthetic.py` exists so a candidate build can be validated without
scraping anyone. It writes to a cluster that is per-USER and
shared by every checkout (`docs/development.md`), so "it cannot touch a row it did not write"
is not a nicety here — it is the property that makes the script safe to ship at
all, and the one a public repository's contributors will lean on hardest.

Every claim here is checked by planting the break, not by inspection: disable
the guard and the first test fails; widen `--clear`'s filter and the third
fails; switch the persist call to `RECONCILE` and the last fails.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from scripts.seed_synthetic import (
    _TASK_POSTINGS,
    _TASK_PURSUITS,
    SYNTHETIC_PREFIX,
    TRIAL_SEEDED_KEY,
    clear,
    export_workspace,
    seed,
    seed_trial,
    task_req_id,
)
from tracker.db.models import Favorite, Job, Pursuit, PursuitEvent, ScrapeRun, SourceBinding
from tracker.intelligence_runtime.disclosed_comp import extract_disclosed_comp
from tracker.notifications.pursuit_due import overdue_pursuit_clause
from tracker.schema import UNPLACED_BASIS_VALUES
from tracker.settings_store import get_enabled_bands, set_enabled_bands, set_setting_dict
from tracker.taxonomy.locations import pay_country

# Small on purpose: these assert behaviour, not throughput, and each seeded row
# costs an enrichment pass.
_COUNT = 8


def _a_row_the_seeder_must_never_touch() -> Job:
    """A job with no synthetic prefix — i.e. indistinguishable from real data."""
    return Job(
        company="google",
        req_id="REAL-12345",
        dedupe_key="google:REAL-12345",
        title="A real posting",
        url="https://example.com/real",
        level_band="senior",
    )


@pytest.mark.asyncio
async def test_it_refuses_a_database_holding_rows_it_did_not_write(db_session):
    db_session.add(_a_row_the_seeder_must_never_touch())
    await db_session.flush()

    with pytest.raises(SystemExit) as refusal:
        await seed(db_session, _COUNT, seed_value=1, derived=False)

    assert SYNTHETIC_PREFIX in str(refusal.value)
    # The refusal must come BEFORE any write, not after a partial seed.
    assert await db_session.scalar(select(func.count()).select_from(Job)) == 1


@pytest.mark.asyncio
async def test_it_seeds_an_empty_database_and_marks_every_row(db_session):
    total = await seed(db_session, _COUNT, seed_value=1, derived=False)

    assert total == _COUNT
    req_ids = (await db_session.scalars(select(Job.req_id))).all()
    assert len(req_ids) == _COUNT
    assert all(req.startswith(SYNTHETIC_PREFIX) for req in req_ids)
    # A dataset whose comp and level columns are empty renders a comp-shaped UI
    # with nothing in it, and would validate a candidate build of nothing. Our
    # pay is US pay, and a level we cannot place is never priced: every posting
    # in the US alone at a placed level is priced, and every other one is not.
    jobs = (await db_session.execute(select(Job.location_groups, Job.level_basis, Job.comp_median))).all()
    us = [comp for groups, basis, comp in jobs if pay_country(groups) == "US" and basis not in UNPLACED_BASIS_VALUES]
    unpriced = [comp for groups, basis, comp in jobs
                if pay_country(groups) != "US" or basis in UNPLACED_BASIS_VALUES]
    assert us and unpriced  # control: the seed has both
    assert all(comp is not None for comp in us)
    assert all(comp is None for comp in unpriced)
    assert await db_session.scalar(
        select(func.count()).select_from(Job).where(Job.level_band.isnot(None))
    ) == _COUNT


@pytest.mark.asyncio
async def test_clear_removes_its_own_rows_and_leaves_everything_else(db_session):
    await seed(db_session, _COUNT, seed_value=1, derived=False)
    db_session.add(_a_row_the_seeder_must_never_touch())
    await db_session.flush()

    removed = await clear(db_session)

    assert removed == _COUNT
    survivors = (await db_session.scalars(select(Job.req_id))).all()
    assert survivors == ["REAL-12345"]


@pytest.mark.asyncio
async def test_seeding_twice_upserts_rather_than_duplicating(db_session):
    first = await seed(db_session, _COUNT, seed_value=1, derived=False)
    second = await seed(db_session, _COUNT, seed_value=1, derived=False)

    assert first == second == _COUNT
    assert await db_session.scalar(select(func.count()).select_from(Job)) == _COUNT


@pytest.mark.asyncio
async def test_a_trial_is_seeded_on_its_first_start_only(db_session):
    """A later start leaves the trial user's bands and scan history as they are, also once the
    postings are gone."""
    first = await seed_trial(db_session)
    await set_enabled_bands(db_session, ["mid"])
    scans = await db_session.scalar(select(func.count()).select_from(ScrapeRun))

    assert first > 0
    assert await seed_trial(db_session) == first
    assert await get_enabled_bands(db_session) == {"mid"}
    assert await db_session.scalar(select(func.count()).select_from(ScrapeRun)) == scans

    await clear(db_session)
    assert await seed_trial(db_session) == 0
    assert await get_enabled_bands(db_session) == {"mid"}
    assert await db_session.scalar(select(func.count()).select_from(ScrapeRun)) == scans


@pytest.mark.asyncio
@pytest.mark.parametrize("postings", ["kept", "removed"])
async def test_a_trial_seeded_without_the_record_is_not_seeded_again(db_session, postings):
    """A database `seed` filled has no record of a trial's seeding; its user's bands stay, whether
    or not its postings are still there."""
    await seed(db_session, _COUNT, seed_value=1, derived=False)
    await set_enabled_bands(db_session, ["mid"])
    if postings == "removed":
        await clear(db_session)
    scans = await db_session.scalar(select(func.count()).select_from(ScrapeRun))

    assert await seed_trial(db_session) == (_COUNT if postings == "kept" else 0)
    assert await get_enabled_bands(db_session) == {"mid"}
    assert await db_session.scalar(select(func.count()).select_from(ScrapeRun)) == scans
    await clear(db_session)
    assert await seed_trial(db_session) == 0
    assert await get_enabled_bands(db_session) == {"mid"}


@pytest.mark.asyncio
async def test_a_trial_holding_only_a_posting_of_its_own_is_left_as_it_is(db_session):
    """No synthetic postings, scan or saved bands, but a posting `seed` would refuse to write
    beside: the trial starts on it instead of failing to seed."""
    db_session.add(_a_row_the_seeder_must_never_touch())
    await db_session.flush()

    assert await seed_trial(db_session) == 0
    assert (await db_session.scalars(select(Job.req_id))).all() == ["REAL-12345"]
    assert await db_session.scalar(select(func.count()).select_from(ScrapeRun)) == 0
    assert await seed_trial(db_session) == 0


@pytest.mark.asyncio
async def test_it_leaves_no_trace_in_binding_health(db_session):
    """Discovery mode, so fabricated rows never advance a binding's health.

    Health is what the closure gate reads: it is the system's belief about
    whether a source can be trusted to say a requisition is gone. Seeded rows
    must not be able to move it in either direction. `_record_source_health`
    runs only under `RECONCILE`, so this fails the moment the persist call is
    switched — which the weaker "binding never activates" assertion did NOT,
    because a synthetic collection is not `list_complete` and so could not have
    activated a binding under either mode.
    """
    await seed(db_session, _COUNT, seed_value=1, derived=False)

    bindings = (await db_session.scalars(select(SourceBinding))).all()
    assert bindings, "the seeder should have bootstrapped bindings"
    assert all(b.activated_at is None for b in bindings)


async def _task_job(session, key: str) -> Job:
    return await session.scalar(select(Job).where(Job.req_id == task_req_id(key)))


@pytest.mark.asyncio
async def test_agent_tasks_add_their_postings_and_the_users_pursuits(db_session):
    """The corpus names these rows by key; each must exist, carry the prefix,
    and hang its pursuit from the pursuit seam as the user's own write."""
    total = await seed(db_session, _COUNT, seed_value=1, derived=False, agent_tasks=True)

    assert total == _COUNT + len(_TASK_POSTINGS)
    for spec in _TASK_POSTINGS:
        job = await _task_job(db_session, spec["key"])
        assert job is not None and job.req_id.startswith(SYNTHETIC_PREFIX)
    pursuits = (await db_session.scalars(select(Pursuit))).all()
    assert len(pursuits) == len(_TASK_PURSUITS)
    assert await db_session.scalar(select(func.count()).select_from(Favorite)) == len(_TASK_PURSUITS)
    assert set((await db_session.scalars(select(PursuitEvent.actor))).all()) == {"user"}
    # Two follow-ups are overdue, one is due later and one pursuit has none:
    # a count that ignored the due date, or the stage, would not land on 2.
    overdue = await db_session.scalar(
        select(func.count(Pursuit.id)).where(overdue_pursuit_clause(datetime.now(UTC)))
    )
    assert overdue == 2
    assert any(p.next_action is None for p in pursuits)
    inject = await _task_job(db_session, "INJECT")
    assert "save_opportunity" in (inject.description_text or "")


@pytest.mark.asyncio
async def test_agent_tasks_state_pay_only_where_the_posting_text_does(db_session):
    """The stated range comes from the real disclosed-pay reader, and the
    posting beside it, priced by an estimate, states nothing."""
    await seed(db_session, _COUNT, seed_value=1, derived=False, agent_tasks=True)
    stated = await _task_job(db_session, "STATED")
    estimate_only = await _task_job(db_session, "ESTONLY")

    await extract_disclosed_comp(db_session, [stated.id, estimate_only.id], page_band=None)
    await db_session.flush()

    assert (stated.disclosed_base_min, stated.disclosed_base_max) == (212_000, 264_500)
    assert stated.comp_median is not None and stated.comp_median != stated.disclosed_base_max
    assert (estimate_only.disclosed_base_min, estimate_only.disclosed_base_max) == (None, None)
    assert estimate_only.comp_median is not None


@pytest.mark.asyncio
async def test_clear_removes_the_task_postings_with_their_pursuits(db_session):
    await seed(db_session, _COUNT, seed_value=1, derived=False, agent_tasks=True)

    await clear(db_session)

    assert await db_session.scalar(select(func.count()).select_from(Job)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Pursuit)) == 0


@pytest.mark.asyncio
async def test_export_writes_every_row_with_its_hash_and_no_embedding(db_session, tmp_path):
    await seed(db_session, _COUNT, seed_value=1, derived=False, agent_tasks=True)

    manifest = await export_workspace(db_session, tmp_path)

    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    assert manifest["tables"]["jobs"]["rows"] == _COUNT + len(_TASK_POSTINGS)
    assert manifest["tables"]["pursuits"]["rows"] == len(_TASK_PURSUITS)
    for table in manifest["tables"].values():
        body = (tmp_path / table["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == table["sha256"]
        assert len(body.splitlines()) == table["rows"]
    jobs = [json.loads(line) for line in (tmp_path / "jobs.ndjson").read_text().splitlines()]
    assert all(row["req_id"].startswith(SYNTHETIC_PREFIX) for row in jobs)
    assert not {"embedding", "search_vector"} & set(jobs[0])
    assert manifest["task_postings"]["STATED"] == task_req_id("STATED")


@pytest.mark.asyncio
async def test_export_refuses_a_database_holding_a_real_row(db_session, tmp_path):
    await seed(db_session, _COUNT, seed_value=1, derived=False, agent_tasks=True)
    db_session.add(_a_row_the_seeder_must_never_touch())
    await db_session.flush()

    with pytest.raises(SystemExit) as refusal:
        await export_workspace(db_session, tmp_path / "out")

    assert SYNTHETIC_PREFIX in str(refusal.value)
    assert not (tmp_path / "out").exists()


@pytest.mark.asyncio
async def test_export_refuses_a_trial_database_and_keeps_other_settings_behind(db_session, tmp_path):
    """A desktop trial's database is its user's once seeded; elsewhere only the
    radar's scope and the agent switches leave with the postings."""
    await seed(db_session, _COUNT, seed_value=1, derived=False, agent_tasks=True)
    await set_setting_dict(db_session, "some_personal_setting", {"note": "mine"})

    manifest = await export_workspace(db_session, tmp_path / "out")
    keys = {json.loads(line)["key"] for line in (tmp_path / "out" / "app_settings.ndjson").read_text().splitlines()}
    assert "enabled_seniority_bands" in keys and "some_personal_setting" not in keys
    assert manifest["tables"]["app_settings"]["rows"] == len(keys)

    await set_setting_dict(db_session, TRIAL_SEEDED_KEY, {"seeded": True})
    with pytest.raises(SystemExit, match="trial"):
        await export_workspace(db_session, tmp_path / "again")

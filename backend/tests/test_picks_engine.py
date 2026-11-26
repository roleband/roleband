"""The engine's half of Top picks: hard rules, the queue, the brief, health and setup.

Everything here is decided by code before any model reads a posting. The
workspace is two followed companies and one the person does not follow, with
postings that differ in the fields the checkable rules read: level, stated pay
and its basis, place and work mode.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import not_, select

from tests.factories import make_company, make_job
from tracker.config import get_settings
from tracker.db.models import (
    CandidateBackground,
    Favorite,
    Job,
    JobFeedback,
    JobLineage,
    PickBrief,
    PickRun,
    PickVerdict,
)
from tracker.picks import background, mode, queue, runs, setup
from tracker.picks import brief as briefs
from tracker.picks.background import DocumentError, Reading
from tracker.picks.brief import BriefBody, BriefError, Patch, RevisionMoved
from tracker.picks.health import RunFact, health
from tracker.picks.rules import ruled_out
from tracker.settings_store import get_top_picks_settings, update_top_picks_settings

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
ON_SINCE = NOW - timedelta(days=3)


def _posting(req_id: str, **over) -> Job:
    return make_job(req_id, **{"first_seen": NOW - timedelta(hours=6), "last_seen": NOW, "content_hash": f"h-{req_id}",
                               **over})


@pytest_asyncio.fixture
async def board(db_session, scratch_scope) -> dict[str, Job]:
    """Postings by key. `staff`, `principal`, `senior`, `nopay`, `total` and
    `unplaced` are on the Board; the rest are not, each for one reason."""
    db_session.add_all([
        make_company("google", "Google"), make_company("stripe", "Stripe"),
        make_company("acme", "Acme", enabled=False),
    ])
    jobs = {
        "staff": _posting(
            "staff", disclosed_base_min=240_000, disclosed_base_max=310_000, disclosed_currency="USD",
            disclosed_pay_basis="base", disclosed_pay_period="year",
        ),
        "principal": _posting(
            "principal", company="stripe", level_band="principal", workplace_type="remote", locations=["Remote, USA"],
            location_groups=["remote_us"], disclosed_base_min=300_000, disclosed_base_max=380_000,
            disclosed_currency="USD", disclosed_pay_basis="base", disclosed_pay_period="year",
        ),
        "senior": _posting(
            "senior", level_band="senior", disclosed_base_min=180_000, disclosed_base_max=220_000,
            disclosed_currency="USD", disclosed_pay_basis="base", disclosed_pay_period="year",
        ),
        "nopay": _posting(
            "nopay", company="stripe", workplace_type="hybrid", locations=["New York, NY, USA"],
            location_groups=["nyc"],
        ),
        # A total-pay band under any base floor: a base rule reads base bands only.
        "total": _posting(
            "total", company="stripe", disclosed_base_min=150_000, disclosed_base_max=200_000,
            disclosed_currency="USD", disclosed_pay_basis="total", disclosed_pay_period="year",
            workplace_type="unknown", locations=[], location_groups=[],
        ),
        # States no level the engine can place; its band is a sort default.
        "unplaced": _posting("unplaced", company="stripe", level_band="mid", level_basis="none"),
        "unfollowed": _posting("unfollowed", company="acme"),
        "closed": _posting("closed", status="closed", closed_at=NOW - timedelta(hours=1)),
        "out_of_scope": _posting("out_of_scope", in_scope=False),
        "dismissed": _posting("dismissed"),
        "before_on": _posting("before_on", first_seen=ON_SINCE - timedelta(days=5)),
    }
    db_session.add_all(jobs.values())
    await db_session.flush()
    db_session.add(JobFeedback(job_id=jobs["dismissed"].id, verdict="dismissed", reason="wrong_role"))
    await db_session.commit()
    return jobs


def _body(*rules: dict, **parts) -> BriefBody:
    return BriefBody.model_validate({
        "rules": [{"id": f"r{index}", "text": "A hard rule", "check": check} for index, check in enumerate(rules, 1)],
        **parts,
    })


async def _kept(session, body: BriefBody) -> set[str]:
    """The Board postings the checkable rules of `body` leave."""
    stmt = queue.candidates(await queue.board_filters(session), trial=True, active_version=1, now=NOW)
    return set((await session.scalars(stmt.with_only_columns(Job.req_id).where(not_(ruled_out(body))))).all())


ON_BOARD = {"staff", "principal", "senior", "nopay", "total", "unplaced", "before_on"}


# --------------------------------------------------------------------------- #
# Checkable hard rules
# --------------------------------------------------------------------------- #


async def test_a_base_floor_rules_out_a_stated_base_below_it_and_nothing_that_states_none(db_session, board):
    kept = await _kept(db_session, _body({"form": "min_base", "amount": 250_000}))

    # The senior band tops out at 220,000: ruled out. The staff band tops out at 310,000: kept.
    assert "senior" not in kept and "staff" in kept
    # No pay stated, or a total band (200,000 at most), is never a base below the floor.
    assert {"nopay", "total", "unplaced"} <= kept
    # Control: without the rule the senior posting is there.
    assert await _kept(db_session, _body()) == ON_BOARD


async def test_a_base_floor_rules_out_only_a_band_whose_top_is_below_it(db_session, board):
    # "From 150,000": a band with no top says nothing of where it ends.
    board["staff"].disclosed_base_min, board["staff"].disclosed_base_max = 150_000, None
    # One figure as both ends, and a band stated only by its top: both end under the floor.
    board["senior"].disclosed_base_min = board["senior"].disclosed_base_max = 180_000
    board["nopay"].disclosed_base_max, board["nopay"].disclosed_currency = 150_000, "USD"
    board["nopay"].disclosed_pay_basis, board["nopay"].disclosed_pay_period = "base", "year"
    await db_session.commit()

    kept = await _kept(db_session, _body({"form": "min_base", "amount": 200_000}))

    assert "staff" in kept, "a band with no top is never below a floor"
    assert {"senior", "nopay"}.isdisjoint(kept)


async def test_a_base_floor_reads_only_a_yearly_band_in_its_own_currency(db_session, board):
    board["senior"].disclosed_currency = "EUR"
    board["staff"].disclosed_pay_period = "hour"
    board["staff"].disclosed_base_min, board["staff"].disclosed_base_max = 90, 120
    await db_session.commit()

    kept = await _kept(db_session, _body({"form": "min_base", "amount": 250_000}))

    assert {"senior", "staff"} <= kept, "a euro band and an hourly rate are not a yearly dollar base"
    assert "senior" not in await _kept(db_session, _body({"form": "min_base", "amount": 250_000, "currency": "EUR"}))


async def test_a_band_with_no_stated_period_reads_yearly_by_its_size_in_dollars(db_session, board):
    # JPY 400,000 to 500,000 is about USD 3,000: no yearly pay is that small, so
    # the band is not read as a year's base whatever its raw figure.
    board["senior"].disclosed_currency, board["senior"].disclosed_pay_period = "JPY", None
    board["senior"].disclosed_base_min, board["senior"].disclosed_base_max = 400_000, 500_000
    # JPY 5,000,000 to 6,000,000 is about USD 40,000: a year's base, under the floor.
    board["staff"].disclosed_currency, board["staff"].disclosed_pay_period = "JPY", None
    board["staff"].disclosed_base_min, board["staff"].disclosed_base_max = 5_000_000, 6_000_000
    await db_session.commit()

    kept = await _kept(db_session, _body({"form": "min_base", "amount": 8_000_000, "currency": "JPY"}))

    assert "senior" in kept, "a band too small for a year is not a yearly base below the floor"
    assert "staff" not in kept


async def test_a_total_floor_reads_the_total_band_and_leaves_base_bands_alone(db_session, board):
    kept = await _kept(db_session, _body({"form": "min_total", "amount": 250_000}))

    assert "total" not in kept
    assert {"senior", "staff", "nopay"} <= kept


async def test_a_level_floor_rules_out_lower_levels_and_keeps_a_posting_that_states_none(db_session, board):
    kept = await _kept(db_session, _body({"form": "min_level", "level": "principal"}))

    assert kept == {"principal", "unplaced"}, "an unplaced level is `mid` only as a sort default, never a stated one"
    assert "senior" in await _kept(db_session, _body({"form": "min_level", "level": "senior"}))


async def test_a_places_rule_keeps_remote_only_where_remote_is_accepted_and_a_posting_with_no_place(db_session, board):
    here = {"form": "places", "places": ["silicon_valley"]}

    strict = await _kept(db_session, _body(here))
    with_remote = await _kept(db_session, _body({**here, "remote_ok": True}))

    assert "nopay" not in strict and "nopay" not in with_remote, "New York is not in the list"
    assert "principal" not in strict and "principal" in with_remote
    assert "total" in strict, "a posting that names no place is not ruled out by place"


async def test_with_remote_accepted_a_posting_elsewhere_that_states_no_work_mode_is_kept(db_session, board):
    board["nopay"].workplace_type = "unknown"
    await db_session.commit()
    here = {"form": "places", "places": ["silicon_valley"]}

    assert "nopay" not in await _kept(db_session, _body(here)), "remote not accepted: New York is out"
    assert "nopay" in await _kept(db_session, _body({**here, "remote_ok": True})), "it may be remote: the judge reads it"


async def test_a_work_mode_rule_keeps_a_posting_that_states_no_mode(db_session, board):
    kept = await _kept(db_session, _body({"form": "work_modes", "modes": ["remote", "hybrid"]}))

    assert {"principal", "nopay", "total"} <= kept
    assert "staff" not in kept and "senior" not in kept


async def test_an_avoided_company_is_ruled_out_and_two_rules_remove_their_union(db_session, board):
    kept = await _kept(db_session, _body(
        {"form": "avoid_companies", "companies": ["stripe"]}, {"form": "min_level", "level": "staff"},
    ))

    assert kept == {"staff", "before_on"}


async def test_a_rule_of_an_unknown_form_or_level_is_refused():
    with pytest.raises(ValidationError):
        _body({"form": "max_commute", "minutes": 30})
    with pytest.raises(ValidationError):
        _body({"form": "min_level", "level": "wizard"})
    with pytest.raises(ValidationError):
        _body({"form": "min_base", "amount": 0})


# --------------------------------------------------------------------------- #
# The queue
# --------------------------------------------------------------------------- #


async def _queue(session, body: BriefBody | None = None, *, trial: bool = False, version: int = 1) -> list[str]:
    stmt = queue.candidates(
        await queue.board_filters(session), trial=trial, active_version=version, now=NOW,
    )
    return [job.req_id for job in await queue.best_first(session, stmt, body or BriefBody(), limit=50)]


async def test_the_queue_is_every_open_role_on_the_board_those_open_before_the_mode_included(db_session, board):
    waiting = await _queue(db_session)

    # `before_on` was open days before the mode was turned on: a person who has just set up is not
    # made to wait for new roles to arrive.
    assert set(waiting) == {"staff", "principal", "senior", "nopay", "total", "unplaced", "before_on"}
    # Each absent for its own reason: not followed, closed, out of scope, Not for me.
    assert not {"unfollowed", "closed", "out_of_scope", "dismissed"} & set(waiting)


@pytest.mark.parametrize(("closest", "furthest"), [("principal", "staff"), ("staff", "principal")])
async def test_the_queue_reads_the_closest_fit_first_and_a_role_with_no_embedding_last(
    db_session, board, monkeypatch, closest, furthest,
):
    dim = get_settings().embedding_dim
    intent = [1.0] + [0.0] * (dim - 1)

    async def stored(_session):
        return {"vector": intent}

    async def composed(_session, statement):
        return statement

    monkeypatch.setattr(queue, "get_intent_embedding", stored)
    monkeypatch.setattr(queue, "build_intent_vector", composed)
    board[closest].embedding = intent
    board[furthest].embedding = [0.0, 1.0] + [0.0] * (dim - 2)
    await db_session.commit()

    waiting = await _queue(db_session)
    # Both orders are asked for, so the recency tie-break cannot pass for fit.
    assert waiting[:2] == [closest, furthest]
    assert len(waiting) == 7


async def test_a_trial_takes_every_open_role_judged_or_not_and_still_none_the_board_hides(db_session, board):
    await _verdict(db_session, board["staff"])

    assert "staff" not in await _queue(db_session)
    trial = await _queue(db_session, trial=True)
    assert {"staff", "before_on"} <= set(trial)
    assert not {"unfollowed", "closed", "out_of_scope", "dismissed"} & set(trial)


async def _run(session, *, trial: bool = False, version: int = 1) -> PickRun:
    run = PickRun(id=runs.new_run_id(), brief_version=version, trial=trial, started_at=NOW - timedelta(hours=2))
    session.add(run)
    await session.flush()
    return run


async def _verdict(session, job: Job, verdict: str = "pass", *, version: int = 1, trial: bool = False,
                   age: timedelta = timedelta(hours=1), **over) -> PickVerdict:
    run = await _run(session, trial=trial, version=version)
    row = PickVerdict(**{
        "job_id": job.id, "content_hash": job.content_hash or "", "brief_version": version, "verdict": verdict,
        "pass_code": "not_real" if verdict == "pass" else None,
        "against_baseline": None if verdict == "pass" else "better",
        "run_id": run.id, "trial": trial, "created_at": NOW - age, **over,
    })
    session.add(row)
    await session.commit()
    return row


async def test_a_judged_posting_leaves_the_queue_until_its_text_changes(db_session, board):
    verdict_id = (await _verdict(db_session, board["staff"])).id
    assert "staff" not in await _queue(db_session)

    board["staff"].content_hash = "h-staff-rewritten"
    await db_session.commit()

    assert "staff" in await _queue(db_session), "new text is a new case"
    # Control: the verdict itself is untouched, so only the hash decided it.
    db_session.expire_all()
    held = await db_session.get(PickVerdict, verdict_id)
    assert held is not None and (held.content_hash, held.superseded_at) == ("h-staff", None)


async def test_a_trials_verdict_never_counts_as_judged(db_session, board):
    await _verdict(db_session, board["staff"], trial=True)

    assert "staff" in await _queue(db_session)


async def test_one_verdict_covers_a_duplicate_stack_and_only_its_newest_posting_is_queued(db_session, board):
    lineage = JobLineage(company="google", root_job_id=board["staff"].id, size=2, open_members=2,
                         first_seen=NOW - timedelta(days=1), last_seen=NOW)
    db_session.add(lineage)
    await db_session.flush()
    board["staff"].lineage_id, board["staff"].lineage_seq, board["staff"].lineage_role = lineage.id, 1, "original"
    board["senior"].lineage_id, board["senior"].lineage_seq, board["senior"].lineage_role = lineage.id, 2, "repost"
    await db_session.commit()

    waiting = await _queue(db_session)
    assert "senior" in waiting and "staff" not in waiting, "the stack is judged once, through its newest posting"

    await _verdict(db_session, board["senior"])
    assert not {"staff", "senior"} & set(await _queue(db_session))
    # Control: a posting outside the stack is still waiting.
    assert "principal" in await _queue(db_session)


async def test_a_newer_posting_the_board_does_not_show_never_stands_in_for_its_stack(db_session, board):
    lineage = JobLineage(company="google", root_job_id=board["staff"].id, size=2, open_members=2,
                         first_seen=NOW - timedelta(days=1), last_seen=NOW)
    db_session.add(lineage)
    await db_session.flush()
    board["staff"].lineage_id, board["staff"].lineage_seq, board["staff"].lineage_role = lineage.id, 1, "original"
    board["senior"].lineage_id, board["senior"].lineage_seq, board["senior"].lineage_role = lineage.id, 2, "repost"
    db_session.add(JobFeedback(job_id=board["senior"].id, verdict="dismissed", reason="wrong_level"))
    await db_session.commit()

    waiting = await _queue(db_session)

    assert "senior" not in waiting, "marked Not for me: off the Board"
    assert "staff" in waiting, "the stack's newest posting the Board shows is judged"


async def test_a_newer_brief_takes_a_second_look_only_where_it_could_change_the_answer(db_session, board):
    await _verdict(db_session, board["staff"], "pick")
    await _verdict(db_session, board["principal"], "pick")
    db_session.add(Favorite(job_id=board["principal"].id))
    await _verdict(db_session, board["senior"], "near_miss", age=timedelta(days=2))
    await _verdict(db_session, board["nopay"], "near_miss", age=timedelta(days=20))
    await _verdict(db_session, board["total"], "pass", pass_code="not_better")
    await _verdict(db_session, board["unplaced"], "pass", pass_code="hard_rule")

    # Under the brief that judged them every case is closed; only the role never judged waits.
    assert await _queue(db_session, version=1) == ["before_on"]

    again = set(await _queue(db_session, version=2)) - {"before_on"}
    # A pick nobody reacted to, a recent near miss, and a recent posting passed as no better.
    assert again == {"staff", "senior", "total"}
    # Not: a pick the person saved, a near miss older than the window, a pass for another reason.
    assert not {"principal", "nopay", "unplaced"} & again


async def test_counts_say_what_the_rules_remove_and_what_waits(db_session, board):
    body = _body({"form": "min_level", "level": "staff"}, {"form": "avoid_companies", "companies": ["stripe"]})
    stmt = queue.candidates(
        await queue.board_filters(db_session), trial=False, active_version=1, now=NOW,
    )

    counted = await queue.counts(db_session, stmt, body, since=ON_SINCE)

    assert (counted.waiting, counted.ruled_out_by_rules) == (2, 5)
    # r1 removes the senior posting; r2 the four at Stripe. A posting both would remove counts under both.
    assert counted.by_rule == {"r1": 1, "r2": 4}
    # `before_on` was open eight days ago, but nothing judged roles then: it has waited since the mode was on.
    assert counted.oldest_waiting_since == ON_SINCE
    assert (await queue.counts(db_session, stmt, body)).oldest_waiting_since == board["before_on"].first_seen
    assert (await queue.counts(db_session, stmt, BriefBody())).waiting == 7


async def test_volume_falls_when_a_level_rule_is_added_and_returns_when_it_is_removed(db_session, board):
    without = await queue.volume(db_session, BriefBody(), now=NOW)
    with_rule = await queue.volume(db_session, _body({"form": "min_level", "level": "principal"}), now=NOW)
    again = await queue.volume(db_session, _body(), now=NOW)

    # Eight roles arrived in scope at followed companies: seven on one day (one of them closed since)
    # and one eight days ago. The role marked Not for me does not count. A normal day is the median.
    assert (without.expected_per_day, without.busiest_day) == (4, 7)
    # Only the principal role and the one stating no level pass the rule: two on the busy day, none on the other.
    assert (with_rule.expected_per_day, with_rule.busiest_day) == (1, 2)
    assert [(share.rule, share.removes_share) for share in with_rule.by_rule] == [("r1", 0.75)]
    assert (again.expected_per_day, again.busiest_day) == (4, 7)


# --------------------------------------------------------------------------- #
# The brief
# --------------------------------------------------------------------------- #


async def _patch(session, parts: dict, *, if_revision: int, **over) -> PickBrief:
    row = await briefs.patch(session, Patch(parts=parts, reason="Said in setup.", if_revision=if_revision, **over))
    await session.commit()
    return row


async def test_items_get_ids_that_are_kept_and_never_given_to_another_item(db_session, scratch_scope):
    first = await _patch(db_session, {"pulls": [{"text": "Owns a whole product", "weight": 3},
                                                {"text": "A team that ships"}]}, if_revision=0)
    assert [pull["id"] for pull in first.body["pulls"]] == ["p1", "p2"]

    second = await _patch(db_session, {"pulls": [{"id": "p1", "text": "Owns a whole product line", "weight": 3},
                                                 {"text": "AI as the product"}]}, if_revision=1)

    # p2 was removed. A verdict may still name it, so the new pull is p3, never p2 again.
    assert [(pull["id"], pull["text"]) for pull in second.body["pulls"]] == [
        ("p1", "Owns a whole product line"), ("p3", "AI as the product"),
    ]
    with pytest.raises(BriefError) as refused:
        await briefs.patch(db_session, Patch(parts={"pulls": [{"id": "p2", "text": "Back again"}]},
                                             reason="x", if_revision=2))
    assert refused.value.code == "unknown_item"


async def test_a_new_draft_beside_the_active_brief_counts_its_ids_on_from_it(db_session, scratch_scope):
    await _patch(db_session, {"pulls": [{"text": "Owns a whole product"}, {"text": "A team that ships"}]},
                 if_revision=0, activate=True)

    draft = await _patch(db_session, {"pulls": [{"text": "AI as the product"}]}, if_revision=0, target="draft")

    # p1 already names an item of the active brief, which a verdict may cite.
    assert [pull["id"] for pull in draft.body["pulls"]] == ["p3"]


async def test_a_brief_written_after_remove_takes_no_revision_one_read_before_it_held(
    db_session, scratch_scope, tmp_path,
):
    await _patch(db_session, {"urgency": "open"}, if_revision=0, activate=True)
    await mode.remove(db_session, NOW, directory=tmp_path)
    await db_session.commit()

    fresh = await _patch(db_session, {"urgency": "active"}, if_revision=0, activate=True)

    assert fresh.revision == 2
    with pytest.raises(RevisionMoved):
        await briefs.patch(db_session, Patch(parts={"budget": 4}, reason="Read before Remove.", if_revision=1))
    await db_session.rollback()
    # A second Remove keeps the floor it found.
    await mode.remove(db_session, NOW, directory=tmp_path)
    await db_session.commit()
    assert (await _patch(db_session, {"urgency": "open"}, if_revision=0)).revision == 3


async def test_a_part_given_replaces_that_part_and_a_part_left_out_stays(db_session, scratch_scope):
    await _patch(db_session, {"urgency": "open", "budget": 5}, if_revision=0)

    row = await _patch(db_session, {"budget": 3}, if_revision=1)

    assert (row.body["urgency"], row.body["budget"]) == ("open", 3)
    assert row.status == "draft" and row.revision == 2 and row.version == 1


async def test_a_change_against_a_revision_that_moved_is_refused_and_writes_nothing(db_session, scratch_scope):
    await _patch(db_session, {"urgency": "open"}, if_revision=0)

    with pytest.raises(RevisionMoved) as moved:
        await briefs.patch(db_session, Patch(parts={"urgency": "active"}, reason="x", if_revision=0))
    await db_session.rollback()

    assert (moved.value.expected, moved.value.current) == (0, 1)
    assert (await briefs.draft(db_session)).body["urgency"] == "open"


async def test_activating_the_draft_supersedes_the_active_brief_and_a_later_change_is_a_new_version(
    db_session, scratch_scope,
):
    await _patch(db_session, {"urgency": "open"}, if_revision=0, activate=True)
    changed = await _patch(db_session, {"budget": 5}, if_revision=1)

    # A revision is never reused, so one read from the version before cannot apply to this one.
    assert (changed.version, changed.status, changed.revision) == (2, "active", 2)
    assert changed.body["urgency"] == "open", "the new version starts from the one before"
    statuses = dict((await db_session.execute(select(PickBrief.version, PickBrief.status))).all())
    assert statuses == {1: "superseded", 2: "active"}

    # Starting over: a draft beside the active brief, then made active.
    draft = await _patch(db_session, {"urgency": "active"}, if_revision=0, target="draft")
    assert draft.revision == 3, "a new draft takes a revision no version has had"
    await _patch(db_session, {}, if_revision=draft.revision, activate=True, summary="Actively looking.")
    statuses = dict((await db_session.execute(select(PickBrief.version, PickBrief.status))).all())
    assert statuses == {1: "superseded", 2: "superseded", 3: "active"}


async def test_a_routine_write_cannot_change_a_hard_rule_and_the_same_write_by_the_person_can(
    db_session, scratch_scope,
):
    await _patch(db_session, {"rules": [{"text": "No on-call"}]}, if_revision=0, activate=True)
    stricter = {"rules": [{"id": "r1", "text": "No on-call"}, {"text": "No travel"}]}

    with pytest.raises(BriefError) as refused:
        await briefs.patch(db_session, Patch(parts=stricter, reason="Two picks removed for travel.", if_revision=1,
                                             routine=True))
    await db_session.rollback()
    assert refused.value.code == "needs_the_person" and refused.value.details == {"parts": ["rules"]}
    assert len((await briefs.active(db_session)).body["rules"]) == 1
    # The summary is the person's own account of the brief, as the rules are.
    with pytest.raises(BriefError) as summary:
        await briefs.patch(db_session, Patch(parts={"pulls": [{"text": "Remote first"}]}, reason="Learned.",
                                             if_revision=1, routine=True, summary="Wants remote above all."))
    await db_session.rollback()
    assert summary.value.code == "needs_the_person" and summary.value.details == {"parts": ["summary"]}

    learned = await _patch(
        db_session,
        {"proposed_rules": [{"text": "No travel", "reason": "Two picks were removed for travel."}],
         "pulls": [{"text": "Remote first", "source": "reaction"}]},
        if_revision=1, routine=True,
    )
    assert learned.made_by == "routine" and learned.body["proposed_rules"][0]["id"] == "x1"
    assert len(learned.body["rules"]) == 1, "a proposal is not a rule"

    by_person = await _patch(db_session, stricter, if_revision=learned.revision)
    assert [rule["id"] for rule in by_person.body["rules"]] == ["r1", "r2"] and by_person.made_by == "person"


# --------------------------------------------------------------------------- #
# The background
# --------------------------------------------------------------------------- #

READING = Reading.model_validate({
    "current": {"title": "Senior Product Manager", "employer": "Acme", "level": "Senior"},
    "years": 9, "strengths": ["Platform products", "Pricing"],
})


async def test_each_saved_reading_is_a_new_version_and_only_a_confirmed_one_is_the_persons(db_session, scratch_scope):
    first = await background.save_reading(db_session, READING, source="spoken", document_id=None, confirmed=False,
                                          host="claude-code", now=NOW)
    second = await background.save_reading(db_session, READING, source="spoken", document_id=None, confirmed=True,
                                           host="claude-code", now=NOW + timedelta(minutes=5))
    await db_session.commit()

    assert (first.version, first.confirmed_at, second.version) == (1, None, 2)
    assert second.confirmed_at == NOW + timedelta(minutes=5)
    assert (await background.newest(db_session)).id == second.id
    assert (await db_session.get(CandidateBackground, first.id)).superseded_at == NOW + timedelta(minutes=5)


async def test_a_document_is_stored_once_as_a_private_file_and_never_in_the_database(db_session, scratch_scope, tmp_path):
    content = b"%PDF-1.7 Dana Reyes, Senior Product Manager"

    row, stored = await background.store_document(db_session, filename="/Users/dana/CV 2026.PDF", content=content,
                                                  now=NOW, directory=tmp_path)
    again, stored_again = await background.store_document(db_session, filename="cv-copy.pdf", content=content,
                                                          now=NOW, directory=tmp_path)
    await db_session.commit()

    assert (row.filename, row.media_type, row.size_bytes) == ("CV 2026.PDF", "application/pdf", len(content))
    path = tmp_path / row.stored_name
    assert path.read_bytes() == content and "CV" not in row.stored_name
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    assert (stored, stored_again, again.id) == (True, False, row.id)
    assert [item.name for item in tmp_path.iterdir()] == [row.stored_name], "the same bytes are not written twice"


async def test_a_document_whose_write_rolls_back_leaves_no_file_and_a_committed_one_stays(
    db_session, scratch_scope, tmp_path,
):
    content = b"%PDF-1.7 Dana Reyes"
    await background.store_document(db_session, filename="cv.pdf", content=content, now=NOW, directory=tmp_path)
    assert len(list(tmp_path.iterdir())) == 1

    await db_session.rollback()

    assert list(tmp_path.iterdir()) == [], "no file is left without the row Remove reads"
    row, stored = await background.store_document(db_session, filename="cv.pdf", content=content, now=NOW,
                                                  directory=tmp_path)
    await db_session.commit()
    await db_session.rollback()
    assert stored is True and [item.name for item in tmp_path.iterdir()] == [row.stored_name]


async def test_a_remove_that_rolled_back_leaves_rows_whose_file_the_same_bytes_put_back(
    db_session, scratch_scope, tmp_path,
):
    content = b"%PDF-1.7 Dana Reyes"
    row, _ = await background.store_document(db_session, filename="cv.pdf", content=content, now=NOW, directory=tmp_path)
    await db_session.commit()
    await background.remove_all(db_session, directory=tmp_path)
    await db_session.rollback()
    assert list(tmp_path.iterdir()) == [], "Remove deleted the file before its transaction failed"

    again, stored = await background.store_document(db_session, filename="cv.pdf", content=content, now=NOW,
                                                    directory=tmp_path)
    await db_session.commit()

    assert (again.id, stored) == (row.id, True)
    assert (tmp_path / row.stored_name).read_bytes() == content


async def test_a_document_whose_write_fails_leaves_no_part_of_it(db_session, scratch_scope, tmp_path, monkeypatch):
    real = os.fdopen

    class Full:
        def __init__(self, descriptor, mode):
            self.handle = real(descriptor, mode)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def write(self, data):
            self.handle.write(data[:4])
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(background.os, "fdopen", Full)
    with pytest.raises(OSError):
        await background.store_document(db_session, filename="cv.pdf", content=b"%PDF-1.7 Dana Reyes", now=NOW,
                                        directory=tmp_path)

    assert list(tmp_path.iterdir()) == []


async def test_remove_deletes_every_file_in_the_documents_folder_and_nothing_a_link_points_to(
    db_session, scratch_scope, tmp_path,
):
    folder, outside = tmp_path / "documents", tmp_path / "elsewhere.txt"
    outside.write_text("kept")
    await background.store_document(db_session, filename="cv.pdf", content=b"%PDF-1.7 Dana", now=NOW, directory=folder)
    await db_session.commit()
    # A file a failed write left behind has no row to find it by.
    (folder / "0123456789abcdef-00000000.pdf").write_bytes(b"%PDF-1.7 Dana, an older copy")
    (folder / "link.txt").symlink_to(outside)

    _, documents = await background.remove_all(db_session, directory=folder)
    await db_session.commit()

    assert documents == 1
    assert [item.name for item in folder.iterdir()] == ["link.txt"]
    assert outside.read_text() == "kept"


@pytest.mark.parametrize(("filename", "content", "code"), [
    ("cv.exe", b"MZ", "unsupported_type"),
    ("cv", b"text", "unsupported_type"),
    ("cv.pdf", b"", "empty"),
    ("cv.pdf", b"x" * (background.MAX_DOCUMENT_BYTES + 1), "too_large"),
])
async def test_a_file_the_engine_does_not_store_is_refused_and_leaves_nothing(
    db_session, scratch_scope, tmp_path, filename, content, code,
):
    with pytest.raises(DocumentError) as refused:
        await background.store_document(db_session, filename=filename, content=content, now=NOW, directory=tmp_path)

    assert refused.value.code == code
    assert list(tmp_path.iterdir()) == []


async def test_a_reading_cannot_name_a_document_that_is_not_stored(db_session, scratch_scope):
    with pytest.raises(DocumentError) as refused:
        await background.save_reading(db_session, READING, source="document", document_id=41, confirmed=True,
                                      host=None, now=NOW)

    assert refused.value.code == "unknown_document"


# --------------------------------------------------------------------------- #
# Health and setup: pure readings
# --------------------------------------------------------------------------- #


def _fact(outcome: str | None, hours_ago: float) -> RunFact:
    at = NOW - timedelta(hours=hours_ago)
    return RunFact(outcome=outcome, started_at=at, finished_at=at if outcome else None)


@pytest.mark.parametrize(("state", "newest", "last_finished", "oldest_waiting", "expected"), [
    ("off", _fact("finished", 1), 1, 50, "off"),
    ("never_set_up", None, None, None, "off"),
    ("on", None, None, None, "never_ran"),
    ("on", _fact("finished", 1), 1, None, "healthy"),
    # Roles waiting 40 hours, but a run finished an hour ago: it is doing its job.
    ("on", _fact("finished", 1), 1, 40, "healthy"),
    # A run 40 hours ago and a role waiting 30: not yet late.
    ("on", _fact("finished", 40), 40, 30, "healthy"),
    ("on", _fact("finished", 40), 40, 37, "late"),
    # Nothing waits, however long ago the last run was.
    ("on", _fact("finished", 400), 400, None, "healthy"),
    ("on", _fact("stopped", 1), 30, None, "stopped_early"),
    ("on", _fact("abandoned", 1), None, None, "stopped_early"),
])
async def test_health_reads_the_runs_and_the_waiting_roles(state, newest, last_finished, oldest_waiting, expected):
    assert health(
        state=state, newest=newest,
        last_finished_at=NOW - timedelta(hours=last_finished) if last_finished is not None else None,
        oldest_waiting_since=NOW - timedelta(hours=oldest_waiting) if oldest_waiting is not None else None,
        now=NOW,
    ) == expected


async def test_a_run_left_open_past_the_bound_reads_as_abandoned_before_anything_closes_it():
    fresh = PickRun(id="run_a", brief_version=1, started_at=NOW - timedelta(minutes=30))
    stale = PickRun(id="run_b", brief_version=1, started_at=NOW - timedelta(hours=3))

    assert runs.as_fact(fresh, NOW).outcome is None
    assert runs.as_fact(stale, NOW).outcome == "abandoned"


async def test_health_reads_the_run_that_ended_last_whichever_started_last(db_session, scratch_scope):
    await update_top_picks_settings(db_session, state="on", enabled_at=NOW - timedelta(days=1))
    db_session.add_all([
        PickRun(id="run_early", brief_version=1, started_at=NOW - timedelta(minutes=50),
                finished_at=NOW - timedelta(minutes=5), outcome="finished"),
        PickRun(id="run_late", brief_version=1, started_at=NOW - timedelta(minutes=40),
                finished_at=NOW - timedelta(minutes=20), outcome="stopped"),
    ])
    await db_session.commit()

    standing = await mode.standing(db_session, await get_top_picks_settings(db_session), None, NOW)

    assert standing.health == "healthy"
    assert standing.newest.id == "run_late", "the newest run started is still the one shown"


async def test_an_opening_that_reaches_the_lock_late_moves_nothing_back(db_session, scratch_scope):
    await mode.mark_opened(db_session, NOW)
    await mode.mark_opened(db_session, NOW - timedelta(minutes=2))

    assert (await get_top_picks_settings(db_session)).last_opened_at == NOW
    # Remove still clears it.
    await update_top_picks_settings(db_session, last_opened_at=None)
    assert (await get_top_picks_settings(db_session)).last_opened_at is None


@pytest.mark.parametrize("cap", [2.5, True, 0, 5001])
async def test_the_daily_limit_is_a_whole_number_in_range(db_session, scratch_scope, cap):
    with pytest.raises(ValueError):
        await update_top_picks_settings(db_session, daily_cap=cap)


def _facts(**over) -> setup.Facts:
    return setup.Facts(**{
        "background_confirmed": False, "body": BriefBody(), "has_active_brief": False, "trial_finished": False,
        "routine_ran": False, "has_postings": True, **over,
    })


async def test_setup_names_the_first_stage_whose_fact_is_missing():
    assert setup.progress(_facts()).next_step == "background"
    assert setup.progress(_facts(background_confirmed=True)).next_step == "situation"
    # Urgency alone does not end `situation`: the baseline is the other half.
    half = _facts(background_confirmed=True, body=BriefBody(urgency="open"))
    assert setup.progress(half).next_step == "situation"

    body = BriefBody.model_validate({
        "urgency": "open", "baseline": {"title": "Senior PM"}, "pulls": [{"id": "p1", "text": "Scope"}],
        # The person has no hard rules: asked and answered, so the stage is done.
        "rules": [],
    })
    progress = setup.progress(_facts(background_confirmed=True, body=body))
    assert progress.next_step == "tradeoffs"
    assert progress.saved_parts == ("urgency", "baseline", "rules", "pulls")
    assert {step.id for step in progress.steps if step.done} == {"connect", "background", "situation", "bar", "rules"}


async def test_calibration_and_the_trial_wait_for_roles_and_setup_goes_on_past_them():
    body = BriefBody.model_validate({
        "urgency": "open", "baseline": {}, "pulls": [], "rules": [], "tradeoffs": [], "targets": {}, "budget": 3,
    })
    waiting = setup.progress(_facts(background_confirmed=True, body=body, has_active_brief=True, has_postings=False))
    with_roles = setup.progress(_facts(background_confirmed=True, body=body, has_active_brief=True))

    assert (waiting.next_step, waiting.deferred) == ("routine", ("calibration", "trial"))
    assert (with_roles.next_step, with_roles.deferred) == ("calibration", ())

    done = setup.progress(_facts(
        background_confirmed=True, has_active_brief=True, trial_finished=True, routine_ran=True,
        body=body.model_copy(update={"examples": [briefs.Example(job=7, reaction="wanted", reason="Platform scope")]}),
    ))
    assert done.next_step == "done" and all(step.done for step in done.steps)

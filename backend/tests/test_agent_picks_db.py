"""An assistant chooses the person's top picks: setup, a run of the judge, and what the person does next.

Every call goes through the agent routes, and every read-back opens a fresh
session. The workspace is two followed companies with four open roles that
differ in level and stated pay, a confirmed background and an active brief
whose pulls and rules the verdicts' reasons name.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.barriers import until_waiting
from tests.factories import make_company, make_job
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations import picks as picks_operations
from tracker.agents.operations.outcomes import outcome
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.api.agent_operations import IDEMPOTENCY_KEY_HEADER, MAX_BODY_BYTES, PREFIX
from tracker.db.models import (
    AgentActivity,
    CandidateDocument,
    CommandReceipt,
    Favorite,
    Job,
    JobFeedback,
    JobPlaceSet,
    JobPlaceSetMember,
    PickBrief,
    PickRun,
    PickVerdict,
    ScrapeRun,
    TrackedCompany,
)
from tracker.picks import background as background_store
from tracker.picks import brief as briefs
from tracker.picks import mode as picks_mode
from tracker.picks.background import Reading
from tracker.picks.brief import Patch
from tracker.picks.health import ABANDONED_AFTER
from tracker.picks.lock import lock_picks
from tracker.picks.verdicts import REASON_MAX
from tracker.platform import agent_hosts
from tracker.settings_store import get_top_picks_settings, update_top_picks_settings

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

HOST = {"X-RoleBand-Host": "claude-code"}
_keys = iter(range(10_000))


def _key() -> str:
    return f"idk_picks_{next(_keys):06d}"


def _fresh(db_session) -> AsyncSession:
    return async_sessionmaker(db_session.bind, expire_on_commit=False)()


async def _read(api_client, path: str, **params):
    response = await api_client.get(f"{PREFIX}{path}", params=params, headers=HOST)
    return response, response.json()


async def _write(api_client, method: str, path: str, body: dict[str, Any], *, key: str | None = None):
    response = await api_client.request(
        method, f"{PREFIX}{path}", json=body, headers={IDEMPOTENCY_KEY_HEADER: key or _key(), **HOST},
    )
    return response, response.json()


def _data(response, body: dict) -> dict:
    assert response.status_code == 200 and body["ok"] is True, body
    return body["data"]


def _refused(response, body: dict, code: str) -> dict:
    assert body["ok"] is False, body
    assert body["error"]["code"] == code, body["error"]
    assert response.status_code == outcome(code).http_status
    return body["error"]


BRIEF = {
    "urgency": "not_looking",
    "baseline": {"title": "Senior Product Manager", "level": "senior", "employer": "Acme", "pay": 210_000},
    "rules": [{"text": "No on-call"}, {"text": "Base under 200,000", "check": {"form": "min_base", "amount": 200_000}}],
    "pulls": [{"text": "Owns a whole product", "weight": 3}, {"text": "A step up in level", "weight": 3}],
    "tradeoffs": [{"text": "Scope over pay when pay matches today"}],
    "targets": {"companies": ["Stripe"], "kinds": [], "avoid": []},
    "budget": 3,
}

STAFF_TEXT = "Own the pricing platform end to end. You will lead a team of six product managers."


@pytest_asyncio.fixture
async def workspace(db_session, scratch_scope) -> dict[str, Any]:
    """Four open roles on the Board, a confirmed background, an active brief
    (version 1) and the mode on since three days ago."""
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    now = datetime.now(UTC)
    seen = now - timedelta(hours=5)
    db_session.add_all([make_company("google", "Google"), make_company("stripe", "Stripe")])
    jobs = {
        "staff": make_job(
            "staff", title="Staff Product Manager, Pricing", first_seen=seen, last_seen=now, content_hash="h-staff",
            description_text=STAFF_TEXT, disclosed_base_min=240_000, disclosed_base_max=310_000,
            disclosed_currency="USD", disclosed_pay_basis="base", disclosed_pay_period="year",
            comp_base_median=987_654, comp_median=1_234_567,
        ),
        "principal": make_job(
            "principal", company="stripe", title="Principal Product Manager, Risk", level_band="principal",
            first_seen=seen, last_seen=now, content_hash="h-principal", description_text="Lead risk products.",
            comp_base_median=876_543,
        ),
        "lead": make_job(
            "lead", company="stripe", title="Group Product Manager, Billing", level_band="principal",
            first_seen=seen, last_seen=now, content_hash="h-lead", description_text="Lead billing.",
            comp_base_median=765_432,
        ),
        # States a base band that tops out under the brief's floor: the engine rules it out.
        "underpaid": make_job(
            "underpaid", title="Staff Product Manager, Ads", first_seen=seen, last_seen=now, content_hash="h-under",
            disclosed_base_min=150_000, disclosed_base_max=190_000, disclosed_currency="USD",
            disclosed_pay_basis="base", disclosed_pay_period="year",
        ),
    }
    db_session.add_all(jobs.values())
    await background_store.save_reading(
        db_session, Reading.model_validate({"current": {"title": "Senior Product Manager"}, "years": 9}),
        source="spoken", document_id=None, confirmed=True, host="claude-code", now=now,
    )
    await briefs.patch(db_session, Patch(
        parts=BRIEF, reason="Setup.", if_revision=0, summary="Not looking. Wants a whole product.", activate=True,
    ))
    await update_top_picks_settings(db_session, state="on", enabled_at=now - timedelta(days=3))
    await db_session.commit()
    return {"jobs": {key: job.id for key, job in jobs.items()}, "now": now}


def _reason(opening: str | None, rest: str, item: str = "p1") -> dict:
    return {"opening": opening, "rest": rest, "brief_item": item} if opening is not None else {
        "rest": rest, "brief_item": item,
    }


def _pick(job: int, reasons: list[dict] | None = None, **over) -> dict:
    return {
        "job": job, "verdict": "pick", "against_baseline": "better",
        "reasons": reasons if reasons is not None else [
            _reason("Staff level", ", one step above your Senior role today.", "p2"),
            _reason("240,000 to 310,000 base", ", above the 210,000 you hold.", "baseline"),
        ],
        **over,
    }


async def _begin(api_client, **body) -> dict:
    return _data(*await _write(api_client, "POST", "/picks/runs", body))


async def _decide(api_client, run: dict, verdicts: list[dict], *, key: str | None = None):
    return await _write(
        api_client, "POST", "/picks/verdicts",
        {"run": run["run"], "brief_version": run["brief"]["version"], "verdicts": verdicts}, key=key,
    )


async def _verdicts(db_session) -> list[PickVerdict]:
    async with _fresh(db_session) as session:
        return list((await session.scalars(select(PickVerdict).order_by(PickVerdict.id))).all())


async def _outcomes(api_client, run: dict, verdicts: list[dict]) -> dict[int, str | None]:
    """Each posting's refusal code, or None when its verdict was saved."""
    data = _data(*await _decide(api_client, run, verdicts))
    # One result for each posting sent, none twice and none left out.
    assert sorted(item["job"] for item in data["results"]) == sorted(verdict["job"] for verdict in verdicts)
    for item in data["results"]:
        assert (item["outcome"], item["refusal"] is None) in {("saved", True), ("refused", False)}, item
    return {item["job"]: item["refusal"] for item in data["results"]}


# --------------------------------------------------------------------------- #
# A whole run
# --------------------------------------------------------------------------- #


async def test_a_run_hands_out_the_roles_worth_judging_and_its_verdicts_are_read_back(api_client, db_session, workspace):
    jobs = workspace["jobs"]

    run = await _begin(api_client, model="claude-fable-5-2")

    assert {posting["job"] for posting in run["batch"]} == {jobs["staff"], jobs["principal"], jobs["lead"]}
    assert run["counts"] == {"waiting": 3, "ruled_out_by_rules": 1, "handed": 3, "held_back": 0}
    assert [posting["fit_rank"] for posting in run["batch"]] == [1, 2, 3]
    staff = next(posting for posting in run["batch"] if posting["job"] == jobs["staff"])
    assert (staff["company"], staff["level"], staff["text"]) == ("Google", "staff", STAFF_TEXT)
    assert staff["stated_pay"] == {
        "base_min": 240_000, "base_max": 310_000, "currency": "USD", "basis": "base", "period": "year",
    }
    assert staff["continue_with"] == [
        {"operation": "opportunities.get", "arguments": {"opportunity_id": jobs["staff"], "view": "detail"}},
    ]
    # The judge reads the rules only reading can check; the engine already applied the floor.
    assert run["brief"]["rules"] == [{"id": "r1", "text": "No on-call", "judged": True}]
    assert run["brief"]["rules_applied_by_engine"] == ["r2"]
    assert run["budget"]["per_month"] == 3 and run["budget"]["picks_this_month"] == 0

    decided = _data(*await _decide(api_client, run, [
        _pick(jobs["staff"]),
        {"job": jobs["principal"], "verdict": "near_miss", "against_baseline": "comparable",
         "reasons": [_reason("Leads risk products", ", but the posting names an on-call rotation.", "r1")]},
        {"job": jobs["lead"], "verdict": "pass", "pass_code": "not_better", "note": "Same scope as today."},
    ]))
    assert (decided["saved"], decided["refused"], decided["picks"]) == (3, 0, 1)

    finished = _data(*await _write(api_client, "POST", "/picks/runs/finish",
                                   {"run": run["run"], "outcome": "finished", "tokens": 41_200}))
    assert (finished["outcome"], finished["judged"], finished["picks"], finished["near_misses"]) == (
        "finished", 3, 1, 1,
    )

    picks = _data(*await _read(api_client, "/picks"))
    assert picks["count"] == 1
    assert picks["picks"][0]["job"] == jobs["staff"] and picks["picks"][0]["title"] == "Staff Product Manager, Pricing"
    assert picks["picks"][0]["reasons"][0] == {
        "opening": "Staff level", "rest": ", one step above your Senior role today.", "brief_item": "p2",
    }
    near = _data(*await _read(api_client, "/picks", view="near_misses"))
    assert [row["job"] for row in near["picks"]] == [jobs["principal"]]
    passed = _data(*await _read(api_client, "/picks", view="passed"))
    assert [(row["job"], row["pass_code"], row["note"]) for row in passed["picks"]] == [
        (jobs["lead"], "not_better", "Same scope as today."),
    ]
    async with _fresh(db_session) as session:
        stored = await session.get(PickRun, run["run"])
        assert (stored.host, stored.model, stored.outcome, stored.tokens) == (
            "claude-code", "claude-fable-5-2", "finished", 41_200,
        )

    # Every case is closed, so the next run is handed nothing.
    again = await _begin(api_client)
    assert again["batch"] == [] and again["counts"]["waiting"] == 0
    assert again["budget"]["picks_this_month"] == 1 and again["budget"]["picks"][0]["job"] == jobs["staff"]


async def test_a_run_larger_than_a_batch_is_read_on_with_next(api_client, workspace):
    run = await _begin(api_client, limit=2)

    assert run["count"] == 2 and run["next_cursor"] == 2
    assert run["continue_with"] == [{"operation": "picks.next", "arguments": {"run": run["run"], "cursor": 2}}]

    rest = _data(*await _read(api_client, "/picks/runs/next", run=run["run"], cursor=2))
    assert rest["count"] == 1 and rest["next_cursor"] is None and rest["batch"][0]["fit_rank"] == 3
    assert {posting["job"] for posting in (*run["batch"], *rest["batch"])} == {
        workspace["jobs"]["staff"], workspace["jobs"]["principal"], workspace["jobs"]["lead"],
    }
    _refused(*await _read(api_client, "/picks/runs/next", run="run_000000000000", cursor=0), "not_found")


# --------------------------------------------------------------------------- #
# What a verdict must be
# --------------------------------------------------------------------------- #


async def test_a_pick_with_one_reason_is_refused_and_the_rest_of_the_batch_is_saved(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)

    data = _data(*await _decide(api_client, run, [
        _pick(jobs["staff"], [_reason("Staff level", ", one step above your Senior role today.", "p2")]),
        _pick(jobs["principal"]),
    ]))

    assert [(item["job"], item["outcome"], item["refusal"]) for item in data["results"]] == [
        (jobs["staff"], "refused", "incomplete"), (jobs["principal"], "saved", None),
    ]
    assert [row.job_id for row in await _verdicts(db_session)] == [jobs["principal"]], "the refused item left no row"
    # The same posting, now with two reasons, is saved: the refusal closed nothing.
    assert await _outcomes(api_client, run, [_pick(jobs["staff"])]) == {jobs["staff"]: None}


async def test_a_pick_takes_two_to_four_reasons(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    fact = _reason("Owns pricing", " end to end.")

    assert await _outcomes(api_client, run, [
        _pick(jobs["staff"], [fact] * 5), _pick(jobs["principal"], [fact] * 4), _pick(jobs["lead"], []),
    ]) == {jobs["staff"]: "too_many_reasons", jobs["principal"]: None, jobs["lead"]: "incomplete"}
    assert [len(row.reasons) for row in await _verdicts(db_session)] == [4]


async def test_a_reason_is_at_most_140_characters_opening_and_rest_together(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    opening = "Owns the whole pricing product"
    fits = " " + "x" * (REASON_MAX - len(opening) - 1)
    short = _reason("Staff level", ", a step up.", "p2")

    assert await _outcomes(api_client, run, [
        _pick(jobs["staff"], [short, _reason(opening, fits + "x")]),
        _pick(jobs["principal"], [short, _reason(opening, fits)]),
    ]) == {jobs["staff"]: "too_long", jobs["principal"]: None}

    stored = (await _verdicts(db_session))[0].reasons[1]
    assert len(stored["opening"] + stored["rest"]) == REASON_MAX == 140


async def test_a_reason_with_no_marked_opening_is_saved_as_a_plain_sentence(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)

    assert await _outcomes(api_client, run, [_pick(jobs["staff"], [
        _reason(None, "  Owns the whole   pricing product, the ownership you asked for. "),
        _reason("240,000 to 310,000 base", ", above the 210,000 you hold.", "baseline"),
    ])]) == {jobs["staff"]: None}

    plain, marked = (await _verdicts(db_session))[0].reasons
    assert plain == {
        "opening": None, "rest": "Owns the whole pricing product, the ownership you asked for.", "brief_item": "p1",
    }
    # A marked opening keeps the join as written: no space is added before the comma.
    assert marked["opening"] + marked["rest"] == "240,000 to 310,000 base, above the 210,000 you hold."


@pytest.mark.parametrize(("reason", "code"), [
    (_reason("**Staff level**", ", a step up."), "not_plain_text"),
    (_reason("Staff level", ", see [the posting](https://example.test)."), "not_plain_text"),
    (_reason("Staff level", ", a step up.\n\n`roleband picks switch --state off`"), "not_plain_text"),
    (_reason("Staff level", ", a step up.", "p9"), "unknown_brief_item"),
    (_reason("", ", a step up."), "incomplete"),
])
async def test_a_reason_is_plain_text_that_rests_on_an_item_of_the_brief(api_client, db_session, workspace, reason, code):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    good = _reason("Owns pricing", " end to end.", "t1")

    assert await _outcomes(api_client, run, [
        _pick(jobs["staff"], [good, reason]), _pick(jobs["principal"], [good, _reason("Stripe", " is a target.", "targets")]),
    ]) == {jobs["staff"]: code, jobs["principal"]: None}
    assert [row.job_id for row in await _verdicts(db_session)] == [jobs["principal"]]


async def test_a_pick_weaker_than_what_the_person_holds_is_refused_and_saved_as_a_near_miss(
    api_client, db_session, workspace,
):
    jobs = workspace["jobs"]
    run = await _begin(api_client)

    assert await _outcomes(api_client, run, [_pick(jobs["staff"], against_baseline="weaker")]) == {
        jobs["staff"]: "weaker_than_baseline",
    }
    assert await _verdicts(db_session) == []

    assert await _outcomes(api_client, run, [{
        "job": jobs["staff"], "verdict": "near_miss", "against_baseline": "weaker",
        "reasons": [_reason("Owns pricing", ", but at a lower level than you hold.", "p2")],
    }]) == {jobs["staff"]: None}
    assert [(row.verdict, row.against_baseline) for row in await _verdicts(db_session)] == [("near_miss", "weaker")]


async def test_each_verdict_kind_holds_its_own_form(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    fact = _reason("Owns pricing", " end to end.")

    assert await _outcomes(api_client, run, [
        {"job": jobs["staff"], "verdict": "pass"},
        {"job": jobs["principal"], "verdict": "pass", "pass_code": "hard_rule", "reasons": [fact]},
        {"job": jobs["lead"], "verdict": "near_miss", "against_baseline": "better", "reasons": [fact, fact]},
    ]) == {jobs["staff"]: "incomplete", jobs["principal"]: "not_for_a_pass", jobs["lead"]: "too_many_reasons"}
    assert await _outcomes(api_client, run, [
        {"job": jobs["staff"], "verdict": "pick", "reasons": [fact, fact]},
        {"job": jobs["principal"], "verdict": "pass", "pass_code": "hard_rule", "note": "x" * 201},
    ]) == {jobs["staff"]: "incomplete", jobs["principal"]: "too_long"}
    assert await _verdicts(db_session) == []


async def test_a_posting_given_twice_in_one_call_or_a_shape_outside_the_schema_fails_the_call(api_client, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)

    _refused(*await _decide(api_client, run, [_pick(jobs["staff"]), _pick(jobs["staff"])]), "invalid_input")
    _refused(*await _decide(api_client, run, [{**_pick(jobs["staff"]), "catch": "Three days in the office."}]),
             "invalid_input")
    _refused(*await _decide(api_client, run, [{**_pick(jobs["staff"]), "verdict": "maybe"}]), "invalid_input")


# --------------------------------------------------------------------------- #
# Reruns, and a run that no longer matches the world
# --------------------------------------------------------------------------- #


async def test_a_replay_under_the_same_key_saves_nothing_twice_and_a_new_key_is_a_judged_case(
    api_client, db_session, workspace,
):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    key = _key()

    first_response, first = await _decide(api_client, run, [_pick(jobs["staff"])], key=key)
    replay_response, replay = await _decide(api_client, run, [_pick(jobs["staff"])], key=key)

    assert _data(first_response, first) == _data(replay_response, replay)
    assert (first["meta"]["replayed"], replay["meta"]["replayed"]) == (False, True)
    assert len(await _verdicts(db_session)) == 1
    async with _fresh(db_session) as session:
        listed = await session.scalar(
            select(func.count()).select_from(AgentActivity).where(AgentActivity.operation == "picks.decide")
        )
    assert listed == 1, "a replay changed nothing and lists nothing"

    assert await _outcomes(api_client, run, [_pick(jobs["staff"])]) == {jobs["staff"]: "already_judged"}
    assert len(await _verdicts(db_session)) == 1
    # The same key with another request is a conflict, never a second write.
    _refused(*await _decide(api_client, run, [_pick(jobs["principal"])], key=key), "idempotency_conflict")


async def test_beginning_again_under_the_same_key_answers_the_same_run(api_client, db_session, workspace):
    key = _key()

    first = _data(*await _write(api_client, "POST", "/picks/runs", {}, key=key))
    again = _data(*await _write(api_client, "POST", "/picks/runs", {}, key=key))

    assert again["run"] == first["run"] and again["batch"] == first["batch"]
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(PickRun)) == 1


async def test_a_posting_outside_the_run_or_changed_since_it_began_is_refused(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    async with _fresh(db_session) as session:
        await session.execute(update(Job).where(Job.id == jobs["staff"]).values(content_hash="h-staff-rewritten"))
        await session.commit()

    assert await _outcomes(api_client, run, [
        _pick(jobs["staff"]), _pick(jobs["underpaid"]), _pick(987_654), _pick(jobs["principal"]),
    ]) == {
        jobs["staff"]: "posting_changed", jobs["underpaid"]: "not_in_run", 987_654: "not_in_run",
        jobs["principal"]: None,
    }
    # The rewritten posting is a new case: the next run hands it out again.
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}))
    assert jobs["staff"] in {posting["job"] for posting in (await _begin(api_client))["batch"]}


async def test_a_brief_changed_during_a_run_refuses_its_verdicts(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    _data(*await _write(api_client, "PATCH", "/brief", {"if_revision": 1, "reason": "They now want remote.",
                                                         "pulls": [{"text": "Remote first", "weight": 3}]}))

    assert await _outcomes(api_client, run, [_pick(jobs["staff"])]) == {jobs["staff"]: "brief_changed"}
    assert await _verdicts(db_session) == []
    # A verdict that names another version than the run's is a malformed call, not a refused item.
    _refused(*await _write(api_client, "POST", "/picks/verdicts", {
        "run": run["run"], "brief_version": 2, "verdicts": [_pick(jobs["staff"])],
    }), "invalid_input")


async def test_a_closed_or_unknown_run_takes_no_verdict(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    _refused(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "stopped"}),
             "invalid_input")
    stopped = _data(*await _write(api_client, "POST", "/picks/runs/finish", {
        "run": run["run"], "outcome": "stopped", "note": "The plan's limit was reached.",
    }))
    assert (stopped["outcome"], stopped["note"]) == ("stopped", "The plan's limit was reached.")

    error = _refused(*await _decide(api_client, run, [_pick(jobs["staff"])]), "invalid_input")
    assert error["details"]["reason"] == "run_closed"
    _refused(*await _decide(api_client, {**run, "run": "run_000000000000"}, [_pick(jobs["staff"])]), "not_found")
    assert await _verdicts(db_session) == []

    status = _data(*await _read(api_client, "/picks/status"))
    assert status["routine"]["health"] == "stopped_early"
    assert status["routine"]["last_run"]["note"] == "The plan's limit was reached."


async def test_a_run_open_past_the_bound_reads_as_abandoned_and_takes_no_write(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    await db_session.execute(update(PickRun).where(PickRun.id == run["run"]).values(
        started_at=datetime.now(UTC) - ABANDONED_AFTER - timedelta(minutes=1),
    ))
    await db_session.commit()

    for answer in (
        await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}),
        await _decide(api_client, run, [_pick(jobs["staff"])]),
        await _write(api_client, "PATCH", "/brief", {
            "if_revision": 1, "reason": "A pull.", "run": run["run"], "pulls": [{"text": "Payments"}],
        }),
    ):
        assert _refused(*answer, "invalid_input")["details"]["reason"] == "run_closed"
    assert await _verdicts(db_session) == []
    assert _data(*await _read(api_client, "/picks/status"))["routine"]["health"] == "stopped_early"
    # A run begun since and still open says nothing yet of how it will end.
    await _begin(api_client)
    assert _data(*await _read(api_client, "/picks/status"))["routine"]["health"] == "stopped_early"


async def test_a_further_batch_leaves_out_a_posting_whose_text_changed_since_the_run_began(
    api_client, db_session, workspace,
):
    run = await _begin(api_client, limit=1)
    async with _fresh(db_session) as session:
        queued = [int(job) for job, _ in (await session.get(PickRun, run["run"])).queue]
        await session.execute(update(Job).where(Job.id == queued[1]).values(content_hash="h-rewritten"))
        await session.commit()

    rest = _data(*await _read(api_client, "/picks/runs/next", run=run["run"], cursor=1))

    # Its verdict would be refused as posting_changed; the next run hands out the new text.
    assert [(posting["job"], posting["fit_rank"]) for posting in rest["batch"]] == [(queued[2], 3)]
    assert rest["next_cursor"] is None


async def test_a_replayed_run_start_answers_no_postings_once_postings_are_not_shared(api_client, db_session, workspace):
    key = _key()
    first = _data(*await _write(api_client, "POST", "/picks/runs", {}, key=key))
    assert first["batch"]

    await _choose(db_session, public_posting="not_shared")
    replay = await _write(api_client, "POST", "/picks/runs", {}, key=key)

    error = _refused(*replay, "category_disabled")
    assert error["details"]["category"] == "public_posting"
    assert "Staff Product Manager" not in str(replay[1])


async def test_a_change_to_the_active_brief_beside_a_draft_is_listed_as_a_change_not_an_activation(
    api_client, db_session, workspace,
):
    drafted = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 0, "target": "draft", "reason": "Starting over.", "urgency": "active",
    }))
    changed = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 1, "target": "active", "reason": "Budget.", "budget": 5,
    }))
    assert changed["status"] == "active"

    async with _fresh(db_session) as session:
        listed = await session.scalar(
            select(AgentActivity).where(AgentActivity.operation == "brief.patch").order_by(AgentActivity.id.desc())
        )
    assert listed.summary == f"Changed your top picks brief (version {changed['version']})"
    assert listed.changes == []
    # Control: making the draft active is an activation.
    _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": drafted["revision"], "target": "draft", "reason": "Ready.", "activate": True,
    }))
    async with _fresh(db_session) as session:
        activated = await session.scalar(
            select(AgentActivity).where(AgentActivity.operation == "brief.patch").order_by(AgentActivity.id.desc())
        )
    assert activated.summary.startswith("Made your top picks brief active")


async def test_the_status_budget_is_the_one_runs_keep_to_with_a_drafts_beside_it(api_client, workspace):
    _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 0, "target": "draft", "reason": "A wider net.", "budget": 8,
    }))

    status = _data(*await _read(api_client, "/picks/status"))
    run = await _begin(api_client)

    assert status["budget"]["per_month"] == run["budget"]["per_month"] == 3, "the active brief governs the run"
    assert status["budget"]["draft_per_month"] == 8


async def _listed(db_session, operation: str) -> AgentActivity:
    async with _fresh(db_session) as session:
        listed = await session.scalar(
            select(AgentActivity).where(AgentActivity.operation == operation).order_by(AgentActivity.id.desc())
        )
    assert listed is not None
    return listed


async def test_a_limit_change_beside_a_switch_lists_the_state_it_wrote_under(api_client, db_session, workspace):
    """A switch held open turns the mode off while a change of the daily limit
    waits on it: the limit's entry lists a settings change, not that switch."""
    async with _fresh(db_session) as holder:
        await picks_mode.change(holder, state="off", now=datetime.now(UTC))
        task = asyncio.create_task(_write(api_client, "PUT", "/picks/mode", {"daily_cap": 40}))
        await until_waiting(db_session.bind, task)
        assert not task.done(), "the limit's write waits for the switch"
        await holder.commit()
    assert _data(*await task)["state"] == "off"

    listed = await _listed(db_session, "picks.switch")
    assert listed.summary == "Changed the top picks settings"
    assert listed.changes == []


async def test_a_change_beside_a_draft_being_made_lists_the_row_it_wrote(api_client, db_session, workspace):
    """A draft is made, uncommitted, while a change that names no row waits:
    the change lands on that draft, and its entry says the draft stayed a draft."""
    async with _fresh(db_session) as holder:
        drafted = await briefs.patch(holder, Patch(parts={"budget": 6}, reason="A wider net.", if_revision=0, target="draft"))
        task = asyncio.create_task(_write(api_client, "PATCH", "/brief", {
            "if_revision": drafted.revision, "reason": "Budget.", "budget": 7,
        }))
        await until_waiting(db_session.bind, task)
        assert not task.done(), "the change waits for the draft"
        await holder.commit()
    assert _data(*await task)["status"] == "draft"

    listed = await _listed(db_session, "brief.patch")
    assert listed.changes == [], "the draft it wrote was a draft before"


async def test_a_routine_change_waits_for_the_picks_lock_before_it_holds_its_run(api_client, db_session, workspace):
    """`picks.decide` holds the picks lock, then its run's row. A routine change
    of the brief waiting on the same lock holds neither, so the two cannot
    deadlock: the run's row is free while the change waits."""
    run = await _begin(api_client)
    async with _fresh(db_session) as holder:
        await lock_picks(holder)
        task = asyncio.create_task(_write(api_client, "PATCH", "/brief", {
            "if_revision": 1, "reason": "A pull.", "run": run["run"], "pulls": [{"text": "Payments"}],
        }))
        await until_waiting(db_session.bind, task)
        assert not task.done(), "the change waits for the picks lock"
        async with asyncio.timeout(5):
            await holder.execute(select(PickRun.id).where(PickRun.id == run["run"]).with_for_update())
        await holder.commit()
    assert _data(*await task)["made_by"] == "routine"


@pytest.mark.parametrize("operation", ["decide", "finish"])
async def test_a_run_that_passes_the_bound_while_a_write_waits_for_the_lock_takes_no_write(
    api_client, db_session, workspace, monkeypatch, operation,
):
    """The run is open when the write is sent and past the bound when the
    picks lock comes free: the write reads the clock under the lock, so the
    run is closed and nothing lands on it."""
    run = await _begin(api_client)
    started = await db_session.scalar(select(PickRun.started_at).where(PickRun.id == run["run"]))
    clock = {"now": started + ABANDONED_AFTER - timedelta(minutes=1)}

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"] if tz is None else clock["now"].astimezone(tz)

    monkeypatch.setattr(picks_operations, "datetime", _Clock)
    async with _fresh(db_session) as holder:
        await lock_picks(holder)
        task = asyncio.create_task(
            _decide(api_client, run, [_pick(workspace["jobs"]["staff"])]) if operation == "decide"
            else _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"})
        )
        await until_waiting(db_session.bind, task)
        assert not task.done(), "the write waits for the picks lock"
        clock["now"] = started + ABANDONED_AFTER + timedelta(minutes=1)
        await holder.commit()
    assert _refused(*await task, "invalid_input")["details"]["reason"] == "run_closed"
    assert await _verdicts(db_session) == []
    async with _fresh(db_session) as session:
        assert await session.scalar(select(PickRun.outcome).where(PickRun.id == run["run"])) is None


async def test_the_suggested_check_times_are_the_half_hours_just_after_scans_most_often_end(db_session, monkeypatch):
    zone = ZoneInfo("America/New_York")
    monkeypatch.setattr(picks_operations, "local_zone", lambda: zone)
    day = datetime(2026, 11, 24, tzinfo=zone)
    for hour, minute, second in ((9, 0, 30), (9, 1, 0), (13, 10, 0), (13, 29, 59), (23, 45, 0)):
        at = day.replace(hour=hour, minute=minute, second=second)
        db_session.add(ScrapeRun(started_at=at - timedelta(minutes=20), finished_at=at, status="ok"))
    await db_session.commit()

    times = await picks_operations._suggested_check_times(db_session, datetime(2026, 11, 25, 12, tzinfo=UTC))

    # A scan that ends at 09:00:30 is not done by 09:00.
    assert times == ["09:30", "13:30"]


async def test_beginning_a_run_closes_the_same_assistants_open_run_as_abandoned(api_client, db_session, workspace):
    first = await _begin(api_client)
    second = await _begin(api_client)

    async with _fresh(db_session) as session:
        outcomes = dict((await session.execute(select(PickRun.id, PickRun.outcome))).all())
    assert outcomes == {first["run"]: "abandoned", second["run"]: None}
    # The abandoned run handed its postings out and judged none: they are handed out again.
    assert {posting["job"] for posting in second["batch"]} == {posting["job"] for posting in first["batch"]}


async def test_a_days_runs_together_hand_out_at_most_the_daily_cap(api_client, db_session, workspace, monkeypatch):
    await update_top_picks_settings(db_session, daily_cap=2)
    await db_session.commit()
    # Every run of the test begins at the same instant, so all of them fall on one local day.
    at = datetime.now(UTC)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at if tz is None else at.astimezone(tz)

    monkeypatch.setattr(picks_operations, "datetime", _Frozen)

    first = await _begin(api_client)
    assert first["counts"] == {"waiting": 3, "ruled_out_by_rules": 1, "handed": 2, "held_back": 1}
    await _outcomes(api_client, first, [
        {"job": posting["job"], "verdict": "pass", "pass_code": "not_better"} for posting in first["batch"]
    ])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": first["run"], "outcome": "finished"}))

    second = await _begin(api_client)
    assert second["batch"] == [] and second["counts"]["handed"] == 0 and second["counts"]["held_back"] == 1

    # Yesterday's runs do not count against today.
    async with _fresh(db_session) as session:
        await session.execute(update(PickRun).values(started_at=PickRun.started_at - timedelta(days=2)))
        await session.commit()
    third = await _begin(api_client)
    assert third["counts"]["handed"] == 1


# --------------------------------------------------------------------------- #
# The mode
# --------------------------------------------------------------------------- #


async def test_no_run_begins_while_the_mode_is_off_but_a_trial_does(api_client, db_session, workspace):
    off = _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "off"}))
    assert off["state"] == "off"

    error = _refused(*await _write(api_client, "POST", "/picks/runs", {}), "mode_off")
    assert outcome("mode_off").exit_status == 4 and error["details"] == {"setting": "top_picks.state"}

    trial = await _begin(api_client, trial=True)
    assert trial["trial"] is True and trial["counts"]["handed"] == 3
    await _outcomes(api_client, trial, [_pick(workspace["jobs"]["staff"])])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": trial["run"], "outcome": "finished"}))

    # A trial's pick is kept apart: it is no pick, and its posting is still to be judged.
    assert _data(*await _read(api_client, "/picks"))["count"] == 0
    assert [row.trial for row in await _verdicts(db_session)] == [True]
    on = _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "on"}))
    assert on["state"] == "on"
    async with _fresh(db_session) as session:
        await session.execute(update(Job).values(first_seen=datetime.now(UTC)))
        await session.commit()
    assert workspace["jobs"]["staff"] in {posting["job"] for posting in (await _begin(api_client))["batch"]}


async def test_turning_the_mode_on_needs_an_active_brief_and_starts_its_clock(api_client, db_session, scratch_scope):
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    await db_session.commit()

    _refused(*await _write(api_client, "PUT", "/picks/mode", {"state": "on"}), "brief_required")
    _refused(*await _write(api_client, "POST", "/picks/runs", {"trial": True}), "brief_required")
    assert (await get_top_picks_settings(db_session)).state == "never_set_up"

    await briefs.patch(db_session, Patch(parts={"urgency": "open"}, reason="Setup.", if_revision=0, activate=True))
    await db_session.commit()
    before = datetime.now(UTC)
    on = _data(*await _write(api_client, "PUT", "/picks/mode", {
        "state": "on", "routine_host": "claude-code", "schedule": "daily 09:30  and 17:30",
    }))

    assert (on["state"], on["routine_host"], on["schedule"], on["daily_cap"]) == (
        "on", "claude-code", "daily 09:30 and 17:30", 1000,
    )
    assert datetime.fromisoformat(on["enabled_at"]) >= before
    # Turning it on again does not restart the clock; turning it off deletes nothing.
    again = _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "on"}))
    assert again["enabled_at"] == on["enabled_at"]
    off = _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "off"}))
    assert (off["enabled_at"], off["schedule"]) == (on["enabled_at"], on["schedule"])
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(PickBrief)) == 1


# --------------------------------------------------------------------------- #
# Setup, as the app mirrors it
# --------------------------------------------------------------------------- #


async def test_status_follows_the_setup_conversation_as_it_saves_each_part(api_client, db_session, scratch_scope):
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True))
    await ensure_workspace_id(db_session)
    db_session.add(make_company("google", "Google"))
    db_session.add(make_job("open", first_seen=datetime.now(UTC), last_seen=datetime.now(UTC)))
    await db_session.commit()

    async def setup() -> dict:
        return _data(*await _read(api_client, "/picks/status"))["setup"]

    start = await setup()
    assert (start["next_step"], start["saved_parts"]) == ("background", [])
    assert [step["id"] for step in start["steps"] if step["done"]] == ["connect"]

    reading = {"current": {"title": "Senior Product Manager"}, "years": 9}
    _data(*await _write(api_client, "PUT", "/background", {"reading": reading, "source": "spoken"}))
    assert (await setup())["next_step"] == "background", "a reading the person has not confirmed is not theirs yet"
    _data(*await _write(api_client, "PUT", "/background", {"reading": reading, "source": "spoken", "confirmed": True}))
    assert (await setup())["next_step"] == "situation"

    saved = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 0, "reason": "Where they stand.", "urgency": "open", "baseline": {"title": "Senior PM"},
    }))
    assert (saved["status"], saved["revision"]) == ("draft", 1)
    after_situation = await setup()
    assert (after_situation["next_step"], after_situation["saved_parts"]) == ("bar", ["urgency", "baseline"])

    _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 1, "reason": "What pulls and what rules.", "pulls": [{"text": "Owns a product", "weight": 3}],
        "rules": [], "tradeoffs": [{"text": "Scope over pay"}], "targets": {"companies": ["Stripe"]},
    }))
    assert (await setup())["next_step"] == "calibration"
    _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 2, "reason": "Reactions and budget.", "budget": 3,
        "examples": [{"job": 1, "reaction": "wanted", "reason": "Platform scope"}],
    }))
    assert (await setup())["next_step"] == "confirm"

    active = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 3, "reason": "The person confirmed it.", "activate": True, "summary": "Open to a product to own.",
    }))
    assert (active["status"], active["summary"]) == ("active", "Open to a product to own.")
    status = _data(*await _read(api_client, "/picks/status"))
    assert status["setup"]["next_step"] == "trial" and status["state"] == "never_set_up"
    assert status["brief"] == {"active_version": 1, "draft_version": None, "calibrated": False}

    trial = await _begin(api_client, trial=True)
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": trial["run"], "outcome": "finished"}))
    assert (await setup())["next_step"] == "routine"
    _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "on", "routine_host": "claude-code"}))
    assert (await setup())["next_step"] == "routine", "the routine is set up once a run of it has finished"
    run = await _begin(api_client)
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}))

    done = _data(*await _read(api_client, "/picks/status"))
    assert done["setup"]["next_step"] == "done" and all(step["done"] for step in done["setup"]["steps"])
    assert (done["state"], done["routine"]["health"], done["routine"]["host"]) == ("on", "healthy", "claude-code")


async def test_status_says_what_the_app_already_knows_and_what_waits(api_client, db_session, workspace):
    db_session.add(Favorite(job_id=workspace["jobs"]["lead"]))
    await db_session.commit()

    status = _data(*await _read(api_client, "/picks/status"))

    assert status["routine"]["waiting"] == 3 and status["routine"]["health"] == "never_ran"
    assert status["budget"] == {"per_month": 3, "picks_this_month": 0, "draft_per_month": None}
    assert status["known"]["has_background"] is True and status["known"]["background_confirmed"] is True
    assert (status["known"]["saved"], status["known"]["not_for_me"]) == (1, 0)
    # Four roles arrived on one day; the floor rules out the one under it.
    assert (status["volume"]["expected_per_day"], status["volume"]["busiest_day"]) == (3, 3)
    assert status["volume"]["by_rule"] == [{"rule": "r2", "removes_share": 0.25}]
    assert status["unseen_pick"] is False

    run = await _begin(api_client)
    await _outcomes(api_client, run, [_pick(workspace["jobs"]["staff"])])
    assert _data(*await _read(api_client, "/picks/status"))["unseen_pick"] is True
    await update_top_picks_settings(db_session, last_opened_at=datetime.now(UTC))
    await db_session.commit()
    assert _data(*await _read(api_client, "/picks/status"))["unseen_pick"] is False


# --------------------------------------------------------------------------- #
# Not for me on a pick, and putting it back
# --------------------------------------------------------------------------- #


async def _picked(api_client, workspace) -> None:
    run = await _begin(api_client)
    await _outcomes(api_client, run, [_pick(workspace["jobs"]["staff"]), _pick(workspace["jobs"]["principal"])])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}))


async def test_not_for_me_on_a_pick_removes_it_keeps_the_reason_and_can_be_put_back(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _picked(api_client, workspace)

    removed = await api_client.put(f"/api/jobs/{jobs['staff']}/feedback", json={
        "verdict": "dismissed", "reason": "pay_too_low", "reason_text": "  The base is   under what I hold. ",
    })
    assert removed.status_code == 200 and removed.json()["reason_text"] == "The base is under what I hold."
    # A role the person dismissed that no assistant picked is not a removed pick.
    await api_client.put(f"/api/jobs/{jobs['lead']}/feedback", json={"verdict": "dismissed", "reason": "wrong_role"})

    assert [row["job"] for row in _data(*await _read(api_client, "/picks"))["picks"]] == [jobs["principal"]]
    listed = _data(*await _read(api_client, "/picks", view="removed"))
    assert [row["job"] for row in listed["picks"]] == [jobs["staff"]]
    assert {key: listed["picks"][0]["reaction"][key] for key in ("kind", "reason", "reason_text")} == {
        "kind": "not_for_me", "reason": "pay_too_low", "reason_text": "The base is under what I hold.",
    }
    app = (await api_client.get("/api/picks/removed")).json()["picks"]
    assert [(row["job_id"], row["company"], row["reason"], row["reason_text"]) for row in app] == [
        (jobs["staff"], "Google", "pay_too_low", "The base is under what I hold."),
    ]
    assert app[0]["reasons"][0] == {"opening": "Staff level", "rest": ", one step above your Senior role today."}
    board = (await api_client.get("/api/jobs", params={"status": "open"})).json()
    assert jobs["staff"] not in {row["id"] for row in board["items"]}, "the role left the Radar with the pick"

    # The next run is told what the person did, and why.
    reactions = (await _begin(api_client))["reactions"]
    assert [(row["job"], row["reaction"]["kind"], row["reaction"]["reason_text"]) for row in reactions] == [
        (jobs["staff"], "not_for_me", "The base is under what I hold."),
    ]

    back = await api_client.delete(f"/api/jobs/{jobs['staff']}/feedback")
    assert back.status_code == 200
    assert {row["job"] for row in _data(*await _read(api_client, "/picks"))["picks"]} == {
        jobs["staff"], jobs["principal"],
    }
    assert _data(*await _read(api_client, "/picks", view="removed"))["picks"] == []
    assert (await api_client.get("/api/picks/removed")).json() == {"picks": []}
    board = (await api_client.get("/api/jobs", params={"status": "open"})).json()
    assert jobs["staff"] in {row["id"] for row in board["items"]}, "put back on the Radar as well"
    assert len(await _verdicts(db_session)) == 2, "removing and putting back never touched a verdict"


async def test_passed_over_reads_the_weeks_near_misses_passes_by_why_and_what_the_rules_ruled_out(
    api_client, db_session, workspace,
):
    jobs = workspace["jobs"]
    # Under the floor too, but it arrived before this week.
    db_session.add(make_job(
        "underpaid-earlier", title="Staff Product Manager, Search", first_seen=datetime.now(UTC) - timedelta(days=10),
        last_seen=datetime.now(UTC), content_hash="h-earlier", disclosed_base_min=150_000, disclosed_base_max=190_000,
        disclosed_currency="USD", disclosed_pay_basis="base", disclosed_pay_period="year",
    ))
    await db_session.commit()
    run = await _begin(api_client)
    near = _reason("Owns risk products", ", but the base tops out under the 210,000 you hold.")
    await _outcomes(api_client, run, [
        _pick(jobs["staff"]),
        {"job": jobs["principal"], "verdict": "near_miss", "against_baseline": "comparable", "reasons": [near]},
        {"job": jobs["lead"], "verdict": "pass", "pass_code": "hard_rule"},
    ])

    passed = (await api_client.get("/api/picks/passed")).json()
    assert passed["passed_this_week"] == 2, "the pick is not passed over"
    assert [(row["job_id"], row["reason"]) for row in passed["near_misses"]] == [
        (jobs["principal"], {"opening": "Owns risk products", "rest": ", but the base tops out under the 210,000 you hold."}),
    ]
    assert passed["passes"] == [{"code": "hard_rule", "count": 1}]
    assert passed["judged_rules"] == ["No on-call"]
    # The underpaid role states a base under the floor: no assistant read it.
    assert (passed["ruled_out"], passed["ruled_out_by_rule"]) == (1, [{"rule": "Base under 200,000", "count": 1}])

    # A near miss the person marked Not for me leaves the list.
    await api_client.put(f"/api/jobs/{jobs['principal']}/feedback", json={"verdict": "dismissed"})
    assert (await api_client.get("/api/picks/passed")).json()["near_misses"] == []

    # Verdicts from before the last seven days are not this week's.
    async with _fresh(db_session) as session:
        await session.execute(update(PickVerdict).values(created_at=datetime.now(UTC) - timedelta(days=8)))
        await session.commit()
    stale = (await api_client.get("/api/picks/passed")).json()
    assert (stale["passed_this_week"], stale["near_misses"], stale["passes"]) == (0, [], [])


async def test_a_dismissal_keeps_only_a_known_reason_and_a_short_line_of_the_persons_words(
    api_client, db_session, workspace,
):
    job = workspace["jobs"]["staff"]

    unknown = await api_client.put(f"/api/jobs/{job}/feedback", json={"verdict": "dismissed", "reason": "boring"})
    too_long = await api_client.put(f"/api/jobs/{job}/feedback", json={"verdict": "dismissed", "reason_text": "x" * 201})
    assert (unknown.status_code, too_long.status_code) == (422, 422)
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(JobFeedback)) == 0

    for reason in ("wrong_place", "pay_too_low"):
        assert (await api_client.put(f"/api/jobs/{job}/feedback", json={"verdict": "dismissed", "reason": reason})
                ).status_code == 200
    words_only = await api_client.put(f"/api/jobs/{job}/feedback", json={"verdict": "dismissed", "reason_text": "x" * 200})
    assert words_only.status_code == 200
    async with _fresh(db_session) as session:
        row = await session.scalar(select(JobFeedback))
        assert (row.reason, row.reason_text) == (None, "x" * 200), "a later mark replaces the earlier reason whole"


async def test_a_pick_a_new_hard_rule_rules_out_leaves_the_picks(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _picked(api_client, workspace)

    _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 1, "reason": "They will not work at Google.",
        "rules": [{"id": "r1", "text": "No on-call"},
                  {"id": "r2", "text": "Base under 200,000", "check": {"form": "min_base", "amount": 200_000}},
                  {"text": "Not Google", "check": {"form": "avoid_companies", "companies": ["google"]}}],
    }))

    assert [row["job"] for row in _data(*await _read(api_client, "/picks"))["picks"]] == [jobs["principal"]]


# --------------------------------------------------------------------------- #
# The brief and the background through their operations
# --------------------------------------------------------------------------- #


async def test_a_routine_write_names_its_run_and_cannot_change_what_only_the_person_decides(
    api_client, db_session, workspace,
):
    run = await _begin(api_client)
    stricter = {"if_revision": 1, "reason": "Two picks removed for travel.", "run": run["run"],
                "rules": [{"id": "r1", "text": "No on-call"}, {"text": "No travel"}]}

    error = _refused(*await _write(api_client, "PATCH", "/brief", stricter), "needs_the_person")
    assert outcome("needs_the_person").exit_status == 7 and error["details"] == {"parts": ["rules"]}
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(PickBrief)) == 1

    learned = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 1, "reason": "Two picks removed for travel.", "run": run["run"],
        "proposed_rules": [{"text": "No travel", "reason": "Two picks were removed for travel."}],
    }))
    assert (learned["version"], learned["made_by"], learned["ids"]["proposed_rules"]) == (2, "routine", ["x1"])
    assert len(learned["body"]["rules"]) == 2

    # The same change without a run is the person's, and succeeds.
    by_person = _data(*await _write(api_client, "PATCH", "/brief", {
        **stricter, "run": None, "if_revision": learned["revision"],
    }))
    assert (by_person["version"], by_person["made_by"], by_person["ids"]["rules"]) == (3, "person", ["r1", "r3"])
    _refused(*await _write(api_client, "PATCH", "/brief", {**stricter, "run": "run_000000000000"}), "invalid_input")


async def test_a_revision_read_from_a_replaced_brief_never_applies_to_its_replacement(api_client, workspace):
    # Two callers read the active brief at revision 1; the first change replaces it.
    first = _data(*await _write(api_client, "PATCH", "/brief", {"if_revision": 1, "reason": "Budget.", "budget": 5}))
    assert first["version"] == 2 and first["revision"] != 1
    stale = _refused(*await _write(api_client, "PATCH", "/brief", {"if_revision": 1, "reason": "Budget.", "budget": 4}),
                     "revision_conflict")
    assert stale["details"] == {"expected_revision": 1, "current_revision": first["revision"]}
    assert _data(*await _read(api_client, "/brief"))["body"]["budget"] == 5, "the stale change did not land"

    # A draft made active takes no revision the brief has held either.
    draft = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 0, "target": "draft", "reason": "A new draft.", "budget": 2,
    }))
    made = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": draft["revision"], "reason": "The person confirmed it.", "activate": True,
    }))
    assert made["status"] == "active" and made["revision"] not in (1, first["revision"])
    # With a draft beside it, the retry reads the brief the change named, not the draft.
    _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 0, "target": "draft", "reason": "Another draft.", "budget": 1,
    }))
    conflict = _refused(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": first["revision"], "target": "active", "reason": "Budget.", "budget": 9,
    }), "revision_conflict")
    assert conflict["next_actions"] == [{"operation": "brief.get", "arguments": {"which": "active"}}]
    assert conflict["details"]["current_revision"] == made["revision"]
    stale = _refused(*await _write(api_client, "PATCH", "/brief", {"if_revision": 1, "reason": "Budget.", "budget": 9}),
                     "revision_conflict")
    assert stale["next_actions"] == [{"operation": "brief.get", "arguments": {}}]

    # Stated against what it read, a change lands.
    assert _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": made["revision"], "target": "active", "reason": "Budget.", "budget": 4,
    }))["body"]["budget"] == 4


async def test_a_brief_patch_is_checked_against_the_briefs_schema_and_the_revision_it_read(api_client, workspace):
    bad = _refused(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 1, "reason": "A rule.", "rules": [{"text": "Short commute", "check": {"form": "max_commute"}}],
    }), "invalid_input")
    assert bad["details"]["errors"][0]["location"][:3] == ["rules", "0", "check"]
    assert bad["next_actions"] == [{"operation": "brief.get", "arguments": {"view": "schema"}}]

    stale = _refused(*await _write(api_client, "PATCH", "/brief", {"if_revision": 7, "reason": "Budget.", "budget": 5}),
                     "revision_conflict")
    assert stale["details"] == {"expected_revision": 7, "current_revision": 1}

    schema = _data(*await _read(api_client, "/brief", view="schema"))
    forms = {option["$ref"].rsplit("/", 1)[-1] for option in
             schema["parts_schema"]["$defs"]["Rule"]["properties"]["check"]["anyOf"][0]["oneOf"]}
    assert forms == {"MinBase", "MinTotal", "Places", "WorkModes", "MinLevel", "AvoidCompanies"}

    summary = _data(*await _read(api_client, "/brief", view="summary"))
    assert summary["body"] is None and summary["summary"] == "Not looking. Wants a whole product."
    assert summary["ids"] == {"rules": ["r1", "r2"], "pulls": ["p1", "p2"], "tradeoffs": ["t1"]}
    assert _data(*await _read(api_client, "/brief", which="draft"))["exists"] is False
    _refused(*await _read(api_client, "/brief", number=9), "not_found")
    history = _data(*await _read(api_client, "/brief/history"))
    assert [(row["version"], row["status"], row["reason"]) for row in history["versions"]] == [(1, "active", "Setup.")]


async def test_a_document_larger_than_the_usual_body_is_stored_and_no_other_operation_takes_one(
    api_client, db_session, workspace, tmp_path, monkeypatch,
):
    monkeypatch.setattr(background_store, "documents_dir", lambda: tmp_path)
    content = b"%PDF-1.7 " + b"Dana Reyes " * 140_000
    assert len(content) > MAX_BODY_BYTES
    body = {"filename": "Dana Reyes CV.pdf", "content_base64": base64.b64encode(content).decode()}

    added = _data(*await _write(api_client, "POST", "/background/documents", body))

    assert added["stored"] is True and added["document"]["size_bytes"] == len(content)
    async with _fresh(db_session) as session:
        row = await session.scalar(select(CandidateDocument))
    assert (tmp_path / row.stored_name).read_bytes() == content
    # The same file again, under a new key, is that document; Activity says nothing new was stored.
    again = _data(*await _write(api_client, "POST", "/background/documents", body))
    assert (again["stored"], again["document"]["id"]) == (False, added["document"]["id"])
    async with _fresh(db_session) as session:
        logged = (await session.scalars(
            select(AgentActivity).where(AgentActivity.operation == "background.add_document").order_by(AgentActivity.id)
        )).all()
    assert [row.subject["topic"] for row in logged] == ["background.document_added", "background.document_known"]
    # The larger bound is this operation's alone: another is refused for its size, before its shape is read.
    oversized = _refused(*await _write(api_client, "PUT", "/background", {
        "reading": {"scope": "x"}, "source": "spoken", "padding": "x" * MAX_BODY_BYTES,
    }), "invalid_input")
    assert "larger than the engine accepts" in oversized["message"] and "errors" not in oversized["details"]

    saved = _data(*await _write(api_client, "PUT", "/background", {
        "reading": {"current": {"title": "Senior Product Manager"}}, "source": "document",
        "document_id": added["document"]["id"], "confirmed": True,
    }))
    assert saved["document"]["filename"] == "Dana Reyes CV.pdf" and saved["version"] == 2
    assert _data(*await _read(api_client, "/background")) == saved

    _refused(*await _write(api_client, "POST", "/background/documents",
                           {"filename": "cv.exe", "content_base64": body["content_base64"]}), "invalid_input")
    _refused(*await _write(api_client, "POST", "/background/documents",
                           {"filename": "cv.pdf", "content_base64": "not base64!"}), "invalid_input")
    _refused(*await _write(api_client, "PUT", "/background", {
        "reading": {}, "source": "document", "document_id": 404,
    }), "not_found")
    assert len(list(tmp_path.iterdir())) == 1


async def test_each_write_is_listed_for_the_person_with_what_it_did(api_client, db_session, workspace):
    run = await _begin(api_client)
    await _outcomes(api_client, run, [_pick(workspace["jobs"]["staff"]), {"job": workspace["jobs"]["lead"], "verdict": "pass"}])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}))
    _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "off"}))

    async with _fresh(db_session) as session:
        rows = (await session.scalars(
            select(AgentActivity).where(AgentActivity.kind == "change").order_by(AgentActivity.id)
        )).all()
    assert [(row.operation, row.subject["topic"], row.action_group, row.host) for row in rows] == [
        ("picks.begin", "picks.began", "tuning_radar", "claude-code"),
        ("picks.decide", "picks.decided", "tuning_radar", "claude-code"),
        ("picks.finish", "picks.finished", "tuning_radar", "claude-code"),
        ("picks.switch", "picks.switched", "tuning_radar", "claude-code"),
    ]
    assert rows[1].subject == {"topic": "picks.decided", "run": run["run"], "saved": 1, "picks": 1, "refused": 1}
    assert rows[1].summary == "Judged 1 role: 1 top pick"
    assert rows[3].changes == [{"field": "state", "before": "on", "after": "off"}]


async def test_with_the_radar_group_off_no_run_begins(api_client, db_session, workspace):
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True, groups={"tuning_radar": "off"}))
    await db_session.commit()

    error = _refused(*await _write(api_client, "POST", "/picks/runs", {}), "writes_disabled")

    assert error["details"]["setting"] == "agent_access.groups.tuning_radar"
    assert _data(*await _read(api_client, "/picks/status"))["state"] == "on", "reads stay open"


# --------------------------------------------------------------------------- #
# A data category the person does not share is absent
# --------------------------------------------------------------------------- #


async def _choose(db_session, **categories: str) -> None:
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=True, categories=categories))
    await db_session.commit()


async def test_status_counts_saves_and_dismissals_only_while_pursuits_are_shared(api_client, db_session, workspace):
    db_session.add(Favorite(job_id=workspace["jobs"]["lead"]))
    await db_session.commit()
    shared = _data(*await _read(api_client, "/picks/status"))
    assert shared["known"]["saved"] == 1 and shared["unseen_pick"] is False

    await _choose(db_session, private_pursuit="not_shared")
    kept = _data(*await _read(api_client, "/picks/status"))

    assert kept["known"]["saved"] is None and kept["known"]["not_for_me"] is None and kept["unseen_pick"] is None
    assert kept["routine"]["waiting"] == shared["routine"]["waiting"]


async def test_a_run_does_not_begin_while_postings_are_not_shared(api_client, db_session, workspace):
    await _choose(db_session, public_posting="not_shared")

    error = _refused(*await _write(api_client, "POST", "/picks/runs", {}), "category_disabled")

    assert error["details"]["category"] == "public_posting"
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(PickRun)) == 0
    await _choose(db_session)
    assert (await _begin(api_client))["count"] == 3


async def test_a_batch_leaves_the_estimate_out_while_market_statistics_are_not_shared(api_client, db_session, workspace):
    staff = workspace["jobs"]["staff"]
    estimates = {987_654, 876_543, 765_432}

    def bases(batch: list[dict]) -> set[int | None]:
        return {posting["estimated_pay"]["base_median"] if posting["estimated_pay"] else None for posting in batch}

    # Two postings in the run's first answer and one read on: every way a batch is answered.
    shared = await _begin(api_client, limit=2)
    shared_rest = _data(*await _read(api_client, "/picks/runs/next", run=shared["run"], cursor=2))["batch"]
    assert bases(shared["batch"]) | bases(shared_rest) == estimates
    assert None not in bases(shared["batch"]) and None not in bases(shared_rest)
    # Samples are drawn from the whole Board: the fourth role has no estimate to show.
    assert bases(_data(*await _read(api_client, "/picks/samples"))["samples"]) == estimates | {None}

    await _choose(db_session, market_statistic="not_shared")
    kept = await _begin(api_client, limit=2)
    rest = _data(*await _read(api_client, "/picks/runs/next", run=kept["run"], cursor=2))["batch"]
    samples = _data(*await _read(api_client, "/picks/samples"))["samples"]

    assert (len(kept["batch"]), len(rest), len(samples)) == (2, 1, 4)
    for batch in (kept["batch"], rest, samples):
        assert bases(batch) == {None}
    # The employer's own figure is the posting's, and stays.
    assert next(p for p in samples if p["job"] == staff)["stated_pay"]["base_max"] == 310_000
    assert not any(str(figure) in str(kept) + str(rest) + str(samples) for figure in estimates)


async def test_a_run_says_nothing_of_the_persons_reactions_while_pursuits_are_not_shared(api_client, db_session, workspace):
    await _picked(api_client, workspace)
    db_session.add(Favorite(job_id=workspace["jobs"]["staff"]))
    await db_session.commit()
    key = _key()

    shared = _data(*await _write(api_client, "POST", "/picks/runs", {}, key=key))
    assert [(row["job"], row["reaction"]["kind"]) for row in shared["reactions"]] == [(workspace["jobs"]["staff"], "saved")]
    assert shared["budget"]["picks"][0]["reaction"]["kind"] == "saved"

    await _choose(db_session, private_pursuit="not_shared")
    # The receipt keeps the answer whole; the replay under the new choice leaves the reactions out.
    replay = _data(*await _write(api_client, "POST", "/picks/runs", {}, key=key))
    fresh = await _begin(api_client)

    for answer in (replay, fresh):
        assert answer["reactions"] is None
        assert [row["reaction"] for row in answer["budget"]["picks"]] == [None, None]


async def test_the_list_leaves_out_postings_and_reactions_the_person_does_not_share(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _picked(api_client, workspace)
    await api_client.put(f"/api/jobs/{jobs['staff']}/feedback", json={"verdict": "dismissed", "reason": "company"})
    db_session.add(Favorite(job_id=jobs["principal"]))
    await db_session.commit()

    shared = _data(*await _read(api_client, "/picks"))
    assert [(row["job"], row["title"], row["reaction"]["kind"]) for row in shared["picks"]] == [
        (jobs["principal"], "Principal Product Manager, Risk", "saved"),
    ]

    await _choose(db_session, public_posting="not_shared")
    untitled = _data(*await _read(api_client, "/picks"))["picks"]
    assert [(row["job"], row["title"], row["company"]) for row in untitled] == [(jobs["principal"], None, None)]
    assert untitled[0]["reasons"] and untitled[0]["reaction"]["kind"] == "saved"

    await _choose(db_session, private_pursuit="not_shared")
    private = _data(*await _read(api_client, "/picks"))["picks"]
    # Leaving the removed pick out would say the person removed it.
    assert {row["job"] for row in private} == {jobs["staff"], jobs["principal"]}
    assert [row["reaction"] for row in private] == [None, None]
    error = _refused(*await _read(api_client, "/picks", view="removed"), "category_disabled")
    assert error["details"] == {
        "category": "private_pursuit", "setting": "agent_access.categories.private_pursuit", "field": "view",
    }


# --------------------------------------------------------------------------- #
# What the app's rail and Settings card read and change
# --------------------------------------------------------------------------- #


async def _state(api_client) -> dict:
    response = await api_client.get("/api/picks/state")
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_dot_is_lit_only_by_a_pick_newer_than_the_persons_last_visit(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    assert (await _state(api_client))["unseen_pick"] is False, "no pick, no dot"

    run = await _begin(api_client)
    await _outcomes(api_client, run, [
        _pick(jobs["staff"]), {"job": jobs["lead"], "verdict": "pass", "pass_code": "not_better"},
    ])
    assert (await _state(api_client))["unseen_pick"] is True

    opened = await api_client.post("/api/picks/opened")
    assert opened.status_code == 200 and opened.json()["unseen_pick"] is False
    assert (await _state(api_client))["unseen_pick"] is False, "a pick older than the visit lights nothing"
    assert _data(*await _read(api_client, "/picks/status"))["unseen_pick"] is False

    # A pass or a near miss made after the visit is not a pick.
    await _outcomes(api_client, run, [{
        "job": jobs["principal"], "verdict": "near_miss", "against_baseline": "comparable",
        "reasons": [_reason("Leads risk", ", but the posting names an on-call rotation.", "r1")],
    }])
    assert (await _state(api_client))["unseen_pick"] is False

    async with _fresh(db_session) as session:
        await session.execute(update(Job).where(Job.id == jobs["principal"]).values(content_hash="h-principal-2"))
        await session.commit()
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}))
    later = await _begin(api_client)
    await _outcomes(api_client, later, [_pick(jobs["principal"])])
    state = await _state(api_client)
    assert state["unseen_pick"] is True, "a yes or no, however many picks are new"

    # The person removed the new pick themself: nothing is left to look at.
    await api_client.put(f"/api/jobs/{jobs['principal']}/feedback", json={"verdict": "dismissed"})
    assert (await _state(api_client))["unseen_pick"] is False


async def test_the_settings_card_reads_who_checks_when_it_last_did_and_what_the_person_wants(api_client, workspace):
    await update_top_picks_settings_through(api_client)
    before = await _state(api_client)
    assert (before["state"], before["routine_host"], before["schedule"], before["last_check"]) == (
        "on", "claude-code", "daily 09:30 and 17:30", None,
    )
    assert before["brief_summary"] == "Not looking. Wants a whole product."

    run = await _begin(api_client)
    finished = _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}))

    after = await _state(api_client)
    assert after["last_check"]["host"] == "claude-code" and after["last_check"]["outcome"] == "finished"
    assert datetime.fromisoformat(after["last_check"]["finished_at"]) == datetime.fromisoformat(finished["finished_at"])
    last_run = _data(*await _read(api_client, "/picks/status"))["routine"]["last_run"]
    assert (last_run["host"], last_run["run"]) == ("claude-code", run["run"])


async def update_top_picks_settings_through(api_client) -> None:
    _data(*await _write(api_client, "PUT", "/picks/mode", {
        "state": "on", "routine_host": "claude-code", "schedule": "daily 09:30 and 17:30",
    }))


async def test_pausing_in_the_app_starts_no_run_and_keeps_everything_saved(api_client, db_session, workspace):
    await _picked(api_client, workspace)
    async with _fresh(db_session) as session:
        runs_before = await session.scalar(select(func.count()).select_from(PickRun))

    paused = await api_client.put("/api/picks/mode", json={"state": "off"})
    assert paused.status_code == 200 and paused.json()["state"] == "off"

    _refused(*await _write(api_client, "POST", "/picks/runs", {}), "mode_off")
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(PickRun)) == runs_before, "no run was opened"
        assert await session.scalar(select(func.count()).select_from(PickBrief)) == 1
    assert len(await _verdicts(db_session)) == 2
    assert _data(*await _read(api_client, "/background"))["confirmed"] is True
    assert _data(*await _read(api_client, "/picks"))["count"] == 2, "the picks made before the pause stay"
    assert paused.json()["brief_summary"] == "Not looking. Wants a whole product."

    resumed = await api_client.put("/api/picks/mode", json={"state": "on"})
    assert resumed.json()["state"] == "on"
    assert (await _begin(api_client))["run"].startswith("run_")
    assert (await api_client.put("/api/picks/mode", json={"state": "paused"})).status_code == 422


async def test_the_app_cannot_switch_on_a_mode_that_was_never_set_up(api_client, db_session, scratch_scope):
    refused = await api_client.put("/api/picks/mode", json={"state": "on"})

    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "invalid-input"
    assert (await get_top_picks_settings(db_session)).state == "never_set_up"
    assert await _state(api_client) == {
        "state": "never_set_up", "routine_host": None, "schedule": None, "last_check": None, "brief_summary": None,
        "unseen_pick": False, "health": "off", "waiting": 0, "read_this_week": 0, "passed_this_week": 0,
        "routine_host_connection": None, "daily_limit": 1000, "daily_limit_max": 5000,
    }


async def test_remove_deletes_the_cv_the_reading_and_the_brief_and_nothing_else(
    api_client, db_session, workspace, tmp_path, monkeypatch,
):
    jobs = workspace["jobs"]
    monkeypatch.setattr(background_store, "documents_dir", lambda: tmp_path)
    added = _data(*await _write(api_client, "POST", "/background/documents", {
        "filename": "Dana Reyes CV.pdf", "content_base64": base64.b64encode(b"%PDF-1.7 Dana Reyes").decode(),
    }))
    _data(*await _write(api_client, "PUT", "/background", {
        "reading": {"current": {"title": "Senior Product Manager"}}, "source": "document",
        "document_id": added["document"]["id"], "confirmed": True,
    }))
    _data(*await _write(api_client, "PATCH", "/brief", {"if_revision": 1, "reason": "Budget.", "budget": 5}))
    run = await _begin(api_client)
    await _outcomes(api_client, run, [_pick(jobs["staff"]), _pick(jobs["principal"])])
    # A finish note may repeat the person's facts too.
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {
        "run": run["run"], "outcome": "finished", "note": "Two above the 210,000 floor.",
    }))
    await api_client.put(f"/api/jobs/{jobs['lead']}/feedback", json={"verdict": "dismissed", "reason": "wrong_role"})
    db_session.add(Favorite(job_id=jobs["staff"]))
    await db_session.commit()
    open_run = await _begin(api_client)
    assert len(list(tmp_path.iterdir())) == 1
    async with _fresh(db_session) as session:
        held = (await session.scalars(select(CommandReceipt))).all()
    # Before Remove the receipts do hold the person's facts, so their absence after it means something.
    assert {"background.set", "background.add_document", "brief.patch", "picks.begin", "picks.finish"} <= {
        row.operation for row in held
    }
    assert "210000" in str([row.result for row in held]) and "Senior Product Manager" in str([row.result for row in held])

    removed = await api_client.delete("/api/picks/setup")

    assert removed.status_code == 200 and removed.json() == {
        "briefs": 2, "readings": 2, "documents": 1, "verdicts": 2,
    }
    assert list(tmp_path.iterdir()) == [], "the CV is gone from the disk"
    async with _fresh(db_session) as session:
        counts = {
            model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in (PickBrief, CandidateDocument, Job, Favorite, JobFeedback, PickVerdict, PickRun)
        }
        left_open = await session.get(PickRun, open_run["run"])
    assert (counts["pick_brief"], counts["candidate_document"]) == (0, 0)
    assert _data(*await _read(api_client, "/background"))["saved"] is False
    # The person's saved role, their Not for me and the postings are untouched; that two roles were
    # read is still on record.
    assert (counts["jobs"], counts["favorites"], counts["job_feedback"], counts["pick_verdict"], counts["pick_run"]) == (
        4, 1, 1, 2, 2,
    )
    # What the verdicts said quoted the person ("above the 210,000 you hold"): none of it is left, anywhere.
    kept = await _verdicts(db_session)
    assert [(row.reasons, row.note, row.superseded_at is not None) for row in kept] == [([], None, True)] * 2
    async with _fresh(db_session) as session:
        for model in (PickVerdict, PickRun):
            rows = (await session.scalars(select(model))).all()
            assert "210,000" not in str([vars(row) for row in rows])
    # The receipts of the writes that saved the reading, the brief and the finish note repeated them:
    # gone with them.
    async with _fresh(db_session) as session:
        receipts = (await session.scalars(select(CommandReceipt))).all()
        finished = await session.get(PickRun, run["run"])
    assert {row.operation for row in receipts} == {"picks.decide"}, "other receipts stay"
    assert finished.note is None and finished.outcome == "finished"
    assert not any(word in str([row.result for row in receipts]) for word in ("210", "Senior Product Manager", "Dana"))
    # Activity is kept, and never held the file's name, which can be the person's own.
    async with _fresh(db_session) as session:
        logged = (await session.scalars(
            select(AgentActivity).where(AgentActivity.operation == "background.add_document")
        )).all()
    assert [row.subject for row in logged] == [{"topic": "background.document_added", "document": added["document"]["id"]}]
    assert "Dana" not in str([(row.subject, row.changes) for row in logged])
    assert _data(*await _read(api_client, "/picks"))["picks"] == [], "a pick with nothing left to say is no pick"
    assert (await api_client.get("/api/picks/removed")).json() == {"picks": []}
    assert (left_open.outcome, left_open.note) == ("abandoned", "Top picks was removed.")
    board = (await api_client.get("/api/jobs", params={"status": "open"})).json()
    assert {row["id"] for row in board["items"]} == {jobs["staff"], jobs["principal"], jobs["underpaid"]}
    assert (await api_client.get("/api/jobs", params={"favorites_only": True})).json()["total"] == 1

    state = await _state(api_client)
    assert (state["state"], state["brief_summary"], state["routine_host"]) == ("never_set_up", None, None)
    status = _data(*await _read(api_client, "/picks/status"))
    assert (status["setup"]["next_step"], status["setup"]["saved_parts"]) == ("background", [])
    _refused(*await _write(api_client, "POST", "/picks/runs", {}), "brief_required")
    # Removing again finds no CV, reading or brief, and fails nothing.
    assert (await api_client.delete("/api/picks/setup")).json() == {
        "briefs": 0, "readings": 0, "documents": 0, "verdicts": 2,
    }

    # Setting up again is a new brief with a number no verdict was made under, and the roles are read afresh.
    again = _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 0, "reason": "Starting over.", "urgency": "open", "pulls": [{"text": "Owns a product"}],
        "activate": True,
    }))
    assert again["version"] == 3, "versions 1 and 2 were judged under, and are not given out again"
    _data(*await _write(api_client, "PUT", "/picks/mode", {"state": "on"}))
    fresh = await _begin(api_client)
    assert jobs["staff"] in {posting["job"] for posting in fresh["batch"]}
    assert await _outcomes(api_client, fresh, [_pick(jobs["staff"], [
        _reason("Owns pricing", " end to end."), _reason("Leads a team", " of six.", "urgency"),
    ])]) == {jobs["staff"]: None}
    assert [row["job"] for row in _data(*await _read(api_client, "/picks"))["picks"]] == [jobs["staff"]]


async def test_the_daily_limit_starts_at_a_thousand_and_the_person_changes_it_in_the_app_or_through_the_assistant(
    api_client, db_session, workspace,
):
    assert (await _state(api_client))["daily_limit"] == 1000
    assert _data(*await _read(api_client, "/picks/status"))["volume"]["daily_cap"] == 1000

    # Through the assistant, naming the limit alone: the mode and its clock stay as they were.
    before = await get_top_picks_settings(db_session)
    changed = _data(*await _write(api_client, "PUT", "/picks/mode", {"daily_cap": 2}))
    assert (changed["daily_cap"], changed["state"]) == (2, "on")
    assert datetime.fromisoformat(changed["enabled_at"]) == before.enabled_at
    async with _fresh(db_session) as session:
        listed = await session.scalar(
            select(AgentActivity).where(AgentActivity.operation == "picks.switch").order_by(AgentActivity.id.desc())
        )
    assert (listed.summary, listed.changes) == ("Changed the top picks settings", [])
    first = await _begin(api_client)
    assert first["counts"] == {"waiting": 3, "ruled_out_by_rules": 1, "handed": 2, "held_back": 1}

    # In the app: the same number, read back by both.
    in_app = await api_client.put("/api/picks/mode", json={"daily_limit": 300})
    assert in_app.status_code == 200 and (in_app.json()["daily_limit"], in_app.json()["state"]) == (300, "on")
    assert _data(*await _read(api_client, "/picks/status"))["volume"]["daily_cap"] == 300
    # The role the lower limit held back is read the same day once the limit allows it, beside the two
    # the first run was handed and never judged.
    assert (await _begin(api_client))["counts"] == {
        "waiting": 3, "ruled_out_by_rules": 1, "handed": 3, "held_back": 0,
    }

    for refused in ({"daily_limit": 0}, {"daily_limit": 5001}, {}):
        assert (await api_client.put("/api/picks/mode", json=refused)).status_code == 422
    _refused(*await _write(api_client, "PUT", "/picks/mode", {"daily_cap": 5001}), "invalid_input")
    assert (await _state(api_client))["daily_limit"] == 300

    # Pausing keeps the person's number; Remove returns it to the default.
    assert (await api_client.put("/api/picks/mode", json={"state": "off"})).json()["daily_limit"] == 300
    await api_client.delete("/api/picks/setup")
    assert (await _state(api_client))["daily_limit"] == 1000


async def test_the_first_run_after_setup_reads_the_roles_already_open_and_a_resumed_mode_reads_what_arrived_meanwhile(
    api_client, db_session, workspace,
):
    jobs = workspace["jobs"]
    # The mode was turned on a moment ago; every role on the Board was open hours before that.
    await update_top_picks_settings(db_session, enabled_at=datetime.now(UTC))
    await db_session.commit()

    status = _data(*await _read(api_client, "/picks/status"))
    assert status["routine"]["waiting"] == 3
    # They wait from when the mode was turned on, not from when they were first seen.
    assert datetime.fromisoformat(status["routine"]["oldest_waiting_since"]) > workspace["now"]
    first = await _begin(api_client)
    assert {posting["job"] for posting in first["batch"]} == {jobs["staff"], jobs["principal"], jobs["lead"]}
    await _outcomes(api_client, first, [
        {"job": posting["job"], "verdict": "pass", "pass_code": "not_better"} for posting in first["batch"]
    ])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": first["run"], "outcome": "finished"}))

    assert (await api_client.put("/api/picks/mode", json={"state": "off"})).json()["state"] == "off"
    arrived = make_job("arrived", company="stripe", title="Principal Product Manager, Identity",
                       level_band="principal", first_seen=datetime.now(UTC), last_seen=datetime.now(UTC),
                       content_hash="h-arrived")
    db_session.add(arrived)
    await db_session.commit()
    assert (await api_client.put("/api/picks/mode", json={"state": "on"})).json()["state"] == "on"

    resumed = await _begin(api_client)
    assert [posting["job"] for posting in resumed["batch"]] == [arrived.id], "seen during the pause, read after it"


# --------------------------------------------------------------------------- #
# The Top picks screen: the Radar's own list, narrowed to the picks
# --------------------------------------------------------------------------- #


async def _radar(api_client, **params) -> dict:
    response = await api_client.get("/api/jobs", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _judged(api_client, workspace) -> None:
    """Two picks (staff, then principal a little later), a pass and nothing on the fourth role."""
    jobs = workspace["jobs"]
    run = await _begin(api_client)
    await _outcomes(api_client, run, [_pick(jobs["staff"])])
    await _outcomes(api_client, run, [
        _pick(jobs["principal"], [_reason("Leads risk", " for the whole company.", "p1"),
                                  _reason("Stripe", " is on your list.", "targets")]),
        {"job": jobs["lead"], "verdict": "pass", "pass_code": "not_better"},
    ])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": run["run"], "outcome": "finished"}))


async def test_the_radar_list_narrowed_to_picks_is_the_radars_rows_with_their_reasons(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _judged(api_client, workspace)
    # The app reads its own list: the assistant's switches do not gate it and nothing is logged as the assistant's.
    await set_agent_access(db_session, AgentAccessConfig(enabled=False, allow_writes=False))
    await db_session.commit()
    async with _fresh(db_session) as session:
        logged = await session.scalar(select(func.count()).select_from(AgentActivity))

    picks = await _radar(api_client, top_picks=True)
    radar = await _radar(api_client)

    assert picks["total"] == 2 and radar["total"] == 4
    assert [row["id"] for row in picks["items"]] == [jobs["principal"], jobs["staff"]], "newest pick first"
    by_id = {row["id"]: row for row in radar["items"]}
    for row in picks["items"]:
        plain = by_id[row["id"]]
        assert {key: value for key, value in row.items() if key not in ("pick_reasons", "picked_at")} == plain
        assert "pick_reasons" not in plain and "picked_at" not in plain, "the Radar's own rows are unchanged"
    staff = next(row for row in picks["items"] if row["id"] == jobs["staff"])
    assert staff["pick_reasons"] == [
        {"opening": "Staff level", "rest": ", one step above your Senior role today."},
        {"opening": "240,000 to 310,000 base", "rest": ", above the 210,000 you hold."},
    ]
    assert datetime.fromisoformat(staff["picked_at"]) > workspace["now"]
    async with _fresh(db_session) as session:
        assert await session.scalar(select(func.count()).select_from(AgentActivity)) == logged

    # Every Radar control still narrows, orders and pages the picks.
    assert [row["id"] for row in (await _radar(api_client, top_picks=True, company="stripe"))["items"]] == [jobs["principal"]]
    async with _fresh(db_session) as session:
        await session.execute(update(Job).values(search_vector=func.to_tsvector("english", Job.title)))
        await session.commit()
    assert [row["id"] for row in (await _radar(api_client, top_picks=True, q="Pricing"))["items"]] == [jobs["staff"]]
    assert (await _radar(api_client, top_picks=True, q="Billing"))["total"] == 0, "a role that is no pick is not found"
    assert (await _radar(api_client, q="Billing"))["total"] == 1
    assert [row["id"] for row in (await _radar(api_client, top_picks=True, discloses_pay=True))["items"]] == [
        jobs["staff"],
    ]
    assert [row["id"] for row in (await _radar(api_client, top_picks=True, level_band="principal"))["items"]] == [
        jobs["principal"],
    ]
    by_title = await _radar(api_client, top_picks=True, sort="title", order="asc")
    assert [row["title"] for row in by_title["items"]] == [
        "Principal Product Manager, Risk", "Staff Product Manager, Pricing",
    ]
    oldest_first = await _radar(api_client, top_picks=True, order="asc")
    assert [row["id"] for row in oldest_first["items"]] == [jobs["staff"], jobs["principal"]]
    second = await _radar(api_client, top_picks=True, limit=1, offset=1)
    assert (second["total"], [row["id"] for row in second["items"]]) == (2, [jobs["staff"]])


async def test_newest_among_picks_is_the_newest_pick_not_the_newest_posting(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _judged(api_client, workspace)
    # The staff role was posted last, but picked first.
    async with _fresh(db_session) as session:
        await session.execute(update(Job).where(Job.id == jobs["staff"]).values(first_seen=datetime.now(UTC)))
        await session.commit()

    assert [row["id"] for row in (await _radar(api_client, top_picks=True))["items"]] == [
        jobs["principal"], jobs["staff"],
    ]
    # Control: on the Radar itself Newest is still the newest posting.
    assert (await _radar(api_client))["items"][0]["id"] == jobs["staff"]


async def test_removed_picks_read_newest_removal_first_not_newest_pick_first(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _judged(api_client, workspace)
    assert [row["id"] for row in (await _radar(api_client, top_picks=True))["items"]] == [
        jobs["principal"], jobs["staff"],
    ]
    for job in (jobs["principal"], jobs["staff"]):
        await api_client.put(f"/api/jobs/{job}/feedback", json={"verdict": "dismissed", "reason": "company"})
    async with _fresh(db_session) as session:
        await session.execute(update(JobFeedback).where(JobFeedback.job_id == jobs["staff"]).values(
            created_at=datetime.now(UTC) + timedelta(minutes=5),
        ))
        await session.commit()

    removed = await _radar(api_client, top_picks=True, dismissed_only=True)

    assert [row["id"] for row in removed["items"]] == [jobs["staff"], jobs["principal"]]


async def test_a_role_the_radar_would_not_show_is_never_listed_as_a_pick(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _judged(api_client, workspace)

    async def listed() -> set[int]:
        return {row["id"] for row in (await _radar(api_client, top_picks=True))["items"]}

    assert await listed() == {jobs["staff"], jobs["principal"]}

    await api_client.put(f"/api/jobs/{jobs['staff']}/feedback", json={"verdict": "dismissed", "reason": "company"})
    assert await listed() == {jobs["principal"]}, "Not for me removes it here as on the Radar"
    assert [row["id"] for row in (await _radar(api_client, top_picks=True, dismissed_only=True))["items"]] == [
        jobs["staff"]
    ]
    await api_client.delete(f"/api/jobs/{jobs['staff']}/feedback")

    async with _fresh(db_session) as session:
        await session.execute(update(TrackedCompany).where(TrackedCompany.slug == "stripe").values(visible=False))
        await session.commit()
    assert await listed() == {jobs["staff"]}, "a hidden company's role is no pick to show"
    async with _fresh(db_session) as session:
        await session.execute(update(TrackedCompany).where(TrackedCompany.slug == "stripe").values(visible=True))
        await session.execute(update(Job).where(Job.id == jobs["staff"]).values(in_scope=False))
        await session.commit()
    assert await listed() == {jobs["principal"]}, "nor one outside the saved scope"
    async with _fresh(db_session) as session:
        await session.execute(update(Job).where(Job.id == jobs["staff"]).values(in_scope=True))
        await session.execute(update(Job).where(Job.id == jobs["principal"]).values(status="closed"))
        await session.commit()
    assert await listed() == {jobs["staff"]}, "nor a closed one"


async def test_only_a_pick_that_stands_is_listed(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    trial = await _begin(api_client, trial=True)
    await _outcomes(api_client, trial, [_pick(jobs["lead"])])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {"run": trial["run"], "outcome": "finished"}))
    run = await _begin(api_client)
    await _outcomes(api_client, run, [
        _pick(jobs["staff"]),
        {"job": jobs["principal"], "verdict": "near_miss", "against_baseline": "comparable",
         "reasons": [_reason("Leads risk", ", but on call.", "r1")]},
    ])

    # Not the trial's pick, not the near miss, not the role nobody judged.
    assert [row["id"] for row in (await _radar(api_client, top_picks=True))["items"]] == [jobs["staff"]]

    _data(*await _write(api_client, "PATCH", "/brief", {
        "if_revision": 1, "reason": "Not Google.",
        "rules": [{"id": "r1", "text": "No on-call"},
                  {"text": "Not Google", "check": {"form": "avoid_companies", "companies": ["google"]}}],
    }))
    assert (await _radar(api_client, top_picks=True))["total"] == 0, "a new hard rule takes the pick away at once"


async def test_the_filter_options_of_the_picks_offer_only_what_the_picks_contain(api_client, workspace):
    await _judged(api_client, workspace)

    picks = (await api_client.get("/api/facets", params={"top_picks": True})).json()
    radar = (await api_client.get("/api/facets")).json()

    assert (picks["total"], radar["total"]) == (2, 4)
    assert picks["counts"]["company"] == {"google": 1, "stripe": 1}
    assert radar["counts"]["company"] == {"google": 2, "stripe": 2}
    assert picks["counts"]["level_band"] == {"staff": 1, "principal": 1}
    assert radar["counts"]["level_band"] == {"staff": 2, "principal": 2}
    assert picks["counts"]["location_group"] == {"silicon_valley": 2}
    assert set(picks["families"]) == {"product_management"} and len(radar["families"]) > 1

    # A pick the person removed no longer offers its company.
    await api_client.put(f"/api/jobs/{workspace['jobs']['staff']}/feedback", json={"verdict": "dismissed"})
    removed = (await api_client.get("/api/facets", params={"top_picks": True})).json()
    assert (removed["total"], removed["counts"]["company"], set(removed["companies"])) == (1, {"stripe": 1}, {"stripe"})


async def test_the_picks_total_counts_a_place_set_through_its_picked_member(api_client, db_session, workspace):
    jobs = workspace["jobs"]
    await _judged(api_client, workspace)
    # The staff pick turns out to be one place of a role listed at two, and the
    # other place was seen first: it would stand for the role on the Radar.
    async with _fresh(db_session) as session:
        elsewhere = make_job(
            "staff-nyc", title="Staff Product Manager, Pricing", first_seen=workspace["now"] - timedelta(days=1),
            last_seen=workspace["now"], content_hash="h-staff-nyc", locations=["New York, NY, USA"],
            location_groups=["nyc"],
        )
        session.add(elsewhere)
        place_set = JobPlaceSet(company="google", title="staff product manager pricing", text_hash="0" * 32, size=2,
                                places=["New York, NY, USA", "Mountain View, CA, USA"], rule_version="t1")
        session.add(place_set)
        await session.flush()
        session.add_all([JobPlaceSetMember(job_id=job_id, set_id=place_set.id, status="auto")
                         for job_id in (elsewhere.id, jobs["staff"])])
        await session.commit()

    picks = await _radar(api_client, top_picks=True)
    facets = (await api_client.get("/api/facets", params={"top_picks": True})).json()

    assert {row["id"] for row in picks["items"]} == {jobs["staff"], jobs["principal"]}
    assert facets["total"] == picks["total"] == 2
    assert facets["counts"]["company"] == {"google": 1, "stripe": 1}
    # Control: the Radar's own total counts the role once too.
    assert (await api_client.get("/api/facets")).json()["total"] == 4


async def test_the_state_says_how_the_checks_stand_and_what_the_week_held(api_client, db_session, workspace, monkeypatch):
    jobs = workspace["jobs"]
    # Only a host `connect` sets up has files to read: asking about any other is a defect.
    connections: dict[str, str | None] = {"claude-code": "rule_missing", "codex": "connected"}
    monkeypatch.setattr(agent_hosts, "connection", lambda host: connections[host])
    before = await _state(api_client)
    assert (before["health"], before["waiting"], before["read_this_week"], before["passed_this_week"]) == (
        "never_ran", 3, 0, 0,
    )
    assert before["routine_host_connection"] is None, "no assistant is named as running the checks yet"

    await update_top_picks_settings_through(api_client)
    await _judged(api_client, workspace)
    after = await _state(api_client)
    assert (after["health"], after["waiting"], after["read_this_week"], after["passed_this_week"]) == (
        "healthy", 0, 3, 1,
    )
    assert after["routine_host_connection"] == "rule_missing", "it asks before each command"
    assert after["last_check"]["note"] is None

    # A role read twice this week counts once; one judged before the week does not count.
    async with _fresh(db_session) as session:
        await session.execute(update(Job).where(Job.id == jobs["lead"]).values(content_hash="h-lead-2"))
        await session.execute(
            update(PickVerdict).where(PickVerdict.job_id == jobs["principal"])
            .values(created_at=datetime.now(UTC) - timedelta(days=8))
        )
        await session.commit()
    again = await _begin(api_client)
    assert (await _state(api_client))["waiting"] == 1
    await _outcomes(api_client, again, [{"job": jobs["lead"], "verdict": "pass", "pass_code": "other"}])
    _data(*await _write(api_client, "POST", "/picks/runs/finish", {
        "run": again["run"], "outcome": "stopped", "note": "The plan's limit was reached.",
    }))

    stopped = await _state(api_client)
    assert (stopped["read_this_week"], stopped["passed_this_week"]) == (2, 1)
    assert (stopped["health"], stopped["last_check"]["outcome"], stopped["last_check"]["note"]) == (
        "stopped_early", "stopped", "The plan's limit was reached.",
    )
    connections["claude-code"] = None
    assert (await _state(api_client))["routine_host_connection"] is None, "no longer connected"

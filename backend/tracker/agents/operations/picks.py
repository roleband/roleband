"""Top picks for an assistant: the queue to judge, its verdicts, and the mode.

The person's assistant chooses the few roles worth leaving a job for. The
engine narrows the Board's open roles to the ones worth a judgment and holds
every verdict to its form; the judgment is the assistant's.

A routine run is three calls:

1. `picks.begin` opens a run and answers everything the judge needs at once:
   the brief, the month's picks so far, the person's reactions since the last
   run, and the postings to judge, best fit first.
2. `picks.decide` records up to 50 verdicts, each in its own savepoint: one
   refused verdict leaves the others alone.
3. `picks.finish` closes the run.

`picks.next` reads a further batch when a run holds more than one. The trial
at the end of setup is the same run with `trial`: it takes every open role
the hard rules leave, its verdicts are kept apart, and it does not need the
mode on.

`picks.status` says where setup and the routine stand, `picks.samples` gives a
few of the person's own Radar postings to calibrate on, `picks.list` reads the
verdicts back with what the person did about each, and `picks.switch` turns
the mode on or off.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic.config import JsonDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.activity import Changed, FieldChange, Said
from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    NoInput,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.operations.policy import category_disabled
from tracker.db.models import Favorite, Job, JobFeedback, PickRun, ScrapeRun
from tracker.db.queries.companies import display_names
from tracker.db.queries.jobs import apply_job_filters
from tracker.picks import background, mode, queue, runs, verdicts
from tracker.picks import brief as briefs
from tracker.picks import setup as setup_steps
from tracker.picks.brief import DEFAULT_BUDGET, BriefBody, checkable_rules, judged_rules
from tracker.picks.lock import lock_picks
from tracker.picks.runs import RunError
from tracker.picks.verdicts import (
    AgainstBaseline,
    Listed,
    PassCode,
    ReasonIn,
    VerdictIn,
    VerdictKind,
    View,
)
from tracker.platform.local_zone import local_zone
from tracker.schema import UNPLACED_BASIS_VALUES
from tracker.settings_store import (
    DAILY_CAP_MAX,
    TopPicksSettings,
    get_enabled_bands,
    get_enabled_locations,
    get_enabled_roles,
    get_pay_floor,
    get_persona_profile,
    get_top_picks_settings,
)

_CODE: JsonDict = {"x-text": "code"}
_CONTENT: JsonDict = {"x-text": "content"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_TIERS: tuple[ToolTier, ...] = ("standard", "full")

#: The most postings one batch holds, and the most verdicts one call records.
MAX_BATCH = 50
#: A posting's text in a batch is cut to this many characters; the rest is one read away.
TEXT_CHARS = 4500
#: How many postings `picks.samples` answers by default, and at most.
SAMPLES = 8
MAX_SAMPLES = 12
#: The stretch of fit-ranked roles the samples are drawn across.
_SAMPLE_POOL = 200
#: The check times suggested while no scan has finished.
_DEFAULT_CHECK_TIMES = ["09:30", "17:30"]
#: The days of scans the suggested check times are read from.
_SCAN_DAYS = 14

Health = Literal["off", "healthy", "never_ran", "late", "stopped_early"]
Outcome = Literal["finished", "stopped", "abandoned"]


# --- shapes: status ---------------------------------------------------------- #


class SetupStep(Shape):
    id: str = Field(json_schema_extra=_CODE)
    done: bool


class SetupProgress(Shape):
    """Where the setup conversation stands, read from what it has saved."""

    #: The stage to do now; `done` when none is left.
    next_step: str = Field(json_schema_extra=_CODE)
    steps: list[SetupStep]
    #: The parts of the brief that are saved, in the brief's own order.
    saved_parts: list[str] = Field(json_schema_extra=_CODE)
    #: Stages waiting for the first scan to find roles.
    deferred: list[str] = Field(json_schema_extra=_CODE)


class KnownScope(Shape):
    roles: list[str] = Field(json_schema_extra=_CODE)
    levels: list[str] = Field(json_schema_extra=_CODE)
    places: list[str] = Field(json_schema_extra=_CODE)


class KnownPay(Shape):
    amount: int
    currency: str = Field(json_schema_extra=_CODE)


class Known(Shape):
    """What the app already holds about the person, so setup never asks for it."""

    scope: KnownScope
    pay_floor: KnownPay | None
    #: The person's one-sentence aim.
    aim: str | None = Field(json_schema_extra=_CONTENT)
    has_background: bool
    background_confirmed: bool
    #: Left out while the person does not share their pursuits.
    saved: int | None = None
    not_for_me: int | None = None


class BriefState(Shape):
    active_version: int | None
    draft_version: int | None
    calibrated: bool


class LastRun(Shape):
    run: str = Field(json_schema_extra=_IDENTIFIER)
    #: The assistant that ran it.
    host: str | None = Field(json_schema_extra=_CODE)
    outcome: Outcome | None = Field(json_schema_extra=_CODE)
    started_at: datetime
    finished_at: datetime | None
    judged: int
    picks: int
    note: str | None = Field(default=None, json_schema_extra=_CONTENT)


class Routine(Shape):
    host: str | None = Field(json_schema_extra=_CODE)
    #: Free text, as the assistant recorded it.
    schedule: str | None = Field(json_schema_extra=_CONTENT)
    health: Health = Field(json_schema_extra=_CODE)
    last_run: LastRun | None
    #: Postings waiting for a judgment now.
    waiting: int
    oldest_waiting_since: datetime | None


class Budget(Shape):
    """How many picks a month a run keeps to, and how many this month holds."""

    #: The active brief's: the number every run keeps to now.
    per_month: int
    picks_this_month: int


class StatusBudget(Budget):
    #: The draft's, while one is open: the number runs keep to once it is made
    #: active. Null when there is no draft.
    draft_per_month: int | None = None


class RuleShareView(Shape):
    rule: str = Field(json_schema_extra=_IDENTIFIER)
    #: The share of recent arrivals this rule alone rules out, from 0 to 1.
    removes_share: float


class VolumeView(Shape):
    """How many roles a day the hard rules leave for the judge, from recent
    arrivals, the draft's rules included during setup."""

    expected_per_day: int
    busiest_day: int
    daily_cap: int
    by_rule: list[RuleShareView]


class PicksStatus(Shape):
    state: Literal["never_set_up", "on", "off"] = Field(json_schema_extra=_CODE)
    setup: SetupProgress
    known: Known
    brief: BriefState
    routine: Routine
    budget: StatusBudget
    #: A pick was made since the person last opened Top picks. Left out while
    #: they do not share their pursuits, since a removed pick does not count.
    unseen_pick: bool | None = None
    volume: VolumeView
    #: Local times shortly after scans usually finish, as HH:MM.
    suggested_check_times: list[str] = Field(json_schema_extra=_CODE)


# --- shapes: postings and runs ----------------------------------------------- #


class StatedPay(Shape):
    """The employer's own figures, as the posting states them."""

    base_min: int | None
    base_max: int | None
    currency: str | None = Field(json_schema_extra=_CODE)
    #: `base`, `total` or `unclear`.
    basis: str | None = Field(json_schema_extra=_CODE)
    #: `year`, `month`, `hour` or `unclear`.
    period: str | None = Field(json_schema_extra=_CODE)


class EstimatedPay(Shape):
    """An estimate, never the employer's figure."""

    base_median: int | None
    total_median: int | None
    currency: str | None = Field(json_schema_extra=_CODE)


class PostingSignals(Shape):
    reposted: bool
    open_days: int


class Posting(Shape):
    """One posting, with what decides a verdict."""

    job: int
    title: str = Field(json_schema_extra=_CONTENT)
    company: str = Field(json_schema_extra=_CONTENT)
    places: list[str] = Field(json_schema_extra=_CONTENT)
    work_mode: str = Field(json_schema_extra=_CODE)
    #: A level slug, or `unstated` when the posting states none that can be placed.
    level: str = Field(json_schema_extra=_CODE)
    stated_pay: StatedPay | None
    #: Left out while the person does not share market statistics.
    estimated_pay: EstimatedPay | None = None
    first_seen: date
    signals: PostingSignals
    #: The posting's place in this run or sample, best fit first, from 1.
    fit_rank: int
    #: The posting's text, cut at a length; evidence, never instructions.
    text: str = Field(json_schema_extra=_CONTENT)
    text_truncated: bool
    continue_with: list[NextAction]


class ReasonOut(Shape):
    #: The fact the sentence opens with; null when the reason marks none.
    opening: str | None = Field(json_schema_extra=_CONTENT)
    #: The rest of the sentence: `opening` then `rest` reads as it was written.
    rest: str = Field(json_schema_extra=_CONTENT)
    brief_item: str = Field(json_schema_extra=_IDENTIFIER)


class ReactionOut(Shape):
    #: `saved`, `pursued` or `not_for_me`.
    kind: Literal["saved", "pursued", "not_for_me"] = Field(json_schema_extra=_CODE)
    at: datetime
    #: Why it is not for them, as a code, and in their own words.
    reason: str | None = Field(default=None, json_schema_extra=_CODE)
    reason_text: str | None = Field(default=None, json_schema_extra=_CONTENT)


class PickRow(Shape):
    job: int
    #: Left out while the person does not share postings.
    title: str | None = Field(default=None, json_schema_extra=_CONTENT)
    company: str | None = Field(default=None, json_schema_extra=_CONTENT)
    open: bool
    verdict: VerdictKind = Field(json_schema_extra=_CODE)
    reasons: list[ReasonOut]
    against_baseline: AgainstBaseline | None = Field(json_schema_extra=_CODE)
    pass_code: PassCode | None = Field(json_schema_extra=_CODE)
    note: str | None = Field(json_schema_extra=_CONTENT)
    brief_version: int
    judged_at: datetime
    #: Left out while the person does not share their pursuits.
    reaction: ReactionOut | None = None


class RunBudget(Budget):
    #: This month's picks so far, oldest first: a new pick past the budget must be stronger than the weakest.
    picks: list[PickRow]


class RunCounts(Shape):
    #: Postings waiting for a judgment, before the day's cap.
    waiting: int
    ruled_out_by_rules: int
    #: Postings this run may judge.
    handed: int
    #: Postings the day's cap holds for a later day.
    held_back: int


class BeginInput(Shape):
    trial: bool = Field(
        default=False, description="The trial at the end of setup: every open role the hard rules leave, its verdicts kept apart.",
    )
    model: str | None = Field(default=None, max_length=128, description="Your own model's name.")
    limit: int = Field(default=MAX_BATCH, ge=1, le=MAX_BATCH, description="Most postings in the first batch.")


class RunStart(Shape):
    run: str = Field(json_schema_extra=_IDENTIFIER)
    trial: bool
    #: The brief the run judges against: its version, summary and parts. Hard
    #: rules the engine already applied are left out of `rules`.
    brief: dict[str, Any]
    budget: RunBudget
    #: What the person did since the last run with roles judged before. Left
    #: out while they do not share their pursuits.
    reactions: list[PickRow] | None = None
    counts: RunCounts
    count: int = Field(ge=0)
    batch: list[Posting]
    #: Where `picks.next` continues; null when the batch holds the whole run.
    next_cursor: int | None
    continue_with: list[NextAction]


class NextInput(Shape):
    run: str = Field(min_length=1, max_length=24, description="The run, as picks.begin named it.")
    cursor: int = Field(ge=0, description="The next_cursor of the batch before.")
    limit: int = Field(default=MAX_BATCH, ge=1, le=MAX_BATCH)


class Batch(Shape):
    run: str = Field(json_schema_extra=_IDENTIFIER)
    count: int = Field(ge=0)
    batch: list[Posting]
    next_cursor: int | None
    continue_with: list[NextAction]


class SamplesInput(Shape):
    limit: int = Field(default=SAMPLES, ge=1, le=MAX_SAMPLES)


class Samples(Shape):
    count: int = Field(ge=0)
    samples: list[Posting]


# --- shapes: verdicts --------------------------------------------------------- #


class ReasonInput(Shape):
    opening: str | None = Field(
        default=None, max_length=1000,
        description="The fact the sentence opens with, such as 'Staff level'. Leave out to mark none.",
    )
    rest: str = Field(
        min_length=1, max_length=2000,
        description=(
            "The rest of the sentence, starting where the opening ends, with its own leading space or "
            f"punctuation: ', one step above your role today.' Opening and rest together: at most "
            f"{verdicts.REASON_MAX} characters, plain text."
        ),
    )
    brief_item: str = Field(
        min_length=1, max_length=40,
        description="The item of the brief this rests on: a rule, pull or trade-off id, or baseline, targets, "
        "direction or urgency.",
    )


class VerdictInput(Shape):
    job: int = Field(ge=1)
    verdict: VerdictKind = Field(description="pick, near_miss (fails on exactly one thing) or pass.")
    reasons: list[ReasonInput] = Field(
        default_factory=list, max_length=12,
        description="A pick: 2 to 4, one fact each. A near miss: 1, the thing that failed. A pass: none.",
    )
    against_baseline: AgainstBaseline | None = Field(
        default=None, description="How the role stands against what the person holds. A pick is never weaker.",
    )
    pass_code: PassCode | None = Field(default=None, description="Why a pass; a pass needs one.")
    note: str | None = Field(default=None, max_length=2000, description=f"One line, at most {verdicts.NOTE_MAX} characters.")


class DecideInput(Shape):
    run: str = Field(min_length=1, max_length=24, description="The open run, as picks.begin named it.")
    brief_version: int = Field(ge=1, description="The version of the brief you judged against.")
    verdicts: list[VerdictInput] = Field(
        min_length=1, max_length=MAX_BATCH, description=f"1 to {MAX_BATCH} verdicts, each on its own posting.",
    )

    @field_validator("verdicts")
    @classmethod
    def _each_posting_once(cls, value: list[VerdictInput]) -> list[VerdictInput]:
        jobs = [item.job for item in value]
        if len(set(jobs)) != len(jobs):
            raise ValueError("each posting takes one verdict per call")
        return value


class VerdictItem(Shape):
    job: int
    verdict: VerdictKind = Field(json_schema_extra=_CODE)
    outcome: Literal["saved", "refused"] = Field(json_schema_extra=_CODE)
    #: Why an item was refused: `not_in_run`, `brief_changed`, `posting_changed`,
    #: `already_judged`, `posting_ineligible`, `incomplete`, `too_many_reasons`, `too_long`,
    #: `not_plain_text`, `unknown_brief_item`, `weaker_than_baseline` or `not_for_a_pass`.
    refusal: str | None = Field(default=None, json_schema_extra=_CODE)


class DecideResult(Shape):
    run: str = Field(json_schema_extra=_IDENTIFIER)
    saved: int = Field(ge=0)
    refused: int = Field(ge=0)
    picks: int = Field(ge=0)
    results: list[VerdictItem]


class FinishInput(Shape):
    run: str = Field(min_length=1, max_length=24)
    outcome: Literal["finished", "stopped"] = Field(description="finished, or stopped when you ended early.")
    note: str | None = Field(default=None, max_length=300, description="Why it stopped; a stopped run needs one.")
    tokens: int | None = Field(default=None, ge=0, le=10**12, description="Tokens the run used, as you count them.")


class RunSummary(Shape):
    run: str = Field(json_schema_extra=_IDENTIFIER)
    trial: bool
    outcome: Outcome = Field(json_schema_extra=_CODE)
    started_at: datetime
    finished_at: datetime
    judged: int
    picks: int
    near_misses: int
    note: str | None = Field(default=None, json_schema_extra=_CONTENT)


class ListInput(Shape):
    view: View = Field(
        default="picks",
        description="picks, near_misses, passed, or removed (picks the person marked Not for me, with why).",
    )
    days: int = Field(default=7, ge=1, le=90, description="How far back near misses and passes go.")
    limit: int = Field(default=MAX_BATCH, ge=1, le=200)


class PickList(Shape):
    view: View = Field(json_schema_extra=_CODE)
    count: int = Field(ge=0)
    picks: list[PickRow]


class SwitchInput(Shape):
    state: Literal["on", "off"] | None = Field(
        default=None, description="on or off; left out, the mode stays as it is.",
    )
    routine_host: Literal["claude-code", "codex"] | None = Field(
        default=None, description="The assistant that runs the routine.",
    )
    schedule: str | None = Field(
        default=None, min_length=1, max_length=120, description="When it runs, in words, such as 'daily 09:30 and 17:30'.",
    )
    daily_cap: int | None = Field(
        default=None, ge=1, le=DAILY_CAP_MAX,
        description="The most roles read in a day, when the person asks to change it; the rest wait for the next day.",
    )


class ModeState(Shape):
    state: Literal["never_set_up", "on", "off"] = Field(json_schema_extra=_CODE)
    enabled_at: datetime | None
    routine_host: str | None = Field(json_schema_extra=_CODE)
    schedule: str | None = Field(json_schema_extra=_CONTENT)
    daily_cap: int


# --- descriptors -------------------------------------------------------------- #

PICKS_STATUS = OperationDescriptor(
    id="picks.status",
    summary=(
        "Where top picks stands: the mode, the next setup step and what setup has saved, what the app "
        "already knows about the person, the routine's health, the budget and the daily volume."
    ),
    input=NoInput,
    result=PicksStatus,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_TIERS,
    data_classes=("candidate", "private_pursuit"),
)

PICKS_SAMPLES = OperationDescriptor(
    id="picks.samples",
    summary="A few postings from the person's own Radar, chosen for contrast, to learn their reactions from.",
    input=SamplesInput,
    result=Samples,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_TIERS,
    data_classes=("public_posting", "market_statistic"),
)

PICKS_BEGIN = OperationDescriptor(
    id="picks.begin",
    summary=(
        "Open a run of the judge: the brief, this month's picks, the person's reactions since the last run, "
        "and the postings to judge, best fit first."
    ),
    input=BeginInput,
    result=RunStart,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_TIERS,
    data_classes=("candidate", "public_posting", "market_statistic", "private_pursuit"),
    examples=({}, {"trial": True, "model": "claude-fable-5-2"}),
)

PICKS_NEXT = OperationDescriptor(
    id="picks.next",
    summary="Read the next batch of an open run.",
    input=NextInput,
    result=Batch,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_TIERS,
    data_classes=("public_posting", "market_statistic"),
)

PICKS_DECIDE = OperationDescriptor(
    id="picks.decide",
    summary=(
        "Record verdicts on a run's postings: pick, near_miss or pass, each reason a plain sentence with its "
        "opening fact marked. A refused verdict leaves the others alone."
    ),
    input=DecideInput,
    result=DecideResult,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
    examples=(
        {"run": "run_8f3k2a91c0de", "brief_version": 4, "verdicts": [
            {"job": 13301, "verdict": "pick", "against_baseline": "better", "reasons": [
                {"opening": "Staff level", "rest": ", one step above your Senior role today.", "brief_item": "p3"},
                {"opening": "240,000 to 310,000 base", "rest": ", above the 210,000 you hold.",
                 "brief_item": "baseline"},
            ]},
            {"job": 13302, "verdict": "pass", "pass_code": "not_better"},
        ]},
    ),
)

PICKS_FINISH = OperationDescriptor(
    id="picks.finish",
    summary="Close a run: finished, or stopped with a line saying why.",
    input=FinishInput,
    result=RunSummary,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
    examples=({"run": "run_8f3k2a91c0de", "outcome": "finished"},),
)

PICKS_LIST = OperationDescriptor(
    id="picks.list",
    summary=(
        "Read the verdicts that stand: picks, near misses, passes, or the picks the person removed with "
        "their reason, each with what the person did about it."
    ),
    input=ListInput,
    result=PickList,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_TIERS,
    data_classes=("candidate", "public_posting", "private_pursuit"),
    examples=({}, {"view": "removed"}, {"view": "near_misses", "days": 14}),
)

PICKS_SWITCH = OperationDescriptor(
    id="picks.switch",
    summary=(
        "Turn top picks on or off, record which assistant runs the routine and when, or change how many roles "
        "are read a day. On needs an active brief."
    ),
    input=SwitchInput,
    result=ModeState,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
    examples=({"state": "on", "routine_host": "claude-code", "schedule": "daily 09:30 and 17:30"}, {"daily_cap": 300}),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (
    PICKS_STATUS, PICKS_SAMPLES, PICKS_BEGIN, PICKS_NEXT, PICKS_DECIDE, PICKS_FINISH, PICKS_LIST, PICKS_SWITCH,
)


# --- postings ------------------------------------------------------------------ #


def _level(job: Job) -> str:
    return "unstated" if (job.level_basis or "generic") in UNPLACED_BASIS_VALUES else job.level_band


def _posting(job: Job, *, rank: int, names: dict[str, str], now: datetime, estimates: bool) -> Posting:
    text = " ".join((job.description_text or "").split())
    stated = None
    if job.disclosed_base_min is not None or job.disclosed_base_max is not None:
        stated = StatedPay(
            base_min=job.disclosed_base_min, base_max=job.disclosed_base_max, currency=job.disclosed_currency,
            basis=job.disclosed_pay_basis, period=job.disclosed_pay_period,
        )
    estimated = None
    if estimates and (job.comp_base_median is not None or job.comp_median is not None):
        estimated = EstimatedPay(
            base_median=job.comp_base_median, total_median=job.comp_median, currency=job.comp_currency,
        )
    listed = min(job.first_posted_at or job.first_seen, job.first_seen)
    return Posting(
        job=job.id, title=job.title, company=names.get(job.company, job.company), places=list(job.locations or []),
        work_mode=job.workplace_type, level=_level(job), stated_pay=stated, estimated_pay=estimated,
        first_seen=job.first_seen.date(),
        signals=PostingSignals(
            reposted=job.lineage_role in ("repost", "duplicate") or (job.repost_count or 0) > 0,
            open_days=max((now - listed).days, 0),
        ),
        fit_rank=rank, text=text[:TEXT_CHARS], text_truncated=len(text) > TEXT_CHARS,
        continue_with=[NextAction(operation="opportunities.get", arguments={"opportunity_id": job.id, "view": "detail"})],
    )


async def _postings(
    session: AsyncSession, jobs: list[Job], *, first_rank: int, now: datetime, estimates: bool,
    ranks: list[int] | None = None,
) -> list[Posting]:
    """`ranks`, when given, is each posting's place in the run's queue; else
    the postings run on from `first_rank`."""
    names = await display_names(session) if jobs else {}
    return [
        _posting(job, rank=ranks[index] if ranks is not None else first_rank + index, names=names, now=now,
                 estimates=estimates)
        for index, job in enumerate(jobs)
    ]


def _row(item: Listed, names: dict[str, str], *, postings: bool = True, pursuits: bool = True) -> PickRow:
    reaction = item.reaction
    return PickRow(
        job=item.job.id,
        title=item.job.title if postings else None,
        company=names.get(item.job.company, item.job.company) if postings else None,
        open=item.job.status == "open",
        verdict=item.verdict.verdict,  # type: ignore[arg-type]
        reasons=[ReasonOut.model_validate(reason) for reason in item.verdict.reasons],
        against_baseline=item.verdict.against_baseline,  # type: ignore[arg-type]
        pass_code=item.verdict.pass_code,  # type: ignore[arg-type]
        note=item.verdict.note, brief_version=item.verdict.brief_version, judged_at=item.verdict.created_at,
        reaction=ReactionOut(
            kind=reaction.kind, at=reaction.at, reason=reaction.reason, reason_text=reaction.reason_text,
        ) if reaction is not None and pursuits else None,
    )


def _month_start(now: datetime) -> datetime:
    local = now.astimezone(local_zone())
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


# --- status -------------------------------------------------------------------- #


async def _suggested_check_times(session: AsyncSession, now: datetime) -> list[str]:
    """The two half hours scans most often finished just before, in local time:
    each scan counts toward the first half hour strictly after it ended."""
    finished = (await session.scalars(
        select(ScrapeRun.finished_at).where(
            ScrapeRun.finished_at.isnot(None), ScrapeRun.finished_at >= now - timedelta(days=_SCAN_DAYS),
        )
    )).all()
    zone = local_zone()
    slots: Counter[str] = Counter()
    for at in finished:
        if at is None:
            continue
        local = at.astimezone(zone)
        after = local.replace(minute=30 if local.minute >= 30 else 0, second=0, microsecond=0) + timedelta(minutes=30)
        slots[f"{after.hour:02d}:{after.minute:02d}"] += 1
    if not slots:
        return list(_DEFAULT_CHECK_TIMES)
    return sorted(slot for slot, _ in sorted(slots.items(), key=lambda pair: (-pair[1], pair[0]))[:2])


async def status(session: AsyncSession, *, pursuits: bool, now: datetime | None = None) -> PicksStatus:
    now = now or datetime.now(UTC)
    settings = await get_top_picks_settings(session)
    active, draft = await briefs.active(session), await briefs.draft(session)
    writing = briefs.body_of(draft or active)
    reading = await background.newest(session)
    newest = await runs.newest_routine_run(session)
    progress = setup_steps.progress((await setup_steps.stored(session, mode_on=settings.state == "on")).facts)
    stands = await mode.standing(session, settings, active, now)
    persona = await get_persona_profile(session) or {}
    floor = await get_pay_floor(session)
    aim = persona.get("intent_statement")
    known = Known(
        scope=KnownScope(
            roles=sorted(await get_enabled_roles(session)),
            levels=sorted(await get_enabled_bands(session)),
            places=sorted(await get_enabled_locations(session)),
        ),
        pay_floor=KnownPay(amount=floor["amount"], currency=floor["currency"]) if floor else None,
        aim=aim if isinstance(aim, str) and aim.strip() else None,
        has_background=reading is not None,
        background_confirmed=reading is not None and reading.confirmed_at is not None,
    )
    if pursuits:
        known.saved = int(await session.scalar(select(func.count()).select_from(Favorite)) or 0)
        known.not_for_me = int(await session.scalar(
            select(func.count()).select_from(JobFeedback).where(JobFeedback.verdict == "dismissed")
        ) or 0)
    volume = await queue.volume(session, writing, now=now)
    month = await verdicts.picks_since(session, _month_start(now))
    unseen = None
    if pursuits:
        unseen = await verdicts.unseen_pick(
            session, body=briefs.body_of(active), last_opened_at=settings.last_opened_at,
        )
    return PicksStatus(
        state=settings.state,  # type: ignore[arg-type]
        setup=SetupProgress(
            next_step=progress.next_step,
            steps=[SetupStep(id=step.id, done=step.done) for step in progress.steps],
            saved_parts=list(progress.saved_parts), deferred=list(progress.deferred),
        ),
        known=known,
        brief=BriefState(
            active_version=active.version if active is not None else None,
            draft_version=draft.version if draft is not None else None,
            calibrated=bool(writing.calibrated),
        ),
        routine=Routine(
            host=settings.routine_host, schedule=settings.schedule, health=stands.health,
            last_run=_last_run(newest, now) if newest is not None else None,
            waiting=stands.waiting, oldest_waiting_since=stands.oldest_waiting_since,
        ),
        budget=StatusBudget(
            per_month=briefs.body_of(active).budget or DEFAULT_BUDGET, picks_this_month=len(month),
            draft_per_month=(briefs.body_of(draft).budget or DEFAULT_BUDGET) if draft is not None else None,
        ),
        unseen_pick=unseen,
        volume=VolumeView(
            expected_per_day=volume.expected_per_day, busiest_day=volume.busiest_day,
            daily_cap=settings.daily_cap,
            by_rule=[RuleShareView(rule=share.rule, removes_share=share.removes_share) for share in volume.by_rule],
        ),
        suggested_check_times=await _suggested_check_times(session, now),
    )


def _last_run(run: PickRun, now: datetime) -> LastRun:
    return LastRun(
        run=run.id, host=run.host,
        outcome=runs.as_fact(run, now).outcome,  # type: ignore[arg-type]
        started_at=run.started_at, finished_at=run.finished_at,
        judged=int(run.counts.get("judged", 0)), picks=int(run.counts.get("picks", 0)), note=run.note,
    )


# --- samples -------------------------------------------------------------------- #


async def samples(
    session: AsyncSession, params: SamplesInput, *, withheld: Collection[DataClass], now: datetime | None = None,
) -> Samples:
    """Postings spread evenly across the Board's open roles in fit order, the
    best first and the weakest last, one per company where that is possible:
    reactions to roles that differ teach more than reactions to the best few."""
    now = now or datetime.now(UTC)
    pool = await queue.best_first(
        session, apply_job_filters(select(Job), await queue.board_filters(session)), BriefBody(), limit=_SAMPLE_POOL,
    )
    wanted = min(params.limit, len(pool))
    chosen: list[Job] = []
    if wanted:
        step = (len(pool) - 1) / (wanted - 1) if wanted > 1 else 0.0
        companies: set[str] = set()
        for index in range(wanted):
            at = round(index * step)
            # The nearest role of a company not yet shown, else the role at this place.
            near = sorted(range(len(pool)), key=lambda other: abs(other - at))
            pick = next(
                (pool[other] for other in near if pool[other] not in chosen and pool[other].company not in companies),
                next(pool[other] for other in near if pool[other] not in chosen),
            )
            chosen.append(pick)
            companies.add(pick.company)
        chosen.sort(key=pool.index)
    postings = await _postings(
        session, chosen, first_rank=1, now=now, estimates="market_statistic" not in withheld,
    )
    return Samples(count=len(postings), samples=postings)


# --- a run ---------------------------------------------------------------------- #


def _brief_packet(row: Any, body: BriefBody) -> dict[str, Any]:
    """The brief as the judge reads it. Checkable rules are left out: the
    engine applied them, and no posting in the run breaks one."""
    stored = body.model_dump(mode="json", exclude_none=True)
    packet: dict[str, Any] = {"version": row.version, "summary": row.summary}
    for part in ("urgency", "baseline", "pulls", "tradeoffs", "targets", "direction", "examples", "gaps"):
        if part in stored:
            packet[part] = stored[part]
    packet["rules"] = [{"id": rule.id, "text": rule.text, "judged": True} for rule in judged_rules(body)]
    packet["rules_applied_by_engine"] = [str(rule.id) for rule in checkable_rules(body)]
    return packet


def _mode_refusal(code: str) -> OperationError:
    if code == "brief_required":
        return OperationError(
            "brief_required",
            "Top picks needs an active brief first. Finish setup: picks.status names the next step.",
            next_actions=[NextAction(operation=PICKS_STATUS.id)],
        )
    return OperationError(
        "mode_off",
        "Top picks is off, so no run begins. The person turns it on; a trial during setup still runs.",
        details={"setting": "top_picks.state"},
        next_actions=[NextAction(operation=PICKS_STATUS.id)],
    )


def _run_refusal(error: RunError) -> OperationError:
    return OperationError(
        "not_found" if error.code == "unknown_run" else "invalid_input", error.message,
        details={"field": "run", "reason": error.code},
        next_actions=[NextAction(operation=PICKS_BEGIN.id)],
    )


async def begin(
    session: AsyncSession, params: BeginInput, *, host: str | None, withheld: Collection[DataClass],
    now: datetime | None = None,
) -> RunStart:
    """Open a run and answer its first batch. Commits nothing: the caller's
    write commits the run, the receipt and the Activity entry together."""
    if "public_posting" in withheld:
        raise category_disabled("public_posting")
    await lock_picks(session)
    now = now or datetime.now(UTC)
    settings = await get_top_picks_settings(session)
    active = await briefs.active(session)
    if active is None:
        raise _mode_refusal("brief_required")
    if not params.trial and settings.state != "on":
        raise _mode_refusal("mode_off")
    await runs.close_abandoned(session, now, host=host)
    body = briefs.body_of(active)
    stmt = queue.candidates(
        await queue.board_filters(session), trial=params.trial,
        active_version=active.version, now=now,
    )
    counted = await queue.counts(session, stmt, body)
    room = queue.TRIAL_CAP if params.trial else max(settings.daily_cap - await runs.handed_today(session, now), 0)
    jobs = await queue.best_first(session, stmt, body, limit=room)
    counts = RunCounts(
        waiting=counted.waiting, ruled_out_by_rules=counted.ruled_out_by_rules, handed=len(jobs),
        held_back=max(counted.waiting - len(jobs), 0),
    )
    last = await runs.last_finished(session)
    run = await runs.begin(
        session, host=host, model=params.model, trial=params.trial, brief_version=active.version,
        queue=[(job.id, job.content_hash or "") for job in jobs], counts=counts.model_dump(), now=now,
    )
    names = await display_names(session)
    month = await verdicts.picks_since(session, _month_start(now))
    reacted = await verdicts.reacted_since(session, last.started_at if last is not None else None)
    first = jobs[: params.limit]
    more = len(jobs) > len(first)
    return RunStart(
        run=run.id, trial=run.trial, brief=_brief_packet(active, body),
        budget=RunBudget(
            per_month=body.budget or DEFAULT_BUDGET, picks_this_month=len(month),
            picks=[_row(item, names) for item in month],
        ),
        reactions=[_row(item, names) for item in reacted],
        counts=counts, count=len(first),
        batch=await _postings(session, first, first_rank=1, now=now, estimates=True),
        next_cursor=len(first) if more else None,
        continue_with=[NextAction(
            operation=PICKS_NEXT.id, arguments={"run": run.id, "cursor": len(first)},
        )] if more else [],
    )


def shown_begin(result: RunStart, withheld: Collection[DataClass]) -> RunStart:
    """A run's first answer under the caller's categories: the stored receipt
    keeps it whole, and an answer leaves out what the person does not share."""
    if "public_posting" in withheld:
        # The first batch is postings: a replay after posting sharing was
        # turned off answers nothing of them.
        raise category_disabled("public_posting")
    shown = result.model_copy(deep=True)
    if "private_pursuit" in withheld:
        shown.reactions = None
        for row in shown.budget.picks:
            row.reaction = None
    if "market_statistic" in withheld:
        for posting in shown.batch:
            posting.estimated_pay = None
    return shown


async def _read_open_run(session: AsyncSession, run_id: str, now: datetime | None = None) -> PickRun:
    try:
        return await runs.open_run(session, run_id, now, for_write=False)
    except RunError as error:
        raise _run_refusal(error) from None


async def _eligible_run_postings(
    session: AsyncSession, run: PickRun, ids: list[int], now: datetime,
) -> dict[int, Job]:
    if not ids:
        return {}
    body = briefs.body_of(await briefs.version(session, run.brief_version))
    stmt = await queue.eligible_in_run(session, run, ids, body=body, now=now)
    handed = runs.queue_of(run)
    return {
        job.id: job for job in (await session.scalars(stmt)).all()
        if (job.content_hash or "") == handed.get(job.id)
    }


async def replayed_begin(session: AsyncSession, result: RunStart, withheld: Collection[DataClass]) -> RunStart:
    """Reading the first batch again requires a run that can still serve it."""
    if "public_posting" in withheld:
        raise category_disabled("public_posting")
    run = await _read_open_run(session, result.run)
    eligible = await _eligible_run_postings(session, run, [posting.job for posting in result.batch], datetime.now(UTC))
    batch = [posting for posting in result.batch if posting.job in eligible]
    return result.model_copy(update={"batch": batch, "count": len(batch)})


async def next_batch(
    session: AsyncSession, params: NextInput, *, withheld: Collection[DataClass], now: datetime | None = None,
) -> Batch:
    run = await _read_open_run(session, params.run, now)
    now = now or datetime.now(UTC)
    ids = [int(job_id) for job_id, _ in run.queue]
    window = ids[params.cursor : params.cursor + params.limit]
    found = await _eligible_run_postings(session, run, window, now)
    kept = [
        (params.cursor + offset + 1, found[job_id]) for offset, job_id in enumerate(window) if job_id in found
    ]
    end = params.cursor + len(window)
    more = end < len(ids)
    postings = await _postings(
        session, [job for _, job in kept], first_rank=params.cursor + 1, now=now,
        estimates="market_statistic" not in withheld, ranks=[rank for rank, _ in kept],
    )
    return Batch(
        run=run.id, count=len(postings), batch=postings, next_cursor=end if more else None,
        continue_with=[NextAction(operation=PICKS_NEXT.id, arguments={"run": run.id, "cursor": end})] if more else [],
    )


# --- verdicts ------------------------------------------------------------------- #


async def decide(session: AsyncSession, params: DecideInput, *, now: datetime | None = None) -> DecideResult:
    """Record each verdict the engine accepts. Commits nothing: the caller's
    write commits the verdicts, the receipt and the Activity entry together."""
    # The clock is read once the lock is held: a run that passed the bound
    # while this waited is closed, and takes no verdict.
    await lock_picks(session)
    now = now or datetime.now(UTC)
    try:
        run = await runs.open_run(session, params.run, now)
    except RunError as error:
        raise _run_refusal(error) from None
    if params.brief_version != run.brief_version:
        raise OperationError(
            "invalid_input",
            f"This run judges against version {run.brief_version} of the brief, as picks.begin answered it.",
            details={"field": "brief_version", "run_brief_version": run.brief_version},
        )
    active = await briefs.active(session)
    body = briefs.body_of(await briefs.version(session, run.brief_version))
    saved = await verdicts.save(
        session, run,
        [
            VerdictIn(
                job=item.job, verdict=item.verdict,
                reasons=tuple(ReasonIn(reason.rest, reason.brief_item, reason.opening) for reason in item.reasons),
                against_baseline=item.against_baseline, pass_code=item.pass_code, note=item.note,
            )
            for item in params.verdicts
        ],
        body=body, active_version=active.version if active is not None else -1, now=now,
    )
    return DecideResult(
        run=run.id,
        saved=sum(item.saved for item in saved),
        refused=sum(not item.saved for item in saved),
        picks=sum(item.saved and item.verdict == "pick" for item in saved),
        results=[
            VerdictItem(
                job=item.job, verdict=item.verdict, outcome="saved" if item.saved else "refused",
                refusal=item.refusal,
            )
            for item in saved
        ],
    )


async def finish(session: AsyncSession, params: FinishInput, *, now: datetime | None = None) -> RunSummary:
    note = " ".join(params.note.split()) if params.note else None
    if params.outcome == "stopped" and not note:
        raise OperationError(
            "invalid_input", "A stopped run says why, in note.", details={"field": "note"},
        )
    # As in `decide`: the clock is read once the lock is held.
    await lock_picks(session)
    now = now or datetime.now(UTC)
    try:
        run = await runs.finish(session, params.run, outcome=params.outcome, note=note, tokens=params.tokens, now=now)
    except RunError as error:
        raise _run_refusal(error) from None
    return RunSummary(
        run=run.id, trial=run.trial,
        outcome=params.outcome, started_at=run.started_at, finished_at=now,
        judged=int(run.counts.get("judged", 0)), picks=int(run.counts.get("picks", 0)),
        near_misses=int(run.counts.get("near_misses", 0)), note=run.note,
    )


async def listed(
    session: AsyncSession, params: ListInput, *, withheld: Collection[DataClass], now: datetime | None = None,
) -> PickList:
    """One view of the verdicts that stand. Without the person's pursuits
    shared, no row says what they did, the removed view is refused, and the
    picks view keeps the picks they removed, since leaving one out would say so."""
    now = now or datetime.now(UTC)
    pursuits = "private_pursuit" not in withheld
    if params.view == "removed" and not pursuits:
        raise category_disabled("private_pursuit", field="view")
    active = await briefs.active(session)
    rows = await verdicts.listed(
        session, params.view, body=briefs.body_of(active), since=now - timedelta(days=params.days),
        limit=params.limit, keep_removed=not pursuits,
    )
    names = await display_names(session) if rows else {}
    return PickList(
        view=params.view, count=len(rows),
        picks=[_row(item, names, postings="public_posting" not in withheld, pursuits=pursuits) for item in rows],
    )


# --- the mode ------------------------------------------------------------------- #


def _mode(settings: TopPicksSettings) -> ModeState:
    return ModeState(
        state=settings.state,  # type: ignore[arg-type]
        enabled_at=settings.enabled_at, routine_host=settings.routine_host, schedule=settings.schedule,
        daily_cap=settings.daily_cap,
    )


async def switch(session: AsyncSession, params: SwitchInput, *, now: datetime | None = None) -> ModeState:
    """Turn the mode on or off, or change its settings. Turning it off pauses
    the checks and deletes nothing; what arrived meanwhile is read once it is on again."""
    changes: dict[str, Any] = {}
    if params.routine_host is not None:
        changes["routine_host"] = params.routine_host
    if params.schedule is not None:
        changes["schedule"] = " ".join(params.schedule.split())
    if params.daily_cap is not None:
        changes["daily_cap"] = params.daily_cap
    try:
        return _mode(await mode.change(session, state=params.state, now=now, **changes))
    except mode.BriefRequired:
        raise _mode_refusal("brief_required") from None


# --- activity -------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunActivity:
    """What opening, judging and closing a run list on the Activity screen."""

    async def before(self, session: AsyncSession) -> None:
        return None

    def entry(self, before: object, result: BaseModel) -> Changed:
        if isinstance(result, RunStart):
            english = (
                f"Began a trial on {result.counts.handed} role{_s(result.counts.handed)}" if result.trial
                else f"Began choosing top picks from {result.counts.handed} role{_s(result.counts.handed)}"
            )
            return Changed(Said("picks.began", english, {
                "run": result.run, "trial": result.trial, "handed": result.counts.handed,
                "ruled_out": result.counts.ruled_out_by_rules,
            }))
        if isinstance(result, DecideResult):
            english = f"Judged {result.saved} role{_s(result.saved)}: {result.picks} top pick{_s(result.picks)}"
            return Changed(Said("picks.decided", english, {
                "run": result.run, "saved": result.saved, "picks": result.picks, "refused": result.refused,
            }))
        if isinstance(result, RunSummary):
            english = (
                f"Finished choosing top picks: {result.judged} judged, {result.picks} picked"
                if result.outcome == "finished" else "Stopped choosing top picks early"
            )
            return Changed(Said("picks.finished", english, {
                "run": result.run, "outcome": result.outcome, "trial": result.trial, "judged": result.judged,
                "picks": result.picks,
            }))
        raise TypeError(f"a run write does not answer {type(result).__name__}")


@dataclass(frozen=True)
class SwitchActivity:
    """What a switch lists: the mode turned on or off with its state before
    and after, or the settings changed when the mode stayed as it was."""

    async def before(self, session: AsyncSession) -> str:
        # Under the lock `mode.change` takes, so the state read here is the one
        # the write sees, not one a concurrent switch replaces in between.
        await lock_picks(session)
        return (await get_top_picks_settings(session)).state

    def entry(self, before: object, result: BaseModel) -> Changed:
        if not isinstance(result, ModeState):
            raise TypeError(f"a switch answers ModeState, not {type(result).__name__}")
        if before == result.state:
            # The daily limit, the host or the schedule changed; the mode did not.
            english = "Changed the top picks settings"
        else:
            english = "Turned top picks on" if result.state == "on" else "Turned top picks off"
        changes = (FieldChange("state", before, result.state),) if before != result.state else ()
        return Changed(Said("picks.switched", english, {"state": result.state, "host": result.routine_host}), changes)


def _s(count: int) -> str:
    return "" if count == 1 else "s"

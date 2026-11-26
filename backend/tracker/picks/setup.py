"""Where setup stands, derived from what is stored.

Setup is a conversation in the person's assistant, in the stages of `STEPS`.
No pointer records which stage it reached: each stage is done when the fact it
ends with exists (a confirmed reading, a part of the brief, an active brief, a
finished trial, a finished run), so the answer cannot disagree with the data,
and any assistant can resume where another stopped.

`calibration` and `trial` need postings. While the Board has none open they
are deferred: setup goes on past them and they stay named in `deferred`.

`stored` reads the facts for `progress`; `picks.status` and the dashboard's
`GET /api/picks/state` both read setup through it, so the two cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import CandidateDocument, Job, PickBrief
from tracker.db.queries.jobs import apply_job_filters
from tracker.picks import background, queue, runs
from tracker.picks import brief as briefs
from tracker.picks.brief import BriefBody

Step = Literal[
    "connect", "background", "situation", "bar", "rules", "tradeoffs", "targets", "calibration", "budget",
    "confirm", "trial", "routine", "done",
]
STEPS: tuple[Step, ...] = (
    "connect", "background", "situation", "bar", "rules", "tradeoffs", "targets", "calibration", "budget",
    "confirm", "trial", "routine", "done",
)
#: The steps that end with a part of the brief saved, and the parts each needs.
BRIEF_STEPS: dict[Step, tuple[str, ...]] = {
    "situation": ("urgency", "baseline"),
    "bar": ("pulls",),
    "rules": ("rules",),
    "tradeoffs": ("tradeoffs",),
    "targets": ("targets",),
    "calibration": ("examples",),
    "budget": ("budget",),
}
_NEEDS_POSTINGS: frozenset[Step] = frozenset({"calibration", "trial"})


@dataclass(frozen=True)
class Facts:
    """The stored facts setup is read from."""

    #: The newest reading is confirmed by the person.
    background_confirmed: bool
    #: The brief setup is writing: the draft when there is one, else the active brief.
    body: BriefBody
    has_active_brief: bool
    trial_finished: bool
    #: The mode is on and a run of the routine has finished.
    routine_ran: bool
    #: The Board has open roles to show the person and to try the judge on.
    has_postings: bool


@dataclass(frozen=True)
class StepState:
    id: Step
    done: bool


@dataclass(frozen=True)
class Progress:
    next_step: Step
    steps: tuple[StepState, ...]
    #: The parts of the brief that are saved, in the brief's own order.
    saved_parts: tuple[str, ...]
    deferred: tuple[Step, ...]


@dataclass(frozen=True)
class Stored:
    """What setup has stored, read once."""

    facts: Facts
    #: The conversation saved something: a document, a reading of the
    #: background or a brief. False until then, and again after Remove.
    started: bool


async def stored(session: AsyncSession, *, mode_on: bool) -> Stored:
    """Read the facts setup is derived from. `mode_on`: the mode's state is on."""
    # One statement, so a confirm that turns the draft into the active brief
    # between two reads cannot hide both.
    held = {
        brief.status: brief
        for brief in await session.scalars(select(PickBrief).where(PickBrief.status.in_(("active", "draft"))))
    }
    active, draft = held.get("active"), held.get("draft")
    reading = await background.newest(session)
    open_role = await session.scalar(apply_job_filters(select(Job.id), await queue.board_filters(session)).limit(1))
    finished = await runs.last_finished(session)
    document = await session.scalar(select(CandidateDocument.id).where(CandidateDocument.removed_at.is_(None)).limit(1))
    facts = Facts(
        background_confirmed=reading is not None and reading.confirmed_at is not None,
        body=briefs.body_of(draft or active),
        has_active_brief=active is not None,
        trial_finished=await runs.last_finished(session, trial=True) is not None,
        routine_ran=mode_on and finished is not None,
        has_postings=open_role is not None,
    )
    started = document is not None or reading is not None or draft is not None or active is not None
    return Stored(facts=facts, started=started)


def saved_parts(body: BriefBody) -> tuple[str, ...]:
    """The parts of `body` that were saved. A list saved empty counts: the
    person was asked and has none."""
    return tuple(part for part in BriefBody.model_fields if getattr(body, part) is not None)


def progress(facts: Facts) -> Progress:
    saved = saved_parts(facts.body)

    def done(step: Step) -> bool:
        if step == "connect":
            return True
        if step == "background":
            return facts.background_confirmed
        if step in BRIEF_STEPS:
            if step == "calibration":
                return bool(facts.body.examples)
            return all(part in saved for part in BRIEF_STEPS[step])
        if step == "confirm":
            return facts.has_active_brief
        if step == "trial":
            return facts.trial_finished
        if step == "routine":
            return facts.routine_ran
        return False

    states = [StepState(step, done(step)) for step in STEPS[:-1]]
    deferred = tuple(
        state.id for state in states if not state.done and state.id in _NEEDS_POSTINGS and not facts.has_postings
    )
    next_step: Step = next((state.id for state in states if not state.done and state.id not in deferred), "done")
    states.append(StepState("done", next_step == "done"))
    return Progress(next_step=next_step, steps=tuple(states), saved_parts=saved, deferred=deferred)

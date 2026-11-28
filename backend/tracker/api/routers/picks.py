"""Top picks, as the dashboard reads it."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents import receipts
from tracker.api.deps import SessionDep
from tracker.api.errors import ErrorCode, api_error
from tracker.api.schemas.picks import (
    LastCheck,
    NearMiss,
    PassedOverResponse,
    PassGroup,
    PickReason,
    PicksModeInput,
    PicksRemovedResponse,
    PicksSetup,
    PicksSetupStep,
    PicksStateResponse,
    RuleCount,
)
from tracker.notifications import reconcile_picks_stalled
from tracker.picks import brief as briefs
from tracker.picks import mode, queue, runs, setup, verdicts
from tracker.platform import agent_hosts
from tracker.settings_store import DAILY_CAP_MAX, get_top_picks_settings

router = APIRouter(tags=["picks"])

#: The assistant writes whose answers carry the person's background or brief:
#: Remove deletes their receipts with what they saved.
PERSONAL_WRITES = frozenset({
    "background.set", "background.add_document", "brief.patch", "picks.begin", "picks.finish",
})


@router.get("/api/picks/passed", response_model=PassedOverResponse)
async def passed_over(session: SessionDep) -> PassedOverResponse:
    """What the assistant read in the last seven days and did not pick: the
    near misses with the one thing that failed, the passes by why, and what
    the hard rules ruled out before any reading."""
    since = datetime.now(UTC) - timedelta(days=7)
    body = briefs.body_of(await briefs.active(session))
    week = await verdicts.tally_since(session, since)
    near = await verdicts.listed(session, "near_misses", body=body, since=since)
    by_code = await verdicts.passes_by_code(session, since)
    out = await queue.ruled_out_since(session, body, since)
    return PassedOverResponse(
        passed_this_week=week.passed_over,
        near_misses=[
            NearMiss(
                job_id=item.job.id, judged_at=item.verdict.created_at,
                reason=PickReason(opening=item.verdict.reasons[0].get("opening"), rest=item.verdict.reasons[0]["rest"]),
            )
            for item in near
            if item.verdict.reasons and not (item.reaction is not None and item.reaction.kind == "not_for_me")
        ],
        passes=[
            PassGroup(code=code, count=count)  # type: ignore[arg-type]
            for code, count in sorted(by_code.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
        judged_rules=[rule.text for rule in briefs.judged_rules(body)],
        ruled_out=out.total,
        ruled_out_by_rule=[RuleCount(rule=rule.text, count=count) for rule, count in out.by_rule if count],
    )


async def _state(session: AsyncSession) -> PicksStateResponse:
    now = datetime.now(UTC)
    settings = await get_top_picks_settings(session)
    active = await briefs.active(session)
    stands = await mode.standing(session, settings, active, now)
    newest = await runs.newest_closed_routine_run(session)
    week = await verdicts.tally_since(session, now - timedelta(days=7))
    host = settings.routine_host
    # The host's own files are read off the event loop, as the Assistant apps card reads them.
    connection = (
        await asyncio.to_thread(agent_hosts.connection, host) if host in agent_hosts.HOSTS else None
    )
    stored = await setup.stored(session, mode_on=settings.state == "on")
    progress = setup.progress(stored.facts)
    return PicksStateResponse(
        state=settings.state,  # type: ignore[arg-type]
        routine_host=host, schedule=settings.schedule,
        last_check=LastCheck(
            host=newest.host, finished_at=newest.finished_at,
            outcome=newest.outcome,  # type: ignore[arg-type]
            note=newest.note if newest.outcome != "finished" else None,
        ) if newest is not None and newest.finished_at is not None else None,
        brief_summary=(active.summary or None) if active is not None else None,
        unseen_pick=await verdicts.unseen_pick(
            session, body=briefs.body_of(active), last_opened_at=settings.last_opened_at,
        ),
        health=stands.health, waiting=stands.waiting,
        read_this_week=week.read, passed_this_week=week.passed_over,
        routine_host_connection=connection,
        daily_limit=settings.daily_cap, daily_limit_max=DAILY_CAP_MAX,
        setup=PicksSetup(
            started=stored.started, next_step=progress.next_step,
            steps=[PicksSetupStep(id=step.id, done=step.done) for step in progress.steps],
            deferred=list(progress.deferred),
        ),
    )


@router.get("/api/picks/state", response_model=PicksStateResponse)
async def picks_state(session: SessionDep) -> PicksStateResponse:
    return await _state(session)


@router.put("/api/picks/mode", response_model=PicksStateResponse)
async def set_picks_mode(payload: PicksModeInput, session: SessionDep) -> PicksStateResponse:
    """Pause or resume the checks, or change how many roles are read a day.
    Off keeps everything saved; on needs the brief setup ends with, so a mode
    never set up cannot be switched on here."""
    if payload.state is None and payload.daily_limit is None:
        raise api_error(422, ErrorCode.INVALID_INPUT, "name the state, the daily limit, or both")
    changes = {"daily_cap": payload.daily_limit} if payload.daily_limit is not None else {}
    try:
        await mode.change(session, state=payload.state, now=None, **changes)
    except mode.BriefRequired:
        raise api_error(409, ErrorCode.INVALID_INPUT, "top picks is not set up") from None
    # Paused, the checks are not expected: a stall's row goes with the switch.
    await reconcile_picks_stalled(session)
    await session.commit()
    return await _state(session)


@router.post("/api/picks/opened", response_model=PicksStateResponse)
async def picks_opened(session: SessionDep) -> PicksStateResponse:
    """The person opened Top picks: no pick made before now is unseen."""
    await mode.mark_opened(session, datetime.now(UTC))
    await session.commit()
    return await _state(session)


@router.delete("/api/picks/setup", response_model=PicksRemovedResponse)
async def remove_picks_setup(session: SessionDep) -> PicksRemovedResponse:
    """Delete the stored CV, every reading of it and the brief, clear what past
    verdicts say and the receipts that repeat any of it, and return the mode to never set up. Saved roles, Not for me
    marks and the Board stay."""
    removed = await mode.remove(session, datetime.now(UTC))
    await reconcile_picks_stalled(session)
    # The receipts of the writes that saved these hold them too.
    await receipts.forget(session, PERSONAL_WRITES)
    await session.commit()
    return PicksRemovedResponse(
        briefs=removed.briefs, readings=removed.readings, documents=removed.documents, verdicts=removed.verdicts,
    )

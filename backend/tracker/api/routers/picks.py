"""Top picks, as the dashboard reads it."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.api.deps import SessionDep
from tracker.api.errors import ErrorCode, api_error
from tracker.api.schemas.picks import (
    LastCheck,
    PickReason,
    PicksModeInput,
    PicksRemovedResponse,
    PicksStateResponse,
    RemovedPick,
    RemovedPicksResponse,
)
from tracker.db.queries.companies import display_names
from tracker.picks import brief as briefs
from tracker.picks import mode, runs, verdicts
from tracker.picks.brief import BriefBody
from tracker.settings_store import DAILY_CAP_MAX, get_top_picks_settings

router = APIRouter(tags=["picks"])


@router.get("/api/picks/removed", response_model=RemovedPicksResponse)
async def removed_picks(session: SessionDep) -> RemovedPicksResponse:
    """The picks the person marked Not for me, each with the reason they gave.

    Removing a pick is the Board's own dismissal, so the role left Top picks
    and the Radar together, and clearing that dismissal
    (`DELETE /api/jobs/{job_id}/feedback`) puts it back in both."""
    rows = await verdicts.listed(session, "removed", body=BriefBody())
    names = await display_names(session) if rows else {}
    return RemovedPicksResponse(picks=[
        RemovedPick(
            job_id=item.job.id, title=item.job.title, company=names.get(item.job.company, item.job.company),
            company_slug=item.job.company, is_open=item.job.status == "open",
            reasons=[PickReason(opening=reason.get("opening"), rest=reason["rest"]) for reason in item.verdict.reasons],
            reason=item.reaction.reason, reason_text=item.reaction.reason_text, removed_at=item.reaction.at,
            judged_at=item.verdict.created_at,
        )
        for item in rows if item.reaction is not None
    ])


async def _state(session: AsyncSession) -> PicksStateResponse:
    settings = await get_top_picks_settings(session)
    active = await briefs.active(session)
    newest = await runs.newest_closed_routine_run(session)
    return PicksStateResponse(
        state=settings.state,  # type: ignore[arg-type]
        routine_host=settings.routine_host, schedule=settings.schedule,
        last_check=LastCheck(
            host=newest.host, finished_at=newest.finished_at,
            outcome=newest.outcome,  # type: ignore[arg-type]
        ) if newest is not None and newest.finished_at is not None else None,
        brief_summary=(active.summary or None) if active is not None else None,
        unseen_pick=await verdicts.unseen_pick(
            session, body=briefs.body_of(active), last_opened_at=settings.last_opened_at,
        ),
        daily_limit=settings.daily_cap, daily_limit_max=DAILY_CAP_MAX,
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
        await mode.change(session, state=payload.state, now=datetime.now(UTC), **changes)
    except mode.BriefRequired:
        raise api_error(409, ErrorCode.INVALID_INPUT, "top picks is not set up") from None
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
    verdicts say, and return the mode to never set up. Saved roles, Not for me
    marks and the Board stay."""
    removed = await mode.remove(session, datetime.now(UTC))
    await session.commit()
    return PicksRemovedResponse(
        briefs=removed.briefs, readings=removed.readings, documents=removed.documents, verdicts=removed.verdicts,
    )

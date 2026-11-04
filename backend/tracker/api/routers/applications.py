"""The application pipeline: the board, one application, its activity, and the
comment and interview writes on it.

Writes go through `agents/pursuits.py`, the same store the MCP tools use; the
reads are `agents/applications.py`. Stage moves stay on `PUT /api/jobs/{job_id}/pursuit`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from tracker.agents import applications as reads
from tracker.agents.pursuits import (
    CommentNotEditable,
    CommentWrite,
    InterviewUpdate,
    InterviewWrite,
    add_comment,
    add_interview,
    delete_comment,
    delete_interview,
    edit_comment,
    public_comment,
    public_interview,
    update_interview,
)
from tracker.api.deps import SessionDep
from tracker.api.errors import ErrorCode, api_error
from tracker.api.schemas.applications import (
    ApplicationActivityResponse,
    ApplicationBoardResponse,
    ApplicationCommentResponse,
    ApplicationDeleted,
    ApplicationDetailResponse,
    ApplicationInterviewResponse,
)

router = APIRouter()


@router.get("/api/applications", response_model=ApplicationBoardResponse)
async def board_ep(session: SessionDep) -> dict:
    return {"applications": await reads.board(session, now=datetime.now(UTC))}


@router.get("/api/applications/{job_id}", response_model=ApplicationDetailResponse)
async def application_ep(job_id: int, session: SessionDep) -> dict:
    found = await reads.application(session, job_id, now=datetime.now(UTC))
    if found is None:
        raise api_error(404, ErrorCode.APPLICATION_NOT_FOUND, "role is not on the board")
    return found


@router.get("/api/applications/{job_id}/activity", response_model=ApplicationActivityResponse)
async def activity_ep(
    job_id: int,
    session: SessionDep,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=reads.ACTIVITY_LIMIT_MAX)] = 100,
) -> dict:
    items = await reads.activity(session, job_id, before=before, limit=limit)
    if items is None:
        raise api_error(404, ErrorCode.APPLICATION_NOT_FOUND, "role is not on the board")
    return {"items": items}


# --- comments ------------------------------------------------------------------


@router.post("/api/jobs/{job_id}/pursuit/comments", response_model=ApplicationCommentResponse)
async def add_comment_ep(job_id: int, payload: CommentWrite, session: SessionDep) -> dict:
    try:
        comment = await add_comment(session, job_id, payload, actor="user")
    except LookupError as err:
        raise api_error(404, ErrorCode.JOB_NOT_FOUND, str(err)) from err
    await session.commit()
    return {"comment": public_comment(comment)}


@router.put(
    "/api/jobs/{job_id}/pursuit/comments/{comment_id}", response_model=ApplicationCommentResponse
)
async def edit_comment_ep(
    job_id: int, comment_id: int, payload: CommentWrite, session: SessionDep
) -> dict:
    try:
        comment = await edit_comment(session, job_id, comment_id, payload)
    except LookupError as err:
        raise api_error(404, ErrorCode.COMMENT_NOT_FOUND, str(err)) from err
    except CommentNotEditable as err:
        raise api_error(403, ErrorCode.COMMENT_NOT_YOURS, str(err)) from err
    await session.commit()
    return {"comment": public_comment(comment)}


@router.delete(
    "/api/jobs/{job_id}/pursuit/comments/{comment_id}", response_model=ApplicationDeleted
)
async def delete_comment_ep(job_id: int, comment_id: int, session: SessionDep) -> dict:
    try:
        await delete_comment(session, job_id, comment_id)
    except LookupError as err:
        raise api_error(404, ErrorCode.COMMENT_NOT_FOUND, str(err)) from err
    except CommentNotEditable as err:
        raise api_error(403, ErrorCode.COMMENT_NOT_YOURS, str(err)) from err
    await session.commit()
    return {"id": comment_id, "deleted": True}


# --- interviews ----------------------------------------------------------------


@router.post("/api/jobs/{job_id}/pursuit/interviews", response_model=ApplicationInterviewResponse)
async def add_interview_ep(job_id: int, payload: InterviewWrite, session: SessionDep) -> dict:
    try:
        interview = await add_interview(session, job_id, payload, actor="user")
    except LookupError as err:
        raise api_error(404, ErrorCode.JOB_NOT_FOUND, str(err)) from err
    await session.commit()
    return {"interview": public_interview(interview)}


@router.patch(
    "/api/jobs/{job_id}/pursuit/interviews/{interview_id}",
    response_model=ApplicationInterviewResponse,
)
async def update_interview_ep(
    job_id: int, interview_id: int, payload: InterviewUpdate, session: SessionDep
) -> dict:
    try:
        interview = await update_interview(session, job_id, interview_id, payload)
    except LookupError as err:
        raise api_error(404, ErrorCode.INTERVIEW_NOT_FOUND, str(err)) from err
    await session.commit()
    return {"interview": public_interview(interview)}


@router.delete(
    "/api/jobs/{job_id}/pursuit/interviews/{interview_id}", response_model=ApplicationDeleted
)
async def delete_interview_ep(job_id: int, interview_id: int, session: SessionDep) -> dict:
    try:
        await delete_interview(session, job_id, interview_id)
    except LookupError as err:
        raise api_error(404, ErrorCode.INTERVIEW_NOT_FOUND, str(err)) from err
    await session.commit()
    return {"id": interview_id, "deleted": True}

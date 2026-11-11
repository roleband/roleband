"""Single-use browser handoffs issued only by authenticated native control."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from tracker.api.errors import ErrorCode, api_error
from tracker.api.schemas.local_auth import BrowserExchange, BrowserSession, BrowserTicket
from tracker.platform.local_http import AuthenticationError, Authority

router = APIRouter(prefix="/api/local-auth", tags=["local-auth"])


def _authority(request: Request) -> Authority:
    authority = getattr(request.app.state, "local_authority", None)
    if authority is None:
        raise api_error(401, ErrorCode.ENGINE_LOCKED, "Open the dashboard from the app")
    return authority


@router.post("/browser-ticket", response_model=BrowserTicket)
async def browser_ticket(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _authority(request).issue_ticket()
    except AuthenticationError as error:
        raise api_error(429, ErrorCode.ENGINE_LOCKED, "Browser handoff limit reached") from error


@router.post("/browser-session", response_model=BrowserSession)
async def browser_session(body: BrowserExchange, request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _authority(request).redeem(body.ticket)
    except AuthenticationError as error:
        raise api_error(401, ErrorCode.ENGINE_LOCKED, "Browser handoff expired or already used") from error

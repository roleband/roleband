"""Authenticate API reads, writes and upgrades before any route can act."""

from __future__ import annotations

from collections.abc import Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tracker.api.errors import ErrorCode, ErrorDetail
from tracker.platform.local_http import (
    MAX_BODY,
    PROOF_HEADER,
    SESSION_PATH,
    AuthenticationError,
    Authority,
    response_proof,
)


class LocalAuthentication:
    def __init__(self, app: ASGIApp, *, authority: Callable[[], Authority | None], enabled: bool) -> None:
        self.app, self.authority, self.enabled = app, authority, enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        async def refuse(status: int = 401) -> None:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                detail = ErrorDetail(code=ErrorCode.ENGINE_LOCKED, params={}, message="Engine authentication required")
                await JSONResponse({"detail": detail.model_dump()}, status_code=status,
                                   headers={"Cache-Control": "no-store"})(scope, receive, send)

        authority = self.authority()
        headers = Headers(scope=scope)
        if authority is None:
            await refuse(503)
            return
        expected_host = authority.endpoint.removeprefix("http://")
        if (headers.getlist("host") != [expected_host]
                or len(headers.getlist("origin")) > 1
                or headers.get("origin", authority.endpoint) != authority.endpoint):
            await refuse(403)
            return
        path = scope["path"]
        protected = path.startswith("/api/") or path in {"/api", "/openapi.json", "/docs", "/redoc"} or path.startswith("/docs/")
        if scope["type"] == "http" and scope["method"] in {"GET", "HEAD"} and not protected:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await refuse()
            return
        exchange = path == SESSION_PATH and scope["method"] == "POST"
        if not exchange and len(headers.getlist("authorization")) != 1:
            await refuse()
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > (1024 if exchange else MAX_BODY):
                await refuse(413)
                return
            if not message.get("more_body", False):
                break
        raw_path = scope.get("raw_path", path.encode("utf-8"))
        target = raw_path.decode("ascii")
        if scope.get("query_string"):
            target += "?" + scope["query_string"].decode("ascii")
        delivered = False

        async def replay_body() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        if exchange:
            await self.app(scope, replay_body, send)
            return
        signed = headers["authorization"]
        try:
            credential = authority.authenticate(signed, scope["method"], target, bytes(body))
        except AuthenticationError:
            await refuse()
            return
        start: Message | None = None
        response = bytearray()

        async def prove(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
            elif message["type"] == "http.response.body":
                response.extend(message.get("body", b""))
                if len(response) > MAX_BODY:
                    raise ValueError("Authenticated engine response exceeds the transport limit")
                if not message.get("more_body", False):
                    assert start is not None
                    response_headers = MutableHeaders(scope=start)
                    response_headers[PROOF_HEADER] = response_proof(credential.secret, signed, start["status"], bytes(response))
                    response_headers["Cache-Control"] = "no-store"
                    await send(start)
                    await send({"type": "http.response.body", "body": bytes(response)})

        await self.app(scope, replay_body, prove)

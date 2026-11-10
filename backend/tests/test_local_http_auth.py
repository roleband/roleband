"""Requests prove the account and exact operation before data or control is reached."""

from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from tracker.api.boundary import LoopbackBoundary
from tracker.api.local_auth import LocalAuthentication
from tracker.api.routers.local_auth import router
from tracker.platform import local_http
from tracker.platform.local_http import (
    PROOF_HEADER,
    SESSION_PATH,
    TICKET_PATH,
    AuthenticationError,
    Authority,
    Client,
    authorization,
    response_proof,
)


@pytest.fixture
def engine(tmp_path):
    authority = Authority(tmp_path / "state", "http://127.0.0.1:58329")
    app = FastAPI()
    app.state.local_authority = authority
    touched = []

    @app.get("/api/read")
    async def read():
        touched.append("read")
        return {"sentinel": "account-private-history"}

    @app.post("/api/write")
    async def write(request: Request):
        touched.append(await request.json())
        return {"saved": True}

    @app.get("/")
    async def shell():
        return {"shell": True}

    app.include_router(router)
    app.add_middleware(LocalAuthentication, authority=lambda: authority, enabled=True)
    app.add_middleware(LoopbackBoundary, local_origin=lambda: authority.endpoint)
    try:
        yield app, authority, touched
    finally:
        authority.close()


def signed(authority, method, target, body=b"", *, key_id="control", secret=None):
    return {"Authorization": authorization(secret or authority.secret, key_id, method, target, authority.endpoint, body)}


@pytest.mark.asyncio
async def test_reads_health_control_and_documents_require_credentials(engine):
    app, authority, touched = engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url=authority.endpoint) as client:
        for path in ("/api/read", "/api/health", "/api/launcher-health", "/api/status", "/openapi.json", "/docs"):
            response = await client.get(path)
            assert response.status_code == 401
            assert set(response.json()["detail"]) == {"code", "params", "message"}
        assert (await client.post("/api/write", json={"side_effect": True})).status_code == 401
        assert (await client.get("/")).status_code == 200
    assert not touched


@pytest.mark.asyncio
async def test_signed_reads_writes_and_response_body_are_bound_to_the_request(engine):
    app, authority, touched = engine
    body = '{"value":"你好, café"}'.encode()
    headers = {**signed(authority, "POST", "/api/write?mode=save", body), "Content-Type": "application/json"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url=authority.endpoint) as client:
        response = await client.post("/api/write?mode=save", content=body, headers=headers)
        assert response.status_code == 200
        proof = response.headers[PROOF_HEADER]
        assert proof == response_proof(authority.secret, headers["Authorization"], 200, response.content)
        assert proof != response_proof(authority.secret, headers["Authorization"], 200, b'{"saved":false}')
        assert response.headers["cache-control"] == "no-store"
    assert touched == [{"value": "你好, café"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["body", "query", "method", "signature", "account", "origin", "host", "duplicate-host", "duplicate-auth"])
async def test_altered_or_foreign_requests_cannot_act(engine, tmp_path, changed):
    app, authority, touched = engine
    body, path, method = b'{"saved":true}', "/api/write?mode=save", "POST"
    headers = {**signed(authority, method, path, body), "Content-Type": "application/json"}
    if changed == "body":
        body = b'{"saved":false}'
    elif changed == "query":
        path = "/api/write?mode=delete"
    elif changed == "method":
        method = "DELETE"
    elif changed == "signature":
        headers["Authorization"] = headers["Authorization"][:-1] + ("0" if headers["Authorization"][-1] != "0" else "1")
    elif changed == "account":
        other = Authority(tmp_path / "other-account", "http://127.0.0.1:58329")
        try:
            headers.update(signed(other, method, path, body))
        finally:
            other.close()
    elif changed == "origin":
        headers["Origin"] = "http://127.0.0.1:5173"
    elif changed == "host":
        headers["Host"] = "localhost:58329"
    items = list(headers.items())
    if changed == "duplicate-host":
        items += [("Host", "127.0.0.1:58329"), ("Host", "127.0.0.1:58329")]
    elif changed == "duplicate-auth":
        items.append(("Authorization", headers["Authorization"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url=authority.endpoint) as client:
        response = await client.request(method, path, content=body, headers=items)
        assert response.status_code in {401, 403}
    assert not touched


@pytest.mark.asyncio
async def test_a_signature_is_single_use_and_old_or_future_requests_are_refused(engine, monkeypatch):
    app, authority, touched = engine
    headers = signed(authority, "GET", "/api/read")
    async with AsyncClient(transport=ASGITransport(app=app), base_url=authority.endpoint) as client:
        assert (await client.get("/api/read", headers=headers)).status_code == 200
        assert (await client.get("/api/read", headers=headers)).status_code == 401
        now = time.time()
        for offset in (-100, 100):
            with monkeypatch.context() as patch:
                patch.setattr(local_http.time, "time", lambda offset=offset: now + offset)
                expired = signed(authority, "GET", "/api/read")
            assert (await client.get("/api/read", headers=expired)).status_code == 401
    assert touched == ["read"]


@pytest.mark.asyncio
async def test_browser_handoff_is_single_use_and_browser_keys_cannot_issue_control_tickets(engine):
    app, authority, touched = engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url=authority.endpoint) as client:
        issued = await client.post(TICKET_PATH, headers=signed(authority, "POST", TICKET_PATH))
        assert issued.status_code == 200
        ticket = issued.json()["url"].split("#roleband=")[1]
        assert authority.secret not in issued.text
        browser = await client.post(SESSION_PATH, json={"ticket": ticket})
        assert browser.status_code == 200
        credential = browser.json()
        assert credential["secret"] != authority.secret
        assert (await client.post(SESSION_PATH, json={"ticket": ticket})).status_code == 401
        headers = signed(authority, "GET", "/api/read", key_id=credential["key_id"], secret=credential["secret"])
        assert (await client.get("/api/read", headers=headers)).status_code == 200
        for path in (TICKET_PATH, "/api/local-auth/%62rowser-ticket"):
            headers = signed(authority, "POST", path, key_id=credential["key_id"], secret=credential["secret"])
            assert (await client.post(path, headers=headers)).status_code == 401
    assert touched == ["read"]


def test_expired_browser_handoffs_and_sessions_do_not_survive_a_new_engine(tmp_path, monkeypatch):
    data = tmp_path / "state"
    first = Authority(data, "http://127.0.0.1:58329")
    stale = Client(data)
    try:
        ticket = first.issue_ticket()["url"].split("#roleband=")[1]
        elapsed = local_http._elapsed()
        monkeypatch.setattr(local_http, "_elapsed", lambda: elapsed + 61)
        with pytest.raises(AuthenticationError):
            first.redeem(ticket)
        ticket = first.issue_ticket()["url"].split("#roleband=")[1]
        browser = first.redeem(ticket)
    finally:
        first.close()
    second = Authority(data, "http://127.0.0.1:58329")
    try:
        assert second.secret != stale.secret
        assert second.endpoint != stale.endpoint
        with pytest.raises(AuthenticationError):
            second.authenticate(authorization(stale.secret, "control", "GET", "/api/read", stale.endpoint), "GET", "/api/read", b"")
        with pytest.raises(AuthenticationError):
            second.authenticate(authorization(browser["secret"], browser["key_id"], "GET", "/api/read", stale.endpoint), "GET", "/api/read", b"")
    finally:
        second.close()


def test_one_process_owns_discovery_and_closed_authority_cannot_authenticate(tmp_path):
    data = tmp_path / "state"
    authority = Authority(data, "http://127.0.0.1:58329")
    header = authorization(authority.secret, "control", "GET", "/api/read", authority.endpoint)
    try:
        before = local_http.record_path(data).read_bytes()
        with pytest.raises(OSError):
            Authority(data, "http://127.0.0.1:58329")
        assert local_http.record_path(data).read_bytes() == before
        assert not list((data / "launcher").glob(".http-engine-*"))
    finally:
        authority.close()
    assert not local_http.record_path(data).exists()
    with pytest.raises(AuthenticationError):
        authority.authenticate(header, "GET", "/api/read", b"")


def test_discovery_refuses_external_or_malformed_endpoints(tmp_path):
    authority = Authority(tmp_path / "state", "http://127.0.0.1:58329")
    try:
        path = authority.path
        record = json.loads(path.read_bytes())
        for endpoint in ("http://example.com:58329", "http://127.0.0.1:58329/", "http://user@127.0.0.1:58329", "http://127.0.0.1:58329/path"):
            path.write_text(json.dumps({**record, "origin": endpoint}), encoding="utf-8")
            with pytest.raises(ValueError):
                Client(tmp_path / "state")
    finally:
        authority.close()


@pytest.mark.parametrize("forged_body", [False, True])
def test_native_client_refuses_a_foreign_listener_without_sending_a_reusable_secret(tmp_path, forged_body):
    seen = []
    authority = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            seen.append(self.headers["Authorization"])
            content = b'{"sentinel":"foreign"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            if forged_body:
                self.send_header(PROOF_HEADER, response_proof(authority.secret, seen[-1], 200, b'{"sentinel":"private"}'))
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = Authority(tmp_path / "state", f"http://127.0.0.1:{server.server_port}")
    try:
        with pytest.raises(AuthenticationError, match="listener did not authenticate"):
            Client(tmp_path / "state").request("GET", "/api/health")
        assert len(seen) == 1
        assert seen[0].startswith("RoleBand control:")
        assert authority.secret not in seen[0]
    finally:
        authority.close()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(("timeout", "waited"), [(0.3, (0.0, 2.0)), (None, (2.5, 6.0))])
def test_the_native_client_waits_as_long_as_its_caller_says(tmp_path, timeout, waited):
    """A health pass gives /api/status more time than the client's default; a listener that never answers is given up
    on at the caller's time, not the default's."""
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            release.wait(10)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = Authority(tmp_path / "state", f"http://127.0.0.1:{server.server_port}")
    client = Client(tmp_path / "state")
    started = time.monotonic()
    try:
        with pytest.raises(OSError):
            client.request("GET", "/api/status", **({} if timeout is None else {"timeout": timeout}))
        assert waited[0] <= time.monotonic() - started < waited[1]
    finally:
        release.set()
        authority.close()
        server.shutdown()
        server.server_close()
        thread.join()


def test_preparation_health_is_authenticated_before_any_database_is_opened(tmp_path, monkeypatch):
    from tracker.platform import preparation
    from tracker.supervisor import prepare

    data = tmp_path / "preparation"
    preparation.update(data, database="creating")
    settings = SimpleNamespace(api_host="127.0.0.1", api_port=58329)
    monkeypatch.setattr(prepare, "DATA_DIR", data)
    monkeypatch.setattr(prepare, "get_settings", lambda: settings)
    monkeypatch.setenv("ROLEBAND_LOCAL_AUTH", "1")
    with prepare.PreparationServer("127.0.0.1", 0) as responder:
        settings.api_port = responder.server.server_port
        connection = http.client.HTTPConnection("127.0.0.1", settings.api_port, timeout=3)
        try:
            connection.request("GET", "/api/launcher-health", headers={"Host": Client(data).endpoint.removeprefix("http://")})
            response = connection.getresponse()
            assert response.status == 401
            response.read()
        finally:
            connection.close()
        status, content = Client(data).request("GET", "/api/launcher-health")
        assert status == 200
        assert json.loads(content)["preparation"]["database"] == "creating"
        assert not (data / "db").exists()
    assert not local_http.record_path(data).exists()


@pytest.mark.asyncio
async def test_browser_exchange_refuses_foreign_origins_and_large_bodies_before_consuming_ticket(engine):
    app, authority, _ = engine
    ticket = authority.issue_ticket()["url"].split("#roleband=")[1]
    async with AsyncClient(transport=ASGITransport(app=app), base_url=authority.endpoint) as client:
        response = await client.post(SESSION_PATH, json={"ticket": ticket}, headers={"Origin": "http://127.0.0.1:5173"})
        assert response.status_code == 403
        response = await client.post(SESSION_PATH, content=b"x" * 1025, headers={"Content-Type": "application/json"})
        assert response.status_code == 413
        assert (await client.post(SESSION_PATH, json={"ticket": ticket})).status_code == 200


def test_replay_memory_refuses_new_work_instead_of_forgetting_live_nonces(tmp_path):
    authority = Authority(tmp_path / "state", "http://127.0.0.1:58329")
    try:
        authority._used = {("control", str(index)): local_http._elapsed() + 100 for index in range(8192)}
        header = authorization(authority.secret, "control", "GET", "/api/read", authority.endpoint)
        with pytest.raises(AuthenticationError):
            authority.authenticate(header, "GET", "/api/read", b"")
        assert len(authority._used) == 8192
    finally:
        authority.close()


def _browser(authority):
    return authority.redeem(authority.issue_ticket()["url"].split("#roleband=")[1])


@pytest.mark.parametrize("step", [0.001, 30, local_http.TOLERATED_STEP_SECONDS])
def test_a_small_backward_clock_step_keeps_every_key_and_still_refuses_replays(tmp_path, monkeypatch, step):
    data = tmp_path / "state"
    authority = Authority(data, "http://127.0.0.1:58329")
    try:
        browser = _browser(authority)
        captured = authorization(authority.secret, "control", "GET", "/api/read", authority.endpoint)
        authority.authenticate(captured, "GET", "/api/read", b"")
        now, elapsed = time.time(), local_http._elapsed()
        monkeypatch.setattr(local_http.time, "time", lambda: now - step)
        # Long after the first window the nonce would have aged out on the wall clock.
        monkeypatch.setattr(local_http, "_elapsed", lambda: elapsed + 2 * local_http.WINDOW_SECONDS)
        with pytest.raises(AuthenticationError):
            authority.authenticate(captured, "GET", "/api/read", b"")
        authority.authenticate(authorization(authority.secret, "control", "GET", "/api/read", authority.endpoint),
                               "GET", "/api/read", b"")
        authority.authenticate(authorization(browser["secret"], browser["key_id"], "GET", "/api/read", authority.endpoint),
                               "GET", "/api/read", b"")
        assert Client(data).secret == authority.secret
    finally:
        authority.close()


def test_a_large_backward_clock_step_replaces_the_keys_in_place(tmp_path, monkeypatch):
    data = tmp_path / "state"
    authority = Authority(data, "http://127.0.0.1:58329")
    try:
        browser = _browser(authority)
        before = Client(data)
        captured = authorization(before.secret, "control", "GET", "/api/read", authority.endpoint)
        authority.authenticate(captured, "GET", "/api/read", b"")
        now = time.time()
        monkeypatch.setattr(local_http.time, "time", lambda: now - 600)
        replayed = authorization(before.secret, "control", "GET", "/api/read", authority.endpoint)
        with pytest.raises(AuthenticationError):
            authority.authenticate(replayed, "GET", "/api/read", b"")
        after = Client(data)
        assert after.secret == authority.secret != before.secret
        assert after.endpoint == before.endpoint
        authority.authenticate(authorization(after.secret, "control", "GET", "/api/read", after.endpoint),
                               "GET", "/api/read", b"")
        with pytest.raises(AuthenticationError):
            authority.authenticate(authorization(browser["secret"], browser["key_id"], "GET", "/api/read", authority.endpoint),
                                   "GET", "/api/read", b"")
        with pytest.raises(AuthenticationError):
            authority.authenticate(captured, "GET", "/api/read", b"")
    finally:
        authority.close()


def test_a_client_recovers_from_a_large_clock_step_by_reading_discovery_again(tmp_path, monkeypatch):
    """Over real HTTP: the request that meets the step is refused, the next one
    succeeds with the new key, and the responder keeps running throughout."""
    from tracker.platform import preparation
    from tracker.supervisor import prepare

    data = tmp_path / "preparation"
    preparation.update(data, database="ready", service="ready")
    settings = SimpleNamespace(api_host="127.0.0.1", api_port=58329)
    monkeypatch.setattr(prepare, "DATA_DIR", data)
    monkeypatch.setattr(prepare, "get_settings", lambda: settings)
    monkeypatch.setenv("ROLEBAND_LOCAL_AUTH", "1")
    with prepare.PreparationServer("127.0.0.1", 0) as responder:
        settings.api_port = responder.server.server_port
        assert Client(data).request("GET", "/api/launcher-health")[0] == 200
        stale = Client(data)
        now = time.time()
        monkeypatch.setattr(local_http.time, "time", lambda: now - 600)
        with pytest.raises(AuthenticationError):
            stale.request("GET", "/api/launcher-health")
        status, content = Client(data).request("GET", "/api/launcher-health")
        assert status == 200 and json.loads(content)["preparation"]["database"] == "ready"
        assert responder.thread.is_alive()


def _browser_request(authority, browser, target="/api/read"):
    return authority.authenticate(authorization(browser["secret"], browser["key_id"], "GET", target, authority.endpoint),
                                  "GET", target, b"")


def test_an_api_restart_keeps_the_engines_browser_address_and_sessions(tmp_path, monkeypatch):
    data = tmp_path / "state"
    local_http.begin_engine_session(data)
    first = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    try:
        browser = _browser(first)
        captured = authorization(browser["secret"], browser["key_id"], "GET", "/api/read", first.endpoint)
        first.authenticate(captured, "GET", "/api/read", b"")
    finally:
        first.close()
    now = time.time()
    monkeypatch.setattr(local_http.time, "time", lambda: now + 2)
    second = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    try:
        assert second.endpoint == first.endpoint
        assert second.secret != first.secret, "the control key is still each API process's own"
        _browser_request(second, browser)
        # The new process has no memory of the nonces the first one accepted.
        with pytest.raises(AuthenticationError):
            second.authenticate(captured, "GET", "/api/read", b"")
    finally:
        second.close()


def test_a_new_engine_starts_a_new_browser_address_without_old_sessions(tmp_path):
    data = tmp_path / "state"
    local_http.begin_engine_session(data)
    first = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    browser = _browser(first)
    first.close()
    local_http.end_engine_session(data)
    assert not local_http.session_path(data).exists()
    local_http.begin_engine_session(data)
    second = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    try:
        assert second.endpoint != first.endpoint
        with pytest.raises(AuthenticationError):
            _browser_request(second, browser)
    finally:
        second.close()


def test_without_an_engine_session_each_process_mints_its_own_address(tmp_path):
    data = tmp_path / "state"
    local_http.begin_engine_session(data)
    first = Authority(data, "http://127.0.0.1:58329")
    browser = _browser(first)
    first.close()
    second = Authority(data, "http://127.0.0.1:58329")
    try:
        assert second.endpoint != first.endpoint
        with pytest.raises(AuthenticationError):
            _browser_request(second, browser)
    finally:
        second.close()


def test_a_browser_session_lasts_as_long_as_its_engine(tmp_path, monkeypatch):
    data = tmp_path / "state"
    local_http.begin_engine_session(data)
    authority = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    try:
        browser = _browser(authority)
        elapsed = local_http._elapsed()
        monkeypatch.setattr(local_http, "_elapsed", lambda: elapsed + 9 * 60 * 60)
        _browser_request(authority, browser)
    finally:
        authority.close()


def test_opening_one_session_past_the_limit_ends_the_oldest(tmp_path):
    data = tmp_path / "state"
    local_http.begin_engine_session(data)
    authority = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    try:
        sessions = [_browser(authority) for _ in range(local_http.BROWSER_SESSIONS + 1)]
        with pytest.raises(AuthenticationError):
            _browser_request(authority, sessions[0])
        for browser in sessions[1:]:
            _browser_request(authority, browser)
        stored = json.loads(local_http.session_path(data).read_text())["browser"]
        assert set(stored) == {browser["key_id"] for browser in sessions[1:]}
    finally:
        authority.close()


def test_a_large_clock_step_ends_the_stored_sessions_too(tmp_path, monkeypatch):
    data = tmp_path / "state"
    local_http.begin_engine_session(data)
    first = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    try:
        browser = _browser(first)
        now = time.time()
        monkeypatch.setattr(local_http.time, "time", lambda: now - 600)
        with pytest.raises(AuthenticationError):
            _browser_request(first, browser)
    finally:
        first.close()
    assert json.loads(local_http.session_path(data).read_text())["browser"] == {}
    second = Authority(data, "http://127.0.0.1:58329", engine_session=True)
    try:
        with pytest.raises(AuthenticationError):
            _browser_request(second, browser)
    finally:
        second.close()


@pytest.mark.parametrize("record", [
    "not json", json.dumps({"format": 2, "instance": "a" * 32, "browser": {}}),
    json.dumps({"format": 1, "instance": "../evil", "browser": {}}),
    json.dumps({"format": 1, "instance": "a" * 32, "browser": {"b" * 32: "short"}}),
])
def test_a_damaged_engine_session_is_refused(tmp_path, record):
    data = tmp_path / "state"
    local_http.begin_engine_session(data)
    local_http.session_path(data).write_text(record)
    with pytest.raises(ValueError):
        Authority(data, "http://127.0.0.1:58329", engine_session=True)

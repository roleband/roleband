"""The `roleband` client as a process: its output, its exit statuses, its engine.

Every case runs `python -m tracker.cli` in a subprocess with its own HOME and
context file, so nothing on this machine selects an engine. Three kinds of
peer: none (offline answers and an engine that is down), a stub HTTP server
for replies a real engine never sends (an older engine, hostile text, a slow
answer), and a real engine (uvicorn on the API) on a scratch database of the
throwaway cluster for the switch, the workspace identity and a restart.
"""

from __future__ import annotations

import asyncio
import errno
import http.client
import json
import os
import re
import select
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = re.compile(r"^ws_[0-9a-f]{32}$")
ENVELOPE_KEYS = {"contract_version", "request_id", "workspace_id", "operation", "ok", "data", "meta", "warnings", "error"}


# --------------------------------------------------------------------------- #
# Running the client
# --------------------------------------------------------------------------- #


@dataclass
class Home:
    """A scratch HOME with an optional context file."""

    root: Path
    config: Path

    def contexts(self, current: str | None = None, **entries: dict) -> None:
        document: dict = {"format": 1, "contexts": entries}
        if current is not None:
            document["current"] = current
        self.config.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def home(tmp_path) -> Home:
    root = tmp_path / "home"
    root.mkdir()
    return Home(root, tmp_path / "cli.json")


def _env(home: Home, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home.root),
        "XDG_CONFIG_HOME": str(home.root / ".config"),
        "PYTHONPATH": str(BACKEND),
        "ROLEBAND_CLI_CONFIG": str(home.config),
        "LANG": "en_US.UTF-8",
    }
    env.update(extra)
    return {key: value for key, value in env.items() if value is not None}


@dataclass
class Result:
    status: int
    stdout: str
    stderr: str

    @property
    def envelope(self) -> dict:
        lines = self.stdout.splitlines()
        assert len(lines) == 1, f"JSON mode must write exactly one line, got {self.stdout!r}"
        body = json.loads(lines[0])
        assert set(body) == ENVELOPE_KEYS, body
        return body


def cli(home: Home, *args: str, cwd: Path | None = None, timeout: float = 30, **env: str) -> Result:
    process = subprocess.run(
        [sys.executable, "-m", "tracker.cli", *args],
        cwd=cwd or home.root,
        env=_env(home, **env),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return Result(process.returncode, process.stdout, process.stderr)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# --------------------------------------------------------------------------- #
# No engine at all
# --------------------------------------------------------------------------- #


def test_help_and_version_need_no_engine_and_no_context(home):
    helped = cli(home, "--help")
    assert helped.status == 0
    assert helped.stdout.startswith("usage: roleband")
    assert "--context NAME" in helped.stdout
    for command in ("status", "capabilities", "describe"):
        assert command in helped.stdout
    leaf = cli(home, "describe", "--help")
    assert leaf.status == 0 and "OPERATION" in leaf.stdout

    version = cli(home, "--version")
    assert version.status == 0
    assert re.fullmatch(r"roleband \S+ \(contract 1\.\d+\)\n", version.stdout)


def test_offline_capabilities_and_describe_read_the_bundle(home):
    listed = cli(home, "capabilities", "--offline", "--format", "json")
    assert listed.status == 0 and listed.stderr == ""
    body = listed.envelope
    assert body["ok"] is True and body["operation"] == "capabilities"
    # No engine was asked, so no workspace is named.
    assert body["workspace_id"] is None
    assert body["data"]["metadata_source"] == "bundled"
    assert body["data"]["engine_version"] is None
    assert {entry["operation"] for entry in body["data"]["operations"]} == {"capabilities", "describe", "status"}
    # Offline availability is unknown, never false.
    assert {entry["availability"]["state"] for entry in body["data"]["operations"]} == {"unknown"}

    described = cli(home, "describe", "status", "--offline", "--json")
    assert described.status == 0
    data = described.envelope["data"]
    assert data["operation"] == "status" and data["metadata_source"] == "bundled"
    assert data["output_schema"]["title"] == "StatusResult"

    unknown = cli(home, "describe", "no.such", "--offline", "--json")
    assert unknown.status == 2
    assert unknown.envelope["error"]["code"] == "unknown_operation"


@pytest.mark.parametrize(
    ("args", "operation"),
    [
        (("--bogus",), "cli.parse"),
        (("status", "--bogus"), "status"),
        (("capabilities", "--tier", "huge"), "capabilities"),
        (("describe",), "describe"),
        (("describe", "a/../b"), "describe"),
        (("status", "--timeout", "forever"), "status"),
        (("--format", "json", "status", "--format", "human"), "status"),
        (("--context", "a", "status", "--context", "b"), "status"),
        (("--form", "json", "status"), "status"),
        ((), "cli.parse"),
    ],
)
def test_a_parse_failure_is_one_json_envelope_with_exit_2(home, args, operation):
    result = cli(home, *args, "--json") if "--format" not in args else cli(home, *args)
    assert result.status == 2, result
    assert result.stderr == ""
    body = result.envelope
    assert body["ok"] is False and body["data"] is None
    assert body["operation"] == operation
    assert body["workspace_id"] is None
    assert body["error"]["code"] == "invalid_arguments"


def test_ndjson_is_refused_for_a_command_that_is_not_a_stream(home):
    result = cli(home, "capabilities", "--offline", "--format", "ndjson")
    assert result.status == 2
    assert result.envelope["error"]["code"] == "invalid_arguments"


def test_no_context_is_an_error_never_a_default_engine(home, tmp_path):
    """Neither a project `.env`, an engine port setting nor `ROLEBAND_PGDATA`
    selects an engine: a stub listening where they point gets no request."""
    with Stub() as stub:
        decoy = tmp_path / "decoy.json"
        decoy.write_text(json.dumps({"format": 1, "current": "x", "contexts": {"x": {"url": stub.url}}}))
        project = tmp_path / "project"
        project.mkdir()
        (project / ".env").write_text(
            f"ROLEBAND_CLI_CONFIG={decoy}\nROLEBAND_API_PORT={stub.port}\nROLEBAND_AGENT=1\n", encoding="utf-8"
        )
        result = cli(
            home, "status", "--json", cwd=project,
            ROLEBAND_PGDATA=str(tmp_path / "pgdata"), ROLEBAND_API_PORT=str(stub.port),
        )
        assert result.status == 2
        assert result.envelope["error"]["code"] == "context_required"
        assert stub.requests == []


def test_an_unknown_context_names_the_ones_there_are(home):
    home.contexts(dev={"url": "http://127.0.0.1:9"})
    result = cli(home, "status", "--context", "prod", "--json")
    assert result.status == 2
    error = result.envelope["error"]
    assert error["code"] == "context_not_found"
    assert error["details"]["contexts"] == ["dev"]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8011",  # a name, resolved by DNS
        "http://192.168.1.10:8011",  # another machine
        "https://127.0.0.1:8011",
        "http://127.0.0.1",  # no port: no default is assumed
        "http://127.0.0.1:8011/api",
        "http://user@127.0.0.1:8011",
        "http://[::1:8011",  # an unclosed bracket does not parse
    ],
)
def test_a_context_must_be_a_literal_loopback_address_and_port(home, url):
    home.contexts(current="dev", dev={"url": url})
    result = cli(home, "status", "--json")
    assert result.status == 2
    assert result.envelope["error"]["code"] == "context_invalid"


def test_a_context_file_that_is_not_utf8_is_context_invalid(home):
    home.config.write_bytes(b'{"format": 1, "current": "dev", "contexts": {"d\xe9v": {}}}')
    result = cli(home, "status", "--json")
    assert result.status == 2
    assert result.envelope["error"]["code"] == "context_invalid"
    assert "Traceback" not in result.stderr


def test_an_engine_that_is_down_is_engine_unavailable_with_exit_3(home):
    port = _free_port()
    home.contexts(current="dev", dev={"url": f"http://127.0.0.1:{port}"})
    result = cli(home, "status", "--json")
    assert result.status == 3
    body = result.envelope
    assert body["error"]["code"] == "engine_unavailable"
    assert body["error"]["retryable"] is True
    assert body["error"]["details"]["url"] == f"http://127.0.0.1:{port}"
    # A live describe never falls back to the bundle.
    described = cli(home, "describe", "status", "--json")
    assert described.status == 3 and described.envelope["data"] is None


@pytest.mark.skipif(sys.platform == "win32", reason="a pseudo-terminal is POSIX")
def test_agent_mode_selects_json_on_a_terminal_and_a_flag_still_wins(home):
    human = _on_a_terminal(home, ["capabilities", "--offline"])
    assert human.startswith("contract 1.")
    agent = _on_a_terminal(home, ["capabilities", "--offline"], ROLEBAND_AGENT="1")
    assert json.loads(agent)["ok"] is True
    explicit = _on_a_terminal(home, ["capabilities", "--offline", "--format", "human"], ROLEBAND_AGENT="1")
    assert explicit.startswith("contract 1.")


def _on_a_terminal(home: Home, args: list[str], **env: str) -> str:
    import pty

    leader, follower = pty.openpty()
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "tracker.cli", *args],
            cwd=home.root, env=_env(home, **env), stdout=follower, stderr=subprocess.PIPE,
        )
        os.close(follower)
        chunks = []
        while True:
            ready, _, _ = select.select([leader], [], [], 30)
            if not ready:
                break
            try:
                chunk = os.read(leader, 65536)
            except OSError as error:  # the follower closed: EIO on macOS and Linux
                if error.errno != errno.EIO:
                    raise
                break
            if not chunk:
                break
            chunks.append(chunk)
        assert process.wait(timeout=30) == 0, process.stderr.read() if process.stderr else ""
    finally:
        os.close(leader)
    return b"".join(chunks).decode().replace("\r\n", "\n")


def test_a_closed_pipe_ends_quietly_with_the_outcome(home):
    reader, writer = os.pipe()
    os.close(reader)
    try:
        process = subprocess.run(
            [sys.executable, "-m", "tracker.cli", "capabilities", "--offline", "--json"],
            cwd=home.root, env=_env(home), stdout=writer, stderr=subprocess.PIPE, text=True, timeout=30,
        )
    finally:
        os.close(writer)
    assert process.returncode == 0
    assert process.stderr == ""


# --------------------------------------------------------------------------- #
# A stub peer: replies a real engine never sends
# --------------------------------------------------------------------------- #


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    content_type: str = "application/json"
    delay: float = 0.0
    #: Seconds between body bytes: a peer that keeps every receive alive.
    trickle: float = 0.0


@dataclass
class Stub:
    reply: Reply = field(default_factory=Reply)
    requests: list[str] = field(default_factory=list)

    def __enter__(self) -> Stub:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                stub.requests.append(self.path)
                time.sleep(stub.reply.delay)
                self.send_response(stub.reply.status)
                self.send_header("Content-Type", stub.reply.content_type)
                self.send_header("Content-Length", str(len(stub.reply.body)))
                self.end_headers()
                try:
                    if stub.reply.trickle:
                        for byte in stub.reply.body:
                            self.wfile.write(bytes([byte]))
                            time.sleep(stub.reply.trickle)
                    else:
                        self.wfile.write(stub.reply.body)
                except OSError:
                    pass

            def log_message(self, *_args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


def _envelope(operation: str, *, ok: bool = True, data: object = None, error: dict | None = None,
              workspace_id: object = "ws_" + "a" * 32, version: str = "1.0", request_id: object = "req_stub",
              meta: object = None, warnings: object = ()) -> bytes:
    if meta is None:
        meta = {"observed_at": "2026-11-13T14:00:00Z", "partial": False, "truncated": False, "data_classes": []}
    return json.dumps({
        "contract_version": version, "request_id": request_id, "workspace_id": workspace_id,
        "operation": operation, "ok": ok, "data": data, "meta": meta,
        "warnings": list(warnings) if isinstance(warnings, tuple) else warnings, "error": error,
    }).encode()


def _failure(**fields: object) -> dict:
    error = {"code": "access_disabled", "message": "off", "retryable": False, "details": {}, "next_actions": []}
    error.update(fields)
    return {key: value for key, value in error.items() if value is not ...}


STATUS_DATA = {
    "workspace_id": "ws_" + "a" * 32,
    "engine_session_id": "f" * 32,
    "engine_version": "0.2.0",
    "contract_version": "1.0",
    "trust": {"mode": "same_account_loopback", "verified": False},
    "access": {"enabled": True, "allow_writes": False},
}


@pytest.mark.parametrize(
    "reply",
    [
        Reply(404, b'{"detail":"Not Found"}'),  # an engine from before the agent API
        Reply(200, b"<!doctype html><title>dashboard</title>", "text/html"),
        Reply(200, _envelope("status", data=STATUS_DATA, version="2.0")),
        Reply(200, _envelope("capabilities", data=STATUS_DATA)),  # answers another operation
        Reply(200, b"{not json"),
        Reply(500, _envelope("status", ok=False, error=_failure(message=...))),
        Reply(500, _envelope("status", ok=False, error=_failure(details=None))),
        Reply(500, _envelope("status", ok=False, error=_failure(retryable="no"))),
        Reply(200, _envelope("status", data=STATUS_DATA, request_id=None)),
        Reply(200, _envelope("status", data=STATUS_DATA, meta=[])),
        Reply(200, _envelope("status", data=STATUS_DATA, warnings=None)),
        Reply(200, _envelope("status", data=STATUS_DATA, workspace_id=7)),
    ],
    ids=["no-agent-api", "html", "major-2", "wrong-operation", "garbage",
         "failure-without-message", "failure-details-null", "failure-retryable-not-bool",
         "request-id-null", "meta-not-object", "warnings-null", "workspace-id-not-text"],
)
def test_a_reply_outside_the_contract_is_incompatible_with_exit_10(home, reply):
    with Stub(reply) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "status", "--json")
    assert result.status == 10
    assert result.envelope["error"]["code"] == "contract_incompatible"


def test_an_engine_that_accepts_only_signed_requests_is_transport_unverified(home):
    from tracker.api.errors import ErrorCode, ErrorDetail

    refusal = ErrorDetail(code=ErrorCode.ENGINE_LOCKED, params={}, message="Engine authentication required")
    with Stub(Reply(401, json.dumps({"detail": refusal.model_dump(mode="json")}).encode())) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "status", "--json")
    assert result.status == 3
    error = result.envelope["error"]
    assert error["code"] == "transport_unverified"
    assert error["retryable"] is False
    assert error["details"] == {"context": "dev", "trust": "signed_local_http"}


def test_another_401_is_still_outside_the_contract(home):
    with Stub(Reply(401, b'{"detail": {"code": "unauthorized"}}')) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "status", "--json")
    assert result.status == 10
    assert result.envelope["error"]["code"] == "contract_incompatible"


def test_a_connect_that_times_out_at_the_deadline_is_a_deadline(monkeypatch):
    from tracker.cli import transport
    from tracker.cli.contexts import Context
    from tracker.cli.errors import ClientError

    def connect_slowly(self: http.client.HTTPConnection) -> None:
        time.sleep(self.timeout)
        raise TimeoutError

    monkeypatch.setattr(http.client.HTTPConnection, "connect", connect_slowly)
    context = Context(name="dev", host="127.0.0.1", port=9)

    def outcome(seconds: float) -> str:
        with pytest.raises(ClientError) as raised:
            transport.get(context, "/api/agent/v1/status", operation="status",
                          deadline=time.monotonic() + seconds, request_id="req_x", user_agent="test")
        return raised.value.code

    # The caller's deadline ran out while connecting.
    assert outcome(0.2) == "deadline_exceeded"
    # The connect limit ran out with deadline to spare: nothing answers.
    monkeypatch.setattr(transport, "CONNECT_SECONDS", 0.1)
    assert outcome(5) == "engine_unavailable"


def test_the_exit_status_follows_the_error_code_not_the_http_status(home):
    refusal = _envelope("status", ok=False, workspace_id=None, error=_failure())
    with Stub(Reply(500, refusal)) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "status", "--json")
    assert result.status == 4
    assert result.envelope["error"]["code"] == "access_disabled"


def test_a_context_pinned_to_one_workspace_refuses_another(home):
    with Stub(Reply(200, _envelope("status", data=STATUS_DATA))) as stub:
        home.contexts(current="dev", dev={"url": stub.url, "workspace_id": "ws_" + "b" * 32})
        result = cli(home, "status", "--json")
    assert result.status == 3
    error = result.envelope["error"]
    assert error["code"] == "workspace_mismatch"
    assert error["details"]["answered"] == "ws_" + "a" * 32


def test_a_pinned_context_refuses_a_success_that_names_no_workspace(home):
    with Stub(Reply(200, _envelope("status", data=STATUS_DATA, workspace_id=None))) as stub:
        home.contexts(current="dev", dev={"url": stub.url, "workspace_id": "ws_" + "a" * 32})
        result = cli(home, "status", "--json")
    assert result.status == 3
    assert result.envelope["error"]["code"] == "workspace_mismatch"
    assert result.envelope["error"]["details"]["answered"] is None


def test_a_pinned_context_passes_on_a_failure_from_an_engine_that_names_no_workspace(home):
    refusal = _envelope("status", ok=False, workspace_id=None, error=_failure())
    with Stub(Reply(403, refusal)) as stub:
        home.contexts(current="dev", dev={"url": stub.url, "workspace_id": "ws_" + "a" * 32})
        result = cli(home, "status", "--json")
    assert result.status == 4
    assert result.envelope["error"]["code"] == "access_disabled"


def test_human_output_escapes_terminal_control_sequences(home):
    hostile = dict(STATUS_DATA, engine_version="0.2.0\x1b[2J\x1b]0;owned\x07\u202e")
    with Stub(Reply(200, _envelope("status", data=hostile))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "status", "--format", "human")
    assert result.status == 0
    assert "\x1b" not in result.stdout and "\x07" not in result.stdout and "\u202e" not in result.stdout
    assert "\\u001b[2J" in result.stdout


def test_a_slow_engine_is_a_deadline_with_exit_8(home):
    with Stub(Reply(200, _envelope("status", data=STATUS_DATA), delay=3)) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        started = time.monotonic()
        result = cli(home, "status", "--json", "--timeout", "500ms")
        elapsed = time.monotonic() - started
    assert result.status == 8
    assert result.envelope["error"]["code"] == "deadline_exceeded"
    assert elapsed < 3, "the client waited past its deadline"


def test_a_reply_that_trickles_past_the_deadline_is_a_deadline_with_exit_8(home):
    # Every byte arrives well inside the per-receive timeout; only a deadline
    # on the whole exchange ends this before the body is done.
    body = _envelope("status", data=STATUS_DATA)
    assert len(body) * 0.05 > 10
    with Stub(Reply(200, body, trickle=0.05)) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        started = time.monotonic()
        result = cli(home, "status", "--json", "--timeout", "1s")
        elapsed = time.monotonic() - started
    assert result.status == 8
    assert result.envelope["error"]["code"] == "deadline_exceeded"
    assert elapsed < 4, "the client waited past its deadline"


def test_the_client_sends_its_request_id_and_reaches_only_the_operations_route(home):
    with Stub(Reply(200, _envelope("describe", data={"operation": "status"}))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "describe", "status", "--json")
    assert result.status == 0
    assert stub.requests == ["/api/agent/v1/operations/status"]
    assert result.envelope["meta"]["context"] == {"name": "dev", "url": stub.url, "discovery": "configured"}


# --------------------------------------------------------------------------- #
# A real engine on a scratch database
# --------------------------------------------------------------------------- #


@pytest.fixture
def engine_database(tmp_path) -> Iterator[str]:
    """A new database on the throwaway cluster, schema built without
    migrations, so the engine's own start writes the workspace identity."""
    from tests import conftest
    from tracker.db.models import Base

    base = conftest._base_url()
    if conftest._refused:
        pytest.fail(f"{conftest._refused} Tests that need a database run on a throwaway cluster.", pytrace=False)
    if base is None:
        pytest.skip("no database configured")
    name = f"roleband_cli_{os.getpid()}_{tmp_path.name[-12:]}".replace("-", "_").lower()

    async def create() -> None:
        admin = create_async_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
        try:
            async with admin.connect() as conn:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
                await conn.execute(text(f'CREATE DATABASE "{name}"'))
        finally:
            await admin.dispose()
        engine = create_async_engine(base.set(database=name))
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    async def drop() -> None:
        admin = create_async_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
        try:
            async with admin.connect() as conn:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        finally:
            await admin.dispose()

    try:
        asyncio.run(create())
    except OSError as error:
        pytest.skip(f"database unavailable ({error})")
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(drop())


class Engine:
    """`uvicorn tracker.api.app:app` on a free port, stopped by the test."""

    def __init__(self, database_url: str, state: Path) -> None:
        self.database_url = database_url
        self.state = state
        self.port = _free_port()
        self.process: subprocess.Popen[bytes] | None = None
        self.log = state / "engine.log"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.state / "home"),
            "PYTHONPATH": os.pathsep.join(str(BACKEND / p) for p in (".", "../sdk/python", "../robots/python")),
            "ROLEBAND_DATABASE_URL": self.database_url,
            "ROLEBAND_PGDATA": os.environ.get("ROLEBAND_PGDATA", str(self.state / "unused-pgdata")),
            "ROLEBAND_STATE_DIR": str(self.state / "state"),
            "ROLEBAND_CACHE_DIR": os.environ.get("ROLEBAND_CACHE_DIR", str(self.state / "cache")),
            "ROLEBAND_PLUGINS_DIR": str(self.state / "plugins"),
            "ROLEBAND_SECRET_KEY_FILE": str(self.state / "secret.key"),
            "ROLEBAND_USAGE_STATS_HOST": "http://127.0.0.1:9",
            "ROLEBAND_SEARCH_WARM_MODEL_ON_STARTUP": "false",
            "ROLEBAND_API_PORT": str(self.port),
            "LANG": "en_US.UTF-8",
        }
        with self.log.open("ab") as log:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "tracker.api.app:app",
                 "--host", "127.0.0.1", "--port", str(self.port), "--no-proxy-headers"],
                cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                pytest.fail(f"the engine exited at start:\n{self.log.read_text()[-4000:]}")
            if self._healthy():
                return
            time.sleep(0.2)
        self.stop()
        pytest.fail(f"the engine did not answer within 90s:\n{self.log.read_text()[-4000:]}")

    def _healthy(self) -> bool:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
            connection.request("GET", "/api/health")
            return connection.getresponse().status == 200
        except OSError:
            return False

    def put_json(self, path: str, payload: dict) -> int:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("PUT", path, body=json.dumps(payload), headers={"Content-Type": "application/json"})
        return connection.getresponse().status

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)


@pytest.fixture
def engine(engine_database, tmp_path) -> Iterator[Engine]:
    running = Engine(engine_database, tmp_path / "engine")
    running.start()
    try:
        yield running
    finally:
        running.stop()


def test_a_real_engine_refuses_until_the_switch_and_then_names_its_workspace(home, engine):
    home.contexts(current="dev", dev={"url": engine.url})

    refused = cli(home, "status", "--json")
    assert refused.status == 4, refused
    assert refused.envelope["error"]["code"] == "access_disabled"
    assert refused.envelope["workspace_id"] is None

    # The person turns agent access on in Settings.
    assert engine.put_json("/api/intelligence/agents", {"enabled": True, "allow_writes": False}) == 200

    status = cli(home, "status", "--json")
    assert status.status == 0, status
    assert status.stderr == ""
    body = status.envelope
    data = body["data"]
    assert WORKSPACE.fullmatch(data["workspace_id"])
    assert body["workspace_id"] == data["workspace_id"]
    assert data["engine_session_id"] != data["workspace_id"]
    assert data["trust"] == {"mode": "same_account_loopback", "verified": False}
    assert body["meta"]["context"]["name"] == "dev"

    capabilities = cli(home, "capabilities", "--tier", "small", "--json")
    assert capabilities.status == 0
    assert capabilities.envelope["data"]["metadata_source"] == "engine"
    assert {e["availability"]["state"] for e in capabilities.envelope["data"]["operations"]} == {"available"}

    described = cli(home, "describe", "capabilities", "--json")
    assert described.status == 0
    assert described.envelope["data"]["metadata_source"] == "engine"
    unknown = cli(home, "describe", "opportunities.search", "--json")
    assert unknown.status == 2
    assert unknown.envelope["error"]["code"] == "unknown_operation"


def test_the_workspace_survives_a_restart_and_the_engine_session_does_not(home, engine):
    assert engine.put_json("/api/intelligence/agents", {"enabled": True, "allow_writes": False}) == 200
    home.contexts(current="dev", dev={"url": engine.url})
    before = cli(home, "status", "--json").envelope["data"]

    engine.stop()
    down = cli(home, "status", "--json")
    assert down.status == 3
    assert down.envelope["error"]["code"] == "engine_unavailable"

    engine.start()
    after = cli(home, "status", "--json").envelope["data"]
    assert after["workspace_id"] == before["workspace_id"]
    assert after["engine_session_id"] != before["engine_session_id"]

    # Pinning the context to that workspace keeps working across the restart.
    home.contexts(current="dev", dev={"url": engine.url, "workspace_id": before["workspace_id"]})
    assert cli(home, "status", "--json").status == 0


def test_human_output_of_a_shape_this_client_cannot_lay_out_is_shown_as_data(home):
    with Stub(Reply(200, _envelope("status", data={"workspace_id": "ws_" + "a" * 32, "note": "\x1b[31m"}))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "status", "--format", "human")
    assert result.status == 0
    assert result.stderr == ""
    assert '"note": "\\u001b[31m"' in result.stdout

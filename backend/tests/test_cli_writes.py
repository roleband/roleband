"""The client sends a write under one idempotency key, and hands it back.

Against a stub engine on a loopback port that records each request: a write
the caller gave no key is sent under a key the client makes, every resend in
the same invocation reuses it, the key comes back in `meta.idempotency_key`
on the result, and a write that timed out returns it in its error envelope so
the caller can retry without writing twice.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tracker.agents.operations.outcomes import EXIT_DEADLINE, outcome
from tracker.cli.contexts import Context
from tracker.cli.errors import ClientError, error_envelope
from tracker.cli.writes import IDEMPOTENCY_KEY_HEADER, send_write

OPERATION = "pursuits.patch"
PATH = "/api/agent/v1/pursuits/7"
WORKSPACE = "ws_" + "a" * 32


@dataclass
class Seen:
    method: str
    path: str
    key: str | None
    body: dict[str, Any]


@dataclass
class Engine:
    """Answers each request with the next behaviour: `drop` closes the
    connection without a reply, `hold` answers only once the test is over, `ok`
    answers a success envelope that names no key."""

    behaviours: list[str]
    seen: list[Seen] = field(default_factory=list)
    #: A `hold` reply waits for this, set only when the engine stops, so the
    #: client's deadline passes first however slowly the host runs.
    release: threading.Event = field(default_factory=threading.Event)

    def __enter__(self) -> Engine:
        engine = self

        class Handler(BaseHTTPRequestHandler):
            def do_PATCH(self) -> None:  # noqa: N802 - http.server's name
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                engine.seen.append(Seen("PATCH", self.path, self.headers.get(IDEMPOTENCY_KEY_HEADER), body))
                behaviour = engine.behaviours.pop(0) if engine.behaviours else "ok"
                if behaviour == "drop":
                    self.close_connection = True
                    self.connection.shutdown(2)
                    return
                if behaviour == "hold":
                    engine.release.wait(30)
                reply = json.dumps({
                    "contract_version": "1.0", "request_id": "req_stub", "workspace_id": WORKSPACE,
                    "operation": OPERATION, "ok": True, "data": {"revision": 2},
                    "meta": {"observed_at": "2026-11-15T10:00:00Z", "partial": False, "truncated": False,
                             "data_classes": []},
                    "warnings": [], "error": None,
                }).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(reply)))
                    self.end_headers()
                    self.wfile.write(reply)
                except OSError:
                    pass

            def log_message(self, *_args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.context = Context(name="dev", host="127.0.0.1", port=self.server.server_address[1])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


def _send(engine: Engine, *, key: str | None = None, seconds: float = 5.0) -> dict[str, Any]:
    return send_write(
        engine.context, "PATCH", PATH, operation=OPERATION, body={"if_revision": 1, "notes": "x"},
        deadline=time.monotonic() + seconds, request_id="req_test", user_agent="roleband/test",
        idempotency_key=key,
    )


def test_a_write_without_a_key_gets_one_and_returns_it():
    with Engine(["ok"]) as engine:
        envelope = _send(engine)
    (sent,) = engine.seen
    assert re.fullmatch(r"idk_[0-9a-f]{32}", sent.key or "")
    assert envelope["meta"]["idempotency_key"] == sent.key
    assert sent.body == {"if_revision": 1, "notes": "x"}


def test_two_invocations_make_two_keys_and_a_given_key_is_used_as_is():
    with Engine(["ok", "ok", "ok"]) as engine:
        _send(engine)
        _send(engine)
        _send(engine, key="my-own-key-0001")
    assert len({seen.key for seen in engine.seen}) == 3
    assert engine.seen[2].key == "my-own-key-0001"


def test_a_lost_reply_is_resent_under_the_same_key():
    with Engine(["drop", "ok"]) as engine:
        envelope = _send(engine)
    assert [seen.key for seen in engine.seen] == [engine.seen[0].key] * 2
    assert envelope["ok"] is True and envelope["meta"]["idempotency_key"] == engine.seen[0].key


def test_a_timed_out_write_names_its_key_operation_and_workspace():
    with Engine(["hold"]) as engine:
        engine.context = Context(name="dev", host="127.0.0.1", port=engine.context.port, workspace_id=WORKSPACE)
        with pytest.raises(ClientError) as raised:
            _send(engine, seconds=0.5)
    error = raised.value
    assert error.code == "deadline_exceeded"
    assert outcome(error.code).exit_status == EXIT_DEADLINE
    (sent,) = engine.seen  # a timeout is not resent: the write may have landed
    assert error.details["idempotency_key"] == sent.key
    assert error.details["operation"] == OPERATION and error.details["workspace_id"] == WORKSPACE
    envelope = error_envelope(OPERATION, error, request_id="req_test")
    assert envelope["meta"]["idempotency_key"] == sent.key


def test_a_key_that_is_not_a_plain_token_is_refused_before_sending():
    with Engine([]) as engine:
        with pytest.raises(ClientError) as raised:
            _send(engine, key="has spaces in it")
    assert raised.value.code == "invalid_arguments"
    assert engine.seen == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()], ids=["nan", "infinity", "object"])
def test_an_input_json_cannot_carry_is_refused_with_its_key_before_sending(value):
    with Engine([]) as engine:
        with pytest.raises(ClientError) as raised:
            send_write(
                engine.context, "PATCH", PATH, operation=OPERATION, body={"if_revision": 1, "score": value},
                deadline=time.monotonic() + 5, request_id="req_test", user_agent="roleband/test",
            )
    assert raised.value.code == "invalid_arguments"
    assert re.fullmatch(r"idk_[0-9a-f]{32}", raised.value.idempotency_key or "")
    assert engine.seen == []

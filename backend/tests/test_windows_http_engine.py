"""The real HTTP engine authenticates native control and browser access against SQL."""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import socket
import subprocess
import sys
import time

import pytest

from tracker.platform.local_http import (
    SESSION_PATH,
    AuthenticationError,
    Client,
    authorization,
    record_path,
)
from tracker.platform.paths import REPO_ROOT
from tracker.supervisor.api import RUNNING, ApiService

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows state discovery requires Windows")


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    from tests.embedded_utils import destroy
    from tracker.platform.embedded_db import ensure_server
    from tracker.platform.windows_private import private_directory

    root = tmp_path_factory.mktemp("http-engine") / "state"
    private_directory(root)
    server = ensure_server(root / "db", database="http_fixture", required_extensions=("vector", "pg_trgm"))
    env = {**os.environ, "ROLEBAND_STATE_DIR": str(root), "ROLEBAND_PGDATA": str(server.pgdata),
           "ROLEBAND_POSTGRES_DB": "http_fixture", "ROLEBAND_DATABASE_URL": "", "ROLEBAND_DB_EMBEDDED": "true",
           "ROLEBAND_CACHE_DIR": str(root / "cache"), "ROLEBAND_PLUGINS_DIR": str(root / "plugins"),
           "ROLEBAND_SECRET_KEY_FILE": str(root / "secret.key"), "ROLEBAND_PACKAGED": "0",
           "ROLEBAND_LOCAL_AUTH": "1", "ROLEBAND_API_HOST": "127.0.0.1",
           "ROLEBAND_SEARCH_SEMANTIC_ENABLED": "false", "ROLEBAND_SEARCH_WARM_MODEL_ON_STARTUP": "false",
           "ROLEBAND_NO_USAGE_STATS": "1"}
    try:
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                                cwd=REPO_ROOT / "backend", env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        yield root, server, env
    finally:
        destroy(server.pgdata)


def raw(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_real_api_signs_control_and_browser_responses_and_keeps_committed_state_after_stop(database):
    from tracker.platform.embedded_db import run_psql

    root, server, env = database
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = {**env, "ROLEBAND_API_PORT": str(port)}
    # Importing the API alone takes seconds; parallel database work stretches every start.
    startup_budget = 60
    service = ApiService(repo_root=REPO_ROOT, data_dir=root, host="127.0.0.1", port=port,
                         env=environment, start_grace_seconds=startup_budget)

    async def exercise():
        started = time.monotonic()
        try:
            await service.tend(0)
            while service.state != RUNNING and time.monotonic() - started < startup_budget:
                await asyncio.sleep(0.1)
                await service.tend(time.monotonic() - started)
            assert service.state == RUNNING, service.log.read_text(encoding="utf-8")
            client = Client(root)
            assert client.endpoint.endswith(f".localhost:{port}")
            host = client.endpoint.removeprefix("http://")
            status, content = await asyncio.to_thread(client.request, "GET", "/api/health")
            assert status == 200 and json.loads(content)["status"] == "ok"
            assert (await asyncio.to_thread(raw, port, "GET", "/api/settings/locale", None, {"Host": host}))[0] == 401
            assert (await asyncio.to_thread(raw, port, "PUT", "/api/settings/locale", b'{"language":"zh-Hans"}',
                                           {"Content-Type": "application/json", "Host": host}))[0] == 401
            status, content = await asyncio.to_thread(client.request, "PUT", "/api/settings/locale", b'{"language":"es","region":"es-ES"}')
            assert status == 200 and json.loads(content)["language"] == "es"
            browser_url = await asyncio.to_thread(client.browser_url)
            ticket = browser_url.split("#roleband=")[1]
            status, content = await asyncio.to_thread(raw, port, "POST", SESSION_PATH,
                                                     json.dumps({"ticket": ticket}).encode(), {"Content-Type": "application/json", "Host": host})
            assert status == 200
            browser = json.loads(content)
            assert browser["secret"] != client.secret
            header = authorization(browser["secret"], browser["key_id"], "GET", "/api/settings/locale", client.endpoint)
            status, content = await asyncio.to_thread(raw, port, "GET", "/api/settings/locale", None, {"Authorization": header, "Host": host})
            assert status == 200 and json.loads(content)["language"] == "es"
            assert (await asyncio.to_thread(raw, port, "GET", "/api/settings/locale", None, {"Authorization": header, "Host": host}))[0] == 401
            assert (await asyncio.to_thread(raw, port, "POST", SESSION_PATH, json.dumps({"ticket": ticket}).encode(),
                                           {"Content-Type": "application/json", "Host": host}))[0] == 401
            with socket.socket() as foreign:
                foreign.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                with pytest.raises(OSError):
                    foreign.bind(("127.0.0.1", port))
            # A successful health status alone cannot make an unrelated private key valid.
            client.secret = "00" * 32
            with pytest.raises(AuthenticationError):
                await asyncio.to_thread(client.request, "GET", "/api/health")
            old = Client(root)
            keepalive = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                header = authorization(old.secret, "control", "GET", "/api/launcher-health", old.endpoint)
                keepalive.request("GET", "/api/launcher-health", headers={"Host": host, "Authorization": header})
                response = keepalive.getresponse()
                assert response.status == 200
                response.read()
                await service.stop(grace_seconds=5)
                began = time.monotonic()
                await service.tend(0)
                while service.state != RUNNING and time.monotonic() - began < startup_budget:
                    await asyncio.sleep(.1)
                    await service.tend(time.monotonic() - began)
                assert service.state == RUNNING, service.log.read_text(encoding="utf-8")
                replacement = Client(root)
                assert replacement.secret != old.secret
                assert replacement.endpoint != old.endpoint
                status, content = await asyncio.to_thread(replacement.request, "GET", "/api/settings/locale")
                assert status == 200 and json.loads(content)["language"] == "es"
            finally:
                keepalive.close()
        finally:
            await service.stop(grace_seconds=5)
        assert not record_path(root).exists()
        assert run_psql(server.dsn(), server.bin_dir, "SELECT value->>'language' FROM app_settings WHERE key='locale'") == "es"

    asyncio.run(exercise())

"""The API, run by the supervisor as its own child.

Its process containment ends with the supervisor, and the next supervisor
starts it afresh. The supervisor restarts it when it
exits, and when it stops answering `/api/health`: alive but hung is what a
process watch alone cannot see. Restarts back off (1 s doubling to 60 s), so an
API that cannot start does not spin.
"""

from __future__ import annotations

import asyncio
import http.client
import logging
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from tracker.db import job_store
from tracker.platform.local_http import Client, required
from tracker.platform.paths import backend_dir
from tracker.supervisor import runner

logger = logging.getLogger("tracker.supervisor")

KEY = "api"

STOPPED = "stopped"
STARTING = "starting"
RUNNING = "running"
#: Exited or unhealthy, waiting out the backoff before the next start.
WAITING = "waiting"

#: Reason codes, beside the state.
EXITED = "api_exited"
UNHEALTHY = "api_unhealthy"


def uvicorn_command(python: str, host: str, port: int, *, authenticated: bool = False) -> list[str]:
    # No access log: one line per dashboard poll is most of the volume an
    # always-on API writes, and none of it is read.
    if authenticated:
        return [python, "-m", "tracker.supervisor.http_server", "--host", host, "--port", str(port)]
    return [python, "-m", "uvicorn", "tracker.api.app:app", "--host", host, "--port", str(port), "--no-access-log"]


class ApiService:
    def __init__(
        self,
        *,
        repo_root: Path,
        data_dir: Path,
        host: str,
        port: int,
        python: str = sys.executable,
        command: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        start_grace_seconds: float = 60.0,
        probe_every_seconds: float = 30.0,
        failures_to_restart: int = 3,
        max_backoff_seconds: float = 60.0,
    ) -> None:
        self.repo_root = repo_root
        self.data_dir = data_dir
        self.host, self.port = host, port
        self.authenticated = required() or (env is not None and (
            env.get("ROLEBAND_LOCAL_AUTH") == "1" or (sys.platform == "win32" and env.get("ROLEBAND_PACKAGED") == "1")
        ))
        self.command = list(command) if command is not None else uvicorn_command(python, host, port, authenticated=self.authenticated)
        self.env = env
        self.log = data_dir / "logs" / "api.log"
        self.start_grace = start_grace_seconds
        self.probe_every = probe_every_seconds
        self.failures_to_restart = failures_to_restart
        self.max_backoff = max_backoff_seconds
        self.process: subprocess.Popen | None = None
        self._process_identity: datetime | None = None
        self.state = STOPPED
        self.reason: str | None = None
        self.since = datetime.now(UTC)
        self.restarts = 0
        self._backoff = 1.0
        self._started_at = 0.0
        self._resume_at = 0.0
        self._probed_at = 0.0
        self._failures = 0

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/api/health"

    def _set(self, state: str, reason: str | None = None) -> None:
        if (state, reason) != (self.state, self.reason):
            self.state, self.reason, self.since = state, reason, datetime.now(UTC)

    def _env(self) -> dict[str, str]:
        merged = runner.child_env(self.env, 0, self.repo_root)
        merged.pop(runner.RUN_ENV, None)
        if self.authenticated:
            merged["ROLEBAND_LOCAL_AUTH"] = "1"
            merged["ROLEBAND_STATE_DIR"] = str(self.data_dir)
        return merged

    def _start(self, now: float) -> None:
        if self.authenticated and sys.platform == "win32":
            from tracker.platform.windows_private import private_directory

            private_directory(self.data_dir)
        self.process = runner.start_service(
            self.command, cwd=backend_dir(self.repo_root), env=self._env(), log=self.log
        )
        self._process_identity = runner.process_started_at(self.process) if sys.platform == "win32" else None
        self._started_at = self._probed_at = now
        self._failures = 0
        self._set(STARTING)
        logger.info("api started (pid %s) on %s:%s", self.process.pid, self.host, self.port)

    async def _healthy(self) -> bool:
        if self.authenticated:
            try:
                status, _ = await asyncio.to_thread(lambda: Client(self.data_dir).request("GET", "/api/health"))
                return status == 200
            except (OSError, ValueError, http.client.HTTPException):
                return False
        try:
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
                response = await client.get(self.url)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def _end(self, now: float, reason: str) -> None:
        """Stop the process (if it still runs) and wait out the backoff."""
        await self.stop()
        self.restarts += 1
        self._resume_at = now + self._backoff
        self._backoff = min(self._backoff * 2, self.max_backoff)
        self._set(WAITING, reason)

    async def tend(self, now: float) -> None:
        """One look: start, probe, or restart, as the API's state asks."""
        if self.process is None:
            if now >= self._resume_at:
                self._start(now)
            return
        code = self.process.poll()
        if code is not None:
            logger.error("api exited (code %s); restarting in %.0f s", code, self._backoff)
            self.process = None
            await self._end(now, EXITED)
            return
        if self.state == STARTING:
            if await self._healthy():
                self._backoff = 1.0
                self._set(RUNNING)
            elif now - self._started_at > self.start_grace:
                logger.error("api not healthy %.0f s after its start; restarting", self.start_grace)
                await self._end(now, UNHEALTHY)
            return
        if now - self._probed_at < self.probe_every:
            return
        self._probed_at = now
        if await self._healthy():
            self._failures = 0
            return
        self._failures += 1
        if self._failures >= self.failures_to_restart:
            logger.error("api stopped answering its health check; restarting")
            await self._end(now, UNHEALTHY)

    async def stop(self, grace_seconds: float = 30.0) -> None:
        """Request a stop, allow requests in flight, then force termination."""
        process, self.process = self.process, None
        identity, self._process_identity = self._process_identity, None
        if process is None:
            return
        if process.poll() is None:
            if sys.platform == "win32":
                await runner.stop_group(
                    process.pid, grace_seconds, reap=process.poll, run_id=0, proc_started_at=identity,
                )
            else:
                process.terminate()
                try:
                    await asyncio.to_thread(process.wait, grace_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait)
        self._set(STOPPED)

    def status(self) -> job_store.Status:
        detail: dict = {"restarts": self.restarts, "port": self.port}
        if self.process is not None:
            detail["pid"] = self.process.pid
        return job_store.Status(
            key=KEY, job=KEY, state=self.state, reason=self.reason, since=self.since, detail=detail
        )

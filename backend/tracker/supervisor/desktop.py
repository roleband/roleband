"""Own the Windows engine, with a private lease and a parent-only stop pipe."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import psutil

from tracker.config import get_settings
from tracker.db.session import get_engine, get_session_factory
from tracker.platform import preparation
from tracker.platform.embedded_db import claim_cluster, stop_server
from tracker.platform.local_http import SESSION_ENV, begin_engine_session, end_engine_session
from tracker.platform.local_zone import local_zone
from tracker.platform.paths import BACKEND_DIR, DATA_DIR, PACKAGED, REPO_ROOT
from tracker.supervisor import runner
from tracker.supervisor.api import ApiService
from tracker.supervisor.clock import awake_seconds
from tracker.supervisor.dispatch import Dispatcher
from tracker.supervisor.prepare import PREPARE_TIMEOUT_SECONDS, PreparationServer
from tracker.supervisor.registry import JOBS
from tracker.supervisor.service import serve

logger = logging.getLogger(__name__)


def _write_record(path: Path, marker: str) -> None:
    from tracker.platform.windows_fs import publish

    record = {"format": 1, "pid": os.getpid(), "started": psutil.Process().create_time(),
              "executable": psutil.Process().exe(), "resources": str(REPO_ROOT.resolve()),
              "state": str(DATA_DIR.resolve()), "marker": marker}
    # The native host polls this record while the engine starts.
    publish(path, json.dumps(record).encode())


async def _prepare_process(stop: asyncio.Event, development: bool, action: str) -> bool:
    args = [sys.executable, "-I", "-B", str(BACKEND_DIR / "desktop.py")]
    if development:
        args.append("--source")
    args.append(action)
    process = runner.start_service(args, cwd=BACKEND_DIR, env=runner.child_env(None, 0, REPO_ROOT),
                                   log=DATA_DIR / "logs" / "preparation.log")
    began = awake_seconds()
    try:
        while process.poll() is None and not stop.is_set():
            if awake_seconds() - began > PREPARE_TIMEOUT_SECONDS:
                raise TimeoutError("Desktop preparation exceeded its time limit")
            await asyncio.sleep(0.1)
        if stop.is_set():
            return False
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, args)
        return True
    finally:
        if process.poll() is None:
            await runner.stop_group(process.pid, 5, reap=process.poll, run_id=0,
                                    proc_started_at=runner.process_started_at(process))
        await asyncio.to_thread(process.wait)


async def run(marker: str, *, development: bool, fixture: bool, dry_run: bool) -> int:
    if sys.platform != "win32":
        raise ValueError("The desktop engine requires Windows")
    if not os.environ.get("ROLEBAND_STATE_DIR") or not DATA_DIR.is_absolute():
        raise ValueError("The desktop engine requires explicit retained state")
    settings = get_settings()
    if (settings.database_url_override or not settings.db_embedded
            or settings.embedded_pgdata().resolve() != (DATA_DIR / "db").resolve()
            or settings.cache_dir().resolve() != (DATA_DIR / "cache").resolve()
            or settings.plugins_dir().resolve() != (DATA_DIR / "plugins").resolve()):
        raise ValueError("The desktop engine requires its own database and state")
    if development and not dry_run:
        raise ValueError("Source desktop trials require network dry-run mode")
    if fixture and not dry_run:
        raise ValueError("Synthetic desktop fixtures require network dry-run mode")
    from tracker.platform.windows_leases import ENGINE, lease
    from tracker.platform.windows_private import private_directory, require_private

    for directory in (DATA_DIR, DATA_DIR / "launcher", DATA_DIR / "logs"):
        private_directory(directory)
    logging.basicConfig(filename=DATA_DIR / "logs" / "engine.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    held = ExitStack()
    record = DATA_DIR / "launcher" / "owned-engine.json"
    leased = False
    server = None
    engine = None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def listen() -> None:
        for line in sys.stdin:
            if line.strip() == "stop":
                break
        loop.call_soon_threadsafe(stop.set)

    threading.Thread(target=listen, name="desktop-parent", daemon=True).start()
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGBREAK):
        signal.signal(signum, lambda *_: loop.call_soon_threadsafe(stop.set))
    try:
        held.enter_context(lease(DATA_DIR / "launcher" / ENGINE))
        leased = True
        if record.exists():
            require_private(record)
        _write_record(record, marker)
        begin_engine_session(DATA_DIR)
        claim_cluster(settings.embedded_pgdata(), "app")
        preparation.update(DATA_DIR, database="creating", service="starting", model="waiting", reason=None)
        with PreparationServer("127.0.0.1", 0):
            # The database is owned here, outside every cancellable trampoline.
            server = await asyncio.to_thread(settings.ensure_embedded_server)
            if not await _prepare_process(stop, development, "prepare"):
                return 0
            preparation.update(DATA_DIR, database="ready", model="unused" if dry_run else "waiting")
            if fixture and not stop.is_set():
                if not await _prepare_process(stop, development, "seed"):
                    return 0
        if stop.is_set():
            return 0
        engine = get_engine()
        jobs = tuple(
            replace(job, command=("{python}", "-m", "tracker.supervisor.entries", "backup"), cwd="backend")
            if job.name == "backup" else job
            for job in JOBS if job.name not in {"preflight", "dashboard_build"}
        )
        dispatcher = Dispatcher(get_session_factory(), REPO_ROOT, DATA_DIR, zone=local_zone(), jobs=jobs,
                                read_gate=None, dry_run_network=dry_run)
        api = ApiService(repo_root=REPO_ROOT, data_dir=DATA_DIR, host="127.0.0.1", port=settings.api_port,
                         env={**os.environ, SESSION_ENV: "1"})
        await serve(dispatcher, engine, stop, api=api, cancel_on_stop=True)
        return 0
    except Exception:
        logger.exception("desktop engine stopped")
        if leased:
            preparation.update(DATA_DIR, service="failed", reason="service_failed")
        raise
    finally:
        if engine is not None:
            await engine.dispose()
        if server is not None:
            await asyncio.to_thread(stop_server, server.pgdata)
        if leased:
            end_engine_session(DATA_DIR)
            record.unlink(missing_ok=True)
        held.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--synthetic-fixture", action="store_true")
    parser.add_argument("--dry-run-network", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{32}", args.marker):
        parser.error("invalid desktop process marker")
    if args.development == PACKAGED:
        parser.error("desktop resource layout does not match its launch mode")
    return asyncio.run(run(args.marker, development=args.development,
                           fixture=args.synthetic_fixture, dry_run=args.dry_run_network))


if __name__ == "__main__":
    sys.exit(main())

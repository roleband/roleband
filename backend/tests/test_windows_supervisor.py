"""Native job containment, recovery identity and cancellation on synthetic processes."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psutil
import pytest

from tests.conftest import allow_windows_process_control
from tracker.platform.paths import REPO_ROOT
from tracker.supervisor import child, runner
from tracker.supervisor.registry import JobSpec, OnRequest, Power

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="Windows process control requires Windows"),
    pytest.mark.usefixtures("no_escape"),
]

#: Captured at import, before `no_escape` replaces them. The fixture below hands them back to these tests
#: only: starting, signalling and stopping processes is the behaviour under test, and every process is one
#: this file started.
REAL_POPEN = subprocess.Popen
REAL_KILL = os.kill


@pytest.fixture(autouse=True)
def real_processes(no_escape, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", REAL_POPEN)
    monkeypatch.setattr(os, "kill", REAL_KILL)
    allow_windows_process_control(monkeypatch)


def wait_for(check, *, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.025)
    raise AssertionError("owned process did not reach the expected state")


def job(code: str, *, caffeinate=False) -> JobSpec:
    return JobSpec("probe", ("{python}", "-c", code), OnRequest(), power=Power.NONE,
                   uses_database=False, caffeinate=caffeinate)


@pytest.fixture
def launch(tmp_path):
    launched = []

    def start(code, run_id=41, *, data_dir=None, caffeinate=False):
        result = runner.launch(job(code, caffeinate=caffeinate), run_id, repo_root=REPO_ROOT, data_dir=data_dir or tmp_path)
        launched.append(result)
        return result

    yield start
    for result in launched:
        if result.process.poll() is None:
            asyncio.run(runner.stop_group(result.pid, 0, reap=result.process.poll))
        if result.process.poll() is None:
            result.process.kill()
        result.process.wait(timeout=15)


def cooperative(ready: Path, finished: Path) -> str:
    return (
        "import os, signal, time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGBREAK, signal.default_int_handler)\n"
        f"Path({str(ready)!r}).write_text(str(os.getpid()))\n"
        "try:\n    while True: time.sleep(0.05)\n"
        f"finally: Path({str(finished)!r}).write_text('cleaned')\n"
    )


def test_native_pid_exit_status_log_and_private_result(launch, tmp_path):
    from tracker.platform.windows_private import require_private

    result = launch("import os; print(os.getpid(), flush=True); raise SystemExit(3)")
    assert result.process.wait(timeout=20) == 3, result.log_path.read_text()
    assert int(result.log_path.read_text().strip()) != result.pid
    assert child.read_result(runner.result_path(tmp_path, 41))["exit_code"] == 3
    require_private(result.log_path)
    require_private(runner.result_path(tmp_path, 41))
    assert not runner.is_run(result.pid, 41, result.proc_started_at)


def test_a_run_names_the_wrapper_a_stop_signals(launch, tmp_path):
    """A scan records what a stop of it signals; Windows has no process group, so that is the run's wrapper."""
    from tracker.platform.windows_process import run_wrapper

    named = tmp_path / "named.txt"
    result = launch("from pathlib import Path\nfrom tracker.platform.windows_process import run_wrapper\n"
                    f"Path({str(named)!r}).write_text(str(run_wrapper()))")
    assert result.process.wait(timeout=20) == 0, result.log_path.read_text()
    assert named.read_text() == str(result.pid), "the run did not name the wrapper the supervisor stops"
    assert run_wrapper() is None, "a process outside any run named a wrapper"


def test_requested_keep_awake_uses_native_trampoline_lifetime(launch):
    result = launch("print('completed under power request')", caffeinate=True)
    assert result.process.wait(timeout=20) == 0, result.log_path.read_text()
    assert "completed under power request" in result.log_path.read_text()


@pytest.mark.parametrize("accepted", [True, False])
def test_keep_awake_requests_system_state_and_reports_native_failure(monkeypatch, accepted):
    from types import SimpleNamespace

    from tracker.platform import windows_process

    requested = []

    def request(flags):
        requested.append(flags)
        return int(accepted)

    monkeypatch.setattr(windows_process, "_kernel", lambda: SimpleNamespace(SetThreadExecutionState=request))
    if accepted:
        windows_process.hold_awake()
    else:
        with pytest.raises(OSError):
            windows_process.hold_awake()
    assert requested == [0x80000001]


def test_unsafe_log_acl_is_a_spawn_error_before_any_job_starts(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    subprocess.run(["icacls", str(logs), "/grant", "*S-1-1-0:(R)"], capture_output=True, check=True)
    with pytest.raises(OSError, match="another account"):
        runner.launch(job("pass"), 41, repo_root=REPO_ROOT, data_dir=tmp_path)
    assert not (tmp_path / "run").exists()


def test_an_alternate_virtualenv_keeps_one_kernel_pid(tmp_path):
    import shutil

    from tracker.platform.windows_process import popen_options

    environment = tmp_path / "alternate"
    scripts = environment / "Scripts"
    scripts.mkdir(parents=True)
    python = scripts / "python.exe"
    shutil.copyfile(sys.executable, python)
    native = Path(psutil.Process().exe())
    (environment / "pyvenv.cfg").write_text(
        f"home = {native.parent}\nexecutable = {native}\ninclude-system-site-packages = false\nversion = 3.12.10\n",
        encoding="utf-8",
    )
    code = "import os,sys,json; print(json.dumps({'pid':os.getpid(),'prefix':sys.prefix}))"
    env = dict(os.environ)
    process = subprocess.Popen([str(python), "-c", code], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, **popen_options(str(python), env))
    stdout, stderr = process.communicate(timeout=20)
    assert process.returncode == 0, stderr
    actual = json.loads(stdout)
    assert actual["pid"] == process.pid
    assert Path(actual["prefix"]).resolve() == environment.resolve()


def test_graceful_break_runs_cleanup_and_records_cancellation(launch, tmp_path):
    ready, finished = tmp_path / "ready", tmp_path / "finished"
    result = launch(cooperative(ready, finished))
    wait_for(ready.exists)
    outcome = asyncio.run(runner.stop_group(
        result.pid, 5, reap=result.process.poll, run_id=41,
        proc_started_at=result.proc_started_at, data_dir=tmp_path,
    ))
    assert outcome == "terminated", result.log_path.read_text()
    assert finished.read_text() == "cleaned"
    assert child.read_result(runner.result_path(tmp_path, 41))["signalled"]


def test_forced_stop_kills_descendants_that_ignore_break(launch, tmp_path):
    descendant = tmp_path / "descendant"
    grandchild = (
        "import os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGBREAK, signal.SIG_IGN); "
        f"Path({str(descendant)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    code = (
        "import subprocess,sys,signal,time\n"
        "signal.signal(signal.SIGBREAK, signal.SIG_IGN)\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(60)\n"
    )
    result = launch(code)
    wait_for(descendant.exists)
    descendant_pid = int(descendant.read_text())
    began = time.monotonic()
    assert asyncio.run(runner.stop_group(result.pid, 0.3, reap=result.process.poll)) == "killed"
    assert time.monotonic() - began >= 0.3
    wait_for(lambda: not psutil.pid_exists(descendant_pid))
    assert not runner.group_alive(result.pid)


def test_stop_during_startup_leaves_no_owned_job(launch):
    result = launch("import time; time.sleep(60)")
    assert asyncio.run(runner.stop_group(result.pid, 0.2, reap=result.process.poll)) in {"terminated", "killed"}
    result.process.wait(timeout=10)
    assert not runner.group_alive(result.pid)


def test_recovery_identity_refuses_wrong_start_run_and_state_directory(launch, tmp_path):
    first = launch("import time; time.sleep(60)", 123)
    second = launch("import time; time.sleep(60)", 123, data_dir=tmp_path / "another")
    assert runner.is_run(first.pid, 123, first.proc_started_at, data_dir=tmp_path)
    assert not runner.is_run(first.pid, 12, first.proc_started_at, data_dir=tmp_path)
    assert not runner.is_run(first.pid, 123, first.proc_started_at + timedelta(seconds=30), data_dir=tmp_path)
    assert not runner.is_run(first.pid, 123, first.proc_started_at, data_dir=tmp_path / "another")
    assert runner.find_run(123, data_dir=tmp_path) == first.pid
    assert runner.find_run(123, data_dir=tmp_path / "another") == second.pid
    assert asyncio.run(runner.stop_group(
        first.pid, 0, run_id=12, proc_started_at=first.proc_started_at, data_dir=tmp_path,
    )) == "gone"
    assert first.process.poll() is None


def _parent(tmp_path, *, service):
    from tracker.platform.windows_process import popen_options

    state = tmp_path / "parent-state.json"
    ready = tmp_path / "ready"
    finished = tmp_path / "finished"
    script = tmp_path / "parent.py"
    code = cooperative(ready, finished)
    start = (
        f"p = runner.start_service([sys.executable,'-c',{code!r}],cwd=REPO_ROOT/'backend',"
        f"env=runner.child_env(None,0,REPO_ROOT),log=Path({str(tmp_path / 'logs/api.log')!r}))\n"
        if service else
        f"p = runner.launch(JobSpec('probe',('{{python}}','-c',{code!r}),OnRequest(),"
        f"power=Power.NONE,uses_database=False),77,repo_root=REPO_ROOT,data_dir=Path({str(tmp_path)!r})).process\n"
    )
    script.write_text(
        "import sys,time,json\nfrom pathlib import Path\nfrom tracker.supervisor import runner\n"
        "from tracker.platform.paths import REPO_ROOT\nfrom tracker.supervisor.registry import JobSpec,OnRequest,Power\n"
        + start + f"Path({str(state)!r}).write_text(json.dumps({{'pid':p.pid}}))\n"
        "time.sleep(60)\n", encoding="utf-8",
    )
    env = runner.child_env(None, 0, REPO_ROOT)
    env.pop(runner.RUN_ENV, None)
    process = subprocess.Popen([sys.executable, str(script)], env=env, **popen_options(sys.executable, env))
    try:
        wait_for(state.exists)
        wait_for(ready.exists)
    except BaseException:
        process.kill()
        process.wait(timeout=10)
        if state.exists():
            asyncio.run(runner.stop_group(int(json.loads(state.read_text())["pid"]), 0))
        raise
    return process, int(json.loads(state.read_text())["pid"]), int(ready.read_text()), finished


def test_job_survives_supervisor_crash_and_can_be_adopted_then_cancelled(tmp_path):
    parent, pid, command_pid, finished = _parent(tmp_path, service=False)
    began = runner.started_at(pid)
    try:
        parent.kill()
        parent.wait(timeout=10)
        assert runner.is_run(pid, 77, began, data_dir=tmp_path)
        assert runner.find_run(77, data_dir=tmp_path) == pid
        assert asyncio.run(runner.stop_group(pid, 5, run_id=77, proc_started_at=began, data_dir=tmp_path)) == "terminated"
        assert finished.read_text() == "cleaned"
        wait_for(lambda: not psutil.pid_exists(command_pid))
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=10)
        asyncio.run(runner.stop_group(pid, 0))


def test_service_and_descendants_end_when_supervisor_crashes(tmp_path):
    parent, pid, command_pid, _finished = _parent(tmp_path, service=True)
    try:
        parent.kill()
        parent.wait(timeout=10)
        wait_for(lambda: not psutil.pid_exists(pid))
        wait_for(lambda: not psutil.pid_exists(command_pid))
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=10)
        asyncio.run(runner.stop_group(pid, 0))


def test_api_service_stop_uses_graceful_console_cancellation(tmp_path):
    from tracker.supervisor.api import ApiService

    ready, finished = tmp_path / "ready", tmp_path / "finished"
    api = ApiService(repo_root=REPO_ROOT, data_dir=tmp_path, host="127.0.0.1", port=0,
                     command=[sys.executable, "-c", cooperative(ready, finished)])

    async def exercise():
        try:
            await api.tend(0)
            await asyncio.to_thread(wait_for, ready.exists)
            await api.stop(grace_seconds=5)
            assert api.state == "stopped"
            assert finished.read_text() == "cleaned"
        finally:
            await api.stop(grace_seconds=0)

    asyncio.run(exercise())


def test_cancellation_refuses_an_unrelated_process(tmp_path):
    from tracker.platform.windows_process import popen_options

    env = dict(os.environ)
    foreign = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"],
                               env=env, **popen_options(sys.executable, env))
    try:
        assert asyncio.run(runner.stop_group(foreign.pid, 0)) == "gone"
        assert foreign.poll() is None
    finally:
        foreign.kill()
        foreign.wait(timeout=10)


@pytest.mark.parametrize("code,expected", [(0, 0), (137, 137), (0xC000013A, -1073741510)])
def test_native_exit_status_preserves_bits_in_a_signed_sql_integer(code, expected):
    assert child.exit_status(code) == expected


def test_a_normal_exit_also_removes_descendants(launch, tmp_path):
    descendant = tmp_path / "descendant"
    grandchild = (
        "import os,time;from pathlib import Path;"
        f"Path({str(descendant)!r}).write_text(str(os.getpid()));time.sleep(60)"
    )
    code = (
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        f"subprocess.Popen([sys.executable,'-c',{grandchild!r}])\n"
        f"while not Path({str(descendant)!r}).exists(): time.sleep(0.01)\n"
    )
    result = launch(code)
    assert result.process.wait(timeout=20) == 0, result.log_path.read_text()
    wait_for(lambda: not psutil.pid_exists(int(descendant.read_text())))


def test_an_unstartable_command_records_failure(tmp_path):
    missing = JobSpec("missing", (str(tmp_path / "missing.exe"),), OnRequest(), power=Power.NONE, uses_database=False)
    result = runner.launch(missing, 13, repo_root=REPO_ROOT, data_dir=tmp_path)
    assert result.process.wait(timeout=20) == 127, result.log_path.read_text()
    assert child.read_result(runner.result_path(tmp_path, 13))["exit_code"] == 127


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    from tests.embedded_utils import destroy
    from tracker.platform.embedded_db import ensure_server

    root = tmp_path_factory.mktemp("windows-dispatcher")
    server = ensure_server(root / "db", database="probe", required_extensions=("vector", "pg_trgm"))
    env = {**os.environ, "ROLEBAND_PGDATA": str(server.pgdata), "ROLEBAND_POSTGRES_DB": "probe",
           "ROLEBAND_DATABASE_URL": "", "ROLEBAND_CACHE_DIR": str(root / "cache"),
           "ROLEBAND_PLUGINS_DIR": str(root / "plugins"), "ROLEBAND_SECRET_KEY_FILE": str(root / "secret.key")}
    try:
        migrated = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                                  cwd=REPO_ROOT / "backend", env=env, capture_output=True, text=True, timeout=120)
        assert migrated.returncode == 0, migrated.stderr
        yield server
    finally:
        destroy(server.pgdata)


def test_job_cancellation_leaves_database_owner_and_history_alive(database, launch, tmp_path):
    from tracker.platform.embedded_db import run_psql

    ready = tmp_path / "database-write"
    run_psql(database.dsn(), database.bin_dir, "CREATE TABLE cancellation_history (value text)")
    code = (
        "import psycopg2,signal,time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGBREAK,signal.SIG_IGN)\n"
        f"connection=psycopg2.connect({database.dsn()!r})\n"
        "with connection.cursor() as cursor: cursor.execute(\"INSERT INTO cancellation_history VALUES ('retained')\")\n"
        "connection.commit()\n"
        f"Path({str(ready)!r}).write_text('committed')\n"
        "time.sleep(60)\n"
    )
    result = launch(code)
    wait_for(ready.exists)
    assert asyncio.run(runner.stop_group(result.pid, 0.1, reap=result.process.poll)) == "killed"
    assert run_psql(database.dsn(), database.bin_dir, "SELECT value FROM cancellation_history") == "retained"


def test_native_liveness_and_cluster_inventory_stay_within_the_requested_root(database):
    from tracker.supervisor.residue import clusters_under, pid_alive

    assert pid_alive(os.getpid())
    assert not pid_alive(2**31 - 1)
    assert clusters_under(database.pgdata) == [database.pgdata.resolve()]
    assert clusters_under(database.pgdata.parent / "db2") == []


def test_cancellable_job_cannot_initialize_its_own_postmaster(launch, tmp_path):
    target = tmp_path / "unsafe-job-db"
    code = (
        "from pathlib import Path\nfrom tracker.platform.embedded_db import ensure_server,EmbeddedDbError\n"
        f"try: ensure_server(Path({str(target)!r}),database='probe')\n"
        "except EmbeddedDbError as error:\n    print(error)\n    raise SystemExit(7)\n"
        "raise SystemExit(0)\n"
    )
    result = launch(code)
    assert result.process.wait(timeout=20) == 7, result.log_path.read_text()
    assert "engine host" in result.log_path.read_text()
    assert not (target / "PG_VERSION").exists()
    assert not (tmp_path / "unsafe-job-db.auth" / "pgpass.conf").exists()


def test_dispatcher_adopts_once_and_records_a_cancel_in_sql(database, tmp_path):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from tracker.db import job_store
    from tracker.db.models import JobRun
    from tracker.platform.power import Power as Machine
    from tracker.supervisor.dispatch import Dispatcher

    ready, finished = tmp_path / "ready", tmp_path / "finished"
    spec = JobSpec("windows_dispatch", ("{python}", "-c", cooperative(ready, finished)), OnRequest(),
                   power=Power.NONE, uses_database=False, grace_seconds=5)

    async def exercise():
        engine = create_async_engine(database.uri())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        dispatcher = Dispatcher(factory, REPO_ROOT, tmp_path, zone=ZoneInfo("UTC"), jobs=(spec,), read_gate=None,
                                power=lambda: Machine(False, False), awake_every=None, prune_every=None, wake_log=lambda: None)
        try:
            async with factory() as session:
                await job_store.ring(session, spec.name, requested_by="test")
                await session.commit()
            await dispatcher.tick()
            [watched] = dispatcher.watched.values()
            await asyncio.to_thread(wait_for, ready.exists)
            successor = Dispatcher(factory, REPO_ROOT, tmp_path, zone=ZoneInfo("UTC"), jobs=(spec,), read_gate=None,
                                   power=lambda: Machine(False, False), awake_every=None, prune_every=None, wake_log=lambda: None)
            [(run_id, verdict)] = await successor.adopt()
            assert verdict.action == "adopt"
            await successor.tick()
            async with factory() as session:
                rows = list(await session.scalars(select(JobRun).where(JobRun.job == spec.name)))
                assert len(rows) == 1
                assert await job_store.request_cancel(session, run_id, reason="test")
                await session.commit()
            deadline = time.monotonic() + 20
            while successor.watched and time.monotonic() < deadline:
                await successor.tick()
                await asyncio.sleep(0.025)
            assert not successor.watched
            async with factory() as session:
                row = await session.get(JobRun, run_id)
                assert row.state == job_store.RUN_CANCELLED
                assert -(2**31) <= row.exit_code < 2**31
            assert finished.read_text() == "cleaned"
            assert watched.launched.process.wait(timeout=10) != 0
        finally:
            for active in dispatcher.watched.values():
                await runner.stop_group(active.launched.pid, 0, reap=active.launched.process.poll)
            await engine.dispose()

    asyncio.run(exercise())


def test_dispatcher_timeout_records_its_reason_and_allows_cleanup(database, tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from tracker.db import job_store
    from tracker.db.models import JobRun
    from tracker.platform.power import Power as Machine
    from tracker.supervisor.dispatch import Dispatcher

    ready, finished = tmp_path / "ready", tmp_path / "finished"
    spec = JobSpec("windows_timeout", ("{python}", "-c", cooperative(ready, finished)), OnRequest(),
                   power=Power.NONE, uses_database=False, timeout_seconds=0.2, grace_seconds=5)

    async def exercise():
        engine = create_async_engine(database.uri())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        dispatcher = Dispatcher(factory, REPO_ROOT, tmp_path, zone=ZoneInfo("UTC"), jobs=(spec,), read_gate=None,
                                power=lambda: Machine(False, False), awake_every=None, prune_every=None, wake_log=lambda: None)
        try:
            async with factory() as session:
                await job_store.ring(session, spec.name, requested_by="test")
                await session.commit()
            await dispatcher.tick()
            [watched] = dispatcher.watched.values()
            await asyncio.to_thread(wait_for, ready.exists)
            deadline = time.monotonic() + 20
            while dispatcher.watched and time.monotonic() < deadline:
                await dispatcher.tick()
                await asyncio.sleep(0.025)
            assert not dispatcher.watched
            async with factory() as session:
                row = await session.get(JobRun, watched.launched.run_id)
                assert row.state == job_store.TIMED_OUT
            assert finished.read_text() == "cleaned"
        finally:
            for active in dispatcher.watched.values():
                await runner.stop_group(active.launched.pid, 0, reap=active.launched.process.poll)
            await engine.dispose()

    asyncio.run(exercise())

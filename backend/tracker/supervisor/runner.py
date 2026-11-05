"""Start, find, prove and stop supervised processes.

Every job starts through the trampoline (`tracker.supervisor.child`) in a POSIX
session or a Windows Job Object, so a supervisor restart leaves the job running.
Cancellation reaches its descendants through that containment.
Identity is the PID, the process start time and the run marker in the argv
together: the OS recycles PIDs, so a PID alone proves nothing.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tracker.platform.paths import PACKAGED, backend_dir
from tracker.supervisor import child, logs
from tracker.supervisor.clock import awake_seconds
from tracker.supervisor.registry import JobSpec

#: The environment variable a child reads to know its own run, for progress.
RUN_ENV = "ROLEBAND_JOB_RUN"
#: Where a job writes its own return value; `entries.RAW_ENV` reads the same name.
RAW_ENV = "ROLEBAND_JOB_RAW"

#: `ps` prints start times like "Mon Oct 19 05:01:18 2026", in local time.
_LSTART = "%a %b %d %H:%M:%S %Y"
_PS_ENV = {"LC_ALL": "C", "PATH": "/bin:/usr/bin"}


@dataclass
class Launched:
    run_id: int
    pid: int
    pgid: int
    proc_started_at: datetime | None
    log_path: Path
    log_offset: int
    #: Our own child, reaped through it; None for a run adopted after a restart.
    process: subprocess.Popen | None
    #: Awake time at launch or adoption, for the timeout.
    since_awake: float


def command(job: JobSpec, extra: Sequence[str] = (), *, python: str = sys.executable) -> list[str]:
    return [python if part == "{python}" else part for part in job.command] + list(extra)


def result_path(data_dir: Path, run_id: int) -> Path:
    return data_dir / "run" / f"{run_id}.json"


def raw_path(data_dir: Path, run_id: int) -> Path:
    """Where a job's own return value goes (`tracker.supervisor.entries`)."""
    return data_dir / "run" / f"{run_id}.raw.json"


def log_path(data_dir: Path, job: JobSpec) -> Path:
    return data_dir / "logs" / f"{job.name}.log"


def launch(
    job: JobSpec,
    run_id: int,
    *,
    repo_root: Path,
    data_dir: Path,
    extra: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    python: str = sys.executable,
) -> Launched:
    """Start `job` as an isolated run, with output appended to its log."""
    log = log_path(data_dir, job)
    fd = logs.open_append(log)
    try:
        offset = os.fstat(fd).st_size
        result = result_path(data_dir, run_id)
        if sys.platform == "win32":
            from tracker.platform.windows_private import private_directory

            private_directory(result.parent)
        else:
            result.parent.mkdir(parents=True, exist_ok=True)
        result.unlink(missing_ok=True)
        raw = raw_path(data_dir, run_id)
        raw.unlink(missing_ok=True)
        argv = [python, "-m", child.MARKER, "--run", str(run_id), "--result", str(result)]
        if job.caffeinate:
            argv.append("--caffeinate")
        argv += ["--", *command(job, extra, python=python)]
        environment = child_env(env, run_id, repo_root)
        environment.update({name: value.replace("{python}", python) for name, value in job.env})
        environment[RAW_ENV] = str(raw)
        options: dict = {"start_new_session": True}
        if sys.platform == "win32":
            from tracker.platform.windows_process import popen_options

            options = popen_options(python, environment)
        process = subprocess.Popen(  # noqa: S603 - registry commands only
            argv,
            cwd=backend_dir(repo_root) if job.cwd == "backend" else repo_root / job.cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=fd,
            stderr=fd,
            **options,
        )
    finally:
        os.close(fd)
    return Launched(
        run_id=run_id,
        pid=process.pid,
        pgid=process.pid,
        proc_started_at=process_started_at(process),
        log_path=log,
        log_offset=offset,
        process=process,
        since_awake=awake_seconds(),
    )


def child_env(env: Mapping[str, str] | None, run_id: int, repo_root: Path) -> dict[str, str]:
    """The child's environment. The checkout's own `backend/` leads the import
    path, so a job started from the repository root or `dashboard/` still loads
    this checkout's code, never another checkout's installed copy."""
    merged = dict(os.environ if env is None else env)
    backend = str(backend_dir(repo_root))
    path = merged.get("PYTHONPATH", "")
    merged["PYTHONPATH"] = backend if not path else f"{backend}{os.pathsep}{path}"
    merged["PYTHONUNBUFFERED"] = "1"
    if PACKAGED:
        merged["PYTHONDONTWRITEBYTECODE"] = "1"
    merged[RUN_ENV] = str(run_id)
    return merged


def _ps(*args: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603 - fixed system tool
            ["ps", *args], capture_output=True, text=True, timeout=5, check=False, env=_PS_ENV
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _parse_lstart(text: str) -> datetime | None:
    try:
        local = datetime.strptime(" ".join(text.split()[:5]), _LSTART)
    except ValueError:
        return None
    return local.astimezone().astimezone(UTC)


def started_at(pid: int) -> datetime | None:
    if sys.platform == "win32":
        import psutil

        try:
            return datetime.fromtimestamp(psutil.Process(pid).create_time(), UTC)
        except psutil.Error:
            return None
    out = _ps("-o", "lstart=", "-p", str(pid))
    return None if not out or not out.strip() else _parse_lstart(out)


def process_started_at(process: subprocess.Popen) -> datetime | None:
    """An owned handle pins the kernel creation time across Windows PID reuse."""
    if sys.platform == "win32":
        from tracker.platform.windows_process import creation_time

        # CPython's owned Windows handle is absent from the public Popen stubs.
        return datetime.fromtimestamp(creation_time(int(process._handle)), UTC)  # type: ignore[attr-defined]
    return started_at(process.pid)


def identity(pid: int) -> tuple[datetime | None, str] | None:
    """(start time, command line) of a live process, or None."""
    if sys.platform == "win32":
        import psutil

        from tracker.platform.windows_process import owned_process

        process = owned_process(pid)
        if process is None:
            return None
        try:
            return datetime.fromtimestamp(process.create_time(), UTC), subprocess.list2cmdline(process.cmdline())
        except psutil.Error:
            return None
    out = _ps("-o", "lstart=", "-o", "command=", "-p", str(pid))
    if not out or not out.strip():
        return None
    words = out.strip().split(None, 5)
    if len(words) < 6:
        return None
    return _parse_lstart(" ".join(words[:5])), words[5]


def is_run(pid: int, run_id: int, proc_started_at: datetime | None, *, data_dir: Path | None = None) -> bool:
    """Whether `pid` is still run `run_id`'s trampoline."""
    if sys.platform == "win32":
        from tracker.platform.windows_process import owned_process

        return owned_process(pid, run_id=run_id, started=proc_started_at, data_dir=data_dir) is not None
    found = identity(pid)
    if found is None:
        return False
    began, line = found
    if not child.marks_run(line, run_id):
        return False
    if proc_started_at is None or began is None:
        return True
    return abs((began - proc_started_at).total_seconds()) <= 1


def find_run(run_id: int, *, data_dir: Path | None = None) -> int | None:
    """The PID of run `run_id`'s trampoline, by its marker, for a run whose PID was
    never recorded (the supervisor died between the spawn and the write)."""
    if sys.platform == "win32":
        import psutil

        from tracker.platform.windows_process import owned_process

        matches = [process.pid for process in psutil.process_iter()
                   if owned_process(process.pid, run_id=run_id, data_dir=data_dir) is not None]
        if len(matches) > 1:
            raise OSError(f"more than one process claims supervised run {run_id}")
        return matches[0] if matches else None
    out = _ps("-axo", "pid=,command=")
    for line in (out or "").splitlines():
        pid, _, rest = line.strip().partition(" ")
        if pid.isdigit() and child.marks_run(rest, run_id):
            return int(pid)
    return None


def group_alive(pgid: int) -> bool:
    if sys.platform == "win32":
        from tracker.platform.windows_process import owned_process

        return owned_process(pgid) is not None
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_group(pgid: int, signum: int) -> bool:
    if sys.platform == "win32":
        from tracker.platform.windows_process import owned_process, request_interrupt, terminate

        process = owned_process(pgid)
        if process is None:
            return False
        return request_interrupt(process) if signum in (signal.SIGTERM, signal.SIGINT) else terminate(process)
    try:
        os.killpg(pgid, signum)
    except ProcessLookupError:
        return False
    return True


async def stop_group(
    pgid: int,
    grace_seconds: float,
    *,
    reap: Callable[[], object] | None = None,
    poll_seconds: float = 0.05,
    run_id: int | None = None,
    proc_started_at: datetime | None = None,
    data_dir: Path | None = None,
) -> str:
    """Request a stop, allow `grace_seconds` of awake time, then end containment.

    `reap` collects our own child, which would otherwise linger as a zombie and
    keep the group alive. Returns "gone", "terminated" or "killed"."""

    if sys.platform == "win32":
        from tracker.platform.windows_process import owned_process, request_interrupt, terminate

        process = owned_process(pgid, run_id=run_id, started=proc_started_at, data_dir=data_dir)
        if process is None:
            return "gone"
        # Keep this process's kernel start time even when the database row has
        # not recorded one yet, so escalation cannot follow a recycled PID.
        expected = datetime.fromtimestamp(process.create_time(), UTC)
        await asyncio.to_thread(request_interrupt, process)
        deadline = awake_seconds() + grace_seconds
        while awake_seconds() < deadline:
            if reap is not None:
                reap()
            if owned_process(pgid, run_id=run_id, started=expected, data_dir=data_dir) is None:
                return "terminated"
            await asyncio.sleep(poll_seconds)
        if owned_process(pgid, run_id=run_id, started=expected, data_dir=data_dir) is None or not terminate(process):
            return "terminated"
        for _ in range(100):
            if reap is not None:
                reap()
            if not process.is_running():
                break
            await asyncio.sleep(poll_seconds)
        return "killed"

    def alive() -> bool:
        if reap is not None:
            reap()
        return group_alive(pgid)

    if not alive() or not signal_group(pgid, signal.SIGTERM):
        return "gone"
    deadline = awake_seconds() + grace_seconds
    while awake_seconds() < deadline:
        if not alive():
            return "terminated"
        await asyncio.sleep(poll_seconds)
    signal_group(pgid, signal.SIGKILL)
    for _ in range(100):
        if not alive():
            break
        await asyncio.sleep(poll_seconds)
    return "killed"


def start_service(argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], log: Path) -> subprocess.Popen:
    """Start a service owned by the supervisor, with output appended to `log`.

    POSIX shares the supervisor's process group. Windows uses a contained
    trampoline watching a pinned supervisor handle, so an abrupt parent exit
    also ends the service and its descendants.
    """
    fd = logs.open_append(log)
    try:
        environment = dict(env)
        options: dict = {}
        arguments = list(argv)
        if sys.platform == "win32":
            import psutil

            from tracker.platform.windows_process import popen_options

            arguments = [sys.executable, "-m", child.MARKER, "--run", "0", "--parent-pid", str(os.getpid()),
                         "--parent-start", str(psutil.Process().create_time()), "--", *arguments]
            options = popen_options(sys.executable, environment)
        return subprocess.Popen(  # noqa: S603 - a fixed command, never user input
            arguments, cwd=cwd, env=environment, stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, **options,
        )
    finally:
        os.close(fd)

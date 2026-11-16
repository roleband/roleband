"""The embedded Postgres clusters running on this machine, who holds each, and
a way to stop the ones nobody holds any more.

Every process that opens an embedded cluster records its PID in the cluster's
`.handle_pids.json` and removes it when it exits. The server itself stays up
after its last holder leaves (`DEFAULT_CLEANUP_MODE`), as the app needs, so a
throwaway cluster a test run or a `ROLEBAND_PGDATA` command started outlives
it. Each running cluster holds a System V shared memory segment, and a machine
allows only so many (`kern.sysv.shmmni`, 32 on a Mac): enough strays and the
next `initdb` fails for everyone.

    .venv/bin/python -m scripts.stray_clusters          # list them
    .venv/bin/python -m scripts.stray_clusters --stop   # stop the strays

A stray is a cluster in a throwaway place (the system's temporary folders or
`~/.cache`) whose recorded holders have all exited. Stopping one keeps its
data: the next command that opens it starts it again. Nothing else is stopped:
not a cluster with a live holder, not one elsewhere (a checkout's development
database idles with no holder), not one an app claimed (`<pgdata>.owner.json`),
and not one with no holder record (started with `pg_ctl` directly), whose
owner is unknown.
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import getpass
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

HOLDERS = ".handle_pids.json"


@dataclass(frozen=True)
class RunningCluster:
    pgdata: Path
    postmaster: int
    #: Holders still running, or None when the cluster keeps no holder record.
    holders: tuple[int, ...] | None
    #: Why the cluster is never stopped here, or None for a stray.
    kept: str | None

    @property
    def state(self) -> str:
        if self.holders:
            return "held"
        return "kept" if self.kept else "stray"


def throwaway_places() -> tuple[Path, ...]:
    """Where throwaway clusters live: the temporary folders and `~/.cache`."""
    places = {Path(tempfile.gettempdir()), Path("/tmp"), Path.home() / ".cache"}
    if sys.platform == "darwin":
        places.add(Path("/private/var/folders"))
    return tuple(sorted({place.resolve() for place in places}))


def recorded_holders(pgdata: Path) -> list[int] | None:
    """The PIDs the cluster's holder record names, or None without a record."""
    try:
        text = (pgdata / HOLDERS).read_text().strip()
    except OSError:
        return None
    try:
        pids = json.loads(text or "[]")
    except json.JSONDecodeError:
        return None
    return [pid for pid in pids if isinstance(pid, int)]


def live_holders(pgdata: Path, *, ignore: frozenset[int] = frozenset()) -> tuple[int, ...] | None:
    """The recorded holders still running, less `ignore`; None without a record."""
    import psutil  # a pgserver dependency: without it no cluster was started

    pids = recorded_holders(pgdata)
    if pids is None:
        return None
    return tuple(pid for pid in pids if pid not in ignore and psutil.pid_exists(pid))


def _why_kept(pgdata: Path, holders: tuple[int, ...] | None) -> str | None:
    from tracker.platform.embedded_db import owner_record

    if any(path.exists() for path in (owner_record(pgdata), owner_record(pgdata.resolve()))):
        return "an app's cluster"
    if holders is None:
        return "no holder record, owner unknown"
    if not any(pgdata.is_relative_to(place) for place in throwaway_places()):
        return "not in a throwaway place"
    return None


def _arguments(proc) -> list[str]:
    import psutil

    try:
        return proc.cmdline()
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied, SystemError):
        return []


def running_clusters() -> list[RunningCluster]:
    """Every cluster this account's postmasters serve now, read from the
    process table: a `postmaster.pid` can outlive its server."""
    import psutil

    me = getpass.getuser()
    found = []
    for proc in psutil.process_iter(["pid", "name", "username"]):
        if not (proc.info["name"] or "").startswith("postgres") or proc.info["username"] != me:
            continue
        arguments = _arguments(proc)
        # Only a postmaster is started with -D, never its backends.
        if "-D" not in arguments[:-1]:
            continue
        pgdata = Path(arguments[arguments.index("-D") + 1]).resolve()
        holders = live_holders(pgdata)
        found.append(RunningCluster(pgdata, proc.info["pid"], holders, _why_kept(pgdata, holders)))
    return sorted(found, key=lambda cluster: str(cluster.pgdata))


def stop_unheld(pgdata: Path, *, ignore: frozenset[int] = frozenset()) -> bool:
    """Stop the cluster at `pgdata` if no recorded holder but `ignore` runs.

    Checked and stopped under the lock every process takes to start or join a
    cluster, so none can join between the check and the stop. Returns whether
    it stopped the cluster; one with a holder, one with no holder record (its
    owner is unknown), or one not running is left alone.
    """
    from tracker.platform.embedded_db import _upstream, bundled_bin_dir

    lock = getattr(_upstream().PostgresServer, "_lock", None)
    with lock if lock is not None else contextlib.nullcontext():
        holders = live_holders(pgdata, ignore=ignore)
        if not (pgdata / "postmaster.pid").exists() or holders is None or holders:
            return False
        version = int((pgdata / "PG_VERSION").read_text().strip())
        pg_ctl = bundled_bin_dir(version) / "pg_ctl"
        done = subprocess.run(
            [str(pg_ctl), "-D", str(pgdata), "-w", "stop"], capture_output=True, text=True, check=False
        )
        if done.returncode != 0:
            raise RuntimeError(f"could not stop {pgdata}: {(done.stderr or '').strip()}")
        _retire_handle(pgdata)
        return True


def _retire_handle(pgdata: Path) -> None:
    """Drop this process's cached handle on a cluster stopped under it, as
    `stop_server` does, so a later start in this process starts it again
    instead of handing back a stopped server. Called with the lock held."""
    from tracker.platform.embedded_db import _upstream

    instances = getattr(_upstream().PostgresServer, "_instances", None)
    handle = instances.pop(pgdata.resolve(), None) if isinstance(instances, dict) else None
    if handle is not None:
        atexit.unregister(handle._cleanup)
        handle.global_process_id_list.get_and_remove(os.getpid())


def running_postmaster(pgdata: Path) -> bool:
    """Whether a server runs on `pgdata` now, by the PID its lock file names."""
    import psutil

    try:
        pid = int((pgdata / "postmaster.pid").read_text().split("\n", 1)[0])
    except (OSError, ValueError):
        return False
    return psutil.pid_exists(pid)


def stop_after_run(pgdata: Path, *, settle: float = 30.0) -> bool:
    """End a test run's hold on its cluster: stop it if it sits in a throwaway
    place and no process outside the run holds it.

    The run's own workers are its child processes; each leaves the holder
    record as it exits, so they are waited for (at most `settle` seconds)
    rather than counted. A cluster elsewhere, such as a checkout's development
    database, is left running whoever started it, and so is an app's."""
    import psutil

    pgdata = pgdata.resolve()
    if not running_postmaster(pgdata) or _why_kept(pgdata, ()) is not None:
        return False
    me = psutil.Process()
    deadline = time.monotonic() + settle
    while time.monotonic() < deadline:
        workers = {child.pid for child in me.children(recursive=True)}
        if not workers.intersection(live_holders(pgdata) or ()):
            break
        time.sleep(0.1)
    return stop_unheld(pgdata, ignore=frozenset({os.getpid()}))


def _home(path: Path) -> str:
    home = str(Path.home().resolve())
    return "~" + str(path)[len(home):] if str(path).startswith(home + "/") else str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--stop", action="store_true", help="stop each stray cluster")
    args = parser.parse_args(argv)

    clusters = running_clusters()
    for cluster in clusters:
        if cluster.state == "held":
            detail = "holders " + ", ".join(map(str, cluster.holders or ()))
        else:
            detail = cluster.kept or "every holder has exited"
        print(f"{cluster.state:5}  postmaster {cluster.postmaster:<6}  {_home(cluster.pgdata)}  ({detail})")
    strays = [cluster for cluster in clusters if cluster.state == "stray"]
    print(f"{len(clusters)} running, {len(strays)} stray")
    if not args.stop:
        return 0
    failed = 0
    for cluster in strays:
        try:
            stopped = stop_unheld(cluster.pgdata)
        except (OSError, RuntimeError, ValueError) as exc:
            failed += 1
            print(f"not stopped: {exc}", file=sys.stderr)
            continue
        print(f"{'stopped' if stopped else 'left (a holder joined)'}: {_home(cluster.pgdata)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

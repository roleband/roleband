"""Authenticated Windows embedded PostgreSQL initialization and endpoint ownership."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path

import psutil

from tracker.platform import filelock
from tracker.platform.windows_private import native_path, private_directory, require_private
from tracker.platform.windows_process import CANCELLABLE_ENV

if sys.platform != "win32":
    raise ImportError("Windows embedded database requires Windows")

_HBA = "host all all 127.0.0.1/32 scram-sha-256\n"
_RESERVED_SETTINGS = {"data_directory", "config_file", "hba_file", "listen_addresses", "port", "password_encryption"}
logger = logging.getLogger("tracker.platform.embedded_db")


class WindowsDbError(RuntimeError):
    """A Windows cluster or endpoint cannot safely be opened."""


def _write(path: Path, content: str) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _run(bin_dir: Path, tool: str, *args: str) -> None:
    # pg_ctl's server inherits output handles. Files let pg_ctl finish without
    # waiting for the lifetime of the detached postmaster's inherited pipe.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(
            [native_path(bin_dir / f"{tool}.exe"), *args], stdout=output, stderr=output,
            timeout=120, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            output.seek(0)
            detail = output.read().decode("utf-8", errors="replace")[-1500:]
            raise WindowsDbError(f"{tool} failed: {detail}")


def verified_port(pgdata: Path, bin_dir: Path) -> int:
    """Verify the pidfile against the owned binary, process start and TCP listener."""
    try:
        lines = (pgdata / "postmaster.pid").read_text(encoding="utf-8").splitlines()
        pid, recorded_path, started, port = lines[:4]
        process = psutil.Process(int(pid))
        arguments = process.cmdline()
        owned = (
            Path(recorded_path).resolve() == pgdata.resolve()
            and Path(process.exe()).resolve() == (bin_dir / "postgres.exe").resolve()
            and process.username() == psutil.Process().username()
            and abs(process.create_time() - int(started)) < 3
            and "-D" in arguments[:-1]
            and Path(arguments[arguments.index("-D") + 1]).resolve() == pgdata.resolve()
            and lines[5] == "127.0.0.1"
            and lines[7].strip() == "ready"
        )
        listeners = [
            connection for connection in psutil.net_connections(kind="tcp")
            if connection.status == psutil.CONN_LISTEN and connection.laddr.port == int(port)
        ]
        if not owned or not listeners or any(
            connection.pid != process.pid or connection.laddr.ip != "127.0.0.1"
            for connection in listeners
        ):
            raise WindowsDbError("database endpoint does not belong to the expected postmaster")
        return int(port)
    except (OSError, ValueError, IndexError, psutil.Error) as exc:
        raise WindowsDbError(f"cannot verify the database process at {pgdata}") from exc


def _retire_dead_pid(pgdata: Path) -> bool:
    path = pgdata / "postmaster.pid"
    require_private(path)
    original = path.read_bytes()
    try:
        if len(original) > 8192:
            raise ValueError("oversized pidfile")
        lines = original.decode("utf-8").splitlines()
        pid, recorded_path, started = int(lines[0]), Path(lines[1]), int(lines[2])
        if pid <= 0 or started <= 0 or recorded_path.resolve() != pgdata.resolve():
            raise ValueError("invalid database identity")
        try:
            process = psutil.Process(pid)
            if abs(process.create_time() - started) < 3:
                return False
        except psutil.NoSuchProcess:
            pass
        # A dead process record does not prove that no other postmaster owns
        # the directory. Inspect parsed -D arguments before allowing a start.
        for candidate in psutil.process_iter(["name"]):
            if (candidate.info["name"] or "").lower() != "postgres.exe":
                continue
            try:
                arguments = candidate.cmdline()
                if "-D" in arguments[:-1] and Path(arguments[arguments.index("-D") + 1]).resolve() == pgdata.resolve():
                    raise WindowsDbError("a live database process owns the directory despite its stale pidfile")
            except psutil.NoSuchProcess:
                continue
        if path.read_bytes() != original:
            raise WindowsDbError("database pidfile changed during ownership verification")
        retained = path.with_name("postmaster.pid.stale-" + uuid.uuid4().hex)
        path.rename(retained)
        logger.info("retained dead database process record at %s", retained)
        return True
    except (OSError, ValueError, IndexError, psutil.Error) as exc:
        raise WindowsDbError("cannot establish that the recorded database process is dead") from exc


def _initialize(pgdata: Path, auth: Path, bin_dir: Path, version: int, locale: str) -> None:
    marker = auth / "cluster.json"
    passfile = auth / "pgpass.conf"
    if (pgdata / "PG_VERSION").exists():
        try:
            require_private(pgdata)
            require_private(marker)
            require_private(passfile)
            record = json.loads(marker.read_text(encoding="utf-8"))
            valid = record == {"format": 1, "pgdata": str(pgdata), "version": version}
            valid = valid and (pgdata / "PG_VERSION").read_text().strip() == str(version)
            valid = valid and (pgdata / "pg_hba.conf").read_text(encoding="utf-8") == _HBA
        except (OSError, ValueError) as exc:
            raise WindowsDbError("existing Windows cluster has no verified SCRAM credentials") from exc
        if not valid:
            raise WindowsDbError("existing Windows cluster has unsafe authentication or incompatible identity")
        return
    if pgdata.exists() and any(pgdata.iterdir()):
        raise WindowsDbError("incomplete Windows cluster is preserved; choose fresh storage for a new trial")
    private_directory(pgdata)
    # A marker belongs to a particular initialized cluster. Its presence beside
    # a missing cluster is a recovery case, never a reason to generate new data.
    if marker.exists() or passfile.exists():
        raise WindowsDbError("Windows cluster credentials already exist; recover the original cluster")
    password = secrets.token_urlsafe(48)
    _write(passfile, f"127.0.0.1:*:*:postgres:{password}\n")
    transient = auth / "initdb-password"
    _write(transient, password + "\n")
    try:
        _run(
            bin_dir, "initdb", "-D", native_path(pgdata), "-U", "postgres", "--encoding=UTF8",
            f"--locale={locale}", "--auth=scram-sha-256", f"--pwfile={native_path(transient)}",
        )
    finally:
        transient.unlink(missing_ok=True)
    _write(pgdata / "pg_hba.conf", _HBA)
    with (pgdata / "postgresql.conf").open("a", encoding="utf-8") as config:
        config.write("\ninclude = 'roleband-runtime.conf'\n")
    _write(marker, json.dumps({"format": 1, "pgdata": str(pgdata), "version": version}) + "\n")


def ensure_cluster(
    pgdata: Path, bin_dir: Path, version: int, locale: str, settings: Mapping[str, str],
) -> tuple[int, Path]:
    """Initialize once under an account-private lock, then start or verify the server."""
    auth = pgdata.parent / f"{pgdata.name}.auth"
    private_directory(auth)
    with (auth / "startup.lock").open("a+b") as lock:
        filelock.lock(lock)
        try:
            if os.environ.get(CANCELLABLE_ENV) == "1" and not (pgdata / "postmaster.pid").exists():
                raise WindowsDbError("start PostgreSQL in the engine host before launching a cancellable process")
            _initialize(pgdata, auth, bin_dir, version, locale)
            if (pgdata / "postmaster.pid").exists():
                if os.environ.get(CANCELLABLE_ENV) == "1" or not _retire_dead_pid(pgdata):
                    return verified_port(pgdata, bin_dir), Path(native_path(auth / "pgpass.conf"))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            config = {
                **settings, "listen_addresses": "127.0.0.1", "port": str(port),
                "password_encryption": "scram-sha-256", "hba_file": native_path(pgdata / "pg_hba.conf"),
            }
            if _RESERVED_SETTINGS.intersection(settings):
                raise WindowsDbError("server settings cannot override database identity or authentication")
            lines = []
            for name, value in config.items():
                if not re.fullmatch(r"[a-z_][a-z0-9_.]*", name) or any(c in value for c in "\r\n\x00"):
                    raise WindowsDbError("invalid PostgreSQL server setting")
                escaped = value.replace("\\", "\\\\").replace("'", "''")
                lines.append(f"{name} = '{escaped}'\n")
            _write(pgdata / "roleband-runtime.conf", "".join(lines))
            logger.info("starting embedded Postgres at %s with %s", pgdata,
                        " ".join(f"{name}={value}" for name, value in settings.items()) or "stock settings")
            native_pgdata = native_path(pgdata)
            # Crash recovery fsyncs PGDATA. An open log there can cause Windows
            # sharing violations and exhaust the database's startup deadline.
            log = auth / "postgres.log"
            if log.exists():
                require_private(log)
            _run(bin_dir, "pg_ctl", "-D", native_pgdata, "-w", "-t", "30", "-l", native_path(auth) + "/postgres.log", "start")
            return verified_port(pgdata, bin_dir), Path(native_path(auth / "pgpass.conf"))
        finally:
            filelock.unlock(lock)


def stop_cluster(pgdata: Path, bin_dir: Path) -> None:
    """Stop only a verified postmaster, with narrow-argv-compatible storage paths."""
    verified_port(pgdata, bin_dir)
    _run(bin_dir, "pg_ctl", "-D", native_path(pgdata), "-w", "stop")

"""Windows clusters authenticate real clients and preserve history across restarts."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.embedded_utils import destroy, psql
from tracker.platform.embedded_db import EmbeddedDbError, ensure_server, stop_server

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows embedded database requires Windows")


@pytest.fixture
def server(tmp_path):
    server = ensure_server(tmp_path / "account data" / "db", database="probe")
    try:
        yield server
    finally:
        destroy(server.pgdata)


def test_scram_requires_the_private_password_and_keeps_it_out_of_urls(server, tmp_path, monkeypatch):
    import psycopg2

    from tracker.platform.windows_private import require_private

    auth = server.pgdata.parent / "db.auth"
    passfile = auth / "pgpass.conf"
    require_private(auth)
    require_private(server.pgdata)
    require_private(passfile)
    password = passfile.read_text().strip().rsplit(":", 1)[1]
    assert len(password) >= 48
    assert password not in repr(server)
    assert password not in server.dsn()
    assert password not in server.uri()
    assert not (auth / "initdb-password").exists()
    assert psql(server, "SHOW password_encryption") == "scram-sha-256"
    assert psql(server, "SELECT DISTINCT auth_method FROM pg_hba_file_rules") == "scram-sha-256"
    assert psql(server, "SELECT rolpassword LIKE 'SCRAM-SHA-256$%' FROM pg_authid WHERE rolname='postgres'") == "t"
    monkeypatch.delenv("PGPASSWORD", raising=False)
    parts = urlsplit(server.dsn())
    args = {"host": parts.hostname, "port": parts.port, "user": "postgres", "dbname": "probe", "connect_timeout": 3}
    with pytest.raises(psycopg2.OperationalError, match="no password supplied"):
        psycopg2.connect(**args, passfile=str(tmp_path / "absent"))
    with pytest.raises(psycopg2.OperationalError, match="password authentication failed"):
        psycopg2.connect(**args, password="deliberately-wrong")


def test_a_password_set_for_another_postgresql_does_not_reach_the_embedded_one(tmp_path, monkeypatch):
    """libpq prefers PGPASSWORD to the password file; a machine with its own PostgreSQL often sets it."""
    monkeypatch.setenv("PGPASSWORD", "root")
    monkeypatch.setenv("PGOPTIONS", "-c statement_timeout=1")
    server = ensure_server(tmp_path / "account data" / "db", database="probe")
    try:
        assert "PGPASSWORD" not in os.environ and "PGOPTIONS" not in os.environ
        assert psql(server, "SELECT current_setting('statement_timeout')") == "0"
    finally:
        destroy(server.pgdata)


def test_sqlalchemy_direct_asyncpg_and_psycopg2_share_the_authenticated_database(server):
    import asyncpg
    import psycopg2
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine

    from tracker.platform.embedded_db import asyncpg_arguments

    psql(server, "CREATE TABLE sentinel (value text); INSERT INTO sentinel VALUES ('preserved history')")

    async def query():
        engine = create_async_engine(server.uri())
        try:
            async with engine.connect() as connection:
                assert (await connection.execute(text("SELECT value FROM sentinel"))).scalar_one() == "preserved history"
        finally:
            await engine.dispose()
        connection = await asyncpg.connect(**asyncpg_arguments(make_url(server.uri())))
        try:
            assert await connection.fetchval("SELECT value FROM sentinel") == "preserved history"
            received = asyncio.get_running_loop().create_future()
            await connection.add_listener("roleband_probe", lambda *args: received.set_result(args[-1]))
            notifier = await asyncpg.connect(server.dsn())
            try:
                await notifier.execute("SELECT pg_notify('roleband_probe', 'authenticated notification')")
                assert await asyncio.wait_for(received, timeout=5) == "authenticated notification"
            finally:
                await notifier.close()
        finally:
            await connection.close()

    asyncio.run(query())
    with psycopg2.connect(server.dsn()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT value FROM sentinel")
        assert cursor.fetchone() == ("preserved history",)


def test_restart_keeps_credentials_and_history(server):
    auth = server.pgdata.parent / "db.auth"
    credentials = (auth / "pgpass.conf").read_bytes()
    psql(server, "CREATE TABLE history (value text); INSERT INTO history VALUES ('before restart')")
    assert stop_server(server.pgdata)
    restarted = ensure_server(server.pgdata, database=server.database)
    assert psql(restarted, "SELECT value FROM history") == "before restart"
    assert (auth / "pgpass.conf").read_bytes() == credentials


def test_dump_restore_preserves_unicode_and_all_dated_history(server, tmp_path):
    from tracker.platform.backups import dump_database
    from tracker.platform.windows_private import require_private

    psql(server, "CREATE TABLE jobs (id integer, title text);"
         "INSERT INTO jobs VALUES (1, 'Éclair'), (2, '中文');"
         "CREATE TABLE job_observations (job_id integer, observed_on date);"
         "INSERT INTO job_observations VALUES (1,'2025-01-01'), (1,'2026-11-04'), (2,'2026-11-04')")
    archive = dump_database(server, tmp_path / "backups")
    require_private(archive.parent)
    require_private(archive)
    require_private(archive.parent / "monthly" / archive.name)
    target = ensure_server(tmp_path / "restored", database="probe")
    try:
        subprocess.run([
            str(target.tool("pg_restore")), "--exit-on-error", "--no-owner", "-d", target.dsn(), str(archive),
        ], check=True, capture_output=True)
        assert psql(target, "SELECT string_agg(title, ',' ORDER BY id) FROM jobs") == "Éclair,中文"
        assert psql(target, "SELECT count(*) FROM job_observations") == "3"
        assert psql(target, "SELECT min(observed_on) FROM job_observations") == "2025-01-01"
        assert psql(target, "INSERT INTO jobs VALUES (3,'after restore') RETURNING id").splitlines()[0] == "3"
    finally:
        destroy(target.pgdata)


def test_unicode_encoding_case_matching_and_search_are_explicit(server):
    assert psql(server, "SHOW server_encoding") == "UTF8"
    assert psql(server, "SELECT datcollate FROM pg_database WHERE datname=current_database()") == "en_US.UTF-8"
    assert psql(server, "SELECT 'Éclair' ILIKE 'écl%' AND '中文' LIKE '中%'") == "t"
    assert psql(server, "SELECT to_tsvector('simple','Éclair 中文') @@ plainto_tsquery('simple','éclair')") == "t"
    assert psql(
        server, "SELECT string_agg(value, ',' ORDER BY value)"
        " FROM (VALUES ('Zebra'),('Árbol'),('Éclair'),('中文')) AS words(value)",
    ) == "Árbol,Éclair,Zebra,中文"


def test_c_locale_is_an_explicit_choice_with_ascii_case_rules(tmp_path):
    server = ensure_server(tmp_path / "ascii", database="probe", locale="C")
    try:
        assert psql(server, "SELECT 'Éclair' ILIKE 'écl%'") == "f"
        assert psql(server, "SHOW server_encoding") == "UTF8"
    finally:
        destroy(server.pgdata)


def test_psql_preserves_multistatement_failure_atomicity_and_unicode_literals(server):
    psql(server, "CREATE TABLE atomic_write (value text)")
    with pytest.raises(EmbeddedDbError):
        psql(server, "INSERT INTO atomic_write VALUES ('Éclair; 中文'); SELECT definitely_missing_column")
    assert psql(server, "SELECT count(*) FROM atomic_write") == "0"
    assert psql(server, "SELECT 'Éclair; 中文'") == "Éclair; 中文"


@pytest.mark.parametrize("copy_runtime", [False, True])
def test_non_latin_storage_paths_start_query_and_stop(tmp_path, monkeypatch, copy_runtime):
    if copy_runtime:
        import shutil

        from pixeltable_pgserver.utils import POSTGRES_VERSIONS

        from tracker.platform.embedded_db import bundled_bin_dir
        from tracker.platform.windows_private import private_directory

        # pytest's folders admit their owner, which an elevated run makes the Administrators group, and
        # PostgreSQL drops that group from its own token; the copy goes where this account is named.
        runtime = tmp_path / "运行时"
        private_directory(runtime)
        shutil.copytree(bundled_bin_dir().parent, runtime, dirs_exist_ok=True)
        monkeypatch.setitem(POSTGRES_VERSIONS, 16, runtime / "bin")
    server = ensure_server(tmp_path / "中文資料" / "db", database="probe")
    try:
        assert psql(server, "SELECT '中文'") == "中文"
    finally:
        destroy(server.pgdata)


def test_a_first_setup_whose_initdb_failed_is_kept_aside_and_the_next_start_begins_again(tmp_path, monkeypatch):
    run = subprocess.run

    def fail_initdb(argv, **kwargs):
        if Path(argv[0]).name == "initdb.exe":
            (pgdata / "half-made").write_text("left by initdb", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 1)
        return run(argv, **kwargs)

    pgdata = tmp_path / "first-setup" / "db"
    auth = pgdata.parent / "db.auth"
    monkeypatch.setattr(subprocess, "run", fail_initdb)
    with pytest.raises(EmbeddedDbError, match="initdb failed"):
        ensure_server(pgdata, database="probe")
    abandoned = (auth / "pgpass.conf").read_bytes()
    assert not (auth / "initdb-password").exists()
    assert not (auth / "cluster.json").exists()
    monkeypatch.setattr(subprocess, "run", run)
    server = ensure_server(pgdata, database="probe")
    try:
        assert psql(server, "SELECT 1") == "1"
        assert (auth / "cluster.json").exists()
        assert (auth / "pgpass.conf").read_bytes() != abandoned
        [kept_password] = auth.glob("pgpass.conf.unfinished-*")
        assert kept_password.read_bytes() == abandoned
        [kept_folder] = pgdata.parent.glob("db.unfinished-*")
        assert (kept_folder / "half-made").read_text(encoding="utf-8") == "left by initdb"
        assert kept_password.name.removeprefix("pgpass.conf.") == kept_folder.name.removeprefix("db.")
    finally:
        destroy(server.pgdata)


class Interrupted(BaseException):
    """The person quits while setup runs."""


def test_a_first_setup_stopped_after_initdb_but_before_its_record_is_kept_aside(tmp_path, monkeypatch):
    from tracker.platform import windows_storage

    def interrupted(*args, **kwargs):
        raise Interrupted

    pgdata = tmp_path / "first-setup" / "db"
    auth = pgdata.parent / "db.auth"
    recorded = windows_storage.metadata
    monkeypatch.setattr(windows_storage, "metadata", interrupted)
    with pytest.raises(Interrupted):
        ensure_server(pgdata, database="probe")
    assert (pgdata / "PG_VERSION").exists()
    assert not (auth / "cluster.json").exists()
    monkeypatch.setattr(windows_storage, "metadata", recorded)
    server = ensure_server(pgdata, database="probe")
    try:
        assert psql(server, "SELECT 1") == "1"
        [kept_folder] = pgdata.parent.glob("db.unfinished-*")
        assert (kept_folder / "PG_VERSION").exists()
        assert len(list(auth.glob("pgpass.conf.unfinished-*"))) == 1
    finally:
        destroy(server.pgdata)


def test_a_cluster_that_has_run_and_lost_its_record_is_refused_and_left_in_place(tmp_path):
    pgdata = tmp_path / "used" / "db"
    auth = pgdata.parent / "db.auth"
    server = ensure_server(pgdata, database="probe")
    assert stop_server(server.pgdata)
    assert (pgdata / "postmaster.opts").exists()
    record = auth / "cluster.json"
    lost = record.with_name("cluster.lost")
    record.rename(lost)
    try:
        with pytest.raises(EmbeddedDbError, match="no verified SCRAM credentials"):
            ensure_server(pgdata, database="probe")
        assert (pgdata / "PG_VERSION").exists()
        assert (auth / "pgpass.conf").exists()
        assert not list(auth.glob("*.unfinished-*"))
        assert not list(pgdata.parent.glob("db.unfinished-*"))
    finally:
        lost.rename(record)
        destroy(pgdata)


def test_a_finished_cluster_whose_data_folder_is_missing_is_still_refused(tmp_path):
    pgdata = tmp_path / "finished" / "db"
    auth = pgdata.parent / "db.auth"
    server = ensure_server(pgdata, database="probe")
    assert stop_server(server.pgdata)
    password = (auth / "pgpass.conf").read_bytes()
    moved = pgdata.with_name("db.elsewhere")
    pgdata.rename(moved)
    try:
        with pytest.raises(EmbeddedDbError, match="recover the original cluster"):
            ensure_server(pgdata, database="probe")
        assert (auth / "pgpass.conf").read_bytes() == password
        assert not list(auth.glob("*.unfinished-*"))
        assert not list(pgdata.parent.glob("db.unfinished-*"))
    finally:
        if pgdata.exists() and not any(pgdata.iterdir()):
            pgdata.rmdir()
        moved.rename(pgdata)
        destroy(pgdata)


def test_existing_trust_cluster_is_refused_without_rewriting_its_files(server):
    hba = server.pgdata / "pg_hba.conf"
    original = hba.read_bytes()
    unsafe = b"host all all 127.0.0.1/32 trust\n"
    hba.write_bytes(unsafe)
    try:
        with pytest.raises(EmbeddedDbError, match="unsafe authentication"):
            ensure_server(server.pgdata, database="probe")
        assert hba.read_bytes() == unsafe
    finally:
        hba.write_bytes(original)


def test_foreign_listener_is_refused_before_any_connection(server):
    import psutil

    assert stop_server(server.pgdata)
    pidfile = server.pgdata / "postmaster.pid"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        pidfile.write_text(
            f"{os.getpid()}\n{server.pgdata}\n{int(psutil.Process().create_time())}\n{port}\n\n127.0.0.1\n\nready\n",
            encoding="utf-8",
        )
        try:
            with pytest.raises(EmbeddedDbError, match="expected postmaster"):
                ensure_server(server.pgdata, database="probe")
            listener.setblocking(False)
            with pytest.raises(BlockingIOError):
                listener.accept()
            assert pidfile.exists()
        finally:
            pidfile.unlink()


def test_missing_credentials_refuse_existing_cluster_without_generating_a_password(server):
    marker = server.pgdata.parent / "db.auth" / "cluster.json"
    saved = marker.read_bytes()
    marker.unlink()
    try:
        with pytest.raises(EmbeddedDbError, match="no verified SCRAM credentials"):
            ensure_server(server.pgdata, database="probe")
        assert not marker.exists()
    finally:
        marker.write_bytes(saved)


def test_private_storage_rejects_an_acl_granting_everyone_access(tmp_path):
    from tracker.platform.windows_private import (
        PrivatePathError,
        private_directory,
        require_private,
    )

    private = tmp_path / "private"
    private_directory(private)
    subprocess.run(["icacls", str(private), "/grant", "*S-1-1-0:(R)"], check=True, capture_output=True)
    with pytest.raises(PrivatePathError, match="another account"):
        require_private(private)


def test_concurrent_first_launch_agrees_on_one_cluster_and_credential(tmp_path):
    pgdata = tmp_path / "concurrent"
    script = tmp_path / "launch.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\nfrom tracker.platform.embedded_db import ensure_server\n"
        "print(ensure_server(Path(sys.argv[1]), database='probe').dsn())\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    children = [subprocess.Popen(
        [sys.executable, str(script), str(pgdata)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    ) for _ in range(2)]
    try:
        results = [child.communicate(timeout=120) for child in children]
        for child, (stdout, stderr) in zip(children, results, strict=True):
            assert child.returncode == 0, stderr
            assert parse_qs(urlsplit(stdout.strip()).query)["passfile"]
        assert results[0][0] == results[1][0]
        record = json.loads((pgdata.parent / "concurrent.auth" / "cluster.json").read_text())
        assert record["pgdata"] == str(pgdata.resolve())
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
        destroy(pgdata)

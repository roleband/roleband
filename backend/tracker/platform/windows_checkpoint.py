"""Publish private recovery checkpoints only after a scratch restore matches."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection, cursor

from tracker.platform.embedded_db import EmbeddedServer, ensure_server, stop_server

if sys.platform != "win32":
    raise ImportError("Windows recovery checkpoints require Windows")

from tracker.platform.windows_fs import checked_path

MANIFEST_LIMIT = 2 * 1024 * 1024


class CheckpointError(RuntimeError):
    """A checkpoint cannot establish a safe recovery copy."""


class _DigestWriter:
    def __init__(self) -> None:
        self.digest = hashlib.sha256()

    def write(self, data: bytes) -> int:
        self.digest.update(data)
        return len(data)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _ordinary(path: Path, *, directory: bool = False) -> None:
    from tracker.platform.windows_private import require_private

    if path.is_dir() != directory or not (path.is_dir() or path.is_file()):
        raise CheckpointError("Checkpoint storage is not an ordinary file or directory")
    require_private(path)


def _separate(left: Path, right: Path) -> None:
    if left.is_relative_to(right) or right.is_relative_to(left):
        raise CheckpointError("Recovery storage must be separate from database and checkpoint storage")


def _connect(server: EmbeddedServer) -> connection:
    conn = psycopg2.connect(server.dsn(), connect_timeout=5)
    try:
        conn.set_client_encoding("UTF8")
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'; SET DateStyle = 'ISO, YMD'; SET extra_float_digits = 3;"
                        " SET bytea_output = 'hex'; SET lock_timeout = '5s'; SET statement_timeout = '30min'")
            cur.execute("SELECT current_database(), current_setting('data_directory'), current_setting('server_version_num')")
            database, data, version = cur.fetchone()
            if database != server.database or Path(data).resolve() != server.pgdata.resolve() or int(version) // 10000 != 16:
                raise CheckpointError("Recovery connection does not identify the expected PG16 database")
        return conn
    except BaseException:
        conn.close()
        raise


def _sequences(cur: cursor) -> list[list[Any]]:
    cur.execute("SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
                " WHERE c.relkind='S' AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' ORDER BY 1,2")
    result = []
    for schema, name in cur.fetchall():
        cur.execute(sql.SQL("SELECT last_value, is_called FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(name)))
        value, called = cur.fetchone()
        result.append([schema, name, value, called])
    return result


def _expression(cur: cursor, expression: str, schema: str, table: str) -> str:
    # Dump/restore can move array casts onto individual constants. PostgreSQL's
    # planner normalizes those expressions without executing the query.
    command = sql.SQL("EXPLAIN (VERBOSE, FORMAT JSON, COSTS FALSE) SELECT ({}) FROM ONLY {}.{}").format(
        sql.SQL(expression), sql.Identifier(schema), sql.Identifier(table),
    )
    cur.execute(command)
    output = cur.fetchone()[0][0]["Plan"].get("Output")
    if not isinstance(output, list) or len(output) != 1 or not isinstance(output[0], str):
        raise CheckpointError("Schema expression cannot be normalized for recovery verification")
    return output[0]


#: The one checkpoint purpose that may hold no roles yet: the engine takes it of its own
#: database before a migration, so it cannot be another database mistaken for this one.
PRE_MIGRATION = "pre-migration"


def _empty_history_allowed(manifest: dict[str, Any]) -> bool:
    return manifest.get("purpose") == PRE_MIGRATION


def _facts(conn: connection, *, empty_history: bool = False) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT n.nspname, c.relname, c.relkind FROM pg_class c"
                    " JOIN pg_namespace n ON n.oid=c.relnamespace"
                    " WHERE c.relkind IN ('r','p','m','f') AND n.nspname !~ '^pg_'"
                    " AND n.nspname <> 'information_schema' ORDER BY 1,2")
        relations = cur.fetchall()
        names = {(schema, name) for schema, name, _kind in relations}
        if not {('public', 'jobs'), ('public', 'job_observations'), ('public', 'alembic_version')} <= names:
            raise CheckpointError("Recovery checkpoint requires the schema, jobs and observation history")
        if any(kind == 'f' for _schema, _name, kind in relations):
            raise CheckpointError("Foreign-table data cannot be verified by this checkpoint")
        tables = []
        for schema, name, kind in relations:
            identifier = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))
            cur.execute(sql.SQL("SELECT count(*) FROM ONLY {}").format(identifier))
            rows = cur.fetchone()[0]
            writer = _DigestWriter()
            command = sql.SQL("COPY (SELECT to_jsonb(t)::text FROM ONLY {} AS t"
                              " ORDER BY to_jsonb(t)::text COLLATE \"C\") TO STDOUT WITH (ENCODING 'UTF8')").format(identifier)
            cur.copy_expert(command.as_string(conn), writer)
            cur.execute("SELECT a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull,"
                        " a.attidentity, a.attgenerated, pg_get_expr(d.adbin,d.adrelid)"
                        " FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum"
                        " WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
                        (identifier.as_string(conn),))
            columns = cur.fetchall()
            tables.append({"schema": schema, "name": name, "kind": kind, "rows": rows,
                           "data_sha256": writer.digest.hexdigest(), "columns": columns})
        if not empty_history and next(table["rows"] for table in tables
                                      if (table["schema"], table["name"]) == ('public', 'jobs')) == 0:
            raise CheckpointError("An empty jobs table cannot establish a recovery checkpoint")
        cur.execute("SELECT version_num FROM public.alembic_version ORDER BY version_num")
        heads = [row[0] for row in cur.fetchall()]
        if not heads:
            raise CheckpointError("Recovery checkpoint has no schema revision")
        cur.execute("SELECT extname, extversion FROM pg_extension ORDER BY extname")
        extensions = cur.fetchall()
        cur.execute("SELECT n.nspname, t.relname, c.relname, pg_get_indexdef(c.oid,0,false),"
                    " pg_get_expr(i.indpred,i.indrelid,false) FROM pg_index i"
                    " JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_class t ON t.oid=i.indrelid"
                    " JOIN pg_namespace n ON n.oid=t.relnamespace"
                    " WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' ORDER BY 1,2,3")
        indexes = []
        for schema, table, name, definition, predicate in cur.fetchall():
            if predicate is not None:
                if not definition.endswith(" WHERE " + predicate):
                    raise CheckpointError("Partial index definition cannot be normalized for recovery verification")
                definition = definition[:-len(predicate)] + _expression(cur, predicate, schema, table)
            indexes.append([schema, table, name, definition])
        cur.execute("SELECT n.nspname, t.relname, c.conname, pg_get_constraintdef(c.oid,false), c.convalidated,"
                    " c.connoinherit, pg_get_expr(c.conbin,c.conrelid,false)"
                    " FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid"
                    " JOIN pg_namespace n ON n.oid=t.relnamespace"
                    " WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' ORDER BY 1,2,3")
        constraints = []
        for schema, table, name, definition, validated, no_inherit, expression in cur.fetchall():
            if expression is not None:
                definition = "CHECK (" + _expression(cur, expression, schema, table) + ")"
            constraints.append([schema, table, name, definition, validated, no_inherit])
        facts = {"tables": tables, "schema_heads": heads, "extensions": extensions,
                 "indexes": indexes, "constraints": constraints, "sequences": _sequences(cur)}
        # JSON normalization makes in-memory tuples and a persisted manifest identical.
        return json.loads(json.dumps(facts, ensure_ascii=False))


def same_facts(live: dict[str, Any], recorded: Any) -> bool:
    """Whether a database's facts are the ones a checkpoint recorded.

    Extensions are compared by name. A restore creates each at the runtime's default
    version while the database it was taken from keeps the version it was made with,
    so their versions differ after any runtime update that carries a newer one.
    """
    def comparable(facts: Any) -> Any:
        if not isinstance(facts, dict) or not isinstance(facts.get("extensions"), list):
            return facts
        return {**facts, "extensions": [entry[0] if isinstance(entry, list) and entry else entry
                                        for entry in facts["extensions"]]}

    return bool(comparable(live) == comparable(recorded))


def _run(server: EmbeddedServer, tool: str, *arguments: str) -> None:
    from tracker.platform.windows_private import native_path

    result = subprocess.run([native_path(server.tool(tool)), *arguments], capture_output=True, timeout=1800,
                            env={**os.environ, "PGCLIENTENCODING": "UTF8"},
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise CheckpointError(f"{tool} could not complete the recovery checkpoint")


def _archive(directory: Path, manifest: dict[str, Any]) -> Path:
    _ordinary(directory, directory=True)
    archive = directory / "database.dump"
    _ordinary(archive)
    if archive.stat().st_size != manifest.get("bytes") or _digest(archive) != manifest.get("sha256"):
        raise CheckpointError("Recovery archive checksum does not match")
    return archive


def verify_restored(server: EmbeddedServer, manifest: dict[str, Any]) -> None:
    with closing(_connect(server)) as conn:
        if not same_facts(_facts(conn, empty_history=_empty_history_allowed(manifest)), manifest["facts"]):
            raise CheckpointError("Restored checkpoint does not match its schema and history fingerprints")
        conn.rollback()
        conn.set_session(readonly=False)
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE roleband_restore_probe(value text);")
            cur.execute("INSERT INTO roleband_restore_probe VALUES (%s) RETURNING value", ("Recovery · 中文",))
            if cur.fetchone() != ("Recovery · 中文",):
                raise CheckpointError("Restored checkpoint did not pass its scratch write")
        conn.rollback()


def _restore(directory: Path, manifest: dict[str, Any], verification_state: Path,
             *, database: str = "roleband_restore_check") -> dict[str, Any]:
    from tracker.platform.windows_private import native_path, private_directory

    archive = _archive(directory, manifest)
    verification_state = checked_path(verification_state)
    _separate(verification_state, checked_path(directory))
    _separate(verification_state, checked_path(Path(manifest["source_pgdata"])))
    private_directory(verification_state, exist_ok=False)
    pgdata = verification_state / "db"
    try:
        server = ensure_server(pgdata, database=database, required_extensions=("vector", "pg_trgm"))
        _run(server, "pg_restore", "--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges",
             "-d", server.dsn(), native_path(archive))
        verify_restored(server, manifest)
        return {"verified": True, "verification_state": str(verification_state), "scratch_write": "rolled back"}
    finally:
        if (pgdata / "postmaster.pid").exists() and not stop_server(pgdata):
            raise CheckpointError("Recovery verification cluster did not confirm shutdown")


def create_checkpoint(server: EmbeddedServer, destination: Path, verification_state: Path,
                      *, purpose: str | None = None) -> Path:
    """Export one snapshot and publish only after restoring it into fresh storage."""
    from tracker.platform.windows_private import native_path, private_directory
    from tracker.platform.windows_storage import READER_CONTRACT, retained_profile

    destination, verification_state = checked_path(destination), checked_path(verification_state)
    _separate(destination, checked_path(server.pgdata))
    _separate(destination, verification_state)
    _separate(verification_state, checked_path(server.pgdata))
    if destination.exists() or verification_state.exists():
        raise FileExistsError("Choose fresh checkpoint and verification destinations")
    staged = destination.with_name(destination.name + ".partial-" + uuid.uuid4().hex)
    private_directory(staged, exist_ok=False)
    archive = staged / "database.dump"
    archive.touch(exist_ok=False)
    owner = server.pgdata.parent / f"{server.pgdata.name}.owner.json"
    profile = retained_profile(server.pgdata) if owner.exists() else None
    with closing(_connect(server)) as conn:
        facts = _facts(conn, empty_history=purpose == PRE_MIGRATION)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_export_snapshot()")
            snapshot = cur.fetchone()[0]
        _run(server, "pg_dump", "-d", server.dsn(), "--format=custom", "--snapshot", snapshot,
             "--file", native_path(archive))
        with conn.cursor() as cur:
            if _sequences(cur) != facts["sequences"]:
                raise CheckpointError("Sequences changed during export; quiesce writers before retrying")
    with archive.open("rb+") as stream:
        os.fsync(stream.fileno())
    manifest = {"format": 1, "postgres_major": 16, "source_database": server.database,
                "source_pgdata": str(server.pgdata.resolve()), "sha256": _digest(archive),
                "bytes": archive.stat().st_size, "facts": facts,
                "reader_contract": READER_CONTRACT, "retained_profile": profile}
    if purpose is not None:
        manifest["purpose"] = purpose
    if profile is not None and retained_profile(server.pgdata) != profile:
        raise CheckpointError("Retained credentials or key changed while building the checkpoint")
    manifest.update(_restore(staged, manifest, verification_state))
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    if len(encoded) > MANIFEST_LIMIT:
        raise CheckpointError("Recovery manifest exceeds its size limit")
    with (staged / "checkpoint.json").open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    _ordinary(staged / "checkpoint.json")
    staged.rename(destination)
    return destination


def intact(server: EmbeddedServer, directory: Path) -> dict[str, Any] | None:
    """The manifest of a published, verified checkpoint of this server's database whose archive is whole, or None:
    private ordinary storage, a manifest within its limit and an archive matching its digest and size."""
    try:
        directory = checked_path(directory)
        _ordinary(directory, directory=True)
        path = directory / "checkpoint.json"
        _ordinary(path)
        if path.stat().st_size > MANIFEST_LIMIT:
            return None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(manifest, dict) or manifest.get("format") != 1 or manifest.get("verified") is not True
                or manifest.get("source_database") != server.database
                or manifest.get("source_pgdata") != str(server.pgdata.resolve())):
            return None
        _archive(directory, manifest)
    except (OSError, ValueError, CheckpointError):
        return None
    return manifest


def still_matches(server: EmbeddedServer, directory: Path) -> bool:
    """Whether a published, verified checkpoint holds exactly what the live database holds now.

    Equal schema and history fingerprints, an intact archive and the same retained credentials
    make the checkpoint as good as a new one, without another export and scratch restore.
    """
    from tracker.platform.windows_storage import retained_profile

    manifest = intact(server, directory)
    if manifest is None:
        return False
    owner = server.pgdata.parent / f"{server.pgdata.name}.owner.json"
    if manifest.get("retained_profile") != (retained_profile(server.pgdata) if owner.exists() else None):
        return False
    with closing(_connect(server)) as conn:
        return same_facts(_facts(conn, empty_history=_empty_history_allowed(manifest)), manifest.get("facts"))


def verify_checkpoint(directory: Path, verification_state: Path) -> dict[str, Any]:
    """Recheck a published archive and restore it into a new stopped scratch cluster."""
    directory = checked_path(directory)
    _ordinary(directory, directory=True)
    path = directory / "checkpoint.json"
    _ordinary(path)
    if path.stat().st_size > MANIFEST_LIMIT:
        raise CheckpointError("Recovery manifest exceeds its size limit")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("format") != 1 or manifest.get("postgres_major") != 16
            or manifest.get("verified") is not True or not isinstance(manifest.get("facts"), dict)
            or not isinstance(manifest.get("source_pgdata"), str) or not Path(manifest["source_pgdata"]).is_absolute()):
        raise CheckpointError("Unsupported or incomplete recovery manifest")
    return _restore(directory, manifest, verification_state)

"""Build or recheck a private recovery checkpoint using explicit Windows paths."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create")
    create.add_argument("--pgdata", type=Path, required=True)
    create.add_argument("--database", required=True)
    create.add_argument("--destination", type=Path, required=True)
    create.add_argument("--verification-state", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--checkpoint", type=Path, required=True)
    verify.add_argument("--verification-state", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Recovery checkpoints require Windows")
    state = os.path.abspath(args.pgdata.parent if args.action == "create" else args.verification_state)
    os.environ.update(ROLEBAND_STATE_DIR=state, ROLEBAND_PGDATA=str(Path(state) / "db"),
                      ROLEBAND_CACHE_DIR=str(Path(state) / "cache"), ROLEBAND_PLUGINS_DIR=str(Path(state) / "plugins"),
                      ROLEBAND_SECRET_KEY_FILE=str(Path(state) / "secret.key"), ROLEBAND_DATABASE_URL="",
                      ROLEBAND_NO_USAGE_STATS="1")
    import psycopg2
    from sqlalchemy.engine import make_url

    from tracker.platform.embedded_db import claim_cluster, ensure_server, stop_server
    from tracker.platform.paths import within_installed_data
    from tracker.platform.windows_checkpoint import create_checkpoint, verify_checkpoint
    from tracker.platform.windows_leases import lifecycle_leases
    from tracker.platform.windows_private import require_private

    if args.action == "verify":
        print(json.dumps(verify_checkpoint(args.checkpoint, args.verification_state)))
        return
    pgdata = Path(os.path.abspath(args.pgdata))
    if pgdata.name != "db" or not (pgdata / "PG_VERSION").is_file():
        parser.error("Creation requires an existing app-owned state/db cluster")
    if within_installed_data(pgdata):
        parser.error("The Windows trial cannot reach an installed app's data")
    require_private(pgdata.parent)
    require_private(pgdata)
    with lifecycle_leases(pgdata.parent):
        claim_cluster(pgdata, "app")
        if (pgdata / "postmaster.pid").exists():
            parser.error("Stop the desktop engine before creating a recovery checkpoint")
        server = ensure_server(pgdata, database="postgres")
        try:
            with closing(psycopg2.connect(server.dsn(), connect_timeout=5)) as conn, conn.cursor() as cur:
                conn.set_session(readonly=True)
                cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (args.database,))
                if cur.fetchone() != (1,):
                    parser.error("The source database must already exist")
            server = replace(server, database=args.database,
                             base_uri=make_url(server.dsn()).set(database=args.database).render_as_string(hide_password=False))
            checkpoint = create_checkpoint(server, args.destination, args.verification_state)
            print(json.dumps({"checkpoint": str(checkpoint), "verified": True}))
        finally:
            if (pgdata / "postmaster.pid").exists():
                stop_server(pgdata)


if __name__ == "__main__":
    main()

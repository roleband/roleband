"""Restore a bound Windows checkpoint while retaining the current database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("begin", "status", "resume", "abort"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--preserve-current", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32" or not args.state.is_absolute():
        parser.error("Windows restore requires explicit absolute retained state")
    if (args.action == "begin") != (args.checkpoint is not None and args.preserve_current):
        parser.error("Begin requires --checkpoint and --preserve-current")
    if args.action != "begin" and (args.checkpoint is not None or args.preserve_current):
        parser.error("Only begin accepts a checkpoint and preservation confirmation")
    state = args.state
    os.environ.update(ROLEBAND_STATE_DIR=str(state), ROLEBAND_PGDATA=str(state / "db"),
                      ROLEBAND_CACHE_DIR=str(state / "cache"), ROLEBAND_PLUGINS_DIR=str(state / "plugins"),
                      ROLEBAND_SECRET_KEY_FILE=str(state / "secret.key"), ROLEBAND_DATABASE_URL="",
                      ROLEBAND_NO_USAGE_STATS="1")
    from tracker.platform.windows_restore import read_restore, restore

    if args.action == "status":
        result = read_restore(state)
    else:
        from tracker.platform.windows_process import CANCELLABLE_ENV, enter_job

        enter_job()
        os.environ.pop(CANCELLABLE_ENV, None)
        result = restore(state, args.action, args.checkpoint)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()

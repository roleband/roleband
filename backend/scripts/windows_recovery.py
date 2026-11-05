"""Run or resolve a durable Windows recovery drill without replacing current data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("begin", "status", "retry", "abandon"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    if sys.platform != "win32" or not args.state.is_absolute():
        parser.error("Windows recovery requires an explicit absolute state directory")
    if (args.action == "begin") != (args.checkpoint is not None):
        parser.error("Only begin requires --checkpoint")
    state = args.state
    os.environ.update(ROLEBAND_STATE_DIR=str(state), ROLEBAND_PGDATA=str(state / "db"),
                      ROLEBAND_CACHE_DIR=str(state / "cache"), ROLEBAND_PLUGINS_DIR=str(state / "plugins"),
                      ROLEBAND_SECRET_KEY_FILE=str(state / "secret.key"), ROLEBAND_DATABASE_URL="",
                      ROLEBAND_NO_USAGE_STATS="1")
    from tracker.platform.windows_recovery import read_recovery, recover

    if args.action != "status":
        from tracker.platform.windows_process import CANCELLABLE_ENV, enter_job

        enter_job()
        # Recovery owns only disposable scratch descendants, so initialization
        # is allowed inside its kill-on-close job without leaving an orphan.
        os.environ.pop(CANCELLABLE_ENV, None)
    result = read_recovery(state) if args.action == "status" else recover(state, args.action, args.checkpoint)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()

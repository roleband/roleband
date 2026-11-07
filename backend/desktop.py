"""Isolated Windows desktop entry point for source trials and packaged resources."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    source = "--source" in sys.argv[1:]
    args = [value for value in sys.argv[1:] if value != "--source"]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.dont_write_bytecode = True
    os.environ["ROLEBAND_PACKAGED"] = "0" if source else "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["ROLEBAND_LOCAL_AUTH"] = "1"
    if not args or args[0] not in {"run", "prepare", "seed", "checkpoint", "recovery", "restore", "update"}:
        sys.exit("usage: desktop.py [--source] {run|prepare|seed|checkpoint|recovery|restore|update} [arguments]")
    if args[0] in {"checkpoint", "recovery", "restore", "update"}:
        module = "scripts.windows_" + args[0]
        sys.argv = [module, *args[1:]]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return
    if sys.platform == "win32":
        from tracker.platform.windows_recovery import require_launchable

        state = os.environ.get("ROLEBAND_STATE_DIR")
        if not state or not Path(state).is_absolute():
            sys.exit("The desktop engine requires explicit absolute retained state")
        require_launchable(Path(state))
    if args == ["prepare"]:
        from tracker.supervisor.prepare import migrate

        migrate()
        return
    if args == ["seed"]:
        import asyncio

        from scripts.seed_synthetic import seed
        from tracker.db.session import session_scope

        async def seed_fixture() -> None:
            async with session_scope() as session:
                await seed(session, count=12, seed_value=20261105, derived=False)

        asyncio.run(seed_fixture())
        return
    sys.argv = ["tracker.supervisor.desktop", *args[1:]]
    if source:
        sys.argv.append("--development")
    runpy.run_module("tracker.supervisor.desktop", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()

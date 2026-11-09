"""Record the update choice or check the feed for the native Windows host, as JSON on stdout."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any


def identity_path() -> Path:
    from tracker.platform.paths import PACKAGED, REPO_ROOT

    # A package carries the identity it trusts in its resources; a checkout keeps it with the launcher.
    return REPO_ROOT / "release-identity.json" if PACKAGED else REPO_ROOT / "launcher" / "windows" / "release-identity.json"


def _last_update(state: Path, running: str) -> dict[str, Any] | None:
    """The last update as the running version sees it: Settings says how it ended, or that it is being undone."""
    from tracker.platform import windows_update_journal as journal
    from tracker.platform.windows_recovery import RecoveryError

    try:
        record = journal.read(state)
    except RecoveryError:
        return None
    if record is None:
        return None
    role = "to" if running == record["to_version"] else "from" if running == record["from_version"] else None
    return {"phase": record["phase"], "from": record["from_version"], "to": record["to_version"], "running": role}


def _held_back(update: dict[str, Any] | None) -> str | None:
    """A version this installation updated to and undid is not offered again; a newer release is."""
    return update["to"] if update is not None and update["phase"] == "recovered" else None


def _way_back(state: Path, running: str) -> str:
    """The version an update from here could be undone to: the running one, or, when the running version is a
    failed update that a newer release takes over, the version from before that update."""
    from tracker.platform import windows_update_journal as journal
    from tracker.platform.windows_recovery import RecoveryError

    try:
        record = journal.read(state)
    except RecoveryError:
        return running
    failed = record is not None and record["phase"] == "failed" and record["to_version"] == running
    return record["from_version"] if record is not None and failed else running


def _begin(state: Path, identity: Any, package: Path, running: str) -> int:
    """Journal a replacement by a retained, verified package while no engine is running."""
    from tracker.platform import windows_update_journal as journal
    from tracker.platform.filelock import LockHeld
    from tracker.platform.windows_leases import ENGINE, lease
    from tracker.platform.windows_packages import retained
    from tracker.platform.windows_recovery import RecoveryError

    kept = retained(state, identity)
    found = [offer for offer, path in kept if path.resolve() == package.resolve()]
    if not found or found[0].version == running:
        print(json.dumps({"status": "refused", "reason": "The package is not a verified retained update."}))
        return 1
    if not any(offer.version == _way_back(state, running) for offer, _path in kept):
        print(json.dumps({"status": "refused", "reason": "The installed version's package is not kept, so the "
                          "update could not be undone. Download the update again."}))
        return 1
    try:
        with lease(state / "launcher" / ENGINE):
            if (state / "db" / "postmaster.pid").exists():
                raise RecoveryError("Stop the engine before updating")
            record = journal.begin(state, from_version=running, to_version=found[0].version,
                                   package=package.resolve(), package_sha256=found[0].sha256)
    except (LockHeld, RecoveryError) as error:
        print(json.dumps({"status": "refused", "reason": str(error)}))
        return 1
    print(json.dumps({"phase": record["phase"], "to_version": record["to_version"]}))
    return 0


def _recover_begin(state: Path, identity: Any, running: str) -> int:
    """Name the retained previous package, downloading its release when it is not kept, and mark the update as
    returning to it."""
    from httpx import HTTPError

    from tracker.platform import windows_update_journal as journal
    from tracker.platform.windows_packages import retain_running, retained
    from tracker.platform.windows_recovery import RecoveryError
    from tracker.platform.windows_release import ReleaseError

    record = journal.read(state)
    if record is None:
        print(json.dumps({"status": "refused", "reason": "There is no update to undo."}))
        return 1
    previous = [path for offer, path in retained(state, identity) if offer.version == record["from_version"]]
    if not previous:
        try:
            # Kept as if it were running, so keeping it never prunes it again.
            previous = [retain_running(state, identity, record["from_version"])]
        except (OSError, HTTPError, ReleaseError) as error:
            print(json.dumps({"status": "refused", "reason": f"Version {record['from_version']} could not be "
                              f"downloaded from its release, so the update was not undone. ({error})"}))
            return 1
    try:
        journal.recover_begin(state, running)
    except RecoveryError as error:
        print(json.dumps({"status": "refused", "reason": str(error)}))
        return 1
    print(json.dumps({"phase": "recovering", "package": str(previous[0])}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    consent = commands.add_parser("consent")
    consent.add_argument("--state", type=Path, required=True)
    consent.add_argument("--automatic", choices=("on", "off"), required=True)
    consent.add_argument("--text", required=True)
    consent.add_argument("--language", required=True)
    commands.add_parser("status").add_argument("--state", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--state", type=Path, required=True)
    check.add_argument("--manual", action="store_true")
    fetch = commands.add_parser("download")
    fetch.add_argument("--state", type=Path, required=True)
    begin = commands.add_parser("begin")
    begin.add_argument("--state", type=Path, required=True)
    begin.add_argument("--package", type=Path, required=True)
    resume = commands.add_parser("resume")
    resume.add_argument("--state", type=Path, required=True)
    for name in ("recover-begin", "recover"):
        commands.add_parser(name).add_argument("--state", type=Path, required=True)
    settle = commands.add_parser("settle")
    settle.add_argument("--state", type=Path, required=True)
    settle.add_argument("--prepared", choices=("yes", "no"), required=True)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("Windows updates require Windows")
    if not args.state.is_absolute():
        parser.error("Updates require explicit absolute retained state")
    os.environ.setdefault("ROLEBAND_STATE_DIR", str(args.state))
    from tracker.platform.releases import running_version
    from tracker.platform.windows_release import ReleaseError, read_identity
    from tracker.platform.windows_updates import check as check_feed
    from tracker.platform.windows_updates import record_consent

    if args.action == "consent":
        record_consent(args.state, automatic=args.automatic == "on", text=args.text, language=args.language)
        print(json.dumps({"recorded": True}))
        return 0
    if args.action == "recover":
        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_process import CANCELLABLE_ENV, enter_job
        from tracker.platform.windows_recovery import RecoveryError

        enter_job()
        os.environ.pop(CANCELLABLE_ENV, None)
        try:
            record = journal.recover_database(args.state, running_version())
        except (RecoveryError, OSError) as error:
            print(json.dumps({"status": "refused", "reason": str(error)}))
            return 1
        print(json.dumps({"phase": record["phase"]}))
        return 0
    if args.action in {"resume", "settle"}:
        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_recovery import RecoveryError

        try:
            record = (journal.resume(args.state, running_version()) if args.action == "resume"
                      else journal.settle(args.state, running_version(), prepared=args.prepared == "yes"))
        except RecoveryError as error:
            print(json.dumps({"status": "refused", "reason": str(error)}))
            return 1
        running = running_version()
        role = None if record is None else "to" if running == record["to_version"] else (
            "from" if running == record["from_version"] else None)
        print(json.dumps({"phase": record["phase"] if record else None, "running": role}))
        return 0
    path = identity_path()
    if not path.is_file():
        print(json.dumps({"status": "unavailable", "reason": "This build carries no update identity."}))
        return 0
    if args.action == "status":
        from tracker.platform.windows_updates import status

        try:
            identity = read_identity(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, ReleaseError):
            print(json.dumps({"status": "unavailable", "reason": "This build's update identity is damaged."}))
            return 1
        update = _last_update(args.state, running_version())
        print(json.dumps({"status": "ok", **status(args.state, identity, running_version(), _held_back(update)),
                          "update": update}))
        return 0
    try:
        identity = read_identity(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ReleaseError):
        print(json.dumps({"status": "unavailable", "reason": "This build's update identity is damaged."}))
        return 1
    if args.action == "begin":
        return _begin(args.state, identity, args.package, running_version())
    if args.action == "recover-begin":
        return _recover_begin(args.state, identity, running_version())
    if args.action == "download":
        from httpx import HTTPError

        from tracker.platform.windows_packages import download, retain_running
        from tracker.platform.windows_updates import stored_offer

        stored = stored_offer(args.state, identity, running_version(), _held_back(_last_update(args.state, running_version())))
        if stored is None:
            print(json.dumps({"status": "no-offer"}))
            return 1
        try:
            # The way back is kept first: without it the update could not be undone.
            retain_running(args.state, identity, _way_back(args.state, running_version()))
        except (OSError, HTTPError, ReleaseError) as error:
            print(json.dumps({"status": "failed", "kind": "download", "reason": "The installed version's package could not be kept, "
                              f"so this update could not be undone. Try again later. ({error})"}))
            return 1
        try:
            path = download(args.state, identity, stored[0], stored[1], running_version())
        except ReleaseError as error:
            # The bytes arrived but are not the signed release: nothing to resume, and nothing may be installed.
            print(json.dumps({"status": "failed", "kind": "check", "reason": str(error)}))
            return 1
        except (OSError, HTTPError) as error:
            print(json.dumps({"status": "failed", "kind": "download", "reason": str(error)}))
            return 1
        print(json.dumps({"status": "downloaded", "package": str(path), "offer": dataclasses.asdict(stored[0])}))
        return 0
    update = _last_update(args.state, running_version())
    result = check_feed(args.state, identity, running_version(), manual=args.manual, held_back=_held_back(update))
    from tracker.platform.windows_updates import status

    kept = status(args.state, identity, running_version(), _held_back(update))
    print(json.dumps({"status": result.status, "until": result.until, "checked_at": kept["checked_at"],
                      "automatic": kept["automatic"],
                      "offer": dataclasses.asdict(result.offer) if result.offer else None, "update": update}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

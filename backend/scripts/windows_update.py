"""Record the update choice or check the feed for the native Windows host, as JSON on stdout."""

from __future__ import annotations

import argparse
import dataclasses
import errno
import json
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def identity_path() -> Path | None:
    """The update identity this build trusts, which a package carries in its resources. A source run has none: the
    checkout's committed identity is what release builds are made from, and a checkout never updates from their feed."""
    from tracker.platform.paths import PACKAGED, REPO_ROOT

    return REPO_ROOT / "release-identity.json" if PACKAGED else None


def _journal(state: Path) -> dict[str, Any] | None:
    """The update journal, read once per command; None when there is none, or when it is damaged, which `resume`
    reports and which keeps the database closed."""
    from tracker.platform import windows_update_journal as journal
    from tracker.platform.windows_recovery import RecoveryError

    try:
        return journal.read(state)
    except RecoveryError:
        return None


def _last_update(state: Path, running: str, record: dict[str, Any] | None) -> dict[str, Any] | None:
    """The last update as the running version sees it: Settings says how it ended, or that it is being undone."""
    from tracker.platform import windows_update_journal as journal

    if record is None:
        return None
    role = "to" if running == record["to_version"] else "from" if running == record["from_version"] else None
    # When the journal last changed: for an update still applying, when it began, which is how the native host finds
    # Windows' install of it.
    since = journal.journal(state).stat().st_mtime
    return {"phase": record["phase"], "from": record["from_version"], "to": record["to_version"], "running": role, "since": since,
            "package": Path(record["package"]).name}


def _held_back(update: dict[str, Any] | None) -> str | None:
    """A version this installation updated to and undid is not offered again; a newer release is."""
    return update["to"] if update is not None and update["phase"] == "recovered" else None


#: Beyond the packages themselves: Windows' own working files and the room a full disk would leave nothing for.
_SPACE_MARGIN = 256 * 2**20


class _NoRoom(OSError):
    """Too little free space for a download and Windows' copy of it, found before the download starts."""

    def __init__(self, needed: int) -> None:
        super().__init__(errno.ENOSPC, "not enough free space")
        self.needed = needed


def _space_needed(offer: Any, missing: set[str]) -> int:
    """Room for the packages still to download, and for Windows' copy of the update when it installs it. A version not
    kept yet is counted at the update's size, the nearest known."""
    return offer.bytes * (len(missing) + 1) + _SPACE_MARGIN


def _missing(state: Path, identity: Any, offer: Any, way_back: str) -> set[str]:
    """The versions whose packages this download fetches: the way back and the update, unless kept and verified. A
    file under a release's name that does not verify is fetched again."""
    from tracker.platform.windows_packages import retained

    return {way_back, offer.version} - {release.version for release, _path in retained(state, identity)}


class _Progress:
    """How much of the packages this download fetches has arrived, as JSON lines on stderr that the app shows. A
    package not started yet counts at its estimate, so the total holds still while the first one arrives."""

    def __init__(self, pending: dict[str, int]) -> None:
        self.pending = pending
        self.parts: dict[str, tuple[int, int]] = {}
        self.shown = 0.0

    def part(self, name: str) -> Callable[[int, int], None]:
        def report(received: int, size: int) -> None:
            self.pending.pop(name, None)
            self.parts[name] = (received, size)
            now = time.monotonic()
            if now - self.shown >= 0.5 or received == size:
                self.shown = now
                self.show()
        return report

    def skip(self, name: str) -> None:
        """A package that was already kept: nothing of it is fetched."""
        if self.pending.pop(name, None) is not None:
            self.show()

    def show(self) -> None:
        print(json.dumps({"received": sum(received for received, _size in self.parts.values()),
                          "total": sum(size for _received, size in self.parts.values()) + sum(self.pending.values())}),
              file=sys.stderr, flush=True)


def _failure(error: BaseException) -> str:
    """What a failed download says: a full disk, a connection that dropped (it resumes), a release the feed does not
    have, a package that is not the signed release (nothing to resume), or a download that did not finish, a feed
    asking to wait included."""
    from httpx import TransportError

    from tracker.platform.windows_packages import DownloadIncomplete, DownloadInterrupted
    from tracker.platform.windows_release import ReleaseError
    from tracker.platform.windows_updates import ReleaseMissing

    # Windows reports a full disk as ERROR_HANDLE_DISK_FULL (39) or ERROR_DISK_FULL (112), not always as ENOSPC.
    if isinstance(error, OSError) and (error.errno == errno.ENOSPC or getattr(error, "winerror", None) in (39, 112)):
        return "space"
    if isinstance(error, (TransportError, DownloadInterrupted)):
        return "offline"
    if isinstance(error, ReleaseMissing):
        return "missing"
    if isinstance(error, ReleaseError) and not isinstance(error, DownloadIncomplete):
        return "check"
    return "download"


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
    way_back = journal.way_back(_journal(state), running)
    if not any(offer.version == way_back for offer, _path in kept):
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
    from tracker.platform.windows_updates import RateLimited

    # Refused before the previous release, hundreds of megabytes, is downloaded for nothing.
    try:
        record = journal.read(state)
        if record is not None:
            journal.undoable(record, running)
    except RecoveryError as error:
        print(json.dumps({"status": "refused", "reason": str(error)}))
        return 1
    if record is None:
        print(json.dumps({"status": "refused", "reason": "There is no update to undo."}))
        return 1
    previous = [path for offer, path in retained(state, identity) if offer.version == record["from_version"]]
    if not previous:

        def room(offer: Any) -> None:
            # Its package and Windows' copy of it when it installs it, as for an update's own download.
            needed = _space_needed(offer, {offer.version})
            if shutil.disk_usage(state).free < needed:
                raise _NoRoom(needed)

        try:
            # Kept as if it were running, so keeping it never prunes it again.
            previous = [retain_running(state, identity, record["from_version"], room=room)]
        except (OSError, HTTPError, ReleaseError, RateLimited) as error:
            kind = _failure(error)
            version = record["from_version"]
            reason = {
                "missing": f"Version {version} is no longer published, so this update can't be undone.",
                "offline": f"Undo downloads version {version} first, and the connection was lost.",
                "space": f"There is not enough free space to download version {version}.",
            }.get(kind, f"Version {version} could not be downloaded from its release, so the update was not undone.")
            if isinstance(error, _NoRoom):
                print(json.dumps({"status": "refused", "kind": kind, "needed": error.needed, "reason": reason}))
            else:
                print(json.dumps({"status": "refused", "kind": kind, "reason": f"{reason} ({error})"}))
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
    def unavailable(reason: str) -> dict[str, Any]:
        """Updates are off for this build. Its status still names an update it left applying: the native host asks
        Windows about that update before `resume` settles it."""
        answer: dict[str, Any] = {"status": "unavailable", "reason": reason}
        if args.action == "status" and (update := _last_update(args.state, running_version(), _journal(args.state))):
            answer["update"] = update
        return answer

    identity_file = identity_path()
    if identity_file is None or not identity_file.is_file():
        print(json.dumps(unavailable("This build carries no update identity.")))
        return 0
    if args.action == "status":
        from tracker.platform.windows_updates import status

        try:
            identity = read_identity(json.loads(identity_file.read_text(encoding="utf-8")))
        except (ValueError, ReleaseError):
            print(json.dumps(unavailable("This build's update identity is damaged.")))
            return 1
        update = _last_update(args.state, running_version(), _journal(args.state))
        print(json.dumps({"status": "ok", **status(args.state, identity, running_version(), _held_back(update)),
                          "update": update}))
        return 0
    try:
        identity = read_identity(json.loads(identity_file.read_text(encoding="utf-8")))
    except (ValueError, ReleaseError):
        print(json.dumps({"status": "unavailable", "reason": "This build's update identity is damaged."}))
        return 1
    if args.action == "begin":
        return _begin(args.state, identity, args.package, running_version())
    if args.action == "recover-begin":
        return _recover_begin(args.state, identity, running_version())
    if args.action == "download":
        from httpx import HTTPError

        from tracker.platform import windows_update_journal as journal
        from tracker.platform.windows_packages import download, retain_running
        from tracker.platform.windows_updates import RateLimited, stored_offer

        running = running_version()
        record = _journal(args.state)
        stored = stored_offer(args.state, identity, running, _held_back(_last_update(args.state, running, record)))
        if stored is None:
            print(json.dumps({"status": "no-offer"}))
            return 1
        way_back = journal.way_back(record, running)
        missing = _missing(args.state, identity, stored[0], way_back)
        needed = _space_needed(stored[0], missing)
        if shutil.disk_usage(args.state).free < needed:
            print(json.dumps({"status": "failed", "kind": "space", "needed": needed,
                              "reason": "There is not enough free space for the download and its install."}))
            return 1
        # The way back's size is known once its release is read; until then it counts at the update's.
        progress = _Progress({version: stored[0].bytes for version in missing})
        try:
            # The way back is kept first: without it the update could not be undone.
            retain_running(args.state, identity, way_back, progress=progress.part(way_back))
            progress.skip(way_back)
        except (OSError, HTTPError, ReleaseError, RateLimited) as error:
            # This is the installed version's release, not the offer: the offer is neither unsigned nor unpublished,
            # and the app shows a download that did not finish, with Try again.
            kind = _failure(error)
            print(json.dumps({"status": "failed", "kind": "download" if kind in {"check", "missing"} else kind,
                              "reason": "The installed version's package could not be kept, "
                              f"so this update could not be undone. Try again later. ({error})"}))
            return 1
        try:
            path = download(args.state, identity, stored[0], stored[1], running, progress=progress.part(stored[0].version))
        except (OSError, HTTPError, ReleaseError, RateLimited) as error:
            print(json.dumps({"status": "failed", "kind": _failure(error), "reason": str(error)}))
            return 1
        print(json.dumps({"status": "downloaded", "package": str(path), "offer": dataclasses.asdict(stored[0])}))
        return 0
    update = _last_update(args.state, running_version(), _journal(args.state))
    result = check_feed(args.state, identity, running_version(), manual=args.manual, held_back=_held_back(update))
    from tracker.platform.windows_updates import status

    kept = status(args.state, identity, running_version(), _held_back(update))
    print(json.dumps({"status": result.status, "until": result.until, "checked_at": kept["checked_at"],
                      "automatic": kept["automatic"],
                      "offer": dataclasses.asdict(result.offer) if result.offer else None, "update": update}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

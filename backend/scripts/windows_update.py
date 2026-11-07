"""Record the update choice or check the feed for the native Windows host, as JSON on stdout."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path


def identity_path() -> Path:
    from tracker.platform.paths import PACKAGED, REPO_ROOT

    # A package carries the identity it trusts in its resources; a checkout keeps it with the launcher.
    return REPO_ROOT / "release-identity.json" if PACKAGED else REPO_ROOT / "launcher" / "windows" / "release-identity.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    consent = commands.add_parser("consent")
    consent.add_argument("--state", type=Path, required=True)
    consent.add_argument("--automatic", choices=("on", "off"), required=True)
    consent.add_argument("--text", required=True)
    consent.add_argument("--language", required=True)
    check = commands.add_parser("check")
    check.add_argument("--state", type=Path, required=True)
    check.add_argument("--manual", action="store_true")
    fetch = commands.add_parser("download")
    fetch.add_argument("--state", type=Path, required=True)
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
    path = identity_path()
    if not path.is_file():
        print(json.dumps({"status": "unavailable", "reason": "This build carries no update identity."}))
        return 0
    try:
        identity = read_identity(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ReleaseError):
        print(json.dumps({"status": "unavailable", "reason": "This build's update identity is damaged."}))
        return 1
    if args.action == "download":
        from httpx import HTTPError

        from tracker.platform.windows_packages import download
        from tracker.platform.windows_updates import stored_offer

        stored = stored_offer(args.state, identity, running_version())
        if stored is None:
            print(json.dumps({"status": "no-offer"}))
            return 1
        try:
            path = download(args.state, identity, stored[0], stored[1], running_version())
        except (OSError, HTTPError, ReleaseError) as error:
            print(json.dumps({"status": "failed", "reason": str(error)}))
            return 1
        print(json.dumps({"status": "downloaded", "package": str(path), "offer": dataclasses.asdict(stored[0])}))
        return 0
    result = check_feed(args.state, identity, running_version(), manual=args.manual)
    print(json.dumps({"status": result.status, "until": result.until,
                      "offer": dataclasses.asdict(result.offer) if result.offer else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

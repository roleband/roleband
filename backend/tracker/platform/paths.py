"""Code, immutable resources and writable state for source and packaged engines."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def user_data_dir() -> Path:
    """Retained account state, with an explicit override for isolated trials."""
    override = os.environ.get("ROLEBAND_STATE_DIR")
    if override:
        selected = Path(override).expanduser()
        if not selected.is_absolute():
            raise ValueError("ROLEBAND_STATE_DIR must be absolute")
        return selected
    if sys.platform == "win32":
        from tracker.platform.windows_state import local_app_data

        return local_app_data() / "RoleBand"
    return Path.home() / ".roleband"


def installed_data_roots() -> tuple[Path, ...]:
    """Default state roots of installed apps, which trial and repair tools never open.

    `~/.roleband` is the macOS app's and a source install's; Windows installs keep
    theirs under the LocalAppData known folder."""
    roots = [Path.home() / ".roleband"]
    if sys.platform == "win32":
        from tracker.platform.windows_state import local_app_data

        roots.append(local_app_data() / "RoleBand")
    return tuple(roots)


def within_installed_data(path: Path) -> bool:
    """Whether `path` is an installed app's state root or inside one, by where it really is: a junction or link
    on the way is followed, so it cannot lead a tool into an installed app's data under another name."""
    selected = Path(os.path.realpath(path))
    return any(selected.is_relative_to(os.path.realpath(root)) for root in installed_data_roots())


# Both layouts put tracker two levels below the resource root:
# backend/tracker/platform in a checkout, engine/tracker/platform in a bundle.
REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGED = os.environ.get("ROLEBAND_PACKAGED") == "1"
BACKEND_DIR = REPO_ROOT / ("engine" if PACKAGED else "backend")
DATA_DIR = user_data_dir() if PACKAGED or os.environ.get("ROLEBAND_STATE_DIR") else REPO_ROOT / "data"


def release_channel(resources: Path) -> bool:
    """Whether a packaged build is made for people's own data: its resources carry `build.json` naming the release
    channel. Development trials carry `trial.json` instead, and a checkout carries neither."""
    marker = resources / "build.json"
    try:
        record = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None
    except (OSError, ValueError):
        return False
    return isinstance(record, dict) and record.get("format") == 1 and record.get("channel") == "release"


#: An installed release engine, the one process that works in an installed app's data.
RELEASE = PACKAGED and release_channel(REPO_ROOT)


def reaches_installed_data(path: Path) -> bool:
    """Whether `path` is installed app data this process must leave alone: any of it, except the state a release
    engine was started on, which is its own."""
    if not within_installed_data(path):
        return False
    return not (RELEASE and Path(os.path.realpath(path)).is_relative_to(os.path.realpath(DATA_DIR)))
#: One slot file per rate-limit scope, shared by every provider-facing process
#: of this checkout (`ratelimit.enable_shared_pacing`).
PACING_DIR = DATA_DIR / "pacing"
DASHBOARD_DIST = REPO_ROOT / "dashboard" if PACKAGED else REPO_ROOT / "dashboard" / "dist"
VERSION_FILE = BACKEND_DIR / "release.json" if PACKAGED else REPO_ROOT / "dashboard" / "package.json"


def backend_dir(root: Path) -> Path:
    """Backend working directory within a caller's resource root."""
    return root / ("engine" if PACKAGED else "backend")

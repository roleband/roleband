"""Best-effort desktop notifications.

Used by the daily run (on failure) and the watchdog (on a newly-detected
unhealthy condition). Never raises: notification failure must not affect the
pipeline or supervision path.

On macOS the engine posts the banner itself. On Windows the RoleBand app shows
it: an engine the app starts is given a folder (`ALERTS_ENV`), and each alert is
one JSON file there that the app takes, shows and deletes
(`launcher/windows/RoleBand.EngineHost/EngineAlerts.cs`).
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TITLE = "RoleBand"

#: Names the folder where a Windows engine leaves alerts for the app that started it.
ALERTS_ENV = "ROLEBAND_ALERTS_DIR"
#: The alert file format the app reads.
ALERT_FORMAT = 1
#: Alerts waiting for the app beyond this many are dropped, so an app that is not
#: reading them never fills the folder.
MAX_PENDING_ALERTS = 20
#: The largest alert file the app reads (`max_bytes` in the contract).
ALERT_MAX_BYTES = 16 * 1024
#: Longer words are cut, with an ellipsis, so every alert file stays within
#: `ALERT_MAX_BYTES`: a character takes at most six bytes once written as JSON.
_MAX_TITLE_CHARS = 200
_MAX_MESSAGE_CHARS = 1000
_SEQUENCE = itertools.count()


def build_command(
    title: str,
    message: str,
    *,
    subtitle: str | None = None,
    has_terminal_notifier: bool = False,
) -> list[str]:
    """Build the notifier argv. Pure (no IO) so it can be unit-tested.

    Prefers ``terminal-notifier`` when present (richer, non-blocking); otherwise
    falls back to ``osascript`` which ships with macOS. Double quotes are
    downgraded to single quotes to keep the AppleScript string literal intact.
    """
    if has_terminal_notifier:
        cmd = ["terminal-notifier", "-title", title, "-message", message]
        if subtitle:
            cmd += ["-subtitle", subtitle]
        return cmd

    safe_title = title.replace('"', "'")
    safe_msg = message.replace('"', "'")
    script = f'display notification "{safe_msg}" with title "{safe_title}"'
    if subtitle:
        script += f' subtitle "{subtitle.replace(chr(34), chr(39))}"'
    return ["osascript", "-e", script]


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def write_alert(folder: Path, title: str, message: str, *, subtitle: str | None = None) -> Path | None:
    """Leave one alert for the Windows app. Returns its file, or None when too many already wait.

    The file appears whole: it is written under a dot name the app ignores and
    then renamed. Names sort in the order the alerts were written."""
    folder.mkdir(parents=True, exist_ok=True)
    if sum(1 for entry in folder.glob("*.json") if not entry.name.startswith(".")) >= MAX_PENDING_ALERTS:
        logger.warning("desktop notification dropped: %d alerts are waiting for the app", MAX_PENDING_ALERTS)
        return None
    record = {
        "format": ALERT_FORMAT,
        "title": _cut(title, _MAX_TITLE_CHARS),
        "message": _cut(message, _MAX_MESSAGE_CHARS),
        "subtitle": None if subtitle is None else _cut(subtitle, _MAX_TITLE_CHARS),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    # Windows' clock can give two alerts of one pass the same time; the sequence keeps both, in order.
    name = f"{time.time_ns():020d}-{os.getpid()}-{next(_SEQUENCE):06d}.json"
    partial = folder / f".{name}.tmp"
    partial.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    final = folder / name
    os.replace(partial, final)
    return final


def notify(title: str, message: str, *, subtitle: str | None = None) -> bool:
    """Post a desktop banner. Returns True if it was dispatched."""
    if sys.platform == "win32":
        folder = os.environ.get(ALERTS_ENV)
        if not folder:
            # A source run nobody's app started: there is no window to show it in.
            logger.info("desktop notification not shown (no RoleBand app): %s", message)
            return False
        try:
            return write_alert(Path(folder), title, message, subtitle=subtitle) is not None
        except Exception as exc:  # noqa: BLE001 - notifications are best-effort
            logger.warning("desktop notification failed: %s", exc)
            return False
    cmd = build_command(
        title,
        message,
        subtitle=subtitle,
        has_terminal_notifier=shutil.which("terminal-notifier") is not None,
    )
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=10)
        return True
    except Exception as exc:  # noqa: BLE001 - notifications are best-effort
        logger.warning("desktop notification failed: %s", exc)
        return False


def banner(key: str, **params: object) -> str:
    """Desktop product copy has the same FTL owner as dashboard text.

    English until a banner locale is deliberately introduced; no account read
    on the failure path, which may itself be reporting an unavailable database.
    """
    from tracker.notifications.catalog_gen import BANNERS
    return str(BANNERS[key](params))

"""The `app` context: the entry in the `roleband` context file that names the app's own engine.

The client reaches an engine only through a named context, and never guesses one
(`tracker/cli/contexts.py`). The Mac app keeps one context for itself: each time it starts its
own engine it writes `app` with that engine's loopback address, and makes it current when the
file names no current context. A person's other contexts and their choice of current one are
kept as they are, and so is a `workspace_id` the person pinned to `app`. A file that is not a
context file the client can read, or a link, is left alone, so a hand-kept file is never
rewritten into something else. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

#: Overrides where the context file lives, for the client and for the app.
CONFIG_ENV = "ROLEBAND_CLI_CONFIG"
#: The name the app's own engine has in the context file.
APP = "app"
FORMAT = 1

WRITTEN = "written"
UNCHANGED = "unchanged"
#: The file is not one the client could read, or is a link: nothing is written.
KEPT_FOREIGN = "kept_foreign"

FILE_KEYS = frozenset({"format", "current", "contexts"})
ENTRY_KEYS = frozenset({"url", "workspace_id"})
WORKSPACE = re.compile(r"^ws_[0-9a-f]{32}$")
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
#: The engine binds 127.0.0.1 only. A name would depend on resolution, and ::1
#: reaches whatever else holds the port there, never the engine.
LOOPBACK = "127.0.0.1"


def context_file(environ: Mapping[str, str], home: Path | None = None) -> Path:
    """Where the context file is: `ROLEBAND_CLI_CONFIG`, else `roleband/cli.json` under
    `XDG_CONFIG_HOME`, else under `~/.config`.

    The home folder is looked up only for the last case: a process started without one (no
    `HOME` or `USERPROFILE`) still finds a file the environment names."""
    explicit = environ.get(CONFIG_ENV)
    if explicit:
        return Path(explicit).expanduser()
    base = environ.get("XDG_CONFIG_HOME") or str((home if home is not None else Path.home()) / ".config")
    return Path(base).expanduser() / "roleband" / "cli.json"


def loopback_port(url: str) -> int | None:
    """The port of a context's `http://127.0.0.1:PORT` url, or None for any other url.

    Raises `ValueError` when the url does not parse."""
    parts = urlsplit(url)
    port = parts.port
    if (
        parts.scheme != "http"
        or parts.hostname != LOOPBACK
        or port is None
        or parts.username is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        return None
    return port


def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A JSON object hook that refuses a repeated key, which `json` would otherwise resolve to
    its last value."""
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("a key is repeated")
    return dict(pairs)


def _readable(document: object) -> bool:
    if not (
        isinstance(document, dict)
        and set(document) <= FILE_KEYS
        and document.get("format") == FORMAT
        and isinstance(document.get("contexts", {}), dict)
    ):
        return False
    current = document.get("current")
    if current is not None and not (isinstance(current, str) and NAME.fullmatch(current)):
        return False
    if APP not in document.get("contexts", {}):
        return True
    # The entry about to be replaced: one the client refuses is the person's to fix, so a
    # field it would drop is never dropped here.
    entry = document["contexts"][APP]
    if not isinstance(entry, dict) or not set(entry) <= ENTRY_KEYS or not isinstance(entry.get("url"), str):
        return False
    try:
        if loopback_port(entry["url"]) is None:
            return False
    except ValueError:
        return False
    workspace = entry.get("workspace_id")
    return workspace is None or (isinstance(workspace, str) and WORKSPACE.fullmatch(workspace) is not None)


def write_app_context(path: Path, port: int) -> str:
    """Point the `app` context in the file at `path` to `http://127.0.0.1:{port}`; one of the
    outcome constants above.

    Raises `OSError` when the folder or file cannot be written; the caller decides whether that
    matters (an engine start goes on without it)."""
    if path.is_symlink():
        return KEPT_FOREIGN
    try:
        current_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current_text = None
    except (UnicodeDecodeError, IsADirectoryError):
        return KEPT_FOREIGN
    found: object = {"format": FORMAT}
    if current_text is not None:
        try:
            found = json.loads(current_text, object_pairs_hook=no_duplicates)
        except ValueError:
            return KEPT_FOREIGN
    if not isinstance(found, dict) or not _readable(found):
        return KEPT_FOREIGN
    contexts = dict(found.get("contexts") or {})
    entry: dict[str, object] = {"url": f"http://127.0.0.1:{port}"}
    previous = contexts.get(APP)
    if isinstance(previous, dict) and isinstance(previous.get("workspace_id"), str):
        entry["workspace_id"] = previous["workspace_id"]
    contexts[APP] = entry
    document = {**found, "contexts": contexts}
    if document.get("current") is None:
        document["current"] = APP
    # A file that already says this keeps its own layout.
    if current_text is not None and document == found:
        return UNCHANGED
    text = json.dumps(document, indent=2) + "\n"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Created exclusively (mode 0600), so a link already at a staging name is never followed.
    descriptor, staged = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".partial")
    partial = Path(staged)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)
    return WRITTEN

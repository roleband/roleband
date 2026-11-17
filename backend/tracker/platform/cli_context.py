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
from collections.abc import Mapping
from pathlib import Path

#: Overrides where the context file lives, for the client and for the app.
CONFIG_ENV = "ROLEBAND_CLI_CONFIG"
#: The name the app's own engine has in the context file.
APP = "app"
FORMAT = 1

WRITTEN = "written"
UNCHANGED = "unchanged"
#: The file is not one the client could read, or is a link: nothing is written.
KEPT_FOREIGN = "kept_foreign"

_FILE_KEYS = {"format", "current", "contexts"}


def context_file(environ: Mapping[str, str], home: Path) -> Path:
    """Where the context file is: `ROLEBAND_CLI_CONFIG`, else `roleband/cli.json` under
    `XDG_CONFIG_HOME`, else under `~/.config`."""
    explicit = environ.get(CONFIG_ENV)
    if explicit:
        return Path(explicit).expanduser()
    base = environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(base).expanduser() / "roleband" / "cli.json"


def _readable(document: object) -> bool:
    return (
        isinstance(document, dict)
        and set(document) <= _FILE_KEYS
        and document.get("format") == FORMAT
        and isinstance(document.get("contexts", {}), dict)
    )


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
            found = json.loads(current_text)
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
    partial = path.with_name(f".{path.name}.{os.getpid()}.partial")
    try:
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)
    return WRITTEN

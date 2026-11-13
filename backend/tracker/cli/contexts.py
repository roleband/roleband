"""Named contexts: which engine a command reaches, chosen explicitly.

A context file maps names to loopback endpoints:

    {"format": 1, "current": "dev",
     "contexts": {"dev": {"url": "http://127.0.0.1:8011",
                          "workspace_id": "ws_..."}}}

It is `ROLEBAND_CLI_CONFIG` when set, else `roleband/cli.json` under
`XDG_CONFIG_HOME` (default `~/.config`). `--context NAME` picks one, else
`current`. Nothing else selects an engine: no default port, no project `.env`,
no `ROLEBAND_PGDATA`, and a missing context is an error, never a fallback.

A context may pin `workspace_id`; a reply from any other workspace is then
refused, so a context cannot silently reach a different store.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from tracker.cli.errors import ClientError

CONFIG_ENV = "ROLEBAND_CLI_CONFIG"
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_WORKSPACE = re.compile(r"^ws_[0-9a-f]{32}$")
#: Literal loopback addresses only: a name would depend on resolution.
_LOOPBACK = {"127.0.0.1", "::1"}
_ENTRY_KEYS = {"url", "workspace_id"}
_FILE_KEYS = {"format", "current", "contexts"}


@dataclass(frozen=True)
class Context:
    name: str
    host: str
    port: int
    workspace_id: str | None = None

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"


def config_path() -> Path:
    explicit = os.environ.get(CONFIG_ENV)
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "roleband" / "cli.json"


def _invalid(path: Path, reason: str, **details: object) -> ClientError:
    return ClientError(
        "context_invalid",
        f"The context file is not valid: {reason}",
        details={"path": str(path), **details},
    )


def _read(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError:
        raise _invalid(path, "it is not UTF-8 text.") from None
    except OSError as error:
        raise _invalid(path, f"it cannot be read ({error.strerror}).") from None
    try:
        document = json.loads(text, object_pairs_hook=_no_duplicates)
    except ValueError as error:
        raise _invalid(path, f"it is not JSON ({error}).") from None
    if not isinstance(document, dict) or not set(document) <= _FILE_KEYS or document.get("format") != 1:
        raise _invalid(path, "it needs format 1 and only the keys format, current and contexts.")
    return document


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("a key is repeated")
    return dict(pairs)


def _parse(path: Path, name: str, entry: object) -> Context:
    if not isinstance(entry, dict) or not set(entry) <= _ENTRY_KEYS or not isinstance(entry.get("url"), str):
        raise _invalid(path, f"context {name!r} needs a url and may name a workspace_id.", context=name)
    try:
        parts = urlsplit(entry["url"])
        port = parts.port
    except ValueError:
        raise _invalid(path, f"context {name!r} has a url that does not parse.", context=name) from None
    if (
        parts.scheme != "http"
        or parts.hostname not in _LOOPBACK
        or port is None
        or parts.username is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise _invalid(
            path,
            f"context {name!r} must be http://127.0.0.1:PORT or http://[::1]:PORT.",
            context=name,
        )
    workspace = entry.get("workspace_id")
    if workspace is not None and (not isinstance(workspace, str) or not _WORKSPACE.fullmatch(workspace)):
        raise _invalid(path, f"context {name!r} has a malformed workspace_id.", context=name)
    return Context(name=name, host=parts.hostname, port=port, workspace_id=workspace)


def resolve(requested: str | None) -> Context:
    """The context to call: the one named, else the file's current one."""
    path = config_path()
    document = _read(path)
    contexts = document.get("contexts", {})
    if not isinstance(contexts, dict):
        raise _invalid(path, "contexts must be an object.")
    names = sorted(contexts)
    name = requested if requested is not None else document.get("current")
    if name is None:
        raise ClientError(
            "context_required",
            "Name a context with --context; none is set as current.",
            details={"path": str(path), "contexts": names},
        )
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise _invalid(path, "a context name is lowercase letters, digits, - and _.")
    if name not in contexts:
        raise ClientError(
            "context_not_found",
            f"No context is named {name!r}.",
            details={"path": str(path), "context": name, "contexts": names},
        )
    return _parse(path, name, contexts[name])

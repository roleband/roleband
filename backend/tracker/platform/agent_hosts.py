"""The agent hosts `roleband connect` sets up: where each keeps its settings, what
connecting writes there, and which host a `roleband` call runs under.

Shared by the command, which writes these files, and the engine, which reads
them to show each host's state in Settings. Neither imports the other
(`pyproject.toml`), so what both must agree on lives here. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

Host = Literal["claude-code", "codex"]
HOSTS: tuple[Host, ...] = ("claude-code", "codex")

#: A call from any host not named in `HOSTS`, a script or the person's own terminal included.
OTHER = "other"

#: The header the command names its host in. The engine records it with each
#: activity row and reads nothing else from it.
HOST_HEADER = "X-RoleBand-Host"

CLAUDE_EXCLUDED = "roleband *"
CLAUDE_RULE = "Bash(roleband *)"
CODEX_TABLE = "sandbox_workspace_write"
CODEX_KEY = "network_access"

#: The skill's version. A copy installed at a lower one, and never edited, is out of date.
SKILL_VERSION = 5
SKILL_RECORD = ".roleband-skill.json"

#: What a host's files say about it, or None when it was never connected.
#: `outdated` is an unedited skill older than `SKILL_VERSION`; `rule_missing`
#: is a skill whose host no longer lets `roleband` run without asking.
Connection = Literal["connected", "outdated", "rule_missing"]


def _home() -> Path:
    return Path.home()


def claude_dir() -> Path:
    explicit = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(explicit).expanduser() if explicit else _home() / ".claude"


def codex_dir() -> Path:
    explicit = os.environ.get("CODEX_HOME")
    return Path(explicit).expanduser() if explicit else _home() / ".codex"


def host_dir(host: Host) -> Path:
    return claude_dir() if host == "claude-code" else codex_dir()


def skill_dir(host: Host) -> Path:
    return host_dir(host) / "skills" / "roleband"


def running_host(environ: Mapping[str, str]) -> Host | None:
    """The host whose command runner set `environ`: each sets a variable of its
    own in every command it runs (`CLAUDECODE=1`; Codex names its thread or
    its sandbox). None for anything else."""
    if environ.get("CLAUDECODE") == "1":
        return "claude-code"
    if any(environ.get(name) for name in ("CODEX_THREAD_ID", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED")):
        return "codex"
    return None


def caller(header: str | None) -> str:
    """The host a request's header names, or `OTHER` for any other value or none."""
    return header if header in HOSTS else OTHER


def _rule_present(host: Host) -> bool:
    """Whether the host's settings hold what `connect` writes there. A file
    this cannot read or parse counts as not holding it."""
    try:
        if host == "claude-code":
            document = json.loads((claude_dir() / "settings.json").read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                return False

            def listed(section: str, key: str, value: str) -> bool:
                table = document.get(section)
                entries = table.get(key) if isinstance(table, dict) else None
                return isinstance(entries, list) and value in entries

            return listed("sandbox", "excludedCommands", CLAUDE_EXCLUDED) and listed(
                "permissions", "allow", CLAUDE_RULE
            )
        table = tomllib.loads((codex_dir() / "config.toml").read_text(encoding="utf-8")).get(CODEX_TABLE)
        return isinstance(table, dict) and table.get(CODEX_KEY) is True
    except (OSError, UnicodeDecodeError, ValueError):
        return False


def _skill_state(host: Host) -> Literal["current", "outdated"] | None:
    """The installed skill: None when there is none, `outdated` when it is an
    unedited copy of an older version. An edited copy is the person's and
    counts as current: `connect` never replaces it."""
    directory = skill_dir(host)
    try:
        present = (directory / "SKILL.md").read_bytes()
    except OSError:
        return None
    try:
        record = json.loads((directory / SKILL_RECORD).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return "current"
    if not isinstance(record, dict):
        return "current"
    version = record.get("version")
    unedited = record.get("sha256") == hashlib.sha256(present).hexdigest()
    older = isinstance(version, int) and not isinstance(version, bool) and version < SKILL_VERSION
    return "outdated" if unedited and older else "current"


def connection(host: Host) -> Connection | None:
    """What the host's files say: connected, connected with an older skill, or
    a skill whose rule was removed. A host with no skill was never connected,
    whatever its settings hold, and so is one with no home folder to look in."""
    try:
        skill = _skill_state(host)
    except RuntimeError:
        # `Path.home()` raises where the environment names no home folder.
        return None
    if skill is None:
        return None
    if not _rule_present(host):
        return "rule_missing"
    return "outdated" if skill == "outdated" else "connected"

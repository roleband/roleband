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
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
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

#: The sidecar `connect` writes in each skill folder it installs: the version
#: it installed and the hash of each file it wrote, so a file the person
#: edited is told apart from an older unedited one.
SKILL_RECORD = ".roleband-skill.json"
_RECORD_FORMAT = 2

#: The command's bundled index of operations, which ships beside it in `tracker/cli/`.
OPERATIONS_INDEX = Path(__file__).resolve().parents[1] / "cli" / "operations.json"
#: The skills `connect` installs ship beside the command, one folder each.
SKILLS_SOURCE = Path(__file__).resolve().parents[1] / "cli" / "skills"


@dataclass(frozen=True)
class Skill:
    """A skill `connect` installs into a host: a folder of files, versioned as
    one. A folder installed at a lower version holds older files."""

    name: str
    version: int
    files: tuple[str, ...]

    @property
    def source(self) -> Path:
        return SKILLS_SOURCE / self.name


ROLEBAND_SKILL = Skill("roleband", 6, ("SKILL.md",))
TOP_PICKS_SKILL = Skill("roleband-top-picks", 3, ("SKILL.md", "setup.md", "judging.md"))
#: Every skill `connect` installs. The first is the one a connected host
#: always has: without it the host was never connected.
SKILLS: tuple[Skill, ...] = (ROLEBAND_SKILL, TOP_PICKS_SKILL)

#: What a host's files say about it, or None when it was never connected.
#: `outdated` is a host where `connect` would install or update a skill file:
#: a skill it never installed there, or an unedited file of an older version;
#: `rule_missing` is a skill whose host no longer lets `roleband` run without
#: asking; `read_only` is Codex set to its read-only sandbox, which blocks the
#: engine whatever `connect` wrote and which `connect` never changes.
Connection = Literal["connected", "outdated", "rule_missing", "read_only"]


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


def skill_dir(host: Host, skill: Skill = ROLEBAND_SKILL) -> Path:
    return host_dir(host) / "skills" / skill.name


# --------------------------------------------------------------------------- #
# What installing a skill would do
# --------------------------------------------------------------------------- #

FileAction = Literal["install", "update", "unchanged", "kept_edited"]


@dataclass(frozen=True)
class Record:
    """A skill folder's sidecar: the version `connect` installed, and the hash
    of each file as it wrote it."""

    version: int | None
    files: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> str:
        return json.dumps({"format": _RECORD_FORMAT, "version": self.version, "files": self.files},
                          sort_keys=True) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_record(directory: Path) -> Record | None:
    """The sidecar in `directory`, or None when there is none to read. A
    one-file sidecar (`sha256`, from before skills were folders) names the
    hash of `SKILL.md`."""
    try:
        document = json.loads((directory / SKILL_RECORD).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    version = document.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        version = None
    files = document.get("files")
    if isinstance(files, dict):
        hashes = {name: value for name, value in files.items() if isinstance(name, str) and isinstance(value, str)}
    elif isinstance(document.get("sha256"), str):
        hashes = {"SKILL.md": document["sha256"]}
    else:
        hashes = {}
    return Record(version, hashes)


@dataclass
class FilePlan:
    """What installing does to one file of a skill folder."""

    name: str
    path: Path
    action: FileAction
    #: The shipped bytes.
    content: bytes
    #: What was there when the plan was made; None when nothing was.
    present: bytes | None = None


def plan_skill(skill: Skill, directory: Path, record: Record | None) -> list[FilePlan]:
    """What `connect` does to each file of `skill` in `directory`: install a
    missing one, update one that is an unedited copy of another version (its
    hash is the one `record` holds), leave a current one, and keep one the
    person edited, linked or wrote themself. Raises OSError when a shipped
    file cannot be read."""
    plans = []
    for name in skill.files:
        shipped = (skill.source / name).read_bytes()
        target = directory / name
        if target.is_symlink():
            plans.append(FilePlan(name, target, "kept_edited", shipped))
            continue
        try:
            present = target.read_bytes()
        except FileNotFoundError:
            plans.append(FilePlan(name, target, "install", shipped))
            continue
        except OSError:
            plans.append(FilePlan(name, target, "kept_edited", shipped))
            continue
        if present == shipped:
            action: FileAction = "unchanged"
        elif record is not None and record.files.get(name) == sha256(present):
            action = "update"
        else:
            action = "kept_edited"
        plans.append(FilePlan(name, target, action, shipped, present))
    return plans


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


def roleband_calls() -> list[str]:
    """The calls the skill teaches, for every operation the command knows: `status`,
    `capabilities`, `describe OPERATION` and the operation's own command, each with and
    without `--json`."""
    try:
        document = json.loads(OPERATIONS_INDEX.read_text(encoding="utf-8"))
        operations = [entry["operation"] for entry in document["operations"]]
    except (OSError, ValueError, KeyError, TypeError):
        operations = ["status", "capabilities", "describe"]
    calls = {"roleband status", "roleband capabilities", "roleband capabilities --offline"}
    for operation in operations:
        calls.add(f"roleband describe {operation}")
        calls.add("roleband " + operation.replace(".", " ").replace("_", "-"))
    return sorted(calls | {f"{call} --json" for call in calls})


def covers(rule: str) -> bool:
    """Whether a Claude Code Bash rule applies to a roleband call an agent makes: `Bash` alone,
    a pattern (`*` is its one wildcard; `prefix:*` is the older prefix form) whose fixed start
    is a roleband command, such as `Bash(roleband describe *)`, or one that matches a call
    from `roleband_calls()`. A pattern that matches only some other text in a call's arguments,
    such as `Bash(*sudo*)`, does not count: no call the skill teaches carries it."""
    if rule == "Bash":
        return True
    match = re.fullmatch(r"Bash\((.*)\)", rule)
    if match is None:
        return False
    pattern = match.group(1)
    if pattern.endswith(":*"):
        pattern = pattern[:-2] + "*"
    if pattern.split("*", 1)[0].startswith("roleband "):
        return True
    compiled = re.compile(".*".join(re.escape(part) for part in pattern.split("*")), re.DOTALL)
    return any(compiled.fullmatch(call) for call in roleband_calls())


def claude_conflict(document: Mapping[str, object]) -> tuple[str, str] | None:
    """The first rule in Claude Code's `permissions.deny`, then `permissions.ask`, that
    applies to a roleband call, as (list, rule). Claude Code reads both before any allow
    rule, so either one outweighs the rule `connect` writes."""
    permissions = document.get("permissions")
    for kind in ("deny", "ask"):
        rules = permissions.get(kind) if isinstance(permissions, dict) else None
        for rule in rules if isinstance(rules, list) else []:
            if isinstance(rule, str) and covers(rule):
                return kind, rule
    return None


def _rule_present(host: Host) -> bool:
    """Whether the host's settings hold what `connect` writes there, with no
    deny or ask rule over it. A file this cannot read or parse counts as not
    holding it."""
    try:
        if host == "claude-code":
            document = json.loads((claude_dir() / "settings.json").read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                return False

            def listed(section: str, key: str, value: str) -> bool:
                table = document.get(section)
                entries = table.get(key) if isinstance(table, dict) else None
                return isinstance(entries, list) and value in entries

            return (
                listed("sandbox", "excludedCommands", CLAUDE_EXCLUDED)
                and listed("permissions", "allow", CLAUDE_RULE)
                and claude_conflict(document) is None
            )
        table = _codex_config().get(CODEX_TABLE)
        return isinstance(table, dict) and table.get(CODEX_KEY) is True
    except (OSError, UnicodeDecodeError, ValueError):
        return False


def _codex_config() -> dict[str, object]:
    return tomllib.loads((codex_dir() / "config.toml").read_text(encoding="utf-8"))


def _codex_read_only() -> bool:
    """Whether Codex's config sets its read-only sandbox, where no command reaches
    the network. Only an explicit setting counts: an unset mode is Codex's choice
    per workspace, which its files do not say."""
    try:
        return _codex_config().get("sandbox_mode") == "read-only"
    except (OSError, UnicodeDecodeError, ValueError):
        return False


def _outdated(skill: Skill, directory: Path) -> bool:
    """Whether `connect` would install or update a file of `skill` in
    `directory`. A folder it never installed, with files in it, is the
    person's; one installed at this client's version or a newer one is
    current; an edited or linked file is the person's and counts as current."""
    record = read_record(directory)
    if record is None:
        return not any((directory / name).exists() or (directory / name).is_symlink() for name in skill.files)
    if record.version is not None and record.version >= skill.version:
        return False
    try:
        plans = plan_skill(skill, directory, record)
    except OSError:
        return False
    # A file the record lists and the folder lacks was deleted by the person.
    return any(plan.action == "update" or (plan.action == "install" and plan.name not in record.files)
               for plan in plans)


def _skill_state(host: Host) -> Literal["current", "outdated"] | None:
    """The installed skills: None when the host has no `roleband` skill,
    `outdated` when `connect` would install or update one of their files."""
    try:
        (skill_dir(host) / "SKILL.md").stat()
    except OSError:
        return None
    if any(_outdated(skill, skill_dir(host, skill)) for skill in SKILLS):
        return "outdated"
    return "current"


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
    if host == "codex" and _codex_read_only():
        return "read_only"
    if not _rule_present(host):
        return "rule_missing"
    return "outdated" if skill == "outdated" else "connected"

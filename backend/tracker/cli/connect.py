"""`roleband connect [HOST] --print|--apply`: let an agent host run `roleband` without a prompt per call.

What each host needs was measured against the host itself:

- Claude Code's sandbox blocks loopback connections. `sandbox.excludedCommands: ["roleband *"]`
  runs the command outside it (a bare `roleband` does not match a call with arguments), and the
  permission rule `Bash(roleband *)` lets it run without asking.
- Codex's workspace-write mode blocks the network. `[sandbox_workspace_write] network_access =
  true` opens it; Codex has no switch for loopback alone.

Any other host is refused as `unsupported_host`: nothing was measured for it.

`--print` shows exactly what `--apply` would change. `--apply` merges into the person's file,
removes nothing, keeps a dated backup beside it before the first change, and changes nothing
on a second run. A value the person set the other way, or a layout this command cannot edit
safely, is theirs to change: the command stops with `approval_required` and touches nothing.

HOST may be left out when the command runs inside a host: each host names itself in a variable
it sets in every command it runs (`running_host`), so the person can ask the assistant to connect
itself. In a plain terminal no host is named that way, and HOST is required.

Each host also gets the versioned skills in `skills/` (`SKILLS`), each a folder. A sidecar in
each installed folder records its version and the hash of every file connect wrote, so a file
the person edited is never replaced, file by file. `capabilities` and `picks status` bring the
unedited files of an older installed version up to this client's (`refresh_installed_skills`),
so a new version reaches a host without a second connect.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tracker.cli.errors import ClientError
from tracker.platform import command_shim
from tracker.platform.agent_hosts import (
    CLAUDE_EXCLUDED,
    CLAUDE_RULE,
    CODEX_KEY,
    CODEX_TABLE,
    HOSTS,
    SKILL_RECORD,
    SKILLS,
    FilePlan,
    Record,
    Skill,
    claude_conflict,
    claude_dir,
    codex_dir,
    plan_skill,
    read_record,
    running_host,
    sha256,
)

#: Hosts people may name that were not measured. Each is refused rather than guessed at.
UNTESTED = ("gemini", "gemini-cli")

COSTS = {
    "claude-code": (
        "A command that starts with `roleband ` runs outside Claude Code's sandbox, with no limit on "
        "the files or network it reaches, and the permission rule lets Claude Code run it without asking."
    ),
    "codex": (
        "network_access = true opens all network access, not only this computer's engine, to every "
        "command Codex runs in workspace-write mode. Codex has no setting for loopback alone."
    ),
}

_TOML_TABLE = CODEX_TABLE
_TOML_KEY = CODEX_KEY
_TOML_HEADER = re.compile(rf"^[ \t]*\[[ \t]*{_TOML_TABLE}[ \t]*\][ \t]*(#[^\n]*)?$", re.MULTILINE)


def register(command: Callable[[str, str], argparse.ArgumentParser]) -> None:
    """Add `connect` through the client's own subcommand factory."""
    sub = command("connect", "Set up an agent host to run roleband without asking each time.")
    sub.add_argument("host", metavar="HOST", nargs="?", default=None,
                     help="claude-code or codex; left out inside a host, the host it runs in")
    mode = sub.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", dest="connect_mode", action="store_const", const="print",
                      help="show what would change; change nothing")
    mode.add_argument("--apply", dest="connect_mode", action="store_const", const="apply",
                      help="make those changes, keeping a backup of each changed file")
    # Asks no engine: the client answers it as it answers --offline.
    sub.set_defaults(offline=True)


# --------------------------------------------------------------------------- #
# Planned changes
# --------------------------------------------------------------------------- #


@dataclass
class FileChange:
    path: Path
    before: str | None
    after: str
    #: The bytes read, so a write can tell that someone else changed the file meanwhile.
    raw: bytes | None
    notes: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        if self.before is None:
            return "create"
        return "unchanged" if self.before == self.after else "update"


def _read(path: Path) -> tuple[str | None, bytes | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as error:
        raise ClientError("invalid_input", f"{path} cannot be read ({error.strerror}).",
                          details={"path": str(path)}) from None
    try:
        return raw.decode("utf-8"), raw
    except UnicodeDecodeError:
        raise ClientError("invalid_input", f"{path} is not UTF-8 text; nothing was changed.",
                          details={"path": str(path)}) from None


def _home() -> Path:
    return Path.home()


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("a key is repeated")
    return dict(pairs)


def _claude_settings(path: Path) -> FileChange:
    before, raw = _read(path)
    document: dict[str, Any] = {}
    if before is not None and before.strip():
        try:
            parsed = json.loads(before, object_pairs_hook=_no_duplicates)
        except ValueError as error:
            raise ClientError("invalid_input", f"{path} is not valid JSON ({error}); nothing was changed.",
                              details={"path": str(path)}) from None
        if not isinstance(parsed, dict):
            raise ClientError("invalid_input", f"{path} is not a JSON object; nothing was changed.",
                              details={"path": str(path)})
        document = parsed
    conflict = claude_conflict(document)
    if conflict is not None:
        kind, rule = conflict
        raise ClientError(
            "approval_required",
            f"Your rule {rule!r} in permissions.{kind} in {path} comes before any allow rule, so "
            f"Claude Code would still {'refuse' if kind == 'deny' else 'ask about'} every roleband call. "
            "Nothing was changed; remove or narrow that rule yourself if you want roleband to run.",
            details={"path": str(path), "rule": rule, "list": f"permissions.{kind}"},
        )
    added: list[str] = []

    def listed(section: str, key: str, value: str) -> None:
        table = document.setdefault(section, {})
        if not isinstance(table, dict):
            raise ClientError("invalid_input", f"{section} in {path} is not an object; nothing was changed.",
                              details={"path": str(path), "key": section})
        entries = table.setdefault(key, [])
        if not isinstance(entries, list):
            raise ClientError("invalid_input", f"{section}.{key} in {path} is not a list; nothing was changed.",
                              details={"path": str(path), "key": f"{section}.{key}"})
        if value not in entries:
            entries.append(value)
            added.append(value)

    listed("sandbox", "excludedCommands", CLAUDE_EXCLUDED)
    listed("permissions", "allow", CLAUDE_RULE)
    if before is not None and not added:
        # Already connected: the person's file stays byte for byte as it is.
        return FileChange(path, before, before, raw)
    return FileChange(path, before, json.dumps(document, indent=2, ensure_ascii=False) + "\n", raw)


def _refuse_codex(path: Path, reason: str) -> ClientError:
    return ClientError(
        "approval_required",
        f"{reason} Nothing was changed; to connect, set it yourself in {path}:\n"
        f"[{_TOML_TABLE}]\n{_TOML_KEY} = true",
        details={"path": str(path), "setting": f"{_TOML_TABLE}.{_TOML_KEY}"},
    )


def _codex_config(path: Path) -> FileChange:
    import tomllib

    before, raw = _read(path)
    text = before or ""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ClientError("invalid_input", f"{path} is not valid TOML ({error}); nothing was changed.",
                          details={"path": str(path)}) from None
    notes = []
    mode = document.get("sandbox_mode")
    if mode != "workspace-write":
        notes.append(
            f"sandbox_mode is {json.dumps(mode) if mode is not None else 'not set'}: this setting matters only "
            "when Codex runs commands in workspace-write mode (read-only blocks the engine either way)."
        )
    table = document.get(_TOML_TABLE)
    if table is None:
        separator = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        after = f"{text}{separator}[{_TOML_TABLE}]\n{_TOML_KEY} = true\n"
    elif not isinstance(table, dict):
        raise _refuse_codex(path, f"{_TOML_TABLE} is not a table.")
    elif table.get(_TOML_KEY) is True:
        return FileChange(path, before, text, raw, notes)
    elif _TOML_KEY in table:
        raise _refuse_codex(path, f"{_TOML_TABLE}.{_TOML_KEY} is set to {table[_TOML_KEY]!r} in your file.")
    else:
        headers = list(_TOML_HEADER.finditer(text))
        if len(headers) != 1:
            raise _refuse_codex(path, f"[{_TOML_TABLE}] is written in a form this command does not edit.")
        # The key goes on the line after the table's header, ahead of the table's other keys.
        end = headers[0].end()
        rest = text[end:] or "\n"
        after = f"{text[:end]}\n{_TOML_KEY} = true{rest}"
    # The edit is text, so prove it: the file must read as the old settings plus this one key.
    expected = copy.deepcopy(document)
    expected.setdefault(_TOML_TABLE, {})[_TOML_KEY] = True
    try:
        merged = tomllib.loads(after)
    except tomllib.TOMLDecodeError:
        merged = None
    if merged != expected:
        raise _refuse_codex(path, f"[{_TOML_TABLE}] could not be added without changing other settings.")
    return FileChange(path, before, after, raw, notes)


# --------------------------------------------------------------------------- #
# The skills
# --------------------------------------------------------------------------- #


@dataclass
class SkillPlan:
    skill: Skill
    directory: Path
    files: list[FilePlan]
    #: The sidecar as the plan read it.
    record: Record | None

    @property
    def action(self) -> str:
        """The folder's action: `install` when every file is new, `update`
        when any file is new or updated, `kept_edited` when the only files
        that differ are the person's, else `unchanged`."""
        actions = {plan.action for plan in self.files}
        if actions == {"install"}:
            return "install"
        if actions & {"install", "update"}:
            return "update"
        return "kept_edited" if "kept_edited" in actions else "unchanged"

    def kept(self) -> list[str]:
        return [plan.name for plan in self.files if plan.action == "kept_edited"]


def _skill(skill: Skill, directory: Path) -> SkillPlan:
    """What to do with `skill` in `directory`, file by file."""
    record = read_record(directory)
    return SkillPlan(skill, directory, plan_skill(skill, directory, record), record)


def _install_skill(plan: SkillPlan, applied: list[str], *, refresh: bool = False) -> None:
    """Install or update the skill's files as planned, adding each file it
    changes to `applied`, then record what it wrote. A `refresh` leaves out a
    missing file the sidecar lists, which the person deleted, and records the
    folder only when a file's recorded hash changes: only `connect`, the
    person's own act, records a folder whose differing files are all theirs,
    while a file already at this version's bytes under an older hash is
    recorded, so a sidecar that failed to save is repaired by the next call."""
    listed = plan.record.files if plan.record is not None else {}
    hashes = dict(listed)
    ours = False
    for item in plan.files:
        if item.action == "install" and refresh and item.name in listed:
            continue
        if item.action in ("install", "update"):
            if not _as_planned(item):
                item.action = "kept_edited"
                continue
            plan.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            _replace(item.path, item.content, mode=0o644)
            applied.append(str(item.path))
        if item.action != "kept_edited":
            hashes[item.name] = sha256(item.content)
            ours = True
    if not ours or (refresh and hashes == listed):
        # Nothing here is connect's at this version: the sidecar stays as it was.
        return
    record = Record(plan.skill.version, {name: hashes[name] for name in plan.skill.files if name in hashes})
    path = plan.directory / SKILL_RECORD
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        current = None
    if current != record.as_json():
        _replace(path, record.as_json().encode(), mode=0o644)
        applied.append(str(path))


def _as_planned(item: FilePlan) -> bool:
    """Whether the file is still as the plan read it. The person may have
    saved, linked or locked it since; a link or a file that cannot be read
    is theirs, whatever the plan saw."""
    if item.path.is_symlink():
        return False
    try:
        return item.path.read_bytes() == item.present
    except FileNotFoundError:
        return item.present is None
    except OSError:
        return False


def refresh_installed_skills() -> list[dict[str, str]]:
    """Bring each skill `connect` installed up to this client's version, and
    return a notice for each one it updated or could not.

    Only a folder whose sidecar records an older version is touched, so two
    clients of different versions on one computer never trade the files back
    and forth. A file the person edited stays as it is, as `connect` keeps
    it, and so does one they deleted; a file new in this version is added.
    A skill `connect` never installed is left to `connect`. Nothing here
    fails the call it runs in."""
    notices: list[dict[str, str]] = []
    for host, base in (("claude-code", claude_dir), ("codex", codex_dir)):
        for skill in SKILLS:
            try:
                directory = base() / "skills" / skill.name
            except (OSError, RuntimeError):
                # No home folder to find (`Path.home()` raises where the
                # environment names none): no installed skill to keep current.
                continue
            record = read_record(directory)
            installed = record.version if record is not None else None
            if installed is None or installed >= skill.version:
                continue
            try:
                plan = _skill(skill, directory)
                # Another client may have installed its own version since the
                # record was read; that copy is not this client's to replace.
                if read_record(directory) != record:
                    continue
                written: list[str] = []
                _install_skill(plan, written, refresh=True)
            except OSError as error:
                notices.append({
                    "code": "skill_outdated",
                    "message": f"The {skill.name} skill installed for {host} is version {installed} and could not "
                    f"be updated to {skill.version} ({error.strerror or error}); run roleband connect {host} --apply.",
                })
                continue
            kept = plan.kept()
            if written:
                notices.append({
                    "code": "skill_updated",
                    "message": f"The {skill.name} skill installed for {host} is now version {skill.version}, "
                    f"was {installed}; the host reads it from its next session."
                    + (f" You edited {', '.join(kept)}, so it stays as you wrote it." if kept else ""),
                })
            elif kept:
                paths = ", ".join(str(directory / name) for name in kept)
                notices.append({
                    "code": "skill_outdated",
                    "message": f"The {skill.name} skill installed for {host} was edited at {paths}, so it stays "
                    f"at version {installed}; this client ships version {skill.version}.",
                })
    return notices


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #


def _replace(path: Path, data: bytes, *, mode: int) -> None:
    partial = path.with_name(f".{path.name}.{os.getpid()}.partial")
    try:
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.chmod(partial, mode)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def _backup_path(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.roleband-backup-{stamp}")
    count = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.roleband-backup-{stamp}-{count}")
        count += 1
    return candidate


def _write(change: FileChange) -> str | None:
    """Apply one file change; returns the backup's path when one was made."""
    if change.action == "unchanged":
        return None
    # A link (a dotfiles manager's, say) stays a link: the file it names is the one changed.
    target = Path(os.path.realpath(change.path))
    _, now = _read(target)
    if now != change.raw:
        raise ClientError("revision_conflict", f"{change.path} changed while connect was reading it; run it again.",
                          details={"path": str(change.path)})
    backup = None
    if change.raw is not None:
        mode = target.stat().st_mode & 0o777
        backup = _backup_path(target)
        _replace(backup, change.raw, mode=mode)
    else:
        mode = 0o600
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _replace(target, change.after.encode("utf-8"), mode=mode)
    return str(backup) if backup else None


def _diff(change: FileChange) -> list[str]:
    import difflib

    if change.action == "unchanged":
        return []
    before = (change.before or "").splitlines(keepends=True)
    after = change.after.splitlines(keepends=True)
    label = str(change.path)
    lines = difflib.unified_diff(before, after, fromfile=label if change.before is not None else "/dev/null",
                                 tofile=label)
    return [line.rstrip("\n") for line in lines]


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #


def _shim() -> dict[str, Any]:
    home = _home()
    path = command_shim.shim_path(home)
    on_path = command_shim.directory_on_path(path.parent, os.environ.get("PATH"))
    present = command_shim.is_ours(path)
    notes = []
    if not present:
        notes.append(f"{path} is not there yet: open the RoleBand app once and it writes the command.")
    if not on_path:
        notes.append(
            f"{path.parent} is not on your PATH, so a host finds `roleband` only by its full path, which the "
            "rule above does not match. Add it to PATH in your shell profile, for example: "
            'export PATH="$HOME/.local/bin:$PATH"'
        )
    return {"path": str(path), "present": present, "on_path": on_path, "notes": notes}


def _host(named: str | None, environ: Mapping[str, str]) -> tuple[str, bool]:
    """The host to connect, and whether it was found from the environment
    rather than named."""
    if named is not None:
        return named, False
    found = running_host(environ)
    if found is None:
        raise ClientError(
            "invalid_arguments",
            "Name the host to connect, such as roleband connect claude-code --apply or roleband connect codex "
            "--apply. Run inside Claude Code or Codex, connect finds the host by itself.",
            details={"supported": list(HOSTS)},
        )
    return found, True


def run(args: argparse.Namespace, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    host, detected = _host(args.host, os.environ if environ is None else environ)
    if host not in HOSTS:
        untested = host in UNTESTED
        raise ClientError(
            "unsupported_host",
            f"{host} is not tested with roleband yet, so connect does not change its settings."
            if untested else f"connect knows no host named {host!r}.",
            details={"host": host, "supported": list(HOSTS)},
        )
    if host == "claude-code":
        base = claude_dir()
        changes = [_claude_settings(base / "settings.json")]
    else:
        base = codex_dir()
        changes = [_codex_config(base / "config.toml")]
    try:
        skills = [_skill(skill, base / "skills" / skill.name) for skill in SKILLS]
    except OSError as error:
        raise ClientError("internal_error", f"This client's skill files cannot be read ({error.strerror or error}).",
                          details={"path": error.filename}) from None
    apply = args.connect_mode == "apply"
    backups: dict[str, str | None] = {}
    applied: list[str] = []
    if apply:
        try:
            for change in changes:
                backups[str(change.path)] = _write(change)
                if change.action != "unchanged":
                    applied.append(str(change.path))
            for skill in skills:
                _install_skill(skill, applied)
        except OSError as error:
            path = error.filename or "a file"
            done = f" Already changed: {', '.join(applied)}." if applied else " Nothing was changed."
            raise ClientError(
                "internal_error",
                f"connect could not write {path} ({error.strerror or error}).{done}",
                details={"path": error.filename, "applied": applied,
                         "backups": [backup for backup in backups.values() if backup]},
            ) from None
    changed = (any(change.action != "unchanged" for change in changes)
               or any(skill.action in ("install", "update") for skill in skills))
    return {
        "host": host,
        # Whether the host was found from the variable it sets rather than named.
        "host_detected": detected,
        "mode": args.connect_mode,
        "applied": apply,
        # With --print: whether --apply would change anything.
        "changed": changed,
        "cost": COSTS[host],
        "files": [
            {
                "path": str(change.path),
                "action": change.action,
                "diff": _diff(change),
                "backup": backups.get(str(change.path)),
                "notes": change.notes,
            }
            for change in changes
        ],
        "skills": [_skill_view(skill) for skill in skills],
        "command": _shim(),
    }


def _skill_view(plan: SkillPlan) -> dict[str, Any]:
    note = {
        "install": "installs", "update": "updates", "unchanged": "is already current",
        "kept_edited": "is kept as you edited it; the new version is not installed",
    }[plan.action]
    kept = plan.kept()
    if kept and plan.action == "update":
        note += f"; {', '.join(kept)} is kept as you edited it"
    return {
        "name": plan.skill.name,
        "path": str(plan.directory),
        "action": plan.action,
        "version": plan.skill.version,
        "files": [{"name": item.name, "path": str(item.path), "action": item.action} for item in plan.files],
        "summary": f"the {plan.skill.name} skill, version {plan.skill.version}, {note}",
    }


def human_lines(data: dict[str, Any], escape: Callable[[object], str]) -> list[str]:
    if not data["changed"]:
        headline = "already connected, nothing to change"
    else:
        headline = "changed" if data["applied"] else "what --apply would change"
    found = " (the host this runs in)" if data["host_detected"] else ""
    lines = [f"{escape(data['host'])}{found}: {headline}"]
    for change in data["files"]:
        verb = {"create": "create", "update": "update", "unchanged": "already set, no change"}[change["action"]]
        lines.append(f"  {escape(change['path'])}: {verb}")
        lines.extend(f"    {escape(line)}" for line in change["diff"])
        if change["backup"]:
            lines.append(f"    backup: {escape(change['backup'])}")
        lines.extend(f"    note: {escape(note)}" for note in change["notes"])
    lines.extend(f"  {escape(skill['path'])}: {escape(skill['summary'])}" for skill in data["skills"])
    command = data["command"]
    state = "present" if command["present"] else "missing"
    lines.append(f"  {escape(command['path'])}: {state}, {'on' if command['on_path'] else 'not on'} PATH")
    lines.extend(f"    note: {escape(note)}" for note in command["notes"])
    lines.append(f"Cost: {escape(data['cost'])}")
    return lines

"""`roleband connect`: what it writes into an agent host's settings, and what it leaves alone.

Every case runs `python -m tracker.cli` in a subprocess whose HOME is a scratch folder, with
`CLAUDE_CONFIG_DIR` and `CODEX_HOME` unset, so the person's real `~/.claude`, `~/.codex` and
`~/.local/bin` are never read or written.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tracker.platform import agent_hosts

BACKEND = Path(__file__).resolve().parents[1]
SKILLS_SOURCE = BACKEND / "tracker" / "cli" / "skills"
SHIPPED_SKILL = SKILLS_SOURCE / "roleband" / "SKILL.md"
TOP_PICKS = "roleband-top-picks"
SKILL_VERSION = agent_hosts.ROLEBAND_SKILL.version

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="connect sets up Mac hosts")


class Home:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def claude(self) -> Path:
        return self.root / ".claude" / "settings.json"

    @property
    def codex(self) -> Path:
        return self.root / ".codex" / "config.toml"

    def skill(self, host: str, name: str = "roleband", file: str = "SKILL.md") -> Path:
        return self.root / (".claude" if host == "claude-code" else ".codex") / "skills" / name / file

    def files(self) -> dict[str, bytes]:
        """Every file under the home, by relative path."""
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in sorted(self.root.rglob("*")) if path.is_file()}

    def connect(self, host: str | None, mode: str, *, path: str | None = None,
                env: dict[str, str] | None = None) -> tuple[int, dict]:
        return self.run("connect", *([host] if host else []), f"--{mode}", path=path, env=env)

    def run(self, *args: str, path: str | None = None, env: dict[str, str] | None = None) -> tuple[int, dict]:
        # Built from nothing, so the variable a host sets in the shell running
        # these tests never reaches the command.
        env = {
            "PATH": path if path is not None else "/usr/bin:/bin",
            "HOME": str(self.root),
            "PYTHONPATH": str(BACKEND),
            "LANG": "en_US.UTF-8",
            "ROLEBAND_CLI_CONFIG": str(self.root / "no-contexts.json"),
            **(env or {}),
        }
        process = subprocess.run(
            [sys.executable, "-m", "tracker.cli", *args, "--json"],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=30,
        )
        lines = process.stdout.splitlines()
        assert len(lines) == 1, (process.stdout, process.stderr)
        return process.returncode, json.loads(lines[0])


@pytest.fixture
def home(tmp_path) -> Home:
    root = tmp_path / "home"
    root.mkdir()
    return Home(root)


def _backups(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.name}.roleband-backup-*"))


def _skill_of(envelope: dict, name: str = "roleband") -> dict:
    """The answer's entry for one skill."""
    [entry] = [skill for skill in envelope["data"]["skills"] if skill["name"] == name]
    return entry


def _shipped(name: str, file: str) -> bytes:
    return (SKILLS_SOURCE / name / file).read_bytes()


# --------------------------------------------------------------------------- #
# Claude Code
# --------------------------------------------------------------------------- #


def test_claude_code_gets_the_excluded_command_the_rule_and_the_skill(home):
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0 and envelope["ok"], envelope
    settings = json.loads(home.claude.read_text())
    assert settings["sandbox"]["excludedCommands"] == ["roleband *"]
    assert settings["permissions"]["allow"] == ["Bash(roleband *)"]
    assert home.skill("claude-code").read_bytes() == SHIPPED_SKILL.read_bytes()
    for file in agent_hosts.TOP_PICKS_SKILL.files:
        assert home.skill("claude-code", TOP_PICKS, file).read_bytes() == _shipped(TOP_PICKS, file)
    data = envelope["data"]
    assert data["files"][0]["action"] == "create" and data["files"][0]["backup"] is None
    assert [(skill["name"], skill["action"]) for skill in data["skills"]] == [
        ("roleband", "install"), (TOP_PICKS, "install")]
    assert data["host_detected"] is False
    # The other host was not touched.
    assert not (home.root / ".codex").exists()
    assert "outside Claude Code's sandbox" in data["cost"]


def test_a_second_apply_changes_nothing(home):
    home.connect("claude-code", "apply")
    before = home.files()
    stamps = {path: path.stat().st_mtime_ns for path in home.root.rglob("*") if path.is_file()}
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0
    assert home.files() == before
    assert {path: path.stat().st_mtime_ns for path in home.root.rglob("*") if path.is_file()} == stamps
    assert envelope["data"]["changed"] is False
    assert envelope["data"]["files"][0]["action"] == "unchanged"
    assert envelope["data"]["files"][0]["diff"] == []
    assert {skill["action"] for skill in envelope["data"]["skills"]} == {"unchanged"}


def test_existing_settings_and_permission_rules_survive(home):
    original = {
        "model": "opus",
        "env": {"FOO": "bar"},
        "permissions": {"allow": ["Bash(git status)", "Read(~/notes/**)"], "deny": ["Bash(rm *)"],
                        "defaultMode": "acceptEdits"},
        "sandbox": {"enabled": True, "excludedCommands": ["docker *"], "network": {"allowLocalBinding": False}},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say done"}]}]},
    }
    home.claude.parent.mkdir()
    raw = json.dumps(original, indent=4).encode()
    home.claude.write_bytes(raw)
    home.claude.chmod(0o640)
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0, envelope
    settings = json.loads(home.claude.read_text())
    expected = json.loads(raw)
    expected["permissions"]["allow"].append("Bash(roleband *)")
    expected["sandbox"]["excludedCommands"].append("roleband *")
    assert settings == expected
    assert home.claude.stat().st_mode & 0o777 == 0o640
    [backup] = _backups(home.claude)
    assert backup.read_bytes() == raw
    assert envelope["data"]["files"][0]["backup"] == str(backup)


def test_rules_that_are_already_there_are_not_repeated_and_the_file_is_untouched(home):
    home.claude.parent.mkdir()
    raw = b'{"permissions":{"allow":["Bash(roleband *)"]},"sandbox":{"excludedCommands":["roleband *"]}}'
    home.claude.write_bytes(raw)
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0
    assert home.claude.read_bytes() == raw
    assert _backups(home.claude) == []
    assert envelope["data"]["files"][0]["action"] == "unchanged"


def test_print_shows_the_change_apply_makes_and_writes_nothing(home):
    home.claude.parent.mkdir()
    home.claude.write_text('{"permissions": {"allow": ["Bash(ls)"]}}\n')
    before = home.files()
    status, printed = home.connect("claude-code", "print")
    assert status == 0
    assert home.files() == before
    diff = printed["data"]["files"][0]["diff"]
    assert '+      "Bash(roleband *)"' in diff and '+      "roleband *"' in diff
    assert printed["data"]["changed"] is True and printed["data"]["applied"] is False
    assert {skill["action"] for skill in printed["data"]["skills"]} == {"install"}
    _, applied = home.connect("claude-code", "apply")
    assert applied["data"]["files"][0]["diff"] == diff


@pytest.mark.parametrize("content", ['{"permissions": ', "[]", '{"a": 1, "a": 2}',
                                     '{"permissions": []}', '{"sandbox": {"excludedCommands": "roleband *"}}'])
def test_a_settings_file_it_cannot_merge_into_is_left_untouched(home, content):
    home.claude.parent.mkdir()
    home.claude.write_text(content)
    status, envelope = home.connect("claude-code", "apply")
    assert status == 2 and envelope["error"]["code"] == "invalid_input", envelope
    assert home.claude.read_text() == content
    assert _backups(home.claude) == []
    assert not home.skill("claude-code").exists()


@pytest.mark.parametrize(("kind", "rule"), [
    ("deny", "Bash"), ("deny", "Bash(*)"), ("ask", "Bash(roleband *)"), ("ask", "Bash(roleband:*)"),
    ("deny", "Bash(roleband*)"), ("ask", "Bash(roleband capabilities)"), ("deny", "Bash(roleband describe *)"),
    ("ask", "Bash(roleband opportunities search *)"), ("ask", "Bash(*describe capabilities)"),
    ("deny", "Bash(* --json)"), ("ask", "Bash(*status)"),
])
def test_an_ask_or_deny_rule_that_would_still_stop_roleband_is_the_persons_to_change(home, kind, rule):
    home.claude.parent.mkdir()
    content = json.dumps({"permissions": {kind: [rule]}})
    home.claude.write_text(content)
    status, envelope = home.connect("claude-code", "apply")
    assert status == 7 and envelope["error"]["code"] == "approval_required", envelope
    assert envelope["error"]["details"] == {"path": str(home.claude), "rule": rule, "list": f"permissions.{kind}"}
    assert home.claude.read_text() == content
    assert _backups(home.claude) == []


def test_ask_and_deny_rules_for_other_commands_are_kept(home):
    home.claude.parent.mkdir()
    home.claude.write_text(json.dumps({"permissions": {"deny": ["Bash(rm *)", "Bash(*rm -rf*)", "Read(.env)"],
                                                       "ask": ["Bash(git push:*)", "Bash(rolebandx *)", "Bash(*sudo*)",
                                                               "Bash(roleband)", "Bash(rolebAND[x] *)"]}}))
    status, _ = home.connect("claude-code", "apply")
    assert status == 0
    permissions = json.loads(home.claude.read_text())["permissions"]
    assert permissions["deny"] == ["Bash(rm *)", "Bash(*rm -rf*)", "Read(.env)"]
    assert permissions["ask"] == ["Bash(git push:*)", "Bash(rolebandx *)", "Bash(*sudo*)", "Bash(roleband)",
                                  "Bash(rolebAND[x] *)"]
    assert permissions["allow"] == ["Bash(roleband *)"]


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes through permissions")
def test_a_settings_folder_it_cannot_write_is_one_error_and_nothing_changes(home):
    home.claude.parent.mkdir()
    home.claude.write_text('{"model": "opus"}')
    home.claude.parent.chmod(0o500)
    try:
        status, envelope = home.connect("claude-code", "apply")
    finally:
        home.claude.parent.chmod(0o755)
    assert status == 1 and envelope["error"]["code"] == "internal_error", envelope
    assert "Nothing was changed" in envelope["error"]["message"]
    assert envelope["error"]["details"]["applied"] == []
    assert home.claude.read_text() == '{"model": "opus"}'


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes through permissions")
def test_a_skill_it_cannot_write_names_the_settings_already_changed(home):
    skill_folder = home.skill("claude-code").parent
    skill_folder.mkdir(parents=True)
    skill_folder.chmod(0o500)
    try:
        status, envelope = home.connect("claude-code", "apply")
    finally:
        skill_folder.chmod(0o755)
    assert status == 1 and envelope["error"]["code"] == "internal_error", envelope
    assert envelope["error"]["details"]["applied"] == [str(home.claude)]
    assert str(home.claude) in envelope["error"]["message"]
    assert json.loads(home.claude.read_text())["permissions"]["allow"] == ["Bash(roleband *)"]


def test_a_linked_settings_file_stays_a_link(home, tmp_path):
    dotfiles = tmp_path / "dotfiles" / "claude-settings.json"
    dotfiles.parent.mkdir()
    dotfiles.write_text('{"model": "opus"}')
    home.claude.parent.mkdir()
    home.claude.symlink_to(dotfiles)
    status, _ = home.connect("claude-code", "apply")
    assert status == 0
    assert home.claude.is_symlink()
    assert json.loads(dotfiles.read_text())["permissions"]["allow"] == ["Bash(roleband *)"]


# --------------------------------------------------------------------------- #
# The skill
# --------------------------------------------------------------------------- #


def test_an_edited_skill_is_not_overwritten(home):
    home.connect("claude-code", "apply")
    skill = home.skill("claude-code")
    edited = skill.read_text() + "\nAlways use --format json.\n"
    skill.write_text(edited)
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0
    assert skill.read_text() == edited
    assert _skill_of(envelope)["action"] == "kept_edited"


def test_a_skill_that_was_there_before_connect_is_the_persons(home):
    skill = home.skill("codex")
    skill.parent.mkdir(parents=True)
    skill.write_text("my own roleband notes\n")
    status, envelope = home.connect("codex", "apply")
    assert status == 0
    assert skill.read_text() == "my own roleband notes\n"
    assert _skill_of(envelope)["action"] == "kept_edited"
    assert _skill_of(envelope, TOP_PICKS)["action"] == "install"


def test_an_unedited_older_skill_is_updated(home):
    skill = home.skill("claude-code")
    skill.parent.mkdir(parents=True)
    older = b"---\nname: roleband\n---\nAn older version.\n"
    skill.write_bytes(older)
    (skill.parent / ".roleband-skill.json").write_text(
        json.dumps({"format": 1, "version": 0, "sha256": hashlib.sha256(older).hexdigest()}))
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0
    assert _skill_of(envelope)["action"] == "update"
    assert skill.read_bytes() == SHIPPED_SKILL.read_bytes()


def test_a_skill_saved_after_connect_read_it_is_kept(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    from tracker.cli import connect

    directory = tmp_path / "skills" / "roleband"
    plan = connect._skill(agent_hosts.ROLEBAND_SKILL, directory)
    assert plan.action == "install"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("written by the person meanwhile\n")
    connect._install_skill(plan, [])
    assert (directory / "SKILL.md").read_text() == "written by the person meanwhile\n"
    assert plan.action == "kept_edited"
    assert not (directory / ".roleband-skill.json").exists()


# --------------------------------------------------------------------------- #
# A skill folder, file by file
# --------------------------------------------------------------------------- #

OLDER_SETUP = b"# Setting up top picks\n\nAn older version of the setup conversation.\n"
OLDER_JUDGING = b"# Judging a posting\n\nAn older version of the judging guide.\n"


def _older_top_picks(home: Home, host: str, *, edited: set[str] = frozenset(), listed: tuple[str, ...] | None = None,
                     missing: set[str] = frozenset()) -> Path:
    """The top picks skill as an older client's connect left it: SKILL.md
    current, setup.md and judging.md at an older version. A file in `edited`
    was changed by the person since; `listed` limits the sidecar to the files
    that version had; a file in `missing` is gone from the folder."""
    folder = home.skill(host, TOP_PICKS).parent
    folder.mkdir(parents=True, exist_ok=True)
    written = {"SKILL.md": _shipped(TOP_PICKS, "SKILL.md"), "setup.md": OLDER_SETUP, "judging.md": OLDER_JUDGING}
    for name, content in written.items():
        if name not in missing:
            (folder / name).write_bytes(content + (b"My own line.\n" if name in edited else b""))
    names = listed if listed is not None else tuple(written)
    (folder / ".roleband-skill.json").write_text(json.dumps(
        {"format": 2, "version": agent_hosts.TOP_PICKS_SKILL.version - 1,
         "files": {name: _sha(written[name]) for name in names}}))
    return folder


def _actions(skill: dict) -> dict[str, str]:
    return {item["name"]: item["action"] for item in skill["files"]}


def test_connect_updates_an_unedited_older_file_and_keeps_an_edited_one_in_the_same_folder(home):
    folder = _older_top_picks(home, "claude-code", edited={"judging.md"})
    edited = (folder / "judging.md").read_bytes()
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0, envelope
    assert (folder / "setup.md").read_bytes() == _shipped(TOP_PICKS, "setup.md")
    assert (folder / "judging.md").read_bytes() == edited
    assert (folder / "SKILL.md").read_bytes() == _shipped(TOP_PICKS, "SKILL.md")
    skill = _skill_of(envelope, TOP_PICKS)
    assert skill["action"] == "update"
    assert _actions(skill) == {"SKILL.md": "unchanged", "setup.md": "update", "judging.md": "kept_edited"}
    assert "judging.md is kept as you edited it" in skill["summary"]
    # The sidecar names the new version and what connect wrote; the edited
    # file keeps the hash connect last wrote, so it stays the person's.
    assert _record(folder / "SKILL.md") == {"format": 2, "version": agent_hosts.TOP_PICKS_SKILL.version, "files": {
        "SKILL.md": _sha(_shipped(TOP_PICKS, "SKILL.md")), "setup.md": _sha(_shipped(TOP_PICKS, "setup.md")),
        "judging.md": _sha(OLDER_JUDGING)}}
    # A second connect changes nothing, the edited file included.
    before = home.files()
    status, again = home.connect("claude-code", "apply")
    assert status == 0 and home.files() == before
    assert _actions(_skill_of(again, TOP_PICKS))["judging.md"] == "kept_edited"


def test_print_names_each_file_of_a_folder_and_writes_nothing(home):
    _older_top_picks(home, "codex", edited={"setup.md"})
    before = home.files()
    status, printed = home.connect("codex", "print")
    assert status == 0 and home.files() == before
    assert _actions(_skill_of(printed, TOP_PICKS)) == {
        "SKILL.md": "unchanged", "setup.md": "kept_edited", "judging.md": "update"}
    assert printed["data"]["changed"] is True


@pytest.mark.parametrize("call", [("capabilities", "--offline"), ("picks", "status")])
def test_the_skills_first_calls_update_an_unedited_older_file_and_keep_an_edited_one(home, call):
    """`capabilities` is the roleband skill's first call and `picks status` the
    top picks skill's, so either brings an installed folder up to date, even
    with no engine to answer."""
    folder = _older_top_picks(home, "claude-code", edited={"setup.md"})
    edited = (folder / "setup.md").read_bytes()
    _, envelope = home.run(*call)
    assert (folder / "judging.md").read_bytes() == _shipped(TOP_PICKS, "judging.md")
    assert (folder / "setup.md").read_bytes() == edited
    assert _notices(envelope) == ["skill_updated"]
    message = envelope["warnings"][0]["message"]
    assert f"roleband-top-picks skill installed for claude-code is now version {agent_hosts.TOP_PICKS_SKILL.version}" \
        in message
    assert "You edited setup.md" in message
    assert _record(folder / "SKILL.md")["version"] == agent_hosts.TOP_PICKS_SKILL.version
    # Current now: the next call changes nothing and says nothing.
    before = home.files()
    _, envelope = home.run(*call)
    assert envelope["warnings"] == [] and home.files() == before


def test_a_refresh_adds_a_file_new_in_this_version_and_leaves_a_deleted_one_deleted(home):
    """The older version had no judging.md; the person deleted setup.md."""
    folder = _older_top_picks(home, "codex", listed=("SKILL.md", "setup.md"), missing={"judging.md", "setup.md"})
    _, envelope = home.run("picks", "status")
    assert (folder / "judging.md").read_bytes() == _shipped(TOP_PICKS, "judging.md")
    assert not (folder / "setup.md").exists()
    assert _notices(envelope) == ["skill_updated"]
    # Connect is the person's own act: it installs the file they deleted.
    status, envelope = home.connect("codex", "apply")
    assert status == 0
    assert (folder / "setup.md").read_bytes() == _shipped(TOP_PICKS, "setup.md")


def test_a_refresh_with_every_differing_file_edited_changes_nothing_and_says_so(home):
    folder = _older_top_picks(home, "claude-code", edited={"setup.md", "judging.md"})
    before = home.files()
    _, envelope = home.run("picks", "status")
    assert home.files() == before
    assert _notices(envelope) == ["skill_outdated"]
    assert str(folder) in envelope["warnings"][0]["message"]


def test_a_folder_file_saved_after_connect_read_it_is_kept(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    from tracker.cli import connect

    directory = tmp_path / "skills" / TOP_PICKS
    plan = connect._skill(agent_hosts.TOP_PICKS_SKILL, directory)
    assert plan.action == "install"
    directory.mkdir(parents=True)
    (directory / "judging.md").write_text("written by the person meanwhile\n")
    written: list[str] = []
    connect._install_skill(plan, written)
    assert (directory / "judging.md").read_text() == "written by the person meanwhile\n"
    assert (directory / "setup.md").read_bytes() == _shipped(TOP_PICKS, "setup.md")
    assert "judging.md" not in json.loads((directory / ".roleband-skill.json").read_text())["files"]
    assert str(directory / "judging.md") not in written


def test_an_empty_file_the_person_links_after_connect_read_it_is_kept(tmp_path, monkeypatch):
    """An empty file connect wrote plans as an update; once the person puts a
    link in its place, the link and what it points to are theirs."""
    monkeypatch.syspath_prepend(str(BACKEND))
    from tracker.cli import connect

    directory = tmp_path / "skills" / TOP_PICKS
    directory.mkdir(parents=True)
    (directory / "setup.md").write_bytes(b"")
    (directory / ".roleband-skill.json").write_text(json.dumps(
        {"format": 2, "version": agent_hosts.TOP_PICKS_SKILL.version - 1, "files": {"setup.md": _sha(b"")}}))
    plan = connect._skill(agent_hosts.TOP_PICKS_SKILL, directory)
    assert _plan_actions(plan)["setup.md"] == "update"
    target = tmp_path / "setup-of-my-own"
    target.write_bytes(b"")
    (directory / "setup.md").unlink()
    (directory / "setup.md").symlink_to(target)
    written: list[str] = []
    connect._install_skill(plan, written)
    assert (directory / "setup.md").is_symlink() and target.read_bytes() == b""
    assert _plan_actions(plan)["setup.md"] == "kept_edited"
    assert str(directory / "setup.md") not in written
    assert (directory / "judging.md").read_bytes() == _shipped(TOP_PICKS, "judging.md")


def test_a_refresh_records_files_already_at_this_version_when_their_sidecar_did_not_save(home):
    """The files were updated but the sidecar kept the older hashes: the next
    refresh records them, so the release after this one can update them. A
    file the person edited keeps the hash connect last wrote."""
    folder = _older_top_picks(home, "claude-code", edited={"judging.md"})
    (folder / "setup.md").write_bytes(_shipped(TOP_PICKS, "setup.md"))
    before = home.files()
    _, envelope = home.run("picks", "status")
    assert {path: data for path, data in home.files().items() if not path.endswith(".roleband-skill.json")} == {
        path: data for path, data in before.items() if not path.endswith(".roleband-skill.json")}
    assert _record(folder / "SKILL.md") == {"format": 2, "version": agent_hosts.TOP_PICKS_SKILL.version, "files": {
        "SKILL.md": _sha(_shipped(TOP_PICKS, "SKILL.md")), "setup.md": _sha(_shipped(TOP_PICKS, "setup.md")),
        "judging.md": _sha(OLDER_JUDGING)}}
    assert _notices(envelope) == ["skill_updated"]
    assert "You edited judging.md" in envelope["warnings"][0]["message"]


def _plan_actions(plan) -> dict[str, str]:
    return {item.name: item.action for item in plan.files}


def test_every_shipped_skill_file_is_one_connect_installs():
    """A file added to a skill folder without naming it in `SKILLS` would
    never reach a host, and a named file that is gone would fail connect."""
    assert sorted(path.name for path in SKILLS_SOURCE.iterdir() if path.is_dir()) == sorted(
        skill.name for skill in agent_hosts.SKILLS)
    for skill in agent_hosts.SKILLS:
        shipped = sorted(path.name for path in skill.source.iterdir() if not path.name.startswith("."))
        assert shipped == sorted(skill.files), skill.name


# --------------------------------------------------------------------------- #
# Keeping an installed skill current without a second connect
# --------------------------------------------------------------------------- #

OLDER_SKILL = b"---\nname: roleband\n---\n<!-- roleband skill, version 4. -->\nAn older version.\n"


def _installed(home: Home, host: str, content: bytes, *, version: int, recorded: bytes | None = None) -> Path:
    """The roleband skill as `connect` of `version` left it, in the one-file
    sidecar an older client writes; `recorded` is what it wrote, when the
    file has changed since."""
    skill = home.skill(host)
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_bytes(content)
    sha = hashlib.sha256(recorded if recorded is not None else content).hexdigest()
    (skill.parent / ".roleband-skill.json").write_text(json.dumps({"format": 1, "version": version, "sha256": sha}))
    return skill


def _record(skill: Path) -> dict:
    return json.loads((skill.parent / ".roleband-skill.json").read_text())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _notices(envelope: dict) -> list[str]:
    return [notice["code"] for notice in envelope["warnings"]]


def test_capabilities_updates_an_unedited_older_skill_for_each_host(home):
    claude = _installed(home, "claude-code", OLDER_SKILL, version=SKILL_VERSION - 1)
    codex = _installed(home, "codex", OLDER_SKILL, version=SKILL_VERSION - 1)
    status, envelope = home.run("capabilities", "--offline")
    assert status == 0 and envelope["ok"] is True
    for skill in (claude, codex):
        assert skill.read_bytes() == SHIPPED_SKILL.read_bytes()
        assert _record(skill) == {"format": 2, "version": SKILL_VERSION,
                                  "files": {"SKILL.md": _sha(SHIPPED_SKILL.read_bytes())}}
        # A skill connect never installed here is left to connect.
        assert not (skill.parent.parent / TOP_PICKS).exists()
    assert _notices(envelope) == ["skill_updated", "skill_updated"]
    assert f"now version {SKILL_VERSION}" in envelope["warnings"][0]["message"]
    # Current now: a second call changes nothing and says nothing.
    before = home.files()
    status, envelope = home.run("capabilities", "--offline")
    assert status == 0 and envelope["warnings"] == [] and home.files() == before


def test_capabilities_keeps_an_edited_older_skill_and_says_so(home):
    edited = OLDER_SKILL + b"Always answer in French.\n"
    skill = _installed(home, "claude-code", edited, version=SKILL_VERSION - 1, recorded=OLDER_SKILL)
    before = home.files()
    status, envelope = home.run("capabilities", "--offline")
    assert status == 0
    assert home.files() == before
    assert _notices(envelope) == ["skill_outdated"]
    assert str(skill) in envelope["warnings"][0]["message"]


@pytest.mark.parametrize("case", ["newer", "unrecorded", "deleted", "other_command"])
def test_capabilities_leaves_alone_a_skill_it_does_not_own_at_an_older_version(home, case):
    """A newer client's copy (two clients on one computer would trade the file
    back and forth), a copy connect never installed, one the person deleted,
    and any call but capabilities."""
    skill = _installed(home, "codex", OLDER_SKILL, version=SKILL_VERSION + 1 if case == "newer" else SKILL_VERSION - 1)
    if case == "unrecorded":
        (skill.parent / ".roleband-skill.json").unlink()
    if case == "deleted":
        skill.unlink()
    before = home.files()
    status, envelope = home.run(*(("describe", "status", "--offline") if case == "other_command"
                                  else ("capabilities", "--offline")))
    assert status == 0
    assert home.files() == before
    assert envelope["warnings"] == []


def test_a_newer_client_installing_meanwhile_keeps_its_copy(tmp_path, monkeypatch):
    """The record said an older version; by the time the copy is read, a newer
    client has replaced both the file and its record."""
    monkeypatch.syspath_prepend(str(BACKEND))
    from tracker.cli import connect

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    directory = tmp_path / "claude" / "skills" / "roleband"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_bytes(OLDER_SKILL)
    (directory / ".roleband-skill.json").write_text(json.dumps(
        {"format": 1, "version": SKILL_VERSION - 1, "sha256": hashlib.sha256(OLDER_SKILL).hexdigest()}))
    newer = b"---\nname: roleband\n---\nA newer version.\n"
    planned = connect._skill

    def newer_client_installs_first(skill: agent_hosts.Skill, path: Path) -> connect.SkillPlan:
        (path / "SKILL.md").write_bytes(newer)
        (path / ".roleband-skill.json").write_text(json.dumps(
            {"format": 2, "version": SKILL_VERSION + 1, "files": {"SKILL.md": hashlib.sha256(newer).hexdigest()}}))
        return planned(skill, path)

    monkeypatch.setattr(connect, "_skill", newer_client_installs_first)
    assert connect.refresh_installed_skills() == []
    assert (directory / "SKILL.md").read_bytes() == newer
    assert json.loads((directory / ".roleband-skill.json").read_text())["version"] == SKILL_VERSION + 1


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes through a read-only folder")
def test_a_skill_that_cannot_be_written_leaves_capabilities_answering(home):
    skill = _installed(home, "codex", OLDER_SKILL, version=SKILL_VERSION - 1)
    skill.parent.chmod(0o500)
    try:
        status, envelope = home.run("capabilities", "--offline")
    finally:
        skill.parent.chmod(0o700)
    assert status == 0 and envelope["ok"] is True
    assert skill.read_bytes() == OLDER_SKILL
    assert _notices(envelope) == ["skill_outdated"]
    assert "roleband connect codex --apply" in envelope["warnings"][0]["message"]


def test_capabilities_refreshes_the_skill_when_no_engine_answers(home):
    skill = _installed(home, "claude-code", OLDER_SKILL, version=SKILL_VERSION - 1)
    status, envelope = home.run("capabilities")
    assert status == 2 and envelope["error"]["code"] == "context_required"
    assert skill.read_bytes() == SHIPPED_SKILL.read_bytes()
    assert _notices(envelope) == ["skill_updated"]


def test_the_shipped_skill_starts_from_capabilities_and_describe():
    text = SHIPPED_SKILL.read_text()
    assert text.startswith("---\nname: roleband\ndescription: ")
    first, second = [line for line in text.splitlines() if line.startswith(("1. ", "2. "))][:2]
    assert "`capabilities` command" in first
    assert "`describe` command with an id" in second
    # A small model given a tool copies a backticked `roleband capabilities --json`
    # here into the tool's name; the opening steps name the command word alone.
    assert "`roleband " not in first + second
    assert f"<!-- roleband skill, version {SKILL_VERSION}." in text


def test_the_shipped_skill_says_any_answer_names_its_continuation_and_exit_9_is_partial():
    text = SHIPPED_SKILL.read_text()
    assert "Any answer may end in more to read. Its `data.continue_with`" in text
    rows = {line.split("|")[1].strip(): line for line in text.splitlines() if line.startswith("| ")}
    assert "not a failure" in rows["9"]
    # The index names what the person turned off; describe no longer carries the output schema.
    assert "`data.unavailable`" in text
    assert "input and output schemas" not in text


def _skill_commands() -> list[str]:
    """Every whole `roleband ...` command line the skill shows, piped input
    dropped, leaving out those with a placeholder (ID, OPERATION) or `...`,
    and the mention of `roleband connect`, which the person runs, not the agent."""
    import re

    lines = []
    for text in SHIPPED_SKILL.read_text().splitlines():
        for span in re.findall(r"`([^`]+)`", text):
            line = span.split("| ", 1)[-1]
            words = line.split()
            if (len(words) > 1 and words[0] == "roleband" and words[1] != "connect" and "..." not in line
                    and not any(w.isupper() and w.isalpha() for w in words)):
                lines.append(line)
    return lines


def test_every_command_the_skill_shows_is_one_the_client_takes():
    """The skill's examples are what agents copy: each one parses, and its
    clearing write sends the explicit null with the revision from its flag."""
    import io

    from tracker.cli import commands
    from tracker.cli.main import build_parser

    shown = _skill_commands()
    assert any(line.startswith("roleband pursuits patch") for line in shown), shown
    parser = build_parser()
    for line in shown:
        args = parser.parse_args(line.split()[1:])
        generated = getattr(args, "generated", None)
        if generated is not None and generated.operation == "pursuits.patch":
            sent = commands.payload(generated, args, stdin=io.StringIO('{"next_action_due": null}'))
            assert sent == {"next_action_due": None, "if_revision": 12, "opportunity_id": 4821}
            assert generated.keyed and args.idempotency_key


# --------------------------------------------------------------------------- #
# Codex
# --------------------------------------------------------------------------- #


def test_codex_gets_network_access_and_keeps_everything_else(home):
    home.codex.parent.mkdir()
    original = (
        'model = "gpt-6"\nsandbox_mode = "workspace-write"\n\n'
        '[sandbox_workspace_write]  # my sandbox\nwritable_roots = ["/tmp/work"]\n\n'
        '[mcp_servers.docs]\ncommand = "docs-server"\n'
    )
    home.codex.write_text(original)
    status, envelope = home.connect("codex", "apply")
    assert status == 0, envelope
    merged = tomllib.loads(home.codex.read_text())
    expected = tomllib.loads(original)
    expected["sandbox_workspace_write"]["network_access"] = True
    assert merged == expected
    assert "# my sandbox" in home.codex.read_text()
    [backup] = _backups(home.codex)
    assert backup.read_text() == original
    assert "opens all network access" in envelope["data"]["cost"]
    assert envelope["data"]["files"][0]["notes"] == []
    second_before = home.files()
    status, again = home.connect("codex", "apply")
    assert status == 0 and again["data"]["changed"] is False
    assert home.files() == second_before


def test_codex_without_the_table_gets_it_appended(home):
    home.codex.parent.mkdir()
    home.codex.write_text('model = "gpt-6"')
    status, envelope = home.connect("codex", "apply")
    assert status == 0
    assert tomllib.loads(home.codex.read_text()) == {
        "model": "gpt-6", "sandbox_workspace_write": {"network_access": True}}
    note = envelope["data"]["files"][0]["notes"][0]
    assert "sandbox_mode is not set" in note


@pytest.mark.parametrize("content", [
    "[sandbox_workspace_write]\nnetwork_access = false\n",
    "sandbox_workspace_write = { writable_roots = [] }\n",
    'sandbox_workspace_write.writable_roots = ["/tmp"]\n',
])
def test_a_codex_setting_written_another_way_is_the_persons_to_change(home, content):
    home.codex.parent.mkdir()
    home.codex.write_text(content)
    status, envelope = home.connect("codex", "apply")
    assert status == 7 and envelope["error"]["code"] == "approval_required", envelope
    assert "network_access = true" in envelope["error"]["message"]
    assert home.codex.read_text() == content
    assert _backups(home.codex) == []


def test_codex_config_that_is_not_toml_is_left_untouched(home):
    home.codex.parent.mkdir()
    home.codex.write_text("model = \n")
    status, envelope = home.connect("codex", "apply")
    assert status == 2 and envelope["error"]["code"] == "invalid_input"
    assert home.codex.read_text() == "model = \n"


# --------------------------------------------------------------------------- #
# Hosts and the command on PATH
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("host", ["gemini", "cursor"])
def test_an_untested_host_is_refused_and_nothing_is_written(home, host):
    status, envelope = home.connect(host, "apply")
    assert status == 2
    assert envelope["error"]["code"] == "unsupported_host"
    assert envelope["error"]["details"]["supported"] == ["claude-code", "codex"]
    assert home.files() == {}


@pytest.mark.parametrize(("variable", "value", "host"), [
    ("CLAUDECODE", "1", "claude-code"), ("CODEX_THREAD_ID", "019a7c1e", "codex"), ("CODEX_SANDBOX", "seatbelt", "codex"),
])
def test_connect_with_no_host_connects_the_assistant_it_runs_in(home, variable, value, host):
    status, envelope = home.connect(None, "apply", env={variable: value})
    assert status == 0 and envelope["ok"], envelope
    assert envelope["data"]["host"] == host and envelope["data"]["host_detected"] is True
    assert home.skill(host, TOP_PICKS).read_bytes() == _shipped(TOP_PICKS, "SKILL.md")
    other = home.root / (".codex" if host == "claude-code" else ".claude")
    assert not other.exists()
    if host == "claude-code":
        assert json.loads(home.claude.read_text())["permissions"]["allow"] == ["Bash(roleband *)"]
    else:
        assert "network_access = true" in home.codex.read_text()


@pytest.mark.parametrize("env", [{}, {"CLAUDECODE": "0"}, {"CODEX_THREAD_ID": ""}, {"TERM_PROGRAM": "Apple_Terminal"}])
@pytest.mark.parametrize("mode", ["apply", "print"])
def test_connect_with_no_host_outside_an_assistant_is_refused_and_writes_nothing(home, env, mode):
    status, envelope = home.connect(None, mode, env=env)
    assert status == 2 and envelope["error"]["code"] == "invalid_arguments", envelope
    assert "roleband connect claude-code --apply" in envelope["error"]["message"]
    assert envelope["error"]["details"]["supported"] == ["claude-code", "codex"]
    assert home.files() == {}


def test_a_named_host_wins_over_the_assistant_it_runs_in(home):
    status, envelope = home.connect("codex", "apply", env={"CLAUDECODE": "1"})
    assert status == 0
    assert envelope["data"]["host"] == "codex" and envelope["data"]["host_detected"] is False
    assert home.codex.exists() and not home.claude.exists()


def test_human_output_says_which_assistant_connect_found(home):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home.root), "PYTHONPATH": str(BACKEND), "LANG": "en_US.UTF-8",
           "CLAUDECODE": "1"}
    process = subprocess.run([sys.executable, "-m", "tracker.cli", "connect", "--print", "--format", "human"],
                             cwd=home.root, env=env, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    assert process.stdout.startswith("claude-code (the host this runs in): what --apply would change")
    assert "the roleband-top-picks skill, version 1, installs" in process.stdout


def test_connect_reports_whether_the_command_is_on_path(home):
    folder = home.root / ".local" / "bin"
    _, off = home.connect("codex", "print")
    command = off["data"]["command"]
    assert command["on_path"] is False and command["present"] is False
    assert any("not on your PATH" in note for note in command["notes"])
    _, on = home.connect("codex", "print", path=f"/usr/bin:{folder}")
    assert on["data"]["command"]["on_path"] is True
    assert not any("PATH" in note for note in on["data"]["command"]["notes"])


def test_human_output_shows_the_diff_and_the_cost(home):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home.root), "PYTHONPATH": str(BACKEND), "LANG": "en_US.UTF-8"}
    process = subprocess.run([sys.executable, "-m", "tracker.cli", "connect", "claude-code", "--print",
                              "--format", "human"], cwd=home.root, env=env, capture_output=True, text=True,
                             timeout=30)
    assert process.returncode == 0, process.stderr
    assert "what --apply would change" in process.stdout
    assert '+      "Bash(roleband *)"' in process.stdout
    assert "Cost: " in process.stdout
    assert not os.path.exists(home.claude)

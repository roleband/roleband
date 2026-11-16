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

BACKEND = Path(__file__).resolve().parents[1]
SHIPPED_SKILL = BACKEND / "tracker" / "cli" / "skills" / "roleband" / "SKILL.md"

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

    def skill(self, host: str) -> Path:
        return self.root / (".claude" if host == "claude-code" else ".codex") / "skills" / "roleband" / "SKILL.md"

    def files(self) -> dict[str, bytes]:
        """Every file under the home, by relative path."""
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in sorted(self.root.rglob("*")) if path.is_file()}

    def connect(self, host: str, mode: str, *, path: str | None = None) -> tuple[int, dict]:
        env = {
            "PATH": path if path is not None else "/usr/bin:/bin",
            "HOME": str(self.root),
            "PYTHONPATH": str(BACKEND),
            "LANG": "en_US.UTF-8",
            "ROLEBAND_CLI_CONFIG": str(self.root / "no-contexts.json"),
        }
        process = subprocess.run(
            [sys.executable, "-m", "tracker.cli", "connect", host, f"--{mode}", "--json"],
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
    data = envelope["data"]
    assert data["files"][0]["action"] == "create" and data["files"][0]["backup"] is None
    assert data["skill"]["action"] == "install"
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
    assert envelope["data"]["skill"]["action"] == "unchanged"


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
    assert printed["data"]["skill"]["action"] == "install"
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
    assert envelope["data"]["skill"]["action"] == "kept_edited"


def test_a_skill_that_was_there_before_connect_is_the_persons(home):
    skill = home.skill("codex")
    skill.parent.mkdir(parents=True)
    skill.write_text("my own roleband notes\n")
    status, envelope = home.connect("codex", "apply")
    assert status == 0
    assert skill.read_text() == "my own roleband notes\n"
    assert envelope["data"]["skill"]["action"] == "kept_edited"


def test_an_unedited_older_skill_is_updated(home):
    skill = home.skill("claude-code")
    skill.parent.mkdir(parents=True)
    older = b"---\nname: roleband\n---\nAn older version.\n"
    skill.write_bytes(older)
    (skill.parent / ".roleband-skill.json").write_text(
        json.dumps({"format": 1, "version": 0, "sha256": hashlib.sha256(older).hexdigest()}))
    status, envelope = home.connect("claude-code", "apply")
    assert status == 0
    assert envelope["data"]["skill"]["action"] == "update"
    assert skill.read_bytes() == SHIPPED_SKILL.read_bytes()


def test_a_skill_saved_after_connect_read_it_is_kept(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    from tracker.cli import connect

    directory = tmp_path / "skills" / "roleband"
    plan = connect._skill(directory)
    assert plan.action == "install"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("written by the person meanwhile\n")
    connect._install_skill(plan, [])
    assert (directory / "SKILL.md").read_text() == "written by the person meanwhile\n"
    assert plan.action == "kept_edited"
    assert not (directory / ".roleband-skill.json").exists()


def test_the_shipped_skill_starts_from_capabilities_and_describe():
    text = SHIPPED_SKILL.read_text()
    assert text.startswith("---\nname: roleband\ndescription: ")
    first, second = [line for line in text.splitlines() if line.startswith(("1. ", "2. "))][:2]
    assert "`capabilities` command" in first
    assert "`describe` command with an id" in second
    # A small model given a tool copies a backticked `roleband capabilities --json`
    # here into the tool's name; the opening steps name the command word alone.
    assert "`roleband " not in first + second
    from tracker.cli.connect import SKILL_VERSION

    assert f"<!-- roleband skill, version {SKILL_VERSION}." in text


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

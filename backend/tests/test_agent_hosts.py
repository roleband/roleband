"""What Settings reads from each agent host's own files, against what `roleband connect` writes.

Every case runs in a scratch home (`HOME`, `CLAUDE_CONFIG_DIR` and `CODEX_HOME` point into
`tmp_path`), and the connected state is made by `connect --apply` itself, so the reader is
held to the writer: a change to what `connect` writes that the reader does not follow fails here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from tracker.cli import connect
from tracker.platform import agent_hosts
from tracker.platform.agent_hosts import caller, connection, running_host


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("PATH", f"{root / '.local' / 'bin'}:/usr/bin:/bin")
    return root


def _connect(host: str) -> None:
    connect.run(argparse.Namespace(host=host, connect_mode="apply"))


@pytest.mark.parametrize("host", agent_hosts.HOSTS)
def test_a_host_connect_set_up_reads_as_connected_and_one_it_did_not_reads_as_nothing(home, host):
    assert connection(host) is None
    _connect(host)
    assert connection(host) == "connected"
    # The other host's files were not touched, so it still reads as never connected.
    other = next(name for name in agent_hosts.HOSTS if name != host)
    assert connection(other) is None


def test_claude_code_without_its_permission_rule_asks_before_each_command(home):
    _connect("claude-code")
    settings = home / ".claude" / "settings.json"
    document = json.loads(settings.read_text())
    document["permissions"]["allow"].remove(agent_hosts.CLAUDE_RULE)
    settings.write_text(json.dumps(document))
    assert connection("claude-code") == "rule_missing"
    # The sandbox exclusion alone does not let the command run without asking either.
    document["permissions"]["allow"].append(agent_hosts.CLAUDE_RULE)
    document["sandbox"]["excludedCommands"] = []
    settings.write_text(json.dumps(document))
    assert connection("claude-code") == "rule_missing"


def test_codex_with_its_network_closed_again_reads_as_rule_missing(home):
    _connect("codex")
    config = home / ".codex" / "config.toml"
    config.write_text(config.read_text().replace("network_access = true", "network_access = false"))
    assert connection("codex") == "rule_missing"


@pytest.mark.parametrize("text", ["{not json", "[]", "\xff\xfe"])
def test_a_settings_file_that_cannot_be_read_counts_as_no_rule_and_never_raises(home, text):
    _connect("claude-code")
    (home / ".claude" / "settings.json").write_bytes(text.encode("latin-1"))
    assert connection("claude-code") == "rule_missing"


def _make_older(directory: Path, *, edited: bool) -> None:
    """Rewrite the installed skill as an older version's unedited copy, or as the person's edit of it."""
    older = b"<!-- roleband skill, an older version -->\n"
    (directory / "SKILL.md").write_bytes(older + (b"my own notes\n" if edited else b""))
    record = {"format": 1, "version": agent_hosts.SKILL_VERSION - 1, "sha256": hashlib.sha256(older).hexdigest()}
    (directory / agent_hosts.SKILL_RECORD).write_text(json.dumps(record))


@pytest.mark.parametrize("host", agent_hosts.HOSTS)
def test_an_unedited_older_skill_reads_as_outdated_and_an_edited_one_does_not(home, host):
    _connect(host)
    directory = agent_hosts.skill_dir(host)
    _make_older(directory, edited=False)
    assert connection(host) == "outdated"
    # Connect never replaces the person's edit, so offering an update for it would offer nothing.
    _make_older(directory, edited=True)
    assert connection(host) == "connected"
    # The update connect makes is the one the state asked for.
    _make_older(directory, edited=False)
    _connect(host)
    assert connection(host) == "connected"


def test_a_host_whose_skill_was_deleted_reads_as_never_connected_whatever_its_settings_say(home):
    _connect("claude-code")
    (agent_hosts.skill_dir("claude-code") / "SKILL.md").unlink()
    assert connection("claude-code") is None


def test_the_hosts_own_folder_variables_are_read(home, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "elsewhere"))
    _connect("claude-code")
    assert (tmp_path / "elsewhere" / "settings.json").exists()
    assert connection("claude-code") == "connected"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert connection("claude-code") is None


@pytest.mark.parametrize(
    ("environ", "host"),
    [
        ({"CLAUDECODE": "1"}, "claude-code"),
        ({"CODEX_THREAD_ID": "019a7c1e"}, "codex"),
        ({"CODEX_SANDBOX": "seatbelt"}, "codex"),
        ({"CODEX_SANDBOX_NETWORK_DISABLED": "1"}, "codex"),
        ({"CLAUDECODE": "0"}, None),
        ({"CODEX_THREAD_ID": ""}, None),
        ({"TERM": "xterm-256color"}, None),
    ],
)
def test_the_running_host_is_named_by_its_own_variable(environ, host):
    assert running_host(environ) == host


@pytest.mark.parametrize(
    ("header", "recorded"),
    [("claude-code", "claude-code"), ("codex", "codex"), (None, "other"), ("", "other"),
     ("gemini", "other"), ("Claude-Code", "other"), ("other", "other")],
)
def test_a_request_names_a_known_host_or_counts_as_another_app(header, recorded):
    assert caller(header) == recorded

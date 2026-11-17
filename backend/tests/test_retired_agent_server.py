"""The entry point agent hosts set up for the MCP server still launch.

`python -m tracker.mcp.server` serves nothing: it says which `roleband connect`
command replaces it, on standard error where a host shows a server's start-up
output, and exits non-zero so the host reports that the server did not start.
Standard output stays empty, since a host reads it as protocol messages. The
module imports nothing but `sys`, so it runs with no engine, no database and no
MCP package installed.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tracker.cli import connect
from tracker.mcp import server

BACKEND = Path(__file__).resolve().parents[1]


def imported_modules(source: str) -> set[str]:
    """Every module a source file imports, at any depth of the file."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


def _run(*argv: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("ROLEBAND_", "PYTHON"))}
    return subprocess.run([sys.executable, *argv], cwd=BACKEND, env=env, capture_output=True, text=True,
                          timeout=60, stdin=subprocess.DEVNULL)


def test_the_entry_point_imports_nothing_but_sys():
    assert imported_modules(Path(server.__file__).read_text(encoding="utf-8")) <= {"__future__", "sys"}
    # The control: the check sees an import anywhere in the file.
    assert "mcp.server.fastmcp" in imported_modules("def f():\n    from mcp.server.fastmcp import FastMCP\n")


@pytest.mark.parametrize("argv", [("-m", "tracker.mcp.server"), ("-I", "packaged.py", "mcp.server")],
                         ids=["source", "packaged"])
def test_a_host_launching_the_server_is_told_what_replaces_it(argv):
    result = _run(*argv)

    # A literal, not the module's constant: a test that reads the value it checks cannot see it change.
    assert result.returncode == 2
    assert result.stdout == ""
    for host in connect.HOSTS:
        assert f"roleband connect {host} --apply" in result.stderr
    # The control: no host `connect` refuses is suggested.
    assert not any(host in result.stderr for host in connect.UNTESTED)

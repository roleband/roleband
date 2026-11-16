"""The entry point an agent host's older settings launch: it tells the person to switch to `roleband`.

Agent hosts set up for RoleBand's MCP server still start `python -m tracker.mcp.server`, or
`packaged.py mcp.server` inside the app. Agents now reach RoleBand through the `roleband` command
(docs/cli.md), so this program serves nothing: it writes how to switch to standard error, where
a host shows a server's start-up output, and exits with `EXIT_STATUS`. Standard output stays empty,
since a host reads it as protocol messages.

It imports nothing beyond `sys`, so it runs with no engine, no database and no MCP package.
"""

from __future__ import annotations

import sys

#: Not zero, so a host reports that the server did not start.
EXIT_STATUS = 2

MESSAGE = """\
RoleBand no longer runs an MCP server. Agents use the `roleband` command instead.

Remove the `roleband` server from this app's MCP settings, then set the app up with one of:

    roleband connect claude-code --apply
    roleband connect codex --apply

RoleBand's Settings > AI shows the same commands.
"""


def main() -> int:
    sys.stderr.write(MESSAGE)
    return EXIT_STATUS


if __name__ == "__main__":
    sys.exit(main())

"""Printing an envelope: one JSON object, or text for a person.

JSON mode writes exactly one object and a newline to stdout, failures
included. Human mode writes a result to stdout and a failure to stderr, and
escapes every control character in text it did not write itself, so a
posting's title cannot move the cursor or recolour the terminal. No colour is
ever written.
"""

from __future__ import annotations

import json
import re
from typing import Any, TextIO

#: C0 and C1 controls, DEL, and the bidirectional overrides and isolates.
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f‪-‮⁦-⁩]")


def escape(value: object) -> str:
    """`value` as text that cannot steer the terminal."""
    return _CONTROL.sub(lambda match: f"\\u{ord(match.group()):04x}", str(value))


def write_json(envelope: dict[str, Any], stdout: TextIO) -> None:
    stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def write_human(envelope: dict[str, Any], stdout: TextIO, stderr: TextIO) -> None:
    if not envelope["ok"]:
        error = envelope["error"]
        stderr.write(f"error: {escape(error['message'])} ({escape(error['code'])})\n")
        for key, value in sorted(error.get("details", {}).items()):
            stderr.write(f"  {escape(key)}: {escape(value)}\n")
        stderr.flush()
        return
    try:
        lines = _HUMAN.get(envelope["operation"], _generic)(envelope["data"])
    except (KeyError, TypeError, AttributeError):
        # A newer engine's shape this client cannot lay out: show it as data.
        lines = _generic(envelope["data"])
    stdout.write("".join(f"{line}\n" for line in lines))
    stdout.flush()


def _status(data: dict[str, Any]) -> list[str]:
    trust = data["trust"]
    access = data["access"]
    return [
        f"workspace       {escape(data['workspace_id'])}",
        f"engine session  {escape(data['engine_session_id'])}",
        f"engine version  {escape(data['engine_version'])}",
        f"contract        {escape(data['contract_version'])}",
        f"trust           {escape(trust['mode'])}{'' if trust['verified'] else ' (unverified)'}",
        f"agent access    {'on' if access['enabled'] else 'off'}, changes {'allowed' if access['allow_writes'] else 'off'}",
    ]


def _capabilities(data: dict[str, Any]) -> list[str]:
    source = data["metadata_source"]
    lines = [f"contract {escape(data['contract_version'])}, metadata from {escape(source)}"]
    for entry in data["operations"]:
        state = entry["availability"]["state"]
        lines.append(f"  {escape(entry['operation']):<16} {escape(state):<12} {escape(entry['summary'])}")
    return lines


def _describe(data: dict[str, Any]) -> list[str]:
    effects = [name for name, on in data["engine_effects"].items() if on]
    return [
        f"{escape(data['operation'])}: {escape(data['summary'])}",
        f"  access         {escape(data['access'])} ({', '.join(escape(s) for s in data['required_scopes'])})",
        f"  availability   {escape(data['availability']['state'])}",
        f"  engine effects {', '.join(escape(e) for e in effects) or 'none'}",
        f"  client effects {', '.join(escape(e) for e in data['client_effects']) or 'none'}",
        f"  data classes   {', '.join(escape(d) for d in data['data_classes']) or 'none'}",
        f"  tool tiers     {', '.join(escape(t) for t in data['tool_tiers'])}",
        f"  metadata from  {escape(data['metadata_source'])}",
    ]


def _generic(data: object) -> list[str]:
    return [escape(line) for line in json.dumps(data, ensure_ascii=False, indent=2).splitlines()]


_HUMAN = {"status": _status, "capabilities": _capabilities, "describe": _describe}

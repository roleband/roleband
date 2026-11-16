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
    meta = envelope.get("meta")
    following = meta.get("next_cursor") if isinstance(meta, dict) else None
    if isinstance(following, str):
        lines = [*lines, f"more: --cursor {escape(following)}"]
    stdout.write("".join(f"{line}\n" for line in lines))
    stdout.flush()
    # A warning qualifies the result (a shortened page, a cut ranking), so a person sees it too.
    notices = envelope.get("warnings")
    for notice in notices if isinstance(notices, list) else []:
        if isinstance(notice, dict) and "message" in notice:
            stderr.write(f"warning: {escape(notice['message'])}\n")
    stderr.flush()


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
    if "resources" in data:
        unavailable = data.get("unavailable")
        for name, resource in data["resources"].items():
            lines.append(f"  {escape(name)}: {escape(resource['summary'])}")
            for operation in resource["operations"]:
                state = "unknown" if unavailable is None else (
                    "unavailable" if operation in unavailable else "available")
                lines.append(f"    {escape(operation):<28} {escape(state)}")
        return lines
    for entry in data["operations"]:
        state = entry["availability"]["state"]
        lines.append(f"  {escape(entry['operation']):<16} {escape(state):<12} {escape(entry['summary'])}")
    return lines


def _describe(data: dict[str, Any]) -> list[str]:
    effects = [name for name, on in data["engine_effects"].items() if on]
    lines = [
        f"{escape(data['operation'])}: {escape(data['summary'])}",
        f"  access         {escape(data['access'])} ({', '.join(escape(s) for s in data['required_scopes'])})",
        f"  availability   {escape(data['availability']['state'])}",
        f"  engine effects {', '.join(escape(e) for e in effects) or 'none'}",
        f"  client effects {', '.join(escape(e) for e in data['client_effects']) or 'none'}",
        f"  data classes   {', '.join(escape(d) for d in data['data_classes']) or 'none'}",
        f"  tool tiers     {', '.join(escape(t) for t in data['tool_tiers'])}",
        f"  metadata from  {escape(data['metadata_source'])}",
    ]
    if "output_schema" not in data:
        lines.append(f"  output schema  roleband describe {escape(data['operation'])} --view full")
    return lines


def _generic(data: object) -> list[str]:
    return [escape(line) for line in json.dumps(data, ensure_ascii=False, indent=2).splitlines()]


def _connect(data: dict[str, Any]) -> list[str]:
    from tracker.cli.connect import human_lines

    return human_lines(data, escape)


#: How a page's order reads, descending and ascending.
_ORDERS = {
    "best_match": ("best match first", "best match last"),
    "newest": ("newest first", "oldest first"),
    "age": ("listed longest first", "listed most recently first"),
    "pay": ("stated pay high to low", "stated pay low to high"),
    "estimated_pay": ("estimate high to low", "estimate low to high"),
    "level": ("level high to low", "level low to high"),
}


def _order(sort: str, order: str) -> str:
    if sort in _ORDERS:
        return _ORDERS[sort][1 if order == "asc" else 0]
    return f"{escape(sort.replace('_', ' '))} {'A to Z' if order == 'asc' else 'Z to A'}"


def _search(data: dict[str, Any]) -> list[str]:
    columns = data["columns"]
    lines = [f"{data['count']} of {data['total']}, {_order(data['sort'], data['order'])}"]
    for values in data["rows"]:
        row = dict(zip(columns, values, strict=True))
        place = row["location"]
        if place is not None and row["more_locations"]:
            place = f"{place} +{row['more_locations']}"
        parts = [
            row["title"], row["company"], place, row["workplace"], row["level"],
            None if row["listed_days"] is None else f"{row['listed_days']}d",
            None if row["stated_pay"] is None else f"stated {row['stated_pay']}",
            # A column of a category the person does not share is absent.
            None if row.get("estimated_pay") is None else f"estimate {row['estimated_pay']}",
            row.get("pursuit"),
        ]
        lines.append(f"{escape(row['id']):>7}  " + " · ".join(escape(part) for part in parts if part is not None))
    return lines


def _vocabulary(data: dict[str, Any]) -> list[str]:
    lines = [f"{data['count']} of {data['total']} {escape(data['kind'])} values, most open roles first"]
    for entry in data["items"]:
        also = f" (also {', '.join(escape(name) for name in entry['also'])})" if entry["also"] else ""
        lines.append(
            f"  {escape(entry['value']):<28} {entry['open_roles']:>6} open  {escape(entry['name'] or '')}{also}"
        )
    return lines


_HUMAN = {
    "status": _status, "capabilities": _capabilities, "describe": _describe, "connect": _connect,
    "opportunities.search": _search, "vocabulary.list": _vocabulary,
}

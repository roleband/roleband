"""The short views of `capabilities` and `describe`, built from index entries.

A small model pays for every byte of discovery on every later turn, so both
answer a summary by default and name the full view in `continue_with`. The
engine builds them from its descriptors' entries and the client from its
bundled index, through these same functions, so the two cannot drift.

This module imports only the standard library: the client imports it.
"""

from __future__ import annotations

from typing import Any

#: The views both operations take.
VIEWS = ("summary", "full")
#: The JSON Schema keywords whose value maps names to schemas, not keywords.
_SCHEMA_MAPS = frozenset({"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"})
#: The JSON Schema keywords whose value is instance data, kept as written.
_LITERALS = frozenset({"default", "examples", "example", "const", "enum"})
#: The detail `describe`'s summary leaves to the full view.
_FULL_ONLY = ("output_schema", "output_schema_ref")


def resource_of(operation: str) -> str:
    """The resource an operation id belongs to: its first segment. A
    one-segment id (`status`) is a resource of its own."""
    return operation.split(".", 1)[0]


def capabilities_summary(entries: list[dict[str, Any]], *, resources: dict[str, str], availability_known: bool,
                         tier: str | None) -> dict[str, Any]:
    """Each resource's one-line summary and the ids of its operations, the
    effects of the operations that do more than read, and the reason each one
    that cannot be called now cannot. An operation adds only its id here; its
    own summary is in `describe`, so the index grows with resources, not with
    the text of every operation.

    `entries` are `summary_entry` or `full_entry` dicts and `resources` maps
    each resource to its summary. Bundled metadata cannot know the person's
    switches, so there `unavailable` is null, which reads as unknown, never as
    available."""
    grouped: dict[str, list[str]] = {}
    effects: dict[str, list[str]] = {}
    unavailable: dict[str, str] = {}
    for entry in entries:
        operation = entry["operation"]
        grouped.setdefault(resource_of(operation), []).append(operation)
        named = [name for name, on in entry["engine_effects"].items() if on] + list(entry["client_effects"])
        if named:
            effects[operation] = sorted(named)
        state = entry["availability"]
        if state["state"] != "available":
            unavailable[operation] = state["reason"]
    full: dict[str, Any] = {"view": "full"}
    if tier is not None:
        full["tier"] = tier
    return {
        "view": "summary",
        "resources": {name: {"summary": resources[name], "operations": operations}
                      for name, operations in grouped.items()},
        "effects": effects,
        "unavailable": unavailable if availability_known else None,
        "continue_with": [{"operation": "capabilities", "arguments": full}],
    }


def describe_view(entry: dict[str, Any], view: str) -> dict[str, Any]:
    """One operation's `full_entry` in `view`. The summary keeps everything a
    call needs (input schema, effects, scopes, availability, examples) and
    leaves the output schema to the full view its `continue_with` names; its
    input schema drops the titles a schema generator derives from field
    names."""
    if view == "full":
        return {"view": "full", **entry}
    brief = {key: value for key, value in entry.items() if key not in _FULL_ONLY}
    brief["input_schema"] = _untitled(entry["input_schema"])
    return {
        "view": "summary",
        **brief,
        "continue_with": [{"operation": "describe", "arguments": {"operation": entry["operation"], "view": "full"}}],
    }


def _untitled(schema: Any) -> Any:
    """`schema` without its `title` keywords. A property that is itself named
    `title` stays: inside a keyword that maps names to schemas, every key is
    a name. So does a `title` in a default, an example or an allowed value,
    which is data, not schema."""
    if isinstance(schema, list):
        return [_untitled(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    kept: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "title" and isinstance(value, str):
            continue
        if key in _LITERALS:
            kept[key] = value
        elif key in _SCHEMA_MAPS and isinstance(value, dict):
            kept[key] = {name: _untitled(item) for name, item in value.items()}
        else:
            kept[key] = _untitled(value)
    return kept

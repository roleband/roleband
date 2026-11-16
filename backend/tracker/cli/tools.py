"""`roleband tools export`: the operations as tool definitions, for people who
build their own agent.

One tool per operation, in the OpenAI-compatible (`openai`) or Anthropic
(`anthropic`) format, made by the builder the engine's own runner uses
(`tracker/agents/tool_definitions.py`) from the input schemas in the bundled
index. Like `capabilities`, it asks the selected engine which operations are
available and exports only those, so the person's switches decide: a write
appears only while changes are allowed, and a category that is not shared
takes its operations with it. `--offline` asks no engine and exports every
bundled operation of the tier, labelled with availability unknown. The export
grants nothing: a tool is still refused when it is called if the switches
refuse its operation.

Beside the tools, the document names the operation each tool runs and the
command that runs it: a tool call's arguments are that command's `--input`.
A tool name cannot be turned back into an operation id, since a dot and an
underscore both become `_`. The connection's own operations (`status`,
`capabilities`, `describe`) are not tools: they take no `--input`, and the
exported list already says what they would.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tracker.agents.operations.outcomes import CONTRACT_VERSION
from tracker.cli.commands import HANDSHAKE, words_of
from tracker.cli.errors import ClientError, success_envelope

OPERATION = "tools.export"
DIALECTS = ("openai", "anthropic")
TIERS = ("small", "standard", "full")
#: Filesystems without hard links refuse `os.link` with one of these.
_NO_LINKS = frozenset({errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV})


def register(
    subparsers: Any,
    *,
    parser_class: type[argparse.ArgumentParser],
    add_globals: Callable[[argparse.ArgumentParser, str], None],
) -> None:
    """Add `tools export` beside the generated commands, with each level's
    global options as `commands.register` gives them."""
    group = subparsers.add_parser("tools", help="tool definitions for your own agent",
                                  description="Tool definitions for your own agent.", allow_abbrev=False)
    group.set_defaults(group=("tools",))
    add_globals(group, "group1_")
    verbs = group.add_subparsers(metavar="COMMAND", parser_class=parser_class)
    summary = "Write the operations you may call as tool definitions for your own agent."
    export = verbs.add_parser(
        "export", help=summary, description=summary, allow_abbrev=False,
        epilog="Exports what the engine offers now; it changes no setting and allows nothing new.",
    )
    export.add_argument("--dialect", required=True, choices=DIALECTS,
                        help="openai (OpenAI-compatible servers) or anthropic")
    export.add_argument("--tier", choices=TIERS, default="full",
                        help="small, standard or full (default full: every operation)")
    export.add_argument("--offline", action="store_true",
                        help="export every bundled operation of the tier; ask no engine")
    export.add_argument("--output", metavar="FILE", help="write the definitions to FILE instead of stdout")
    export.add_argument("--overwrite", action="store_true", help="replace FILE if it exists")
    add_globals(export, "leaf_")
    export.set_defaults(group=None, client_operation=OPERATION)


def export(
    args: argparse.Namespace,
    *,
    bundle: Mapping[str, dict[str, Any]],
    engine: Callable[[], dict[str, Any]],
    request_id: str,
) -> dict[str, Any]:
    """The envelope of one export. `bundle` is the bundled index by operation
    id; `engine` asks the selected engine for its capabilities in the tier."""
    if args.overwrite and not args.output:
        raise ClientError("invalid_arguments", "--overwrite needs --output FILE.")
    if args.offline:
        listed = [entry for entry in bundle.values() if args.tier in entry["tool_tiers"]]
        envelope = success_envelope(OPERATION, {}, request_id=request_id)
        source = "bundled"
    else:
        envelope = engine()
        envelope["operation"] = OPERATION
        if not envelope["ok"]:
            return envelope
        listed = _engine_operations(envelope["data"])
        source = "engine"
    document = _document(args, listed, bundle, source=source)
    if args.output:
        written = _write(Path(args.output), _encode(document), overwrite=args.overwrite)
        data = {**document, "tools": None, "tool_count": len(document["tools"]), "output": written}
    else:
        data = {**document, "tool_count": len(document["tools"]), "output": None}
    envelope["data"] = data
    return envelope


def _engine_operations(capabilities: object) -> list[dict[str, Any]]:
    operations = capabilities.get("operations") if isinstance(capabilities, dict) else None
    if not isinstance(operations, list) or not all(
        isinstance(entry, dict)
        and isinstance(entry.get("operation"), str)
        and isinstance(entry.get("availability"), dict)
        for entry in operations
    ):
        raise ClientError("contract_incompatible", "The engine's list of operations is not in a shape this client reads.")
    return operations


def _document(
    args: argparse.Namespace,
    listed: list[dict[str, Any]],
    bundle: Mapping[str, dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    # Imported here: help and every other command start without the builder.
    from tracker.agents.tool_definitions import assemble, schema_tool
    from tracker.intelligence.tool_calls import anthropic_format, openai_format

    exported: list[tuple[dict[str, Any], dict[str, Any]]] = []
    not_exported: list[dict[str, Any]] = []
    for entry in sorted(listed, key=lambda entry: entry["operation"]):
        operation = entry["operation"]
        if operation in HANDSHAKE:
            continue
        availability = entry["availability"]
        # Bundled metadata cannot know availability; an engine's word is final.
        wanted = "unknown" if source == "bundled" else "available"
        if availability.get("state") != wanted:
            not_exported.append({"operation": operation, "reason": availability.get("reason")})
            continue
        known = bundle.get(operation)
        if known is None:
            # Offered by a newer engine than this client knows: no schema to export.
            not_exported.append({"operation": operation, "reason": "unknown_to_client"})
            continue
        exported.append((known, availability))
    try:
        tool_set = assemble(
            (entry["operation"], schema_tool(entry["operation"], entry["summary"], entry["input_schema"]))
            for entry, _ in exported
        )
    except ValueError as error:
        raise ClientError("internal_error", f"The bundled index cannot be exported as tools: {error}") from None
    spec = {"openai": openai_format.tool_spec, "anthropic": anthropic_format.tool_spec}[args.dialect]
    return {
        "dialect": args.dialect,
        "tier": args.tier,
        "contract_version": CONTRACT_VERSION,
        "metadata_source": source,
        "tools": [spec(definition) for definition in tool_set.definitions],
        "operations": [
            {"tool": definition.name, "operation": entry["operation"], "command": list(words_of(entry["operation"])),
             "access": entry["access"], "availability": availability}
            for definition, (entry, availability) in zip(tool_set.definitions, exported, strict=True)
        ],
        "not_exported": not_exported,
    }


def _encode(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write(path: Path, data: bytes, *, overwrite: bool) -> dict[str, Any]:
    """Write `data` to `path` whole or not at all. Without `overwrite`
    nothing already at `path` is replaced, a link included, and a link is
    never followed."""
    target = Path(os.path.abspath(path))
    partial = target.with_name(f".{target.name}.{os.getpid()}.partial")
    try:
        try:
            descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if overwrite:
                os.replace(partial, target)
            else:
                _place_new(partial, target, data)
        finally:
            partial.unlink(missing_ok=True)
    except FileExistsError:
        raise ClientError(
            "invalid_arguments", f"{path} exists; choose another file or pass --overwrite to replace it.",
            details={"path": str(target)},
        ) from None
    except OSError as error:
        raise ClientError(
            "internal_error", f"Could not write {path} ({error.strerror or error}).",
            details={"path": str(target)},
        ) from None
    return {"path": str(target), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _place_new(partial: Path, target: Path, data: bytes) -> None:
    """Give `partial` the name `target` unless something has that name."""
    try:
        os.link(partial, target)
        return
    except OSError as error:
        if error.errno not in _NO_LINKS:
            raise
    # No hard links here: create the file exclusively and write it in place.
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    except OSError:
        target.unlink(missing_ok=True)
        raise


def human_lines(data: dict[str, Any], escape: Callable[[object], str]) -> list[str]:
    source = "every bundled operation, availability unknown" if data["metadata_source"] == "bundled" \
        else "what the engine offers now"
    lines = [f"{data['tool_count']} {escape(data['dialect'])} tools, {escape(data['tier'])} tier, {source}"]
    if data["output"] is not None:
        lines.append(f"  written to {escape(data['output']['path'])} ({data['output']['bytes']} bytes)")
    for entry in data["operations"]:
        lines.append(f"  {escape(entry['tool']):<34} {escape(entry['access']):<6} {escape(entry['operation'])}")
    for entry in data["not_exported"]:
        lines.append(f"  not exported: {escape(entry['operation'])} ({escape(entry['reason'])})")
    if data["output"] is None:
        lines.append("Write them with --output FILE, or read them with --format json.")
    return lines

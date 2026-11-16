"""`roleband tools export`: the operations as tool definitions for someone's own agent.

Each format is held to its provider's documented tool shape, with every
field the provider does not define refused, so a definition the provider
would reject fails here. Each exported tool is held to the engine's own
builder over the same operation, and a call built from it (the tool's name,
the model's arguments) is followed back to the operation it came from. What
is left out is held too: an operation the engine does not offer, one it
offers but the switches refuse, and one this client does not know.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, StringConstraints

from tests import test_cli
from tests.test_agent_tool_definitions import _assert_portable
from tests.test_cli import Reply, Stub, _envelope, cli
from tracker.agents.operations.catalog import CATALOG
from tracker.agents.tool_definitions import tool_definition
from tracker.cli import commands, tools
from tracker.cli.errors import ClientError
from tracker.cli.main import BUNDLE, build_parser

home = test_cli.home
engine_database = test_cli.engine_database
engine = test_cli.engine

HANDSHAKE = {"status", "capabilities", "describe"}
#: Both providers name a tool with 1 to 64 letters, digits, `_` or `-`.
ToolName = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]


# --------------------------------------------------------------------------- #
# Each provider's tool shape, as its API reference documents it
# --------------------------------------------------------------------------- #


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OpenAIFunction(_Closed):
    name: ToolName
    description: str | None = None
    parameters: dict[str, Any] | None = None
    strict: bool | None = None


class OpenAITool(_Closed):
    """An entry of `tools` in a chat completions request."""

    type: Literal["function"]
    function: OpenAIFunction


class AnthropicInputSchema(BaseModel):
    """The one part of a tool the Messages API leaves open: any other JSON
    Schema keyword may sit beside these."""

    model_config = ConfigDict(extra="allow", strict=True)

    type: Literal["object"]
    properties: dict[str, Any] | None = None
    required: list[str] | None = None


class AnthropicTool(_Closed):
    """An entry of `tools` in a Messages request (a custom tool)."""

    name: ToolName
    description: str | None = None
    input_schema: AnthropicInputSchema
    type: Literal["custom"] | None = None
    cache_control: dict[str, Any] | None = None


def _parameters(dialect: str, tool: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The tool's name and argument schema, after holding it to its provider's shape."""
    if dialect == "openai":
        checked = OpenAITool.model_validate(tool)
        assert checked.function.parameters is not None and checked.function.description
        return checked.function.name, checked.function.parameters
    anthropic = AnthropicTool.model_validate(tool)
    assert anthropic.description
    return anthropic.name, tool["input_schema"]


def test_the_provider_shapes_refuse_what_their_apis_refuse():
    """Control: the shapes above are strict enough to catch a crossed format."""
    good = {"type": "function", "function": {"name": "a_b", "description": "d", "parameters": {"type": "object"}}}
    OpenAITool.model_validate(good)
    AnthropicTool.model_validate({"name": "a_b", "description": "d", "input_schema": {"type": "object"}})
    for bad in (
        {**good, "function": {**good["function"], "name": "a.b"}},
        {**good, "function": {**good["function"], "input_schema": {"type": "object"}}},
        {"name": "a_b", "description": "d", "parameters": {"type": "object"}},
    ):
        with pytest.raises(ValueError):
            OpenAITool.model_validate(bad)
    for bad in (
        {"type": "function", "function": good["function"]},
        {"name": "a_b", "description": "d", "parameters": {"type": "object"}},
        {"name": "a_b", "description": "d", "input_schema": {"type": "array"}},
    ):
        with pytest.raises(ValueError):
            AnthropicTool.model_validate(bad)


# --------------------------------------------------------------------------- #
# Offline: every bundled operation of the tier
# --------------------------------------------------------------------------- #


def _export(home, *args: str) -> dict[str, Any]:
    result = cli(home, "tools", "export", *args, "--json")
    assert result.status == 0, result
    assert result.stderr == ""
    body = result.envelope
    assert body["ok"] is True and body["operation"] == "tools.export"
    return body


@pytest.mark.parametrize("dialect", ["openai", "anthropic"])
@pytest.mark.parametrize("tier", ["small", "standard", "full"])
def test_each_dialect_is_its_providers_tool_shape_and_the_engines_own_tools(home, dialect, tier):
    data = _export(home, "--dialect", dialect, "--tier", tier, "--offline")["data"]
    assert data["dialect"] == dialect and data["tier"] == tier
    assert data["metadata_source"] == "bundled" and data["output"] is None

    expected = {d.id: d for d in CATALOG if tier in d.tool_tiers and d.id not in HANDSHAKE}
    assert expected, "control: the tier holds operations"
    assert data["tool_count"] == len(data["tools"]) == len(expected)
    by_tool = {entry["tool"]: entry for entry in data["operations"]}
    assert {entry["operation"] for entry in by_tool.values()} == set(expected)
    for tool in data["tools"]:
        name, schema = _parameters(dialect, tool)
        _assert_portable(schema)
        descriptor = expected[by_tool[name]["operation"]]
        # The same tool the engine's runner offers for this operation.
        built = tool_definition(descriptor)
        assert (name, schema) == (built.name, dict(built.parameters))
        assert by_tool[name]["access"] == descriptor.access
        # Offline cannot know what the switches allow; it says so, never "available".
        assert by_tool[name]["availability"] == {"state": "unknown", "reason": "offline"}
    assert data["not_exported"] == []
    # Help and the other commands do not pay for the builder.
    assert dialect in cli(home, "tools", "export", "--help").stdout


def test_a_call_built_from_each_tool_reaches_the_operation_it_came_from(home, tmp_path):
    """The round trip a person's agent makes: the model names a tool and gives
    arguments; the document names the command; the arguments are its input."""
    out = tmp_path / "tools.json"
    _export(home, "--dialect", "anthropic", "--offline", "--output", str(out))
    document = json.loads(out.read_text(encoding="utf-8"))
    by_tool = {entry["tool"]: entry for entry in document["operations"]}
    parser = build_parser()
    called = set()
    for tool in document["tools"]:
        entry = by_tool[tool["name"]]
        descriptor = CATALOG.get(entry["operation"])
        assert descriptor is not None
        for example in descriptor.examples:
            assert set(example) <= set(tool["input_schema"]["properties"])
            arguments = tmp_path / "arguments.json"
            arguments.write_text(json.dumps(example), encoding="utf-8")
            args = parser.parse_args([*entry["command"], "--input", f"@{arguments}"])
            assert args.generated.operation == descriptor.id
            assert commands.payload(args.generated, args) == example
            called.add(descriptor.id)
    # Reads and writes both make the trip.
    assert {CATALOG.get(name).access for name in called} == {"read", "write"}
    assert len(called) >= len(document["tools"]) // 2


def test_a_tool_name_that_is_not_an_operation_id_needs_the_document(home):
    """Control for the document's `operations`: without it a tool name does
    not lead back, because `_` stands for a dot and for itself."""
    data = _export(home, "--dialect", "openai", "--offline")["data"]
    entry = next(entry for entry in data["operations"] if entry["operation"] == "opportunities.get_many")
    assert entry["tool"] == "opportunities_get_many"
    assert entry["command"] == ["opportunities", "get-many"]
    assert CATALOG.get(entry["tool"].replace("_", ".")) is None


# --------------------------------------------------------------------------- #
# Live: only what the engine offers now
# --------------------------------------------------------------------------- #


def _bundled() -> dict[str, dict[str, Any]]:
    return {entry["operation"]: entry for entry in json.loads(BUNDLE.read_text(encoding="utf-8"))["operations"]}


def _capabilities(*entries: dict[str, Any]) -> bytes:
    return _envelope("capabilities", data={
        "contract_version": "1.0", "supported_contract_versions": ["1.0"], "engine_version": "0.2.0",
        "metadata_source": "engine", "operations": list(entries),
    })


def _offered(operation: str, state: str = "available", reason: str | None = None) -> dict[str, Any]:
    keys = ("operation", "summary", "access", "engine_effects", "client_effects", "data_classes",
            "tool_tiers", "idempotency")
    return {**{key: _bundled()[operation][key] for key in keys}, "availability": {"state": state, "reason": reason}}


def test_only_what_the_engine_offers_now_is_exported(home):
    newer = {**_offered("opportunities.search"), "operation": "opportunities.compare", "summary": "Compare."}
    reply = Reply(200, _capabilities(
        _offered("opportunities.search"),
        _offered("radar.summary"),
        _offered("pursuits.save", "unavailable", "writes_disabled"),
        _offered("insights.offer_terms", "unavailable", "category_disabled"),
        _offered("status"),
        newer,
    ))
    with Stub(reply) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        body = _export(home, "--dialect", "openai", "--tier", "small")
    # The export reads every operation's availability: the full list, not the index.
    assert stub.requests == ["/api/agent/v1/capabilities?tier=small&view=full"]
    data = body["data"]
    assert data["metadata_source"] == "engine"
    assert body["workspace_id"] == "ws_" + "a" * 32
    assert body["meta"]["context"]["name"] == "dev"
    assert [tool["function"]["name"] for tool in data["tools"]] == ["opportunities_search", "radar_summary"]
    assert {entry["availability"]["state"] for entry in data["operations"]} == {"available"}
    # The negative controls: a write the switches refuse, a category not
    # shared, an operation this client cannot describe. One the engine no
    # longer offers (every other bundled operation) is simply absent.
    assert data["not_exported"] == [
        {"operation": "insights.offer_terms", "reason": "category_disabled"},
        {"operation": "opportunities.compare", "reason": "unknown_to_client"},
        {"operation": "pursuits.save", "reason": "writes_disabled"},
    ]
    assert "pursuits_patch" not in json.dumps(data["tools"])


def test_an_engine_refusal_is_the_exports_answer(home):
    refusal = _envelope("capabilities", ok=False, workspace_id=None, error={
        "code": "access_disabled", "message": "Agent access is off.", "retryable": False,
        "details": {"setting": "agent_access.enabled"}, "next_actions": [],
    })
    with Stub(Reply(403, refusal)) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "tools", "export", "--dialect", "anthropic", "--json")
    assert result.status == 4
    body = result.envelope
    assert body["operation"] == "tools.export" and body["data"] is None
    assert body["error"]["code"] == "access_disabled"


def test_a_capabilities_reply_in_another_shape_is_incompatible(home):
    with Stub(Reply(200, _capabilities({"operation": "radar.summary"}))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "tools", "export", "--dialect", "openai", "--json")
    assert result.status == 10
    assert result.envelope["error"]["code"] == "contract_incompatible"


def test_the_switches_decide_what_a_real_engine_exports(home, engine, tmp_path):
    home.contexts(current="dev", dev={"url": engine.url})
    assert engine.put_json("/api/intelligence/agents", {"enabled": True, "allow_writes": False}) == 200
    reads_only = _export(home, "--dialect", "openai")["data"]
    accesses = {entry["access"] for entry in reads_only["operations"]}
    assert accesses == {"read"}
    refused = {entry["operation"] for entry in reads_only["not_exported"]}
    writes = {d.id for d in CATALOG if d.access == "write"}
    assert writes and refused == writes

    assert engine.put_json("/api/intelligence/agents", {
        "enabled": True, "allow_writes": True, "categories": {"offer": "not_shared"},
    }) == 200
    data = _export(home, "--dialect", "anthropic")["data"]
    exported = {entry["operation"] for entry in data["operations"]}
    assert writes <= exported
    offer_first = {d.id for d in CATALOG if d.data_classes and d.data_classes[0] == "offer"}
    assert offer_first and not offer_first & exported
    assert {entry["reason"] for entry in data["not_exported"]} == {"category_disabled"}

    # A call built from an exported tool reaches that operation on the engine:
    # the model's arguments, given as the named command's input.
    entry = next(entry for entry in data["operations"] if entry["tool"] == "opportunities_search")
    tool = next(tool for tool in data["tools"] if tool["name"] == entry["tool"])
    descriptor = CATALOG.get("opportunities.search")
    assert descriptor is not None and descriptor.examples
    arguments = descriptor.examples[0]
    assert set(arguments) <= set(tool["input_schema"]["properties"])
    (tmp_path / "call.json").write_text(json.dumps(arguments), encoding="utf-8")
    called = cli(home, *entry["command"], "--input", f"@{tmp_path / 'call.json'}", "--json")
    assert called.status == 0, called
    assert called.envelope["operation"] == "opportunities.search"


# --------------------------------------------------------------------------- #
# --output FILE
# --------------------------------------------------------------------------- #


def test_output_is_written_whole_and_reported_by_size_and_hash(home, tmp_path):
    out = tmp_path / "tools.json"
    data = _export(home, "--dialect", "openai", "--offline", "--output", str(out))["data"]
    written = out.read_bytes()
    assert data["output"] == {
        "path": str(out), "bytes": len(written), "sha256": hashlib.sha256(written).hexdigest(),
    }
    assert data["tools"] is None and data["tool_count"] == len(json.loads(written)["tools"])
    assert [name for name in os.listdir(tmp_path) if name.endswith(".partial")] == []


def test_output_never_replaces_a_file_or_follows_a_link_unless_told(home, tmp_path):
    out = tmp_path / "tools.json"
    out.write_text("mine", encoding="utf-8")
    refused = cli(home, "tools", "export", "--dialect", "openai", "--offline", "--output", str(out), "--json")
    assert refused.status == 2
    assert refused.envelope["error"]["code"] == "invalid_arguments"
    assert "--overwrite" in refused.envelope["error"]["message"]
    assert out.read_text(encoding="utf-8") == "mine"

    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("theirs", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(elsewhere)
    assert cli(home, "tools", "export", "--dialect", "openai", "--offline", "--output", str(link),
               "--json").status == 2
    assert elsewhere.read_text(encoding="utf-8") == "theirs" and link.is_symlink()

    # --overwrite replaces the name it was given; the file a link named stays as it was.
    _export(home, "--dialect", "openai", "--offline", "--output", str(link), "--overwrite")
    assert not link.is_symlink() and json.loads(link.read_text(encoding="utf-8"))["dialect"] == "openai"
    assert elsewhere.read_text(encoding="utf-8") == "theirs"
    _export(home, "--dialect", "anthropic", "--offline", "--output", str(out), "--overwrite")
    assert json.loads(out.read_text(encoding="utf-8"))["dialect"] == "anthropic"


def test_overwrite_without_output_is_refused(home):
    result = cli(home, "tools", "export", "--dialect", "openai", "--offline", "--overwrite", "--json")
    assert result.status == 2
    assert result.envelope["error"]["code"] == "invalid_arguments"


def test_dot_dot_after_a_linked_folder_is_resolved_by_the_filesystem(tmp_path, monkeypatch):
    real = tmp_path / "exports" / "nested"
    real.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    (work / "link").symlink_to(real)
    (work / "tools.json").write_bytes(b"keep")
    monkeypatch.chdir(work)
    written = tools._write(Path("link/../tools.json"), b"{}\n", overwrite=True)
    assert written["path"] == str(work / "link" / ".." / "tools.json")
    # The client writes to the name as given. POSIX resolves `..` against the
    # link's target; Windows collapses it in the name before any folder is read.
    if sys.platform == "win32":
        meant, untouched = work / "tools.json", tmp_path / "exports" / "tools.json"
    else:
        meant, untouched = tmp_path / "exports" / "tools.json", work / "tools.json"
    assert meant.read_bytes() == b"{}\n"
    assert not untouched.exists() or untouched.read_bytes() == b"keep"
    assert [name for name in os.listdir(work) + os.listdir(tmp_path / "exports") if name.endswith(".partial")] == []


def test_a_filesystem_without_hard_links_is_refused_rather_than_written_in_place(tmp_path, monkeypatch):
    def no_links(*_args: object) -> None:
        raise OSError(errno.ENOTSUP, "no hard links")

    monkeypatch.setattr(os, "link", no_links)
    target = tmp_path / "tools.json"
    with pytest.raises(ClientError) as refused:
        tools._write(target, b"{}\n", overwrite=False)
    assert refused.value.code == "unsupported_operation"
    assert os.listdir(tmp_path) == []
    # --overwrite replaces atomically without a link, so it still writes.
    assert tools._write(target, b"{}\n", overwrite=True)["bytes"] == 3
    assert sorted(os.listdir(tmp_path)) == ["tools.json"]


def test_a_partial_file_this_call_did_not_make_is_left_alone(tmp_path, monkeypatch):
    target = tmp_path / "tools.json"
    stranger = tmp_path / ".tools.json.0000000000000000.partial"
    stranger.write_bytes(b"someone else's")
    monkeypatch.setattr(tools.secrets, "token_hex", lambda _n: "0000000000000000")
    with pytest.raises(ClientError) as refused:
        tools._write(target, b"{}\n", overwrite=False)
    assert refused.value.code == "internal_error"
    assert stranger.read_bytes() == b"someone else's" and not target.exists()


# --------------------------------------------------------------------------- #
# For a person
# --------------------------------------------------------------------------- #


def test_human_output_lists_each_tool_and_its_operation(home):
    result = cli(home, "tools", "export", "--dialect", "anthropic", "--offline", "--tier", "small",
                 "--format", "human")
    assert result.status == 0 and result.stderr == ""
    lines = result.stdout.splitlines()
    small = [d for d in CATALOG if "small" in d.tool_tiers and d.id not in HANDSHAKE]
    assert lines[0] == f"{len(small)} anthropic tools, small tier, every bundled operation, availability unknown"
    assert any(line.split() == ["opportunities_search", "read", "opportunities.search"] for line in lines)
    assert lines[-1].startswith("Write them with --output FILE")


def test_human_lines_escape_what_the_engine_names():
    data = {
        "dialect": "openai", "tier": "full", "metadata_source": "engine", "tool_count": 0, "output": None,
        "operations": [], "not_exported": [{"operation": "x\x1b[31m", "reason": "writes_disabled"}],
    }
    from tracker.cli.render import escape

    assert "\x1b" not in "".join(tools.human_lines(data, escape))



@pytest.mark.parametrize("word", ["tools", "connect"])
def test_an_operation_cannot_take_a_written_commands_word(word):
    document = json.loads(BUNDLE.read_text(encoding="utf-8"))
    commands.build(document)
    entry = next(entry for entry in document["operations"] if entry["operation"] == "radar.summary")
    document["operations"].append({**entry, "operation": f"{word}.list"})
    document["routes"][f"{word}.list"] = {"method": "GET", "path": f"/api/agent/v1/{word}"}
    with pytest.raises(ValueError, match="already a command of its own"):
        commands.build(document)

"""Tool definitions generated from operation descriptors, over the real catalog.

Every registered operation must produce a definition both wire formats accept:
a name of letters, digits and underscores, a description, and a
self-contained object schema that still describes exactly the operation's
input. The synthetic shapes below are the cases the catalog does not hold yet
(a nested shape, an enum class, a field named `title`, a self-reference).
"""

from __future__ import annotations

import dataclasses
import json
import re
from enum import StrEnum
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from tracker.agents.operations.catalog import CATALOG
from tracker.agents.operations.descriptor import Shape
from tracker.agents.tool_definitions import input_schema, tool_definition, tool_name, tool_set
from tracker.intelligence.tool_calls import anthropic_format, openai_format

NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
OPERATIONS = list(CATALOG)


def _schema_nodes(node: Any, path: str = "#"):
    """Every subschema, with where it sits."""
    if not isinstance(node, dict):
        return
    yield path, node
    for key in ("items", "additionalProperties", "not", "contains"):
        yield from _schema_nodes(node.get(key), f"{path}/{key}")
    for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
        for index, item in enumerate(node.get(key) or []):
            yield from _schema_nodes(item, f"{path}/{key}/{index}")
    for name, item in (node.get("properties") or {}).items():
        yield from _schema_nodes(item, f"{path}/properties/{name}")


def _assert_portable(schema: dict[str, Any]) -> None:
    assert schema["type"] == "object" and isinstance(schema["properties"], dict)
    assert "$defs" not in schema
    assert set(schema.get("required", [])) <= set(schema["properties"])
    json.dumps(schema)
    for path, node in _schema_nodes(schema):
        assert "$ref" not in node, f"{path} points outside the schema"
        assert "title" not in node, f"{path} keeps a title keyword"
        assert not any(key.startswith("x-") for key in node), f"{path} keeps an x- annotation"


@pytest.mark.parametrize("descriptor", OPERATIONS, ids=[descriptor.id for descriptor in OPERATIONS])
def test_every_operation_is_a_valid_tool_in_both_formats(descriptor):
    definition = tool_definition(descriptor)
    original = descriptor.input.model_json_schema()

    openai = openai_format.tool_spec(definition)
    assert openai["type"] == "function" and set(openai["function"]) == {"name", "description", "parameters"}
    anthropic = anthropic_format.tool_spec(definition)
    assert set(anthropic) == {"name", "description", "input_schema"}
    for name, description, schema in (
        (openai["function"]["name"], openai["function"]["description"], openai["function"]["parameters"]),
        (anthropic["name"], anthropic["description"], anthropic["input_schema"]),
    ):
        assert NAME.fullmatch(name) and name == descriptor.id.replace(".", "_")
        assert description == descriptor.summary and description.strip()
        _assert_portable(schema)
        # The schema still describes the operation's input, field for field.
        assert set(schema["properties"]) == set(original.get("properties", {}))
        assert set(schema.get("required", [])) == set(original.get("required", []))
        assert schema.get("additionalProperties") == original.get("additionalProperties")


@pytest.mark.parametrize("descriptor", [d for d in OPERATIONS if d.examples], ids=lambda d: d.id)
def test_every_example_input_fits_the_tool_it_is_an_example_of(descriptor):
    schema = tool_definition(descriptor).parameters
    for example in descriptor.examples:
        descriptor.input.model_validate(example)
        assert set(example) <= set(schema["properties"])
        assert set(schema.get("required", [])) <= set(example)


def test_the_catalog_is_one_tool_set_with_a_way_back_to_each_operation():
    tools = tool_set(CATALOG)
    assert len(tools.definitions) == len(OPERATIONS)
    assert len({definition.name for definition in tools.definitions}) == len(OPERATIONS)
    for descriptor in OPERATIONS:
        assert tools.operation_for(tool_name(descriptor.id)) == descriptor.id
    assert tools.operation_for("opportunities.search") is None, "the dotted id is not a tool name"


def test_two_operations_that_would_share_a_tool_name_are_refused():
    first = CATALOG.get("opportunities.search")
    assert first is not None
    twin = dataclasses.replace(first, id="opportunities_search")
    with pytest.raises(ValueError, match="share the tool name"):
        tool_set([first, twin])


class Tone(StrEnum):
    WARM = "warm"
    COOL = "cool"


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str = Field(description="Where.")
    tone: Tone = Tone.WARM


class Letter(Shape):
    title: str = Field(description="A field that happens to be called title.", json_schema_extra={"x-text": "content"})
    to: Address
    copies: list[Address] = []
    tone: Tone | None = None


def test_nested_shapes_are_inlined_and_a_field_named_title_survives():
    assert "$defs" in Letter.model_json_schema(), "control: pydantic does put these in $defs"
    schema = input_schema(Letter)
    _assert_portable(schema)
    assert set(schema["properties"]) == {"title", "to", "copies", "tone"}
    assert schema["properties"]["title"]["description"].startswith("A field")
    assert schema["properties"]["to"]["properties"]["city"] == {"description": "Where.", "type": "string"}
    assert schema["properties"]["to"]["properties"]["tone"]["enum"] == ["warm", "cool"]
    assert schema["properties"]["copies"]["items"]["required"] == ["city"]
    assert {"enum": ["warm", "cool"], "type": "string"} in schema["properties"]["tone"]["anyOf"]


class Node(Shape):
    label: str
    children: list[Node] = []


def test_a_shape_that_refers_to_itself_is_refused_rather_than_cut():
    with pytest.raises(ValueError, match="refers to itself"):
        input_schema(Node)

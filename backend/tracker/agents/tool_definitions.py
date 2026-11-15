"""Tool definitions for a model, generated from operation descriptors.

A tool is an operation: its name is the operation id with dots made
underscores (neither wire format allows a dot), its description the
operation's summary, its parameters the operation's input schema. The schema
is made self-contained, because a local server pastes it into the prompt
where a `$ref` points nowhere: definitions are inlined, and `title` and `x-`
annotations, which only cost tokens, are dropped.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from tracker.agents.operations.descriptor import OperationDescriptor
from tracker.intelligence.tool_calls import ToolDefinition

#: Keywords whose value is one subschema.
_ONE = ("additionalProperties", "items", "not", "if", "then", "else", "contains", "propertyNames",
        "unevaluatedItems", "unevaluatedProperties", "additionalItems")
#: Keywords whose value is a list of subschemas.
_MANY = ("anyOf", "allOf", "oneOf", "prefixItems")
#: Keywords whose value maps names to subschemas.
_NAMED = ("properties", "patternProperties", "dependentSchemas")


def tool_name(operation_id: str) -> str:
    return operation_id.replace(".", "_")


def _inline(node: Any, defs: Mapping[str, Any], resolving: tuple[str, ...]) -> Any:
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str):
        prefix = "#/$defs/"
        if not ref.startswith(prefix) or ref[len(prefix):] not in defs:
            raise ValueError(f"schema reference {ref!r} does not resolve inside the schema")
        name = ref[len(prefix):]
        if name in resolving:
            raise ValueError(f"input shape {name!r} refers to itself and cannot be inlined")
        resolved = _inline(defs[name], defs, (*resolving, name))
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        return {**resolved, **_inline(siblings, defs, resolving)}
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in ("$defs", "title") or key.startswith("x-"):
            continue
        if key in _ONE:
            out[key] = _inline(value, defs, resolving)
        elif key in _MANY and isinstance(value, list):
            out[key] = [_inline(item, defs, resolving) for item in value]
        elif key in _NAMED and isinstance(value, dict):
            out[key] = {name: _inline(item, defs, resolving) for name, item in value.items()}
        else:
            out[key] = copy.deepcopy(value)
    return out


def input_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON Schema, self-contained, as a tool's parameters."""
    schema = model.model_json_schema()
    inlined = _inline(schema, schema.get("$defs") or {}, ())
    inlined.setdefault("properties", {})
    return inlined


def tool_definition(descriptor: OperationDescriptor) -> ToolDefinition:
    return ToolDefinition(
        name=tool_name(descriptor.id),
        description=descriptor.summary,
        parameters=input_schema(descriptor.input),
    )


@dataclass(frozen=True)
class ToolSet:
    """The tools offered to a model, and which operation each one runs."""

    definitions: tuple[ToolDefinition, ...]
    operations: Mapping[str, str]

    def operation_for(self, name: str) -> str | None:
        return self.operations.get(name)


def tool_set(descriptors: Iterable[OperationDescriptor]) -> ToolSet:
    definitions: list[ToolDefinition] = []
    operations: dict[str, str] = {}
    for descriptor in descriptors:
        definition = tool_definition(descriptor)
        if definition.name in operations:
            raise ValueError(
                f"operations {operations[definition.name]!r} and {descriptor.id!r} share the tool name {definition.name!r}"
            )
        operations[definition.name] = descriptor.id
        definitions.append(definition)
    return ToolSet(definitions=tuple(definitions), operations=operations)

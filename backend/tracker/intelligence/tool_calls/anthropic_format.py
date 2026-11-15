"""The Anthropic Messages format with tools.

Arguments arrive as an object, tool results travel inside the next user
message, and the two roles alternate: consecutive messages of one role are
merged into one. Tool ids must be letters, digits, `_` or `-`; an id another
server minted is rewritten to fit, the same way on the call and its result.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from tracker.intelligence.tool_calls.conversation import (
    AssistantMessage,
    StopReason,
    ToolCall,
    ToolDefinition,
    ToolRequest,
    ToolResults,
    ToolTransportError,
    Turn,
    Usage,
    UserMessage,
    mapping_of,
    parse_arguments,
    replay_arguments,
    string_of,
)

API_VERSION = "2023-06-01"
#: The format requires a ceiling on every request.
DEFAULT_MAX_TOKENS = 4096

_UNSAFE_ID = re.compile(r"[^a-zA-Z0-9_-]")
_STOPS = {
    "end_turn": StopReason.END,
    "stop_sequence": StopReason.END,
    "pause_turn": StopReason.END,
    "tool_use": StopReason.TOOL_USE,
    "max_tokens": StopReason.MAX_TOKENS,
    "model_context_window_exceeded": StopReason.MAX_TOKENS,
    "refusal": StopReason.REFUSAL,
}
_CHOICES = {"auto": "auto", "required": "any", "none": "none"}


def tool_spec(tool: ToolDefinition) -> dict[str, Any]:
    return {"name": tool.name, "description": tool.description, "input_schema": dict(tool.parameters)}


def _safe_id(call_id: str) -> str:
    """An id the format accepts. A rewritten one carries a digest of the
    original, so two ids that differ only in refused characters stay apart."""
    safe = _UNSAFE_ID.sub("_", call_id)
    if safe == call_id and safe:
        return safe
    return f"{safe or 'call'}_{hashlib.sha256(call_id.encode()).hexdigest()[:8]}"


def _blocks(message: Any) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(message, UserMessage):
        return "user", [{"type": "text", "text": message.text}] if message.text else []
    if isinstance(message, AssistantMessage):
        blocks: list[dict[str, Any]] = [{"type": "text", "text": message.text}] if message.text else []
        blocks += [
            {"type": "tool_use", "id": _safe_id(call.id), "name": call.name, "input": replay_arguments(call)}
            for call in message.tool_calls
        ]
        return "assistant", blocks
    if isinstance(message, ToolResults):
        results: list[dict[str, Any]] = []
        for result in message.results:
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": _safe_id(result.call_id),
                "content": result.content,
            }
            if result.is_error:
                block["is_error"] = True
            results.append(block)
        return "user", results
    raise TypeError(f"not a conversation message: {type(message).__name__}")


def request_body(request: ToolRequest, *, model: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    for message in request.conversation:
        role, blocks = _blocks(message)
        if not blocks:
            # The format refuses an empty text block; an empty message says nothing.
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
        "messages": messages,
    }
    if request.system:
        body["system"] = request.system
    if request.tools:
        body["tools"] = [tool_spec(tool) for tool in request.tools]
        choice: dict[str, Any] = {"type": _CHOICES[request.tool_choice]}
        if not request.parallel_tool_calls and request.tool_choice != "none":
            choice["disable_parallel_tool_use"] = True
        body["tool_choice"] = choice
    return body


def _usage(body: Mapping[str, Any], wall_time_ms: int | None) -> Usage:
    usage = mapping_of(body.get("usage"))

    def count(key: str) -> int | None:
        value = usage.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    uncached, written, read = count("input_tokens"), count("cache_creation_input_tokens"), count("cache_read_input_tokens")
    total = None if uncached is None else uncached + (written or 0) + (read or 0)
    return Usage(
        input_tokens=total,
        output_tokens=count("output_tokens"),
        cached_input_tokens=read,
        wall_time_ms=wall_time_ms,
    )


def read_turn(body: object, *, request: ToolRequest, model: str, wall_time_ms: int | None = None) -> Turn:
    """A Messages response as a `Turn`. Raises only when the body is not a
    message at all."""
    if not isinstance(body, dict):
        raise ToolTransportError("The model's response was not a JSON object.", failure_class="validation")
    content = body.get("content")
    if not isinstance(content, list):
        raise ToolTransportError("The model's response had no content.", failure_class="validation")
    offered = request.offered()
    texts: list[str] = []
    thinking: list[str] = []
    calls: list[ToolCall] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif kind == "thinking" and isinstance(block.get("thinking"), str):
            thinking.append(block["thinking"])
        elif kind == "tool_use":
            name = string_of(block.get("name"))
            arguments, raw, problem = parse_arguments(block.get("input"), name=name, offered=offered)
            call_id = string_of(block.get("id")) or f"toolu_{len(calls)}"
            calls.append(ToolCall(id=call_id, name=name, arguments=arguments, raw_arguments=raw, problem=problem))
    raw_stop = body.get("stop_reason") if isinstance(body.get("stop_reason"), str) else None
    stop = _STOPS.get(raw_stop or "", StopReason.END)
    if stop is StopReason.END and calls:
        stop = StopReason.TOOL_USE
    return Turn(
        message=AssistantMessage(text="".join(texts).strip(), tool_calls=tuple(calls)),
        stop_reason=stop,
        usage=_usage(body, wall_time_ms),
        model=str(body.get("model") or model),
        raw_stop=raw_stop,
        missing_tool_call=request.tool_choice == "required" and bool(offered) and not calls,
        reasoning="\n".join(thinking) or None,
    )

"""The OpenAI chat completions format with tools, as oMLX, LM Studio and other
OpenAI-compatible servers speak it.

Arguments travel as JSON text, so a small model's malformed arguments arrive
here as text and become a `CallProblem`. A server whose tool parser misses a
call leaves it in the answer as a `<tool_call>` block (the Hermes convention
Qwen models write); such a block naming an offered tool is read as the call.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from typing import Any

from tracker.intelligence.tool_calls.conversation import (
    AssistantMessage,
    CallProblem,
    CallProblemKind,
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
    string_of,
)

_OPEN, _CLOSE = "<tool_call>", "</tool_call>"
_TEXT_CALL_NAME = re.compile(r'"name"\s*:\s*"([^"]+)"')
_THINK = re.compile(r"^\s*<think>(.*?)</think>\s*", re.DOTALL)


def tool_spec(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": dict(tool.parameters)},
    }


def _arguments_text(call: ToolCall) -> str:
    # A call that parsed goes back as the model wrote it; one that did not goes
    # back as an empty object, because a server's chat template may parse the
    # text again and fail the whole request on it. Its result quotes the text.
    if call.problem is not None:
        return "{}"
    if call.raw_arguments is not None:
        return call.raw_arguments
    return json.dumps(dict(call.arguments), ensure_ascii=False)


def request_body(
    request: ToolRequest,
    *,
    model: str,
    max_tokens_field: str = "max_tokens",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    for message in request.conversation:
        if isinstance(message, UserMessage):
            messages.append({"role": "user", "content": message.text})
        elif isinstance(message, AssistantMessage):
            # Some servers refuse an assistant message whose content is null;
            # none refuses an empty string.
            entry: dict[str, Any] = {"role": "assistant", "content": message.text}
            if message.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": _arguments_text(call)},
                    }
                    for call in message.tool_calls
                ]
            messages.append(entry)
        elif isinstance(message, ToolResults):
            for result in message.results:
                content = f"Error: {result.content}" if result.is_error else result.content
                messages.append({"role": "tool", "tool_call_id": result.call_id, "content": content})
    body: dict[str, Any] = dict(extra or {})
    body.update({"model": model, "messages": messages, "stream": False})
    if request.tools:
        body["tools"] = [tool_spec(tool) for tool in request.tools]
        body["tool_choice"] = request.tool_choice
        if not request.parallel_tool_calls:
            body["parallel_tool_calls"] = False
    if request.max_tokens is not None:
        body.pop("max_tokens", None)
        body[max_tokens_field] = request.max_tokens
    return body


def _new_id() -> str:
    return f"call_{uuid.uuid4().hex[:24]}"


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


def _structured_calls(message: Mapping[str, Any], offered: frozenset[str]) -> list[ToolCall]:
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        legacy = message.get("function_call")
        raw_calls = [{"function": legacy}] if isinstance(legacy, dict) else []
    calls: list[ToolCall] = []
    seen: set[str] = set()
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        function = mapping_of(raw.get("function"))
        name = string_of(function.get("name"))
        call_id = string_of(raw.get("id")) or _new_id()
        # A server that numbers calls per turn can repeat an id across them;
        # the conversation needs each one distinct.
        if call_id in seen:
            call_id = _new_id()
        seen.add(call_id)
        arguments, text, problem = parse_arguments(function.get("arguments"), name=name, offered=offered)
        calls.append(ToolCall(id=call_id, name=name, arguments=arguments, raw_arguments=text, problem=problem))
    return calls


def _text_call(body: str, offered: frozenset[str]) -> ToolCall | None:
    """The call one `<tool_call>` block holds, or None when it names no
    offered tool."""
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        named = _TEXT_CALL_NAME.search(body)
        if named is None or named.group(1) not in offered:
            return None
        broken = CallProblem(CallProblemKind.MALFORMED_ARGUMENTS, "the call block is not valid JSON")
        return ToolCall(id=_new_id(), name=named.group(1), raw_arguments=body, problem=broken, from_text=True)
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or name not in offered:
        return None
    arguments, raw, problem = parse_arguments(data.get("arguments", {}), name=name, offered=offered)
    return ToolCall(id=_new_id(), name=name, arguments=arguments, raw_arguments=raw, problem=problem, from_text=True)


def _calls_in_text(text: str, offered: frozenset[str]) -> tuple[list[ToolCall], str]:
    """Calls the model wrote as `<tool_call>` blocks, and the text without them.

    Only a block that names an offered tool is a call; anything else stays
    in the text, since the model may be quoting or explaining. The blocks are
    found by scanning for the tags, not by a pattern: a pattern with
    whitespace on both sides of the body backtracks without end over an
    unclosed block, and this runs on the event loop.
    """
    calls: list[ToolCall] = []
    kept: list[str] = []
    position = 0
    while (start := text.find(_OPEN, position)) >= 0:
        end = text.find(_CLOSE, start + len(_OPEN))
        if end < 0:
            break
        kept.append(text[position:start])
        call = _text_call(text[start + len(_OPEN):end].strip(), offered)
        if call is None:
            kept.append(text[start:end + len(_CLOSE)])
        else:
            calls.append(call)
        position = end + len(_CLOSE)
    kept.append(text[position:])
    return (calls, "".join(kept).strip()) if calls else (calls, text)


def _usage(body: Mapping[str, Any], wall_time_ms: int | None) -> Usage:
    usage = mapping_of(body.get("usage"))
    details = mapping_of(usage.get("prompt_tokens_details"))

    def count(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    return Usage(
        input_tokens=count(usage.get("prompt_tokens")),
        output_tokens=count(usage.get("completion_tokens")),
        cached_input_tokens=count(details.get("cached_tokens")),
        wall_time_ms=wall_time_ms,
    )


def read_turn(body: object, *, request: ToolRequest, model: str, wall_time_ms: int | None = None) -> Turn:
    """A chat completions response as a `Turn`. Raises only when the body is
    not a completion at all."""
    if not isinstance(body, dict):
        raise ToolTransportError("The model's response was not a JSON object.", failure_class="validation")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ToolTransportError("The model's response had no completion choice.", failure_class="validation")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ToolTransportError("The model's completion carried no message.", failure_class="validation")
    text = _text_of(message.get("content"))
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    reasoning = reasoning if isinstance(reasoning, str) and reasoning else None
    thought = _THINK.match(text)
    if thought:
        reasoning = reasoning or thought.group(1).strip() or None
        text = text[thought.end():]

    offered = request.offered()
    calls = _structured_calls(message, offered)
    if not calls and offered and request.tool_choice != "none":
        calls, text = _calls_in_text(text, offered)

    refusal = message.get("refusal")
    finish = choice.get("finish_reason")
    raw_stop = finish if isinstance(finish, str) else None
    if isinstance(refusal, str) and refusal:
        stop, text = StopReason.REFUSAL, text or refusal
    elif raw_stop == "length":
        stop = StopReason.MAX_TOKENS
    elif raw_stop == "content_filter":
        stop = StopReason.REFUSAL
    elif calls:
        stop = StopReason.TOOL_USE
    else:
        stop = StopReason.END
    return Turn(
        message=AssistantMessage(text=text.strip(), tool_calls=tuple(calls)),
        stop_reason=stop,
        usage=_usage(body, wall_time_ms),
        model=str(body.get("model") or model),
        raw_stop=raw_stop,
        missing_tool_call=request.tool_choice == "required" and bool(offered) and not calls,
        reasoning=reasoning,
    )

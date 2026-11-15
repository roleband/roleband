"""A tool-calling conversation, in no provider's words.

A runner holds a conversation of `Message`s, offers `ToolDefinition`s and gets
back a `Turn`: final text, or one or more `ToolCall`s. It answers the calls
with `ToolResults` and asks again. Each wire format (`openai_format`,
`anthropic_format`) translates to and from these types and nothing else, so a
conversation can move between a local and a cloud model mid-run.

A call the model got wrong (arguments that are not a JSON object, a tool that
was never offered) is still a `ToolCall`, carrying a `CallProblem`. The runner
answers it with `ToolResult.for_problem`, which tells the model what to fix;
the transport never raises over what a model wrote.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

#: What both formats accept as a tool name.
TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

#: How the model may answer: `auto` lets it choose between text and calls,
#: `required` asks for at least one call, `none` forbids calls.
ToolChoice = Literal["auto", "required", "none"]

#: Why a request failed, as a runner decides what to do next: `timeout`,
#: `connection` and `rate_limited` may be retried, `http_error` and
#: `validation` (a body the transport could not read) are not.
FailureClass = Literal["timeout", "connection", "rate_limited", "http_error", "validation"]


class StopReason(StrEnum):
    """Why the model stopped, normalized across formats."""

    END = "end"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    REFUSAL = "refusal"


class CallProblemKind(StrEnum):
    MALFORMED_ARGUMENTS = "malformed_arguments"
    UNKNOWN_TOOL = "unknown_tool"


class ToolTransportError(RuntimeError):
    """A request that produced no turn. Never raised over what a model wrote."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: FailureClass,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class: FailureClass = failure_class
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class ToolDefinition:
    """A tool the model may call: its name, what it does, and a JSON Schema
    object for its arguments."""

    name: str
    description: str
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not TOOL_NAME.fullmatch(self.name):
            raise ValueError(f"tool name {self.name!r} is not 1 to 64 letters, digits, '_' or '-'")
        if not self.description.strip():
            raise ValueError(f"tool {self.name!r} has no description")
        if self.parameters.get("type") != "object":
            raise ValueError(f"tool {self.name!r}: its parameters are a JSON Schema of type object")


@dataclass(frozen=True)
class CallProblem:
    kind: CallProblemKind
    detail: str


@dataclass(frozen=True)
class ToolCall:
    """One call the model asked for.

    `arguments` is the parsed object, empty when `problem` is set.
    `raw_arguments` is the JSON text as the model wrote it, or None for a
    call a runner built itself; a format that carries arguments as text sends
    it back verbatim when it parsed, and serializes `arguments` otherwise.
    `from_text` marks a call recovered from a `<tool_call>` block the model
    wrote into its answer instead of the structured field.
    """

    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    raw_arguments: str | None = None
    problem: CallProblem | None = None
    from_text: bool = False


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False

    @classmethod
    def for_problem(cls, call: ToolCall) -> ToolResult:
        """The answer to a call that cannot run, telling the model what to fix."""
        if call.problem is None:
            raise ValueError(f"call {call.id} has no problem to report")
        if call.problem.kind is CallProblemKind.UNKNOWN_TOOL:
            text = f"There is no tool named {call.name!r}. {call.problem.detail}"
        else:
            text = (
                f"The arguments for {call.name!r} were not a JSON object ({call.problem.detail}). "
                f"You sent: {(call.raw_arguments or '')[:500]}. Call it again with a JSON object."
            )
        return cls(call_id=call.id, content=text, is_error=True)


@dataclass(frozen=True)
class ToolResults:
    """The answers to every call of the assistant message before it."""

    results: tuple[ToolResult, ...]


Message = UserMessage | AssistantMessage | ToolResults


@dataclass(frozen=True)
class Usage:
    """Tokens of one call. `input_tokens` counts the whole prompt, cached
    tokens included; `cached_input_tokens` says how many of them were cached."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    wall_time_ms: int | None = None


@dataclass(frozen=True)
class Turn:
    """One model answer.

    `message` is what to append to the conversation. `raw_stop` keeps the
    provider's own word for why it stopped. `missing_tool_call` is set when
    the request required a call and the model answered in text instead.
    `reasoning` is the thinking a local server returned beside the answer; it
    is never sent back.
    """

    message: AssistantMessage
    stop_reason: StopReason
    usage: Usage
    model: str
    raw_stop: str | None = None
    missing_tool_call: bool = False
    reasoning: str | None = None

    @property
    def text(self) -> str:
        return self.message.text

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return self.message.tool_calls


@dataclass(frozen=True)
class ToolRequest:
    """Everything a format needs to build one request body."""

    conversation: Sequence[Message]
    tools: Sequence[ToolDefinition] = ()
    system: str | None = None
    tool_choice: ToolChoice = "auto"
    parallel_tool_calls: bool = True
    max_tokens: int | None = None

    def offered(self) -> frozenset[str]:
        return frozenset(tool.name for tool in self.tools)


def check_conversation(conversation: Sequence[Message], tools: Sequence[ToolDefinition] = ()) -> None:
    """Refuse a conversation no format can send, before anything is sent.

    It opens with the person, every tool call is answered by the `ToolResults`
    right after it, and no result answers a call that was not made. Both
    formats reject anything else with an HTTP 400 that names no cause.
    """
    names = [tool.name for tool in tools]
    if len(set(names)) != len(names):
        raise ValueError("two tools share a name")
    if not conversation:
        raise ValueError("a conversation needs at least one message")
    if not isinstance(conversation[0], UserMessage):
        raise ValueError("a conversation opens with a user message")
    pending: list[str] = []
    for index, message in enumerate(conversation):
        if pending and not isinstance(message, ToolResults):
            raise ValueError(f"message {index}: the tool calls before it are not answered")
        if isinstance(message, AssistantMessage):
            ids = [call.id for call in message.tool_calls]
            if len(set(ids)) != len(ids):
                raise ValueError(f"message {index}: two tool calls share an id")
            pending = ids
        elif isinstance(message, ToolResults):
            answered = [result.call_id for result in message.results]
            if sorted(answered) != sorted(pending):
                raise ValueError(
                    f"message {index}: results answer {sorted(answered)}, the calls were {sorted(pending)}"
                )
            pending = []
    if pending:
        raise ValueError("the last assistant message's tool calls are not answered")


def mapping_of(value: object) -> Mapping[str, Any]:
    """A JSON object from a response body, or an empty one for anything else."""
    return value if isinstance(value, dict) else {}


def string_of(value: object) -> str:
    return value if isinstance(value, str) else ""


def parse_arguments(raw: Any, *, name: str, offered: frozenset[str]) -> tuple[dict[str, Any], str, CallProblem | None]:
    """Arguments as a format delivered them, read into an object.

    Returns the object, its JSON text and the problem, if any. Text that is
    not JSON, or JSON that is not an object, is a problem, not an error; so is
    a tool that was not offered.
    """
    if isinstance(raw, Mapping):
        arguments: Any = dict(raw)
        text = json.dumps(arguments, ensure_ascii=False)
    elif raw is not None and not isinstance(raw, str):
        # A format that delivers parsed arguments delivered something else.
        arguments = raw
        text = json.dumps(raw, ensure_ascii=False, default=str)
    else:
        text = raw or ""
        stripped = text.strip()
        if not stripped:
            arguments, text = {}, "{}"
        else:
            try:
                arguments = json.loads(stripped)
            except json.JSONDecodeError as exc:
                return {}, text, CallProblem(CallProblemKind.MALFORMED_ARGUMENTS, f"invalid JSON: {exc.msg}")
            except (ValueError, RecursionError) as exc:
                # An integer past Python's digit limit, or nesting past the
                # recursion limit: valid-looking text no reader should accept.
                return {}, text, CallProblem(CallProblemKind.MALFORMED_ARGUMENTS, f"unreadable JSON: {type(exc).__name__}")
    if not isinstance(arguments, dict):
        return {}, text, CallProblem(
            CallProblemKind.MALFORMED_ARGUMENTS, f"a JSON {type(arguments).__name__}, not an object"
        )
    if name not in offered:
        listed = ", ".join(sorted(offered)) or "none"
        return {}, text, CallProblem(CallProblemKind.UNKNOWN_TOOL, f"The tools offered are: {listed}.")
    return arguments, text, None


def replay_arguments(call: ToolCall) -> dict[str, Any]:
    """The arguments to send back in an assistant message: the parsed object,
    or an empty one for a call that had a problem (its result says what the
    model sent)."""
    return dict(call.arguments) if call.problem is None else {}

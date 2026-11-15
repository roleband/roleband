"""Tool calling over the OpenAI-compatible and Anthropic wire formats.

`conversation` holds the provider-neutral types, `openai_format` and
`anthropic_format` translate them, and `transport` sends one request for a
tier the routing ladder admitted. The one-prompt clients in `local_llm` and
`cloud_llm` stay as they are; this package serves a runner that loops over
tool calls.
"""

from tracker.intelligence.tool_calls.conversation import (
    AssistantMessage,
    CallProblem,
    CallProblemKind,
    Message,
    StopReason,
    ToolCall,
    ToolChoice,
    ToolDefinition,
    ToolResult,
    ToolResults,
    ToolTransportError,
    Turn,
    Usage,
    UserMessage,
)
from tracker.intelligence.tool_calls.transport import (
    TierNotAdmitted,
    ToolTransport,
    transport_for_tier,
)

__all__ = [
    "AssistantMessage",
    "CallProblem",
    "CallProblemKind",
    "Message",
    "StopReason",
    "TierNotAdmitted",
    "ToolCall",
    "ToolChoice",
    "ToolDefinition",
    "ToolResult",
    "ToolResults",
    "ToolTransport",
    "ToolTransportError",
    "Turn",
    "Usage",
    "UserMessage",
    "transport_for_tier",
]

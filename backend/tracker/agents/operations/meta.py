"""The handshake operations: who is answering, and what it offers.

`status` names the workspace, the engine session and how the connection is
trusted. `capabilities` is the index of operations; `describe` is one
operation. Both answer a summary view by default, sized for a small model's
context, and name their full view in `continue_with` (`index.py`). None of
them reads the person's data.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, RootModel
from pydantic.config import JsonDict

from tracker.agents.operations.descriptor import (
    OPERATION_ID,
    Access,
    AvailabilityState,
    ClientEffect,
    DataClass,
    EngineEffects,
    Idempotency,
    NoInput,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_DIAGNOSTIC: JsonDict = {"x-text": "diagnostic"}

#: How the engine treats a caller. `local_loopback`: the engine requires no local
#: authentication, so any process that reaches the loopback address is served;
#: TCP loopback cannot tell the engine which account or program called.
#: `signed_local_http`: the engine requires local authentication (packaged
#: Windows, or `ROLEBAND_LOCAL_AUTH=1`), and every request is signed with a key
#: from account-private discovery.
TrustMode = Literal["local_loopback", "signed_local_http"]


class EngineTrust(Shape):
    mode: TrustMode = Field(json_schema_extra=_CODE)
    #: Whether the engine proves its identity to the caller. Loopback trust
    #: does not, so a client must not treat a reply as verified.
    verified: bool


class AgentSwitchState(Shape):
    enabled: bool
    allow_writes: bool


class StatusResult(Shape):
    workspace_id: str = Field(json_schema_extra=_IDENTIFIER)
    engine_session_id: str = Field(json_schema_extra=_IDENTIFIER)
    engine_version: str = Field(json_schema_extra=_IDENTIFIER)
    contract_version: str = Field(json_schema_extra=_IDENTIFIER)
    trust: EngineTrust
    access: AgentSwitchState


class AvailabilityShape(Shape):
    state: AvailabilityState = Field(json_schema_extra=_CODE)
    reason: str | None = Field(json_schema_extra=_CODE)


class EffectsShape(Shape):
    state_write: bool
    outbound_network: bool
    model_egress: bool
    external_action: bool


class OperationSummary(Shape):
    operation: str = Field(json_schema_extra=_IDENTIFIER)
    summary: str = Field(json_schema_extra=_DIAGNOSTIC)
    access: Access = Field(json_schema_extra=_CODE)
    availability: AvailabilityShape
    engine_effects: EffectsShape
    client_effects: list[ClientEffect] = Field(json_schema_extra=_CODE)
    data_classes: list[DataClass] = Field(json_schema_extra=_CODE)
    tool_tiers: list[ToolTier] = Field(json_schema_extra=_CODE)
    idempotency: Idempotency = Field(json_schema_extra=_CODE)


#: summary: what a caller needs to choose an operation; full: every entry's metadata.
DiscoveryView = Literal["summary", "full"]


class CapabilitiesInput(Shape):
    tier: ToolTier | None = Field(default=None, description="List only the operations in this tool tier.")
    view: DiscoveryView = Field(
        default="summary",
        description="summary (each resource's summary and operation ids) or full (each operation's summary, "
        "access, availability, effects, data classes, tiers and idempotency).",
    )


class _Versions(Shape):
    contract_version: str = Field(json_schema_extra=_IDENTIFIER)
    supported_contract_versions: list[str] = Field(json_schema_extra=_IDENTIFIER)
    #: Null in the client's bundled index, which no engine answered.
    engine_version: str | None = Field(json_schema_extra=_IDENTIFIER)
    metadata_source: Literal["bundled", "engine"] = Field(json_schema_extra=_CODE)


class ResourceIndex(Shape):
    summary: str = Field(json_schema_extra=_DIAGNOSTIC)
    #: The ids of the resource's operations; `describe` gives each one's summary.
    operations: list[str] = Field(json_schema_extra=_IDENTIFIER)


class CapabilitiesSummary(_Versions):
    view: Literal["summary"] = Field(json_schema_extra=_CODE)
    #: Each resource's summary and operations, by name.
    resources: dict[str, ResourceIndex]
    #: The engine and client effects of each operation that has any, by id.
    #: An operation absent here only reads.
    effects: dict[str, list[str]]
    #: Why each operation that cannot be called now cannot, by id. Null when
    #: the answer is the client's bundled index, which cannot know.
    unavailable: dict[str, str] | None
    #: The full view of the same list.
    continue_with: list[NextAction]


class CapabilitiesFull(_Versions):
    view: Literal["full"] = Field(json_schema_extra=_CODE)
    operations: list[OperationSummary]


class CapabilitiesResult(RootModel[CapabilitiesSummary | CapabilitiesFull]):
    """The operation index in the view asked for; `view` names which."""

    root: CapabilitiesSummary | CapabilitiesFull = Field(discriminator="view")


class DescribeInput(Shape):
    operation: str = Field(
        min_length=1, max_length=128, pattern=OPERATION_ID, description="A dotted operation id from capabilities."
    )
    view: DiscoveryView = Field(
        default="summary",
        description="summary (how to call it: input schema, effects, scopes, examples) or full (also its "
        "output schema).",
    )


class _OperationFacts(Shape):
    operation: str = Field(json_schema_extra=_IDENTIFIER)
    contract_version: str = Field(json_schema_extra=_IDENTIFIER)
    introduced: str = Field(json_schema_extra=_IDENTIFIER)
    summary: str = Field(json_schema_extra=_DIAGNOSTIC)
    access: Access = Field(json_schema_extra=_CODE)
    input_schema: dict[str, Any]
    required_scopes: list[str] = Field(json_schema_extra=_CODE)
    engine_effects: EffectsShape
    client_effects: list[ClientEffect] = Field(json_schema_extra=_CODE)
    data_classes: list[DataClass] = Field(json_schema_extra=_CODE)
    tool_tiers: list[ToolTier] = Field(json_schema_extra=_CODE)
    idempotency: Idempotency = Field(json_schema_extra=_CODE)
    supports_dry_run: bool
    availability: AvailabilityShape
    metadata_source: Literal["bundled", "engine"] = Field(json_schema_extra=_CODE)
    examples: list[dict[str, Any]]


class OperationBrief(_OperationFacts):
    """How to call one operation. Its input schema leaves out the titles
    derived from field names; its output schema is in the full view."""

    view: Literal["summary"] = Field(json_schema_extra=_CODE)
    #: The full view, with the output schema.
    continue_with: list[NextAction]


class OperationDetail(_OperationFacts):
    view: Literal["full"] = Field(json_schema_extra=_CODE)
    output_schema_ref: str = Field(json_schema_extra=_IDENTIFIER)
    output_schema: dict[str, Any]


class OperationView(RootModel[OperationBrief | OperationDetail]):
    """One operation in the view asked for; `view` names which."""

    root: OperationBrief | OperationDetail = Field(discriminator="view")


_HANDSHAKE = EngineEffects()
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

STATUS = OperationDescriptor(
    id="status",
    summary="Name the workspace and the engine answering, and how the connection is trusted.",
    input=NoInput,
    result=StatusResult,
    access="read",
    idempotency="read",
    engine_effects=_HANDSHAKE,
    tool_tiers=_EVERY_TIER,
)

CAPABILITIES = OperationDescriptor(
    id="capabilities",
    summary="List the operations this engine offers and whether each can be called now.",
    input=CapabilitiesInput,
    result=CapabilitiesResult,
    access="read",
    idempotency="read",
    engine_effects=_HANDSHAKE,
    # The client brings an installed skill older than its own up to date.
    client_effects=("file_write",),
    tool_tiers=_EVERY_TIER,
    examples=({"tier": "small"}, {"view": "full"}),
)

DESCRIBE = OperationDescriptor(
    id="describe",
    summary="Describe one operation: its input and output schemas, effects and data classes.",
    input=DescribeInput,
    result=OperationView,
    access="read",
    idempotency="read",
    engine_effects=_HANDSHAKE,
    tool_tiers=_EVERY_TIER,
    examples=({"operation": "status"}, {"operation": "status", "view": "full"}),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (STATUS, CAPABILITIES, DESCRIBE)

"""The handshake operations: who is answering, and what it offers.

`status` names the workspace, the engine session and how the connection is
trusted. `capabilities` is the short index of operations; `describe` is one
operation in full. None of them reads the person's data.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field
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

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_DIAGNOSTIC: JsonDict = {"x-text": "diagnostic"}

#: How the engine knows who is calling. `same_account_loopback`: any process of
#: this user account that reaches the loopback address is trusted, which is how
#: the Mac app serves today; nothing proves which program called.
#: `signed_local_http`: requests are signed with a key from account-private
#: discovery (the packaged Windows engine).
TrustMode = Literal["same_account_loopback", "signed_local_http"]


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
    client_effects: list[ClientEffect]
    data_classes: list[DataClass]
    tool_tiers: list[ToolTier]
    idempotency: Idempotency = Field(json_schema_extra=_CODE)


class CapabilitiesInput(Shape):
    tier: ToolTier | None = Field(default=None, description="List only the operations in this tool tier.")


class CapabilitiesResult(Shape):
    contract_version: str = Field(json_schema_extra=_IDENTIFIER)
    supported_contract_versions: list[str]
    #: Null in the client's bundled index, which no engine answered.
    engine_version: str | None = Field(json_schema_extra=_IDENTIFIER)
    metadata_source: Literal["bundled", "engine"] = Field(json_schema_extra=_CODE)
    operations: list[OperationSummary]


class DescribeInput(Shape):
    operation: str = Field(
        min_length=1, max_length=128, pattern=OPERATION_ID, description="A dotted operation id from capabilities."
    )


class OperationDetail(Shape):
    operation: str = Field(json_schema_extra=_IDENTIFIER)
    contract_version: str = Field(json_schema_extra=_IDENTIFIER)
    introduced: str = Field(json_schema_extra=_IDENTIFIER)
    summary: str = Field(json_schema_extra=_DIAGNOSTIC)
    access: Access = Field(json_schema_extra=_CODE)
    input_schema: dict[str, Any]
    output_schema_ref: str = Field(json_schema_extra=_IDENTIFIER)
    output_schema: dict[str, Any]
    required_scopes: list[str]
    engine_effects: EffectsShape
    client_effects: list[ClientEffect]
    data_classes: list[DataClass]
    tool_tiers: list[ToolTier]
    idempotency: Idempotency = Field(json_schema_extra=_CODE)
    supports_dry_run: bool
    availability: AvailabilityShape
    metadata_source: Literal["bundled", "engine"] = Field(json_schema_extra=_CODE)
    examples: list[dict[str, Any]]


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
    tool_tiers=_EVERY_TIER,
    examples=({"tier": "small"},),
)

DESCRIBE = OperationDescriptor(
    id="describe",
    summary="Describe one operation: its input and output schemas, effects and data classes.",
    input=DescribeInput,
    result=OperationDetail,
    access="read",
    idempotency="read",
    engine_effects=_HANDSHAKE,
    tool_tiers=_EVERY_TIER,
    examples=({"operation": "status"},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (STATUS, CAPABILITIES, DESCRIBE)

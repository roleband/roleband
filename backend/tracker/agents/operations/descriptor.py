"""What an operation is: its identity, its typed shapes and what it may do.

A descriptor is reviewed metadata, not behaviour. Help, schemas, the bundled
client index and availability are all derived from it, so an operation's
effects are declared once, here, and never inferred from its route.

Engine effects are what the engine does on the caller's behalf (write state,
reach the network, send data to a model, act outside the machine). The
client's own connection to the engine is not one of them. Client effects are
what the client does on this computer (write a file, open a browser or the
app). An export, for example, is an engine read plus a client file write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from tracker.agents.operations.outcomes import CONTRACT_VERSION

DataClass = Literal["public_posting", "market_statistic", "private_pursuit", "offer", "candidate"]
ToolTier = Literal["small", "standard", "full"]
Idempotency = Literal["read", "required_key", "natural_key"]
ClientEffect = Literal["file_write", "browser_open", "app_open"]
#: Which of the person's two agent switches an operation needs: a read needs
#: `enabled`, a write needs `enabled` and `allow_writes`.
Access = Literal["read", "write"]
AvailabilityState = Literal["available", "unavailable", "unknown"]

#: An operation id: lowercase segments joined by dots.
OPERATION_ID = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"
_DOTTED = re.compile(OPERATION_ID)
_VERSION = re.compile(r"^1\.[0-9]+$")


class Shape(BaseModel):
    """An operation's input or result: every key is known, an unknown one is an error."""

    model_config = ConfigDict(extra="forbid")


class NoInput(Shape):
    """The input of an operation that takes none."""


@dataclass(frozen=True)
class EngineEffects:
    state_write: bool = False
    outbound_network: bool = False
    model_egress: bool = False
    external_action: bool = False


@dataclass(frozen=True)
class OperationDescriptor:
    """One operation. `id` is its dotted name (`opportunities.search`); a
    one-segment id is kept for the handshake operations (`status`)."""

    id: str
    summary: str
    input: type[BaseModel]
    result: type[BaseModel]
    access: Access
    idempotency: Idempotency
    engine_effects: EngineEffects
    tool_tiers: tuple[ToolTier, ...]
    #: The data classes a result can contain. A handshake operation names none.
    data_classes: tuple[DataClass, ...] = ()
    client_effects: tuple[ClientEffect, ...] = ()
    #: The contract version this operation's shapes belong to.
    version: str = CONTRACT_VERSION
    #: The contract version that first offered it.
    introduced: str = CONTRACT_VERSION
    supports_dry_run: bool = False
    examples: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not _DOTTED.fullmatch(self.id):
            raise ValueError(f"operation id {self.id!r} is not lowercase dotted segments")
        for name, value in (("version", self.version), ("introduced", self.introduced)):
            if not _VERSION.fullmatch(value):
                raise ValueError(f"{self.id}: {name} {value!r} is not a 1.x contract version")
        if not self.tool_tiers:
            raise ValueError(f"{self.id}: an operation belongs to at least one tool tier")
        for name, values in (("tool_tiers", self.tool_tiers), ("data_classes", self.data_classes),
                             ("client_effects", self.client_effects)):
            if len(set(values)) != len(values):
                raise ValueError(f"{self.id}: {name} repeats a value")
        writes = self.engine_effects.state_write or self.engine_effects.external_action
        if writes and self.access != "write":
            raise ValueError(f"{self.id}: an operation that writes state needs write access")
        if self.access == "read" and self.idempotency != "read":
            raise ValueError(f"{self.id}: a read is idempotent as a read")
        if self.access == "write" and self.idempotency == "read":
            raise ValueError(f"{self.id}: a write declares its idempotency key")
        if self.input.model_config.get("extra") != "forbid":
            raise ValueError(f"{self.id}: its input must refuse unknown keys")

    @property
    def required_scopes(self) -> tuple[str, ...]:
        if self.access == "write":
            return ("agent_access.enabled", "agent_access.allow_writes")
        return ("agent_access.enabled",)

    def summary_entry(self, availability: Availability) -> dict[str, Any]:
        """The short index entry `capabilities` lists."""
        return {
            "operation": self.id,
            "summary": self.summary,
            "access": self.access,
            "availability": availability.as_dict(),
            "engine_effects": _effects(self.engine_effects),
            "client_effects": list(self.client_effects),
            "data_classes": list(self.data_classes),
            "tool_tiers": list(self.tool_tiers),
            "idempotency": self.idempotency,
        }

    def full_entry(self, availability: Availability, *, source: Literal["bundled", "engine"]) -> dict[str, Any]:
        """Everything `describe` returns: the operation descriptor contract."""
        return {
            "operation": self.id,
            "contract_version": self.version,
            "introduced": self.introduced,
            "summary": self.summary,
            "access": self.access,
            "input_schema": self.input.model_json_schema(),
            "output_schema_ref": f"#/operations/{self.id}/output_schema",
            "output_schema": self.result.model_json_schema(),
            "required_scopes": list(self.required_scopes),
            "engine_effects": _effects(self.engine_effects),
            "client_effects": list(self.client_effects),
            "data_classes": list(self.data_classes),
            "tool_tiers": list(self.tool_tiers),
            "idempotency": self.idempotency,
            "supports_dry_run": self.supports_dry_run,
            "availability": availability.as_dict(),
            "metadata_source": source,
            "examples": [dict(example) for example in self.examples],
        }


@dataclass(frozen=True)
class Availability:
    """Whether an operation can be called now, and why not. Bundled metadata
    cannot know, so it says `unknown`, never `unavailable`."""

    state: AvailabilityState
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.state == "available") != (self.reason is None):
            raise ValueError("an available operation has no reason; any other state has one")

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "reason": self.reason}


AVAILABLE = Availability("available")
#: What bundled metadata says: only an engine knows the person's switches.
UNKNOWN = Availability("unknown", "offline")


def _effects(effects: EngineEffects) -> dict[str, bool]:
    return {
        "state_write": effects.state_write,
        "outbound_network": effects.outbound_network,
        "model_egress": effects.model_egress,
        "external_action": effects.external_action,
    }

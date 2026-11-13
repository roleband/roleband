"""Whether the person's agent switches admit an operation.

The two switches are the ones the Settings screen already shows
(`tracker/agents/config.py`): `enabled` admits reads, and `allow_writes`
admits writes on top of it. With `enabled` off every operation is refused,
the handshake included, so a switched-off connection learns nothing but that.
"""

from __future__ import annotations

from typing import Protocol

from tracker.agents.operations.descriptor import AVAILABLE, Availability, OperationDescriptor
from tracker.agents.operations.envelope import NextAction, OperationError


class AgentSwitches(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def allow_writes(self) -> bool: ...


def availability(descriptor: OperationDescriptor, switches: AgentSwitches) -> Availability:
    if not switches.enabled:
        return Availability("unavailable", "access_disabled")
    if descriptor.access == "write" and not switches.allow_writes:
        return Availability("unavailable", "writes_disabled")
    return AVAILABLE


def admit(descriptor: OperationDescriptor, switches: AgentSwitches) -> None:
    """Raise the refusal for `descriptor` under these switches, or return."""
    state = availability(descriptor, switches)
    if state.state == "available":
        return
    if state.reason == "access_disabled":
        raise OperationError(
            "access_disabled",
            "Agent access is off. The person can turn it on in Settings.",
            details={"setting": "agent_access.enabled"},
        )
    raise OperationError(
        "writes_disabled",
        "Agent changes are off. The person can allow them in Settings.",
        details={"setting": "agent_access.allow_writes"},
        next_actions=[NextAction(operation="describe", arguments={"operation": descriptor.id})],
    )

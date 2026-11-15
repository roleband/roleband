"""Whether the person's agent switches admit an operation.

The two switches are the ones the Settings screen already shows
(`tracker/agents/config.py`): `enabled` admits reads, and `allow_writes`
admits writes on top of it. With `enabled` off every operation is refused,
the handshake included, so a switched-off connection learns nothing but that.

Under them, the person chooses per data category who may read it
(`docs/decisions/0017-agent-access-open-by-default.md`). A category switched
off is absent, not masked:

- an operation whose primary category (the first it declares) is not shared
  is refused with `category_disabled`;
- an operation leaves out the part of its answer that belongs to any other
  category it declares that is not shared, and refuses an input that would
  select by that part.

Every caller of these operations is an assistant outside the engine, which
RoleBand cannot hold to models on this computer, so `local_only` reads as not
shared here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from tracker.agents.operations.descriptor import (
    AVAILABLE,
    Availability,
    DataClass,
    OperationDescriptor,
)
from tracker.agents.operations.envelope import NextAction, OperationError


class AgentSwitches(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def allow_writes(self) -> bool: ...

    @property
    def categories(self) -> Mapping[DataClass, str]: ...


#: How each category is named to the caller.
CATEGORY_NAMES: dict[DataClass, str] = {
    "public_posting": "postings",
    "market_statistic": "market statistics",
    "private_pursuit": "pursuits and notes",
    "offer": "offer",
    "candidate": "candidate profile",
}


def shared(switches: AgentSwitches, category: DataClass) -> bool:
    """Whether an assistant outside the engine may read `category`. A
    category with no stored choice is shared; `enabled` off shares nothing."""
    return switches.enabled and switches.categories.get(category, "any_model") == "any_model"


def withheld(descriptor: OperationDescriptor, switches: AgentSwitches) -> frozenset[DataClass]:
    """The categories `descriptor` declares that these switches do not share."""
    return frozenset(category for category in descriptor.data_classes if not shared(switches, category))


def availability(descriptor: OperationDescriptor, switches: AgentSwitches) -> Availability:
    if not switches.enabled:
        return Availability("unavailable", "access_disabled")
    if descriptor.data_classes and not shared(switches, descriptor.data_classes[0]):
        return Availability("unavailable", "category_disabled")
    if descriptor.access == "write" and not switches.allow_writes:
        return Availability("unavailable", "writes_disabled")
    return AVAILABLE


def category_disabled(category: DataClass, *, field: str | None = None) -> OperationError:
    """The refusal of a call that would read `category` while it is not
    shared. It says no more than that: nothing of the category is in it.
    `field` names the input that would have selected by it."""
    details: dict[str, str] = {"category": category, "setting": f"agent_access.categories.{category}"}
    if field is not None:
        details["field"] = field
    return OperationError(
        "category_disabled",
        f"The person does not share their {CATEGORY_NAMES[category]} with assistants. "
        "They can share it in Settings.",
        details=details,
    )


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
    if state.reason == "category_disabled":
        raise category_disabled(descriptor.data_classes[0])
    raise OperationError(
        "writes_disabled",
        "Agent changes are off. The person can allow them in Settings.",
        details={"setting": "agent_access.allow_writes"},
        next_actions=[NextAction(operation="describe", arguments={"operation": descriptor.id})],
    )

"""Every operation the engine offers, listed once.

Adding an operation is a descriptor in its own module, its tuple added to
`REGISTERED`, and its route in the agent router; nothing else is edited. The
bundled client index (`tracker/cli/operations.json`) is generated from this
list by `scripts.export_agent_operations`, and a test fails while it is stale.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from tracker.agents.operations import meta
from tracker.agents.operations.descriptor import UNKNOWN, OperationDescriptor, ToolTier
from tracker.agents.operations.outcomes import CONTRACT_VERSION

#: The one registration list.
REGISTERED: tuple[OperationDescriptor, ...] = (*meta.OPERATIONS,)


class Catalog:
    def __init__(self, descriptors: Iterable[OperationDescriptor]) -> None:
        self._by_id: dict[str, OperationDescriptor] = {}
        for descriptor in descriptors:
            if descriptor.id in self._by_id:
                raise ValueError(f"operation {descriptor.id!r} is registered twice")
            self._by_id[descriptor.id] = descriptor

    def __iter__(self) -> Iterator[OperationDescriptor]:
        return iter(sorted(self._by_id.values(), key=lambda descriptor: descriptor.id))

    def __contains__(self, operation_id: object) -> bool:
        return operation_id in self._by_id

    def get(self, operation_id: str) -> OperationDescriptor | None:
        return self._by_id.get(operation_id)

    def in_tier(self, tier: ToolTier | None) -> list[OperationDescriptor]:
        return [descriptor for descriptor in self if tier is None or tier in descriptor.tool_tiers]


CATALOG = Catalog(REGISTERED)


def bundled_index(catalog: Catalog = CATALOG) -> dict[str, Any]:
    """What the client ships: every descriptor in full, availability unknown."""
    return {
        "format": 1,
        "contract_version": CONTRACT_VERSION,
        "operations": [descriptor.full_entry(UNKNOWN, source="bundled") for descriptor in catalog],
    }

"""Every operation the engine offers, listed once.

Adding an operation is a descriptor in its own module, its tuple added to
`REGISTERED`, and its route in the agent router; nothing else is edited. The
bundled client index (`tracker/cli/operations.json`) is generated from this
list by `scripts.export_agent_operations`, and a test fails while it is stale.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from tracker.agents.operations import (
    applications,
    background,
    brief,
    changes,
    companies,
    duplicates,
    export,
    insights,
    meta,
    offer,
    opportunities,
    picks,
    pursuits,
    radar,
    receipts,
    recipes,
    relations,
    search,
    steps,
    vocabulary,
)
from tracker.agents.operations.descriptor import UNKNOWN, OperationDescriptor, ToolTier
from tracker.agents.operations.index import resource_of
from tracker.agents.operations.outcomes import CONTRACT_VERSION

#: The one registration list.
REGISTERED: tuple[OperationDescriptor, ...] = (
    *meta.OPERATIONS,
    *radar.OPERATIONS,
    *opportunities.OPERATIONS,
    *pursuits.OPERATIONS,
    *steps.OPERATIONS,
    *recipes.OPERATIONS,
    *receipts.OPERATIONS,
    *changes.OPERATIONS,
    *search.OPERATIONS,
    *vocabulary.OPERATIONS,
    *companies.OPERATIONS,
    *relations.OPERATIONS,
    *offer.OPERATIONS,
    *applications.OPERATIONS,
    *export.OPERATIONS,
    *insights.OPERATIONS,
    *duplicates.OPERATIONS,
    *background.OPERATIONS,
    *brief.OPERATIONS,
    *picks.OPERATIONS,
)


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

#: What each resource is for, in one line: the index `capabilities` answers
#: by default lists these and the ids under them, and leaves each operation's
#: own summary to `describe`. Every resource of the catalog has one.
RESOURCES: dict[str, str] = {
    "applications": "Applications: the board of stages and the interview calendar.",
    "background": "Who the person is: their background, as read and confirmed.",
    "brief": "What the person wants from a move, in versions.",
    "capabilities": "The operations this engine offers.",
    "changes": "What changed after a position: postings, stated pay, steps due, source health.",
    "companies": "Followed companies: profiles, sourced facts, share prices.",
    "context": "One opportunity as one hashed packet.",
    "describe": "How to call one operation.",
    "doctor": "The engine's checks and settings.",
    "duplicates": "Duplicate postings: pairs worth deciding, and verdicts.",
    "insights": "Market figures: open roles, pay by level and country, trends, skills.",
    "offer": "The person's own offer.",
    "opportunities": "Open roles: search, one posting, its history, similar and duplicates.",
    "picks": "Top picks: roles to judge, verdicts, the mode.",
    "pursuits": "Saved and pursued roles: stage, priority, notes, next steps.",
    "radar": "Counts of open and saved roles, pursuits by stage, overdue steps.",
    "receipts": "What a write sent under an idempotency key did.",
    "recipes": "Careers-site listing recipes: the contract, a live preview, drafts.",
    "sources": "One public careers page, fetched.",
    "status": "The workspace and engine answering.",
    "steps": "A pursuit's next steps: add, change, tick done, open again.",
    "vocabulary": "The values a search filter accepts.",
}


def resources(catalog: Catalog = CATALOG) -> dict[str, str]:
    """The summary of each resource `catalog` has, by name."""
    names = sorted({resource_of(descriptor.id) for descriptor in catalog})
    if missing := [name for name in names if name not in RESOURCES]:
        raise ValueError(f"resources without a summary in RESOURCES: {missing}")
    return {name: RESOURCES[name] for name in names}


def bundled_index(catalog: Catalog = CATALOG) -> dict[str, Any]:
    """What the client ships: every descriptor in full, availability unknown,
    and each resource's summary."""
    return {
        "format": 1,
        "contract_version": CONTRACT_VERSION,
        "operations": [descriptor.full_entry(UNKNOWN, source="bundled") for descriptor in catalog],
        "resources": resources(catalog),
    }

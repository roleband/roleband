"""`vocabulary.list`, and the strict reading of a filter value.

Search filters on closed vocabularies: companies, role families, level bands,
tracks, workplace types, domains and locations. An agent does not know their
slugs, so it passes what a person would say ("ML", "London", "OpenAI"). The
rules, each against a way a search could mislead:

- **Match exactly, after normalising spelling only.** Case, surrounding space
  and runs of space, hyphen or slash are not meaning, so "Product Management",
  "product-management" and "product_management" are one value. Nothing fuzzier:
  a guessed match would narrow to rows the agent did not ask for.
- **An unknown value is an error, never a silent empty result.** A value that
  matches no accepted spelling fails the whole search with `invalid_input`,
  naming every unknown value with its filter and the `vocabulary.list` call
  that lists the accepted ones. Answering zero rows would read to a person as
  a fact about the market ("there are no ML roles").
- A KNOWN value that matches no posting still narrows to zero: that zero is a
  true answer about the radar, not about the vocabulary.

`vocabulary.list` lists one kind's accepted values: the value to filter by,
its display name, the other names it is accepted by, and how many open roles
the Board lists under it now. The counts are the Board's filter counts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, get_args

from pydantic import Field
from pydantic.config import JsonDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations import cursor
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape, ToolTier
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.company_store import OffBoardSlugs, off_board_company_slugs
from tracker.db.models import Job, TrackedCompany
from tracker.db.queries.jobs import (
    LEVEL_FACET_KEY,
    domain_facet_count_stmt,
    facet_count_stmt,
    place_facet_count_stmt,
    unclassified_domain_count_stmt,
)
from tracker.levels import LEVELS, UNSTATED_LEVEL
from tracker.schema import WorkplaceType
from tracker.settings_store import get_enabled_locations
from tracker.taxonomy.domains import DOMAIN_GROUPS
from tracker.taxonomy.locations import location_names
from tracker.taxonomy.role_catalog import UNCLASSIFIED_KEY
from tracker.taxonomy.roles import ROLE_GROUPS
from tracker.taxonomy.tracks import TRACKS

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

#: Every closed vocabulary a search filters on. Each name is also the search
#: filter's input field, so the lookup a failure names reads as its flag.
Kind = Literal["company", "family", "level_band", "track", "workplace_type", "domain", "location"]
KINDS: tuple[Kind, ...] = get_args(Kind)

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

#: What the Board calls the level a posting does not state, and a workplace it does not state.
_UNSTATED_LEVEL_NAME = "Level not stated"
_WORKPLACE_NAMES = {
    WorkplaceType.ONSITE.value: "On-site",
    WorkplaceType.REMOTE.value: "Remote",
    WorkplaceType.HYBRID.value: "Hybrid",
    WorkplaceType.UNKNOWN.value: "Not stated",
}

_SEPARATORS = re.compile(r"[\s\-/]+")


def normalize(value: str) -> str:
    """The spelling-only key a value is compared by."""
    return _SEPARATORS.sub("_", value.strip().casefold()).strip("_")


# --- the vocabularies -------------------------------------------------------- #


@dataclass
class Vocabulary:
    """One kind's accepted values, in display order, and every spelling of each."""

    kind: Kind
    #: value -> display name.
    names: dict[str, str | None] = field(default_factory=dict)
    #: value -> the other names it is accepted by.
    also: dict[str, list[str]] = field(default_factory=dict)
    #: normalised spelling -> value. A value's own spelling always names it;
    #: a name two values share names neither, so the caller must use the value.
    spellings: dict[str, str] = field(default_factory=dict)

    @classmethod
    def of(cls, kind: Kind, pairs: Iterable[tuple[str, str | None]]) -> Vocabulary:
        """From (value, name) pairs in precedence order: a value's first pair
        is its display name, later ones are other names for it."""
        vocabulary = cls(kind)
        pairs = list(pairs)
        for value, name in pairs:
            if value not in vocabulary.names:
                vocabulary.names[value] = name
                vocabulary.also[value] = []
                vocabulary.spellings[normalize(value)] = value
        own = set(vocabulary.spellings)
        named: dict[str, set[str]] = {}
        for value, name in pairs:
            if not name:
                continue
            if name != vocabulary.names[value] and name not in vocabulary.also[value]:
                vocabulary.also[value].append(name)
            key = normalize(name)
            if key not in own:
                named.setdefault(key, set()).add(value)
        for key, values in named.items():
            if len(values) == 1:
                vocabulary.spellings[key] = next(iter(values))
        for value, also in vocabulary.also.items():
            also[:] = [name for name in also if vocabulary.value_of(name) == value]
        return vocabulary

    def value_of(self, spelling: str) -> str | None:
        return self.spellings.get(normalize(spelling))


async def load(session: AsyncSession, kind: Kind) -> Vocabulary:
    """The values `kind` accepts now. Locations follow the person's tracked
    places, as the Board's location filter does; companies are every company
    the person has, followed or not."""
    if kind == "company":
        rows = (await session.execute(
            select(TrackedCompany.slug, TrackedCompany.display).order_by(TrackedCompany.slug)
        )).all()
        return Vocabulary.of(kind, ((slug, display) for slug, display in rows))
    if kind == "family":
        return Vocabulary.of(kind, ((group.slug, group.display) for group in ROLE_GROUPS))
    if kind == "level_band":
        return Vocabulary.of(
            kind, [*((level.slug, level.display) for level in LEVELS), (UNSTATED_LEVEL, _UNSTATED_LEVEL_NAME)]
        )
    if kind == "track":
        return Vocabulary.of(kind, ((track.slug, track.display) for track in TRACKS))
    if kind == "workplace_type":
        return Vocabulary.of(kind, _WORKPLACE_NAMES.items())
    if kind == "domain":
        return Vocabulary.of(
            kind, [*((group.slug, group.display) for group in DOMAIN_GROUPS), (UNCLASSIFIED_KEY, "Unclassified")]
        )
    return Vocabulary.of(kind, location_names(await get_enabled_locations(session)))


async def open_roles(session: AsyncSession, kind: Kind, hidden: OffBoardSlugs) -> dict[str, int]:
    """Open roles the Board lists under each value of `kind`: its filter counts."""
    if kind == "location":
        statement = place_facet_count_stmt(hidden)
    elif kind == "domain":
        statement = domain_facet_count_stmt(hidden)
    else:
        column = {
            "company": Job.company,
            "family": Job.family,
            "level_band": LEVEL_FACET_KEY,
            "track": Job.track,
            "workplace_type": Job.workplace_type,
        }[kind]
        statement = facet_count_stmt(column, hidden)
    counts = {str(value): int(count) for value, count in (await session.execute(statement)).all() if value is not None}
    if kind == "domain":
        counts[UNCLASSIFIED_KEY] = int(await session.scalar(unclassified_domain_count_stmt(hidden)) or 0)
    return counts


# --- strict filter values ---------------------------------------------------- #


@dataclass
class Unknown:
    kind: Kind
    value: str


def resolve(vocabulary: Vocabulary, values: Sequence[str], unknown: list[Unknown]) -> list[str]:
    """`values` as the slugs they name, in order and once each. A value that
    names nothing is added to `unknown`; the caller refuses the request."""
    kept: list[str] = []
    for value in values:
        slug = vocabulary.value_of(value)
        if slug is None:
            unknown.append(Unknown(vocabulary.kind, value))
        elif slug not in kept:
            kept.append(slug)
    return kept


def refuse_unknown(unknown: list[Unknown]) -> None:
    """Fail with every unknown value and the lookup that lists each filter's values."""
    if not unknown:
        return
    kinds = list(dict.fromkeys(item.kind for item in unknown))
    named = "; ".join(
        f"{kind} {', '.join(repr(item.value[:80]) for item in unknown if item.kind == kind)}" for kind in kinds
    )
    raise OperationError(
        "invalid_input",
        f"No accepted value matches {named}. Nothing was searched: list the accepted values with "
        "vocabulary.list for that kind and search again with one of them.",
        details={
            "reason": "unknown_value",
            "unknown": [{"filter": item.kind, "value": item.value[:200]} for item in unknown],
        },
        next_actions=[NextAction(operation=VOCABULARY_LIST.id, arguments={"kind": kind}) for kind in kinds],
    )


# --- the operation ----------------------------------------------------------- #


class VocabularyListInput(Shape):
    kind: Kind = Field(description="The filter whose accepted values to list.")
    contains: str | None = Field(
        default=None, min_length=1, max_length=100,
        description="Only values whose value or a name contains this, ignoring case and separators.",
    )
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Values on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page, read with the same kind and contains.",
    )


class VocabularyEntry(Shape):
    #: The value a search filter takes.
    value: str = Field(json_schema_extra=_IDENTIFIER)
    #: Its display name; null where the value has none of its own. A name
    #: another value also has is shown but not accepted: filter by `value`.
    name: str | None = Field(json_schema_extra=_CONTENT)
    #: Other names the filter accepts for this value, such as "USA" or "Bay Area".
    also: list[str] = Field(json_schema_extra=_CONTENT)
    #: Open roles the Board lists under this value now.
    open_roles: int = Field(ge=0)


class VocabularyPage(Shape):
    kind: Kind = Field(json_schema_extra=_CODE)
    #: Values matching the request, on every page together.
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    #: Most open roles first, then by value; `meta.next_cursor` reads the next page.
    items: list[VocabularyEntry]


VOCABULARY_LIST = OperationDescriptor(
    id="vocabulary.list",
    summary="List the values a search filter accepts, with their names and open roles.",
    input=VocabularyListInput,
    result=VocabularyPage,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting",),
    examples=({"kind": "location", "contains": "york"}, {"kind": "family"}),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (VOCABULARY_LIST,)


async def vocabulary_page(
    session: AsyncSession, params: VocabularyListInput, *, workspace_id: str
) -> tuple[VocabularyPage, str | None]:
    """One page of one kind's values, and the cursor of the next when there is one."""
    request = cursor.fingerprint(
        VOCABULARY_LIST.id, workspace_id, {"kind": params.kind, "contains": params.contains}
    )
    offset = 0
    if params.cursor is not None:
        offset, _ = cursor.decode(params.cursor, request=request)
    vocabulary = await load(session, params.kind)
    counts = await open_roles(session, params.kind, await off_board_company_slugs(session))
    needle = normalize(params.contains) if params.contains else None
    entries = [
        VocabularyEntry(
            value=value, name=name, also=vocabulary.also[value], open_roles=counts.get(value, 0)
        )
        for value, name in vocabulary.names.items()
        if needle is None
        or any(needle in normalize(text) for text in (value, name or "", *vocabulary.also[value]))
    ]
    entries.sort(key=lambda entry: (-entry.open_roles, entry.value))
    page = entries[offset: offset + params.limit]
    end = offset + len(page)
    next_cursor = (
        cursor.encode(request=request, offset=end) if end < len(entries) else None
    )
    return VocabularyPage(kind=params.kind, total=len(entries), count=len(page), items=page), next_cursor

"""`opportunities.search`: the Board's list, filtered and sorted as the Board does.

The filters are the Board's own (`db/queries/jobs.py`): text, companies, role
families, level bands, tracks, workplace types, domains, locations, base pay
bounds, minimum estimated pay, discloses pay, saved only and the listing
window. Every closed-vocabulary value is read strictly
(`operations/vocabulary.py`): one that matches nothing fails the search with
the lookup that lists the accepted values, never an empty page.

The text query is the Board's search box. Under a column sort it matches whole
words through the search index; under `best_match` it is the Board's Best
match, which ranks exact, close and related matches and parses the query on
this computer only. Queryless `best_match` is the Board's Best matches by the
person's intent, or the default order while there is none.

A page is a table of summary rows: `columns` names each position of a row
once, so a page of twenty fits a small model's budget. A row holds the facts
that pick a role out, the employer's stated pay and RoleBand's estimate as
separate columns, and the person's own mark, no text; `opportunities.get`
reads the rest. A page holds at most `limit` rows and stops early rather than
outgrow its tool tier's budget; `next_cursor` continues where it stopped, so
no row is cut or lost to the budget. Paging is live, not a snapshot: a posting that appears,
closes or re-sorts between two pages can be missed or repeated.

A category the person does not share is absent: without their pursuits the
`pursuit` column is left out of `columns` and every row, `saved_only` is
refused. Queryless `best_match` ranks by the person's intent, which blends
the statement in their candidate profile with the roles they saved, pursue
and dismissed: each part counts only while its category is shared, and with
neither the order is the default. Without market statistics the `estimated_pay` column is left out, and
`minimum_estimated_pay` and the `estimated_pay` sort are refused.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator
from pydantic.config import JsonDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations import cursor, vocabulary
from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import OperationError
from tracker.agents.operations.policy import category_disabled
from tracker.analytics.posting_reality import listing_age
from tracker.company_store import off_board_company_slugs
from tracker.db.models import Favorite, Job, Pursuit
from tracker.db.queries.jobs import apply_job_filters, list_rows, resolve_ordering
from tracker.pay_disclosure import disclosure_known
from tracker.pay_period import effective_period
from tracker.platform.util import MAX_WINDOW_DAYS
from tracker.search.best_match import intent_ranking, relevance_search
from tracker.semantic.embed import embed_query
from tracker.semantic.intent import build_intent_vector, combine_intent_vector
from tracker.settings_store import get_intent_embedding

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

#: The most a page (its header, the filters it echoes and its rows) may take,
#: by tool tier, in UTF-8 bytes of its JSON. Stated in tokens for the whole
#: reply (2,000 for the small tier, 4,000 for the standard one, 16,000 for
#: full) and enforced at two and a half bytes a token, the rate this JSON
#: tokenizes at, less 900 bytes for the envelope around the page with its
#: cursor and every warning a page can carry.
PAGE_BUDGET_BYTES: dict[ToolTier, int] = {"small": 4_100, "standard": 9_100, "full": 39_100}

#: The Board's sorts, by the names its menu gives them, and the list key each one reads.
Sort = Literal["best_match", "newest", "age", "pay", "estimated_pay", "level", "company", "title", "location"]
_SORT_KEYS: dict[str, str] = {
    "best_match": "relevance",
    "newest": "first_seen",
    "age": "days_open",
    "pay": "base_pay",
    "estimated_pay": "comp_median",
    "level": "level_band",
    "company": "company",
    "title": "title",
    "location": "location",
}

_Value = Annotated[str, Field(min_length=1, max_length=200)]
_Values = Annotated[list[_Value], Field(max_length=50)]
_Pay = Annotated[int, Field(ge=0, le=100_000_000)]


class SearchInput(Shape):
    query: str | None = Field(
        default=None, min_length=1, max_length=200,
        description="Words to search for, as in the Board's search box.",
    )
    company: _Values = Field(default_factory=list, description="Companies, by slug or name; repeat for more.")
    family: _Values = Field(default_factory=list, description="Role families, by slug or name.")
    level_band: _Values = Field(default_factory=list, description="Level bands, such as senior or staff.")
    track: _Values = Field(default_factory=list, description="Tracks, such as ic or management.")
    workplace_type: _Values = Field(default_factory=list, description="onsite, remote, hybrid or unknown.")
    domain: _Values = Field(default_factory=list, description="Domains (worlds), by slug or name.")
    location: _Values = Field(
        default_factory=list, description="Places, by slug or a name people use, such as London or USA."
    )
    base_pay_min: _Pay | None = Field(default=None, description="Lowest yearly base in US dollars, as the Board's pay filter.")
    base_pay_max: _Pay | None = Field(default=None, description="Highest yearly base in US dollars.")
    minimum_estimated_pay: _Pay | None = Field(
        default=None, description="Lowest estimated pay: the estimated total, else the estimated base."
    )
    discloses_pay: bool = Field(default=False, description="Only postings that state a pay band.")
    saved_only: bool = Field(default=False, description="Only roles the person saved.")
    listed_within_days: int | None = Field(
        default=None, ge=1, le=MAX_WINDOW_DAYS,
        description="Only postings listed within this many days, by the age each row shows.",
    )
    sort: Sort | None = Field(
        default=None, description="Default: best_match with a query, else newest.",
    )
    order: Literal["asc", "desc"] = Field(default="desc", description="Ignored by best_match.")
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Most rows on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page, read with the same filters and sort.",
    )
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")

    @model_validator(mode="after")
    def _bounds_in_order(self) -> SearchInput:
        if self.base_pay_min is not None and self.base_pay_max is not None and self.base_pay_min > self.base_pay_max:
            raise ValueError("base_pay_min is more than base_pay_max")
        return self


#: Each position of a row, in order.
COLUMNS: tuple[str, ...] = (
    "id", "title", "company", "location", "more_locations", "workplace", "level", "listed_days",
    "stated_pay", "estimated_pay", "pursuit",
)

#: One opportunity, positioned as `COLUMNS` names: its id; title; company
#: slug; the first place it names and how many more; workplace type; level
#: band; the listing age every surface shows, in days; the employer's stated
#: pay; RoleBand's estimate; the person's mark.
#:
#: `stated_pay` is null until the posting's text has been read for pay, `none`
#: when it states no band, else `LOW-HIGH CURRENCY/PERIOD BASIS` (`LOW+` or
#: `up to HIGH` for a one-sided band; a part the posting leaves out is left
#: out). `estimated_pay` is `MEDIAN CURRENCY total`, or `... base` where the
#: data prices the posting by its base alone; null without an estimate. It is
#: never the employer's figure. `pursuit` is the person's pursuit stage,
#: `saved` for a role they saved and pursue no further, null otherwise.
SearchRow = tuple[
    int, str, str, str | None, int, str | None, str | None, int | None, str | None, str | None, str | None
]
#: A row as a page answers it: `SearchRow` less the columns of a category the
#: person does not share, so its positions are the ones `columns` names.
PageRow = tuple[int | str | None, ...]

#: The column each category that a row can leave out owns.
_CATEGORY_COLUMNS: dict[DataClass, str] = {"market_statistic": "estimated_pay", "private_pursuit": "pursuit"}


class SearchPage(Shape):
    #: Rows matching the search on every page together.
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    sort: Sort = Field(json_schema_extra=_CODE)
    order: Literal["asc", "desc"] | None = Field(json_schema_extra=_CODE)
    #: Each closed-vocabulary filter as the values it was read as.
    filters: dict[str, list[str]] = Field(json_schema_extra=_IDENTIFIER)
    columns: list[str] = Field(json_schema_extra=_CODE)
    rows: list[PageRow] = Field(
        json_schema_extra={"x-text": "content"},
        description="One array per opportunity, its values in the order `columns` names.",
    )


OPPORTUNITIES_SEARCH = OperationDescriptor(
    id="opportunities.search",
    summary="Search the Board's open roles with its filters and sorts; one page of summary rows.",
    input=SearchInput,
    result=SearchPage,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting", "market_statistic", "private_pursuit", "candidate"),
    examples=(
        {"query": "product manager", "location": ["London"], "limit": 10},
        {"family": ["product_management"], "level_band": ["senior"], "sort": "estimated_pay"},
    ),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (OPPORTUNITIES_SEARCH,)

#: The input fields that are closed vocabularies, each named as its kind.
_CLOSED: tuple[vocabulary.Kind, ...] = vocabulary.KINDS
#: The fields a cursor does not bind: a later page may change its size or tier.
_PAGING = frozenset({"cursor", "limit", "tier"})


@dataclass(frozen=True)
class SearchAnswer:
    page: SearchPage
    next_cursor: str | None
    #: True when the tier's budget ended the page before `limit` rows.
    shortened: bool
    #: True when more postings match than best match could rank, as the
    #: Board reports it: paging to the end does not reach them all.
    ranking_truncated: bool = False
    #: True when the page's only row was longer than the budget and its
    #: longest text was cut to fit; `opportunities.get` gives it whole.
    row_cut: bool = False


async def search(
    session: AsyncSession, params: SearchInput, *, workspace_id: str, withheld: Collection[DataClass] = (),
    now: datetime | None = None,
) -> SearchAnswer:
    now = now or datetime.now(UTC)
    pursuits = "private_pursuit" not in withheld
    statistics = "market_statistic" not in withheld
    profile = "candidate" not in withheld
    if params.saved_only and not pursuits:
        raise category_disabled("private_pursuit", field="saved_only")
    if params.minimum_estimated_pay is not None and not statistics:
        raise category_disabled("market_statistic", field="minimum_estimated_pay")
    if params.sort == "estimated_pay" and not statistics:
        raise category_disabled("market_statistic", field="sort")
    unknown: list[vocabulary.Unknown] = []
    filters: dict[str, list[str]] = {}
    for kind in _CLOSED:
        given: list[str] = getattr(params, kind)
        if given:
            filters[kind] = vocabulary.resolve(await vocabulary.load(session, kind), given, unknown)
    vocabulary.refuse_unknown(unknown)

    sort: Sort = params.sort or ("best_match" if params.query else "newest")
    request = cursor.fingerprint(
        OPPORTUNITIES_SEARCH.id,
        workspace_id,
        {**params.model_dump(mode="json", exclude=set(_PAGING)), "sort": sort, "filters": filters},
    )
    offset, carried = (0, 0)
    if params.cursor is not None:
        offset, carried = cursor.decode(params.cursor, request=request)

    hidden = await off_board_company_slugs(session)
    board: dict[str, Any] = {
        "status": "open",
        "company": filters.get("company"),
        "family": filters.get("family"),
        "level_band": filters.get("level_band"),
        "track": filters.get("track"),
        "workplace_type": filters.get("workplace_type"),
        "domain": filters.get("domain"),
        "location_group": filters.get("location"),
        "q": params.query,
        "base_min": params.base_pay_min,
        "base_max": params.base_pay_max,
        "comp_min": params.minimum_estimated_pay,
        "posted_within_days": params.listed_within_days,
        "discloses_pay": params.discloses_pay,
        "favorites_only": params.saved_only,
        "hidden": hidden,
        "unfollowed": getattr(hidden, "unfollowed", frozenset()),
    }
    # Best match has its own order; `order` reorders only the other sorts.
    order = "desc" if sort == "best_match" else params.order
    ordered = await _ordered(session, board, sort=sort, order=order, query=params.query,
                             offset=offset, limit=params.limit, exact_seen=carried,
                             from_profile=profile, from_taste=pursuits)

    left_out = {_CATEGORY_COLUMNS[category] for category in withheld if category in _CATEGORY_COLUMNS}
    columns = [column for column in COLUMNS if column not in left_out]
    kept_at = [COLUMNS.index(column) for column in columns]
    rows: list[PageRow] = [
        tuple(row[i] for i in kept_at) for row in await _rows(session, ordered.jobs, now=now, pursuits=pursuits)
    ]
    page = SearchPage(
        total=ordered.total,
        count=0,
        sort=sort,
        order=None if sort == "best_match" else params.order,
        filters=filters,
        columns=columns,
        rows=[],
    )
    # The rows share the page's budget with its header, whose filters grow with the request.
    budget = PAGE_BUDGET_BYTES[params.tier]
    header = _size(page.model_dump(mode="json"))
    kept, cut = _within_budget(rows, budget - header)
    if kept and _size(kept[0]) + 1 > budget - header or header > budget:
        raise OperationError(
            "invalid_input",
            "These filters leave no room for a row in the tier's budget; pass fewer filter values or a larger tier.",
            details={"field": "tier", "reason": "over_budget", "budget_bytes": budget, "header_bytes": header},
        )
    page.count, page.rows = len(kept), kept
    end = offset + len(kept)
    next_cursor = (
        cursor.encode(request=request, offset=end, carried=ordered.exact)
        if end < ordered.total
        else None
    )
    return SearchAnswer(
        page, next_cursor, shortened=len(kept) < len(rows), ranking_truncated=ordered.ranking_truncated,
        row_cut=cut,
    )


# --- ordering ---------------------------------------------------------------- #


@dataclass(frozen=True)
class _Ordered:
    #: The rows from the requested position, at most `limit` of them.
    jobs: list[Job]
    total: int
    #: Best match's exact rows, which lead every page of it; the next cursor carries the count.
    exact: int = 0
    ranking_truncated: bool = False


async def _ordered(
    session: AsyncSession, board: dict[str, Any], *, sort: Sort, order: str, query: str | None,
    offset: int, limit: int, exact_seen: int, from_profile: bool = True, from_taste: bool = True,
) -> _Ordered:
    if sort == "best_match" and query:
        return await _best_match(session, board, query, offset=offset, limit=limit, exact_seen=exact_seen)
    if sort == "best_match" and (from_profile or from_taste):
        stored = await get_intent_embedding(session) if from_profile else None
        vector = stored["vector"] if stored else None
        # The taste centroids come from saved, pursued and dismissed roles.
        intent = await build_intent_vector(session, vector) if from_taste else combine_intent_vector(vector, [], [])
        if intent is not None:
            ranking = await intent_ranking(session, board, intent, limit, offset)
            return _Ordered([row.job for row in ranking.rows], ranking.total)
    base = apply_job_filters(select(Job), board)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    statement = list_rows(base.order_by(*resolve_ordering(_SORT_KEYS[sort], order)).limit(limit).offset(offset))
    return _Ordered(list((await session.scalars(statement)).all()), total)


async def _best_match(
    session: AsyncSession, board: dict[str, Any], query: str, *, offset: int, limit: int, exact_seen: int
) -> _Ordered:
    """The Board's Best match as one list: an exact-title or identifier match
    whole, then the related matches. The engine answers the exact rows whole
    and pages only the related ones, so the cursor carries how many exact
    rows came first."""
    async def ranked(related_offset: int) -> tuple[list[Job], int, int, bool]:
        result = await relevance_search(
            session, board, query, limit, related_offset, include_related=True,
            embed=embed_query, parse_with_model=False,
        )
        if result.query_kind == "exploratory":
            return [row.job for row in result.rows], result.total, -1, result.ranking_truncated
        exact = [row.job for row in result.rows]
        return (
            [*exact, *(row.job for row in result.related_rows)],
            len(exact) + result.related_total, len(exact), result.ranking_truncated,
        )

    asked = max(0, offset - exact_seen)
    jobs, total, exact, cut = await ranked(asked)
    if exact < 0:
        return _Ordered(jobs, total, ranking_truncated=cut)
    if max(0, offset - exact) != asked:
        # The exact set changed size since the previous page: read the related page it now starts at.
        jobs, total, exact, cut = await ranked(max(0, offset - exact))
        if exact < 0:
            return _Ordered(jobs, total, ranking_truncated=cut)
    head = jobs[offset:exact] if offset < exact else []
    return _Ordered([*head, *jobs[exact:]][:limit], total, exact, ranking_truncated=cut)


# --- rows -------------------------------------------------------------------- #


async def _rows(session: AsyncSession, jobs: list[Job], *, now: datetime, pursuits: bool = True) -> list[SearchRow]:
    ids = [job.id for job in jobs]
    saved: set[int] = set()
    stages: dict[int, str] = {}
    if ids and pursuits:
        saved = set((await session.scalars(select(Favorite.job_id).where(Favorite.job_id.in_(ids)))).all())
        stages = {
            job_id: stage
            for job_id, stage in (
                await session.execute(select(Pursuit.job_id, Pursuit.stage).where(Pursuit.job_id.in_(ids)))
            ).all()
        }
    return [_row(job, saved=job.id in saved, stage=stages.get(job.id), now=now) for job in jobs]


def _row(job: Job, *, saved: bool, stage: str | None, now: datetime) -> SearchRow:
    listed_days = (
        listing_age(job.first_posted_at, job.first_seen, status=job.status, closed_at=job.closed_at, now=now)[1]
        if job.first_seen
        else None
    )
    places = job.locations or []
    return (
        job.id,
        job.title,
        job.company,
        places[0] if places else None,
        max(len(places) - 1, 0),
        job.workplace_type,
        job.level_band,
        listed_days,
        stated_pay(job),
        estimated_pay(job),
        stage or ("saved" if saved else None),
    )


def stated_pay(job: Job) -> str | None:
    """The employer's band as one row value; see `SearchRow`."""
    if not disclosure_known(job.structured_at, job.disclosed_base_min, job.disclosed_base_max):
        return None
    low, high = _whole(job.disclosed_base_min), _whole(job.disclosed_base_max)
    if low is None and high is None:
        return "none"
    band = f"{low}-{high}" if low is not None and high is not None else f"{low}+" if low is not None else f"up to {high}"
    # The period is checked against the amount, as every surface does.
    period = effective_period(
        job.disclosed_pay_period, job.disclosed_base_min, job.disclosed_base_max, job.disclosed_currency
    )
    unit = f"{job.disclosed_currency or ''}{f'/{period}' if period else ''}"
    return " ".join(part for part in (band, unit, job.disclosed_pay_basis) if part)


def estimated_pay(job: Job) -> str | None:
    """RoleBand's estimate as one row value: a total only where every part of
    it is known; a posting the data prices by its base alone has a base."""
    if job.comp_median is not None:
        median, of = job.comp_median, "total"
    elif job.comp_component == "base" and job.comp_base_median is not None:
        median, of = job.comp_base_median, "base"
    else:
        return None
    return " ".join(part for part in (str(round(median)), job.comp_currency, of) if part)


def _whole(value: float | int | None) -> int | None:
    return None if value is None else round(value)


def _size(value: object) -> int:
    """The UTF-8 bytes of `value` as compact JSON."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


#: The shortest a cut text cell becomes: enough to recognise the posting by.
_SHORTEST_CELL = 24


def _within_budget(rows: list[PageRow], budget: int) -> tuple[list[PageRow], bool]:
    """The leading rows whose JSON fits `budget` bytes, and whether the first
    one was cut to fit. A page always holds its first row, so paging never
    stops before it starts: one longer than the whole budget has its longest
    text cut until it fits, down to `_SHORTEST_CELL` characters a cell."""
    if not rows:
        return [], False
    first, cut = _fit(rows[0], budget)
    kept = [first]
    used = _size(first) + 1
    for row in rows[1:]:
        size = _size(row) + 1
        if used + size > budget:
            break
        kept.append(row)
        used += size
    return kept, cut


def _fit(row: PageRow, budget: int) -> tuple[PageRow, bool]:
    cells: list[Any] = list(row)
    cut = False
    while (excess := _size(cells) + 1 - budget) > 0:
        # A cell cut to the floor is that and its mark; it is not cut again.
        texts = [i for i, value in enumerate(cells) if isinstance(value, str) and len(value) > _SHORTEST_CELL + 1]
        if not texts:
            break
        longest = max(texts, key=lambda i: len(cells[i]))
        # A character takes at least one byte, so cutting `excess` of them (and one for the mark) suffices.
        keep = max(_SHORTEST_CELL, len(cells[longest]) - excess - 1)
        cells[longest] = cells[longest][:keep].rstrip() + "…"
        cut = True
    return tuple(cells), cut

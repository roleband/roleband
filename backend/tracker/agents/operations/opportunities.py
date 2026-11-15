"""`opportunities.get` and `opportunities.history`: one posting, by its id.

`get` answers one of three declared views. `summary` is the posting's facts and
pay, with the detail read in `continue_with`; `detail` adds its department, team and text; `evidence` adds what each
fact rests on: the posting's dates as each side recorded them, and every pay
source's answers. Employer-stated pay and estimates stay separate fields in
every view, and an estimate never fills a stated field.

A detail view is bounded by the caller's tool tier. Past the tier's budget it
is a typed excerpt: the description cut at a word, the sections left out, and
`excerpt` saying so with `truncated: true`. JSON is never cut.

A posting at a company the person hid is not found, unless the person saved or
pursues it: the agent is offered what the person still wants to see, and what
the person chose stays reachable, as it does from Saved. When the person does
not share their pursuits, that exception is not made, so whether a hidden
posting is found says nothing about them.

A category the person does not share is left out of `get`, its keys absent:
their pursuits (`saved` and `pursuit`, so no notes either) and market
statistics (the estimates and `evidence.estimate_sources`).
"""

from __future__ import annotations

import json
from collections.abc import Collection
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import Field, RootModel
from pydantic.config import JsonDict
from pydantic.experimental.missing_sentinel import MISSING
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.operations.pursuits import PURSUITS_GET, PursuitState, state_of
from tracker.analytics.posting_reality import listing_age
from tracker.db.models import Favorite, Job, JobCompEstimate, Pursuit, TrackedCompany
from tracker.db.queries.listing_history import listing_history
from tracker.pay_disclosure import disclosure_known
from tracker.pay_period import effective_period

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

View = Literal["summary", "detail", "evidence"]

#: The most a detail view's data may take, by tool tier, in UTF-8 bytes of its
#: JSON. The budgets are stated in tokens (6,000 for the small tier, 16,000
#: above it) and enforced at two and a half bytes a token, the rate this JSON
#: tokenizes at, so a byte budget admits no more tokens than it states.
DETAIL_BUDGET_BYTES: dict[ToolTier, int] = {"small": 15_000, "standard": 40_000, "full": 40_000}


# --- shapes ------------------------------------------------------------------ #


class EstimatedTotalComp(Shape):
    """RoleBand's estimate of total pay, from the posting's market data."""

    low: int | None
    median: int | None
    high: int | None
    currency: str = Field(json_schema_extra=_CODE)
    provenance: str | None = Field(json_schema_extra=_CODE)


class EstimatedBase(Shape):
    """An estimate of base pay alone, where the data prices the posting by its base."""

    low: int | None
    median: int | None
    high: int | None
    currency: str = Field(json_schema_extra=_CODE)
    provider: str | None = Field(json_schema_extra=_CODE)
    as_of: date | None


class EmployerStatedPay(Shape):
    """The pay band the posting itself states; null bounds when it states none."""

    low: int | None
    high: int | None
    currency: str | None = Field(json_schema_extra=_CODE)
    basis: str | None = Field(json_schema_extra=_CODE)
    period: str | None = Field(json_schema_extra=_CODE)
    #: The posting's own words the band was read from.
    snippet: str | None = Field(json_schema_extra=_CONTENT)


class _Facts(Shape):
    """What every view of a posting carries."""

    id: int
    company: str = Field(json_schema_extra=_IDENTIFIER)
    title: str = Field(json_schema_extra=_CONTENT)
    url: str = Field(json_schema_extra=_IDENTIFIER)
    locations: list[str] = Field(json_schema_extra=_CONTENT)
    workplace_type: str | None = Field(json_schema_extra=_CODE)
    level_band: str | None = Field(json_schema_extra=_CODE)
    family: str | None = Field(json_schema_extra=_CODE)
    track: str | None = Field(json_schema_extra=_CODE)
    status: str = Field(json_schema_extra=_CODE)
    first_seen: datetime | None
    #: The listing age every surface shows, from the earlier of the employer's
    #: date and RoleBand's first sighting; `listed_basis` says whose date it is.
    listed_since: datetime | None
    listed_days: int | None
    listed_basis: str | None = Field(json_schema_extra=_CODE)
    #: What the estimate prices: `total`, or `base` when only the base is known.
    #: The three estimate keys are absent when the person does not share
    #: market statistics.
    estimate_component: str | None | MISSING = Field(default=MISSING, json_schema_extra=_CODE)
    estimated_total_comp: EstimatedTotalComp | None | MISSING = MISSING
    estimated_base: EstimatedBase | None | MISSING = MISSING
    #: Null until the posting's text has been read for pay.
    employer_stated_pay: EmployerStatedPay | None
    #: Both absent when the person does not share their pursuits.
    saved: bool | MISSING = MISSING
    pursuit: PursuitState | None | MISSING = MISSING


class OpportunitySummary(_Facts):
    view: Literal["summary"] = Field(json_schema_extra=_CODE)
    #: The read that adds the posting's text, the detail view; empty when it has none.
    continue_with: list[NextAction] = Field(default_factory=list)


class PostingSection(Shape):
    key: str = Field(json_schema_extra=_CODE)
    title: str = Field(json_schema_extra=_CONTENT)
    content: str = Field(json_schema_extra=_CONTENT)


class Excerpt(Shape):
    """Present when the detail is not whole: it did not fit the tier's budget,
    or it was asked for from a point in the description. On a first read the
    description is cut first, and the pursuit's notes only when they alone do
    not fit; a read from a point leaves the notes out. `continue_with` names
    the calls that read the rest, so nothing cut is out of reach."""

    truncated: Literal[True]
    tier: ToolTier = Field(json_schema_extra=_CODE)
    budget_bytes: int
    #: The size the full detail view would have taken.
    full_bytes: int
    description_chars: int
    #: The character of the description this answer starts at.
    description_from: int = 0
    kept_chars: int
    omitted_sections: int
    #: The pursuit notes' length and how much of them is kept; null without notes.
    notes_chars: int | None = None
    kept_notes_chars: int | None = None
    #: The rest of the description from where this one stops, and the notes
    #: whole when they were cut; empty when nothing is left to read.
    continue_with: list[NextAction] = Field(default_factory=list)


class OpportunityDetail(_Facts):
    view: Literal["detail"] = Field(json_schema_extra=_CODE)
    department: str | None = Field(json_schema_extra=_CONTENT)
    team: str | None = Field(json_schema_extra=_CONTENT)
    description: str | None = Field(json_schema_extra=_CONTENT)
    description_sections: list[PostingSection]
    #: Null when the whole description is here.
    excerpt: Excerpt | None


class PostingDates(Shape):
    #: The employer's current date for the posting, which it can re-stamp.
    employer_published_at: datetime | None
    #: The earliest date the employer ever gave it; listing age starts here.
    employer_first_published_at: datetime | None
    #: When RoleBand first and last saw it listed; no employer can move these.
    first_seen: datetime | None
    last_seen: datetime | None
    closed_at: datetime | None
    #: When the description was last read; null if it never was.
    description_fetched_at: datetime | None


class ProviderAnswer(Shape):
    provider: str | None = Field(json_schema_extra=_CODE)
    median: int | float | None
    low: int | float | None
    high: int | float | None
    currency: str | None = Field(json_schema_extra=_CODE)
    source: str | None = Field(json_schema_extra=_CODE)


class EstimateSource(Shape):
    """One pay source's estimate for this posting and the answers behind it.
    RoleBand's own data and a plugin's are separate sources, never mixed."""

    source: str = Field(json_schema_extra=_CODE)
    estimated_at: datetime
    answers: list[ProviderAnswer]


class Evidence(Shape):
    dates: PostingDates
    #: Absent when the person does not share market statistics.
    estimate_sources: list[EstimateSource] | MISSING = MISSING


class OpportunityEvidence(_Facts):
    view: Literal["evidence"] = Field(json_schema_extra=_CODE)
    evidence: Evidence


class OpportunityView(RootModel[OpportunitySummary | OpportunityDetail | OpportunityEvidence]):
    """One posting in the view the caller asked for; `view` names which."""

    root: OpportunitySummary | OpportunityDetail | OpportunityEvidence = Field(discriminator="view")


class OpportunityGetInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity's id, as search returns it.")
    view: View = Field(default="summary", description="summary, detail (adds the text) or evidence.")
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds a detail view.")
    description_from: int | None = Field(
        default=None, ge=0,
        description=(
            "Detail view only: read the description from this character on, as an excerpt's "
            "continue_with gives it. The pursuit's notes are then left to pursuits.get."
        ),
    )


class OpportunityHistoryInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity's id, as search returns it.")


class HistoryHeadline(Shape):
    since: datetime
    days: int
    basis: str = Field(json_schema_extra=_CODE)


class HistoryRoleAge(Shape):
    since: datetime
    days: int
    postings: int


class HistoryEvent(Shape):
    """One dated fact. Every key is sent; those a kind does not use are null."""

    at: datetime
    kind: str = Field(json_schema_extra=_CODE)
    from_at: datetime | None
    to_at: datetime | None
    field: str | None = Field(json_schema_extra=_CODE)
    count: int | None
    job_id: int | None
    req_id: str | None = Field(json_schema_extra=_IDENTIFIER)
    title: str | None = Field(json_schema_extra=_CONTENT)
    until: datetime | None
    link: str | None = Field(json_schema_extra=_CODE)


class HistoryUnconfirmed(Shape):
    link_id: int
    job_id: int
    req_id: str | None = Field(json_schema_extra=_IDENTIFIER)
    title: str = Field(json_schema_extra=_CONTENT)
    listed_since: datetime


class ListingHistory(Shape):
    headline: HistoryHeadline
    #: Null for a posting counted as no role over several postings.
    role: HistoryRoleAge | None
    events: list[HistoryEvent]
    #: Possibly the same role; counted in no number until a person confirms it.
    unconfirmed: list[HistoryUnconfirmed]


OPPORTUNITIES_GET = OperationDescriptor(
    id="opportunities.get",
    summary="Read one opportunity in a declared view: summary, detail with its text, or evidence.",
    input=OpportunityGetInput,
    result=OpportunityView,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting", "market_statistic", "private_pursuit"),
    examples=({"opportunity_id": 4821, "view": "detail"},),
)

OPPORTUNITIES_HISTORY = OperationDescriptor(
    id="opportunities.history",
    summary="How long a posting has been listed and why: every dated event and the role's other postings.",
    input=OpportunityHistoryInput,
    result=ListingHistory,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting",),
    examples=({"opportunity_id": 4821},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (OPPORTUNITIES_GET, OPPORTUNITIES_HISTORY)


# --- reads ------------------------------------------------------------------- #


def _not_found(opportunity_id: int) -> OperationError:
    return OperationError(
        "not_found", "There is no opportunity with this id.", details={"opportunity_id": opportunity_id}
    )


async def visible_job(session: AsyncSession, opportunity_id: int, *, chosen_counts: bool = True) -> Job:
    """The posting, unless it is unknown or at a company the person hid and
    neither saved nor pursued. Both answer the same `not_found`, so a hidden
    posting cannot be told from a missing one. With `chosen_counts` false a
    saved or pursued posting at a hidden company is not found either."""
    job = await session.get(Job, opportunity_id)
    if job is None:
        raise _not_found(opportunity_id)
    hidden = await session.scalar(
        select(
            exists().where(TrackedCompany.slug == job.company, TrackedCompany.visible.is_(False))
        )
    )
    if hidden and not chosen_counts:
        raise _not_found(opportunity_id)
    if hidden:
        chosen = await session.scalar(
            select(
                or_(
                    exists().where(Favorite.job_id == opportunity_id),
                    exists().where(Pursuit.job_id == opportunity_id),
                )
            )
        )
        if not chosen:
            raise _not_found(opportunity_id)
    return job


def _summary_fields(job: Job, *, saved: bool, pursuit: Pursuit | None, now: datetime) -> dict[str, Any]:
    listed_since, listed_days, listed_basis = (
        listing_age(job.first_posted_at, job.first_seen, status=job.status, closed_at=job.closed_at, now=now)
        if job.first_seen
        else (None, None, None)
    )
    stated = disclosure_known(job.structured_at, job.disclosed_base_min, job.disclosed_base_max)
    has_amount = job.disclosed_base_min is not None or job.disclosed_base_max is not None
    return {
        "id": job.id,
        "company": job.company,
        "title": job.title,
        "url": job.url,
        "locations": job.locations or [],
        "workplace_type": job.workplace_type,
        "level_band": job.level_band,
        "family": job.family,
        "track": job.track,
        "status": job.status,
        "first_seen": job.first_seen,
        "listed_since": listed_since,
        "listed_days": listed_days,
        "listed_basis": listed_basis,
        # A total only where every part of it is known: a posting the data
        # prices by its base alone has a base, and no total.
        "estimate_component": job.comp_component,
        "estimated_total_comp": {
            "low": job.comp_low,
            "median": job.comp_median,
            "high": job.comp_high,
            "currency": job.comp_currency,
            "provenance": job.comp_provenance,
        } if job.comp_median is not None else None,
        "estimated_base": {
            "low": job.comp_base_low,
            "median": job.comp_base_median,
            "high": job.comp_base_high,
            "currency": job.comp_currency,
            "provider": job.comp_provider,
            "as_of": job.comp_as_of,
        } if job.comp_component == "base" and job.comp_base_median is not None else None,
        "employer_stated_pay": {
            "low": job.disclosed_base_min,
            "high": job.disclosed_base_max,
            "currency": job.disclosed_currency,
            "basis": job.disclosed_pay_basis,
            # The period is checked against the amount only when there is one:
            # a read posting that states no pay has no period to check.
            "period": effective_period(
                job.disclosed_pay_period, job.disclosed_base_min, job.disclosed_base_max, job.disclosed_currency,
            ) if has_amount else job.disclosed_pay_period,
            "snippet": job.disclosed_snippet,
        } if stated else None,
        "saved": saved,
        "pursuit": state_of(pursuit) if pursuit is not None else None,
    }


async def opportunity(
    session: AsyncSession, params: OpportunityGetInput, *, withheld: Collection[DataClass] = (),
    now: datetime | None = None,
) -> OpportunityView:
    """One posting in the view asked for, without the `withheld` categories."""
    pursuits = "private_pursuit" not in withheld
    job = await visible_job(session, params.opportunity_id, chosen_counts=pursuits)
    saved = await session.scalar(select(exists().where(Favorite.job_id == job.id))) if pursuits else None
    pursuit = await session.scalar(select(Pursuit).where(Pursuit.job_id == job.id)) if pursuits else None
    if params.description_from is not None and params.view != "detail":
        raise OperationError(
            "invalid_input", "description_from reads a detail view; ask with view detail.",
            details={"field": "description_from", "reason": "detail_only"},
        )
    fields = _summary_fields(job, saved=bool(saved), pursuit=pursuit, now=now or datetime.now(UTC))
    if not pursuits:
        for key in ("saved", "pursuit"):
            del fields[key]
    statistics = "market_statistic" not in withheld
    if not statistics:
        for key in ("estimate_component", "estimated_total_comp", "estimated_base"):
            del fields[key]
    if params.view == "detail":
        detail = {
            **fields,
            "view": "detail",
            "department": job.department,
            "team": job.team,
            "description": job.description_text,
            "description_sections": job.description_sections or [],
            "excerpt": None,
        }
        return OpportunityView(bounded_detail(detail, tier=params.tier, start=params.description_from))
    if params.view == "evidence":
        evidence = {**fields, "view": "evidence", "evidence": await _evidence(session, job, estimates=statistics)}
        return OpportunityView(OpportunityEvidence.model_validate(evidence))
    text = [NextAction(operation=OPPORTUNITIES_GET.id, arguments={
        "opportunity_id": job.id, "view": "detail", "tier": params.tier,
    })] if job.description_text or job.description_sections else []
    return OpportunityView(OpportunitySummary.model_validate({**fields, "view": "summary", "continue_with": text}))


async def _evidence(session: AsyncSession, job: Job, *, estimates: bool) -> dict[str, Any]:
    evidence = {
        "dates": {
            "employer_published_at": job.posted_at,
            "employer_first_published_at": job.first_posted_at,
            "first_seen": job.first_seen,
            "last_seen": job.last_seen,
            "closed_at": job.closed_at,
            "description_fetched_at": job.description_fetched_at,
        },
    }
    if not estimates:
        return evidence
    found = (
        await session.scalars(
            select(JobCompEstimate).where(JobCompEstimate.job_id == job.id).order_by(JobCompEstimate.source)
        )
    ).all()
    return {
        **evidence,
        "estimate_sources": [
            {
                "source": estimate.source,
                "estimated_at": estimate.estimated_at,
                "answers": [
                    {key: answer.get(key) for key in ProviderAnswer.model_fields}
                    for answer in estimate.sources or []
                ],
            }
            for estimate in found
        ],
    }


def _size(value: object) -> int:
    """UTF-8 bytes of `value` as the engine's JSON answer spells it."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode())


def bounded_detail(fields: dict[str, Any], *, tier: ToolTier, start: int | None = None) -> OpportunityDetail:
    """The detail view, whole when it fits the tier's budget, else a typed
    excerpt whose `continue_with` reads the rest. `start` reads the description
    from that character on, leaving the notes to `pursuits.get`, so a run of
    such reads always advances and their descriptions join into the whole."""
    full = OpportunityDetail.model_validate(fields)
    budget = DETAIL_BUDGET_BYTES[tier]
    full_bytes = len(full.model_dump_json().encode())
    # A read from the start of a detail that fits is the whole view, unmarked.
    if not start and full_bytes <= budget:
        return full
    text = full.description or ""
    begin = start or 0
    if begin > len(text):
        raise OperationError(
            "invalid_input", "description_from is past the end of the description.",
            details={"field": "description_from", "reason": "past_end", "description_chars": len(text)},
        )
    rest = text[begin:]
    pursuit = full.pursuit if isinstance(full.pursuit, PursuitState) else None
    notes = pursuit.notes if pursuit is not None else None
    excerpt = Excerpt(
        truncated=True, tier=tier, budget_bytes=budget, full_bytes=full_bytes,
        description_chars=len(text), description_from=begin, kept_chars=0,
        omitted_sections=len(full.description_sections),
        notes_chars=len(notes) if notes else None, kept_notes_chars=len(notes) if notes else None,
    )
    # Measured with the largest counts and calls the excerpt can carry, so
    # filling them in cannot take the answer past the budget.
    widest = excerpt.model_copy(update={
        "kept_chars": len(text), "continue_with": _continuations(full.id, tier, len(text), notes_cut=True),
    })
    shell = full.model_copy(update={"description": "", "description_sections": [], "excerpt": widest})
    room = budget - len(shell.model_dump_json().encode())
    if notes and pursuit is not None and (room < 0 or start is not None):
        # A read from a point is for the description; the notes are read whole elsewhere.
        kept_notes = "" if start is not None else _cut(notes, _size(notes) - 2 + room)
        shell = shell.model_copy(update={"pursuit": pursuit.model_copy(update={"notes": kept_notes})})
        excerpt = excerpt.model_copy(update={"kept_notes_chars": len(kept_notes)})
        # On a first read the notes' word-boundary slack is no room for a
        # scrap of description; on a read from a point the room is what is left.
        room = 0 if start is None else budget - len(shell.model_dump_json().encode())
    kept = _cut(rest, room)
    notes_cut = bool(notes) and excerpt.kept_notes_chars != len(notes or "")
    bounded = shell.model_copy(update={"description": kept, "excerpt": excerpt.model_copy(update={
        "kept_chars": len(kept),
        "continue_with": _continuations(full.id, tier, begin + len(kept), notes_cut=notes_cut)
        if begin + len(kept) < len(text) else _continuations(full.id, tier, None, notes_cut=notes_cut),
    })})
    # Only the description and the notes are cut. A posting whose other fields
    # alone pass the budget, or a read from a point that cannot advance, is
    # refused rather than answered past the budget or without progress.
    if len(bounded.model_dump_json().encode()) > budget or (start is not None and rest and not kept):
        raise OperationError(
            "invalid_input",
            "This posting's detail does not fit the tier's budget, even without its description.",
            details={"field": "tier", "reason": "over_budget", "budget_bytes": budget, "full_bytes": full_bytes},
        )
    return bounded


def _continuations(opportunity_id: int, tier: ToolTier, description_from: int | None, *,
                   notes_cut: bool) -> list[NextAction]:
    """The calls that read what an excerpt left out."""
    calls = []
    if description_from is not None:
        calls.append(NextAction(operation=OPPORTUNITIES_GET.id, arguments={
            "opportunity_id": opportunity_id, "view": "detail", "tier": tier, "description_from": description_from,
        }))
    if notes_cut:
        calls.append(NextAction(operation=PURSUITS_GET.id, arguments={"opportunity_id": opportunity_id}))
    return calls


def _cut(text: str, room: int) -> str:
    """The longest prefix of `text` that ends at a word and whose JSON string
    takes at most `room` more bytes than an empty one; JSON escapes counted."""
    if room <= 0:
        return ""
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _size(text[:middle]) - 2 <= room:
            low = middle
        else:
            high = middle - 1
    if low == len(text):
        return text
    space = text.rfind(" ", 0, low + 1)
    word = text[:space].rstrip() if space > 0 else ""
    # A prefix that is all whitespace has no word to end at; keep what fits,
    # so a read from inside a long gap still advances.
    return word or text[:low]


async def history(
    session: AsyncSession, opportunity_id: int, *, pursuits: bool = True, now: datetime | None = None
) -> ListingHistory:
    """The posting's listing history. `pursuits` false: see `visible_job`."""
    await visible_job(session, opportunity_id, chosen_counts=pursuits)
    found = await listing_history(session, opportunity_id, now or datetime.now(UTC))
    if found is None:
        raise _not_found(opportunity_id)
    return ListingHistory.model_validate(found)

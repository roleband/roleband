"""How one posting relates to others: similar roles, its decks, and whether it stands.

`opportunities.similar` is Job detail's Similar roles: the open postings whose
text is nearest this one's, at the same company, at others, or both, best
first, from the neighbour table the dashboard reads (`semantic.similarity`).

`opportunities.duplicates` is the posting's decks, as Job detail stacks them
(`lineage.decks`, `lineage.place_sets`): its reposts (the role listed again
over time), its twins (the role listed twice at once) and its place set (the
role listed once per place). A deck stacks postings; it never merges them.
Each deck names its members by id with the link or rule that placed each one,
and `rows` holds every posting the decks name, once, as search shows it, so
two postings of one role keep their own dates, places and pay.

`opportunities.reality` is the standing-posting verdict Job detail shows
(`analytics.posting_reality`): `possible` when at least two of its three
structural criteria hold, `none` otherwise, and no verdict for a closed
posting. Each criterion comes with its threshold and what was observed, so a
reader can see why it holds or does not.

A posting at a company the person hid is not found here, as in
`opportunities.get`, unless the person saved or pursues it.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field
from pydantic.config import JsonDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.operations.opportunities import (
    DETAIL_BUDGET_BYTES,
    read_rest,
    visible_job,
    visible_jobs,
)
from tracker.agents.operations.search import (
    PAGE_BUDGET_BYTES,
    PageRow,
    only_columns,
    rows_within_budget,
    shared_columns,
    summary_rows,
)
from tracker.analytics.posting_reality import (
    CRITERIA,
    LONG_OPEN,
    REDATED,
    RELISTED_LISTINGS,
    classify,
    listings,
    standing_since,
)
from tracker.company_store import off_board_company_slugs
from tracker.db.models import Job, JobLineage, JobLineageLink, JobTwinLink
from tracker.db.queries.jobs import exclude_hidden, list_rows, row_context, standing_facts
from tracker.lineage.decks import lineage_stack, twin_deck
from tracker.lineage.place_sets import place_set_of
from tracker.lineage.reasons import duplicate_reasons, twin_reasons
from tracker.semantic.similarity import similar_for_job

_CODE: JsonDict = {"x-text": "code"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")
_ROWS = "One array per posting, its values in the order `columns` names."

SimilarScope = Literal["within", "cross", "all"]


# --- shapes ------------------------------------------------------------------ #


class SimilarInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity's id, as search returns it.")
    scope: SimilarScope = Field(
        default="cross", description="within (the same company), cross (other companies) or all.",
    )
    limit: int = Field(default=8, ge=1, le=50, description="Most similar roles to name.")
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the answer.")


class SimilarRoles(Shape):
    opportunity_id: int
    scope: SimilarScope = Field(json_schema_extra=_CODE)
    #: Every similar open role found, best first, as `[id, score]`; the score
    #: is the texts' cosine similarity, from 0 to 1.
    similar: list[tuple[int, float]]
    columns: list[str] = Field(json_schema_extra=_CODE)
    rows: list[PageRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)
    #: The call that reads the similar roles this answer had no room for.
    continue_with: list[NextAction]


class RelationInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity's id, as search returns it.")
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the answer.")


class Reason(Shape):
    """One reason a link gives, as a code and its numbers (`lineage.reasons`)."""

    code: str = Field(json_schema_extra=_CODE)
    params: dict[str, int | None]


class DeckLink(Shape):
    """Why a member is in its deck: the link that placed it and who decided."""

    #: `repost` or `duplicate` in a repost deck; `twin` in a twin deck.
    relation: str = Field(json_schema_extra=_CODE)
    method: str = Field(json_schema_extra=_CODE)
    #: `auto` when the detector was sure; `suspected` when it asked a person.
    confidence: str = Field(json_schema_extra=_CODE)
    #: `pending`, `confirmed` or `rejected`: a person's verdict, or none yet.
    status: str = Field(json_schema_extra=_CODE)
    #: The verdict the person gave in review, when they gave one.
    decision: str | None = Field(json_schema_extra=_CODE)
    score: float | None
    #: Days between the earlier posting closing and this one appearing; repost links only.
    gap_days: int | None
    reasons: list[Reason]


class RepostMember(Shape):
    opportunity_id: int
    seq: int | None
    #: `original`, `repost` or `duplicate`.
    role: str | None = Field(json_schema_extra=_CODE)
    #: Null for the first posting of the role.
    link: DeckLink | None
    #: The link ties this posting to the one before it in the deck.
    effective: bool


class RepostDeck(Shape):
    """The role listed again over time: every posting of it, oldest first."""

    lineage_id: int
    size: int
    open_members: int | None
    first_seen: datetime | None
    last_seen: datetime | None
    members: list[RepostMember]


class TwinDeckMember(Shape):
    opportunity_id: int
    #: Linked to the asked posting itself, not through another twin.
    direct: bool
    #: The link of a direct twin; null for the asked posting and an indirect twin.
    link: DeckLink | None


class TwinDeck(Shape):
    """The role listed more than once at the same time: the asked posting first."""

    size: int
    direct_count: int
    members: list[TwinDeckMember]


class PlaceMember(Shape):
    opportunity_id: int
    is_this: bool
    #: `place`: the role at another place; `relisted`: listed again at a place it already holds.
    relation: str = Field(json_schema_extra=_CODE)
    #: At the asked posting's own place.
    same_place: bool


class PlaceSetDeck(Shape):
    """The role listed once per place, by rule: same title and text, each at a different place."""

    size: int
    places: list[str] = Field(json_schema_extra=_CONTENT)
    #: The employer's own name for the role across places, when it gives one.
    employer_label: str | None = Field(json_schema_extra=_CONTENT)
    rule_version: str | None = Field(json_schema_extra=_CODE)
    members: list[PlaceMember]


class PostingDecks(Shape):
    opportunity_id: int
    #: Null for a posting listed once.
    reposts: RepostDeck | None
    #: Null for a posting with no twin.
    twins: TwinDeck | None
    #: Null for a posting in no place set.
    place_set: PlaceSetDeck | None
    #: A person split this posting out of its place set.
    place_set_split: bool
    columns: list[str] = Field(json_schema_extra=_CODE)
    #: Every posting the decks name, once, the asked one first.
    rows: list[PageRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)
    #: The call that reads the postings this answer had no room for.
    continue_with: list[NextAction]


class Criterion(Shape):
    key: Literal["long_open", "relisted", "redated"] = Field(json_schema_extra=_CODE)
    met: bool
    #: `days` for long_open and redated, `listings` for relisted.
    unit: Literal["days", "listings"] = Field(json_schema_extra=_CODE)
    #: The criterion holds at this value or above.
    threshold: int
    #: What was observed; null for redated when the employer gives no date or
    #: the date moved when the posting came back after closing.
    observed: int | None


class PostingVerdict(Shape):
    opportunity_id: int
    status: str = Field(json_schema_extra=_CODE)
    #: `possible` when at least two criteria hold, else `none`; null for a
    #: closed posting, which carries no verdict.
    verdict: Literal["possible", "none"] | None = Field(json_schema_extra=_CODE)
    criteria_total: int
    #: In the order a reader should meet them; empty without a verdict.
    criteria: list[Criterion]
    #: What long_open counts from: the role's first listing over its reposts,
    #: or the posting's own.
    standing_since: datetime | None
    counted_from: Literal["role", "posting"] | None = Field(json_schema_extra=_CODE)
    #: What relisted counts: postings of the role, returns of this posting
    #: after closing, and other postings of the role at this posting's place.
    role_postings: int | None
    returns: int | None
    relisted_here: int | None


# --- descriptors ------------------------------------------------------------- #


OPPORTUNITIES_SIMILAR = OperationDescriptor(
    id="opportunities.similar",
    summary="Open roles whose text is nearest one posting's, best first, as search's summary rows.",
    input=SimilarInput,
    result=SimilarRoles,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting", "market_statistic", "private_pursuit"),
    examples=({"opportunity_id": 4821, "scope": "all", "limit": 10},),
)

OPPORTUNITIES_DUPLICATES = OperationDescriptor(
    id="opportunities.duplicates",
    summary="A posting's decks: its reposts, twins and place set, each posting kept apart with why it is there.",
    input=RelationInput,
    result=PostingDecks,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting", "market_statistic", "private_pursuit"),
    examples=({"opportunity_id": 4821},),
)

OPPORTUNITIES_REALITY = OperationDescriptor(
    id="opportunities.reality",
    summary="Whether a posting may be a standing one: the verdict and each criterion with its threshold.",
    input=RelationInput,
    result=PostingVerdict,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    # Whether a saved or pursued posting at a hidden company is found says
    # the person chose it, so the pursuits decide it while they are shared.
    data_classes=("public_posting", "private_pursuit"),
    examples=({"opportunity_id": 4821},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (OPPORTUNITIES_SIMILAR, OPPORTUNITIES_DUPLICATES, OPPORTUNITIES_REALITY)


# --- similar ----------------------------------------------------------------- #


async def similar(
    session: AsyncSession, params: SimilarInput, *, withheld: Collection[DataClass] = (), now: datetime | None = None,
) -> tuple[SimilarRoles, Fitted]:
    """The similar roles, and how their rows fit the tier's budget, without
    the columns of the `withheld` categories."""
    pursuits = "private_pursuit" not in withheld
    await visible_job(session, params.opportunity_id, chosen_counts=pursuits)
    hidden = await off_board_company_slugs(session)
    # Off-Board companies are excluded before the limit, by the neighbour
    # contract the dashboard's Similar roles reads too.
    pairs = await similar_for_job(session, params.opportunity_id, scope=params.scope, limit=params.limit,
                                  hidden=list(hidden))
    found = {
        job.id: job
        for job in (
            await session.scalars(list_rows(exclude_hidden(select(Job).where(Job.id.in_([i for i, _ in pairs])), hidden)))
        ).all()
    } if pairs else {}
    scored = [(job_id, round(score, 4)) for job_id, score in pairs if job_id in found]
    jobs = [found[job_id] for job_id, _ in scored]
    shell = SimilarRoles(opportunity_id=params.opportunity_id, scope=params.scope, similar=scored,
                         columns=shared_columns(withheld), rows=[], continue_with=[])
    fitted = await _fit_rows(session, shell, jobs, PAGE_BUDGET_BYTES[params.tier], params.tier,
                             pursuits=pursuits, now=now)
    return shell.model_copy(update={"rows": fitted.rows, "continue_with": read_rest(fitted.rest, params.tier)}), fitted


# --- decks ------------------------------------------------------------------- #


def _reasons(said: list[Any]) -> list[Reason]:
    return [Reason(code=item["code"], params=item["params"]) for item in said]


def _repost_link(link: JobLineageLink) -> DeckLink:
    evidence = link.evidence or {}
    return DeckLink(
        relation=link.relation, method=link.method, confidence=link.confidence, status=link.status,
        decision=evidence.get("review_outcome"), score=link.score, gap_days=link.gap_days,
        reasons=_reasons(duplicate_reasons(link.method, link.relation, evidence)),
    )


def _twin_link(link: JobTwinLink) -> DeckLink:
    evidence = link.evidence or {}
    return DeckLink(
        relation="twin", method=link.method, confidence=link.confidence, status=link.status,
        decision=evidence.get("review_outcome"), score=link.score, gap_days=None,
        reasons=_reasons(twin_reasons(evidence)),
    )


async def decks(
    session: AsyncSession, params: RelationInput, *, withheld: Collection[DataClass] = (), now: datetime | None = None,
) -> tuple[PostingDecks, Fitted]:
    """The posting's decks, and how their postings' rows fit the tier's budget.

    A deck names only postings an agent may read by id: a saved or pursued
    posting at a company the person hid keeps its deck, without the siblings
    there that are neither, and each count is of the members named. A place
    set holding such a sibling is left out whole, since its places name the
    sibling's city. Without the person's pursuits a save or a pursuit grants
    no access, and the rows hold no `pursuit` column."""
    pursuits = "private_pursuit" not in withheld
    job = await visible_job(session, params.opportunity_id, chosen_counts=pursuits)
    lineage = await session.get(JobLineage, job.lineage_id) if job.lineage_id is not None else None
    stack = await lineage_stack(session, lineage.id) if lineage is not None else []
    deck = await twin_deck(session, job.id)
    state = await place_set_of(session, job.id)
    found = state["set"]

    ids = list(dict.fromkeys([
        job.id, *(member.job.id for member in stack), *deck.member_ids, *(found["member_ids"] if found else ()),
    ]))
    readable = await visible_jobs(session, ids, summary=True, chosen_counts=pursuits)

    reposts = None
    if lineage is not None:
        shown = [member for member in stack if member.job.id in readable]
        whole = len(shown) == len(stack)
        reposts = RepostDeck(
            lineage_id=lineage.id,
            size=lineage.size if whole else len(shown),
            open_members=lineage.open_members if whole else sum(m.job.status == "open" for m in shown),
            first_seen=lineage.first_seen if whole else min((m.job.first_seen for m in shown), default=None),
            last_seen=lineage.last_seen if whole else max((m.job.last_seen for m in shown), default=None),
            members=[
                RepostMember(
                    opportunity_id=member.job.id, seq=member.job.lineage_seq, role=member.job.lineage_role,
                    link=_repost_link(member.link) if member.link is not None else None,
                    effective=member.effective,
                )
                for member in shown
            ],
        )

    twins = None
    twin_ids = [member_id for member_id in deck.member_ids if member_id in readable]
    if len(twin_ids) > 1:
        twins = TwinDeck(
            size=len(twin_ids), direct_count=sum(member_id in deck.direct for member_id in twin_ids),
            members=[
                TwinDeckMember(
                    opportunity_id=member_id, direct=member_id in deck.direct,
                    link=_twin_link(deck.links[member_id]) if member_id in deck.links else None,
                )
                for member_id in twin_ids
            ],
        )

    place_set = None
    if found is not None and all(member_id in readable for member_id in found["member_ids"]):
        here = found["place_keys"].get(job.id)
        place_set = PlaceSetDeck(
            size=found["size"], places=found["places"], employer_label=found["employer_label"],
            rule_version=found["rule_version"],
            members=[
                PlaceMember(
                    opportunity_id=member_id, is_this=member_id == job.id,
                    relation=found["relations"].get(member_id, "place"),
                    same_place=member_id != job.id and here is not None and found["place_keys"].get(member_id) == here,
                )
                for member_id in found["member_ids"]
            ],
        )

    named = [job.id]
    named += [m.opportunity_id for m in reposts.members] if reposts else []
    named += [m.opportunity_id for m in twins.members] if twins else []
    named += [m.opportunity_id for m in place_set.members] if place_set else []
    jobs = [readable[job_id] for job_id in dict.fromkeys(named)]
    shell = PostingDecks(
        opportunity_id=job.id, reposts=reposts, twins=twins, place_set=place_set,
        place_set_split=bool(state["rejected"]), columns=shared_columns(withheld), rows=[], continue_with=[],
    )
    fitted = await _fit_rows(session, shell, jobs, DETAIL_BUDGET_BYTES[params.tier], params.tier,
                             pursuits=pursuits, now=now)
    return shell.model_copy(update={"rows": fitted.rows, "continue_with": read_rest(fitted.rest, params.tier)}), fitted


# --- reality ----------------------------------------------------------------- #


async def reality(
    session: AsyncSession, opportunity_id: int, *, pursuits: bool = True, now: datetime | None = None,
) -> PostingVerdict:
    """The standing verdict. Without the person's `pursuits`, a save or a
    pursuit of a posting at a hidden company grants no access to it."""
    now = now or datetime.now(UTC)
    job = await visible_job(session, opportunity_id, chosen_counts=pursuits)
    context = await row_context(session, [job])
    facts = standing_facts(
        job, lineage_meta=context["lineage_meta"], role_starts=context["role_starts"] or {},
        reopened_ids=context["reopened_ids"] or set(), place_counts=context["place_counts"],
    )
    verdict = classify(facts, now) if facts is not None else None
    if facts is None or verdict is None:
        return PostingVerdict(
            opportunity_id=job.id, status=job.status, verdict=None, criteria_total=len(CRITERIA), criteria=[],
            standing_since=None, counted_from=None, role_postings=None, returns=None, relisted_here=None,
        )
    since = standing_since(facts)
    moved = (
        (facts.posted_at - facts.first_seen).days
        if facts.posted_at is not None and not facts.reopened else None
    )
    met = verdict["met"]
    measured = {
        "long_open": Criterion(key="long_open", met="long_open" in met, unit="days",
                               threshold=LONG_OPEN.days, observed=(now - since).days),
        "relisted": Criterion(key="relisted", met="relisted" in met, unit="listings",
                              threshold=RELISTED_LISTINGS, observed=listings(facts)),
        "redated": Criterion(key="redated", met="redated" in met, unit="days",
                             threshold=REDATED.days, observed=moved),
    }
    return PostingVerdict(
        opportunity_id=job.id,
        status=job.status,
        verdict=verdict["level"],
        criteria_total=verdict["criteria_total"],
        criteria=[measured[key] for key in CRITERIA],
        standing_since=since,
        counted_from="role" if facts.role_since is not None else "posting",
        role_postings=facts.lineage_size or 1,
        returns=facts.repost_count,
        relisted_here=facts.listed_here,
    )


# --- rows within the budget -------------------------------------------------- #


@dataclass(frozen=True)
class Fitted:
    rows: list[PageRow]
    #: The postings left for the `continue_with` read.
    rest: list[Job]
    #: The first row was longer than the budget and its longest text was cut.
    row_cut: bool


async def _fit_rows(
    session: AsyncSession, shell: SimilarRoles | PostingDecks, jobs: list[Job], budget: int, tier: ToolTier,
    *, pursuits: bool, now: datetime | None,
) -> Fitted:
    """The leading postings' rows that fit `budget` beside `shell`, and the
    postings left for the `continue_with` read. The answer is measured with
    the call that would read every posting but the first, the largest
    `continue_with` it can carry; a shell with no room for one row is refused."""
    if not jobs:
        return Fitted([], [], row_cut=False)
    rows = only_columns(await summary_rows(session, jobs, now=now or datetime.now(UTC), pursuits=pursuits), shell.columns)
    widest = shell.model_copy(update={"continue_with": read_rest(jobs[1:], tier)})
    room = budget - _size(widest.model_dump(mode="json"))
    kept, cut = rows_within_budget(rows, room)
    if room <= 0 or _size(kept[0]) + 1 > room:
        raise OperationError(
            "invalid_input",
            "This posting's relations do not fit the tier's budget; ask with a larger tier.",
            details={"field": "tier", "reason": "over_budget", "budget_bytes": budget},
        )
    return Fitted(kept, jobs[len(kept):], row_cut=cut)


def _size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode())

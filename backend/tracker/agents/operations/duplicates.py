"""Duplicate postings for an assistant: the pairs worth deciding, and its verdicts.

An assistant tidies the person's duplicates so the person does not have to:
it reads `duplicates.queue`, settles the clear pairs with `duplicates.decide`
and leaves the unclear ones for the person with a note. The person sees every
verdict in the Review queue, marked as the assistant's with its reason, and
takes any back there with one click.

`duplicates.queue` lists the pending pairs the person can act on (one posting
on the Board, `pair_on_board`), in the order that changes most what the
person sees: a pair touching a role they saved or pursue first; then
suspected pairs, which the Board still shows twice; then pairs the detector
stacked on its own, weakest first, where its mistakes are likeliest. Within a
step, the stronger suspected and the weaker automatic pair come first. A pair
an assistant already left for the person is not listed again. Each pair
carries what differs between its two postings, so one page is enough to judge
it: the fields that changed, and the passages of the text found in one posting
and not the other.

`duplicates.decide` records up to 50 verdicts in one transaction. Each names a
pair, one of four plain verdicts and a one-line reason:

| Verdict | On a repost pair | On a twin pair |
|---|---|---|
| `same_opening` | confirmed | the pair becomes a duplicate |
| `two_openings` | the pair becomes a twin | confirmed |
| `different_roles` | rejected | rejected |
| `unsure` | left pending with the note | left pending with the note |

A pair the person decided is never changed: that item is refused as
`decided_by_person` and the others go ahead. The verdicts, the rebuilt
stacks, the receipt and the Activity entry commit together.

A pair is named by one token, `lineage-<id>` or `twin-<id>`, because the two
kinds number their links separately.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic.config import JsonDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.activity import Changed, FieldChange, Said
from tracker.agents.operations import cursor as page_cursor
from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.operations.opportunities import visible_jobs
from tracker.agents.operations.search import (
    PAGE_BUDGET_BYTES,
    PageRow,
    only_columns,
    shared_columns,
    summary_rows,
)
from tracker.company_store import off_board_company_slugs
from tracker.db.models import Favorite, Job, JobLineageLink, JobTwinLink, Pursuit
from tracker.db.queries.jobs import pair_on_board
from tracker.lineage.content_diff import compare_descriptions
from tracker.lineage.detect import rebuild_lineage_projection
from tracker.lineage.diff import build_member_diff
from tracker.lineage.reasons import duplicate_reasons, twin_reasons
from tracker.lineage.review import (
    DecidedByPerson,
    LinkNotFound,
    decide_lineage_link,
    decide_twin_link,
    leave_for_person,
)

_CODE: JsonDict = {"x-text": "code"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")
_ROWS = "One array per posting, its values in the order `columns` names."

#: One pair, as the queue names it and a verdict takes it back.
PAIR = r"^(lineage|twin)-([1-9][0-9]{0,17})$"
_PAIR = re.compile(PAIR)
#: The most verdicts one call records: one transaction and one rebuild of the stacks.
MAX_VERDICTS = 50
#: A passage of text shown in a pair's differences is cut to this many characters.
_PASSAGE_CHARS = 280
#: Passages shown from each side of a pair; `only_in_*_count` says how many there are.
_PASSAGES = 4

Verdict = Literal["same_opening", "two_openings", "different_roles", "unsure"]
#: The app's own verdict for each plain one, by the kind of pair.
_LINEAGE_VERDICT: dict[str, str] = {"same_opening": "confirmed", "two_openings": "twin", "different_roles": "rejected"}
_TWIN_VERDICT: dict[str, str] = {"same_opening": "duplicate", "two_openings": "confirmed", "different_roles": "rejected"}

#: Why a pair is where it is in the queue, first to last.
Step = Literal["yours", "shown_twice", "stacked"]
_STEP_ORDER: dict[str, int] = {"yours": 0, "shown_twice": 1, "stacked": 2}


# --- shapes ------------------------------------------------------------------ #


class DuplicateQueueInput(Shape):
    mine: bool = Field(
        default=False, description="Only pairs with a posting the person saved or pursues.",
    )
    limit: int = Field(default=10, ge=1, le=50, description="Most pairs on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page, read with the same filters.",
    )
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page.")


class PairReason(Shape):
    """One reason the detector gives, as a code and its numbers (`lineage.reasons`)."""

    code: str = Field(json_schema_extra=_CODE)
    params: dict[str, int | None]


class PairPassage(Shape):
    section: str = Field(json_schema_extra=_CONTENT)
    text: str = Field(json_schema_extra=_CONTENT)


class PairTextDifference(Shape):
    """The postings' texts side by side: whether they could be compared, how
    alike they are, and the passages each has that the other does not."""

    comparable: bool
    #: Shared words over all words, from 0 to 1.
    alike: float
    only_in_older_count: int
    only_in_newer_count: int
    only_in_older: list[PairPassage]
    only_in_newer: list[PairPassage]


class DuplicatePair(Shape):
    #: The token a verdict names this pair by.
    pair: str = Field(json_schema_extra=_CODE)
    #: What the detector proposes: `same_opening` (a repost pair) or
    #: `two_openings` (a twin pair).
    proposed: Literal["same_opening", "two_openings"] = Field(json_schema_extra=_CODE)
    #: `yours` (it touches a role the person saved or pursues), `shown_twice`
    #: (suspected: the Board lists both postings) or `stacked` (the detector
    #: stacked them on its own).
    step: Step = Field(json_schema_extra=_CODE)
    #: The posting seen first, then the other; both are in `rows`.
    older: int
    newer: int
    #: Days between the older posting closing and the newer appearing; repost pairs only.
    gap_days: int | None
    #: The detector's similarity of the two texts, from 0 to 1.
    score: float | None
    reasons: list[PairReason]
    #: The fields that differ, older to newer (`lineage.diff`).
    fields: dict[str, Any]
    text: PairTextDifference


class DuplicateQueue(Shape):
    #: Pending pairs the queue holds, on every page together.
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    pairs: list[DuplicatePair]
    columns: list[str] = Field(json_schema_extra=_CODE)
    rows: list[PageRow] = Field(json_schema_extra=_CONTENT, description=_ROWS)
    continue_with: list[NextAction]


class DuplicateVerdictInput(Shape):
    pair: str = Field(pattern=PAIR, description="The pair, as duplicates.queue names it: lineage-<id> or twin-<id>.")
    verdict: Verdict = Field(
        description=(
            "same_opening (one opening listed again), two_openings (the same role, separate openings), "
            "different_roles, or unsure (leave it for the person)."
        ),
    )
    reason: str = Field(
        min_length=3, max_length=300,
        description="One line the person reads beside the verdict: what in the postings decided it.",
    )

    @field_validator("reason")
    @classmethod
    def _one_line(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("a reason says what decided the verdict")
        return value


class DuplicateVerdictsInput(Shape):
    verdicts: list[DuplicateVerdictInput] = Field(
        min_length=1, max_length=MAX_VERDICTS, description=f"1 to {MAX_VERDICTS} verdicts, each on its own pair.",
    )

    @field_validator("verdicts")
    @classmethod
    def _each_pair_once(cls, value: list[DuplicateVerdictInput]) -> list[DuplicateVerdictInput]:
        pairs = [item.pair for item in value]
        if len(set(pairs)) != len(pairs):
            raise ValueError("each pair takes one verdict per call")
        return value


Outcome = Literal["decided", "left_for_person", "refused"]


class DuplicateVerdictItem(Shape):
    pair: str = Field(json_schema_extra=_CODE)
    verdict: Verdict = Field(json_schema_extra=_CODE)
    outcome: Outcome = Field(json_schema_extra=_CODE)
    #: Why an item was refused: `decided_by_person` or `not_found`.
    refusal: str | None = Field(default=None, json_schema_extra=_CODE)
    #: The pair's status before and after, in the app's words.
    before: str | None = Field(default=None, json_schema_extra=_CODE)
    after: str | None = Field(default=None, json_schema_extra=_CODE)


class DuplicateVerdictsResult(Shape):
    decided: int = Field(ge=0)
    left_for_person: int = Field(ge=0)
    refused: int = Field(ge=0)
    results: list[DuplicateVerdictItem]


# --- descriptors ------------------------------------------------------------- #

DUPLICATES_QUEUE = OperationDescriptor(
    id="duplicates.queue",
    summary=(
        "List the duplicate pairs worth deciding, the person's own roles first, each with what differs "
        "between its two postings."
    ),
    input=DuplicateQueueInput,
    result=DuplicateQueue,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting", "market_statistic", "private_pursuit"),
    examples=({"limit": 10}, {"mine": True}),
)

DUPLICATES_DECIDE = OperationDescriptor(
    id="duplicates.decide",
    summary=(
        "Record verdicts on duplicate pairs, each with a one-line reason; unsure leaves a pair for the "
        "person. A pair the person decided is never changed."
    ),
    input=DuplicateVerdictsInput,
    result=DuplicateVerdictsResult,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting",),
    examples=(
        {"verdicts": [
            {"pair": "lineage-4", "verdict": "same_opening", "reason": "Same site and pay; the first closed a day before."},
            {"pair": "twin-9", "verdict": "unsure", "reason": "Same title, but the team names differ."},
        ]},
    ),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (DUPLICATES_QUEUE, DUPLICATES_DECIDE)


# --- the queue --------------------------------------------------------------- #


@dataclass(frozen=True)
class _Pending:
    kind: Literal["lineage", "twin"]
    link: JobLineageLink | JobTwinLink
    older: int
    newer: int
    step: Step

    @property
    def token(self) -> str:
        return f"{self.kind}-{self.link.id}"


_KIND_ORDER: dict[str, int] = {"lineage": 0, "twin": 1}
_KIND_OF_CODE = {code: kind for kind, code in _KIND_ORDER.items()}


def _rank(item: _Pending) -> tuple[int, float, int, int]:
    score = item.link.score or 0.0
    # A suspected pair: the strongest proposal first. An automatic match: the
    # weakest first, since a wrong automatic stack is the one that hides a role.
    # The kind and id make the order total, so a page can resume after a pair.
    lean = -score if item.link.confidence == "suspected" else score
    return (_STEP_ORDER[item.step], lean, _KIND_ORDER[item.kind], item.link.id)


async def _yours(session: AsyncSession, ids: Collection[int]) -> set[int]:
    if not ids:
        return set()
    saved = set((await session.scalars(select(Favorite.job_id).where(Favorite.job_id.in_(ids)))).all())
    pursued = set((await session.scalars(select(Pursuit.job_id).where(Pursuit.job_id.in_(ids)))).all())
    return saved | pursued


async def _pending(session: AsyncSession, *, pursuits: bool) -> list[_Pending]:
    """Every pending pair the person can act on, not yet left for them, ranked."""
    hidden = await off_board_company_slugs(session)
    lineage = (await session.scalars(
        select(JobLineageLink).where(
            JobLineageLink.status == "pending",
            JobLineageLink.decision_note.is_(None),
            pair_on_board(JobLineageLink.job_id, JobLineageLink.prior_job_id, hidden),
        )
    )).all()
    twins = (await session.scalars(
        select(JobTwinLink).where(
            JobTwinLink.status == "pending",
            JobTwinLink.decision_note.is_(None),
            pair_on_board(JobTwinLink.job_a_id, JobTwinLink.job_b_id, hidden),
        )
    )).all()
    pairs: list[tuple[str, JobLineageLink | JobTwinLink, int, int]] = [
        ("lineage", link, link.prior_job_id, link.job_id) for link in lineage
    ]
    pairs += [("twin", twin, twin.job_a_id, twin.job_b_id) for twin in twins]
    return sorted(await _ranked(session, pairs, pursuits=pursuits), key=_rank)


async def _ranked(
    session: AsyncSession,
    pairs: list[tuple[str, JobLineageLink | JobTwinLink, int, int]],
    *,
    pursuits: bool,
) -> list[_Pending]:
    ids = {older for _, _, older, _ in pairs} | {newer for _, _, _, newer in pairs}
    yours = await _yours(session, ids) if pursuits else set()
    return [
        _Pending(
            kind,  # type: ignore[arg-type]
            link,
            older,
            newer,
            "yours" if older in yours or newer in yours else (
                "shown_twice" if link.confidence == "suspected" else "stacked"
            ),
        )
        for kind, link, older, newer in pairs
    ]


async def _resume_after(session: AsyncSession, kind_code: int, link_id: int, *, pursuits: bool) -> tuple[int, float, int, int]:
    """The rank of the pair a page ended on, read again now. The pair itself
    may have been decided since, which takes it out of the queue but not out
    of the order, so the next page starts after it and skips nothing."""
    kind = _KIND_OF_CODE.get(kind_code)
    link: JobLineageLink | JobTwinLink | None = None
    pair: tuple[str, JobLineageLink | JobTwinLink, int, int] | None = None
    if kind == "lineage":
        link = await session.get(JobLineageLink, link_id)
        pair = ("lineage", link, link.prior_job_id, link.job_id) if link is not None else None
    elif kind == "twin":
        link = await session.get(JobTwinLink, link_id)
        pair = ("twin", link, link.job_a_id, link.job_b_id) if link is not None else None
    if link is None or pair is None:
        raise OperationError(
            "invalid_input",
            "This cursor does not continue this list. Read the first page again without it, with the same filters.",
            details={"field": "cursor", "reason": "pair_gone"},
        )
    return _rank((await _ranked(session, [pair], pursuits=pursuits))[0])


def _passages(passages: Any) -> list[PairPassage]:
    return [
        PairPassage(section=p.section_title or p.section_key, text=_cut(p.text))
        for p in list(passages)[:_PASSAGES]
    ]


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _PASSAGE_CHARS else text[: _PASSAGE_CHARS - 1].rstrip() + "…"


def _text_difference(older: Job, newer: Job) -> PairTextDifference:
    diff = compare_descriptions(
        older.description_sections, older.description_text, newer.description_sections, newer.description_text,
    )
    return PairTextDifference(
        comparable=diff.comparable,
        alike=round(diff.token_similarity, 3),
        only_in_older_count=diff.left_only_count,
        only_in_newer_count=diff.right_only_count,
        only_in_older=_passages(diff.left_only),
        only_in_newer=_passages(diff.right_only),
    )


def _reasons(item: _Pending) -> list[PairReason]:
    evidence = item.link.evidence or {}
    said = (
        duplicate_reasons(item.link.method, item.link.relation, evidence)  # type: ignore[union-attr]
        if item.kind == "lineage" else twin_reasons(evidence)
    )
    return [PairReason(code=reason["code"], params=reason["params"]) for reason in said]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(inner) for key, inner in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(inner) for inner in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def queue(
    session: AsyncSession,
    params: DuplicateQueueInput,
    *,
    workspace_id: str,
    withheld: Collection[DataClass],
    now: datetime | None = None,
) -> tuple[DuplicateQueue, str | None, bool]:
    """One page of the queue, the cursor of the next, and whether the page
    stopped early to stay in the tier's budget. Without the person's pursuits shared, no pair is marked
    theirs and `mine` is refused."""
    pursuits = "private_pursuit" not in withheld
    if params.mine and not pursuits:
        raise OperationError(
            "category_disabled",
            "Only pairs with the person's roles needs their saved roles, which they do not share.",
            details={"category": "private_pursuit", "setting": "agent_access.categories.private_pursuit"},
        )
    request = page_cursor.fingerprint(
        DUPLICATES_QUEUE.id, workspace_id, {"mine": params.mine, "pursuits": pursuits},
    )
    ranked = await _pending(session, pursuits=pursuits)
    if params.mine:
        ranked = [item for item in ranked if item.step == "yours"]
    total = len(ranked)
    if params.cursor:
        # The cursor names the last pair a page held (its id, and its kind as
        # the count it carries), not a position: a verdict between two pages
        # takes pairs out of the queue, and a position would then skip as many.
        link_id, kind_code = page_cursor.decode(params.cursor, request=request)
        after = await _resume_after(session, kind_code, link_id, pursuits=pursuits)
        ranked = [item for item in ranked if _rank(item) > after]
    window = ranked[: params.limit]
    ids = [posting for item in window for posting in (item.older, item.newer)]
    readable = await visible_jobs(session, ids, chosen_counts=pursuits)
    columns = shared_columns(withheld)
    budget = PAGE_BUDGET_BYTES[params.tier]
    pairs: list[DuplicatePair] = []
    shown: list[Job] = []
    used = 0
    taken = 0
    for item in window:
        older, newer = readable.get(item.older), readable.get(item.newer)
        taken += 1
        if older is None or newer is None:
            continue
        pair = DuplicatePair(
            pair=item.token,
            proposed="same_opening" if item.kind == "lineage" else "two_openings",
            step=item.step,
            older=older.id,
            newer=newer.id,
            gap_days=item.link.gap_days if item.kind == "lineage" else None,  # type: ignore[union-attr]
            score=item.link.score,
            reasons=_reasons(item),
            fields=_jsonable(build_member_diff(older, newer)),
            text=_text_difference(older, newer),
        )
        size = len(pair.model_dump_json()) + 400
        if pairs and used + size > budget:
            taken -= 1
            break
        used += size
        pairs.append(pair)
        shown += [job for job in (older, newer) if job not in shown]
    rows = only_columns(await summary_rows(session, shown, now=now or datetime.now(UTC), pursuits=pursuits), columns)
    more = taken < len(ranked)
    continue_with = []
    last = window[taken - 1] if taken else None
    next_cursor = (
        page_cursor.encode(request=request, offset=last.link.id, carried=_KIND_ORDER[last.kind])
        if more and last is not None else None
    )
    if next_cursor:
        arguments: dict[str, Any] = {"cursor": next_cursor, "tier": params.tier}
        if params.mine:
            arguments["mine"] = True
        continue_with.append(NextAction(operation=DUPLICATES_QUEUE.id, arguments=arguments))
    page = DuplicateQueue(
        total=total, count=len(pairs), pairs=pairs, columns=columns, rows=rows, continue_with=continue_with,
    )
    return page, next_cursor, more and taken < len(window)


# --- verdicts ---------------------------------------------------------------- #


def parse_pair(token: str) -> tuple[Literal["lineage", "twin"], int]:
    match = _PAIR.fullmatch(token)
    if match is None:
        raise ValueError(f"{token!r} is not a pair")
    return match.group(1), int(match.group(2))  # type: ignore[return-value]


async def _one(session: AsyncSession, item: DuplicateVerdictInput) -> DuplicateVerdictItem:
    kind, link_id = parse_pair(item.pair)
    link: JobLineageLink | JobTwinLink | None
    if kind == "lineage":
        link = await session.get(JobLineageLink, link_id)
        postings = (link.prior_job_id, link.job_id) if link is not None else ()
    else:
        link = await session.get(JobTwinLink, link_id)
        postings = (link.job_a_id, link.job_b_id) if link is not None else ()
    if link is None:
        return DuplicateVerdictItem(pair=item.pair, verdict=item.verdict, outcome="refused", refusal="not_found")
    if len(await visible_jobs(session, list(postings), summary=True)) != 2:
        return DuplicateVerdictItem(pair=item.pair, verdict=item.verdict, outcome="refused", refusal="not_found")
    before = link.status
    try:
        async with session.begin_nested():
            if item.verdict == "unsure":
                outcome = await leave_for_person(
                    session, "duplicate" if kind == "lineage" else "twin", link_id, item.reason,
                )
            elif kind == "lineage":
                outcome = await decide_lineage_link(
                    session, link_id, _LINEAGE_VERDICT[item.verdict], actor="agent", note=item.reason,
                )
            else:
                outcome = await decide_twin_link(
                    session, link_id, _TWIN_VERDICT[item.verdict], actor="agent", note=item.reason,
                )
    except DecidedByPerson:
        return DuplicateVerdictItem(pair=item.pair, verdict=item.verdict, outcome="refused", refusal="decided_by_person")
    except LinkNotFound:
        return DuplicateVerdictItem(pair=item.pair, verdict=item.verdict, outcome="refused", refusal="not_found")
    return DuplicateVerdictItem(
        pair=item.pair,
        verdict=item.verdict,
        outcome="left_for_person" if item.verdict == "unsure" else "decided",
        before=before,
        after=outcome.link.status,
    )


async def decide(session: AsyncSession, params: DuplicateVerdictsInput) -> DuplicateVerdictsResult:
    """Record each verdict in its own savepoint, so a refused pair leaves the
    others alone, then rebuild the stacks once. Commits nothing: the caller's
    write commits the verdicts, the stacks, the receipt and the Activity entry
    together."""
    results = [await _one(session, item) for item in params.verdicts]
    # An "unsure" on a pair the assistant had decided withdraws that verdict,
    # which changes the stacks as much as a decision does.
    if any(result.outcome != "refused" and result.before != result.after for result in results):
        await rebuild_lineage_projection(session)
    return DuplicateVerdictsResult(
        decided=sum(result.outcome == "decided" for result in results),
        left_for_person=sum(result.outcome == "left_for_person" for result in results),
        refused=sum(result.outcome == "refused" for result in results),
        results=results,
    )


@dataclass(frozen=True)
class DuplicateVerdictsActivity:
    """What a batch of verdicts lists on the Activity screen: how many pairs
    were decided and left for the person, and each pair's status before and after."""

    async def before(self, session: AsyncSession) -> None:
        return None

    def entry(self, before: object, result: BaseModel) -> Changed:
        if not isinstance(result, DuplicateVerdictsResult):
            raise TypeError(f"a verdict batch answers DuplicateVerdictsResult, not {type(result).__name__}")
        changes = tuple(
            FieldChange(item.pair, item.before, item.after if item.outcome == "decided" else "left_for_you")
            for item in result.results
            if item.outcome != "refused"
        )
        decided, left = result.decided, result.left_for_person
        parts = []
        if decided:
            parts.append(f"decided {decided} duplicate pair{'' if decided == 1 else 's'}")
        if left:
            parts.append(f"left {left} for you")
        english = (", ".join(parts) or "decided no duplicate pairs").capitalize()
        return Changed(Said("duplicates.decided", english, {"decided": decided, "left": left}), changes)

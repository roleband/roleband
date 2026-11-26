"""The brief: what the person wants from a move, as versioned parts.

A brief is one JSON document of named parts (`BriefBody`) plus a plain-text
summary. Setup writes a draft part by part; the person confirms it and it
becomes the active version, which the judge reads. A change of the active
brief is a new version, with who made it and why, and the version it replaces
is kept as `superseded`.

Every rule, pull, trade-off and proposed rule has an id the engine assigns
(`r1`, `p1`, `t1`, `x1`) and never reuses, so a verdict's reason can point at
the item it rests on and the pointer never comes to mean another item.

A hard rule is `checkable` when a field of the posting decides it (`check` is
one of six forms, applied by `tracker/picks/rules.py` before any model reads
the posting) and judged when only reading the posting can (`check` is null).

Nothing here commits: the caller owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import PickBrief, PickRun
from tracker.picks.lock import lock_picks
from tracker.schema import LEVEL_BAND_ORDER, WorkplaceType
from tracker.settings_store import get_top_picks_settings

Urgency = Literal["not_looking", "open", "active", "between_roles"]
MadeBy = Literal["person", "routine"]
#: The work modes a posting can state; `unknown` is the absence of one.
WORK_MODES = tuple(mode.value for mode in WorkplaceType if mode is not WorkplaceType.UNKNOWN)

#: The parts a routine run may change. Every other part is the person's: a
#: routine write that names one is refused.
ROUTINE_PARTS = frozenset({"pulls", "tradeoffs", "examples", "proposed_rules"})
#: The parts whose items carry engine-assigned ids, and each one's prefix.
ID_PREFIX = {"rules": "r", "pulls": "p", "tradeoffs": "t", "proposed_rules": "x"}
#: The parts a reason may rest on by name, beside an item's id.
NAMED_ITEMS = frozenset({"baseline", "targets", "direction", "urgency"})


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _line(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("this takes words")
    return value


#: One line of the person's or the assistant's words, its whitespace collapsed.
Line = Annotated[str, Field(min_length=1, max_length=300), AfterValidator(_line)]


class MinBase(_Part):
    """Rules out a posting whose stated yearly base tops out below `amount`."""

    form: Literal["min_base"]
    amount: int = Field(gt=0, le=100_000_000)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")


class MinTotal(_Part):
    """Rules out a posting whose stated yearly total pay tops out below `amount`."""

    form: Literal["min_total"]
    amount: int = Field(gt=0, le=100_000_000)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")


class Places(_Part):
    """Rules out a posting none of whose places is in `places`, unless it is
    remote and `remote_ok`."""

    form: Literal["places"]
    places: list[str] = Field(min_length=1, max_length=50, description="Location slugs, as vocabulary.list names them.")
    remote_ok: bool = False


class WorkModes(_Part):
    """Rules out a posting that states a work mode outside `modes`."""

    form: Literal["work_modes"]
    modes: list[Literal["onsite", "remote", "hybrid"]] = Field(min_length=1, max_length=3)


class MinLevel(_Part):
    """Rules out a posting whose level is below `level`."""

    form: Literal["min_level"]
    level: str = Field(description="A level slug: " + ", ".join(LEVEL_BAND_ORDER) + ".")

    @field_validator("level")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in LEVEL_BAND_ORDER:
            raise ValueError(f"unknown level: {value!r}")
        return value


class AvoidCompanies(_Part):
    """Rules out a posting of a company in `companies`."""

    form: Literal["avoid_companies"]
    companies: list[str] = Field(min_length=1, max_length=200, description="Company slugs, as companies.list names them.")


Check = Annotated[
    MinBase | MinTotal | Places | WorkModes | MinLevel | AvoidCompanies, Field(discriminator="form")
]


class Rule(_Part):
    """A hard rule: the person's words, and how it is checked."""

    id: str | None = Field(default=None, description="Leave out for a new rule; the engine assigns it.")
    text: Line
    check: Check | None = Field(
        default=None, description="A checkable form the engine applies, or null for a rule only reading can judge.",
    )


class Pull(_Part):
    id: str | None = None
    text: Line
    weight: int = Field(default=2, ge=1, le=3)
    source: Literal["cv", "stated", "reaction", "inferred"] = "stated"


class Tradeoff(_Part):
    id: str | None = None
    text: Line


class ProposedRule(_Part):
    """A hard rule the routine proposes from the person's reactions. Only the
    person makes it a rule."""

    id: str | None = None
    text: Line
    check: Check | None = None
    reason: Line


class Baseline(_Part):
    """What every posting is compared with: the person's current role, or an
    offer in hand."""

    title: str | None = Field(default=None, max_length=200)
    level: str | None = None
    employer: str | None = Field(default=None, max_length=200)
    pay: int | None = Field(default=None, gt=0, le=100_000_000, description="Yearly, or null when not shared.")
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    place: str | None = Field(default=None, max_length=200)
    work_mode: Literal["onsite", "remote", "hybrid"] | None = None
    keep: list[Line] = Field(default_factory=list, max_length=12)
    missing: list[Line] = Field(default_factory=list, max_length=12)

    @field_validator("level")
    @classmethod
    def _known(cls, value: str | None) -> str | None:
        if value is not None and value not in LEVEL_BAND_ORDER:
            raise ValueError(f"unknown level: {value!r}")
        return value


class Targets(_Part):
    companies: list[Line] = Field(default_factory=list, max_length=100)
    kinds: list[Line] = Field(default_factory=list, max_length=30)
    avoid: list[Line] = Field(default_factory=list, max_length=100)


class Direction(_Part):
    change: bool = False
    note: str | None = Field(default=None, max_length=300)


class Example(_Part):
    """A posting the person reacted to, with the reaction and their reason."""

    job: int = Field(gt=0)
    reaction: Literal["wanted", "unwanted", "close"]
    reason: Line


class BriefBody(_Part):
    """Every part of a brief. A part absent from a stored body was never saved."""

    urgency: Urgency | None = None
    baseline: Baseline | None = None
    rules: list[Rule] | None = Field(default=None, max_length=40)
    pulls: list[Pull] | None = Field(default=None, max_length=40)
    tradeoffs: list[Tradeoff] | None = Field(default=None, max_length=20)
    targets: Targets | None = None
    direction: Direction | None = None
    examples: list[Example] | None = Field(default=None, max_length=60)
    budget: int | None = Field(default=None, ge=1, le=31, description="Picks a month.")
    gaps: list[Line] | None = Field(default=None, max_length=20)
    calibrated: bool | None = None
    proposed_rules: list[ProposedRule] | None = Field(default=None, max_length=20)


PARTS: tuple[str, ...] = tuple(BriefBody.model_fields)
#: The budget a brief with none saved is judged against.
DEFAULT_BUDGET = 3


class BriefError(Exception):
    """A change of the brief the engine refuses. `code` is one of
    `needs_the_person`, `unknown_item`, `no_brief`, `no_draft` or `nothing_given`."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class RevisionMoved(Exception):
    """The brief moved past the revision the caller read."""

    def __init__(self, *, expected: int, current: int) -> None:
        super().__init__(f"expected revision {expected}, found {current}")
        self.expected = expected
        self.current = current


@dataclass(frozen=True)
class Patch:
    """One change: the parts given (each replaces that part whole), and how
    the change is recorded."""

    parts: dict[str, Any]
    reason: str
    if_revision: int
    summary: str | None = None
    #: `draft` writes the draft, starting one when there is none; `active`
    #: makes a new active version; None is the draft when there is one, else
    #: the active brief, else a first draft.
    target: Literal["draft", "active"] | None = None
    activate: bool = False
    routine: bool = False
    host: str | None = None


async def active(session: AsyncSession) -> PickBrief | None:
    return await session.scalar(select(PickBrief).where(PickBrief.status == "active"))


async def draft(session: AsyncSession) -> PickBrief | None:
    return await session.scalar(select(PickBrief).where(PickBrief.status == "draft"))


async def current(session: AsyncSession) -> PickBrief | None:
    """The brief setup is writing: the draft when there is one, else the active one."""
    return await draft(session) or await active(session)


async def version(session: AsyncSession, number: int) -> PickBrief | None:
    return await session.scalar(select(PickBrief).where(PickBrief.version == number))


async def history(session: AsyncSession) -> list[PickBrief]:
    """Every version, newest first."""
    return list((await session.scalars(select(PickBrief).order_by(PickBrief.version.desc()))).all())


def body_of(row: PickBrief | None) -> BriefBody:
    """The parts of a stored brief. The id counters stored beside them are not a part."""
    if row is None:
        return BriefBody()
    return BriefBody.model_validate({part: value for part, value in row.body.items() if part in PARTS})


def item_ids(body: BriefBody) -> set[str]:
    """Everything a reason may name: each rule, pull and trade-off, and the named parts."""
    ids = {item.id for part in ("rules", "pulls", "tradeoffs") for item in getattr(body, part) or [] if item.id}
    return ids | NAMED_ITEMS


def checkable_rules(body: BriefBody) -> list[Rule]:
    return [rule for rule in body.rules or [] if rule.check is not None]


def judged_rules(body: BriefBody) -> list[Rule]:
    return [rule for rule in body.rules or [] if rule.check is None]


def _with_ids(part: str, given: list[dict[str, Any]], stored: dict[str, Any]) -> list[dict[str, Any]]:
    """`given` with an id on every item: an id an item already has must be one
    this part held before, and a new item takes the next number, counted in
    `stored["ids"]` so a removed item's id is never given to another."""
    prefix = ID_PREFIX[part]
    known = {item["id"] for item in stored.get(part) or []}
    counters: dict[str, int] = stored.setdefault("ids", {})
    seen: set[str] = set()
    for item in given:
        named = item.get("id")
        if named is None:
            continue
        if named not in known or named in seen:
            raise BriefError(
                "unknown_item", f"{part} has no item {named!r} to keep. Leave the id out for a new item.",
                part=part, id=named,
            )
        seen.add(named)
    out = []
    for item in given:
        if item.get("id") is None:
            counters[prefix] = counters.get(prefix, 0) + 1
            item = {**item, "id": f"{prefix}{counters[prefix]}"}
        out.append(item)
    return out


def _applied(stored: dict[str, Any], parts: dict[str, Any]) -> dict[str, Any]:
    """`stored` with each given part replacing that part, validated whole."""
    body = {**stored, "ids": dict(stored.get("ids") or {})}
    for part, value in parts.items():
        if part not in PARTS:
            raise BriefError("unknown_item", f"A brief has no part {part!r}.", part=part)
        if part in ID_PREFIX and value is not None:
            value = _with_ids(part, [dict(item) for item in value], body)
        body[part] = value
    ids = body.pop("ids")
    checked = BriefBody.model_validate(body).model_dump(mode="json", exclude_none=True)
    return {**checked, "ids": ids}


async def _next_version(session: AsyncSession) -> int:
    """One past every version a brief or a run has had. Runs outlive a removed
    brief, and a number they judged under is never given to another brief: a
    verdict's version would then name a brief it was not made for."""
    held = int(await session.scalar(select(func.coalesce(func.max(PickBrief.version), 0))) or 0)
    judged = int(await session.scalar(select(func.coalesce(func.max(PickRun.brief_version), 0))) or 0)
    return max(held, judged) + 1


async def _next_revision(session: AsyncSession) -> int:
    """A revision no row of the brief has held. A replacement or a new draft
    takes one too, so the revision a caller read never names another row:
    a change stated against a version that has since been replaced is
    refused, not applied to its replacement. Remove deletes the rows and
    keeps the highest revision they held as a floor, so this holds across it."""
    return max(await highest_revision(session), (await get_top_picks_settings(session)).brief_revision_floor) + 1


async def highest_revision(session: AsyncSession) -> int:
    """The highest revision any row of the brief holds, 0 with none."""
    return int(await session.scalar(select(func.coalesce(func.max(PickBrief.revision), 0))) or 0)


def _stored(row: PickBrief | None) -> dict[str, Any]:
    return dict(row.body) if row is not None else {}


async def patch(session: AsyncSession, change: Patch) -> PickBrief:
    """Apply one change and return the row it wrote.

    A draft is changed in place and takes a new revision. The active brief
    is never changed in place: its change is a new active version and the one
    before becomes `superseded`. `activate` makes the draft the active
    version. Raises `RevisionMoved` when the row moved past `if_revision`
    (0 names a brief that does not exist yet) and `BriefError` for a change
    the engine refuses.
    """
    await lock_picks(session)
    if change.routine and (kept := sorted(set(change.parts) - ROUTINE_PARTS)):
        raise BriefError(
            "needs_the_person",
            f"A routine run cannot change {', '.join(kept)}: only the person does. Propose a rule with "
            "proposed_rules, or ask the person in a chat.",
            parts=kept,
        )
    if change.routine and change.summary is not None:
        raise BriefError("needs_the_person", "A routine run cannot change the summary: only the person does.",
                         parts=["summary"])
    if change.routine and change.activate:
        raise BriefError("needs_the_person", "Only the person makes a draft the active brief.", parts=["activate"])
    if not change.parts and change.summary is None and not change.activate:
        raise BriefError("nothing_given", "Name at least one part to change.")
    held_draft = await session.scalar(select(PickBrief).where(PickBrief.status == "draft").with_for_update())
    held_active = await session.scalar(select(PickBrief).where(PickBrief.status == "active").with_for_update())
    target = change.target or ("draft" if held_draft is not None or held_active is None else "active")
    if change.routine and target != "active":
        raise BriefError("needs_the_person", "A routine run changes only the active brief.", parts=["target"])
    made_by: MadeBy = "routine" if change.routine else "person"
    if target == "active":
        if held_active is None:
            raise BriefError("no_brief", "There is no active brief to change. Write the draft first.")
        if change.activate:
            raise BriefError("no_draft", "The active brief is already active; activate goes with the draft.")
        _same_revision(held_active.revision, change.if_revision)
        body = _applied(_stored(held_active), change.parts)
        row = PickBrief(
            version=await _next_version(session), status="active", body=body,
            summary=held_active.summary if change.summary is None else change.summary,
            reason=change.reason, made_by=made_by, host=change.host, revision=await _next_revision(session),
        )
        held_active.status = "superseded"
        # The partial unique index admits one active row: the old one leaves first.
        await session.flush()
        session.add(row)
        await session.flush()
        return row
    if held_draft is None:
        _same_revision(0, change.if_revision)
        # Counted on from the active brief's ids, so no id names two items.
        counters = {"ids": dict(_stored(held_active).get("ids") or {})}
        held_draft = PickBrief(
            version=await _next_version(session), status="draft", body=_applied(counters, change.parts),
            summary=change.summary or "", reason=change.reason, made_by=made_by, host=change.host,
            revision=await _next_revision(session),
        )
        session.add(held_draft)
    else:
        _same_revision(held_draft.revision, change.if_revision)
        held_draft.body = _applied(_stored(held_draft), change.parts)
        if change.summary is not None:
            held_draft.summary = change.summary
        held_draft.reason = change.reason
        held_draft.host = change.host
        held_draft.revision = await _next_revision(session)
    if change.activate:
        if held_active is not None:
            held_active.status = "superseded"
            await session.flush()
        held_draft.status = "active"
    await session.flush()
    return held_draft


def _same_revision(current_revision: int, stated: int) -> None:
    if current_revision != stated:
        raise RevisionMoved(expected=stated, current=current_revision)


async def remove_all(session: AsyncSession) -> int:
    """Delete the brief, every version of it, and say how many rows went.
    Only the person's own Remove calls this."""
    await lock_picks(session)
    removed = await session.execute(delete(PickBrief))
    return removed.rowcount or 0

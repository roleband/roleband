"""`offer.get`: the person's own offer and the private-company valuations they
entered, as the Stock tab's offer flow reads them (`GET /api/profile/offer`).

Both come from `tracker.user_profile.offer`, the store that route reads, and
are checked against the same shape on the way out: a stored value this shape
cannot read is left out, as the route leaves it out, never answered as other
figures. The valuations are a list by company slug, paged to the tool tier's
budget; every page carries the offer.

The offer is its own data category, this read's only one: when the person
does not share it, the switches refuse the read before it runs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError, field_validator
from pydantic.config import JsonDict
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations import cursor
from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape, ToolTier
from tracker.agents.operations.search import PAGE_BUDGET_BYTES
from tracker.user_profile.offer import read_offer, read_valuations

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

# --- shapes: the offer as `api/schemas/profile.py` keeps it ------------------ #

#: A dollar figure or a count of shares the person entered.
OfferFigure = Annotated[float, Field(ge=0, lt=1e13, allow_inf_nan=False)]
VestingPercent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
OfferStep = Literal["company", "base", "stock", "strike", "price", "valuation", "vesting", "bonus", "sign_on"]


class KeptOfferInputs(Shape):
    """What the person entered. A null figure is blank, never zero."""

    #: A company slug; empty for a company not on the list.
    company: str = Field(max_length=120, pattern=r"^(|[a-z0-9][a-z0-9-]*)$", json_schema_extra=_IDENTIFIER)
    #: Whether a company not on the list is publicly traded.
    listed: bool
    base: OfferFigure | None
    bonus_pct: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)] | None
    vehicle: Literal["rsu", "options"] = Field(json_schema_extra=_CODE)
    grant_unit: Literal["dollars", "shares"] = Field(json_schema_extra=_CODE)
    grant: OfferFigure | None
    strike: OfferFigure | None
    price: OfferFigure | None
    #: The share of the grant vesting in each year.
    vesting: Annotated[list[VestingPercent | None], Field(min_length=1, max_length=4)] | None
    #: The sign-on bonus paid in the first and the second year.
    sign_on: Annotated[list[OfferFigure | None], Field(min_length=2, max_length=2)]


class KeptOfferOrigin(Shape):
    """The typical figures the offer was started from: a company's median
    role, or one role (with its title)."""

    company: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$", json_schema_extra=_IDENTIFIER)
    title: str | None = Field(max_length=300, json_schema_extra=_CONTENT)


class KeptOffer(Shape):
    inputs: KeptOfferInputs
    #: The questions the person answered; the others still read the company's
    #: rule or the figures the offer started from.
    answered: list[OfferStep] = Field(max_length=9, json_schema_extra=_CODE)
    started_from: KeptOfferOrigin | None
    saved_at: datetime

    @field_validator("answered")
    @classmethod
    def _once_each(cls, steps: list[str]) -> list[str]:
        return list(dict.fromkeys(steps))


class KeptValuation(Shape):
    """A private company's value at grant and the one the person tests, per
    share or for the whole company."""

    company: str = Field(json_schema_extra=_IDENTIFIER)
    unit: Literal["per_share", "company"] = Field(json_schema_extra=_CODE)
    grant_at: OfferFigure | None
    test_at: OfferFigure | None
    #: Shares outstanding: turns a company valuation into a price per share.
    share_count: OfferFigure | None
    saved_at: datetime


class OfferGetInput(Shape):
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the page of valuations.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description="The next_cursor of the previous page: the valuations after it, by company slug.",
    )


class OfferRead(Shape):
    #: Null when the person has entered no offer.
    offer: KeptOffer | None
    #: Every valuation kept, on this page or not.
    valuation_count: int = Field(ge=0)
    #: This page's valuations by company slug; `meta.next_cursor` reads on.
    valuations: list[KeptValuation]


OFFER_GET = OperationDescriptor(
    id="offer.get",
    summary="Read the person's own offer and the private-company valuations they entered.",
    input=OfferGetInput,
    result=OfferRead,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("offer",),
    examples=({},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (OFFER_GET,)


# --- the read ---------------------------------------------------------------- #


def kept_offer(raw: dict[str, Any] | None) -> KeptOffer | None:
    """The stored offer, or None when there is none or this shape cannot read it."""
    if raw is None:
        return None
    try:
        return KeptOffer.model_validate(raw)
    except ValidationError:
        return None


def kept_valuations(raw: dict[str, object]) -> list[KeptValuation]:
    """Every stored valuation this shape can read, by company slug."""
    kept = []
    for company in sorted(raw):
        value = raw[company]
        # A stored key named `company` is one the stored shape does not have.
        if not isinstance(value, dict) or "company" in value:
            continue
        try:
            kept.append(KeptValuation.model_validate({**value, "company": company}))
        except ValidationError:
            continue
    return kept


async def offer_read(
    session: AsyncSession, params: OfferGetInput, *, workspace_id: str
) -> tuple[OfferRead, str | None, bool]:
    """The page, its next cursor, and whether the budget ended it early."""
    request = cursor.fingerprint(OFFER_GET.id, workspace_id, {})
    offset = 0 if params.cursor is None else cursor.decode(params.cursor, request=request)[0]
    offer = kept_offer(await read_offer(session))
    valuations = kept_valuations(await read_valuations(session))
    page = OfferRead(offer=offer, valuation_count=len(valuations), valuations=[])
    rest = valuations[offset:]
    page.valuations = rest[:fitting(rest, PAGE_BUDGET_BYTES[params.tier] - size_of(page))]
    end = offset + len(page.valuations)
    next_cursor = cursor.encode(request=request, offset=end) if end < len(valuations) else None
    return page, next_cursor, next_cursor is not None


def size_of(shape: Shape) -> int:
    """UTF-8 bytes of `shape` as the engine's JSON answer spells it."""
    return len(shape.model_dump_json().encode("utf-8"))


def fitting(items: list[Any], budget: int) -> int:
    """How many leading `items` fit `budget` bytes in one JSON list. A page
    always holds the first, so paging never stops before it starts."""
    used = 0
    for taken, item in enumerate(items):
        size = size_of(item) + 1
        if taken and used + size > budget:
            return taken
        used += size
    return len(items)

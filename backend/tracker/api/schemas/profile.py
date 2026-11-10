"""Contracts for the pay floor, the person's own offer, and pursuits.

`GET`, `PUT` and `DELETE /api/profile/pay-floor`; the offer routes under
`/api/profile/offer`; `GET /api/pursuits` and `PUT /api/jobs/{job_id}/pursuit`.
A pursuit is `JobPursuit`, the row job detail sends; the list adds the
opportunity it tracks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from tracker.api.schemas.base import Built
from tracker.api.schemas.jobs import JobPursuit
from tracker.api.schemas.text_class import text

# --- pay floor ------------------------------------------------------------ #


class PayFloor(Built):
    """The lowest yearly base pay the user would consider."""

    amount: int
    currency: str


class PayFloorResponse(Built):
    """`GET/PUT/DELETE /api/profile/pay-floor`: null when unset."""

    pay_floor: PayFloor | None


# --- the person's own offer (docs/pay.md, "Your offer") ------------------- #

#: A dollar figure or a count of shares the person enters.
OfferFigure = Annotated[float, Field(ge=0, lt=1e13, allow_inf_nan=False)]
#: A share of the grant vesting in one year.
VestingPercent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
#: A company slug; empty for a company not on the list.
OfferCompany = Annotated[
    str, Field(max_length=120, pattern=r"^(|[a-z0-9][a-z0-9-]*)$", json_schema_extra=text("code"))
]
#: The questions of the guided offer, in the dashboard's own words.
OfferStep = Literal["company", "base", "stock", "strike", "price", "valuation", "vesting", "bonus", "sign_on"]


class OfferInputs(Built):
    """What the person entered. A null figure is blank, never zero."""

    company: OfferCompany
    # Read only for a company not on the list.
    listed: bool
    base: OfferFigure | None
    bonus_pct: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)] | None
    vehicle: Literal["rsu", "options"]
    grant_unit: Literal["dollars", "shares"]
    grant: OfferFigure | None
    strike: OfferFigure | None
    price: OfferFigure | None
    vesting: Annotated[list[VestingPercent | None], Field(min_length=1, max_length=4)] | None
    sign_on: Annotated[list[OfferFigure | None], Field(min_length=2, max_length=2)]


class OfferOrigin(Built):
    """The typical figures the offer was started from: a company's median
    role, or one role (with its title)."""

    company: Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$", json_schema_extra=text("code"))]
    title: str | None = Field(max_length=300, json_schema_extra=text("content"))


class OfferDraft(Built):
    """`PUT /api/profile/offer`: the offer as the person has it now."""

    inputs: OfferInputs
    # The questions the person has answered; the rest still read the company's
    # rule or the figures it started from.
    answered: Annotated[list[OfferStep], Field(max_length=9)]
    started_from: OfferOrigin | None

    @field_validator("answered")
    @classmethod
    def _once_each(cls, steps: list[str]) -> list[str]:
        return list(dict.fromkeys(steps))


class StoredOffer(OfferDraft):
    saved_at: datetime


class ValuationDraft(Built):
    """`PUT /api/profile/offer/valuations/{company}`: a private company's value
    at grant and the one to test, per share or for the whole company."""

    unit: Literal["per_share", "company"]
    grant_at: OfferFigure | None
    test_at: OfferFigure | None
    # Shares outstanding: turns a company valuation into a price per share.
    share_count: OfferFigure | None


class StoredValuation(ValuationDraft):
    saved_at: datetime


class OfferResponse(Built):
    """Every offer route: the offer (null when none) and the valuations by
    company slug."""

    offer: StoredOffer | None
    valuations: dict[str, StoredValuation]


# --- pursuits -------------------------------------------------------------- #


class PursuitOpportunity(Built):
    title: str = Field(json_schema_extra=text("content"))
    company: str
    status: str
    url: str


class PursuitListItem(JobPursuit):
    """A pursuit with the opportunity it tracks."""

    opportunity: PursuitOpportunity


class PursuitListResponse(Built):
    """`GET /api/pursuits`: highest priority first, then most recently updated."""

    pursuits: list[PursuitListItem]


class PursuitWriteResponse(Built):
    """`PUT /api/jobs/{job_id}/pursuit`: the pursuit as written, without its opportunity."""

    pursuit: JobPursuit

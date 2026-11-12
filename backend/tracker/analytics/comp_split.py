"""The heuristic share of a year's pay that is equity, where nothing is measured,
and which listed stock a company's grants track.

A role's package (`comp_package`) prefers a company's measured per-level split.
Without one it reads the shares here: equity rises with seniority, a bonus is a
flat target share unless the company states its own bonus rule, and base is the
rest. The shares are the same for every company; a company's own facts enter
only as stated rules (its bonus rule, an equity rule of none), never as a
per-company multiplier. Every figure built from them is labelled an estimate.

A role's equity only tracks a real, liquid stock price for *public* companies:
those the atlas lists, or whose grants track a listed parent (`ticker_for`).
Everything else is treated as private/illiquid.
"""

from __future__ import annotations

from tracker.levels.identity import grant_ticker, identity_for, listed_ticker
from tracker.schema import LevelBand

# Which companies trade, and which listed stock a subsidiary's grants track, is
# the atlas's (`tracker.levels.identity`, `company_identity.csv` `listed` /
# `ticker` / `grant_ticker`).
#
# The one exception: a subsidiary outside the atlas whose employees are granted
# its listed parent's stock. Add a company to the atlas rather than a
# row here; an atlas company is never read from this table.
PARENT_TICKERS_OUTSIDE_ATLAS: dict[str, str] = {
    "linkedin": "MSFT",
}

# Share of a year's total pay that is equity, by seniority band. Senior packages
# tip more toward stock, so the equity share grows with level, and every band
# names its own: a share that fell back to a default would give an early-career
# role more stock than a senior one. An internship carries no equity grant.
_EQUITY_PCT_BY_BAND: dict[LevelBand, float] = {
    LevelBand.INTERN: 0.0,
    LevelBand.ENTRY: 0.20,
    LevelBand.MID: 0.28,
    LevelBand.SENIOR: 0.35,
    LevelBand.STAFF: 0.45,
    LevelBand.PRINCIPAL: 0.52,
    LevelBand.DIRECTOR_PLUS: 0.58,
}

#: Flat target-bonus share of a year's total pay, for a company that states no
#: bonus rule of its own.
BONUS_PCT = 0.12


def is_public(company: str) -> bool:
    """True if the company's equity tracks a liquid, publicly-listed ticker."""
    return ticker_for(company) is not None


def ticker_for(company: str) -> str | None:
    """The ticker a company's RSUs track, or None if private/illiquid."""
    return parent_ticker(company) or listed_ticker(company)


def parent_ticker(company: str) -> str | None:
    """The listed parent's ticker a subsidiary's grants track, or None."""
    if identity_for(company) is not None:
        return grant_ticker(company)
    return PARENT_TICKERS_OUTSIDE_ATLAS.get(company)


def equity_pct(band: LevelBand) -> float:
    """The heuristic equity share of a year's total pay at a band."""
    return _EQUITY_PCT_BY_BAND[band]


def heuristic_ratios(band: LevelBand, bonus_ratio: float | None, *, equity_none: bool = False) -> tuple[float, float]:
    """(bonus per base, equity per base) from the band shares.

    `bonus_ratio` is the company's stated bonus per base (0 for a company that
    pays none), or None when it states no rule; then the flat `BONUS_PCT` of the
    total applies. Whatever the bonus, equity stays the band's share of the
    total: base and bonus share what equity leaves. `equity_none` is a company
    that states it grants no equity.
    """
    equity = 0.0 if equity_none else equity_pct(band)
    if bonus_ratio is None:
        base = 1.0 - equity - BONUS_PCT
        return BONUS_PCT / base, equity / base
    return bonus_ratio, equity * (1.0 + bonus_ratio) / (1.0 - equity)

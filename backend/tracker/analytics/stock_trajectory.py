"""The Stock tab: each company's typical package, and how much of it is stock.

Built from the packages Job detail shows (`comp_package.build_job_package`), so a
role reads the same on both screens: base is the posted range where the posting
states one, bonus follows the company's stated rule, and equity is a measured
grant or the labelled estimate. A role whose package is not split into parts is
counted apart with its reason, never given a split of ours.

Pure: the API builds the packages and hands them here with each company's identity.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from tracker.analytics.comp_package import (
    NO_SPLIT_EMPLOYEE_ELECTION,
    NO_SPLIT_LEVEL_UNPLACED,
    NO_SPLIT_NOT_US,
    PROV_STATED,
    SPLIT_CROSS_FAMILY,
    SPLIT_MEASURED,
    employee_election,
)
from tracker.analytics.comp_split import is_public, parent_ticker, ticker_for
from tracker.levels.model import BONUS_NONE, BONUS_PCT_OF_BASE, EQUITY_NONE
from tracker.levels.pay import bonus_ratio_for, policy_for

# Where a part of a company's package comes from. A company whose roles differ
# reads `mixed`.
FROM_POSTED = "posted"  # the posting states it
FROM_COMPANY_RULE = "company_rule"  # the company states how it pays this part
FROM_MEASURED = "measured"  # a pay row measures this company and level
FROM_ESTIMATED = "estimated"  # our estimate
FROM_MIXED = "mixed"

# A role priced by a base alone, posted or estimated, with no total: bonus and
# equity are unknown, not zero.
SET_APART_BASE_ONLY = "base_only"

@dataclass(frozen=True)
class TrajectoryRole:
    """One open role's package, as Job detail builds it."""

    company: str
    band: str | None
    package: dict
    us_pay: bool


@dataclass(frozen=True)
class _Parts:
    base: float
    bonus: float
    equity: float
    sources: dict[str, str]

    @property
    def total(self) -> float:
        return self.base + self.bonus + self.equity


def _mid(component: dict | None) -> float:
    return (component["low"] + component["high"]) / 2 if component else 0.0


def _measured(package: dict) -> bool:
    return package.get("split_source") in (SPLIT_MEASURED, SPLIT_CROSS_FAMILY)


def _bonus_source(role: TrajectoryRole, bonus: dict | None) -> str:
    """Stated by the posting, read from a pay row, the company's own rule, or ours.
    Mirrors the order `comp_package._ratios` reads them in."""
    if bonus and bonus["provenance"] == PROV_STATED:
        return FROM_POSTED
    if _measured(role.package):
        return FROM_MEASURED
    if bonus_ratio_for(role.company, role.band) is not None:
        return FROM_COMPANY_RULE
    return FROM_ESTIMATED


def _parts(role: TrajectoryRole) -> _Parts | None:
    """The role's base, bonus and equity at the middle of each range, or None
    when its package is not split into all three."""
    package = role.package
    by_kind = {c["kind"]: c for c in package["components"]}
    base = by_kind.get("base")
    if package["total"] is None or base is None:
        return None
    return _Parts(
        base=_mid(base),
        bonus=_mid(by_kind.get("bonus")),
        equity=_mid(by_kind.get("equity")),
        sources={
            "base": FROM_POSTED if base["provenance"] == PROV_STATED else FROM_ESTIMATED,
            "bonus": _bonus_source(role, by_kind.get("bonus")),
            "equity": _equity_source(role),
        },
    )


def _equity_source(role: TrajectoryRole) -> str:
    """Read from a pay row, the company's stated rule of no equity, or ours.
    Mirrors the order `comp_package._ratios` reads them in."""
    if _measured(role.package):
        return FROM_MEASURED
    if policy_for(role.company).equity_rule == EQUITY_NONE:
        return FROM_COMPANY_RULE
    return FROM_ESTIMATED


def _set_apart_reason(role: TrajectoryRole) -> str | None:
    """Why a role with a pay figure has no split here; None for one with no pay
    figure at all, which the tab does not count."""
    package = role.package
    if not role.us_pay:
        # The tab is in US dollars, and our split is measured on US pay.
        return NO_SPLIT_NOT_US
    if package["no_split_reason"]:
        return package["no_split_reason"]
    if package["total"] is not None:
        return None
    if package["base_estimate"]:
        return SET_APART_BASE_ONLY
    if package["estimate"] or package["stated"]:
        # A figure the package built nothing on: the level is not placed.
        return NO_SPLIT_LEVEL_UNPLACED
    return None


def _percentile_50(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _combine(sources: Iterable[str]) -> str:
    seen = set(sources)
    return seen.pop() if len(seen) == 1 else FROM_MIXED


def _summary(parts: list[_Parts]) -> dict:
    """A company's typical package: the median total, split by the dollar-weighted
    share of each part across its roles, so the parts add up to the total."""
    totals = [p.total for p in parts]
    whole = sum(totals)
    equity_share = sum(p.equity for p in parts) / whole if whole else 0.0
    bonus_share = sum(p.bonus for p in parts) / whole if whole else 0.0
    median = round(_percentile_50(totals))
    equity = round(median * equity_share)
    bonus = round(median * bonus_share)
    return {
        "count": len(parts),
        "median_tc": median,
        "base": median - equity - bonus,
        "bonus": bonus,
        "equity": equity,
        "equity_pct": round(equity_share, 4),
        "sources": {
            kind: _combine(p.sources[kind] for p in parts) for kind in ("base", "bonus", "equity")
        },
    }


def _choice_total(package: dict) -> tuple[float, str] | None:
    """A cash-election role's total: the band the posting states, else ours."""
    if package["total"]:
        return _mid(package["total"]), FROM_POSTED
    estimate = package["estimate"]
    if estimate and estimate.get("median"):
        return float(estimate["median"]), FROM_ESTIMATED
    return None


# A subsidiary granted its listed parent's stock is read from `parent_ticker`
# first: its own profile truly says "not listed", which is not what the equity
# does. Resolved identity (`profiles`) beats the hardcoded table, which cannot
# know about a company that listed later.
def _listed(company: str, profiles: Mapping[str, dict]) -> bool:
    if parent_ticker(company):
        return True
    p = profiles.get(company)
    return bool(p["is_public"]) if p and p.get("is_public") is not None else is_public(company)


def _company_ticker(company: str, profiles: Mapping[str, dict]) -> str | None:
    if parent := parent_ticker(company):
        return parent
    p = profiles.get(company)
    return p.get("ticker") if p and p.get("ticker") else ticker_for(company)


def build_comp_trajectory(
    roles: Iterable[TrajectoryRole],
    *,
    profiles: Mapping[str, dict] | None = None,
    company_limit: int = 20,
) -> dict:
    """The Stock tab's companies, in four groups:

    - `public`: a listed company's typical package; its stock part moves with the price;
    - `private`: the same for a company not listed, whose stock cannot be sold;
    - `choice`: a company where each person picks the cash and stock mix, so no
      split and no price move is shown for it;
    - `set_apart`: how many roles with a pay figure have no split, by reason.

    `overall` is the package across every public role: the slider's baseline.
    `profiles` carries resolved identity (is_public / ticker / equity_vehicle);
    without it identity falls back to the atlas.
    """
    profiles = profiles or {}

    def _public(company: str) -> bool:
        return _listed(company, profiles)

    def _ticker(company: str) -> str | None:
        return _company_ticker(company, profiles)

    split: dict[str, list[_Parts]] = {}
    policies: dict[str, dict | None] = {}
    choice: dict[str, list[tuple[float, str]]] = {}
    set_apart: Counter[str] = Counter()
    for role in roles:
        reason = _set_apart_reason(role)
        if reason != NO_SPLIT_NOT_US and employee_election(role.company):
            # The person picks the mix, whatever the posting states or omits.
            if (total := _choice_total(role.package)) is not None:
                choice.setdefault(role.company, []).append(total)
            elif reason is not None:
                # The election itself only explains a yearly base standing alone;
                # an hourly rate or an unplaced level keeps the posting's reason.
                set_apart[SET_APART_BASE_ONLY if reason == NO_SPLIT_EMPLOYEE_ELECTION else reason] += 1
            continue
        if reason is not None:
            set_apart[reason] += 1
            continue
        parts = _parts(role)
        if parts is None:
            continue
        split.setdefault(role.company, []).append(parts)
        policies.setdefault(role.company, role.package.get("policy"))

    public: list[dict] = []
    private: list[dict] = []
    for company, parts in split.items():
        policy = policies.get(company) or {}
        entry = {
            "company": company,
            **_summary(parts),
            "equity_vehicle": "rsu" if parent_ticker(company) else profiles.get(company, {}).get("equity_vehicle"),
            "vesting": policy.get("vesting"),
        }
        if _public(company):
            public.append({**entry, "ticker": _ticker(company)})
        else:
            private.append(entry)

    public.sort(key=lambda d: (-d["equity_pct"], d["company"]))
    private.sort(key=lambda d: (-d["median_tc"], d["company"]))

    choice_rows = []
    for company, totals in choice.items():
        choice_rows.append({
            "company": company,
            "ticker": _ticker(company) if _public(company) else None,
            "count": len(totals),
            "median_tc": round(_percentile_50([t for t, _ in totals])),
            "total_source": _combine(source for _, source in totals),
        })
    choice_rows.sort(key=lambda d: (-d["count"], d["company"]))

    public_parts = [p for company, parts in split.items() if _public(company) for p in parts]
    return {
        "currency": "USD",
        "overall": _summary(public_parts) if public_parts else None,
        "public": public[:company_limit],
        "private": private[:company_limit],
        "choice": choice_rows[:company_limit],
        "set_apart": [
            {"reason": reason, "count": count}
            for reason, count in sorted(set_apart.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


#: The offer calculator shows four years; a schedule longer than that is not
#: offered as a prefill, so the person never sees a grant cut short.
OFFER_YEARS = 4


def _vesting_fractions(schedule: str | None) -> list[float] | None:
    """A stated schedule such as "5/15/40/40" as [5, 15, 40, 40], the percent
    vesting each year; None when absent, unreadable or longer than the
    calculator's four years."""
    if not schedule:
        return None
    try:
        parts = [float(part) for part in schedule.split("/")]
    except ValueError:
        return None
    if not parts or len(parts) > OFFER_YEARS or any(p < 0 for p in parts) or sum(parts) <= 0:
        return None
    return parts


def build_offer_terms(
    companies: Iterable[str],
    *,
    profiles: Mapping[str, dict] | None = None,
    quotes: Mapping[str, dict] | None = None,
) -> list[dict]:
    """What the offer calculator fills in when the person picks a company: the
    stock type, ticker, vesting schedule and bonus rule the company states, and
    the last stored quote for a listed one. A fact the company does not state is
    None, never a default: the screen labels the even schedule it assumes.

    `quotes` holds only quotes already stored by the prices job; nothing here
    asks a price feed.
    """
    profiles = profiles or {}
    quotes = quotes or {}
    rows = []
    for company in sorted(set(companies)):
        policy = policy_for(company)
        listed = _listed(company, profiles)
        vesting = _vesting_fractions(policy.vesting)
        quote = quotes.get(company) if listed else None
        rows.append({
            "company": company,
            "listed": listed,
            "ticker": _company_ticker(company, profiles) if listed else None,
            "equity_vehicle": (
                "rsu" if parent_ticker(company)
                else profiles.get(company, {}).get("equity_vehicle") or policy.equity_vehicle
            ),
            "vesting": vesting,
            "vesting_stated_by": policy.stated_by("vesting") if vesting else None,
            "bonus_rule": policy.bonus_rule if policy.bonus_rule in (BONUS_NONE, BONUS_PCT_OF_BASE) else None,
            "sign_on_bridges_vesting": policy.sign_on_bridges_vesting,
            "quote": (
                {"price": round(float(quote["price"]), 4), "as_of": quote["as_of"]}
                if quote and quote.get("currency", "USD") == "USD"
                else None
            ),
        })
    return rows

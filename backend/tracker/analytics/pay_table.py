"""The Compensation tab's company table at one level, and posted pay by discipline.

Pure, DB-free: the route hands in the roles at one level that list a place in
one country, and these build one row per company and the comparison by
discipline. A company's posted cell reads what a level's figure reads
(`comp_stats.build_posted_pay`): yearly base pay for the role's pay country, in
the country's currency, never a level read from the range itself, each distinct
range once. An estimate never fills that cell and never sorts among posted pay
(docs/pay.md, "Posted pay on Insights").
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from statistics import median
from typing import NamedTuple

from tracker.analytics.comp_stats import (
    DISCLOSED_FLOOR,
    POSTED_MIN_EMPLOYERS,
    POSTED_MIN_RANGES,
    level_figure,
)
from tracker.levels import UNSTATED_LEVEL
from tracker.pay_disclosure import disclosure_known
from tracker.pay_period import effective_period, size_classes
from tracker.schema import LevelBasis
from tracker.taxonomy.locations import pay_country

#: A discipline shows a typical range only while no one employer posts more
#: than this share of its distinct ranges: an employer that posts a range per
#: city can fill a small discipline alone.
DISCIPLINE_MAX_EMPLOYER_SHARE = 0.4
#: The skill filter offers a skill once this many of the table's roles name it.
SKILL_MIN_ROLES = 3

#: Why a company's posted cell holds no range, in the order a tie is broken.
TOTAL = "total"
UNCLEAR = "unclear"
SEVERAL_COUNTRIES = "several_countries"
NOT_YEARLY = "not_yearly"
PLACED_BY_PAY = "placed_by_pay"
UNREAD = "unread"
NONE = "none"
_REASON_ORDER = (TOTAL, UNCLEAR, SEVERAL_COUNTRIES, NOT_YEARLY, PLACED_BY_PAY)

#: The estimate provider whose total is the seed of one rung (`comp_providers.static`).
SEED_PROVIDER = "static"


class TableRole(NamedTuple):
    """One open role at the table's level or with no placed level, in the
    table's country, read through the posting that places it there. `skills`
    are the skills its posting names."""

    company: str
    family: str | None
    level: str
    level_basis: str | None
    places: tuple[str, ...]
    structured_at: datetime | None
    base_min: float | None
    base_max: float | None
    pay_basis: str | None
    currency: str | None
    period: str | None
    skills: frozenset[str] = frozenset()


class EstimateRole(NamedTuple):
    """One role's stored pay estimate in US dollars, read through the posting
    the daily pay record keeps for it (`db.queries.jobs.priced_in_dollars`),
    so the table and that record never price one role from two postings."""

    company: str
    family: str | None
    base: int | None
    total: int | None
    provider: str | None


def _read_range(role: TableRole, country: str, currency: str | None) -> tuple:
    """What one role's posted range adds to its company's cell in `country`:
    `("shown", lo, hi)`, `("other", currency, lo, hi)`, `("reason", why)`, or
    `("none",)` for no range, or no salary at any size."""
    if role.base_min is None or role.base_max is None:
        return ("none",)
    if role.pay_basis != "base":
        return ("reason", TOTAL if role.pay_basis == "total" else UNCLEAR)
    cur = (role.currency or "USD").upper()
    if not size_classes(role.base_min, role.base_max, cur):
        return ("none",)
    if effective_period(role.period, role.base_min, role.base_max, cur) != "year":
        return ("reason", NOT_YEARLY)
    lo, hi = int(role.base_min), int(role.base_max)
    if cur == "USD" and lo < DISCLOSED_FLOOR:
        return ("none",)
    # The role lists a place in `country`; any other pay country means it
    # names places in several, and its range may be for any of them.
    if pay_country(role.places) != country:
        return ("reason", SEVERAL_COUNTRIES)
    if role.level_basis == LevelBasis.PAY_GRADE.value:
        return ("reason", PLACED_BY_PAY)
    if cur != currency:
        return ("other", cur, lo, hi)
    return ("shown", lo, hi)


def _figure(ranges: Mapping[tuple[int, int], int]) -> dict:
    """A company's ranges as the median low to the median high, with each
    distinct range and the roles on it, widest-paying first."""
    return {
        "low": float(median(lo for lo, _ in ranges)),
        "high": float(median(hi for _, hi in ranges)),
        "ranges": [
            {"low": lo, "high": hi, "roles": roles}
            for (lo, hi), roles in sorted(ranges.items(), key=lambda kv: (-kv[0][1], -kv[0][0]))
        ],
    }


def _span(values: Iterable[int]) -> dict | None:
    distinct = sorted(set(values))
    return {"low": distinct[0], "high": distinct[-1]} if distinct else None


def _row(
    company: str,
    roles: list[TableRole],
    *,
    country: str,
    currency: str | None,
    estimates: list[EstimateRole],
    level: str,
    rung: Callable[[str, str], str | None],
    equity: Callable[[str], dict | None],
    followed_as_set: frozenset[str],
) -> dict:
    shown: Counter[tuple[int, int]] = Counter()
    other: dict[str, Counter[tuple[int, int]]] = {}
    reasons: Counter[str] = Counter()
    checked = 0
    for role in roles:
        checked += disclosure_known(role.structured_at, role.base_min, role.base_max)
        read = _read_range(role, country, currency)
        if read[0] == "shown":
            shown[(read[1], read[2])] += 1
        elif read[0] == "other":
            other.setdefault(read[1], Counter())[(read[2], read[3])] += 1
        elif read[0] == "reason":
            reasons[read[1]] += 1

    row: dict = {
        "company": company,
        "followed_as_set": company in followed_as_set,
        "open_roles": len(roles),
        "posting": sum(shown.values()),
        "checked": checked,
        "currency": None,
        "low": None,
        "high": None,
        "ranges": [],
        "other_currency": False,
        "reason": None,
    }
    if shown:
        row.update(currency=currency, **_figure(shown))
    elif other:
        # The currency the company posts most distinct ranges in; the code
        # breaks a tie, so two reads agree.
        cur = max(other, key=lambda c: (len(other[c]), c))
        row.update(currency=cur, other_currency=True, **_figure(other[cur]))
    elif reasons:
        row["reason"] = max(reasons, key=lambda r: (reasons[r], -_REASON_ORDER.index(r)))
    else:
        row["reason"] = UNREAD if checked == 0 else NONE

    row["estimate_base"] = None
    row["estimate_total"] = None
    base = _span(e.base for e in estimates if e.base is not None)
    if base:
        row["estimate_base"] = {
            **base, "families": sorted({e.family for e in estimates if e.base is not None and e.family}),
        }
    total = _span(e.total for e in estimates if e.total is not None)
    if total:
        seeded = any(e.provider == SEED_PROVIDER for e in estimates if e.total is not None)
        row["estimate_total"] = {**total, "rung": rung(company, level) if seeded else None}
    row["equity"] = equity(company)
    return row


def _order(row: dict) -> tuple:
    """Posted ranges first, by the middle of the figure; then ranges in another
    currency, apart per currency; then every company with no range shown, by
    open roles. The name breaks a tie, so two reads list rows in one order."""
    if row["low"] is not None and not row["other_currency"]:
        return (0, "", -(row["low"] + row["high"]) / 2, row["company"])
    if row["other_currency"]:
        return (1, row["currency"], -(row["low"] + row["high"]) / 2, row["company"])
    return (2, "", -row["open_roles"], row["company"])


def build_pay_table(
    roles: Iterable[TableRole],
    *,
    country: str,
    currency: str | None,
    level: str,
    estimates: Iterable[EstimateRole] = (),
    families: Iterable[str] = (),
    skill: str | None = None,
    followed_as_set: frozenset[str] = frozenset(),
    rung: Callable[[str, str], str | None] = lambda _company, _level: None,
    equity: Callable[[str], dict | None] = lambda _company: None,
    min_skill_roles: int = SKILL_MIN_ROLES,
) -> dict:
    """One row per company hiring at `level` in `country`, and the roles at
    the same companies whose level is not placed.

    `roles` are the open roles that list a place in `country` (Insights' place
    rule), at `level` or at no placed level, with the companies side already
    applied. `families` narrows the table to the picked disciplines, then
    `skill` to the roles naming it; the skills offered are those `min_skill_roles`
    of the table's roles name before the skill narrows it. `currency` is the
    country's own (`build_posted_pay`); a company posting only in another shows
    its range in that currency, after the rest.

    `estimates` are the stored estimates of the roles this table shows, read
    through the posting the daily pay record prices each role by: the caller
    narrows them to the level, the side and the skill, as it narrows `roles`,
    so a row's estimate rests on the same roles as its figure. They are US pay
    only, so a country outside the US is given none, and a company with no row
    reads none of them.
    `followed_as_set` names the companies followed as part of a set;
    `rung(company, level)` names the rung a seed total reads, and `equity(company)`
    the equity facts the company itself states.
    """
    picked = set(families)
    pool = [r for r in roles if not picked or r.family in picked]
    at_level = [r for r in pool if r.level == level]
    named = Counter(s for r in at_level for s in r.skills)
    skills = sorted(
        ({"term": term, "roles": n} for term, n in named.items() if n >= min_skill_roles),
        key=lambda s: (-s["roles"], s["term"]),
    )
    if skill:
        pool = [r for r in pool if skill in r.skills]

    by_company: dict[str, list[TableRole]] = {}
    unplaced: Counter[str] = Counter()
    for role in pool:
        if role.level == level:
            by_company.setdefault(role.company, []).append(role)
        elif role.level == UNSTATED_LEVEL:
            unplaced[role.company] += 1

    priced: dict[str, list[EstimateRole]] = {}
    for estimate in estimates:
        if estimate.company in by_company and (not picked or estimate.family in picked):
            priced.setdefault(estimate.company, []).append(estimate)

    rows = sorted(
        (
            _row(
                company, company_roles, country=country, currency=currency,
                estimates=priced.get(company, []) if country == "US" else [],
                level=level, rung=rung, equity=equity, followed_as_set=followed_as_set,
            )
            for company, company_roles in by_company.items()
        ),
        key=_order,
    )
    return {
        "country": country,
        "level_band": level,
        "currency": currency,
        "skill": skill,
        "estimates": country == "US",
        "rows": rows,
        "not_placed": [
            {"company": company, "roles": n} for company, n in sorted(unplaced.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "skills": skills,
        "min_skill_roles": min_skill_roles,
    }


def build_pay_by_discipline(
    roles: Iterable[TableRole],
    *,
    country: str,
    currency: str | None,
    level: str,
    families: Iterable[str] = (),
    min_employers: int = POSTED_MIN_EMPLOYERS,
    min_ranges: int = POSTED_MIN_RANGES,
    max_employer_share: float = DISCIPLINE_MAX_EMPLOYER_SHARE,
) -> dict:
    """Posted base pay per discipline at one level in one country, read as the
    level's own figure is (one vote per distinct range, the same minimums),
    every discipline at once: `families`, the picked ones, are marked, never
    the only ones shown. A discipline is withheld below the minimums
    (`too_few`) or while one employer posts more than `max_employer_share` of
    its ranges (`one_employer`); a withheld one carries its counts, no figure."""
    picked = set(families)
    cells: dict[str, Counter[tuple[str, int, int]]] = {}
    for role in roles:
        if role.level != level or not role.family:
            continue
        read = _read_range(role, country, currency)
        if read[0] == "shown":
            cells.setdefault(role.family, Counter())[(role.company, read[1], read[2])] += 1

    out = []
    for family, ranges in cells.items():
        figure = level_figure(dict(ranges), min_employers=min_employers, min_ranges=min_ranges)
        top_share = max(Counter(company for company, _, _ in ranges).values()) / len(ranges)
        withheld = None
        if not figure["enough"]:
            withheld = "too_few"
        elif top_share > max_employer_share:
            withheld = "one_employer"
            figure.update(enough=False, low=None, high=None, mid_p25=None, mid_p75=None)
        out.append({
            "family": family,
            "picked": family in picked,
            "top_share": round(top_share, 4),
            "withheld": withheld,
            **figure,
        })
    out.sort(key=lambda d: (
        d["withheld"] is not None,
        -((d["low"] + d["high"]) / 2) if d["low"] is not None else -d["ranges"],
        d["family"],
    ))
    return {
        "min_employers": min_employers,
        "min_ranges": min_ranges,
        "max_employer_share": max_employer_share,
        "disciplines": out,
    }

"""Compensation analytics for the Statistics "Compensation" sub-tab.

Pure, DB-free aggregation over the roles open now: what employers post as
base pay (`build_posted_pay`), the estimate's percentile summary and its
per-level, per-company and per-family breakdowns, and who states pay. The API
layer fetches the rows and hands them here, so all the math is unit-testable
without a database. The estimate is a lookup, not a posting (see
`Job.comp_provenance`), and the UI labels it so.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from tracker.levels import UNSTATED_LEVEL
from tracker.pay_disclosure import band_stated, disclosure_known
from tracker.pay_period import effective_period, not_yearly_usd, size_classes
from tracker.schema import LEVEL_BAND_ORDER, LevelBand, LevelBasis, parse_band
from tracker.taxonomy.locations import pay_country


def _percentile(sorted_vals: Sequence[int], p: float) -> float | None:
    """Linear-interpolated percentile (p in [0,1]) matching Postgres percentile_cont."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    idx = p * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _summary(vals: Sequence[int]) -> dict:
    """Count + min/max + p25/p50/p75/p90 for one group of comp values."""
    s = sorted(vals)
    return {
        "count": len(s),
        "min": s[0] if s else None,
        "max": s[-1] if s else None,
        "p25": _percentile(s, 0.25),
        "p50": _percentile(s, 0.50),
        "p75": _percentile(s, 0.75),
        "p90": _percentile(s, 0.90),
    }


def _grouped(rows: Iterable[tuple], key_idx: int) -> dict[object, list[int]]:
    groups: dict[object, list[int]] = {}
    for r in rows:
        key = r[key_idx]
        val = r[3]
        if val is None:
            continue
        groups.setdefault(key, []).append(int(val))
    return groups


# The fewest priced roles a level, company or discipline needs to be shown.
# The estimate is a lookup with few distinct values, so a group of
# one is one lookup cell, not a market.
COMP_MIN_ROLES = 5


def level_order(key: object) -> int:
    """Seniority rank of a level key: the rungs in order, then `unstated`
    (a role whose level we cannot place), as the Board lists it."""
    if key == UNSTATED_LEVEL:
        return max(LEVEL_BAND_ORDER.values()) + 1
    return LEVEL_BAND_ORDER.get(str(key), 0)


def build_comp_stats(
    rows: Sequence[tuple],
    total_open: int,
    *,
    company_limit: int = 15,
    min_roles: int = COMP_MIN_ROLES,
) -> dict:
    """Aggregate open-job comp into the Compensation panel payload.

    `rows` are `(company, level, family, comp_median)`, `level` the level key
    (`db.queries.scope.level_key_expr`); rows with a null
    comp_median are ignored in the math but `total_open` reflects all open jobs so
    the UI can report coverage. `by_level` is ordered by seniority and leaves
    out `unstated` rows: their estimate was looked up at a guessed band, so a
    row of them restates the guess. `by_company`
    and `by_family` are ranked by median (p50) descending. A group needs
    `min_roles` priced roles to be listed; `min_roles` is returned so the UI
    can say so, and every group carries its `count`.
    """
    vals = [int(r[3]) for r in rows if r[3] is not None]

    def _enough(groups: dict[object, list[int]]) -> list[tuple[object, list[int]]]:
        return [(k, vs) for k, vs in groups.items() if k is not None and len(vs) >= min_roles]

    by_level = [
        {"level_band": lb, **_summary(vs)}
        for lb, vs in sorted(_enough(_grouped(rows, 1)), key=lambda kv: level_order(kv[0]))
        if lb != UNSTATED_LEVEL
    ]
    by_company = sorted(
        ({"company": c, **_summary(vs)} for c, vs in _enough(_grouped(rows, 0))),
        # Name breaks a tie in the median, so equal medians never swap places,
        # or swap which company the limit cuts, between two reads of one table.
        key=lambda d: (-(d["p50"] or 0), d["company"]),
    )[:company_limit]
    by_family = sorted(
        ({"family": f, **_summary(vs)} for f, vs in _enough(_grouped(rows, 2))),
        key=lambda d: (-(d["p50"] or 0), d["family"] or ""),
    )

    return {
        "min_roles": min_roles,
        "coverage": {
            "with_comp": len(vals),
            "total_open": total_open,
            "pct": round(len(vals) / total_open, 3) if total_open else 0.0,
        },
        "overall": _summary(vals) if vals else None,
        "by_level": by_level,
        "by_company": by_company,
        "by_family": by_family,
    }


def _pctiles(vals: Sequence[int]) -> dict:
    """Count + p25/p50/p75/p90 for a comp group (the trend rollup slice shape)."""
    s = sorted(vals)
    return {
        "count": len(s),
        "p25": _percentile(s, 0.25),
        "p50": _percentile(s, 0.50),
        "p75": _percentile(s, 0.75),
        "p90": _percentile(s, 0.90),
    }


def build_comp_metric_rows(rows: Sequence[tuple]) -> list[dict]:
    """Independently computed comp percentile slices for the daily trend rollup.

    `rows` are `(company, level_band, family, comp_median)` (same shape as
    `build_comp_stats`). Returns one `{dim, key, count, p25, p50, p75, p90}` per
    grouping: a single `overall` row plus one row per company, per level band, and
    per non-null family. Rows with a null comp_median are ignored. Each slice's
    percentiles are computed from that group's raw values (not re-aggregated), so
    every stored series is exact.
    """
    out: list[dict] = []

    overall = [int(r[3]) for r in rows if r[3] is not None]
    if overall:
        out.append({"dim": "overall", "key": "", **_pctiles(overall)})

    for dim, idx in (("company", 0), ("level", 1), ("family", 2)):
        for key, vals in _grouped(rows, idx).items():
            if key is None:  # unclassified family (or company) — skip
                continue
            out.append({"dim": dim, "key": key, **_pctiles(vals)})

    return out


def _as_band(raw: object) -> LevelBand | None:
    """Coerce a stored level_band (str or enum) into a LevelBand, or None."""
    if isinstance(raw, LevelBand):
        return raw
    try:
        return parse_band(raw)
    except (ValueError, TypeError):
        return None



# Below this an annual figure is not a salary: Anthropic posts a literal
# "Annual Salary: $1—$2 USD" placeholder on some reqs. The extraction is correct
# (the span is verbatim), so the posting is what is junk — drop it here rather
# than let it set the axis floor.
DISCLOSED_FLOOR = 50_000
#: A level shows a typical posted range once this many employers and distinct
#: ranges stand behind it. Below either, one employer's ladder would be the
#: figure (one employer can post a single range on dozens of roles).
POSTED_MIN_EMPLOYERS = 5
POSTED_MIN_RANGES = 8

#: The country a posted-pay read opens on.
POSTED_DEFAULT_COUNTRY = "US"


def _posted_order(d: dict) -> tuple:
    """Seniority, then the widest-paying range first within a level; company
    and low end break the last ties, so two reads list ranges in one order."""
    return (level_order(d["level_band"]), -d["high"], d["company"], d["low"])


def _level_figure(ranges: dict[tuple[str, int, int], int], *, min_employers: int, min_ranges: int) -> dict:
    """One level's posted pay in one country and currency. Each distinct range
    (company, low, high) votes once, however many roles carry it: an employer
    posts one range per level and place and hangs many roles off it. The
    figure is the median low to the median high, with the middle half of the
    ranges' midpoints, and is withheld below the minimums."""
    employers = len({company for company, _, _ in ranges})
    enough = employers >= min_employers and len(ranges) >= min_ranges
    lows = sorted(low for _, low, _ in ranges)
    highs = sorted(high for _, _, high in ranges)
    mids = sorted((low + high) / 2 for _, low, high in ranges)
    return {
        "ranges": len(ranges),
        "employers": employers,
        "roles": sum(ranges.values()),
        "enough": enough,
        "low": _percentile(lows, 0.5) if enough else None,
        "high": _percentile(highs, 0.5) if enough else None,
        "mid_p25": _percentile(mids, 0.25) if enough else None,
        "mid_p75": _percentile(mids, 0.75) if enough else None,
    }


def _currency_weight(currency: str, rows: list[tuple[str, str, int, int]]) -> tuple[int, int, bool, str]:
    """How strongly one currency's `(company, level, low, high)` rows claim a
    country: distinct ranges at a placed level, then all distinct ranges, then
    the US dollar, then the code, so the choice never depends on arrival. A
    range is distinct per level, as each level's figure counts it."""
    placed = {row for row in rows if row[1] != UNSTATED_LEVEL}
    return len(placed), len(set(rows)), currency == "USD", currency


def _country_exclusions() -> dict[str, int]:
    """One country's roles left out, by reason. A role that names no country,
    or several, is counted only across all countries."""
    return {"not_base": 0, "not_yearly": 0, "implausible": 0, "placed_by_pay": 0}


def build_posted_pay(
    rows: Iterable[tuple],
    *,
    your_countries: Iterable[str] = (),
    min_employers: int = POSTED_MIN_EMPLOYERS,
    min_ranges: int = POSTED_MIN_RANGES,
) -> dict:
    """What employers post as yearly base pay, per country and level.

    `rows` are `(company, level, level_basis, base_min, base_max, pay_basis,
    currency, period, location_groups)` for the roles open now, `level` the
    level key (`db.queries.scope.level_key_expr`).

    A figure is one country and one currency: nothing is converted or
    annualised. A role counts for the country every place it names lies in
    (`taxonomy.locations.pay_country`); a role naming places in several
    countries, or none we can place, counts for none. A country's currency is
    the one most of its ranges at a placed level are posted in, and its ranges
    in any other are counted apart.

    Only yearly base pay is read. A range that is total pay or unclear, hourly
    or monthly, or no salary at any size is counted under its reason in
    `excluded`, never silently dropped. A role whose level was read from its
    posted range (`LevelBasis.PAY_GRADE`) is left out too: its range placed
    its level, so counting it would describe pay by pay. A role whose level
    we cannot place is counted apart in `not_placed`, never inside a level.

    `bands` lists every distinct range at a placed level, uncapped, for the
    chart. `your_countries` are the countries of the person's places: each
    is listed even with no range, so the screen can say so.

    `excluded` counts every role left out, across all countries; each
    country's own `excluded` counts the roles in that country only, so a
    note under one country's heading never counts another's roles.
    `excluded["without_country"]` counts every role left out that names
    several countries or none, whatever its reason: no country's note
    counts it otherwise, so each says it.
    """
    excluded = {
        "not_base": 0, "not_yearly": 0, "implausible": 0, "no_country": 0, "placed_by_pay": 0, "without_country": 0,
    }
    by_country: dict[str, dict[str, int]] = {}
    cells: dict[str, dict[str, list[tuple[str, str, int, int]]]] = {}

    def leave_out(reason: str, country: str | None) -> None:
        excluded[reason] += 1
        if country is None:
            excluded["without_country"] += 1
        else:
            own = by_country.setdefault(country, _country_exclusions())
            own[reason] += 1

    for company, level, basis, lo, hi, pay_basis, currency, period, places in rows:
        if company is None or lo is None or hi is None:
            continue
        country = pay_country(places)
        if pay_basis != "base":
            leave_out("not_base", country)
            continue
        currency = (currency or "USD").upper()
        if not size_classes(lo, hi, currency):
            leave_out("implausible", country)
            continue
        if effective_period(period, lo, hi, currency) != "year":
            leave_out("not_yearly", country)
            continue
        lo, hi = int(lo), int(hi)
        if country is None:
            excluded["no_country"] += 1
            excluded["without_country"] += 1
            continue
        if basis == LevelBasis.PAY_GRADE.value:
            leave_out("placed_by_pay", country)
            continue
        cells.setdefault(country, {}).setdefault(currency, []).append((company, level or UNSTATED_LEVEL, lo, hi))

    countries = []
    for country, by_currency in cells.items():
        # The country's own currency: the one most of its distinct ranges at a
        # placed level use. Ranges at no placed level never enter a level, so
        # counting them could pick a currency with nothing to show; they only
        # break a tie.
        currency = max(by_currency, key=lambda cur: _currency_weight(cur, by_currency[cur]))
        levels: dict[str, dict[tuple[str, int, int], int]] = {}
        for company, level, lo, hi in by_currency[currency]:
            key = (company, lo, hi)
            cell = levels.setdefault(level, {})
            cell[key] = cell.get(key, 0) + 1
        unplaced = levels.pop(UNSTATED_LEVEL, {})
        bands = sorted(
            (
                {"company": company, "level_band": level, "low": lo, "high": hi, "reqs": reqs}
                for level, ranges in levels.items()
                for (company, lo, hi), reqs in ranges.items()
            ),
            key=_posted_order,
        )
        countries.append({
            "country": country,
            "currency": currency,
            "ranges": len(bands),
            "levels": [
                {"level_band": level, **_level_figure(ranges, min_employers=min_employers, min_ranges=min_ranges)}
                for level, ranges in sorted(levels.items(), key=lambda kv: level_order(kv[0]))
            ],
            "not_placed": {"roles": sum(unplaced.values()), "ranges": len(unplaced)},
            "other_currency": sum(len(rs) for cur, rs in by_currency.items() if cur != currency),
            "bands": bands,
            "excluded": by_country.get(country, _country_exclusions()),
        })
    listed = {c["country"] for c in countries}
    yours = set(your_countries)
    countries.extend(
        {"country": code, "currency": None, "ranges": 0, "levels": [], "not_placed": {"roles": 0, "ranges": 0},
         "other_currency": 0, "bands": [], "excluded": by_country.get(code, _country_exclusions())}
        for code in sorted(yours - listed)
    )
    for entry in countries:
        entry["yours"] = entry["country"] in yours
    countries.sort(key=lambda c: (-c["ranges"], c["country"]))
    codes = [c["country"] for c in countries]
    return {
        "min_employers": min_employers,
        "min_ranges": min_ranges,
        "default_country": POSTED_DEFAULT_COUNTRY if POSTED_DEFAULT_COUNTRY in codes else (codes[0] if codes else None),
        "countries": countries,
        "excluded": excluded,
    }


# --- pay transparency: the disclosure RATE and its longitudinal grain ---------
#
# `build_posted_pay` above answers "what did employers print?". These answer
# "how many of them printed anything?" — a different question with a different
# denominator, and the one field nothing aggregated. Both builders take the same
# per-role row shape:
#
#     (company, level_band, structured_at, disclosed_base_min,
#      disclosed_base_max, disclosed_pay_basis)

# A band with no stated basis still counts as disclosed (the employer printed a
# range), but it cannot be pooled with base pay — park it with the other rows
# that can't sit on a base-pay axis.
DISCLOSED_BASIS_FALLBACK = "unclear"


def _disclosure_state(
    structured_at: object, base_min: object, base_max: object, pay_basis: object
) -> tuple[bool, str]:
    """`(checked, pay_basis)` for one open role; `pay_basis` is `''` if it stated nothing.

    `pay_disclosure.disclosure_known`, the reading the detail and the
    `discloses_pay` filter share: a stored band discloses whoever
    wrote it, and a role with no band counts only once the text pass has read
    it. An unread role with no band contributes to neither side of the rate:
    absence of a band is not evidence the employer stated nothing, and
    counting it as a non-discloser would make the rate track extraction
    backlog instead of employer behaviour.
    """
    checked = disclosure_known(structured_at, base_min, base_max)
    if band_stated(base_min, base_max):
        return True, (str(pay_basis) if pay_basis else DISCLOSED_BASIS_FALLBACK)
    return checked, ""


def _rate(disclosed: int, checked: int) -> float | None:
    """Disclosure share, or None when nothing in the group has been checked yet."""
    return round(disclosed / checked, 4) if checked else None


def build_disclosure_rates(
    rows: Sequence[tuple],
    *,
    company_limit: int = 15,
) -> dict:
    """Share of open roles whose posting states a pay band, overall / per company / per level.

    `level_band` in each row is the level key (`db.queries.scope.level_key_expr`): roles
    whose level we cannot place are one `unstated` row, listed last.

    Basis-independent by construction: a posted range counts the same whether it
    is base, total or unclear — the question is whether the employer said
    anything, not what they said. (Band *values* are basis-scoped and handled by
    `build_posted_pay` and the snapshot below.)

    Each row is `(company, level_band, structured_at, base_min, base_max,
    pay_basis)`; the snapshot's rows carry two more columns after these, which
    the rate does not read.

    The denominator is `checked`, not `open`: `open - checked` roles are still
    queued for the disclosure pass, so folding them in would report extraction
    progress as employer silence. Both counts are returned so the UI can state the
    backlog rather than hide it. A group with `checked == 0` keeps `rate: None`:
    no rate is honest there, and 0.0 would be a lie.

    `by_company` keeps the `company_limit` employers with the most checked
    roles, most first.
    """
    overall = {"open": 0, "checked": 0, "disclosed": 0}
    by_company: dict[str, dict] = {}
    by_level: dict[str, dict] = {}

    for company, level_band, structured_at, lo, hi, basis, *_ in rows:
        checked, cell_basis = _disclosure_state(structured_at, lo, hi, basis)
        for bucket in (
            overall,
            by_company.setdefault(company, {"open": 0, "checked": 0, "disclosed": 0}),
            by_level.setdefault(level_band or "", {"open": 0, "checked": 0, "disclosed": 0}),
        ):
            bucket["open"] += 1
            bucket["checked"] += int(checked)
            bucket["disclosed"] += int(bool(cell_basis))

    def _largest(entries: list[dict]) -> list[dict]:
        # The employers most checked roles are at, whatever they post. Cut by
        # rate instead, the limit keeps only employers that all post a range
        # (or, lowest first, all post none), since many sit at each end. The
        # name breaks a tie, so the limit cuts the same employers on every
        # read of one table.
        return sorted(entries, key=lambda d: (-d["checked"], d["company"]))

    companies = _largest(
        [{"company": c, **v, "rate": _rate(v["disclosed"], v["checked"])} for c, v in by_company.items()]
    )[:company_limit]
    levels = [
        {"level_band": lb, **v, "rate": _rate(v["disclosed"], v["checked"])}
        for lb, v in sorted(by_level.items(), key=lambda kv: level_order(kv[0]))
    ]

    return {
        "overall": {**overall, "rate": _rate(overall["disclosed"], overall["checked"])},
        "by_company": companies,
        "by_level": levels,
    }


def build_disclosure_snapshot_rows(rows: Sequence[tuple]) -> list[dict]:
    """Collapse open roles into the daily `disclosure_snapshot` grain.

    One entry per `(company, level_band, pay_basis)` carrying `roles`, `checked`
    and the *distinct* bands in that cell as `{low, high, reqs}`. Roles that
    stated nothing land under `pay_basis == ""`, so the open count is the sum over
    every basis and the disclosed count is the sum over the non-empty ones.

    Each row is the rate's six columns followed by the band's currency and
    period. Band values (not the rate) are yearly US-dollar base pay, as the
    trend draws them on that axis: a band in another currency
    or period (`pay_period.not_yearly_usd`) still counts as disclosed and adds
    no band entry, and so does one under the plausibility floor. Anthropic's
    literal `Annual Salary: $1—$2 USD` is a real disclosure, so it belongs in
    the rate, but it is not a salary, so it must never enter a band percentile.
    A one-sided band (only a min, or only a max) counts as disclosed and
    contributes no band entry, since it spans nothing.
    """
    cells: dict[tuple[str, str, str], dict] = {}

    for company, level_band, structured_at, lo, hi, basis, currency, period in rows:
        if company is None:
            continue
        checked, cell_basis = _disclosure_state(structured_at, lo, hi, basis)
        cell = cells.setdefault(
            (company, level_band or "", cell_basis),
            {"roles": 0, "checked": 0, "bands": {}},
        )
        cell["roles"] += 1
        cell["checked"] += int(checked)
        if cell_basis and lo is not None and hi is not None and not not_yearly_usd(lo, hi, currency, period):
            lo, hi = int(lo), int(hi)
            if lo >= DISCLOSED_FLOOR and hi >= lo:
                cell["bands"][(lo, hi)] = cell["bands"].get((lo, hi), 0) + 1

    return [
        {
            "company": company,
            "level_band": level_band,
            "pay_basis": pay_basis,
            "roles": cell["roles"],
            "checked": cell["checked"],
            "bands": [
                {"low": lo, "high": hi, "reqs": reqs}
                for (lo, hi), reqs in sorted(cell["bands"].items())
            ],
        }
        for (company, level_band, pay_basis), cell in cells.items()
    ]

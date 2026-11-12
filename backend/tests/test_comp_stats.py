"""Pure-logic tests for compensation aggregation (no DB).

Pins the percentile math, the posted-pay rules and the ordering and coverage
rules behind the Statistics "Compensation" sub-tab.
"""

from __future__ import annotations

from tracker.analytics.comp_stats import (
    COMP_MIN_ROLES,
    POSTED_MIN_EMPLOYERS,
    POSTED_MIN_RANGES,
    _percentile,
    build_comp_stats,
    build_posted_pay,
)


def test_percentile_linear_interpolation_matches_percentile_cont():
    vals = [300_000, 600_000, 800_000, 1_000_000]  # sorted
    # p50 interpolates the two middle values, like Postgres percentile_cont.
    assert _percentile(vals, 0.50) == 700_000
    assert _percentile(vals, 0.25) == 525_000  # 0.75 between 300k and 600k
    assert _percentile(vals, 0.0) == 300_000
    assert _percentile(vals, 1.0) == 1_000_000
    assert _percentile([], 0.5) is None
    assert _percentile([420_000], 0.9) == 420_000


def _fixture():
    # (company, level_band, family, comp_median); one null-comp row.
    return [
        ("google", "staff", "swe", 600_000),
        ("google", "senior", "swe", 300_000),
        ("openai", "principal", "ml_ai_research", 1_000_000),  # out of level order on purpose
        ("openai", "staff", "ml_ai_research", 800_000),
        ("meta", "senior", "pm", None),  # counted in coverage, excluded from math
    ]


def test_coverage_counts_all_open_but_excludes_null_comp():
    s = build_comp_stats(_fixture(), total_open=5)
    assert s["coverage"] == {"with_comp": 4, "total_open": 5, "pct": 0.8}
    assert s["overall"]["p50"] == 700_000
    assert s["overall"]["min"] == 300_000 and s["overall"]["max"] == 1_000_000


def test_by_level_is_ordered_by_seniority_not_input_order():
    s = build_comp_stats(_fixture(), total_open=5, min_roles=1)
    assert [x["level_band"] for x in s["by_level"]] == ["senior", "staff", "principal"]
    staff = next(x for x in s["by_level"] if x["level_band"] == "staff")
    assert staff["count"] == 2 and staff["p50"] == 700_000  # 600k & 800k


def test_by_company_and_family_ranked_by_median_desc():
    s = build_comp_stats(_fixture(), total_open=5, min_roles=1)
    assert [x["company"] for x in s["by_company"]] == ["openai", "google"]
    # pm only had a null-comp row, so it must not appear as a family group.
    fams = [x["family"] for x in s["by_family"]]
    assert fams == ["ml_ai_research", "swe"]
    assert "pm" not in fams


def test_a_group_below_the_minimum_is_not_listed_and_the_minimum_is_stated():
    # One Operations role priced at $1.1M must not top "pay by discipline".
    rows = [("apple", "staff", "pm", 500_000)] * 5 + [("openai", "staff", "ops", 1_100_000)]
    s = build_comp_stats(rows, total_open=6)
    assert s["min_roles"] == COMP_MIN_ROLES == 5
    assert [f["family"] for f in s["by_family"]] == ["pm"]
    assert [c["company"] for c in s["by_company"]] == ["apple"]
    assert [lv["count"] for lv in s["by_level"]] == [6]
    # The whole still counts every role: the gate is on groups, not the market.
    assert s["overall"]["count"] == 6 and s["overall"]["max"] == 1_100_000


def test_empty_input_yields_null_overall():
    s = build_comp_stats([], total_open=0)
    assert s["overall"] is None
    assert s["by_level"] == [] and s["by_company"] == []
    assert s["coverage"]["pct"] == 0.0


# --- Posted base pay ----------------------------------------------------------
# An employer posts one range per level and place and hangs many roles off it,
# so the unit is the distinct range. A figure is one country and one currency.

US = ["silicon_valley"]


def _posted(company="google", level="staff", lo=240_000, hi=334_000, *, basis="base", currency="USD",
            period="year", places=US, level_basis="company"):
    return (company, level, level_basis, lo, hi, basis, currency, period, places)


def _country(out, code="US"):
    return next(c for c in out["countries"] if c["country"] == code)


def _market(level="principal", employers=POSTED_MIN_EMPLOYERS, per=2, start=200_000):
    """`employers` employers, each posting `per` distinct ranges at `level`."""
    return [
        _posted(f"co{e}", level, start + 10_000 * (e * per + r), start + 80_000 + 10_000 * (e * per + r))
        for e in range(employers)
        for r in range(per)
    ]


def test_one_range_on_many_roles_votes_once():
    out = build_posted_pay([_posted()] * 20)
    [staff] = _country(out)["levels"]
    assert (staff["ranges"], staff["employers"], staff["roles"]) == (1, 1, 20)
    assert _country(out)["bands"] == [
        {"company": "google", "level_band": "staff", "low": 240_000, "high": 334_000, "reqs": 20},
    ]


def test_a_range_many_roles_share_weighs_no_more_in_the_figure():
    # The lowest range carries 30 roles. Weighted by role it would pull the
    # median low and high down to its own; one vote per range leaves the
    # figure where the ten ranges put it.
    rows = _market(per=2)
    rows += [rows[0]] * 29
    [principal] = _country(build_posted_pay(rows))["levels"]
    assert (principal["ranges"], principal["roles"]) == (10, 39)
    assert (principal["low"], principal["high"]) == (245_000, 325_000)
    assert (principal["mid_p25"], principal["mid_p75"]) == (262_500, 307_500)


def test_a_level_shows_the_median_low_to_the_median_high_and_the_middle_half_of_midpoints():
    rows = _market(per=2)  # 5 employers, 10 ranges: 200K-280K up to 290K-370K
    [principal] = _country(build_posted_pay(rows))["levels"]
    assert principal["enough"] is True
    assert (principal["low"], principal["high"]) == (245_000, 325_000)
    # Midpoints 240K to 330K in steps of 10K: the middle half runs 262.5K to 307.5K.
    assert (principal["mid_p25"], principal["mid_p75"]) == (262_500, 307_500)


def test_a_level_below_either_minimum_is_counted_and_shows_no_figure():
    four_employers = _market(employers=POSTED_MIN_EMPLOYERS - 1, per=3)  # 12 ranges, 4 employers
    seven_ranges = _market(employers=7, per=1)  # 7 employers, 7 ranges
    for rows, counts in ((four_employers, (12, 4)), (seven_ranges, (7, 7))):
        [level] = _country(build_posted_pay(rows))["levels"]
        assert (level["ranges"], level["employers"]) == counts
        assert (level["enough"], level["low"], level["high"], level["mid_p25"]) == (False, None, None, None)
    assert (POSTED_MIN_EMPLOYERS, POSTED_MIN_RANGES) == (5, 8)


def test_a_country_reads_its_own_currency_and_never_converts():
    """A pound range is the UK's, in pounds; it never lands on the dollar axis,
    and a dollar range posted for a UK role is counted apart, not converted."""
    out = build_posted_pay([
        _posted(),
        _posted("monzo", lo=90_000, hi=120_000, currency="GBP", places=["london"]),
        _posted("wise", lo=95_000, hi=130_000, currency="GBP", places=["london"]),
        _posted("stripe", lo=200_000, hi=260_000, currency="USD", places=["london"]),
        _posted("figma", lo=180_000, hi=240_000, currency=None),  # no currency stored: dollars
    ])
    us, gb = _country(out), _country(out, "GB")
    assert (us["currency"], [b["company"] for b in us["bands"]]) == ("USD", ["google", "figma"])
    assert (gb["currency"], sorted(b["company"] for b in gb["bands"]), gb["other_currency"]) == (
        "GBP", ["monzo", "wise"], 1,
    )


def test_a_yearly_range_in_forints_is_hungary_s_and_never_a_placeholder():
    out = build_posted_pay([
        _posted("acme", "senior", 14_000_000, 20_000_000, currency="HUF", places=["hungary"]),
        _posted("acme", "senior", 900_000, 1_300_000, currency="HUF", period="month", places=["hungary"]),
    ])
    hu = _country(out, "HU")
    assert (hu["currency"], [(b["low"], b["high"]) for b in hu["bands"]]) == ("HUF", [(14_000_000, 20_000_000)])
    assert (out["excluded"]["implausible"], out["excluded"]["not_yearly"]) == (0, 1)


def test_a_country_reads_the_currency_of_its_ranges_at_a_placed_level():
    """Nine pound ranges at no placed level never outvote eight dollar ranges
    at a level: the figure is in dollars, and the pound roles are counted apart."""
    rows = [_posted(f"us{i}", "senior", 200_000 + i * 1_000, 260_000 + i * 1_000) for i in range(8)]
    rows += [_posted(f"uk{i}", None, 90_000 + i * 1_000, 120_000 + i * 1_000, currency="GBP") for i in range(9)]
    us = _country(build_posted_pay(rows))
    assert (us["currency"], us["ranges"], us["other_currency"]) == ("USD", 8, 9)
    assert [level["level_band"] for level in us["levels"]] == ["senior"]


def test_one_range_posted_at_two_levels_counts_at_each_when_choosing_the_currency():
    """Five pound employers posting the same two ranges at both Senior and Staff
    hold twenty placed ranges, as the levels count them, and outvote eleven
    dollar ranges: the figure is in pounds at both levels."""
    rows = [
        _posted(f"uk{e}", level, 90_000 + r * 10_000, 120_000 + r * 10_000, currency="GBP")
        for e in range(5) for r in range(2) for level in ("senior", "staff")
    ]
    rows += [_posted(f"us{i}", "senior", 200_000 + i * 1_000, 260_000 + i * 1_000) for i in range(11)]
    uk = _country(build_posted_pay(rows))
    assert (uk["currency"], uk["ranges"], uk["other_currency"]) == ("GBP", 20, 11)
    assert {level["level_band"]: level["enough"] for level in uk["levels"]} == {"senior": True, "staff": True}


def test_hourly_monthly_and_contradicted_periods_are_counted_never_annualised():
    out = build_posted_pay([
        _posted("intern", lo=60, hi=90, period="hour"),
        _posted("contract", lo=12_000, hi=15_000, period="month"),
        _posted("typo", lo=600_000, hi=700_000, period="hour"),
        _posted("nodate", lo=200_000, hi=260_000, period=None),
        _posted(),
    ])
    assert sorted(b["company"] for b in _country(out)["bands"]) == ["google", "nodate"]
    assert out["excluded"]["not_yearly"] == 3


def test_what_is_not_base_or_not_salary_is_counted_under_its_reason():
    out = build_posted_pay([
        _posted(),
        _posted("netflix", lo=440_000, hi=725_000, basis="total"),
        _posted("openai", lo=300_000, hi=500_000, basis="unclear"),
        _posted("anthropic", lo=1, hi=2),  # a literal "$1-$2" placeholder
    ])
    assert [b["company"] for b in _country(out)["bands"]] == ["google"]
    assert out["excluded"] == {
        "not_base": 2, "not_yearly": 0, "implausible": 1, "no_country": 0, "placed_by_pay": 0, "without_country": 0,
    }


def test_an_entry_range_under_fifty_thousand_dollars_is_real_pay_in_and_outside_the_us():
    """$45K to $65K a year is an ordinary entry salary, in the US and for a
    dollar range posted elsewhere; only an amount that is no salary at any
    size is a placeholder."""
    out = build_posted_pay([
        _posted("acme", "entry", 45_000, 65_000),
        _posted("globex", "entry", 38_000, 52_000, places=["mexico"]),
        _posted("anthropic", lo=1, hi=2),
    ])
    assert [(b["company"], b["low"], b["high"]) for b in _country(out)["bands"]] == [("acme", 45_000, 65_000)]
    assert [(b["company"], b["low"]) for b in _country(out, "MX")["bands"]] == [("globex", 38_000)]
    assert out["excluded"]["implausible"] == 1


def test_a_role_in_several_countries_or_none_counts_for_no_country():
    out = build_posted_pay([_posted(), _posted("acme", places=[*US, "london"]), _posted("remote", places=[])])
    assert [c["country"] for c in out["countries"]] == ["US"]
    assert out["excluded"]["no_country"] == 2


def test_each_country_counts_only_its_own_roles_left_out():
    """A note under the UK's heading counts the UK's roles; the roles in no
    one country are counted only across all countries."""
    out = build_posted_pay([
        _posted(),
        _posted("netflix", lo=440_000, hi=725_000, basis="total"),
        _posted("intern", lo=60, hi=90, period="hour"),
        _posted("monzo", lo=90_000, hi=120_000, currency="GBP", places=["london"]),
        _posted("wise", lo=4_000, hi=6_000, currency="GBP", period="month", places=["london"]),
        _posted("acme", basis="total", places=[*US, "london"]),
        _posted("remote", places=[]),
    ], your_countries={"SE"})
    zero = {"not_base": 0, "not_yearly": 0, "implausible": 0, "placed_by_pay": 0}
    assert _country(out)["excluded"] == {**zero, "not_base": 1, "not_yearly": 1}
    assert _country(out, "GB")["excluded"] == {**zero, "not_yearly": 1}
    assert _country(out, "SE")["excluded"] == zero
    # The total-pay role in two countries keeps its reason, and is one of
    # the two roles no country's own counts hold.
    assert out["excluded"] == {
        "not_base": 2, "not_yearly": 2, "implausible": 0, "no_country": 1, "placed_by_pay": 0, "without_country": 2,
    }


def test_a_level_read_from_the_range_is_left_out_and_an_unplaced_level_is_counted_apart():
    out = build_posted_pay([
        _posted(),
        _posted("microsoft", level="principal", level_basis="pay_grade"),
        _posted("apple", level="unstated", lo=150_000, hi=200_000),
        _posted("apple", level="unstated", lo=150_000, hi=200_000),
    ])
    us = _country(out)
    assert [lv["level_band"] for lv in us["levels"]] == ["staff"]
    assert us["not_placed"] == {"roles": 2, "ranges": 1}
    assert all(b["level_band"] != "unstated" for b in us["bands"])
    assert out["excluded"]["placed_by_pay"] == 1


def test_every_range_is_kept_however_many_and_one_role_ranges_too():
    rows = [_posted(f"co{i}", lo=200_000 + i * 100, hi=300_000 + i * 100) for i in range(250)]
    rows += [_posted("busy", lo=500_000, hi=600_000)] * 40
    us = _country(build_posted_pay(rows))
    assert us["ranges"] == len(us["bands"]) == 251
    assert sum(b["reqs"] == 1 for b in us["bands"]) == 250


def test_ranges_list_by_seniority_then_pay_however_rows_arrive():
    rows = [
        _posted(level="principal", lo=262_000, hi=365_000),
        _posted(level="senior", lo=174_000, hi=253_000),
        _posted(level="staff", lo=219_000, hi=306_000),
        _posted(level="staff", lo=262_000, hi=365_000),
        _posted(level="staff", lo=250_000, hi=365_000),
    ]
    forward = _country(build_posted_pay(rows))["bands"]
    assert forward == _country(build_posted_pay(list(reversed(rows))))["bands"]
    assert [(b["level_band"], b["low"]) for b in forward] == [
        ("senior", 174_000), ("staff", 250_000), ("staff", 262_000), ("staff", 219_000), ("principal", 262_000),
    ]
    assert [lv["level_band"] for lv in _country(build_posted_pay(rows))["levels"]] == ["senior", "staff", "principal"]


def test_the_persons_countries_are_listed_even_with_no_range_and_the_us_leads():
    out = build_posted_pay(
        [_posted("monzo", lo=90_000, hi=120_000, currency="GBP", places=["london"])] * 3 + [_posted()],
        your_countries={"SE", "GB"},
    )
    assert [(c["country"], c["ranges"], c["yours"]) for c in out["countries"]] == [
        ("GB", 1, True), ("US", 1, False), ("SE", 0, True),
    ]
    assert _country(out, "SE")["currency"] is None
    assert out["default_country"] == "US"
    assert build_posted_pay([], your_countries={"SE"})["default_country"] == "SE"
    assert build_posted_pay([])["default_country"] is None


# --- order of input never orders the output --------------------------------- #
# Tied family medians and tied company-level bands must not retain input
# order: explicit tiebreakers keep equivalent reads deterministic.


def test_families_whose_median_ties_list_in_the_same_order_however_rows_arrive():
    rows = [("acme", "senior", fam, 300_000) for fam in ("data_science", "infrastructure_sre") for _ in range(5)]
    forward = build_comp_stats(rows, total_open=10)["by_family"]
    backward = build_comp_stats(list(reversed(rows)), total_open=10)["by_family"]
    assert [d["family"] for d in forward] == [d["family"] for d in backward] == ["data_science", "infrastructure_sre"]

"""The Compensation tab's company table and its pay by discipline, as pure builders."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tracker.analytics.pay_table import (
    DISCIPLINE_MAX_EMPLOYER_SHARE,
    NONE,
    PLACED_BY_PAY,
    SEED_PROVIDER,
    SEVERAL_COUNTRIES,
    TOTAL,
    UNCLEAR,
    UNREAD,
    EstimateRole,
    TableRole,
    build_pay_by_discipline,
    build_pay_table,
)
from tracker.levels import UNSTATED_LEVEL
from tracker.levels import pay as level_pay
from tracker.levels.model import STATED_BY_EMPLOYER, PayPolicy
from tracker.schema import LevelBasis

READ = datetime(2026, 11, 10, tzinfo=UTC)
US = ("united_states", "north_america")
US_AND_CANADA = ("united_states", "canada", "north_america")
UK = ("uk", "europe")


def role(company: str, low: float | None = None, high: float | None = None, **changes) -> TableRole:
    """A US Principal role, read by the disclosure pass, posting a yearly
    dollar base range when `low` and `high` are given."""
    fields = {
        "company": company,
        "family": "product_management",
        "level": "principal",
        "level_basis": "title",
        "places": US,
        "structured_at": READ,
        "base_min": low,
        "base_max": high,
        "pay_basis": "base" if low is not None else None,
        "currency": "USD" if low is not None else None,
        "period": "year" if low is not None else None,
    }
    fields.update(changes)
    return TableRole(**fields)


def estimate(company: str, base: int | None = None, total: int | None = None, *,
             family: str | None = "product_management", provider: str | None = "builtin") -> EstimateRole:
    """One role's stored estimate, as the posting that prices it carries it."""
    return EstimateRole(company=company, family=family, base=base, total=total, provider=provider)


def table(roles, **changes) -> dict:
    options = {"country": "US", "currency": "USD", "level": "principal"}
    options.update(changes)
    return build_pay_table(roles, **options)


def rows_by_company(out: dict) -> dict[str, dict]:
    return {row["company"]: row for row in out["rows"]}


def test_a_company_reads_the_median_low_to_the_median_high_of_its_distinct_ranges():
    # One range on three roles votes once: weighted by role, the low would be 200K.
    out = table([
        *[role("amazon", 200_000, 280_000)] * 3,
        role("amazon", 220_000, 300_000),
        role("amazon", 260_000, 340_000),
    ])
    [amazon] = out["rows"]
    assert (amazon["low"], amazon["high"]) == (220_000, 300_000)
    assert amazon["ranges"] == [
        {"low": 260_000, "high": 340_000, "roles": 1},
        {"low": 220_000, "high": 300_000, "roles": 1},
        {"low": 200_000, "high": 280_000, "roles": 3},
    ]
    assert (amazon["open_roles"], amazon["posting"], amazon["currency"]) == (5, 5, "USD")


def test_rows_sort_by_the_middle_of_the_posted_range_never_its_top():
    # One wide national range reaches higher, but its middle sits lower than a
    # narrow range's: sorted by the top, width alone would rank it first.
    out = table([role("microsoft", 142_800, 274_800), role("adyen", 220_000, 260_000)])
    assert [r["company"] for r in out["rows"]] == ["adyen", "microsoft"]


def test_an_estimate_never_fills_the_posted_cell_nor_sorts_among_posted_pay():
    out = table(
        [role("okta", 150_000, 170_000), role("servicenow")],
        estimates=[estimate("okta", base=144_000), estimate("servicenow", base=900_000)],
    )
    assert [r["company"] for r in out["rows"]] == ["okta", "servicenow"]
    servicenow = rows_by_company(out)["servicenow"]
    assert (servicenow["low"], servicenow["high"], servicenow["ranges"], servicenow["reason"]) == (None, None, [], NONE)
    assert servicenow["estimate_base"] == {"low": 900_000, "high": 900_000, "families": ["product_management"]}
    # The posted row keeps its estimate too, for the advanced view; the cell is still the range.
    okta = rows_by_company(out)["okta"]
    assert (okta["low"], okta["estimate_base"]["low"]) == (150_000, 144_000)


def test_companies_with_no_range_follow_by_open_roles_then_name():
    out = table([
        role("zscaler", 200_000, 260_000),
        role("anduril"), role("anduril"),
        role("cloudflare"), role("cloudflare"),
        role("arm"),
    ])
    assert [r["company"] for r in out["rows"]] == ["zscaler", "anduril", "cloudflare", "arm"]


def test_estimates_are_read_for_us_pay_only():
    roles = [role("deepmind", 90_000, 130_000, places=UK, currency="GBP")]
    out = table(roles, country="GB", currency="GBP",
                estimates=[estimate("deepmind", base=200_000, total=400_000)])
    [deepmind] = out["rows"]
    assert out["estimates"] is False
    assert (deepmind["estimate_base"], deepmind["estimate_total"]) == (None, None)
    assert (deepmind["low"], deepmind["currency"]) == (90_000, "GBP")


def test_a_role_listed_in_two_countries_joins_the_table_but_its_range_is_no_one_countrys():
    # A "US or Canada" role is hiring in the US, so GitLab has a row; its range
    # may be Canada's, so the cell says why it holds none.
    out = table([role("gitlab", 203_200, 304_800, places=US_AND_CANADA)])
    [gitlab] = out["rows"]
    assert (gitlab["open_roles"], gitlab["low"], gitlab["reason"]) == (1, None, SEVERAL_COUNTRIES)

    # The same company's US-only role still shows its range.
    out = table([role("gitlab", 203_200, 304_800, places=US_AND_CANADA), role("gitlab", 210_000, 290_000)])
    [gitlab] = out["rows"]
    assert (gitlab["low"], gitlab["high"], gitlab["posting"], gitlab["open_roles"]) == (210_000, 290_000, 1, 2)


@pytest.mark.parametrize(("pay_basis", "reason"), [("total", TOTAL), ("unclear", UNCLEAR), (None, UNCLEAR)])
def test_a_range_that_is_not_base_names_why_the_cell_is_empty(pay_basis, reason):
    [netflix] = table([role("netflix", 400_000, 900_000, pay_basis=pay_basis)])["rows"]
    assert (netflix["low"], netflix["reason"]) == (None, reason)


def test_a_level_read_from_its_own_range_never_enters_the_cell():
    [snap] = table([role("snap", 250_000, 300_000, level_basis=LevelBasis.PAY_GRADE.value)])["rows"]
    assert (snap["low"], snap["reason"]) == (None, PLACED_BY_PAY)

    [snap] = table([
        role("snap", 250_000, 300_000, level_basis=LevelBasis.PAY_GRADE.value),
        role("snap", 200_000, 240_000),
    ])["rows"]
    assert (snap["low"], snap["high"], snap["posting"]) == (200_000, 240_000, 1)


def test_the_share_posting_counts_checked_roles_only():
    [datadog] = table([
        role("datadog", 200_000, 260_000),
        role("datadog", 200_000, 260_000),
        role("datadog"),  # read, no range
        role("datadog", structured_at=None),  # not read yet: neither side of the count
    ])["rows"]
    assert (datadog["posting"], datadog["checked"], datadog["open_roles"]) == (2, 3, 4)

    # Nothing read yet is not an employer who posts nothing.
    [arm] = table([role("arm", structured_at=None)])["rows"]
    assert (arm["reason"], arm["checked"]) == (UNREAD, 0)
    [arm] = table([role("arm")])["rows"]
    assert arm["reason"] == NONE


def test_a_range_in_another_currency_shows_in_its_own_currency_after_the_rest():
    out = table([
        role("shopify", 300_000, 400_000, currency="CAD"),
        role("adyen", 150_000, 180_000),
    ])
    assert [r["company"] for r in out["rows"]] == ["adyen", "shopify"]
    shopify = rows_by_company(out)["shopify"]
    assert (shopify["currency"], shopify["other_currency"], shopify["low"]) == ("CAD", True, 300_000)


def test_a_company_with_several_disciplines_shows_the_span_of_its_estimates_never_their_average():
    [qualcomm] = table(
        [role("qualcomm", family="engineering_management"), role("qualcomm")],
        estimates=[estimate("qualcomm", base=379_000, family="engineering_management"),
                   estimate("qualcomm", base=232_000)],
    )["rows"]
    assert qualcomm["estimate_base"] == {
        "low": 232_000, "high": 379_000, "families": ["engineering_management", "product_management"],
    }


def test_the_rung_is_named_for_a_seed_total_only():
    def rung(company: str, level: str) -> str:
        return f"{company} {level} rung"

    [anthropic] = table([role("anthropic")], rung=rung,
                        estimates=[estimate("anthropic", total=1_500_000, provider=SEED_PROVIDER)])["rows"]
    assert anthropic["estimate_total"] == {"low": 1_500_000, "high": 1_500_000, "rung": "anthropic principal rung"}

    # A plugin's total reads no rung we know, and a base estimate pools a whole level.
    [okta] = table([role("okta")], rung=rung,
                   estimates=[estimate("okta", base=250_000, total=400_000, provider="a-plugin")])["rows"]
    assert okta["estimate_total"]["rung"] is None
    assert "rung" not in okta["estimate_base"]


def test_an_estimate_is_read_only_for_a_company_the_table_lists_and_a_picked_discipline():
    # A company with no role at the level never gains a row from an estimate,
    # and the discipline filter narrows the estimate as it narrows the rows.
    out = table(
        [role("stripe", 200_000, 300_000), role("stripe", family="software_engineering")],
        families=["product_management"],
        estimates=[estimate("stripe", base=250_000), estimate("stripe", base=900_000, family="software_engineering"),
                   estimate("ramp", base=400_000)],
    )
    [stripe] = out["rows"]
    assert stripe["estimate_base"] == {"low": 250_000, "high": 250_000, "families": ["product_management"]}


def test_the_skill_filter_narrows_the_rows_and_the_pay_they_show():
    python = frozenset({"python"})
    out = table(
        [
            *[role("stripe", 200_000, 300_000, skills=python | {"sql"})] * 3,
            role("stripe", 400_000, 500_000),
            role("ramp", 250_000, 350_000, skills=frozenset({"sql"})),
        ],
        skill="python",
    )
    [stripe] = out["rows"]
    assert (stripe["open_roles"], stripe["low"], stripe["high"]) == (3, 200_000, 300_000)
    # Offered skills count the table's roles before the skill narrows them.
    assert out["skills"] == [{"term": "sql", "roles": 4}, {"term": "python", "roles": 3}]


def test_a_skill_named_by_fewer_than_three_roles_is_not_offered():
    out = table([role("stripe", skills=frozenset({"go"}))] * 2)
    assert out["skills"] == []


def test_the_discipline_filter_narrows_the_table_and_the_skills_offered():
    out = table(
        [
            role("stripe", 200_000, 300_000, family="software_engineering", skills=frozenset({"go"})),
            *[role("ramp", 250_000, 350_000, skills=frozenset({"figma"}))] * 3,
        ],
        families=["product_management"],
    )
    assert [r["company"] for r in out["rows"]] == ["ramp"]
    assert out["skills"] == [{"term": "figma", "roles": 3}]


def test_roles_with_no_placed_level_are_counted_per_company_never_as_a_row():
    out = table([
        role("apple", level=UNSTATED_LEVEL),
        role("apple", level=UNSTATED_LEVEL),
        role("stripe", 200_000, 300_000),
        role("stripe", level=UNSTATED_LEVEL),
        role("stripe", level="staff"),  # another level: neither a row nor unplaced
    ])
    assert [r["company"] for r in out["rows"]] == ["stripe"]
    assert out["rows"][0]["open_roles"] == 1
    assert out["not_placed"] == [{"company": "apple", "roles": 2}, {"company": "stripe", "roles": 1}]


def test_a_company_followed_as_part_of_a_set_is_marked():
    out = table([role("stripe"), role("acme")], followed_as_set=frozenset({"acme"}))
    assert {r["company"]: r["followed_as_set"] for r in out["rows"]} == {"stripe": False, "acme": True}


def _policies(monkeypatch, *policies: PayPolicy) -> None:
    monkeypatch.setattr(level_pay, "PAY_POLICIES", {p.company: p for p in policies})


def test_equity_shows_only_what_the_company_itself_states(monkeypatch):
    _policies(
        monkeypatch,
        PayPolicy("tsmc", equity_rule="none"),
        PayPolicy("two-sigma", equity_rule="none", estimated=("equity_rule",)),
        PayPolicy("amazon", equity_rule="dollar_grant_by_level", vesting="5/15/40/40", estimated=("vesting",)),
        PayPolicy("microsoft", equity_rule="dollar_grant_by_level", vesting="25/25/25/25"),
        PayPolicy("netflix", equity_rule="employee_election", equity_vehicle="cash_election"),
        PayPolicy("adyen", equity_vehicle="rsu"),
    )
    stated = {c: level_pay.stated_equity(c) for c in ("tsmc", "two-sigma", "amazon", "microsoft", "netflix", "adyen", "acme")}
    assert stated == {
        "tsmc": {"vehicle": None, "vesting": None, "rule": "none"},
        # An estimated rule, or an estimated schedule, is no stated fact.
        "two-sigma": None,
        "amazon": None,
        # A rule that sizes the grant names nothing a reader acts on; the stated schedule shows.
        "microsoft": {"vehicle": None, "vesting": "25/25/25/25", "rule": None},
        "netflix": {"vehicle": "cash_election", "vesting": None, "rule": "employee_election"},
        "adyen": {"vehicle": "rsu", "vesting": None, "rule": None},
        "acme": None,
    }
    assert PayPolicy("x").stated_by("vesting") == STATED_BY_EMPLOYER

    [tsmc] = table([role("tsmc")], equity=level_pay.stated_equity)["rows"]
    assert tsmc["equity"] == {"vehicle": None, "vesting": None, "rule": "none"}


def market(family: str, employers: int, per: int, start: int = 200_000, **changes) -> list[TableRole]:
    """`employers` companies posting `per` distinct ranges each, 10K apart."""
    return [
        role(f"{family}-co{e}", start + 10_000 * (e * per + i), start + 80_000 + 10_000 * (e * per + i), family=family, **changes)
        for e in range(employers)
        for i in range(per)
    ]


def disciplines(roles, **changes) -> dict[str, dict]:
    options = {"country": "US", "currency": "USD", "level": "principal"}
    options.update(changes)
    return {d["family"]: d for d in build_pay_by_discipline(roles, **options)["disciplines"]}


def test_a_discipline_shows_its_typical_range_once_enough_employers_post_it():
    out = disciplines(market("product_management", employers=5, per=2))
    pm = out["product_management"]
    assert (pm["withheld"], pm["ranges"], pm["employers"]) == (None, 10, 5)
    assert (pm["low"], pm["high"]) == (245_000, 325_000)


def test_a_discipline_below_the_minimums_is_withheld_with_its_counts():
    out = disciplines(market("data_science", employers=4, per=3))
    ds = out["data_science"]
    assert (ds["withheld"], ds["low"], ds["ranges"], ds["employers"]) == ("too_few", None, 12, 4)


def test_a_discipline_one_employer_fills_is_withheld():
    # 5 employers and 10 ranges pass the minimums, but one posts 6 of the 10.
    roles = market("engineering_management", employers=4, per=1) + [
        role("amazon", 200_000 + 5_000 * i, 280_000 + 5_000 * i, family="engineering_management") for i in range(6)
    ]
    em = disciplines(roles)["engineering_management"]
    assert em["top_share"] == 0.6 > DISCIPLINE_MAX_EMPLOYER_SHARE
    assert (em["withheld"], em["low"], em["high"], em["ranges"]) == ("one_employer", None, None, 10)


def test_every_discipline_shows_with_the_picked_one_marked():
    roles = market("product_management", 5, 2) + market("program_management", 5, 2, start=150_000)
    out = build_pay_by_discipline(roles, country="US", currency="USD", level="principal", families=["program_management"])
    assert [(d["family"], d["picked"]) for d in out["disciplines"]] == [
        ("product_management", False), ("program_management", True),
    ]


def test_a_discipline_reads_one_level_and_one_country_only():
    roles = (
        market("product_management", 5, 2)
        + market("product_management", 5, 2, start=500_000, level="staff")
        + market("product_management", 5, 2, start=500_000, places=US_AND_CANADA)
    )
    pm = disciplines(roles)["product_management"]
    assert (pm["ranges"], pm["low"]) == (10, 245_000)

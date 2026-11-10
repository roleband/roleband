"""The Stock tab's companies, built from the packages Job detail shows.

Every role here goes through `comp_package.build_job_package`, the function Job
detail calls, with the atlas's real company rules: no package is hand-written,
so a rule the package and the tab disagree on fails here.
"""

from __future__ import annotations

import pytest

from tracker.analytics.comp_package import build_job_package
from tracker.analytics.comp_split import is_public, parent_ticker
from tracker.analytics.stock_trajectory import (
    FROM_COMPANY_RULE,
    FROM_ESTIMATED,
    FROM_MEASURED,
    FROM_MIXED,
    FROM_POSTED,
    TrajectoryRole,
    build_comp_trajectory,
)


def _posted(low: int, high: int, *, basis: str = "base", period: str = "year", bonus: float | None = None) -> dict:
    return {
        "disclosed": True, "base_min": low, "base_max": high, "currency": "USD", "pay_basis": basis,
        "pay_period": period, "bonus_pct": bonus, "snippet": None, "confidence": "high",
    }


def _role(company: str, band: str | None = "staff", *, median: int | None = None, posted: dict | None = None,
          base_estimate: int | None = None, baselines: dict | None = None, us_pay: bool = True,
          level_placed: bool = True, heuristic: bool = True, family: str = "software_engineering") -> TrajectoryRole:
    package = build_job_package(
        company=company, band=band, family=family,
        comp_low=round(median * 0.85) if median else None, comp_median=median,
        comp_high=round(median * 1.15) if median else None,
        comp_provenance="estimated median" if median else None,
        disclosed=posted if posted is not None else {"disclosed": False},
        baselines=baselines or {},
        base_estimate=(
            {"low": base_estimate, "median": base_estimate, "high": base_estimate, "provider": None, "as_of": None}
            if base_estimate else None
        ),
        heuristic=heuristic, us_pay=us_pay, covered=True, level_placed=level_placed,
    )
    return TrajectoryRole(company=company, band=band, package=package, us_pay=us_pay)


def _by_company(out: dict) -> dict[str, dict]:
    return {row["company"]: row for row in out["public"] + out["private"]}


class TestCompanyRules:
    def test_netflix_is_a_choice_row_with_no_split_and_no_price_move(self):
        out = build_comp_trajectory([
            _role("netflix", median=700_000),
            _role("netflix", posted=_posted(440_000, 725_000, basis="total")),
            _role("netflix", median=650_000, posted=_posted(440_000, 725_000, basis="unclear")),
        ])
        assert _by_company(out) == {}
        [netflix] = out["choice"]
        assert netflix == {
            "company": "netflix", "ticker": "NFLX", "count": 3,
            "median_tc": 650_000, "total_source": FROM_MIXED,
        }
        # No part of it can move with a price: there is no stock figure at all.
        assert not {"equity", "equity_pct", "bonus"} & set(netflix)
        assert out["overall"] is None
        assert out["set_apart"] == []

    @pytest.mark.parametrize("company", ["amazon", "openai", "anthropic"])
    def test_a_company_that_pays_no_bonus_shows_none(self, company):
        out = build_comp_trajectory([
            _role(company, median=600_000),
            _role(company, posted=_posted(200_000, 260_000)),
        ])
        row = _by_company(out)[company]
        assert row["bonus"] == 0
        assert row["sources"]["bonus"] == FROM_COMPANY_RULE
        assert row["base"] + row["equity"] == row["median_tc"]

    def test_a_company_with_a_bonus_rule_reads_it_not_a_flat_share(self):
        out = build_comp_trajectory([_role("microsoft", posted=_posted(200_000, 200_000))])
        row = _by_company(out)["microsoft"]
        assert row["sources"]["bonus"] == FROM_COMPANY_RULE
        # Microsoft's rule is 15% of base at this level, of the posted base.
        assert row["bonus"] == 30_000

    def test_the_vesting_the_company_states_rides_on_its_row(self):
        out = build_comp_trajectory([_role("amazon", median=600_000), _role("anthropic", median=900_000)])
        rows = _by_company(out)
        assert rows["amazon"]["vesting"] == "5/15/40/40"
        # Anthropic's schedule was searched for and not found: unknown, never a guess.
        assert rows["anthropic"]["vesting"] is None


class TestBase:
    def test_a_posted_range_reads_as_base(self):
        out = build_comp_trajectory([_role("microsoft", posted=_posted(180_000, 240_000))])
        row = _by_company(out)["microsoft"]
        assert row["base"] == 210_000
        assert row["sources"]["base"] == FROM_POSTED
        assert row["sources"]["equity"] == FROM_ESTIMATED

    def test_a_posted_base_with_no_estimated_total_still_counts(self):
        out = build_comp_trajectory([_role("google", posted=_posted(250_000, 320_000, bonus=0.15))])
        row = _by_company(out)["google"]
        assert row["count"] == 1
        assert row["sources"] == {"base": FROM_POSTED, "bonus": FROM_POSTED, "equity": FROM_ESTIMATED}
        assert row["bonus"] == round(285_000 * 0.15)

    def test_a_company_with_posted_and_estimated_roles_reads_mixed(self):
        out = build_comp_trajectory([
            _role("google", median=600_000),
            _role("google", posted=_posted(250_000, 320_000)),
        ])
        assert _by_company(out)["google"]["sources"]["base"] == FROM_MIXED


class TestEquity:
    def test_a_measured_grant_reads_measured(self):
        row_l6 = {"base_amount": 272_333, "stock_amount": 331_667, "bonus_amount": 58_614}
        out = build_comp_trajectory([_role(
            "google", posted=_posted(240_000, 334_000),
            baselines={("google", "software_engineering", "staff"): row_l6},
        )])
        row = _by_company(out)["google"]
        assert (row["sources"]["equity"], row["sources"]["bonus"]) == (FROM_MEASURED, FROM_MEASURED)
        # The grant is the measured one, never a multiple of the posted base.
        assert row["equity"] == pytest.approx(331_667, abs=1)

    def test_parts_add_up_and_overall_reads_listed_companies_only(self):
        out = build_comp_trajectory([
            _role("google", median=600_000),
            _role("google", "senior", median=400_000),
            _role("amazon", median=500_000),
            _role("openai", median=1_100_000),
        ])
        packages = [out["overall"], *out["public"], *out["private"]]
        assert all(p["base"] + p["bonus"] + p["equity"] == p["median_tc"] for p in packages)
        assert out["overall"]["count"] == 3
        assert [row["company"] for row in out["private"]] == ["openai"]
        assert not is_public("openai")


class TestSetApart:
    def test_roles_without_a_split_are_counted_apart_by_reason(self):
        out = build_comp_trajectory([
            _role("google", median=600_000, us_pay=False),
            _role("google", median=600_000, posted=_posted(250_000, 320_000), us_pay=False),
            _role("google", median=600_000, level_placed=False),
            _role("google", None, median=600_000),
            _role("google", posted=_posted(90, 120, period="hour")),
            _role("google", posted=_posted(300_000, 380_000, basis="total")),
            _role("google", posted=_posted(300_000, 380_000, basis="unclear")),
            _role("google", base_estimate=250_000),
            _role("google", median=600_000, heuristic=False),
        ])
        assert _by_company(out) == {}
        assert out["overall"] is None
        assert {r["reason"]: r["count"] for r in out["set_apart"]} == {
            "not_us_pay": 2, "level_unplaced": 2, "hourly": 1, "total_compensation": 1,
            "basis_unclear": 1, "base_only": 1, "plugin_without_split": 1,
        }

    def test_a_cash_election_role_with_a_base_and_no_total_is_counted_apart(self):
        out = build_comp_trajectory([
            _role("netflix", posted=_posted(300_000, 400_000)),
            _role("netflix", base_estimate=350_000),
        ])
        assert out["choice"] == []
        assert out["set_apart"] == [{"reason": "base_only", "count": 2}]

    def test_a_non_us_netflix_role_is_set_apart_not_a_choice_row(self):
        out = build_comp_trajectory([_role("netflix", median=700_000, us_pay=False)])
        assert out["choice"] == []
        assert out["set_apart"] == [{"reason": "not_us_pay", "count": 1}]

    def test_a_role_with_no_pay_figure_is_not_counted_anywhere(self):
        out = build_comp_trajectory([_role("stripe")])
        assert (out["public"], out["private"], out["choice"], out["set_apart"]) == ([], [], [], [])


class TestIdentity:
    def test_a_resolved_profile_makes_a_newly_listed_company_public(self):
        assert not is_public("databricks")
        out = build_comp_trajectory(
            [_role("databricks", median=650_000)],
            profiles={"databricks": {"is_public": True, "ticker": "DBX2", "equity_vehicle": "rsu"}},
        )
        assert [(e["company"], e["ticker"]) for e in out["public"]] == [("databricks", "DBX2")]

    def test_a_profile_can_mark_a_company_private_again(self):
        out = build_comp_trajectory(
            [_role("google", median=650_000)],
            profiles={"google": {"is_public": False, "ticker": None, "equity_vehicle": None}},
        )
        assert [e["company"] for e in out["private"]] == ["google"]

    def test_a_subsidiary_reprices_with_its_listed_parent(self):
        out = build_comp_trajectory(
            [_role("google-deepmind", median=772_000, family="ml_ai_research")],
            profiles={"google-deepmind": {"is_public": False, "ticker": None, "equity_vehicle": "options"}},
        )
        [row] = out["public"]
        assert (row["ticker"], row["equity_vehicle"]) == ("GOOGL", "rsu")
        assert row["equity"] > 0

    def test_a_subsidiary_with_its_own_equity_stays_private(self):
        assert parent_ticker("waymo") is None
        out = build_comp_trajectory(
            [_role("waymo", median=600_000)],
            profiles={"waymo": {"is_public": False, "ticker": None, "equity_vehicle": "options"}},
        )
        assert [e["company"] for e in out["private"]] == ["waymo"]

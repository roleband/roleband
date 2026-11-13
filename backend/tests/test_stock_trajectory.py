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
    build_offer_terms,
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

    def test_a_company_whose_rule_says_the_person_picks_the_mix_is_a_choice_row(self):
        """Spotify states the rule with no vehicle: its estimated total stands
        whole on a row of its own, as Netflix's does, never split by ours."""
        out = build_comp_trajectory([_role("spotify", median=600_000)])
        assert _by_company(out) == {}
        [spotify] = out["choice"]
        assert (spotify["company"], spotify["count"], spotify["median_tc"]) == ("spotify", 1, 600_000)
        assert not {"equity", "equity_pct", "bonus"} & set(spotify)

    def test_a_company_that_grants_no_equity_has_no_equity_part(self):
        [tsmc] = _by_company(build_comp_trajectory([_role("tsmc", posted=_posted(300_000, 400_000))])).values()
        assert tsmc["equity"] == 0 and tsmc["base"] > 0
        # No equity is the company's stated rule, never an estimate of 0%.
        assert tsmc["sources"]["equity"] == FROM_COMPANY_RULE

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
            _role("google", posted=_posted(300_000, 380_000, basis="unclear"), family="sales_business_development"),
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

    def test_a_cash_election_posting_keeps_its_own_reason_when_it_has_no_total(self):
        out = build_comp_trajectory([
            _role("netflix", posted=_posted(90, 120, period="hour")),
            _role("netflix", posted=_posted(20_000, 25_000, period="month")),
            _role("netflix", posted=_posted(300_000, 400_000, period="unclear")),
            _role("netflix", posted=_posted(300_000, 400_000, basis="unclear"), family="sales_business_development"),
            _role("netflix", posted=_posted(300_000, 400_000), level_placed=False),
        ])
        assert out["choice"] == []
        assert {r["reason"]: r["count"] for r in out["set_apart"]} == {
            "hourly": 1, "monthly": 1, "period_unclear": 1, "basis_unclear": 1, "level_unplaced": 1,
        }

    def test_a_non_us_netflix_role_is_set_apart_not_a_choice_row(self):
        out = build_comp_trajectory([_role("netflix", median=700_000, us_pay=False)])
        assert out["choice"] == []
        assert out["set_apart"] == [{"reason": "not_us_pay", "count": 1}]

    def test_under_a_plugin_only_the_roles_it_splits_are_counted(self):
        row_l6 = {"base_amount": 272_333, "stock_amount": 331_667, "bonus_amount": 58_614}
        measured = {("google", "software_engineering", "staff"): row_l6}
        out = build_comp_trajectory([
            _role("google", median=660_000, baselines=measured, heuristic=False),
            _role("google", "senior", median=450_000, baselines=measured, heuristic=False),
        ])
        row = _by_company(out)["google"]
        assert row["count"] == 1
        assert row["sources"]["equity"] == FROM_MEASURED
        # The level the plugin does not split is counted apart, never split by ours.
        assert out["set_apart"] == [{"reason": "plugin_without_split", "count": 1}]

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

    @pytest.mark.parametrize(("company", "family", "ticker"), [
        ("google-deepmind", "ml_ai_research", "GOOGL"),
        ("linkedin", "product_management", "MSFT"),
    ])
    def test_a_subsidiary_reprices_with_its_listed_parent(self, company, family, ticker):
        out = build_comp_trajectory(
            [_role(company, median=772_000, family=family)],
            profiles={company: {"is_public": False, "ticker": None, "equity_vehicle": "options"}},
        )
        [row] = out["public"]
        assert (row["company"], row["ticker"], row["equity_vehicle"]) == (company, ticker, "rsu")
        assert row["equity"] > 0

    def test_a_subsidiary_with_its_own_equity_stays_private(self):
        assert parent_ticker("waymo") is None
        out = build_comp_trajectory(
            [_role("waymo", median=600_000)],
            profiles={"waymo": {"is_public": False, "ticker": None, "equity_vehicle": "options"}},
        )
        assert [e["company"] for e in out["private"]] == ["waymo"]


class TestOfferTerms:
    """What the offer calculator fills in when a company is picked: only what
    the atlas states, each fact with who states it, never a default."""

    @staticmethod
    def _terms(*companies: str, profiles: dict | None = None, quotes: dict | None = None) -> dict[str, dict]:
        return {row["company"]: row for row in build_offer_terms(companies, profiles=profiles, quotes=quotes)}

    def test_a_back_loaded_schedule_is_read_year_by_year_with_who_states_it(self):
        terms = self._terms("amazon", "microsoft")
        amazon, microsoft = terms["amazon"], terms["microsoft"]
        assert amazon["vesting"] == [5, 15, 40, 40]
        assert amazon["vesting_stated_by"] == "estimated"
        assert (amazon["bonus_rule"], amazon["sign_on_bridges_vesting"]) == ("none", True)
        assert microsoft["vesting"] == [25, 25, 25, 25]
        assert microsoft["vesting_stated_by"] == "employer"
        assert (microsoft["bonus_rule"], microsoft["sign_on_bridges_vesting"]) == ("pct_of_base", False)

    def test_a_company_that_states_no_schedule_gets_none_not_an_even_one(self):
        """The screen assumes the even schedule and says so; the server never
        presents one as stated. Anthropic's vesting is searched and not found."""
        anthropic = self._terms("anthropic")["anthropic"]
        assert (anthropic["vesting"], anthropic["vesting_stated_by"]) == (None, None)
        unknown = self._terms("no-such-company")["no-such-company"]
        assert (unknown["vesting"], unknown["bonus_rule"], unknown["equity_vehicle"]) == (None, None, None)

    def test_the_cash_election_and_a_parent_s_stock_reach_the_calculator(self):
        terms = self._terms("netflix", "google-deepmind")
        assert terms["netflix"]["equity_vehicle"] == "cash_election"
        deepmind = terms["google-deepmind"]
        assert (deepmind["listed"], deepmind["ticker"], deepmind["equity_vehicle"]) == (True, "GOOGL", "rsu")

    def test_a_stored_quote_rides_only_on_a_listed_company_in_dollars(self):
        quotes = {
            "microsoft": {"price": 512.3456789, "currency": "USD", "as_of": "2026-11-07"},
            "openai": {"price": 99.0, "currency": "USD", "as_of": "2026-11-07"},
            "tsmc": {"price": 1100.0, "currency": "TWD", "as_of": "2026-11-07"},
        }
        terms = self._terms("microsoft", "openai", "tsmc", quotes=quotes)
        assert terms["microsoft"]["quote"] == {"price": 512.3457, "as_of": "2026-11-07"}
        assert terms["openai"]["listed"] is False
        assert terms["openai"]["quote"] is None
        assert terms["tsmc"]["quote"] is None

    def test_resolved_identity_beats_the_table(self):
        """A company that listed later is listed with its new ticker."""
        profiles = {"openai": {"is_public": True, "ticker": "OAI", "equity_vehicle": "rsu"}}
        openai = self._terms("openai", profiles=profiles)["openai"]
        assert (openai["listed"], openai["ticker"], openai["equity_vehicle"]) == (True, "OAI", "rsu")

    @pytest.mark.parametrize("schedule", ["unknown", "20/20/20/20/20", "a/b", "0/0", ""])
    def test_a_schedule_the_calculator_cannot_show_is_not_offered(self, monkeypatch, schedule):
        from tracker.analytics import stock_trajectory
        from tracker.levels.model import PayPolicy

        monkeypatch.setattr(stock_trajectory, "policy_for", lambda company: PayPolicy(company, vesting=schedule))
        assert self._terms("acme")["acme"]["vesting"] is None

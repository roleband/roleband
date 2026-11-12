"""Unit tests for the base/bonus/equity heuristic and listed-stock identity."""

from __future__ import annotations

import pytest

from tracker.analytics.comp_split import (
    BONUS_PCT,
    PARENT_TICKERS_OUTSIDE_ATLAS,
    equity_pct,
    heuristic_ratios,
    is_public,
    ticker_for,
)
from tracker.levels.identity import IDENTITIES
from tracker.pay_disclosure import _BONUS_PCT_MAX
from tracker.schema import LevelBand

# Every band, junior to senior: the enum lists them in seniority order.
BANDS = tuple(LevelBand)


def _shares(bonus_r: float, equity_r: float) -> tuple[float, float]:
    """(bonus, equity) as shares of the year's total pay, from base-relative ratios."""
    total = 1 + bonus_r + equity_r
    return bonus_r / total, equity_r / total


class TestHeuristicRatios:
    @pytest.mark.parametrize("band", BANDS)
    @pytest.mark.parametrize("bonus", [None, 0.0, 0.15, 0.275])
    def test_equity_is_the_band_share_of_the_total_whatever_the_bonus_rule(self, band, bonus):
        bonus_r, equity_r = heuristic_ratios(band, bonus)
        assert _shares(bonus_r, equity_r)[1] == pytest.approx(equity_pct(band))

    def test_a_stated_bonus_rule_is_the_bonus_per_base(self):
        assert heuristic_ratios(LevelBand.PRINCIPAL, 0.0)[0] == 0.0
        assert heuristic_ratios(LevelBand.PRINCIPAL, 0.2)[0] == pytest.approx(0.2)

    def test_with_no_bonus_rule_the_bonus_is_the_flat_share_of_the_total(self):
        bonus_share, _ = _shares(*heuristic_ratios(LevelBand.STAFF, None))
        assert bonus_share == pytest.approx(BONUS_PCT)

    def test_equity_share_rises_with_seniority(self):
        assert [band.value for band in BANDS] == [
            "intern", "entry", "mid", "senior", "staff", "principal", "director_plus",
        ]
        shares = [_shares(*heuristic_ratios(band, None))[1] for band in BANDS]
        assert shares == sorted(shares) and len(set(shares)) == len(shares)

    @pytest.mark.parametrize("band", [LevelBand.INTERN, LevelBand.ENTRY, LevelBand.MID])
    def test_no_role_below_senior_gets_a_senior_share_of_stock(self, band):
        assert equity_pct(band) < equity_pct(LevelBand.SENIOR)

    def test_an_internship_carries_no_equity(self):
        assert heuristic_ratios(LevelBand.INTERN, None)[1] == 0.0

    def test_a_company_that_grants_no_equity_gets_none(self):
        bonus_r, equity_r = heuristic_ratios(LevelBand.DIRECTOR_PLUS, None, equity_none=True)
        assert equity_r == 0.0
        assert _shares(bonus_r, equity_r)[0] == pytest.approx(BONUS_PCT)

    def test_the_equity_of_a_year_never_exceeds_the_rest_of_it_many_times_over(self):
        for band in BANDS:
            for bonus in (None, 0.0):
                assert heuristic_ratios(band, bonus)[1] < 2.0

    @pytest.mark.parametrize("band", BANDS)
    @pytest.mark.parametrize("bonus", [0.0, 0.10, 0.30, _BONUS_PCT_MAX])
    def test_a_stated_bonus_up_to_the_cap_keeps_equity_bounded_by_the_year_s_cash(self, band, bonus):
        """A posting states a bonus of at most `_BONUS_PCT_MAX` of base. Equity
        stays the band's share of the year, so against the year's cash (base
        plus bonus) it never passes the largest band's share over the rest."""
        bonus_r, equity_r = heuristic_ratios(band, bonus)
        assert bonus_r == pytest.approx(bonus)
        top = max(equity_pct(b) for b in BANDS)
        assert equity_r / (1 + bonus_r) <= top / (1 - top) + 1e-9


class TestPublicRegistry:
    def test_known_public_company_has_ticker(self):
        assert is_public("google")
        assert ticker_for("google") == "GOOGL"

    def test_private_company_has_no_ticker(self):
        assert not is_public("openai")
        assert ticker_for("openai") is None

    def test_twitch_equity_tracks_parent_amazon(self):
        assert ticker_for("twitch") == "AMZN"

    def test_a_renamed_ticker_is_read_from_the_atlas(self):
        # The ticker is XYZ.
        assert ticker_for("block") == "XYZ"

    def test_an_acquired_company_tracks_its_buyer(self):
        # Grants use the parent's IBM stock.
        assert ticker_for("confluent") == "IBM"
        assert IDENTITIES["confluent"].listed is False

    def test_a_company_outside_the_atlas_reads_the_fallback_table(self):
        assert "linkedin" not in IDENTITIES
        assert ticker_for("linkedin") == "MSFT"


class TestSubsidiaryTracksItsListedParent:
    """A subsidiary is not listed, yet its grants are its parent's stock."""

    def test_a_grant_ticker_is_never_on_a_company_listed_itself(self):
        granted = {s for s, i in IDENTITIES.items() if i.grant_ticker}
        assert granted >= {"twitch", "zoox", "github", "google-deepmind", "hashicorp", "confluent", "wiz"}
        assert not {s for s in granted if IDENTITIES[s].listed}
        assert is_public("twitch") and ticker_for("zoox") == "AMZN"

    def test_the_fallback_table_never_restates_an_atlas_company(self):
        assert not set(PARENT_TICKERS_OUTSIDE_ATLAS) & set(IDENTITIES)

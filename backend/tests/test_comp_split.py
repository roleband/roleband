"""Unit tests for the base/bonus/equity heuristic and listed-stock identity."""

from __future__ import annotations

import pytest

from tracker.analytics.comp_split import (
    BONUS_PCT,
    PARENT_TICKERS_OUTSIDE_ATLAS,
    equity_pct,
    is_public,
    split_tc,
    ticker_for,
)
from tracker.levels.identity import IDENTITIES
from tracker.schema import LevelBand


class TestSplitTc:
    def test_components_sum_back_to_total_exactly(self):
        for tc in (298_053, 479_251, 900_001, 1_234_567):
            parts = split_tc(tc, "google", LevelBand.STAFF)
            assert parts["base"] + parts["bonus"] + parts["equity"] == tc

    def test_bonus_is_flat_share_of_tc(self):
        parts = split_tc(1_000_000, "google", LevelBand.SENIOR)
        assert parts["bonus"] == round(1_000_000 * BONUS_PCT)

    def test_equity_share_rises_with_seniority(self):
        tc = 1_000_000
        eq = {
            band: split_tc(tc, "google", band)["equity"]
            for band in (
                LevelBand.SENIOR,
                LevelBand.STAFF,
                LevelBand.PRINCIPAL,
                LevelBand.DIRECTOR_PLUS,
            )
        }
        assert (
            eq[LevelBand.SENIOR]
            < eq[LevelBand.STAFF]
            < eq[LevelBand.PRINCIPAL]
            < eq[LevelBand.DIRECTOR_PLUS]
        )

    def test_cash_heavy_company_has_thinner_equity(self):
        # Netflix pays mostly cash: its equity slice must be below a peer's.
        nflx = split_tc(1_000_000, "netflix", LevelBand.STAFF)["equity"]
        goog = split_tc(1_000_000, "google", LevelBand.STAFF)["equity"]
        assert nflx < goog

    def test_equity_heavy_company_has_fatter_equity(self):
        # The company multiplier increases equity over the generic share;
        # the clamp must still bound director_plus at the equity cap.
        assert equity_pct("openai", LevelBand.STAFF) == pytest.approx(0.63)
        assert equity_pct("openai", LevelBand.DIRECTOR_PLUS) == pytest.approx(0.80)
        oai = split_tc(1_000_000, "openai", LevelBand.STAFF)["equity"]
        goog = split_tc(1_000_000, "google", LevelBand.STAFF)["equity"]
        assert oai > goog

    def test_equity_pct_is_clamped(self):
        assert 0.0 <= equity_pct("google", LevelBand.DIRECTOR_PLUS) <= 0.80
        assert 0.0 <= equity_pct("netflix", LevelBand.SENIOR) <= 0.80


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


class TestObservedSplitOverridesHeuristic:
    """The comp path must prefer REAL per-level splits over the heuristic."""

    def _observed(self):
        # Netflix as it actually is: 100% base, zero stock (cash election).
        return {
            ("netflix", "staff"): {"base_pct": 1.0, "stock_pct": 0.0, "bonus_pct": 0.0},
            ("google", "principal"): {
                "base_pct": 0.3476, "stock_pct": 0.5502, "bonus_pct": 0.1022,
            },
        }

    def test_observed_split_is_used_when_available(self):
        from tracker.analytics.comp_split import split_tc_observed

        p = split_tc_observed(1_000_000, "google", LevelBand.PRINCIPAL, self._observed())
        assert p["source"] == "measured"
        assert p["equity"] == 550_200  # 55.02%, the measured share
        assert p["base"] + p["bonus"] + p["equity"] == 1_000_000

    def test_falls_back_to_heuristic_when_no_observation(self):
        from tracker.analytics.comp_split import split_tc_observed

        p = split_tc_observed(1_000_000, "stripe", LevelBand.STAFF, self._observed())
        assert p["source"] == "heuristic"
        assert p["base"] + p["bonus"] + p["equity"] == 1_000_000

    def test_zero_equity_company_is_honoured_not_overridden_by_the_guess(self):
        from tracker.analytics.comp_split import split_tc, split_tc_observed

        # The heuristic invents an equity slice for Netflix...
        guessed = split_tc(1_000_000, "netflix", LevelBand.STAFF)
        assert guessed["equity"] > 0
        # ...but the observed split says zero, and the observed split must win.
        real = split_tc_observed(1_000_000, "netflix", LevelBand.STAFF, self._observed())
        assert real["equity"] == 0
        assert real["base"] == 1_000_000
        assert real["source"] == "measured"

    def test_under_a_plugin_the_heuristic_splits_nothing(self):
        """The heuristic is our data: while a plugin answers pay, a level its
        rows do not split gets no split of ours."""
        from tracker.analytics.comp_split import split_tc_observed

        assert split_tc_observed(1_000_000, "stripe", LevelBand.STAFF, self._observed(), heuristic=False) is None


class TestSubsidiaryTracksItsListedParent:
    """A subsidiary is not listed, yet its grants are its parent's stock."""

    def test_a_grant_ticker_is_never_on_a_company_listed_itself(self):
        granted = {s for s, i in IDENTITIES.items() if i.grant_ticker}
        assert granted >= {"twitch", "zoox", "github", "google-deepmind", "hashicorp", "confluent", "wiz"}
        assert not {s for s in granted if IDENTITIES[s].listed}
        assert is_public("twitch") and ticker_for("zoox") == "AMZN"

    def test_the_fallback_table_never_restates_an_atlas_company(self):
        assert not set(PARENT_TICKERS_OUTSIDE_ATLAS) & set(IDENTITIES)

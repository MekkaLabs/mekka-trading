"""
tests/test_story_138_circuit_breakers.py
=========================================
Story 138 — Circuit Breaker Matrix (gaps):
  - RateWindowBreaker (LLM error rate sliding window)
  - StalePriceDetector (frozen price feed)
  - SpreadBreaker (abnormal spread)
"""

from __future__ import annotations
import pytest
from src.services.breakers import RateWindowBreaker, StalePriceDetector, SpreadBreaker


# ---------------------------------------------------------------------------
# RateWindowBreaker
# ---------------------------------------------------------------------------

class TestRateWindowBreaker:
    def test_no_trip_below_threshold(self):
        b = RateWindowBreaker("llm", window=4, max_error_rate=0.5)
        for _ in range(4):
            b.observe(False)
        assert not b.is_tripped

    def test_trips_when_rate_meets_threshold(self):
        b = RateWindowBreaker("llm", window=4, max_error_rate=0.5)
        b.observe(True); b.observe(True); b.observe(False); b.observe(False)
        assert b.is_tripped  # 2/4 = 50% == threshold

    def test_not_tripped_until_window_full(self):
        b = RateWindowBreaker("llm", window=6, max_error_rate=0.5)
        # 3 errors out of 3 observed — but window not full
        b.observe(True); b.observe(True); b.observe(True)
        assert not b.is_tripped

    def test_error_rate_calculation(self):
        b = RateWindowBreaker("llm", window=4, max_error_rate=0.9)
        b.observe(True); b.observe(True); b.observe(False); b.observe(False)
        assert b.error_rate == pytest.approx(0.5)

    def test_reset_clears_history(self):
        b = RateWindowBreaker("llm", window=4, max_error_rate=0.5)
        b.observe(True); b.observe(True); b.observe(True); b.observe(True)
        assert b.is_tripped
        b.reset()
        assert not b.is_tripped
        assert b.error_rate == 0.0

    def test_sliding_window_evicts_old_observations(self):
        b = RateWindowBreaker("llm", window=4, max_error_rate=0.5)
        # Fill with errors, then 4 successes
        b.observe(True); b.observe(True); b.observe(True); b.observe(True)
        assert b.is_tripped
        b.observe(False); b.observe(False); b.observe(False); b.observe(False)
        assert not b.is_tripped  # all 4 in window are False now

    def test_invalid_window_raises(self):
        with pytest.raises(ValueError):
            RateWindowBreaker("x", window=0, max_error_rate=0.5)

    def test_invalid_rate_raises(self):
        with pytest.raises(ValueError):
            RateWindowBreaker("x", window=5, max_error_rate=0.0)

    def test_summary_contains_name(self):
        b = RateWindowBreaker("my_breaker", window=5, max_error_rate=0.5)
        assert "my_breaker" in b.summary()


# ---------------------------------------------------------------------------
# StalePriceDetector
# ---------------------------------------------------------------------------

class TestStalePriceDetector:
    def test_not_stale_with_varying_prices(self):
        d = StalePriceDetector("BTC", window=3, min_variation_pct=0.0001)
        assert not d.observe(50000.0)
        assert not d.observe(50100.0)
        assert not d.observe(50200.0)

    def test_stale_with_identical_prices(self):
        d = StalePriceDetector("BTC", window=3, min_variation_pct=0.0001)
        d.observe(50000.0)
        d.observe(50000.0)
        assert d.observe(50000.0)  # 3rd identical → stale

    def test_not_stale_until_window_full(self):
        d = StalePriceDetector("BTC", window=3, min_variation_pct=0.0001)
        d.observe(50000.0)
        assert not d.observe(50000.0)  # only 2 observations

    def test_tiny_variation_not_stale(self):
        d = StalePriceDetector("BTC", window=3, min_variation_pct=0.01)
        d.observe(50000.0)
        d.observe(50001.0)  # 0.002% variation → below 1% threshold → stale
        assert d.observe(50001.0)

    def test_sufficient_variation_not_stale(self):
        d = StalePriceDetector("BTC", window=3, min_variation_pct=0.0001)
        d.observe(50000.0)
        d.observe(50010.0)  # 0.02% variation > 0.01% threshold
        assert not d.observe(50020.0)

    def test_reset_clears(self):
        d = StalePriceDetector("BTC", window=3)
        d.observe(100.0); d.observe(100.0); d.observe(100.0)
        d.reset()
        assert d.last_price is None

    def test_last_price(self):
        d = StalePriceDetector("BTC", window=3)
        d.observe(42000.0)
        assert d.last_price == pytest.approx(42000.0)

    def test_summary_contains_name(self):
        d = StalePriceDetector("ETH", window=3)
        assert "ETH" in d.summary()

    def test_trip_count_increments(self):
        d = StalePriceDetector("BTC", window=3)
        d.observe(100.0); d.observe(100.0); d.observe(100.0)  # trip 1
        d.observe(100.0)  # trip 2 (still stale)
        assert d.trip_count >= 1


# ---------------------------------------------------------------------------
# SpreadBreaker
# ---------------------------------------------------------------------------

class TestSpreadBreaker:
    def _fill_baseline(self, b: SpreadBreaker, bid=49990.0, ask=50010.0, n=20):
        for _ in range(n):
            b.observe(bid, ask)

    def test_not_abnormal_with_normal_spread(self):
        b = SpreadBreaker("BTC", history_window=20, max_spread_multiplier=3.0)
        self._fill_baseline(b)
        # Same spread as baseline → normal
        assert not b.observe(49990.0, 50010.0)

    def test_abnormal_with_huge_spread(self):
        b = SpreadBreaker("BTC", history_window=20, max_spread_multiplier=3.0)
        self._fill_baseline(b, bid=49990.0, ask=50010.0)  # ~0.04% avg spread
        # Now 10x spread
        result = b.observe(49000.0, 51000.0)  # ~4% spread >> 3x of 0.04%
        assert result

    def test_not_abnormal_until_enough_history(self):
        b = SpreadBreaker("BTC", history_window=20, max_spread_multiplier=3.0)
        # Only 2 observations — below min history
        b.observe(49990.0, 50010.0)
        result = b.observe(48000.0, 52000.0)
        assert not result

    def test_reset_clears_history(self):
        b = SpreadBreaker("BTC")
        self._fill_baseline(b)
        b.reset()
        assert b.avg_spread_pct == 0.0

    def test_invalid_inputs_ignored(self):
        b = SpreadBreaker("BTC")
        assert not b.observe(0.0, 50000.0)
        assert not b.observe(50000.0, 49000.0)  # ask < bid

    def test_skip_count_increments(self):
        b = SpreadBreaker("BTC", history_window=5, max_spread_multiplier=2.0)
        for _ in range(5):
            b.observe(49990.0, 50010.0)
        b.observe(40000.0, 60000.0)  # huge spread
        assert b.skip_count >= 1

    def test_summary_contains_name(self):
        b = SpreadBreaker("ETH_spread")
        assert "ETH_spread" in b.summary()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class TestSettings138:
    def test_fields_exist(self):
        from src.config.settings import settings
        assert hasattr(settings, "llm_error_rate_window")
        assert hasattr(settings, "llm_error_rate_threshold")
        assert hasattr(settings, "stale_price_window")
        assert hasattr(settings, "stale_price_min_variation_pct")
        assert hasattr(settings, "spread_history_window")
        assert hasattr(settings, "spread_max_multiplier")

    def test_defaults(self):
        from src.config.settings import settings
        assert settings.llm_error_rate_window == 10
        assert settings.llm_error_rate_threshold == pytest.approx(0.5)
        assert settings.stale_price_window == 3
        assert settings.spread_max_multiplier == pytest.approx(3.0)

"""
tests/test_story_244_flash_vision.py
=====================================
Story 244 — Flash → Vision Integration

Tests that _momentum_prompt_section() emits correct behavioral guidance
for all Flash direction/strength combinations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.models.market_data import MarketAnalysis, MarketData, Trend


def _make_momentum(direction_val: str, is_strong: bool, strength: float = 0.7):
    """Build a mock MomentumSignal."""
    direction = SimpleNamespace(value=direction_val)
    return SimpleNamespace(
        direction=direction,
        is_strong=is_strong,
        strength=strength,
        price_change_pct=0.003,
        volume_multiplier=1.5,
        notes="",
    )


def _make_market_data() -> MarketData:
    return MarketData(
        symbol="BTC",
        timestamp=datetime.now(timezone.utc),
        timeframe="4h",
        price=65_000.0,
        rsi_14=55.0,
        trend=Trend.BULLISH,
        trend_strength=0.7,
        support_levels=[63_000.0],
        resistance_levels=[67_000.0],
        volume_24h=1_000_000.0,
        atr_14=1_200.0,
        recent_closes=[64_000.0, 64_500.0, 65_000.0],
    )


def _make_analysis(momentum) -> MarketAnalysis:
    return MarketAnalysis(
        symbol="BTC",
        timestamp=datetime.now(timezone.utc),
        chart=_make_market_data(),
        momentum=momentum,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMomentumPromptSection:

    def test_strong_up_confirms_long(self):
        mom = _make_momentum("UP", is_strong=True)
        analysis = _make_analysis(mom)
        section = analysis._momentum_prompt_section()

        assert "STRONG UP" in section
        assert "LONG" in section
        assert "confirmed" in section
        assert "20%" in section  # divergence warning for SHORT

    def test_strong_up_warns_short_divergence(self):
        mom = _make_momentum("UP", is_strong=True)
        analysis = _make_analysis(mom)
        section = analysis._momentum_prompt_section()

        assert "SHORT" in section
        assert "20%" in section

    def test_strong_down_confirms_short(self):
        mom = _make_momentum("DOWN", is_strong=True)
        analysis = _make_analysis(mom)
        section = analysis._momentum_prompt_section()

        assert "STRONG DOWN" in section
        assert "SHORT" in section
        assert "confirmed" in section

    def test_strong_down_warns_long_divergence(self):
        mom = _make_momentum("DOWN", is_strong=True)
        analysis = _make_analysis(mom)
        section = analysis._momentum_prompt_section()

        assert "LONG" in section
        assert "20%" in section

    def test_sideways_reduces_confidence(self):
        mom = _make_momentum("SIDEWAYS", is_strong=False)
        analysis = _make_analysis(mom)
        section = analysis._momentum_prompt_section()

        assert "SIDEWAYS" in section
        assert "0.05" in section

    def test_weak_signal_label(self):
        mom = _make_momentum("UP", is_strong=False, strength=0.3)
        analysis = _make_analysis(mom)
        section = analysis._momentum_prompt_section()

        assert "weak" in section.lower()

    def test_section_header(self):
        mom = _make_momentum("UP", is_strong=True)
        analysis = _make_analysis(mom)
        section = analysis._momentum_prompt_section()

        assert "Flash" in section
        assert "BTC" in section

    def test_none_momentum_returns_empty(self):
        analysis = _make_analysis(None)
        section = analysis._momentum_prompt_section()
        assert section == ""

    def test_section_appears_in_full_prompt(self):
        mom = _make_momentum("DOWN", is_strong=True)
        analysis = _make_analysis(mom)
        prompt = analysis.to_prompt()

        assert "Flash" in prompt
        assert "STRONG DOWN" in prompt

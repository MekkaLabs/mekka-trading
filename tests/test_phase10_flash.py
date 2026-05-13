"""
tests/test_phase10_flash.py
===========================
Phase 10 — Flash Momentum Scalper tests (Story 033).

Coverage:
  • Empty/short history → SIDEWAYS, strength=0
  • Up burst (price climbs ≥ +0.5%) → UP
  • Down burst (price drops ≤ -0.5%) → DOWN
  • Sideways (small net move) → SIDEWAYS
  • Strength scales with magnitude (saturates)
  • Volume multiplier amplifies strength score
  • VOLUME-CONFIRMED tag fires when vol_mult ≥ 1.5 + directional
  • is_strong gate (≥0.7 strength + ≥1.5 vol)
  • is_expired flips when entry_window_seconds <= 0
  • Defensive: prices=None, prices_len < min, garbage volumes

Run: pytest tests/test_phase10_flash.py -v
"""

from __future__ import annotations

import pytest

from src.agents.flash import Flash
from src.models.signal import MomentumDirection, MomentumSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ramp_up(start: float = 100.0, n: int = 10, step_pct: float = 0.002) -> list[float]:
    """Generate n prices going UP by step_pct each step."""
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * (1 + step_pct))
    return out


def _ramp_down(start: float = 100.0, n: int = 10, step_pct: float = 0.002) -> list[float]:
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * (1 - step_pct))
    return out


# ===========================================================================
# Direction classification
# ===========================================================================


@pytest.mark.asyncio
async def test_empty_history_returns_sideways():
    sig = await Flash().run(symbol="BTC", recent_prices=[])
    assert sig.direction == MomentumDirection.SIDEWAYS
    assert sig.strength == 0.0
    assert "Insufficient" in sig.notes


@pytest.mark.asyncio
async def test_short_history_returns_sideways():
    sig = await Flash().run(symbol="BTC", recent_prices=[100, 101, 102])
    assert sig.direction == MomentumDirection.SIDEWAYS
    assert sig.strength == 0.0


@pytest.mark.asyncio
async def test_none_history_returns_sideways():
    sig = await Flash().run(symbol="BTC", recent_prices=None)
    assert sig.direction == MomentumDirection.SIDEWAYS


@pytest.mark.asyncio
async def test_up_burst_classified_as_up():
    """+0.5% threshold; ramp_up at 0.2%/step over 10 prices = ~+1.8% net."""
    prices = _ramp_up(start=100.0, n=10, step_pct=0.002)
    sig = await Flash().run(symbol="BTC", recent_prices=prices)
    assert sig.direction == MomentumDirection.UP
    assert sig.price_change_pct > 0.005


@pytest.mark.asyncio
async def test_down_burst_classified_as_down():
    prices = _ramp_down(start=100.0, n=10, step_pct=0.002)
    sig = await Flash().run(symbol="ETH", recent_prices=prices)
    assert sig.direction == MomentumDirection.DOWN
    assert sig.price_change_pct < -0.005


@pytest.mark.asyncio
async def test_small_net_move_is_sideways():
    """+0.1% net move over 10 prices — under 0.5% threshold."""
    prices = _ramp_up(start=100.0, n=10, step_pct=0.0001)
    sig = await Flash().run(symbol="BTC", recent_prices=prices)
    assert sig.direction == MomentumDirection.SIDEWAYS


# ===========================================================================
# Strength scoring
# ===========================================================================


@pytest.mark.asyncio
async def test_strength_grows_with_magnitude():
    """Bigger move → bigger strength."""
    weak = await Flash().run(
        symbol="BTC", recent_prices=_ramp_up(n=10, step_pct=0.0008),
    )
    strong = await Flash().run(
        symbol="BTC", recent_prices=_ramp_up(n=10, step_pct=0.003),
    )
    assert strong.strength > weak.strength


@pytest.mark.asyncio
async def test_strength_saturates_at_one():
    """Extreme move shouldn't blow past 1.0."""
    extreme = _ramp_up(n=10, step_pct=0.05)  # +50% per step, absurd
    sig = await Flash().run(symbol="BTC", recent_prices=extreme)
    assert sig.strength <= 1.0


@pytest.mark.asyncio
async def test_volume_multiplier_amplifies_strength():
    """Same price ramp, with volume spike → higher strength."""
    prices = _ramp_up(n=10, step_pct=0.002)
    no_vol = await Flash().run(symbol="BTC", recent_prices=prices)
    with_vol = await Flash().run(
        symbol="BTC",
        recent_prices=prices,
        recent_volumes=[100] * 9 + [400],  # current 4× avg
    )
    assert with_vol.strength > no_vol.strength
    assert with_vol.volume_multiplier > 1.5


# ===========================================================================
# VOLUME-CONFIRMED + is_strong gate
# ===========================================================================


@pytest.mark.asyncio
async def test_volume_confirmed_tag_when_directional_and_spike():
    sig = await Flash().run(
        symbol="BTC",
        recent_prices=_ramp_up(n=10, step_pct=0.003),
        recent_volumes=[100] * 9 + [300],  # 3× spike
    )
    assert sig.direction == MomentumDirection.UP
    assert "VOLUME-CONFIRMED" in sig.notes


@pytest.mark.asyncio
async def test_no_volume_confirmed_tag_when_sideways():
    """Volume spike alone without direction → no VOLUME-CONFIRMED tag."""
    flat = [100.0] * 10  # zero net move
    sig = await Flash().run(
        symbol="BTC",
        recent_prices=flat,
        recent_volumes=[100] * 9 + [500],
    )
    assert sig.direction == MomentumDirection.SIDEWAYS
    assert "VOLUME-CONFIRMED" not in sig.notes


@pytest.mark.asyncio
async def test_is_strong_property_requires_both_strength_and_volume():
    """MomentumSignal.is_strong = strength≥0.70 AND volume_multiplier≥1.5"""
    # Strong move + strong volume → is_strong True
    strong = await Flash().run(
        symbol="BTC",
        recent_prices=_ramp_up(n=10, step_pct=0.005),
        recent_volumes=[100] * 9 + [300],
    )
    assert strong.is_strong is True

    # Strong move but weak volume → not is_strong
    weak_vol = await Flash().run(
        symbol="BTC",
        recent_prices=_ramp_up(n=10, step_pct=0.005),
        recent_volumes=[100] * 10,
    )
    assert weak_vol.is_strong is False


# ===========================================================================
# Misc
# ===========================================================================


@pytest.mark.asyncio
async def test_entry_window_seconds_propagated():
    sig = await Flash().run(
        symbol="BTC",
        recent_prices=_ramp_up(n=10),
        window_seconds=120,
    )
    assert sig.entry_window_seconds == 120


def test_is_expired_when_window_zero():
    sig = MomentumSignal(symbol="BTC", strength=0.5, entry_window_seconds=0)
    assert sig.is_expired is True


@pytest.mark.asyncio
async def test_garbage_volumes_does_not_raise():
    """Misaligned volume series should not crash; volume_mult falls back to 1.0."""
    sig = await Flash().run(
        symbol="BTC",
        recent_prices=_ramp_up(n=10, step_pct=0.002),
        recent_volumes=[1, 2],  # mismatched length
    )
    assert sig.direction == MomentumDirection.UP
    assert sig.volume_multiplier == 1.0  # fell back


@pytest.mark.asyncio
async def test_zero_first_price_safe():
    """First price 0 shouldn't divide by zero."""
    prices = [0.0] + _ramp_up(n=9, step_pct=0.002)
    sig = await Flash().run(symbol="BTC", recent_prices=prices)
    # No assertion on direction — just that no exception was raised
    assert isinstance(sig, MomentumSignal)

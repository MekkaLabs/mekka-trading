"""
tests/test_batman_liquidity_gate.py
===================================
Gate de liquidez pré-trade (Batman 4e): bloqueia a entrada quando o slippage
estimado da ordem (Aquaman) é alto demais. Só bloqueia com data_available=True;
em degradado, cai para a penalidade de size.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.batman import Batman
from src.models.market_data import LiquidityData
from src.models.signal import TradingSignal


def _signal(action="LONG"):
    return TradingSignal(
        symbol="BTC", action=action, confidence=0.70,
        entry_price=65_000.0,
        stop_loss=63_000.0 if action == "LONG" else 67_000.0,
        take_profit=71_000.0 if action == "LONG" else 59_000.0,
        size_pct=0.02, leverage=2, reasoning="test",
        agent_contributions={"Superman": "trend"},
    )


def _liq(slippage_pct, *, available=True, score=0.8):
    return LiquidityData(
        symbol="BTC", bid_ask_spread_pct=0.001,
        order_book_depth_buy=50_000.0, order_book_depth_sell=50_000.0,
        estimated_slippage_pct=slippage_pct, liquidity_score=score,
        data_available=available,
    )


@contextmanager
def _neutralize_gates():
    with (
        patch("src.agents.batman.is_kill_switch_active", return_value=False),
        patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
        patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
        patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
        patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
        patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
        patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
        patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
        patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
    ):
        yield


@pytest.mark.asyncio
async def test_high_slippage_blocks_entry():
    with _neutralize_gates():
        approval = await Batman().run(
            signal=_signal("LONG"), equity_usd=10_000.0,
            liquidity=_liq(0.05),  # 5% > limite 2%
        )
    assert not approval.is_executable
    assert "max_entry_slippage_estimate_pct" in (approval.breached_limits or [])


@pytest.mark.asyncio
async def test_low_slippage_does_not_block():
    with _neutralize_gates():
        approval = await Batman().run(
            signal=_signal("LONG"), equity_usd=10_000.0,
            liquidity=_liq(0.001),  # 0.1% < limite
        )
    assert "max_entry_slippage_estimate_pct" not in (approval.breached_limits or [])


@pytest.mark.asyncio
async def test_degraded_data_does_not_hard_block():
    """Slippage alto mas data_available=False → gate NÃO bloqueia (penalidade cuida)."""
    with _neutralize_gates():
        approval = await Batman().run(
            signal=_signal("LONG"), equity_usd=10_000.0,
            liquidity=_liq(0.99, available=False, score=0.1),
        )
    assert "max_entry_slippage_estimate_pct" not in (approval.breached_limits or [])

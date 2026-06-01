"""Regressão H7/H8/H9 (2026-06-01 audit) — monitoramento live.

H8 — alerta CRITICAL quando o mark está perto da liquidação.
H9 — guardian detecta TP ausente (_has_take_profit) e registra em tp_missing.
H7 — reconciliador de PnL de closes live é best-effort (não levanta) e é no-op
     em paper / exchange não-CCXT.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from src.models.portfolio import EquitySnapshot, EquitySource, PositionSummary


# ===========================================================================
# H8 — proximidade de liquidação
# ===========================================================================

def _snapshot(positions):
    return EquitySnapshot(
        source=EquitySource.BINANCE,
        is_paper=False,
        equity_usd=10_000.0,
        available_balance_usd=9_000.0,
        margin_used_usd=1_000.0,
        open_positions_count=len(positions),
        positions=positions,
    )


@pytest.mark.asyncio
async def test_h8_alerts_when_near_liquidation():
    from src.agents.nick_fury import NickFury

    fury = NickFury()
    # Posição long: mark 100, liq 98 → dist 2% < 5% → ALERTA.
    near = PositionSummary(
        symbol="BTC", side="long", size=0.1, entry_price=105.0,
        mark_price=100.0, liquidation_price=98.0,
    )
    alert = AsyncMock()
    fury._telegram = types.SimpleNamespace(alert=alert)

    with patch("src.agents.nick_fury.settings", types.SimpleNamespace(liq_proximity_alert_pct=0.05)), \
         patch("src.agents.nick_fury.MekkaRepository.log_event", AsyncMock()):
        await fury._check_liquidation_proximity(_snapshot([near]))

    assert alert.await_count == 1, "deveria alertar quando perto da liquidação"


@pytest.mark.asyncio
async def test_h8_no_alert_when_far_from_liquidation():
    from src.agents.nick_fury import NickFury

    fury = NickFury()
    far = PositionSummary(
        symbol="BTC", side="long", size=0.1, entry_price=105.0,
        mark_price=100.0, liquidation_price=70.0,  # 30% longe
    )
    alert = AsyncMock()
    fury._telegram = types.SimpleNamespace(alert=alert)

    with patch("src.agents.nick_fury.settings", types.SimpleNamespace(liq_proximity_alert_pct=0.05)), \
         patch("src.agents.nick_fury.MekkaRepository.log_event", AsyncMock()):
        await fury._check_liquidation_proximity(_snapshot([far]))

    assert alert.await_count == 0


@pytest.mark.asyncio
async def test_h8_skips_when_liq_none():
    """Binance cross-margin sem liq_price → pula (não levanta, não alerta)."""
    from src.agents.nick_fury import NickFury

    fury = NickFury()
    no_liq = PositionSummary(
        symbol="BTC", side="long", size=0.1, entry_price=105.0,
        mark_price=100.0, liquidation_price=None,
    )
    alert = AsyncMock()
    fury._telegram = types.SimpleNamespace(alert=alert)

    with patch("src.agents.nick_fury.settings", types.SimpleNamespace(liq_proximity_alert_pct=0.05)), \
         patch("src.agents.nick_fury.MekkaRepository.log_event", AsyncMock()):
        await fury._check_liquidation_proximity(_snapshot([no_liq]))

    assert alert.await_count == 0


# ===========================================================================
# H9 — _has_take_profit
# ===========================================================================

def test_h9_detects_take_profit_present():
    from src.agents.iron_man import IronMan

    # Long protegido por SELL take_profit reduceOnly.
    orders = [
        {"type": "take_profit_market", "side": "sell", "reduceOnly": True},
    ]
    assert IronMan._has_take_profit(orders, is_long=True) is True


def test_h9_detects_take_profit_missing():
    from src.agents.iron_man import IronMan

    # Só há um stop (SL), nenhum TP → ausente.
    orders = [
        {"type": "stop_market", "side": "sell", "reduceOnly": True},
    ]
    assert IronMan._has_take_profit(orders, is_long=True) is False


def test_h9_take_profit_wrong_side_not_counted():
    from src.agents.iron_man import IronMan

    # TP no lado errado (buy para um long) não conta.
    orders = [
        {"type": "take_profit_market", "side": "buy", "reduceOnly": True},
    ]
    assert IronMan._has_take_profit(orders, is_long=True) is False


# ===========================================================================
# H7 — reconciliador best-effort
# ===========================================================================

@pytest.mark.asyncio
async def test_h7_noop_on_non_ccxt_exchange():
    """Em hyperliquid (não-CCXT para este caminho) é no-op silencioso."""
    from src.agents.nick_fury import NickFury

    fury = NickFury()
    with patch("src.agents.nick_fury.settings", types.SimpleNamespace(active_exchange="hyperliquid")):
        # Não deve levantar nem tocar exchange.
        await fury._reconcile_live_close_pnl()

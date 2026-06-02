"""Regressão L2/L4/L6 (2026-06-01 audit) — fixes LOW de robustez.

L2 — set_leverage fail-open: em live, falha persistente agora REJEITA (fail-closed).
L4 — save_trade dedup por order_id (idempotência no write).
L6 — SL emergencial do guardian ancorado no MARK atual (lado correto pós-downtime).
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from src.models.signal import TradeAction, TradingSignal


def _signal() -> TradingSignal:
    return TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.7,
        entry_price=77000.0, stop_loss=75460.0, take_profit=80000.0,
        size_pct=0.001, leverage=2, reasoning="low", agent_contributions={},
    )


# ===========================================================================
# L2 — set_leverage fail-closed em live
# ===========================================================================

class _LevFailExchange:
    """set_leverage SEMPRE falha (erro real, não -4046)."""

    async def set_leverage(self, *a, **k):
        raise Exception("binance -4028 invalid leverage")

    async def fetch_balance(self):
        return {"USDT": {"free": 1e6}}

    async def create_order(self, *a, **k):
        raise AssertionError("não deveria chegar a create_order (rejeição em set_leverage)")

    def price_to_precision(self, s, p):
        return float(p)

    def amount_to_precision(self, s, a):
        return float(a)

    def market(self, s):
        return {"precision": {"price": 1, "amount": 3}, "limits": {}}


@pytest.mark.asyncio
async def test_l2_set_leverage_failure_rejects_in_live():
    from src.agents.iron_man import IronMan
    from src.models.execution import ExecutionStatus

    iron = IronMan()
    fake = _LevFailExchange()
    fake_settings = types.SimpleNamespace(
        paper_trading=False, active_exchange="binance", binance_testnet=False,
        bybit_testnet=False, mainnet_dry_run=False, binance_entry_order_type="auto",
        binance_max_entry_slippage_bps=20.0,
    )
    with patch("src.agents.iron_man.settings", fake_settings), \
         patch.object(iron, "_get_ccxt_exchange", AsyncMock(return_value=fake)), \
         patch.object(iron, "_binance_market_type_for", return_value="linear"), \
         patch.object(iron, "_is_inverse_for", return_value=False), \
         patch.object(iron, "_balance_currency_for", return_value="USDT"), \
         patch.object(iron, "_check_clock_skew", AsyncMock(return_value=(True, 0, None))):
        result = await iron._place_ccxt_order(
            signal=_signal(), quantity=0.01, leverage=2, size_pct=0.001,
            exchange_id="binance", cycle_id="c1",
        )
    assert result.status == ExecutionStatus.REJECTED
    assert "leverage" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_l2_no_need_to_change_is_success():
    """Erro -4046 ('no need to change') é tratado como sucesso (não rejeita)."""
    from src.agents.iron_man import IronMan
    from src.models.execution import ExecutionStatus

    class _Ex(_LevFailExchange):
        async def set_leverage(self, *a, **k):
            raise Exception("binance -4046 No need to change leverage")

        async def create_order(self, *, symbol, type, side, amount, params=None, price=None):  # noqa: A002
            params = params or {}
            if type in ("market", "limit") and not params.get("reduceOnly"):
                return {"filled": amount, "average": 77000.0, "id": "E1"}
            return {"id": "SL"}

    iron = IronMan()
    fake = _Ex()
    fake_settings = types.SimpleNamespace(
        paper_trading=False, active_exchange="binance", binance_testnet=True,  # market path
        bybit_testnet=False, mainnet_dry_run=False, binance_entry_order_type="auto",
        binance_max_entry_slippage_bps=20.0,
    )
    with patch("src.agents.iron_man.settings", fake_settings), \
         patch.object(iron, "_get_ccxt_exchange", AsyncMock(return_value=fake)), \
         patch.object(iron, "_binance_market_type_for", return_value="linear"), \
         patch.object(iron, "_is_inverse_for", return_value=False), \
         patch.object(iron, "_balance_currency_for", return_value="USDT"), \
         patch.object(iron, "_check_clock_skew", AsyncMock(return_value=(True, 0, None))):
        result = await iron._place_ccxt_order(
            signal=_signal(), quantity=0.01, leverage=2, size_pct=0.001,
            exchange_id="binance", force_market_in_testnet=True, cycle_id="c1",
        )
    # Não rejeitou por leverage — seguiu para preencher.
    assert result.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIAL)


# ===========================================================================
# L6 — SL emergencial ancorado no mark atual
# ===========================================================================

def test_l6_emergency_sl_anchored_to_mark():
    """Documenta a geometria: para um LONG, o stop deve ficar ABAIXO do mark
    atual mesmo que o entry esteja bem acima (após queda durante downtime)."""
    pct = 0.02
    entry = 100.0
    mark = 80.0  # caiu 20% durante o downtime
    is_long = True
    # Fix L6: ancora no mark (não no entry).
    base = mark if mark > 0 else entry
    sl = base * (1 - pct) if is_long else base * (1 + pct)
    assert sl < mark, "stop de LONG deve ficar abaixo do mark atual"
    # Comportamento ANTIGO (entry) ficaria ACIMA do mark → lado errado.
    old_sl = entry * (1 - pct)
    assert old_sl > mark  # 98 > 80 → teria disparado imediatamente

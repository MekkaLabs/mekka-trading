"""Regressão C1 (2026-06-01 audit) — fail-safe de SL chama emergency_flatten.

Bug: `_place_ccxt_order` referenciava `cycle_id` que NÃO existia no escopo
(faltava na assinatura). Quando o SL falhava após os retries, a linha
`cycle_id=cycle_id` lançava NameError ANTES de chamar `_emergency_flatten`,
deixando a posição NUA (sem stop) com dinheiro real até o Guardian (≤5 min).

Fix: `cycle_id` virou parâmetro de `_place_ccxt_order`. Este teste simula uma
falha definitiva de SL e asserta que `_emergency_flatten` é REALMENTE chamado
(sem NameError) e que o resultado é ERROR com a posição achatada.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from src.models.signal import TradeAction, TradingSignal


def _signal() -> TradingSignal:
    return TradingSignal(
        symbol="BTC",
        action=TradeAction.LONG,
        confidence=0.7,
        entry_price=77000.0,
        stop_loss=75460.0,   # ~2% — float arbitrário, como Vision gera
        take_profit=80000.0,
        size_pct=0.05,
        leverage=5,
        reasoning="test c1",
        agent_contributions={},
    )


class _FakeExchange:
    """Exchange CCXT falso: entrada preenche, mas TODO stop_market falha."""

    def __init__(self) -> None:
        self.flatten_called = False

    async def create_order(self, *, symbol, type, side, amount, params=None, price=None):  # noqa: A002
        if type == "market" and not (params or {}).get("reduceOnly"):
            # entrada preenche
            return {"filled": amount, "average": 77000.0, "id": "ENTRY-1"}
        if type == "stop_market":
            # SL SEMPRE falha (ex.: PRICE_FILTER) → exercita o fail-safe
            raise Exception("binance -1111 PRICE_FILTER rejected stopPrice")
        # reduceOnly market (emergency flatten interno) ou TP
        return {"id": "X-1", "filled": amount}

    async def fetch_balance(self):
        return {"USDT": {"free": 1_000_000.0}}

    async def set_leverage(self, *a, **k):
        return None

    def price_to_precision(self, symbol, price):
        return float(price)

    def amount_to_precision(self, symbol, amount):
        return float(amount)

    def market(self, symbol):
        return {"precision": {"price": 1, "amount": 3}}


@pytest.mark.asyncio
async def test_sl_failure_triggers_emergency_flatten_no_nameerror():
    from src.agents.iron_man import IronMan
    from src.models.execution import ExecutionStatus

    iron = IronMan()
    fake = _FakeExchange()

    fake_settings = types.SimpleNamespace(
        paper_trading=False,
        active_exchange="binance",
        binance_testnet=True,   # força market na entrada (pula ticker)
        bybit_testnet=False,
        mainnet_dry_run=False,
        binance_entry_order_type="auto",
        binance_max_entry_slippage_bps=20.0,
    )

    flatten_mock = AsyncMock(return_value=(True, None))

    with patch.object(iron, "_get_ccxt_exchange", AsyncMock(return_value=fake)), \
         patch.object(iron, "_binance_market_type_for", return_value="linear"), \
         patch.object(iron, "_is_inverse_for", return_value=False), \
         patch.object(iron, "_balance_currency_for", return_value="USDT"), \
         patch.object(iron, "_check_clock_skew", AsyncMock(return_value=(True, 0, None))), \
         patch.object(iron, "_emergency_flatten", flatten_mock), \
         patch("src.agents.iron_man.settings", fake_settings):
        result = await iron._place_ccxt_order(
            signal=_signal(),
            quantity=0.01,
            leverage=5,
            size_pct=0.05,
            exchange_id="binance",
            force_market_in_testnet=True,
            cycle_id="cyc-abc-123",
        )

    # O ponto central: emergency_flatten FOI chamado (sem NameError no cycle_id).
    assert flatten_mock.await_count >= 1, "emergency_flatten deveria ter sido chamado quando o SL falha"
    # E o cycle_id foi propagado corretamente.
    _, kwargs = flatten_mock.await_args
    assert kwargs.get("cycle_id") == "cyc-abc-123"
    # Resultado final: ERROR (posição não pôde ser protegida → achatada).
    assert result.status == ExecutionStatus.ERROR


@pytest.mark.asyncio
async def test_place_ccxt_order_accepts_cycle_id_param():
    """Garante que a assinatura aceita cycle_id (regressão da causa-raiz)."""
    import inspect
    from src.agents.iron_man import IronMan

    sig = inspect.signature(IronMan._place_ccxt_order)
    assert "cycle_id" in sig.parameters

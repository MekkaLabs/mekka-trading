"""Regressão dos fixes MEDIUM da auditoria de prontidão mainnet (2026-06-01).

M4 — entrada `market` em MAINNET+LIVE rebaixada para limit_ioc (cap de slippage).
M5 — preflight risk_limits FALHA em mainnet+live (antes só WARN / threshold 0.5%).
M7 — SL Guardian escala (alerta CRITICAL) quando não consegue ler posições.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

import scripts.preflight_mainnet as pf
from src.models.signal import TradeAction, TradingSignal


# ===========================================================================
# M5 — preflight risk_limits FAIL em mainnet+live
# ===========================================================================

def _settings_risk(*, size, lev, paper, testnet, trades=3, positions=2):
    return types.SimpleNamespace(
        max_position_size_pct=size,
        max_leverage=lev,
        max_trades_per_day=trades,
        max_open_positions=positions,
        paper_trading=paper,
        active_exchange="binance",
        exchange_is_testnet=lambda _ex=None: testnet,
    )


def _run_risk(s):
    report = pf.PreflightReport()
    with patch.object(pf, "_get_settings", return_value=s):
        pf.check_risk_limits(report)
    return report.checks[0]


def test_m5_loose_limits_fail_in_mainnet_live():
    c = _run_risk(_settings_risk(size=0.02, lev=5, paper=False, testnet=False))
    assert c.level == "FAIL"


def test_m5_loose_limits_only_warn_in_testnet():
    c = _run_risk(_settings_risk(size=0.02, lev=5, paper=False, testnet=True))
    assert c.level == "WARN"


def test_m5_conservative_limits_pass():
    c = _run_risk(_settings_risk(size=0.001, lev=2, paper=False, testnet=False))
    assert c.level == "PASS"


# ===========================================================================
# M7 — SL Guardian escala quando não consegue ler posições
# ===========================================================================

@pytest.mark.asyncio
async def test_m7_guardian_escalates_on_positions_unreadable():
    from src.agents.iron_man import IronMan

    iron = IronMan()
    fake_settings = types.SimpleNamespace(
        paper_trading=False,
        active_exchange="binance",
    )
    alerter = AsyncMock()
    alerter.alert = AsyncMock()

    with patch("src.agents.iron_man.settings", fake_settings), \
         patch.object(iron, "_get_ccxt_exchange", AsyncMock(side_effect=Exception("nonce -1021"))), \
         patch("src.services.telegram_alerter.TelegramAlerter", return_value=alerter):
        summary = await iron.ensure_stops_for_open_positions()

    assert summary.get("escalated") is True
    assert summary["errors"], "deveria registrar o erro de leitura de posições"


# ===========================================================================
# M4 — entrada market em mainnet+live rebaixada para limit_ioc
# ===========================================================================

def _signal() -> TradingSignal:
    return TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.7,
        entry_price=77000.0, stop_loss=75460.0, take_profit=80000.0,
        size_pct=0.001, leverage=2, reasoning="m4", agent_contributions={},
    )


class _TypeCapturingExchange:
    def __init__(self) -> None:
        self.entry_type = None

    async def create_order(self, *, symbol, type, side, amount, params=None, price=None):  # noqa: A002
        params = params or {}
        if type in ("market", "limit") and not params.get("reduceOnly"):
            self.entry_type = type
            return {"filled": amount, "average": 77000.0, "id": "E1"}
        return {"id": "OK"}

    async def fetch_ticker(self, symbol):
        return {"bid": 76990.0, "ask": 77010.0}

    async def fetch_balance(self):
        return {"USDT": {"free": 1_000_000.0}}

    async def set_leverage(self, *a, **k):
        return None

    def price_to_precision(self, symbol, price):
        return float(price)

    def amount_to_precision(self, symbol, amount):
        return float(amount)

    def market(self, symbol):
        return {"precision": {"price": 1, "amount": 3}, "limits": {}}


@pytest.mark.asyncio
async def test_m4_market_downgraded_to_limit_on_mainnet_live():
    from src.agents.iron_man import IronMan

    iron = IronMan()
    fake = _TypeCapturingExchange()
    fake_settings = types.SimpleNamespace(
        paper_trading=False,          # live
        active_exchange="binance",
        binance_testnet=False,        # mainnet
        bybit_testnet=False,
        mainnet_dry_run=False,
        binance_entry_order_type="market",   # operador pediu market explicitamente
        binance_max_entry_slippage_bps=20.0,
    )

    with patch("src.agents.iron_man.settings", fake_settings), \
         patch.object(iron, "_get_ccxt_exchange", AsyncMock(return_value=fake)), \
         patch.object(iron, "_binance_market_type_for", return_value="linear"), \
         patch.object(iron, "_is_inverse_for", return_value=False), \
         patch.object(iron, "_balance_currency_for", return_value="USDT"), \
         patch.object(iron, "_check_clock_skew", AsyncMock(return_value=(True, 0, None))):
        await iron._place_ccxt_order(
            signal=_signal(), quantity=0.01, leverage=2, size_pct=0.001,
            exchange_id="binance", force_market_in_testnet=False, cycle_id="c1",
        )

    # Em mainnet+live, `market` configurado deve virar `limit` (cap de slippage).
    assert fake.entry_type == "limit", f"esperava limit, veio {fake.entry_type}"

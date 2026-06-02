"""Regressão C3+H4 (2026-06-01 audit) — idempotência + retry CCXT.

H4: o filtro de retry usava (TimeoutError, ConnectionError) built-ins, que NÃO
casam com ccxt.RequestTimeout/NetworkError (herdam de ccxt.BaseError). O retry
estava MORTO — um timeout transitório da Binance falhava na 1ª tentativa.

C3: sem clientOrderId, re-enviar uma ordem após timeout da RESPOSTA (a ordem
chegou mas a resposta se perdeu) DUPLICARIA a posição.

Fix conjunto: clientOrderId determinístico + retry com exceções ccxt. Quando a
2ª submissão é rejeitada como duplicata, reconciliamos a ordem existente em vez
de abrir uma segunda.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import ccxt.async_support as _ccxt  # type: ignore
import pytest

from src.models.signal import TradeAction, TradingSignal


def _signal() -> TradingSignal:
    return TradingSignal(
        symbol="BTC",
        action=TradeAction.LONG,
        confidence=0.7,
        entry_price=77000.0,
        stop_loss=75460.0,
        take_profit=80000.0,
        size_pct=0.05,
        leverage=5,
        reasoning="test c3/h4",
        agent_contributions={},
    )


class _DupExchange:
    """1ª entrada: NetworkError transitório (deve disparar retry = H4).
    2ª entrada: DuplicateOrderId (deve reconciliar, não duplicar = C3)."""

    def __init__(self) -> None:
        self.entry_calls = 0
        self.fetch_calls = 0
        self.seen_client_oid = None

    async def create_order(self, *, symbol, type, side, amount, params=None, price=None):  # noqa: A002
        params = params or {}
        if type in ("market", "limit") and not params.get("reduceOnly"):
            self.entry_calls += 1
            self.seen_client_oid = params.get("newClientOrderId")
            if self.entry_calls == 1:
                raise _ccxt.NetworkError("transient timeout from binance")
            if self.entry_calls == 2:
                raise _ccxt.DuplicateOrderId("binance -2010 Duplicate order sent")
            return {"filled": amount, "average": 77000.0, "id": "E1"}
        if type == "stop_market":
            return {"id": "SL1"}
        if type == "take_profit_market":
            return {"id": "TP1"}
        return {"id": "X"}

    async def fetch_order(self, oid, symbol, params=None):
        self.fetch_calls += 1
        return {
            "filled": 0.01,
            "average": 77000.0,
            "id": "E1",
            "clientOrderId": (params or {}).get("origClientOrderId"),
        }

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
async def test_retry_fires_on_ccxt_error_and_duplicate_is_reconciled():
    from src.agents.iron_man import IronMan
    from src.models.execution import ExecutionStatus

    iron = IronMan()
    fake = _DupExchange()
    fake_settings = types.SimpleNamespace(
        paper_trading=False,
        active_exchange="binance",
        binance_testnet=True,
        bybit_testnet=False,
        mainnet_dry_run=False,
        binance_entry_order_type="auto",
        binance_max_entry_slippage_bps=20.0,
    )

    with patch.object(iron, "_get_ccxt_exchange", AsyncMock(return_value=fake)), \
         patch.object(iron, "_binance_market_type_for", return_value="linear"), \
         patch.object(iron, "_is_inverse_for", return_value=False), \
         patch.object(iron, "_balance_currency_for", return_value="USDT"), \
         patch.object(iron, "_check_clock_skew", AsyncMock(return_value=(True, 0, None))), \
         patch("src.agents.iron_man.settings", fake_settings):
        result = await iron._place_ccxt_order(
            signal=_signal(),
            quantity=0.01,
            leverage=5,
            size_pct=0.05,
            exchange_id="binance",
            force_market_in_testnet=True,
            cycle_id="cyc-xyz",
        )

    # H4: o retry disparou no NetworkError ccxt (entry chamada 2×, não 1×).
    assert fake.entry_calls == 2, "retry deveria ter re-tentado após ccxt.NetworkError"
    # C3: a duplicata foi reconciliada (não abriu 2ª posição) via fetch_order.
    assert fake.fetch_calls >= 1, "deveria reconciliar a ordem existente por clientOrderId"
    # clientOrderId determinístico foi enviado.
    assert fake.seen_client_oid and fake.seen_client_oid.startswith("mk_")
    # Resultado final: posição protegida (não ERROR, não duplicada).
    assert result.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIAL)


@pytest.mark.asyncio
async def test_fetch_order_by_client_oid_matches_open_order():
    """_fetch_order_by_client_oid casa pela clientOrderId em ordens abertas."""
    from src.agents.iron_man import IronMan

    iron = IronMan()

    class _Ex:
        async def fetch_order(self, *a, **k):
            raise Exception("not supported")

        async def fetch_open_orders(self, symbol):
            return [
                {"id": "A", "clientOrderId": "outro"},
                {"id": "B", "info": {"clientOrderId": "mk_target"}},
            ]

    found = await iron._fetch_order_by_client_oid(_Ex(), "BTC/USDT:USDT", "mk_target")
    assert found is not None and found["id"] == "B"

    missing = await iron._fetch_order_by_client_oid(_Ex(), "BTC/USDT:USDT", "mk_nope")
    assert missing is None


def test_client_oid_is_deterministic_and_unique():
    from src.agents.iron_man import IronMan

    s1 = types.SimpleNamespace(snapshot_id="abc", symbol="BTC")
    s2 = types.SimpleNamespace(snapshot_id="abc", symbol="BTC")
    s3 = types.SimpleNamespace(snapshot_id="zzz", symbol="BTC")
    a = IronMan._deterministic_client_oid(s1, "buy", "cyc1")
    b = IronMan._deterministic_client_oid(s2, "buy", "cyc1")
    c = IronMan._deterministic_client_oid(s3, "buy", "cyc1")
    assert a == b           # mesma decisão → mesmo id (retry seguro)
    assert a != c           # decisões distintas → ids distintos
    assert len(a) <= 36 and a.startswith("mk_")
    # Identidade fraca (sem snapshot nem cycle) → nonce único, sem colisão.
    w = types.SimpleNamespace(symbol="BTC")
    assert IronMan._deterministic_client_oid(w, "buy", None) != \
        IronMan._deterministic_client_oid(w, "buy", None)

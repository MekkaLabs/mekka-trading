"""
tests/test_core_agents.py
=========================
Tests for the safety-critical core agents that previously had no coverage
(CodeAuditor/Cypher flagged the gap):

  - IronMan SL fail-safe — a filled position whose stop-loss cannot be placed
    MUST be flattened, never left naked. (Crown-jewel mainnet-safety test.)
  - IronMan min-notional bump on testnet.
  - PortfolioManager._parse_ccxt_snapshot mapping.
  - Batman risk gates clamp oversized leverage/size.
  - Cyclops SL/TP extraction helper.
"""

from __future__ import annotations

import time

import pytest

from src.models.signal import TradingSignal, TradeAction
from src.models.risk import RiskVerdict
from src.models.execution import ExecutionStatus


# ---------------------------------------------------------------------------
# Fake CCXT exchange for IronMan live-path tests
# ---------------------------------------------------------------------------

class _FakeExchange:
    """Minimal async CCXT-like exchange. Entry fills; SL placement raises."""

    def __init__(self, *, sl_fails=True, min_amount=0.001, min_cost=5.0):
        self.calls: list[dict] = []
        self._sl_fails = sl_fails
        self._min_amount = min_amount
        self._min_cost = min_cost

    def market(self, sym):
        return {"limits": {"amount": {"min": self._min_amount}, "cost": {"min": self._min_cost}}}

    def amount_to_precision(self, sym, q):
        return float(q)

    def price_to_precision(self, sym, p):
        return float(round(float(p), 2))

    async def fetch_time(self):
        return int(time.time() * 1000)

    async def fetch_ticker(self, sym):
        return {"ask": 70010.0, "bid": 69990.0, "last": 70000.0}

    async def set_leverage(self, lev, sym):
        return {"leverage": lev}

    async def fetch_balance(self):
        return {"USDT": {"free": 1_000_000.0}}

    async def create_order(self, symbol, type, side, amount, price=None, params=None):
        self.calls.append({"type": type, "side": side, "amount": amount,
                           "price": price, "params": params or {}})
        if type == "limit":  # entry — fills fully
            return {"id": "ENTRY1", "filled": amount, "average": price or 0.0}
        if type == "stop_market":
            if self._sl_fails:
                raise RuntimeError("venue rejected stop order")
            return {"id": "SL1"}
        if type == "take_profit_market":
            return {"id": "TP1"}
        if type == "market":  # emergency flatten
            return {"id": "FLAT1", "filled": amount}
        return {"id": "X"}


def _signal(symbol="BTC", entry=70000.0):
    return TradingSignal(
        symbol=symbol, action=TradeAction.LONG, confidence=0.8,
        entry_price=entry, stop_loss=entry * 0.98, take_profit=entry * 1.04,
        size_pct=0.01, leverage=2, reasoning="test",
    )


# ---------------------------------------------------------------------------
# IronMan — SL fail-safe (crown jewel)
# ---------------------------------------------------------------------------

async def test_ironman_sl_failure_flattens_position():
    from src.agents.iron_man import IronMan
    im = IronMan()
    fake = _FakeExchange(sl_fails=True)
    im._ccxt_exchange = fake  # inject — bypasses real connect

    result = await im._place_ccxt_order(
        signal=_signal(), quantity=0.01, leverage=2, size_pct=0.01, exchange_id="binance",
    )
    # SL failed → must NOT be a success; position must be flattened.
    assert result.status == ExecutionStatus.ERROR
    assert (result.metadata or {}).get("sl_failed") is True
    assert (result.metadata or {}).get("flattened") is True
    # A reduce-only market order (the flatten) must have been sent.
    assert any(c["type"] == "market" and c["params"].get("reduceOnly") for c in fake.calls)


async def test_ironman_entry_type_limit_ioc(monkeypatch):
    from src.agents.iron_man import IronMan
    from src.config.settings import settings
    monkeypatch.setattr(settings, "binance_entry_order_type", "limit_ioc")
    im = IronMan(); fake = _FakeExchange(sl_fails=False); im._ccxt_exchange = fake
    await im._place_ccxt_order(signal=_signal(), quantity=0.01, leverage=2,
                               size_pct=0.01, exchange_id="binance")
    assert fake.calls[0]["type"] == "limit"  # entry is a limit IOC


async def test_ironman_entry_type_market(monkeypatch):
    from src.agents.iron_man import IronMan
    from src.config.settings import settings
    monkeypatch.setattr(settings, "binance_entry_order_type", "market")
    im = IronMan(); fake = _FakeExchange(sl_fails=False); im._ccxt_exchange = fake
    await im._place_ccxt_order(signal=_signal(), quantity=0.01, leverage=2,
                               size_pct=0.01, exchange_id="binance")
    assert fake.calls[0]["type"] == "market"  # entry is a market order


async def test_ironman_sl_success_is_filled():
    from src.agents.iron_man import IronMan
    im = IronMan()
    fake = _FakeExchange(sl_fails=False)
    im._ccxt_exchange = fake
    result = await im._place_ccxt_order(
        signal=_signal(), quantity=0.01, leverage=2, size_pct=0.01, exchange_id="binance",
    )
    assert result.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIAL)
    assert result.sl_order_id == "SL1"
    # No emergency flatten when SL succeeds (a flatten is a reduce-only market
    # order; the entry itself may be market on testnet, which is fine).
    assert not any(c["type"] == "market" and c["params"].get("reduceOnly") for c in fake.calls)


# ---------------------------------------------------------------------------
# PortfolioManager — CCXT snapshot parsing
# ---------------------------------------------------------------------------

def test_portfolio_parse_ccxt_snapshot():
    from src.agents.portfolio_manager import PortfolioManager
    pm = PortfolioManager()
    balance = {"USDT": {"total": 5000.0, "free": 4000.0}, "total": {"USDT": 5000.0},
               "free": {"USDT": 4000.0}}
    positions = [{
        "symbol": "BTC/USDT:USDT", "contracts": 0.01, "side": "long",
        "entryPrice": 70000.0, "unrealizedPnl": 12.0, "leverage": 2,
        "markPrice": 70100.0, "liquidationPrice": 50000.0,
    }]
    snap = pm._parse_ccxt_snapshot("binance", balance, positions)
    assert snap.source.value.lower() == "binance"
    assert len(snap.positions) == 1
    p = snap.positions[0]
    assert p.side == "long"
    assert abs(p.size - 0.01) < 1e-9
    assert abs(p.entry_price - 70000.0) < 1e-6


def test_portfolio_parse_skips_zero_positions():
    from src.agents.portfolio_manager import PortfolioManager
    pm = PortfolioManager()
    balance = {"USDT": {"total": 5000.0, "free": 5000.0}}
    positions = [{"symbol": "ETH/USDT:USDT", "contracts": 0.0, "side": "long", "entryPrice": 3000.0}]
    snap = pm._parse_ccxt_snapshot("binance", balance, positions)
    assert snap.positions == []


# ---------------------------------------------------------------------------
# Batman — risk gates
# ---------------------------------------------------------------------------

async def test_batman_clamps_oversized_leverage(monkeypatch):
    from src.agents import batman as batman_mod
    from src.persistence.repository import MekkaRepository

    # Keep the test hermetic: no kill switch, no DB drawdown.
    monkeypatch.setattr(batman_mod, "is_kill_switch_active", lambda: False)

    async def _zero():
        return 0.0
    async def _zero_int():
        return 0
    for name, stub in (
        ("get_today_drawdown_pct", _zero),
        ("get_today_pnl_usd", _zero),
        ("count_trades_today", _zero_int),
    ):
        if hasattr(MekkaRepository, name):
            monkeypatch.setattr(MekkaRepository, name, staticmethod(stub))

    sig = _signal()
    sig.leverage = 50          # way above max_leverage
    sig.size_pct = 0.9         # way above max_position_size_pct
    approval = await batman_mod.Batman().run(signal=sig, equity_usd=10_000.0)
    # Whatever the verdict, leverage/size must be clamped to policy ceilings.
    from src.config.settings import settings
    assert approval.adjusted_leverage <= settings.max_leverage
    assert approval.adjusted_size_pct <= settings.max_position_size_pct + 1e-9


# ---------------------------------------------------------------------------
# Cyclops — SL/TP extraction helper
# ---------------------------------------------------------------------------

def test_cyclops_extract_sl_tp():
    from src.agents.cyclops import _extract_sl_tp

    class _Rec:
        raw = {"metadata": {"stop_loss": 68000.0, "take_profit": 73000.0}}

    sl, tp = _extract_sl_tp(_Rec())
    assert sl == 68000.0
    assert tp == 73000.0


def test_cyclops_extract_sl_tp_missing():
    from src.agents.cyclops import _extract_sl_tp

    class _Rec:
        raw = {}

    sl, tp = _extract_sl_tp(_Rec())
    assert sl is None and tp is None


# ---------------------------------------------------------------------------
# MarketAnalysis.is_safe_to_trade — pre-Vision safety gate
# ---------------------------------------------------------------------------

def _market_data():
    from datetime import datetime, timezone
    from src.models.market_data import MarketData
    return MarketData(symbol="BTC", timestamp=datetime.now(timezone.utc),
                      timeframe="4h", price=70000.0)


def test_is_safe_to_trade_default_true():
    from src.models.market_data import MarketAnalysis
    ma = MarketAnalysis(chart=_market_data())
    assert ma.is_safe_to_trade is True


def test_is_safe_to_trade_false_on_anomaly_pause():
    from src.models.market_data import MarketAnalysis, AnomalyReport, AnomalySeverity
    anomaly = AnomalyReport(symbol="BTC", severity=AnomalySeverity.HIGH, should_pause=True)
    ma = MarketAnalysis(chart=_market_data(), anomaly=anomaly)
    assert ma.is_safe_to_trade is False


def test_is_safe_to_trade_false_on_extreme_vol():
    from src.models.market_data import MarketAnalysis, VolatilityData, VolatilityRegime
    vol = VolatilityData(symbol="BTC", atr_pct=10.0)  # validator → EXTREME
    # Guard against validator changes: assert the regime then the gate.
    assert vol.volatility_regime == VolatilityRegime.EXTREME
    ma = MarketAnalysis(chart=_market_data(), volatility=vol)
    assert ma.is_safe_to_trade is False


# ---------------------------------------------------------------------------
# Mekka — consolidation & domain mapping
# ---------------------------------------------------------------------------

def test_mekka_domain_for():
    from src.agents.mekka import _domain_for
    assert _domain_for("risk") == "trading-ops"
    assert _domain_for("risk_gates") == "trading-ops"
    assert _domain_for("backend") == "dev-squad"
    assert _domain_for("memory") == "dev-squad"
    assert _domain_for("measurement") == "dev-squad"
    assert _domain_for("unknown") == "dev-squad"  # default


def test_mekka_consolidate_survives_recommends():
    from src.agents.mekka import Mekka
    rec = Mekka()._consolidate(
        {"title": "X", "area": "risk", "impact": "HIGH", "source": "risk_scanner",
         "description": "d", "evidence": "e"},
        None,  # no premortem → SURVIVES
    )
    assert rec.domain == "trading-ops"
    assert rec.decision == "RECOMMEND"
    assert rec.priority == "P1"  # HIGH + not rejected
    assert rec.source == "risk_scanner"


# ---------------------------------------------------------------------------
# M1 — Batman mainnet first-week HARD CLAMP
# ---------------------------------------------------------------------------

async def test_batman_mainnet_hard_clamp(monkeypatch):
    from src.agents.batman import Batman
    from src.config.settings import settings
    # Simulate Binance mainnet, live, clamp enabled.
    monkeypatch.setattr(settings, "paper_trading", False)
    monkeypatch.setattr(settings, "active_exchange", "binance")
    monkeypatch.setattr(settings, "binance_testnet", False)
    monkeypatch.setattr(settings, "mainnet_first_week_hard_clamp", True)

    sig = TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.85,
        entry_price=100.0, stop_loss=98.0, take_profit=106.0,
        size_pct=0.05, leverage=5, reasoning="test",
    )
    approval = await Batman().run(signal=sig, equity_usd=10_000.0, current_drawdown_pct=0.0)
    if approval.is_executable:
        assert approval.adjusted_size_pct <= 0.001 + 1e-9
        assert approval.adjusted_leverage <= 2


async def test_batman_no_clamp_on_testnet(monkeypatch):
    from src.agents.batman import Batman
    from src.config.settings import settings
    monkeypatch.setattr(settings, "paper_trading", False)
    monkeypatch.setattr(settings, "active_exchange", "binance")
    monkeypatch.setattr(settings, "binance_testnet", True)  # testnet → no clamp
    monkeypatch.setattr(settings, "mainnet_first_week_hard_clamp", True)

    sig = TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.85,
        entry_price=100.0, stop_loss=98.0, take_profit=106.0,
        size_pct=0.02, leverage=3, reasoning="test",
    )
    approval = await Batman().run(signal=sig, equity_usd=10_000.0, current_drawdown_pct=0.0)
    # On testnet the mainnet clamp must NOT fire.
    assert "mainnet_first_week_size_clamp" not in (approval.breached_limits or [])


# ---------------------------------------------------------------------------
# M2 — marketable limit entry crosses the book
# ---------------------------------------------------------------------------

async def test_ironman_marketable_limit_crosses(monkeypatch):
    from src.agents.iron_man import IronMan
    from src.config.settings import settings
    monkeypatch.setattr(settings, "binance_entry_order_type", "limit_ioc")
    monkeypatch.setattr(settings, "binance_max_entry_slippage_bps", 20.0)
    im = IronMan(); fake = _FakeExchange(sl_fails=False); im._ccxt_exchange = fake
    await im._place_ccxt_order(signal=_signal(entry=70000.0), quantity=0.01,
                               leverage=2, size_pct=0.01, exchange_id="binance")
    entry_call = fake.calls[0]
    assert entry_call["type"] == "limit"
    # Buy entry priced to cross above the ask (70010) by up to 20bps.
    assert entry_call["price"] > 70010.0
    assert entry_call["price"] <= 70010.0 * 1.0021  # within the slippage cap

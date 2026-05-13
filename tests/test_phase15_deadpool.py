"""
tests/test_phase15_deadpool.py
==============================
Phase 15 — Deadpool (Performance Analytics Agent, Story 034).

All tests use a FakeRepository (no DB) and call Deadpool._compute()
directly so the test suite is fast and deterministic.

Coverage:
  - PerformanceReport model fields and defaults
  - PerformanceVerdict: INSUFFICIENT_DATA, NOT_READY, READY
  - Win rate computation (with and without decided trades)
  - Sharpe estimate (only when days_with_data >= 5)
  - Max drawdown threshold
  - Signal actionable rate threshold
  - Batman approval rate (non-fallback actionable)
  - Wolverine endorsement rate (full HOLD, mixed, empty payload)
  - Per-symbol breakdown (top / bottom)
  - list_audit_by_event repository method exists
  - Deadpool.run() integration (mocked repo)
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.deadpool import (
    MAX_DRAWDOWN_PCT,
    MIN_ACTIONABLE_RATE_PCT,
    MIN_DAYS_REQUIRED,
    MIN_WIN_RATE_PCT,
    Deadpool,
)
from src.models.performance import PerformanceReport, PerformanceVerdict, SymbolStats


# ---------------------------------------------------------------------------
# Helpers — fake DB rows
# ---------------------------------------------------------------------------

def _daily(pnl: float = 0.0, drawdown: float = 0.0, trades: int = 1,
           wins: int = 0, losses: int = 0):
    row = MagicMock()
    row.pnl_usd = pnl
    row.drawdown_pct = drawdown
    row.trades_count = trades
    row.wins = wins
    row.losses = losses
    return row


def _trade(symbol: str = "BTC/USDT", pnl: float = 0.0, status: str = "FILLED"):
    row = MagicMock()
    row.symbol = symbol
    row.pnl_usd = pnl
    row.status = status
    return row


def _signal(is_actionable: bool = True, fallback: bool = False):
    row = MagicMock()
    row.is_actionable = is_actionable
    row.fallback = fallback
    return row


def _audit_recovery(positions: list):
    """Fake MONITOR_RECOVERY_PLAN audit row."""
    row = MagicMock()
    row.payload = json.dumps({"positions": positions})
    return row


def _make_deadpool():
    return Deadpool(repo=MagicMock())


# ---------------------------------------------------------------------------
# PerformanceReport model
# ---------------------------------------------------------------------------

class TestPerformanceReportModel:
    def test_defaults(self):
        r = PerformanceReport(window_days=30, days_with_data=0, total_trades=0)
        assert r.verdict == PerformanceVerdict.INSUFFICIENT_DATA
        assert r.win_rate_pct is None
        assert r.total_pnl_usd == 0.0
        assert r.notes == []
        assert r.top_symbols == []
        assert r.bottom_symbols == []

    def test_to_audit_payload(self):
        r = PerformanceReport(window_days=7, days_with_data=5, total_trades=10)
        payload = r.to_audit_payload()
        assert payload["window_days"] == 7
        assert payload["days_with_data"] == 5
        assert "verdict" in payload

    def test_symbol_stats_decided(self):
        s = SymbolStats(symbol="ETH/USDT", trades=10, wins=6, losses=4)
        assert s.decided == 10


# ---------------------------------------------------------------------------
# Verdict: INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestInsufficientData:
    def test_zero_days(self):
        dp = _make_deadpool()
        r = dp._compute(
            window_days=30,
            daily_rows=[],
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.verdict == PerformanceVerdict.INSUFFICIENT_DATA
        assert r.days_with_data == 0

    def test_below_min_days(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=10, trades=2, wins=1, losses=1)
                for _ in range(MIN_DAYS_REQUIRED - 1)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.verdict == PerformanceVerdict.INSUFFICIENT_DATA
        assert r.days_with_data == MIN_DAYS_REQUIRED - 1

    def test_exactly_min_days_transitions_to_verdict(self):
        dp = _make_deadpool()
        # MIN_DAYS_REQUIRED days, all profitable, good win rate
        rows = [_daily(pnl=50, drawdown=2.0, trades=4, wins=3, losses=1)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.verdict != PerformanceVerdict.INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Verdict: NOT_READY
# ---------------------------------------------------------------------------

class TestNotReady:
    def test_low_win_rate(self):
        dp = _make_deadpool()
        # 30% win rate — below MIN_WIN_RATE_PCT (45%)
        rows = [_daily(pnl=10, drawdown=2.0, trades=10, wins=3, losses=7)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.verdict == PerformanceVerdict.NOT_READY
        assert r.win_rate_pct == pytest.approx(30.0, rel=0.01)
        assert any("Win rate" in n for n in r.notes)

    def test_high_drawdown(self):
        dp = _make_deadpool()
        # Win rate OK but drawdown too high
        rows = [_daily(pnl=10, drawdown=20.0, trades=4, wins=3, losses=1)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.verdict == PerformanceVerdict.NOT_READY
        assert any("drawdown" in n.lower() for n in r.notes)
        assert r.max_drawdown_pct == pytest.approx(20.0)

    def test_low_signal_actionable_rate(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=10, drawdown=2.0, trades=4, wins=3, losses=1)
                for _ in range(MIN_DAYS_REQUIRED)]
        # Only 30% signals actionable — below MIN_ACTIONABLE_RATE_PCT (50%)
        signals = [_signal(is_actionable=True)] * 3 + [_signal(is_actionable=False)] * 7
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=signals,
            audit_rows=[],
        )
        assert r.verdict == PerformanceVerdict.NOT_READY
        assert r.signal_actionable_rate_pct == pytest.approx(30.0)
        assert any("actionable" in n.lower() for n in r.notes)


# ---------------------------------------------------------------------------
# Verdict: READY
# ---------------------------------------------------------------------------

class TestReady:
    def _good_rows(self, n=MIN_DAYS_REQUIRED):
        return [_daily(pnl=50, drawdown=2.0, trades=4, wins=3, losses=1)
                for _ in range(n)]

    def test_ready_all_thresholds_met(self):
        dp = _make_deadpool()
        rows = self._good_rows()
        signals = [_signal(is_actionable=True, fallback=False)] * 8 + \
                  [_signal(is_actionable=False)] * 2
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=signals,
            audit_rows=[],
        )
        assert r.verdict == PerformanceVerdict.READY
        assert any("All performance thresholds met" in n for n in r.notes)

    def test_ready_no_signal_rows_skips_threshold(self):
        """If no signals at all, actionable rate is None — should not trigger NOT_READY."""
        dp = _make_deadpool()
        rows = self._good_rows()
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.verdict == PerformanceVerdict.READY
        assert r.signal_actionable_rate_pct is None


# ---------------------------------------------------------------------------
# Win rate and PnL
# ---------------------------------------------------------------------------

class TestWinRateAndPnL:
    def test_win_rate_none_when_no_decided(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=0, trades=5, wins=0, losses=0)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.win_rate_pct is None

    def test_win_rate_computed_correctly(self):
        dp = _make_deadpool()
        # 6 wins, 4 losses across 2 days → 60%
        rows = [
            _daily(pnl=100, trades=6, wins=4, losses=2),
            _daily(pnl=50, trades=4, wins=2, losses=2),
        ] * (MIN_DAYS_REQUIRED // 2 + 1)
        rows = rows[:MIN_DAYS_REQUIRED]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        total_wins = sum(int(row.wins) for row in rows)
        total_losses = sum(int(row.losses) for row in rows)
        expected = 100.0 * total_wins / (total_wins + total_losses)
        assert r.win_rate_pct == pytest.approx(expected, rel=0.01)

    def test_total_pnl_summed(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=25.5, trades=1, wins=1, losses=0)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.total_pnl_usd == pytest.approx(25.5 * MIN_DAYS_REQUIRED, rel=1e-6)

    def test_avg_daily_pnl(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=10, trades=2, wins=1, losses=1) for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.avg_daily_pnl_usd == pytest.approx(10.0, rel=1e-6)

    def test_avg_daily_pnl_zero_when_no_data(self):
        dp = _make_deadpool()
        r = dp._compute(
            window_days=30,
            daily_rows=[],
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.avg_daily_pnl_usd == 0.0


# ---------------------------------------------------------------------------
# Sharpe estimate
# ---------------------------------------------------------------------------

class TestSharpeEstimate:
    def test_sharpe_none_when_few_days(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=10, trades=1, wins=1) for _ in range(4)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.sharpe_estimate is None

    def test_sharpe_computed_when_enough_days(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=10, drawdown=1.0, trades=2, wins=1, losses=1)
                for _ in range(10)]
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        # Constant returns → std = 0 → sharpe is None (division by zero guard)
        assert r.sharpe_estimate is None  # all same returns, std=0

    def test_sharpe_computed_with_variance(self):
        dp = _make_deadpool()
        # Alternating returns to create variance
        rows = (
            [_daily(pnl=20, drawdown=1.0, trades=2, wins=2)] * 5
            + [_daily(pnl=-5, drawdown=5.0, trades=2, wins=0, losses=2)] * 5
        )
        r = dp._compute(
            window_days=30,
            daily_rows=rows,
            trade_rows=[],
            signal_rows=[],
            audit_rows=[],
        )
        assert r.sharpe_estimate is not None
        # Manual sanity check
        returns = [20.0] * 5 + [-5.0] * 5
        mean_r = sum(returns) / 10
        variance = sum((x - mean_r) ** 2 for x in returns) / 10
        std_r = math.sqrt(variance)
        expected_sharpe = (mean_r / std_r) * math.sqrt(252)
        assert r.sharpe_estimate == pytest.approx(expected_sharpe, rel=0.001)


# ---------------------------------------------------------------------------
# Signal actionable and Batman approval rates
# ---------------------------------------------------------------------------

class TestSignalRates:
    def test_actionable_rate(self):
        dp = _make_deadpool()
        signals = [_signal(is_actionable=True)] * 7 + [_signal(is_actionable=False)] * 3
        rows = [_daily(pnl=10, drawdown=2, trades=2, wins=2)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows, trade_rows=[],
            signal_rows=signals, audit_rows=[],
        )
        assert r.signal_actionable_rate_pct == pytest.approx(70.0)

    def test_batman_approval_rate(self):
        dp = _make_deadpool()
        # 5 actionable non-fallback, 2 actionable fallback, 3 not actionable
        signals = (
            [_signal(is_actionable=True, fallback=False)] * 5
            + [_signal(is_actionable=True, fallback=True)] * 2
            + [_signal(is_actionable=False)] * 3
        )
        rows = [_daily(pnl=10, drawdown=2, trades=2, wins=2)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows, trade_rows=[],
            signal_rows=signals, audit_rows=[],
        )
        # 5 / 10 = 50%
        assert r.batman_approval_rate_pct == pytest.approx(50.0)

    def test_rates_none_when_no_signals(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=10, drawdown=2, trades=2, wins=2)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows, trade_rows=[],
            signal_rows=[], audit_rows=[],
        )
        assert r.signal_actionable_rate_pct is None
        assert r.batman_approval_rate_pct is None


# ---------------------------------------------------------------------------
# Wolverine SL endorsement rate
# ---------------------------------------------------------------------------

class TestWolverineEndorseRate:
    def test_none_when_no_audit_rows(self):
        dp = _make_deadpool()
        rows = [_daily(pnl=10, drawdown=2, trades=2, wins=2)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows, trade_rows=[],
            signal_rows=[], audit_rows=[],
        )
        assert r.wolverine_sl_endorse_rate_pct is None

    def test_100_pct_when_all_hold(self):
        dp = _make_deadpool()
        audit = [
            _audit_recovery([{"action": "HOLD", "symbol": "BTC/USDT"}]),
            _audit_recovery([{"action": "HOLD"}, {"action": "HOLD"}]),
        ]
        r = dp._compute(
            window_days=30,
            daily_rows=[_daily(pnl=10, drawdown=2, trades=2, wins=2)
                        for _ in range(MIN_DAYS_REQUIRED)],
            trade_rows=[], signal_rows=[], audit_rows=audit,
        )
        assert r.wolverine_sl_endorse_rate_pct == pytest.approx(100.0)

    def test_partial_endorsement(self):
        dp = _make_deadpool()
        audit = [
            _audit_recovery([{"action": "HOLD"}]),          # endorsed
            _audit_recovery([{"action": "CLOSE"}]),          # not endorsed
            _audit_recovery([{"action": "HOLD"}, {"action": "TIGHTEN_STOP"}]),  # not endorsed
            _audit_recovery([{"action": "HOLD"}]),           # endorsed
        ]
        r = dp._compute(
            window_days=30,
            daily_rows=[_daily(pnl=10, drawdown=2, trades=2, wins=2)
                        for _ in range(MIN_DAYS_REQUIRED)],
            trade_rows=[], signal_rows=[], audit_rows=audit,
        )
        # 2 of 4 cycles are all-HOLD
        assert r.wolverine_sl_endorse_rate_pct == pytest.approx(50.0)

    def test_empty_positions_list_counts_as_endorsed(self):
        dp = _make_deadpool()
        audit = [_audit_recovery([])]  # no open positions
        r = dp._compute(
            window_days=30,
            daily_rows=[_daily(pnl=10, drawdown=2, trades=2, wins=2)
                        for _ in range(MIN_DAYS_REQUIRED)],
            trade_rows=[], signal_rows=[], audit_rows=audit,
        )
        assert r.wolverine_sl_endorse_rate_pct == pytest.approx(100.0)

    def test_bad_payload_skipped_gracefully(self):
        dp = _make_deadpool()
        bad = MagicMock()
        bad.payload = "not valid json {"
        good = _audit_recovery([{"action": "HOLD"}])
        r = dp._compute(
            window_days=30,
            daily_rows=[_daily(pnl=10, drawdown=2, trades=2, wins=2)
                        for _ in range(MIN_DAYS_REQUIRED)],
            trade_rows=[], signal_rows=[], audit_rows=[bad, good],
        )
        # bad row skipped, good row counted → 1/1 = 100%
        assert r.wolverine_sl_endorse_rate_pct == pytest.approx(100.0)

    def test_null_payload_skipped(self):
        dp = _make_deadpool()
        null_row = MagicMock()
        null_row.payload = None
        good = _audit_recovery([{"action": "HOLD"}])
        r = dp._compute(
            window_days=30,
            daily_rows=[_daily(pnl=10, drawdown=2, trades=2, wins=2)
                        for _ in range(MIN_DAYS_REQUIRED)],
            trade_rows=[], signal_rows=[], audit_rows=[null_row, good],
        )
        assert r.wolverine_sl_endorse_rate_pct == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Per-symbol breakdown
# ---------------------------------------------------------------------------

class TestSymbolBreakdown:
    def test_top_symbols_sorted_by_pnl(self):
        dp = _make_deadpool()
        trades = [
            _trade("BTC/USDT", pnl=100, status="FILLED"),
            _trade("ETH/USDT", pnl=50, status="FILLED"),
            _trade("SOL/USDT", pnl=200, status="FILLED"),
            _trade("BTC/USDT", pnl=50, status="FILLED"),
        ]
        rows = [_daily(pnl=400, drawdown=2, trades=4, wins=4)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows,
            trade_rows=trades, signal_rows=[], audit_rows=[],
        )
        # SOL 200, BTC 150, ETH 50
        assert r.top_symbols[0].symbol == "SOL/USDT"
        assert r.top_symbols[1].symbol == "BTC/USDT"
        assert r.top_symbols[2].symbol == "ETH/USDT"
        assert r.top_symbols[0].total_pnl_usd == pytest.approx(200.0)

    def test_bottom_symbols(self):
        dp = _make_deadpool()
        trades = [
            _trade("A", pnl=100, status="FILLED"),
            _trade("B", pnl=50, status="FILLED"),
            _trade("C", pnl=-80, status="FILLED"),
            _trade("D", pnl=-10, status="FILLED"),
        ]
        rows = [_daily(pnl=60, drawdown=2, trades=4, wins=2, losses=2)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows,
            trade_rows=trades, signal_rows=[], audit_rows=[],
        )
        bottom_syms = [s.symbol for s in r.bottom_symbols]
        assert "C" in bottom_syms

    def test_no_bottom_when_3_or_fewer_symbols(self):
        dp = _make_deadpool()
        trades = [_trade("A", pnl=10), _trade("B", pnl=5)]
        rows = [_daily(pnl=15, drawdown=1, trades=2, wins=2)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows,
            trade_rows=trades, signal_rows=[], audit_rows=[],
        )
        assert r.bottom_symbols == []

    def test_symbol_win_rate_computed(self):
        dp = _make_deadpool()
        trades = [
            _trade("BTC/USDT", pnl=10, status="FILLED"),   # win
            _trade("BTC/USDT", pnl=10, status="FILLED"),   # win
            _trade("BTC/USDT", pnl=-5, status="FILLED"),   # loss
        ]
        rows = [_daily(pnl=15, drawdown=1, trades=3, wins=2, losses=1)
                for _ in range(MIN_DAYS_REQUIRED)]
        r = dp._compute(
            window_days=30, daily_rows=rows,
            trade_rows=trades, signal_rows=[], audit_rows=[],
        )
        btc = next(s for s in r.top_symbols if s.symbol == "BTC/USDT")
        assert btc.win_rate_pct == pytest.approx(66.67, rel=0.01)


# ---------------------------------------------------------------------------
# Repository — list_audit_by_event
# ---------------------------------------------------------------------------

class TestRepositoryListAuditByEvent:
    """Smoke test that the repository method exists and is callable."""

    def test_method_exists(self):
        from src.persistence.repository import MekkaRepository
        assert hasattr(MekkaRepository, "list_audit_by_event")
        assert callable(MekkaRepository.list_audit_by_event)


# ---------------------------------------------------------------------------
# Deadpool.run() — async integration (mocked repo)
# ---------------------------------------------------------------------------

class TestDeadpoolRun:
    @pytest.mark.asyncio
    async def test_run_returns_report(self):
        repo = MagicMock()
        repo.list_recent_daily_pnl = AsyncMock(
            return_value=[_daily(pnl=10, drawdown=2, trades=2, wins=1, losses=1)
                          for _ in range(MIN_DAYS_REQUIRED)]
        )
        repo.list_recent_trades = AsyncMock(return_value=[])
        repo.list_recent_signals = AsyncMock(return_value=[])
        repo.list_audit_by_event = AsyncMock(return_value=[])

        dp = Deadpool(repo=repo)
        report = await dp.run(window_days=30)

        assert isinstance(report, PerformanceReport)
        assert report.window_days == 30
        repo.list_audit_by_event.assert_called_once_with(
            "MONITOR_RECOVERY_PLAN", limit=2000
        )

    @pytest.mark.asyncio
    async def test_run_ready_verdict(self):
        repo = MagicMock()
        repo.list_recent_daily_pnl = AsyncMock(
            return_value=[_daily(pnl=50, drawdown=2, trades=4, wins=3, losses=1)
                          for _ in range(MIN_DAYS_REQUIRED)]
        )
        repo.list_recent_trades = AsyncMock(return_value=[])
        repo.list_recent_signals = AsyncMock(
            return_value=[_signal(is_actionable=True, fallback=False)] * 10
        )
        repo.list_audit_by_event = AsyncMock(return_value=[])

        dp = Deadpool(repo=repo)
        report = await dp.run(window_days=30)

        assert report.verdict == PerformanceVerdict.READY

    @pytest.mark.asyncio
    async def test_run_insufficient_data_verdict(self):
        repo = MagicMock()
        repo.list_recent_daily_pnl = AsyncMock(return_value=[])
        repo.list_recent_trades = AsyncMock(return_value=[])
        repo.list_recent_signals = AsyncMock(return_value=[])
        repo.list_audit_by_event = AsyncMock(return_value=[])

        dp = Deadpool(repo=repo)
        report = await dp.run(window_days=30)

        assert report.verdict == PerformanceVerdict.INSUFFICIENT_DATA

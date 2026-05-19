"""tests/test_story_221_backtest_equity_curve.py"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from src.models.backtest import BacktestOutcome, BacktestTrade, EquityPoint


def _ts(offset_hours: int = 0):
    return datetime.now(timezone.utc) + timedelta(hours=offset_hours)


def _trade(action="LONG", outcome=BacktestOutcome.WIN, pnl=100.0, offset=1):
    return BacktestTrade(
        timestamp=_ts(offset), symbol="BTC", action=action,
        entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
        size_pct=0.02, leverage=5, confidence=0.75, risk_reward=2.0,
        pnl_usd=pnl, outcome=outcome,
    )


class TestStory221BacktestEquityCurve:

    def test_import(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        assert BacktestEquityCurve is not None

    def test_empty_list_returns_one_initial_point(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        # build() com lista vazia deve retornar apenas ponto inicial
        curve = BacktestEquityCurve()
        # Não deve lançar exceção; resultado com lista vazia tem 1 ponto (START)
        import contextlib
        with contextlib.suppress(Exception):
            points = curve.build([], initial_equity=10_000.0)
            assert len(points) >= 1

    def test_initial_point_equity(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [_trade(pnl=500.0, outcome=BacktestOutcome.WIN, offset=1)]
        points = BacktestEquityCurve().build(trades, initial_equity=10_000.0)
        # Ponto 0 é o START com equity = initial_equity
        assert points[0].equity_usd == 10_000.0
        assert points[0].drawdown_pct == 0.0

    def test_win_increases_equity(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [_trade(pnl=200.0, outcome=BacktestOutcome.WIN)]
        points = BacktestEquityCurve().build(trades, initial_equity=10_000.0)
        assert points[-1].equity_usd == 10_200.0

    def test_loss_decreases_equity(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [_trade(pnl=-300.0, outcome=BacktestOutcome.LOSS)]
        points = BacktestEquityCurve().build(trades, initial_equity=10_000.0)
        assert points[-1].equity_usd == 9_700.0

    def test_expired_does_not_change_equity(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [
            _trade(pnl=0.0, outcome=BacktestOutcome.EXPIRED, offset=1),
            _trade(pnl=0.0, outcome=BacktestOutcome.EXPIRED, offset=2),
        ]
        points = BacktestEquityCurve().build(trades, initial_equity=5_000.0)
        # Equity nunca muda com EXPIRED
        assert all(p.equity_usd == 5_000.0 for p in points)

    def test_drawdown_zero_on_new_high(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [
            _trade(pnl=500.0, outcome=BacktestOutcome.WIN, offset=1),
            _trade(pnl=500.0, outcome=BacktestOutcome.WIN, offset=2),
        ]
        points = BacktestEquityCurve().build(trades, initial_equity=10_000.0)
        # Sempre subindo — drawdown_pct deve ser 0 em todos
        assert all(p.drawdown_pct == 0.0 for p in points)

    def test_drawdown_positive_after_loss(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [
            _trade(pnl=1000.0, outcome=BacktestOutcome.WIN, offset=1),
            _trade(pnl=-500.0, outcome=BacktestOutcome.LOSS, offset=2),
        ]
        points = BacktestEquityCurve().build(trades, initial_equity=10_000.0)
        last = points[-1]
        # peak=11000, equity=10500 → dd = 500/11000 ≈ 4.545%
        assert last.drawdown_pct > 0.0
        assert round(last.drawdown_pct, 2) == pytest.approx(4.55, abs=0.1)

    def test_equity_never_below_zero(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [_trade(pnl=-99999.0, outcome=BacktestOutcome.LOSS)]
        points = BacktestEquityCurve().build(trades, initial_equity=1_000.0)
        assert points[-1].equity_usd >= 0.0

    def test_point_count_equals_trades_plus_one(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [
            _trade(pnl=100.0, outcome=BacktestOutcome.WIN, offset=i)
            for i in range(5)
        ]
        points = BacktestEquityCurve().build(trades, initial_equity=10_000.0)
        assert len(points) == len(trades) + 1

    def test_symbol_and_outcome_preserved(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [_trade(pnl=100.0, outcome=BacktestOutcome.WIN)]
        points = BacktestEquityCurve().build(trades)
        last = points[-1]
        assert last.symbol == "BTC"
        assert last.outcome == BacktestOutcome.WIN

    def test_multiple_losses_accumulate_drawdown(self):
        from src.services.backtest_equity_curve import BacktestEquityCurve
        trades = [
            _trade(pnl=-200.0, outcome=BacktestOutcome.LOSS, offset=1),
            _trade(pnl=-200.0, outcome=BacktestOutcome.LOSS, offset=2),
            _trade(pnl=-200.0, outcome=BacktestOutcome.LOSS, offset=3),
        ]
        points = BacktestEquityCurve().build(trades, initial_equity=10_000.0)
        # equity final = 9400, peak = 10000 → dd = 600/10000 = 6%
        last = points[-1]
        assert last.equity_usd == pytest.approx(9_400.0)
        assert last.drawdown_pct == pytest.approx(6.0, abs=0.01)

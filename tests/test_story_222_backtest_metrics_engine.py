"""tests/test_story_222_backtest_metrics_engine.py"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from src.models.backtest import BacktestMetrics, BacktestOutcome, BacktestTrade, EquityPoint


def _ts(offset_hours: int = 0):
    return datetime.now(timezone.utc) + timedelta(hours=offset_hours)


def _trade(outcome=BacktestOutcome.WIN, pnl=100.0, rr=2.0, conf=0.75, offset=1):
    return BacktestTrade(
        timestamp=_ts(offset), symbol="BTC", action="LONG",
        entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
        size_pct=0.02, leverage=5, confidence=conf, risk_reward=rr,
        pnl_usd=pnl, outcome=outcome,
    )


def _point(equity=10_000.0, dd=0.0, offset=0):
    return EquityPoint(
        timestamp=_ts(offset),
        equity_usd=equity,
        trade_pnl_usd=0.0,
        drawdown_pct=dd,
        symbol="BTC",
        outcome=BacktestOutcome.WIN,
    )


class TestStory222BacktestMetricsEngine:

    def test_import(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        assert BacktestMetricsEngine is not None

    def test_empty_trades_returns_zeros(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        metrics = BacktestMetricsEngine().compute([], [_point()])
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.profit_factor == 0.0
        assert metrics.expectancy_usd == 0.0

    def test_win_rate_100_percent(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [_trade(outcome=BacktestOutcome.WIN, pnl=100.0, offset=i) for i in range(4)]
        eq = [_point()]
        metrics = BacktestMetricsEngine().compute(trades, eq)
        assert metrics.win_rate == pytest.approx(100.0)
        assert metrics.wins == 4
        assert metrics.losses == 0

    def test_win_rate_50_percent(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=100.0, offset=1),
            _trade(outcome=BacktestOutcome.WIN, pnl=100.0, offset=2),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-50.0, offset=3),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-50.0, offset=4),
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        assert metrics.win_rate == pytest.approx(50.0)

    def test_profit_factor(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=200.0, offset=1),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-100.0, offset=2),
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        # gross_profit=200, gross_loss=100 → PF=2.0
        assert metrics.profit_factor == pytest.approx(2.0)

    def test_expectancy_usd(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=300.0, offset=1),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-100.0, offset=2),
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        # total_pnl=200, total=2 → expectancy=100
        assert metrics.expectancy_usd == pytest.approx(100.0)

    def test_max_drawdown_from_equity_curve(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        # Simula peak=11000, valley=9500 → dd_usd=1500, dd_pct=13.6%
        eq_curve = [
            _point(equity=10_000.0, dd=0.0, offset=0),
            _point(equity=11_000.0, dd=0.0, offset=1),
            _point(equity=9_500.0, dd=13.636, offset=2),
        ]
        trades = [_trade(outcome=BacktestOutcome.WIN, pnl=100.0)]
        metrics = BacktestMetricsEngine().compute(trades, eq_curve, initial_equity=10_000.0)
        assert metrics.max_drawdown_usd == pytest.approx(1_500.0)
        assert metrics.max_drawdown_pct == pytest.approx(13.636, abs=0.01)

    def test_sharpe_ratio_positive_returns(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=100.0, offset=i)
            for i in range(10)
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        # Todos positivos e iguais → std=0 → Sharpe=0.0
        assert metrics.sharpe_ratio == 0.0

    def test_sortino_no_losses_returns_cap(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=100.0, offset=i)
            for i in range(5)
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        # Sem perdas → Sortino deve ser 999.0 (cap)
        assert metrics.sortino_ratio == pytest.approx(999.0)

    def test_sortino_with_losses(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=200.0, offset=1),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-100.0, offset=2),
            _trade(outcome=BacktestOutcome.WIN, pnl=150.0, offset=3),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-50.0, offset=4),
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        # Com perdas → Sortino > 0 (mean positivo > downside_std)
        assert metrics.sortino_ratio > 0.0

    def test_expired_excluded_from_metrics(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=100.0, offset=1),
            _trade(outcome=BacktestOutcome.EXPIRED, pnl=0.0, offset=2),
            _trade(outcome=BacktestOutcome.EXPIRED, pnl=0.0, offset=3),
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        assert metrics.total_trades == 1
        assert metrics.expired == 2
        assert metrics.win_rate == pytest.approx(100.0)

    def test_days_covered(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        # Dois trades com 7 dias de distância
        t1 = BacktestTrade(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            symbol="BTC", action="LONG",
            entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
            size_pct=0.02, leverage=5, confidence=0.75, risk_reward=2.0,
            pnl_usd=100.0, outcome=BacktestOutcome.WIN,
        )
        t2 = BacktestTrade(
            timestamp=datetime(2024, 1, 8, tzinfo=timezone.utc),
            symbol="BTC", action="LONG",
            entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
            size_pct=0.02, leverage=5, confidence=0.75, risk_reward=2.0,
            pnl_usd=100.0, outcome=BacktestOutcome.WIN,
        )
        metrics = BacktestMetricsEngine().compute([t1, t2], [_point()])
        assert metrics.days_covered == pytest.approx(7.0, abs=0.1)

    def test_avg_win_avg_loss(self):
        from src.services.backtest_metrics_engine import BacktestMetricsEngine
        trades = [
            _trade(outcome=BacktestOutcome.WIN, pnl=100.0, offset=1),
            _trade(outcome=BacktestOutcome.WIN, pnl=200.0, offset=2),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-50.0, offset=3),
            _trade(outcome=BacktestOutcome.LOSS, pnl=-150.0, offset=4),
        ]
        metrics = BacktestMetricsEngine().compute(trades, [_point()])
        assert metrics.avg_win_usd == pytest.approx(150.0)
        assert metrics.avg_loss_usd == pytest.approx(100.0)

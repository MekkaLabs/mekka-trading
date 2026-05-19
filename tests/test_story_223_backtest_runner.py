"""tests/test_story_223_backtest_runner.py"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.models.backtest import BacktestOutcome, BacktestSummary, BacktestTrade


def _fake_trade(offset=1, outcome=BacktestOutcome.WIN, pnl=100.0):
    return BacktestTrade(
        timestamp=datetime.now(timezone.utc) + timedelta(hours=offset),
        symbol="BTC", action="LONG",
        entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
        size_pct=0.02, leverage=5, confidence=0.75, risk_reward=2.0,
        pnl_usd=pnl, outcome=outcome,
    )


class TestStory223BacktestRunner:

    def test_import(self):
        from src.services.backtest_runner import BacktestRunner
        assert BacktestRunner is not None

    def test_init_defaults(self):
        from src.services.backtest_runner import BacktestRunner
        runner = BacktestRunner()
        assert runner._initial_equity == 10_000.0
        assert runner._seed is None
        assert runner._actionable_only is True

    def test_init_custom(self):
        from src.services.backtest_runner import BacktestRunner
        runner = BacktestRunner(initial_equity=5_000.0, seed=42, actionable_only=False)
        assert runner._initial_equity == 5_000.0
        assert runner._seed == 42
        assert runner._actionable_only is False

    @pytest.mark.asyncio
    async def test_run_empty_returns_summary(self):
        from src.services.backtest_runner import BacktestRunner
        runner = BacktestRunner(seed=1)
        with patch("src.services.backtest_signal_loader.BacktestSignalLoader.load", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = []
            summary = await runner.run("BTC", days=30)
        assert isinstance(summary, BacktestSummary)
        assert summary.symbol == "BTC"
        assert summary.metrics.total_trades == 0

    @pytest.mark.asyncio
    async def test_run_with_trades_returns_metrics(self):
        from src.services.backtest_runner import BacktestRunner
        fake_trades = [
            _fake_trade(offset=1, outcome=BacktestOutcome.WIN, pnl=200.0),
            _fake_trade(offset=2, outcome=BacktestOutcome.LOSS, pnl=-100.0),
            _fake_trade(offset=3, outcome=BacktestOutcome.WIN, pnl=150.0),
        ]
        runner = BacktestRunner(seed=42)
        with patch("src.services.backtest_signal_loader.BacktestSignalLoader.load", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = fake_trades
            summary = await runner.run("BTC", days=30)
        assert summary.metrics.total_trades > 0
        assert summary.final_equity_usd != summary.initial_equity_usd

    @pytest.mark.asyncio
    async def test_symbol_normalized(self):
        from src.services.backtest_runner import BacktestRunner
        runner = BacktestRunner(seed=0)
        captured_symbol = []

        async def fake_load(symbol, **kwargs):
            captured_symbol.append(symbol)
            return []

        with patch("src.services.backtest_signal_loader.BacktestSignalLoader.load", side_effect=fake_load):
            await runner.run("BTCUSDT", days=7)

        assert captured_symbol[0] == "BTC"

    def test_render_report_returns_markdown(self):
        from src.services.backtest_runner import BacktestRunner
        from src.models.backtest import BacktestMetrics, BacktestSummary
        summary = BacktestSummary(
            symbol="ETH",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            initial_equity_usd=10_000.0,
            final_equity_usd=11_500.0,
            metrics=BacktestMetrics(
                total_trades=10, wins=7, losses=3,
                win_rate=70.0, profit_factor=2.5,
                expectancy_usd=150.0, total_pnl_usd=1500.0,
                sharpe_ratio=1.23, sortino_ratio=2.45,
                max_drawdown_pct=5.0, max_drawdown_usd=500.0,
            ),
            equity_curve=[],
            trades=[],
            generated_at=datetime.now(timezone.utc),
        )
        report = BacktestRunner.render_report(summary)
        assert "# Backtest Report — ETH" in report
        assert "Win Rate" in report
        assert "Sharpe" in report
        assert "Drawdown" in report
        assert "70.00%" in report

    @pytest.mark.asyncio
    async def test_reproducible_with_seed(self):
        from src.services.backtest_runner import BacktestRunner
        fake_trades = [_fake_trade(offset=i) for i in range(10)]
        # trades já têm outcome=WIN/LOSS definido, mas simulador pode modificar se is_real=False
        # Testamos que seed produz o mesmo relatório duas vezes

        async def fake_load(symbol, **kwargs):
            return [_fake_trade(offset=i) for i in range(5)]

        with patch("src.services.backtest_signal_loader.BacktestSignalLoader.load", side_effect=fake_load):
            s1 = await BacktestRunner(seed=999).run("BTC", days=30)

        with patch("src.services.backtest_signal_loader.BacktestSignalLoader.load", side_effect=fake_load):
            s2 = await BacktestRunner(seed=999).run("BTC", days=30)

        assert s1.metrics.win_rate == s2.metrics.win_rate
        assert s1.metrics.total_pnl_usd == s2.metrics.total_pnl_usd

    def test_total_return_pct_property(self):
        from src.models.backtest import BacktestMetrics, BacktestSummary
        summary = BacktestSummary(
            symbol="BTC",
            initial_equity_usd=10_000.0,
            final_equity_usd=12_000.0,
            metrics=BacktestMetrics(),
            equity_curve=[],
            trades=[],
            generated_at=datetime.now(timezone.utc),
        )
        # (12000 - 10000) / 10000 * 100 = 20.0%
        assert summary.total_return_pct == pytest.approx(20.0)

    def test_cli_module_importable(self):
        import importlib
        mod = importlib.import_module("src.backtest.__main__")
        assert hasattr(mod, "main")
        assert hasattr(mod, "_build_parser")

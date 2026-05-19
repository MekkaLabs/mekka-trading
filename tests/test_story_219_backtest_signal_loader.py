"""
tests/test_story_219_backtest_signal_loader.py
================================================
Testes para Story 219 — BacktestSignalLoader (Milestone 35).
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_signal(action="LONG", symbol="BTC", days_ago=1, sig_id=1):
    ts = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta
    ts = ts - timedelta(days=days_ago)
    return {
        "id": sig_id, "timestamp": ts, "symbol": symbol,
        "action": action, "entry_price": 50000.0, "stop_loss": 48000.0,
        "take_profit": 54000.0, "size_pct": 0.02, "leverage": 5,
        "confidence": 0.75, "risk_reward": 2.0, "reasoning": "test",
    }


class TestStory219BacktestSignalLoader:

    def test_import(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        assert BacktestSignalLoader is not None

    def test_backtest_trade_model(self):
        from src.models.backtest import BacktestTrade, BacktestOutcome
        trade = BacktestTrade(
            timestamp=datetime.now(timezone.utc),
            symbol="BTC", action="LONG",
            entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
        )
        assert trade.is_actionable
        assert trade.outcome == BacktestOutcome.UNKNOWN
        assert trade.sl_distance_pct == pytest.approx(4.0, abs=0.01)
        assert trade.tp_distance_pct == pytest.approx(8.0, abs=0.01)

    def test_hold_not_actionable(self):
        from src.models.backtest import BacktestTrade
        t = BacktestTrade(
            timestamp=datetime.now(timezone.utc),
            symbol="BTC", action="HOLD",
            entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
        )
        assert not t.is_actionable

    @pytest.mark.asyncio
    async def test_load_returns_empty_on_db_error(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        loader = BacktestSignalLoader()
        with patch("src.services.backtest_signal_loader.BacktestSignalLoader._fetch_signals",
                   new_callable=AsyncMock, return_value=[]):
            with patch("src.services.backtest_signal_loader.BacktestSignalLoader._fetch_trades_by_signal_id",
                       new_callable=AsyncMock, return_value={}):
                result = await loader.load(symbol="BTC", days=30)
                assert result == []

    @pytest.mark.asyncio
    async def test_load_filters_hold_by_default(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        signals = [
            _make_signal("LONG", sig_id=1),
            _make_signal("HOLD", sig_id=2),
            _make_signal("SHORT", sig_id=3),
        ]
        loader = BacktestSignalLoader(actionable_only=True)
        with patch.object(loader, "_fetch_signals", new_callable=AsyncMock, return_value=signals), \
             patch.object(loader, "_fetch_trades_by_signal_id", new_callable=AsyncMock, return_value={}):
            result = await loader.load(symbol="BTC", days=30)
            assert len(result) == 2
            assert all(t.action in ("LONG", "SHORT") for t in result)

    @pytest.mark.asyncio
    async def test_load_includes_hold_when_disabled(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        signals = [_make_signal("LONG", sig_id=1), _make_signal("HOLD", sig_id=2)]
        loader = BacktestSignalLoader(actionable_only=False)
        with patch.object(loader, "_fetch_signals", new_callable=AsyncMock, return_value=signals), \
             patch.object(loader, "_fetch_trades_by_signal_id", new_callable=AsyncMock, return_value={}):
            result = await loader.load(symbol="BTC", days=30)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_real_pnl_attached_when_trade_exists(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        from src.models.backtest import BacktestOutcome
        signals = [_make_signal("LONG", sig_id=42)]
        trades_by_id = {42: {"id": 99, "pnl_usd": 150.0, "status": "PAPER", "signal_id": 42}}
        loader = BacktestSignalLoader()
        with patch.object(loader, "_fetch_signals", new_callable=AsyncMock, return_value=signals), \
             patch.object(loader, "_fetch_trades_by_signal_id", new_callable=AsyncMock, return_value=trades_by_id):
            result = await loader.load(symbol="BTC", days=30)
            assert len(result) == 1
            assert result[0].real_pnl_usd == pytest.approx(150.0)
            assert result[0].is_real
            assert result[0].outcome == BacktestOutcome.WIN

    @pytest.mark.asyncio
    async def test_loss_outcome_from_negative_pnl(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        from src.models.backtest import BacktestOutcome
        signals = [_make_signal("SHORT", sig_id=10)]
        trades_by_id = {10: {"id": 11, "pnl_usd": -80.0, "status": "PAPER", "signal_id": 10}}
        loader = BacktestSignalLoader()
        with patch.object(loader, "_fetch_signals", new_callable=AsyncMock, return_value=signals), \
             patch.object(loader, "_fetch_trades_by_signal_id", new_callable=AsyncMock, return_value=trades_by_id):
            result = await loader.load(symbol="SHORT", days=30)
            assert result[0].outcome == BacktestOutcome.LOSS

    @pytest.mark.asyncio
    async def test_sorted_by_timestamp(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        signals = [
            _make_signal("LONG", days_ago=5, sig_id=1),
            _make_signal("SHORT", days_ago=1, sig_id=2),
            _make_signal("LONG", days_ago=3, sig_id=3),
        ]
        loader = BacktestSignalLoader()
        with patch.object(loader, "_fetch_signals", new_callable=AsyncMock, return_value=signals), \
             patch.object(loader, "_fetch_trades_by_signal_id", new_callable=AsyncMock, return_value={}):
            result = await loader.load(symbol="BTC", days=30)
            timestamps = [t.timestamp for t in result]
            assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_never_raises(self):
        from src.services.backtest_signal_loader import BacktestSignalLoader
        loader = BacktestSignalLoader()
        with patch.object(loader, "_fetch_signals", new_callable=AsyncMock,
                          side_effect=RuntimeError("db explodiu")):
            result = await loader.load(symbol="BTC", days=30)
            assert result == []

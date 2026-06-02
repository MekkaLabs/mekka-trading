"""
tests/test_performance_tracker.py
==================================
Tests for the Be Water Framework StrategyPerformanceTracker.

Coverage
--------
- record_trade_outcome: creates new row, increments existing row
- record_trade_outcome: win and loss accounting
- record_trade_outcome: idempotency semantics (increments — caller dedups)
- get_performance: aggregates across regimes/symbols when None
- get_performance: filters by window_days (drops stale rows)
- get_top_strategies_for_regime: ranks by Sharpe / win_rate, filters min_trades
- compute_sharpe_ratio: returns None when too few trades
- compute_sharpe_ratio: respects metadata tagging

All tests use an in-memory SQLite via the ``mem_db`` fixture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import patch as _patch


# ---------------------------------------------------------------------------
# In-memory DB fixture (mirrors test_phase18 pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
async def mem_db():
    """Fresh in-memory SQLite engine per test."""
    from src.persistence import db as db_module

    await db_module.dispose()
    with _patch.object(
        db_module, "_resolve_db_url", return_value="sqlite+aiosqlite://"
    ):
        await db_module.init_engine()
        yield
    await db_module.dispose()


# ---------------------------------------------------------------------------
# record_trade_outcome
# ---------------------------------------------------------------------------


class TestRecordTradeOutcome:
    async def test_creates_new_row_on_first_call(self, mem_db):
        from src.services.strategy_performance_tracker import record_trade_outcome
        from src.persistence.db import get_session
        from src.persistence.strategy_performance import StrategyPerformance
        from sqlalchemy import select

        await record_trade_outcome(
            strategy_name="Scalp",
            regime="high_vol_choppy",
            symbol="BTC",
            pnl_usd=25.0,
            pnl_pct=0.5,
            won=True,
            timestamp=datetime.now(timezone.utc),
        )

        async with get_session() as s:
            rows = (
                (await s.execute(select(StrategyPerformance))).scalars().all()
            )
        assert len(rows) == 1
        r = rows[0]
        assert r.strategy_name == "Scalp"
        assert r.regime == "high_vol_choppy"
        assert r.symbol == "BTC"
        assert r.n_trades == 1
        assert r.n_wins == 1
        assert r.n_losses == 0
        assert r.total_pnl_usd == pytest.approx(25.0)
        assert r.sum_win_pnl_usd == pytest.approx(25.0)
        assert r.last_trade_at is not None

    async def test_increments_existing_row(self, mem_db):
        from src.services.strategy_performance_tracker import record_trade_outcome
        from src.persistence.db import get_session
        from src.persistence.strategy_performance import StrategyPerformance
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        await record_trade_outcome(
            "Scalp", "high_vol_choppy", "BTC", 10.0, 0.2, True, now
        )
        await record_trade_outcome(
            "Scalp", "high_vol_choppy", "BTC", -5.0, -0.1, False, now
        )
        await record_trade_outcome(
            "Scalp", "high_vol_choppy", "BTC", 20.0, 0.4, True, now
        )

        async with get_session() as s:
            rows = (
                (await s.execute(select(StrategyPerformance))).scalars().all()
            )
        assert len(rows) == 1
        r = rows[0]
        assert r.n_trades == 3
        assert r.n_wins == 2
        assert r.n_losses == 1
        assert r.total_pnl_usd == pytest.approx(25.0)
        assert r.sum_win_pnl_usd == pytest.approx(30.0)
        assert r.sum_loss_pnl_usd == pytest.approx(-5.0)
        # avg_win = 30/2 = 15, avg_loss = -5/1 = -5
        assert r.avg_win_pnl == pytest.approx(15.0)
        assert r.avg_loss_pnl == pytest.approx(-5.0)

    async def test_loss_updates_max_drawdown_pct(self, mem_db):
        from src.services.strategy_performance_tracker import record_trade_outcome
        from src.persistence.db import get_session
        from src.persistence.strategy_performance import StrategyPerformance
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        await record_trade_outcome(
            "Scalp", "high_vol_choppy", "BTC", -10.0, -1.0, False, now
        )
        await record_trade_outcome(
            "Scalp", "high_vol_choppy", "BTC", -3.0, -0.3, False, now
        )

        async with get_session() as s:
            r = (
                await s.execute(select(StrategyPerformance))
            ).scalar_one()
        # max_drawdown stays at the worst single trade
        assert r.max_drawdown_pct == pytest.approx(1.0)

    async def test_separate_rows_per_triple(self, mem_db):
        from src.services.strategy_performance_tracker import record_trade_outcome
        from src.persistence.db import get_session
        from src.persistence.strategy_performance import StrategyPerformance
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        await record_trade_outcome("Scalp", "high_vol_choppy", "BTC", 5, 0.1, True, now)
        await record_trade_outcome("Scalp", "high_vol_choppy", "ETH", 6, 0.1, True, now)
        await record_trade_outcome("Scalp", "breakout", "BTC", 7, 0.1, True, now)
        await record_trade_outcome("Swing", "high_vol_choppy", "BTC", 8, 0.1, True, now)

        async with get_session() as s:
            rows = (
                (await s.execute(select(StrategyPerformance))).scalars().all()
            )
        assert len(rows) == 4

    async def test_invalid_keys_are_skipped(self, mem_db):
        from src.services.strategy_performance_tracker import record_trade_outcome
        from src.persistence.db import get_session
        from src.persistence.strategy_performance import StrategyPerformance
        from sqlalchemy import select

        await record_trade_outcome("", "high_vol_choppy", "BTC", 1.0, 0.1, True, datetime.now(timezone.utc))
        await record_trade_outcome("Scalp", "", "BTC", 1.0, 0.1, True, datetime.now(timezone.utc))
        await record_trade_outcome("Scalp", "high_vol_choppy", "", 1.0, 0.1, True, datetime.now(timezone.utc))

        async with get_session() as s:
            rows = (
                (await s.execute(select(StrategyPerformance))).scalars().all()
            )
        assert rows == []


# ---------------------------------------------------------------------------
# get_performance
# ---------------------------------------------------------------------------


class TestGetPerformance:
    async def test_empty_returns_empty_summary(self, mem_db):
        from src.services.strategy_performance_tracker import get_performance

        s = await get_performance("Scalp", "high_vol_choppy", "BTC")
        assert s.n_trades == 0
        assert s.total_pnl_usd == 0.0
        assert s.win_rate == 0.0

    async def test_filtered_by_triple(self, mem_db):
        from src.services.strategy_performance_tracker import (
            get_performance,
            record_trade_outcome,
        )

        now = datetime.now(timezone.utc)
        await record_trade_outcome("Scalp", "high_vol_choppy", "BTC", 10, 0.2, True, now)
        await record_trade_outcome("Scalp", "high_vol_choppy", "ETH", 5, 0.1, True, now)

        s = await get_performance("Scalp", "high_vol_choppy", "BTC")
        assert s.n_trades == 1
        assert s.total_pnl_usd == pytest.approx(10.0)

    async def test_none_regime_aggregates_all_regimes(self, mem_db):
        from src.services.strategy_performance_tracker import (
            get_performance,
            record_trade_outcome,
        )

        now = datetime.now(timezone.utc)
        await record_trade_outcome("Scalp", "high_vol_choppy", "BTC", 10, 0.2, True, now)
        await record_trade_outcome("Scalp", "breakout", "BTC", 20, 0.3, True, now)

        s = await get_performance("Scalp", regime=None, symbol="BTC")
        assert s.n_trades == 2
        assert s.total_pnl_usd == pytest.approx(30.0)

    async def test_window_days_filters_stale_rows(self, mem_db):
        from src.services.strategy_performance_tracker import (
            get_performance,
            record_trade_outcome,
        )
        from src.persistence.db import get_session
        from src.persistence.strategy_performance import StrategyPerformance
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        await record_trade_outcome("Scalp", "high_vol_choppy", "BTC", 10, 0.2, True, now)

        # Backdate the row to 60d ago
        old = now - timedelta(days=60)
        async with get_session() as s:
            row = (
                await s.execute(select(StrategyPerformance))
            ).scalar_one()
            row.last_trade_at = old
            await s.commit()

        # window_days=30 → stale row dropped
        s30 = await get_performance("Scalp", "high_vol_choppy", "BTC", window_days=30)
        assert s30.n_trades == 0
        # window_days=90 → still visible
        s90 = await get_performance("Scalp", "high_vol_choppy", "BTC", window_days=90)
        assert s90.n_trades == 1


# ---------------------------------------------------------------------------
# get_top_strategies_for_regime
# ---------------------------------------------------------------------------


class TestGetTopStrategies:
    async def test_empty_regime_returns_empty(self, mem_db):
        from src.services.strategy_performance_tracker import (
            get_top_strategies_for_regime,
        )

        result = await get_top_strategies_for_regime("high_vol_choppy")
        assert result == []

    async def test_filters_min_trades(self, mem_db):
        from src.services.strategy_performance_tracker import (
            get_top_strategies_for_regime,
            record_trade_outcome,
        )

        now = datetime.now(timezone.utc)
        # Strategy with only 3 trades — below default min_trades=10
        for _ in range(3):
            await record_trade_outcome(
                "RareStrategy", "high_vol_choppy", "BTC", 5.0, 0.1, True, now
            )

        result = await get_top_strategies_for_regime(
            "high_vol_choppy", min_trades=10
        )
        assert result == []

        # Lower min_trades — should appear
        result2 = await get_top_strategies_for_regime(
            "high_vol_choppy", min_trades=2
        )
        assert len(result2) == 1
        assert result2[0].strategy_name == "RareStrategy"

    async def test_ranks_by_winrate_fallback_when_sharpe_none(self, mem_db):
        from src.services.strategy_performance_tracker import (
            get_top_strategies_for_regime,
            record_trade_outcome,
        )
        from src.persistence.db import get_session
        from src.persistence.strategy_performance import StrategyPerformance
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        # Strategy A: 8 wins, 2 losses
        for _ in range(8):
            await record_trade_outcome("A", "high_vol_choppy", "BTC", 10, 0.1, True, now)
        for _ in range(2):
            await record_trade_outcome("A", "high_vol_choppy", "BTC", -5, -0.1, False, now)

        # Strategy B: 5 wins, 5 losses
        for _ in range(5):
            await record_trade_outcome("B", "high_vol_choppy", "BTC", 10, 0.1, True, now)
        for _ in range(5):
            await record_trade_outcome("B", "high_vol_choppy", "BTC", -5, -0.1, False, now)

        # Force sharpe to None so we test win-rate fallback specifically
        async with get_session() as s:
            for row in (await s.execute(select(StrategyPerformance))).scalars().all():
                row.sharpe_ratio = None
            await s.commit()

        result = await get_top_strategies_for_regime(
            "high_vol_choppy", limit=5, min_trades=5
        )
        assert len(result) == 2
        assert result[0].strategy_name == "A"  # higher win rate
        assert result[1].strategy_name == "B"

    async def test_respects_limit(self, mem_db):
        from src.services.strategy_performance_tracker import (
            get_top_strategies_for_regime,
            record_trade_outcome,
        )

        now = datetime.now(timezone.utc)
        for name in ("A", "B", "C", "D", "E"):
            for _ in range(10):
                await record_trade_outcome(
                    name, "high_vol_choppy", "BTC", 5.0, 0.1, True, now
                )

        result = await get_top_strategies_for_regime(
            "high_vol_choppy", limit=2, min_trades=5
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# compute_sharpe_ratio
# ---------------------------------------------------------------------------


class TestComputeSharpe:
    async def test_returns_none_when_no_trades(self, mem_db):
        from src.services.strategy_performance_tracker import compute_sharpe_ratio

        v = await compute_sharpe_ratio("Scalp", "high_vol_choppy", "BTC")
        assert v is None

    async def test_returns_none_when_below_min_trades(self, mem_db):
        from src.services.strategy_performance_tracker import compute_sharpe_ratio
        from src.persistence.db import get_session
        from src.persistence.models import TradeRecord

        now = datetime.now(timezone.utc)
        async with get_session() as s:
            for i in range(5):
                s.add(
                    TradeRecord(
                        timestamp=now,
                        symbol="BTC",
                        status="FILLED",
                        is_paper=True,
                        quantity=1.0,
                        avg_price=100.0,
                        pnl_usd=float(i + 1),
                        raw={"metadata": {"strategy_name": "Scalp", "regime": "high_vol_choppy"}},
                    )
                )
            await s.commit()

        v = await compute_sharpe_ratio(
            "Scalp", "high_vol_choppy", "BTC", min_trades=10
        )
        assert v is None

    async def test_returns_sharpe_when_enough_tagged_trades(self, mem_db):
        from src.services.strategy_performance_tracker import compute_sharpe_ratio
        from src.persistence.db import get_session
        from src.persistence.models import TradeRecord

        now = datetime.now(timezone.utc)
        # 12 trades with positive but variable PnL — Sharpe should be >0
        pnls = [10.0, 8.0, 12.0, 7.0, 11.0, 9.0, 13.0, 6.0, 10.5, 8.5, 11.5, 9.5]
        async with get_session() as s:
            for p in pnls:
                s.add(
                    TradeRecord(
                        timestamp=now,
                        symbol="BTC",
                        status="FILLED",
                        is_paper=True,
                        quantity=1.0,
                        avg_price=100.0,
                        pnl_usd=p,
                        raw={"metadata": {"strategy_name": "Scalp", "regime": "high_vol_choppy"}},
                    )
                )
            await s.commit()

        v = await compute_sharpe_ratio(
            "Scalp", "high_vol_choppy", "BTC", min_trades=10
        )
        assert v is not None
        assert v > 0

    async def test_returns_none_when_zero_stddev(self, mem_db):
        from src.services.strategy_performance_tracker import compute_sharpe_ratio
        from src.persistence.db import get_session
        from src.persistence.models import TradeRecord

        now = datetime.now(timezone.utc)
        async with get_session() as s:
            for _ in range(12):
                s.add(
                    TradeRecord(
                        timestamp=now,
                        symbol="BTC",
                        status="FILLED",
                        is_paper=True,
                        quantity=1.0,
                        avg_price=100.0,
                        pnl_usd=5.0,  # constant — zero stddev
                        raw={"metadata": {"strategy_name": "Scalp", "regime": "high_vol_choppy"}},
                    )
                )
            await s.commit()

        v = await compute_sharpe_ratio(
            "Scalp", "high_vol_choppy", "BTC", min_trades=10
        )
        assert v is None

    async def test_filters_by_metadata_strategy(self, mem_db):
        from src.services.strategy_performance_tracker import compute_sharpe_ratio
        from src.persistence.db import get_session
        from src.persistence.models import TradeRecord

        now = datetime.now(timezone.utc)
        async with get_session() as s:
            # 12 trades tagged "Other" — should be skipped
            for _ in range(12):
                s.add(
                    TradeRecord(
                        timestamp=now,
                        symbol="BTC",
                        status="FILLED",
                        is_paper=True,
                        quantity=1.0,
                        avg_price=100.0,
                        pnl_usd=5.0,
                        raw={"metadata": {"strategy_name": "Other", "regime": "high_vol_choppy"}},
                    )
                )
            await s.commit()

        v = await compute_sharpe_ratio(
            "Scalp", "high_vol_choppy", "BTC", min_trades=10
        )
        assert v is None  # tagged trades belong to "Other", not "Scalp"

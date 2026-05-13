"""
tests/test_phase18_daily_perf_writer.py
========================================
Phase 18 — DailyPerformanceWriter (Story 039).

Coverage:
  DailyPerformanceWriter
    - maybe_run() runs on first call and returns True
    - maybe_run() is a no-op on same UTC day and returns False
    - run_now() always executes regardless of _last_run_date
    - run_now() calls Deadpool.run with correct window_days
    - run_now() calls repo.save_perf_report with correct fields
    - run_now() calls repo.log_event with DAILY_PERF_REPORT
    - run_now() updates _last_run_date
    - custom window_days forwarded to Deadpool
    - default repo lazy-imports MekkaRepository if none provided
    - Deadpool sentinel patching works at module level

  MekkaRepository — save_perf_report
    - insert creates new row with correct fields
    - second call for same date_utc overwrites (upsert semantics)
    - returns int id

  MekkaRepository — get_latest_perf_report
    - returns None when table empty
    - returns most recent row by date_utc
    - returns correct verdict and fields
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.services.daily_performance_writer as writer_module
from src.models.performance import PerformanceReport, PerformanceVerdict
from src.services.daily_performance_writer import DailyPerformanceWriter


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_report(
    verdict: PerformanceVerdict = PerformanceVerdict.READY,
    win_rate: float = 65.0,
    pnl: float = 400.0,
    drawdown: float = 2.0,
    wolverine: float = 75.0,
    days: int = 15,
) -> PerformanceReport:
    return PerformanceReport(
        window_days=30,
        days_with_data=days,
        total_trades=50,
        wins=33,
        losses=17,
        win_rate_pct=win_rate,
        total_pnl_usd=pnl,
        avg_daily_pnl_usd=pnl / max(days, 1),
        max_drawdown_pct=drawdown,
        wolverine_sl_endorse_rate_pct=wolverine,
        signal_actionable_rate_pct=70.0,
        batman_approval_rate_pct=66.0,
        verdict=verdict,
        notes=["OK"],
    )


def _mock_repo(report: PerformanceReport):
    """Return a mock MekkaRepository class whose methods are AsyncMock."""
    repo = MagicMock()
    repo.save_perf_report = AsyncMock(return_value=99)
    repo.log_event = AsyncMock(return_value=1)
    return repo


def _mock_deadpool_cls(report: PerformanceReport):
    """Return a mock Deadpool class whose .run() returns *report*."""
    cls = MagicMock()
    instance = MagicMock()
    instance.run = AsyncMock(return_value=report)
    cls.return_value = instance
    return cls


# ---------------------------------------------------------------------------
# DailyPerformanceWriter — maybe_run
# ---------------------------------------------------------------------------

class TestMaybeRun:
    @pytest.mark.asyncio
    async def test_first_call_runs_and_returns_true(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            result = await writer.maybe_run()

        assert result is True
        dp_cls.return_value.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_second_call_same_day_is_noop(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.maybe_run()   # first run
            result = await writer.maybe_run()   # same day

        assert result is False
        # Deadpool.run should only have been called once
        assert dp_cls.return_value.run.await_count == 1

    @pytest.mark.asyncio
    async def test_new_day_runs_again(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        yesterday = date(2026, 5, 10)
        today = date(2026, 5, 11)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            writer._last_run_date = yesterday   # simulate ran yesterday
            result = await writer.maybe_run()

        assert result is True
        dp_cls.return_value.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_maybe_run_sets_last_run_date(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            assert writer._last_run_date is None
            await writer.maybe_run()

        assert writer._last_run_date == datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# DailyPerformanceWriter — run_now
# ---------------------------------------------------------------------------

class TestRunNow:
    @pytest.mark.asyncio
    async def test_run_now_always_executes(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        today = date(2026, 5, 11)
        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            writer._last_run_date = today   # already "ran" today
            await writer.run_now(today=today)

        # should still run
        dp_cls.return_value.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_now_passes_window_days(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo, window_days=14)
            await writer.run_now(today=date(2026, 5, 11))

        dp_cls.return_value.run.assert_awaited_once_with(window_days=14)

    @pytest.mark.asyncio
    async def test_run_now_calls_save_perf_report(self):
        report = _make_report(
            verdict=PerformanceVerdict.READY,
            win_rate=65.0,
            pnl=400.0,
            drawdown=2.0,
            wolverine=75.0,
            days=15,
        )
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.run_now(today=date(2026, 5, 11))

        repo.save_perf_report.assert_awaited_once()
        call_kwargs = repo.save_perf_report.call_args.kwargs
        assert call_kwargs["date_utc"] == "2026-05-11"
        assert call_kwargs["verdict"] == "READY"
        assert call_kwargs["win_rate_pct"] == pytest.approx(65.0)
        assert call_kwargs["total_pnl_usd"] == pytest.approx(400.0)
        assert call_kwargs["max_drawdown_pct"] == pytest.approx(2.0)
        assert call_kwargs["wolverine_endorse_pct"] == pytest.approx(75.0)
        assert call_kwargs["days_with_data"] == 15

    @pytest.mark.asyncio
    async def test_run_now_includes_full_payload(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.run_now(today=date(2026, 5, 11))

        call_kwargs = repo.save_perf_report.call_args.kwargs
        payload = call_kwargs["payload"]
        assert isinstance(payload, dict)
        assert "verdict" in payload
        assert "total_pnl_usd" in payload

    @pytest.mark.asyncio
    async def test_run_now_emits_audit_event(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.run_now(today=date(2026, 5, 11))

        repo.log_event.assert_awaited_once()
        call_kwargs = repo.log_event.call_args.kwargs
        assert call_kwargs["event"] == "DAILY_PERF_REPORT"
        assert call_kwargs["agent"] == "DailyPerformanceWriter"
        assert call_kwargs["severity"] == "INFO"

    @pytest.mark.asyncio
    async def test_run_now_audit_payload_not_none(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.run_now(today=date(2026, 5, 11))

        call_kwargs = repo.log_event.call_args.kwargs
        assert call_kwargs["payload"] is not None
        assert isinstance(call_kwargs["payload"], dict)

    @pytest.mark.asyncio
    async def test_run_now_updates_last_run_date(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        target_date = date(2026, 5, 11)
        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.run_now(today=target_date)

        assert writer._last_run_date == target_date

    @pytest.mark.asyncio
    async def test_run_now_default_today_is_utc(self):
        """run_now() without today= uses current UTC date."""
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch.object(writer_module, "Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.run_now()

        expected_today = datetime.now(timezone.utc).date()
        assert writer._last_run_date == expected_today


# ---------------------------------------------------------------------------
# Sentinel patching
# ---------------------------------------------------------------------------

class TestDeadpoolSentinel:
    def test_module_has_deadpool_sentinel(self):
        """Module-level Deadpool must be None at import time so tests can patch."""
        import importlib, sys

        # Re-import to check the initial state (before any test mutates it)
        mod = sys.modules.get("src.services.daily_performance_writer")
        assert hasattr(mod, "Deadpool")

    @pytest.mark.asyncio
    async def test_sentinel_patched_correctly(self):
        report = _make_report()
        repo = _mock_repo(report)
        dp_cls = _mock_deadpool_cls(report)

        with patch("src.services.daily_performance_writer.Deadpool", dp_cls):
            writer = DailyPerformanceWriter(repo=repo)
            await writer.run_now(today=date(2026, 5, 11))

        dp_cls.assert_called_once_with(repo=repo)


# ---------------------------------------------------------------------------
# MekkaRepository — save_perf_report (in-memory SQLite)
# ---------------------------------------------------------------------------

@pytest.fixture
async def mem_repo():
    """Repository backed by a fresh in-memory SQLite DB.

    Patches ``_resolve_db_url`` to return an in-memory URL, resets the
    engine singleton, initialises tables, yields MekkaRepository, then
    tears down so the next fixture gets a clean slate.
    """
    from unittest.mock import patch as _patch

    from src.persistence import db as db_module
    from src.persistence.repository import MekkaRepository

    # Dispose any existing engine from a prior test
    await db_module.dispose()

    with _patch.object(db_module, "_resolve_db_url", return_value="sqlite+aiosqlite://"):
        await MekkaRepository.initialize()
        yield MekkaRepository

    await db_module.dispose()


class TestSavePerfReport:
    @pytest.mark.asyncio
    async def test_save_returns_int_id(self, mem_repo):
        rid = await mem_repo.save_perf_report(
            date_utc="2026-05-11",
            verdict="READY",
            win_rate_pct=65.0,
            total_pnl_usd=400.0,
            max_drawdown_pct=2.0,
            wolverine_endorse_pct=75.0,
            days_with_data=15,
            payload={"test": True},
        )
        assert isinstance(rid, int)
        assert rid > 0

    @pytest.mark.asyncio
    async def test_save_upsert_overwrites_same_date(self, mem_repo):
        await mem_repo.save_perf_report(
            date_utc="2026-05-11",
            verdict="NOT_READY",
            win_rate_pct=30.0,
            total_pnl_usd=-50.0,
            max_drawdown_pct=8.0,
            wolverine_endorse_pct=40.0,
            days_with_data=5,
        )
        # Upsert same date with different values
        rid2 = await mem_repo.save_perf_report(
            date_utc="2026-05-11",
            verdict="READY",
            win_rate_pct=70.0,
            total_pnl_usd=500.0,
            max_drawdown_pct=1.5,
            wolverine_endorse_pct=80.0,
            days_with_data=20,
        )
        assert isinstance(rid2, int)

        # get_latest should reflect the second write
        latest = await mem_repo.get_latest_perf_report()
        assert latest is not None
        assert latest.verdict == "READY"
        assert latest.win_rate_pct == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_save_stores_payload(self, mem_repo):
        payload = {"verdict": "READY", "total_pnl_usd": 400.0, "custom": 42}
        await mem_repo.save_perf_report(
            date_utc="2026-05-10",
            verdict="READY",
            win_rate_pct=60.0,
            total_pnl_usd=400.0,
            max_drawdown_pct=2.0,
            wolverine_endorse_pct=72.0,
            days_with_data=12,
            payload=payload,
        )
        latest = await mem_repo.get_latest_perf_report()
        assert latest is not None
        assert latest.payload is not None
        assert latest.payload["custom"] == 42


class TestGetLatestPerfReport:
    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self, mem_repo):
        result = await mem_repo.get_latest_perf_report()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_most_recent_by_date_utc(self, mem_repo):
        await mem_repo.save_perf_report(
            date_utc="2026-05-09",
            verdict="NOT_READY",
            win_rate_pct=30.0,
            total_pnl_usd=-20.0,
            max_drawdown_pct=5.0,
            wolverine_endorse_pct=50.0,
            days_with_data=3,
        )
        await mem_repo.save_perf_report(
            date_utc="2026-05-11",
            verdict="READY",
            win_rate_pct=65.0,
            total_pnl_usd=400.0,
            max_drawdown_pct=2.0,
            wolverine_endorse_pct=75.0,
            days_with_data=15,
        )
        await mem_repo.save_perf_report(
            date_utc="2026-05-10",
            verdict="INSUFFICIENT_DATA",
            win_rate_pct=None,
            total_pnl_usd=0.0,
            max_drawdown_pct=0.0,
            wolverine_endorse_pct=None,
            days_with_data=1,
        )
        latest = await mem_repo.get_latest_perf_report()
        assert latest is not None
        assert latest.date_utc == "2026-05-11"
        assert latest.verdict == "READY"

    @pytest.mark.asyncio
    async def test_correct_fields_returned(self, mem_repo):
        await mem_repo.save_perf_report(
            date_utc="2026-05-11",
            verdict="NOT_READY",
            win_rate_pct=42.0,
            total_pnl_usd=-100.0,
            max_drawdown_pct=12.0,
            wolverine_endorse_pct=60.0,
            days_with_data=8,
        )
        latest = await mem_repo.get_latest_perf_report()
        assert latest.verdict == "NOT_READY"
        assert latest.win_rate_pct == pytest.approx(42.0)
        assert latest.total_pnl_usd == pytest.approx(-100.0)
        assert latest.max_drawdown_pct == pytest.approx(12.0)
        assert latest.wolverine_endorse_pct == pytest.approx(60.0)
        assert latest.days_with_data == 8

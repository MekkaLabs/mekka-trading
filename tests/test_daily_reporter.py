"""
tests/test_daily_reporter.py
=============================
Unit tests for src/dashboard/daily_reporter.py

Covers:
- build_telegram_message formatting (positive / negative / zero PnL)
- build_slack_blocks structure (required keys present)
- DailyReporter.send_daily_report:
  - success (Slack + Telegram)
  - no targets configured → skipped
  - same-day dedup → skipped
  - force=True bypasses dedup
  - DB timeout → error key
  - webhook failure (both targets down) → sent_* False, no dedup mark
- DailyReporter.has_targets property
- _sleep_until_report_time: always returns a future time

Run with:
    pytest tests/test_daily_reporter.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Pure formatting tests (no I/O)
# ---------------------------------------------------------------------------


def _today_stub(pnl=123.45, equity=10_000.0, trades=5, wins=3, losses=2, wr=0.6, dd=0.02):
    return {
        "pnl_usd": pnl,
        "latest_equity_usd": equity,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "max_drawdown_pct": dd,
    }


def _alltime_stub(pnl=500.0, days=30, trades=40, wr=0.55):
    return {
        "pnl_usd": pnl,
        "trading_days": days,
        "trades": trades,
        "win_rate": wr,
    }


class TestBuildTelegramMessage:
    def test_positive_pnl_contains_green_emoji(self):
        from src.dashboard.daily_reporter import build_telegram_message
        msg = build_telegram_message(_today_stub(pnl=50.0), _alltime_stub(), "2026-05-11")
        assert "🟢" in msg
        assert "$+50.00" in msg

    def test_negative_pnl_contains_red_emoji(self):
        from src.dashboard.daily_reporter import build_telegram_message
        msg = build_telegram_message(_today_stub(pnl=-30.0), _alltime_stub(), "2026-05-11")
        assert "🔴" in msg
        assert "$-30.00" in msg

    def test_zero_pnl_neutral_emoji(self):
        from src.dashboard.daily_reporter import build_telegram_message
        msg = build_telegram_message(_today_stub(pnl=0.0), _alltime_stub(), "2026-05-11")
        assert "⚪" in msg

    def test_high_drawdown_shows_alert(self):
        from src.dashboard.daily_reporter import build_telegram_message
        msg = build_telegram_message(_today_stub(dd=0.12), _alltime_stub(), "2026-05-11")
        assert "🚨" in msg

    def test_medium_drawdown_shows_warning(self):
        from src.dashboard.daily_reporter import build_telegram_message
        msg = build_telegram_message(_today_stub(dd=0.07), _alltime_stub(), "2026-05-11")
        assert "⚠️" in msg

    def test_none_win_rate_shows_na(self):
        from src.dashboard.daily_reporter import build_telegram_message
        today = _today_stub()
        today["win_rate"] = None
        msg = build_telegram_message(today, _alltime_stub(), "2026-05-11")
        assert "n/a" in msg

    def test_date_present_in_header(self):
        from src.dashboard.daily_reporter import build_telegram_message
        msg = build_telegram_message(_today_stub(), _alltime_stub(), "2026-05-11")
        assert "2026-05-11" in msg


class TestBuildSlackBlocks:
    def test_returns_blocks_key(self):
        from src.dashboard.daily_reporter import build_slack_blocks
        payload = build_slack_blocks(_today_stub(), _alltime_stub(), "2026-05-11")
        assert "blocks" in payload
        assert isinstance(payload["blocks"], list)
        assert len(payload["blocks"]) > 0

    def test_header_block_present(self):
        from src.dashboard.daily_reporter import build_slack_blocks
        payload = build_slack_blocks(_today_stub(), _alltime_stub(), "2026-05-11")
        types = [b["type"] for b in payload["blocks"]]
        assert "header" in types

    def test_header_contains_date(self):
        from src.dashboard.daily_reporter import build_slack_blocks
        payload = build_slack_blocks(_today_stub(), _alltime_stub(), "2026-05-11")
        header = next(b for b in payload["blocks"] if b["type"] == "header")
        assert "2026-05-11" in header["text"]["text"]


# ---------------------------------------------------------------------------
# DailyReporter behaviour tests (mocked I/O)
# ---------------------------------------------------------------------------


def _make_summary(pnl=100.0, trades=5):
    return {
        "window": {
            "pnl_usd": pnl,
            "latest_equity_usd": 10_000.0,
            "trades": trades,
            "wins": 3,
            "losses": 2,
            "win_rate": 0.6,
            "max_drawdown_pct": 0.02,
        },
        "all_time": {
            "pnl_usd": 500.0,
            "trading_days": 30,
            "trades": 40,
            "win_rate": 0.55,
        },
    }


class TestDailyReporterSend:
    @pytest.fixture()
    def env_with_targets(self, monkeypatch):
        monkeypatch.setenv("MEKKA_WEBHOOK_SLACK", "https://hooks.slack.com/test")
        monkeypatch.setenv("MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN", "123:ABC")
        monkeypatch.setenv("MEKKA_WEBHOOK_TELEGRAM_CHAT_ID", "-100")
        # Reload module-level vars by re-importing after env change
        import importlib
        import src.dashboard.daily_reporter as m
        importlib.reload(m)
        yield m
        importlib.reload(m)  # cleanup

    def _make_reporter(self, module, repo_mock):
        reporter = module.DailyReporter(repo=repo_mock)
        reporter._post_with_retry = AsyncMock(return_value=True)
        return reporter

    @pytest.mark.asyncio
    async def test_sends_both_targets(self, env_with_targets):
        m = env_with_targets
        repo = MagicMock()
        repo.get_pnl_summary = AsyncMock(return_value=_make_summary())
        reporter = self._make_reporter(m, repo)

        result = await reporter.send_daily_report(force=True)

        assert result["sent_slack"] is True
        assert result["sent_telegram"] is True
        assert result["skipped"] is False

    @pytest.mark.asyncio
    async def test_no_targets_skips(self, monkeypatch):
        monkeypatch.delenv("MEKKA_WEBHOOK_SLACK", raising=False)
        monkeypatch.delenv("MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("MEKKA_WEBHOOK_TELEGRAM_CHAT_ID", raising=False)
        import importlib
        import src.dashboard.daily_reporter as m
        importlib.reload(m)

        repo = MagicMock()
        reporter = m.DailyReporter(repo=repo)
        result = await reporter.send_daily_report(force=True)

        assert result["skipped"] is True
        importlib.reload(m)

    @pytest.mark.asyncio
    async def test_dedup_same_day(self, env_with_targets):
        m = env_with_targets
        repo = MagicMock()
        repo.get_pnl_summary = AsyncMock(return_value=_make_summary())
        reporter = self._make_reporter(m, repo)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        reporter._last_report_date = today

        result = await reporter.send_daily_report(force=False)
        assert result["skipped"] is True

    @pytest.mark.asyncio
    async def test_force_bypasses_dedup(self, env_with_targets):
        m = env_with_targets
        repo = MagicMock()
        repo.get_pnl_summary = AsyncMock(return_value=_make_summary())
        reporter = self._make_reporter(m, repo)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        reporter._last_report_date = today

        result = await reporter.send_daily_report(force=True)
        assert result["skipped"] is False
        assert result["sent_slack"] is True

    @pytest.mark.asyncio
    async def test_db_timeout_returns_error(self, env_with_targets):
        m = env_with_targets
        repo = MagicMock()
        repo.get_pnl_summary = AsyncMock(side_effect=asyncio.TimeoutError)
        reporter = m.DailyReporter(repo=repo)

        result = await reporter.send_daily_report(force=True)
        assert "error" in result
        assert result["error"] == "db_timeout"

    @pytest.mark.asyncio
    async def test_webhook_failure_not_marked_sent(self, env_with_targets):
        m = env_with_targets
        repo = MagicMock()
        repo.get_pnl_summary = AsyncMock(return_value=_make_summary())
        reporter = self._make_reporter(m, repo)
        # Both webhooks fail
        reporter._post_with_retry = AsyncMock(return_value=False)

        result = await reporter.send_daily_report(force=True)
        assert result["sent_slack"] is False
        assert result["sent_telegram"] is False
        # Should NOT mark as sent since nothing succeeded
        assert reporter._last_report_date is None

    @pytest.mark.asyncio
    async def test_dedup_marked_after_success(self, env_with_targets):
        m = env_with_targets
        repo = MagicMock()
        repo.get_pnl_summary = AsyncMock(return_value=_make_summary())
        reporter = self._make_reporter(m, repo)

        await reporter.send_daily_report(force=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert reporter._last_report_date == today

    @pytest.mark.asyncio
    async def test_has_targets_false_without_env(self, monkeypatch):
        monkeypatch.delenv("MEKKA_WEBHOOK_SLACK", raising=False)
        monkeypatch.delenv("MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("MEKKA_WEBHOOK_TELEGRAM_CHAT_ID", raising=False)
        import importlib
        import src.dashboard.daily_reporter as m
        importlib.reload(m)
        reporter = m.DailyReporter()
        assert reporter.has_targets is False
        importlib.reload(m)


class TestSleepUntilReportTime:
    @pytest.mark.asyncio
    async def test_sleep_returns_future_time(self, monkeypatch):
        """_sleep_until_report_time always targets a time >= now."""
        from src.dashboard.daily_reporter import DailyReporter

        reporter = DailyReporter()
        sleep_calls: list[float] = []

        async def fake_sleep(s: float) -> None:
            sleep_calls.append(s)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        await reporter._sleep_until_report_time()

        assert len(sleep_calls) == 1
        # The sleep duration must be positive (target is in the future)
        assert sleep_calls[0] > 0


# ---------------------------------------------------------------------------
# REST endpoint integration test
# ---------------------------------------------------------------------------


class TestReportEndpoint:
    @pytest.mark.asyncio
    async def test_endpoint_returns_result(self):
        """GET /api/report/daily?force=1 returns a JSON result."""
        from aiohttp.test_utils import TestClient, TestServer
        from src.dashboard.server import MekkaDashboardServer

        server = MekkaDashboardServer()
        server._daily_reporter = MagicMock()
        server._daily_reporter.send_daily_report = AsyncMock(
            return_value={
                "date": "2026-05-11",
                "sent_slack": True,
                "sent_telegram": False,
                "skipped": False,
            }
        )

        # Hit the handler directly (bypass full app startup)
        from aiohttp import web
        from unittest.mock import MagicMock as MM
        request = MM()
        request.query = {"force": "1"}
        resp = await server._handle_report_daily(request)

        assert resp.status == 200
        import json
        data = json.loads(resp.body)
        assert data["sent_slack"] is True
        assert data["date"] == "2026-05-11"

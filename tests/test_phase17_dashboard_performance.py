"""
tests/test_phase17_dashboard_performance.py
============================================
Phase 17 — Dashboard /api/performance endpoint (Story 038).

Strategy: same fixture as test_dashboard_replay — instantiate
MekkaDashboardServer, clear startup/shutdown hooks, run via TestClient.
Deadpool is patched so tests never touch the real DB.

Coverage:
  - GET /api/performance returns 200 + valid JSON
  - Response contains all expected PerformanceReport fields
  - ?days=14 parameter is forwarded to Deadpool.run()
  - Default window is 30 days
  - 504 returned on asyncio.TimeoutError
  - 500 returned on unexpected exception
  - Endpoint is registered in the router
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from src.dashboard import server as server_module
from src.dashboard.server import MekkaDashboardServer
from src.models.performance import PerformanceReport, PerformanceVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_perf_report(
    verdict: PerformanceVerdict = PerformanceVerdict.READY,
    days: int = 12,
    win_rate: float = 65.0,
    pnl: float = 320.0,
    drawdown: float = 2.5,
    wolverine_rate: float = 80.0,
) -> PerformanceReport:
    return PerformanceReport(
        window_days=30,
        days_with_data=days,
        total_trades=40,
        wins=26,
        losses=14,
        win_rate_pct=win_rate,
        total_pnl_usd=pnl,
        avg_daily_pnl_usd=pnl / max(days, 1),
        max_drawdown_pct=drawdown,
        wolverine_sl_endorse_rate_pct=wolverine_rate,
        signal_actionable_rate_pct=72.0,
        batman_approval_rate_pct=68.0,
        verdict=verdict,
        notes=["All performance thresholds met."],
    )


@pytest.fixture
async def perf_client(monkeypatch, tmp_path):
    """TestClient with startup/shutdown hooks cleared (no real DB)."""
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)

    server = MekkaDashboardServer()
    server._app.on_startup.clear()
    server._app.on_shutdown.clear()

    test_server = TestServer(server._app)
    client = TestClient(test_server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPerformanceEndpointRegistered:
    def test_route_exists(self):
        """Router must have /api/performance registered before any request."""
        server = MekkaDashboardServer()
        routes = [str(r) for r in server._app.router.resources()]
        assert any("performance" in r for r in routes)


class TestGetPerformance:
    @pytest.mark.asyncio
    async def test_returns_200_with_json(self, perf_client):
        rpt = _make_perf_report()
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_response_contains_verdict(self, perf_client):
        rpt = _make_perf_report(verdict=PerformanceVerdict.READY)
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        data = await resp.json()
        assert data["verdict"] == "READY"

    @pytest.mark.asyncio
    async def test_response_contains_win_rate(self, perf_client):
        rpt = _make_perf_report(win_rate=65.0)
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        data = await resp.json()
        assert data["win_rate_pct"] == pytest.approx(65.0)

    @pytest.mark.asyncio
    async def test_response_contains_wolverine_rate(self, perf_client):
        rpt = _make_perf_report(wolverine_rate=80.0)
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        data = await resp.json()
        assert data["wolverine_sl_endorse_rate_pct"] == pytest.approx(80.0)

    @pytest.mark.asyncio
    async def test_response_contains_pnl_and_drawdown(self, perf_client):
        rpt = _make_perf_report(pnl=500.0, drawdown=3.2)
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        data = await resp.json()
        assert data["total_pnl_usd"] == pytest.approx(500.0)
        assert data["max_drawdown_pct"] == pytest.approx(3.2)

    @pytest.mark.asyncio
    async def test_response_contains_generated_at(self, perf_client):
        rpt = _make_perf_report()
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        data = await resp.json()
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_default_window_is_30_days(self, perf_client):
        rpt = _make_perf_report()
        with patch("src.dashboard.server.Deadpool") as MockDp:
            mock_run = AsyncMock(return_value=rpt)
            MockDp.return_value.run = mock_run
            await perf_client.get("/api/performance")

        MockDp.return_value.run.assert_called_once_with(window_days=30)

    @pytest.mark.asyncio
    async def test_days_query_param_forwarded(self, perf_client):
        rpt = _make_perf_report()
        with patch("src.dashboard.server.Deadpool") as MockDp:
            mock_run = AsyncMock(return_value=rpt)
            MockDp.return_value.run = mock_run
            await perf_client.get("/api/performance?days=14")

        MockDp.return_value.run.assert_called_once_with(window_days=14)

    @pytest.mark.asyncio
    async def test_not_ready_verdict_serialised(self, perf_client):
        rpt = _make_perf_report(verdict=PerformanceVerdict.NOT_READY, win_rate=30.0)
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        data = await resp.json()
        assert data["verdict"] == "NOT_READY"

    @pytest.mark.asyncio
    async def test_insufficient_data_verdict_serialised(self, perf_client):
        rpt = _make_perf_report(verdict=PerformanceVerdict.INSUFFICIENT_DATA, days=2)
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=rpt)
            resp = await perf_client.get("/api/performance")

        data = await resp.json()
        assert data["verdict"] == "INSUFFICIENT_DATA"


class TestPerformanceEndpointErrors:
    @pytest.mark.asyncio
    async def test_504_on_timeout(self, perf_client):
        import asyncio

        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )
            resp = await perf_client.get("/api/performance")

        assert resp.status == 504
        data = await resp.json()
        assert "timed out" in data["error"]

    @pytest.mark.asyncio
    async def test_500_on_unexpected_error(self, perf_client):
        with patch("src.dashboard.server.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(
                side_effect=RuntimeError("DB not ready")
            )
            resp = await perf_client.get("/api/performance")

        assert resp.status == 500
        data = await resp.json()
        assert "error" in data

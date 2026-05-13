"""
tests/test_phase16_gate_infra.py
=================================
Phase 16 — Gate Infrastructure (Story 037).

Covers:
  - preflight check_h2_deadpool(): PASS, WARN (rate low), WARN (insufficient
    data), WARN (no Wolverine data), WARN (exception)
  - H4 appears in _HUMAN_GATES as delivered
  - check_h2_deadpool adds a result to the report (never raises)
  - Telegram /perf command: returns formatted report, handles args, handles errors
  - Telegram /gates command: H4 done, H2 auto-checked, human gates listed
  - Telegram dispatch routing: /perf and /gates wired up
"""

from __future__ import annotations

import importlib
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import scripts.preflight_mainnet as pfm
from src.agents.deadpool import MIN_DAYS_REQUIRED
from src.models.performance import PerformanceReport, PerformanceVerdict, SymbolStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(
    verdict: PerformanceVerdict = PerformanceVerdict.READY,
    days: int = MIN_DAYS_REQUIRED,
    wolverine_rate: Optional[float] = 75.0,
    win_rate: Optional[float] = 60.0,
    total_pnl: float = 250.0,
    max_dd: float = 3.0,
    trades: int = 20,
    wins: int = 12,
    losses: int = 8,
    signal_rate: Optional[float] = 70.0,
    notes: Optional[list] = None,
) -> PerformanceReport:
    return PerformanceReport(
        window_days=30,
        days_with_data=days,
        total_trades=trades,
        wins=wins,
        losses=losses,
        win_rate_pct=win_rate,
        total_pnl_usd=total_pnl,
        avg_daily_pnl_usd=total_pnl / max(days, 1),
        max_drawdown_pct=max_dd,
        wolverine_sl_endorse_rate_pct=wolverine_rate,
        signal_actionable_rate_pct=signal_rate,
        verdict=verdict,
        notes=notes or [],
    )


def _make_preflight_report():
    return pfm.PreflightReport()


def _make_poller(repo=None):
    """Build a TelegramInboundPoller with mocked dependencies."""
    from src.services.telegram_inbound import TelegramInboundPoller

    fury = MagicMock()
    fury.reset_breakers = MagicMock()
    portfolio = MagicMock()
    if repo is None:
        repo = MagicMock()
    return TelegramInboundPoller(nick_fury=fury, portfolio=portfolio, repo=repo)


# ===========================================================================
# preflight — check_h2_deadpool
# ===========================================================================

class TestCheckH2Deadpool:
    def test_pass_when_rate_above_threshold(self):
        rpt = _make_preflight_report()
        perf = _make_report(verdict=PerformanceVerdict.READY, wolverine_rate=80.0)

        with patch("scripts.preflight_mainnet.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            pfm.check_h2_deadpool(rpt)

        result = next(c for c in rpt.checks if c.name == "h2_wolverine_endorse")
        assert result.level == "PASS"
        assert "80.0%" in result.detail

    def test_warn_when_rate_below_threshold(self):
        rpt = _make_preflight_report()
        perf = _make_report(verdict=PerformanceVerdict.READY, wolverine_rate=55.0)

        with patch("scripts.preflight_mainnet.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            pfm.check_h2_deadpool(rpt)

        result = next(c for c in rpt.checks if c.name == "h2_wolverine_endorse")
        assert result.level == "WARN"
        assert "55.0%" in result.detail

    def test_warn_when_insufficient_data(self):
        rpt = _make_preflight_report()
        perf = _make_report(
            verdict=PerformanceVerdict.INSUFFICIENT_DATA,
            days=2,
            wolverine_rate=None,
        )

        with patch("scripts.preflight_mainnet.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            pfm.check_h2_deadpool(rpt)

        result = next(c for c in rpt.checks if c.name == "h2_wolverine_endorse")
        assert result.level == "WARN"
        assert "Insufficient" in result.detail

    def test_warn_when_wolverine_rate_is_none(self):
        rpt = _make_preflight_report()
        perf = _make_report(
            verdict=PerformanceVerdict.READY,
            wolverine_rate=None,
        )

        with patch("scripts.preflight_mainnet.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            pfm.check_h2_deadpool(rpt)

        result = next(c for c in rpt.checks if c.name == "h2_wolverine_endorse")
        assert result.level == "WARN"
        assert "MONITOR_RECOVERY_PLAN" in result.detail or "Wolverine" in result.detail

    def test_warn_on_exception_never_raises(self):
        rpt = _make_preflight_report()

        with patch("scripts.preflight_mainnet.Deadpool") as MockDp:
            MockDp.side_effect = RuntimeError("DB not initialised")
            pfm.check_h2_deadpool(rpt)

        result = next(c for c in rpt.checks if c.name == "h2_wolverine_endorse")
        assert result.level == "WARN"
        assert result.passed is True  # WARN is still considered passing

    def test_adds_exactly_one_result(self):
        rpt = _make_preflight_report()
        perf = _make_report()

        with patch("scripts.preflight_mainnet.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            pfm.check_h2_deadpool(rpt)

        h2_checks = [c for c in rpt.checks if c.name == "h2_wolverine_endorse"]
        assert len(h2_checks) == 1

    def test_h2_in_run_preflight(self):
        """run_preflight() calls check_h2_deadpool — h2 result appears."""
        perf = _make_report()
        with patch.object(pfm, "check_env_vars"), \
             patch.object(pfm, "check_settings"), \
             patch.object(pfm, "check_kill_switch"), \
             patch.object(pfm, "check_network"), \
             patch.object(pfm, "check_risk_limits"), \
             patch.object(pfm, "check_telegram"), \
             patch.object(pfm, "check_sdk_availability"), \
             patch.object(pfm, "check_authorization_file"), \
             patch("scripts.preflight_mainnet.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            report = pfm.run_preflight()

        h2_checks = [c for c in report.checks if c.name == "h2_wolverine_endorse"]
        assert len(h2_checks) == 1


# ===========================================================================
# preflight — H4 human gate
# ===========================================================================

class TestH4HumanGate:
    def test_h4_marked_delivered(self):
        h4_entry = next(g for g in pfm._HUMAN_GATES if g[0] == "H4")
        desc = h4_entry[1].lower()
        # Should indicate it's done, not just "waiver"
        assert "delivered" in desc or "done" in desc or "✅" in h4_entry[1]

    def test_h4_no_longer_requires_waiver_choice(self):
        """H4 desc should not say 'waiver documented' as the primary path."""
        h4_entry = next(g for g in pfm._HUMAN_GATES if g[0] == "H4")
        # The description should signal it's satisfied, not pending
        assert "032b" in h4_entry[1]

    def test_h2_gate_references_auto_check(self):
        h2_entry = next(g for g in pfm._HUMAN_GATES if g[0] == "H2")
        desc = h2_entry[1].lower()
        assert "auto" in desc or "h2_wolverine" in desc or "deadpool" in desc


# ===========================================================================
# Telegram — /perf command
# ===========================================================================

class TestTelegramCmdPerf:
    @pytest.mark.asyncio
    async def test_perf_returns_formatted_report(self):
        repo = MagicMock()
        poller = _make_poller(repo=repo)
        perf = _make_report(
            verdict=PerformanceVerdict.READY,
            wolverine_rate=80.0,
            win_rate=65.0,
            total_pnl=300.0,
        )

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_perf()

        assert "READY" in result
        assert "80.0%" in result
        assert "65.0%" in result
        assert "300" in result

    @pytest.mark.asyncio
    async def test_perf_uses_default_30_days(self):
        repo = MagicMock()
        poller = _make_poller(repo=repo)
        perf = _make_report()

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            mock_run = AsyncMock(return_value=perf)
            MockDp.return_value.run = mock_run
            await poller._cmd_perf()

        MockDp.return_value.run.assert_called_once_with(window_days=30)

    @pytest.mark.asyncio
    async def test_perf_accepts_custom_days(self):
        repo = MagicMock()
        poller = _make_poller(repo=repo)
        perf = _make_report()

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            await poller._cmd_perf(args=["14"])

        MockDp.return_value.run.assert_called_once_with(window_days=14)

    @pytest.mark.asyncio
    async def test_perf_handles_error_gracefully(self):
        poller = _make_poller()

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.side_effect = Exception("DB connection failed")
            result = await poller._cmd_perf()

        assert "⚠️" in result or "Erro" in result

    @pytest.mark.asyncio
    async def test_perf_insufficient_data_shows_warning_icon(self):
        poller = _make_poller()
        perf = _make_report(
            verdict=PerformanceVerdict.INSUFFICIENT_DATA,
            days=2,
            wolverine_rate=None,
            win_rate=None,
        )

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_perf()

        assert "⚠️" in result or "INSUFFICIENT_DATA" in result

    @pytest.mark.asyncio
    async def test_perf_not_ready_shows_red_icon(self):
        poller = _make_poller()
        perf = _make_report(
            verdict=PerformanceVerdict.NOT_READY,
            win_rate=30.0,
            wolverine_rate=40.0,
        )

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_perf()

        assert "🔴" in result or "NOT_READY" in result


# ===========================================================================
# Telegram — /gates command
# ===========================================================================

class TestTelegramCmdGates:
    @pytest.mark.asyncio
    async def test_gates_shows_h4_done(self):
        poller = _make_poller()
        perf = _make_report()

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_gates()

        assert "H4" in result
        assert "✅" in result  # H4 is auto-done

    @pytest.mark.asyncio
    async def test_gates_h2_pass_when_rate_above_threshold(self):
        poller = _make_poller()
        perf = _make_report(wolverine_rate=80.0)

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_gates()

        assert "H2" in result
        assert "80.0%" in result
        assert "✅" in result

    @pytest.mark.asyncio
    async def test_gates_h2_fail_when_rate_below_threshold(self):
        poller = _make_poller()
        perf = _make_report(wolverine_rate=50.0)

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_gates()

        assert "H2" in result
        assert "50.0%" in result
        assert "❌" in result

    @pytest.mark.asyncio
    async def test_gates_h2_warn_on_insufficient_data(self):
        poller = _make_poller()
        perf = _make_report(
            verdict=PerformanceVerdict.INSUFFICIENT_DATA,
            days=1,
            wolverine_rate=None,
        )

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_gates()

        assert "H2" in result
        assert "⚠️" in result

    @pytest.mark.asyncio
    async def test_gates_h2_error_handled(self):
        poller = _make_poller()

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.side_effect = Exception("timeout")
            result = await poller._cmd_gates()

        assert "H2" in result
        assert "⚠️" in result

    @pytest.mark.asyncio
    async def test_gates_all_six_gates_listed(self):
        poller = _make_poller()
        perf = _make_report()

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_gates()

        for gate in ("H1", "H2", "H3", "H4", "H5", "H6"):
            assert gate in result

    @pytest.mark.asyncio
    async def test_gates_mentions_authorization_file(self):
        poller = _make_poller()
        perf = _make_report()

        with patch("src.services.telegram_inbound.Deadpool") as MockDp:
            MockDp.return_value.run = AsyncMock(return_value=perf)
            result = await poller._cmd_gates()

        assert "MAINNET-AUTHORIZATION" in result


# ===========================================================================
# Telegram — dispatch routing for /perf and /gates
# ===========================================================================

class TestDispatchRouting:
    @pytest.mark.asyncio
    async def test_perf_routed_via_dispatch(self):
        poller = _make_poller()

        with patch.object(poller, "_cmd_perf", new=AsyncMock(return_value="perf_ok")) as mock_perf, \
             patch.object(poller, "_send", new=AsyncMock()), \
             patch("src.services.telegram_inbound.settings") as mock_settings:
            mock_settings.telegram_inbound_allowed_chat_ids = []  # allow any chat
            await poller._dispatch({
                "message": {
                    "chat": {"id": "123"},
                    "text": "/perf 14",
                }
            })
            mock_perf.assert_called_once_with(["14"])

    @pytest.mark.asyncio
    async def test_gates_routed_via_dispatch(self):
        poller = _make_poller()

        with patch.object(poller, "_cmd_gates", new=AsyncMock(return_value="gates_ok")) as mock_gates, \
             patch.object(poller, "_send", new=AsyncMock()), \
             patch("src.services.telegram_inbound.settings") as mock_settings:
            mock_settings.telegram_inbound_allowed_chat_ids = []  # allow any chat
            await poller._dispatch({
                "message": {
                    "chat": {"id": "123"},
                    "text": "/gates",
                }
            })
            mock_gates.assert_called_once()

    @pytest.mark.asyncio
    async def test_help_text_includes_perf_and_gates(self):
        poller = _make_poller()
        result = await poller._cmd_help()
        assert "/perf" in result
        assert "/gates" in result

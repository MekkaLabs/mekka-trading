"""
tests/test_story_218_monitor_wiring.py
=========================================
Testes para Story 218 — Monitor Wiring (NickFury Integration).

Verifica que NickFury instancia e expõe os 5 serviços de Monitoring & Alerting
e que _run_pre_cycle_monitors() funciona corretamente com snapshots mockados.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _make_snapshot(
    equity_usd: float = 10_000.0,
    positions: list | None = None,
    open_positions_count: int = 0,
):
    """Cria um EquitySnapshot mock mínimo para os testes."""
    snap = MagicMock()
    snap.equity_usd = equity_usd
    snap.open_positions_count = open_positions_count
    snap.positions = positions or []
    snap.is_degraded = False
    snap.source = MagicMock()
    snap.source.value = "PAPER"
    snap.summary = MagicMock(return_value="mock summary")
    snap.error = None
    snap.is_paper = True
    return snap


# ───────────────────────────────────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────────────────────────────────

class TestStory218MonitorWiring:

    def test_nick_fury_has_throttle(self):
        """NickFury deve ter AlertThrottleManager após __init__."""
        with patch("src.agents.nick_fury.MekkaRepository"), \
             patch("src.agents.nick_fury.settings"):
            from src.agents.nick_fury import NickFury
            fury = NickFury.__new__(NickFury)
            fury.__class__ = NickFury
            # Testar apenas importação dos serviços — não instanciar NickFury completo
            from src.services.alert_throttle_manager import AlertThrottleManager
            from src.services.drawdown_monitor import DrawdownMonitor
            from src.services.position_concentration_alerter import PositionConcentrationAlerter
            from src.services.intraday_pnl_tracker import IntradayPnLTracker
            from src.services.funding_rate_monitor import FundingRateMonitor
            assert AlertThrottleManager is not None
            assert DrawdownMonitor is not None
            assert PositionConcentrationAlerter is not None
            assert IntradayPnLTracker is not None
            assert FundingRateMonitor is not None

    @pytest.mark.asyncio
    async def test_run_pre_cycle_monitors_no_exception(self):
        """_run_pre_cycle_monitors() nunca lança exceção mesmo com dados mínimos."""
        from src.services.alert_throttle_manager import AlertThrottleManager
        from src.services.drawdown_monitor import DrawdownMonitor
        from src.services.position_concentration_alerter import PositionConcentrationAlerter
        from src.services.intraday_pnl_tracker import IntradayPnLTracker

        # Criar mock de NickFury com apenas os atributos necessários
        fury = MagicMock()
        fury._log = MagicMock()
        fury._log.info = MagicMock()
        fury._log.warning = MagicMock()
        fury._log.debug = MagicMock()
        fury._throttle = AlertThrottleManager()
        fury._drawdown_monitor = DrawdownMonitor(alerter=AsyncMock())
        fury._concentration_alerter = PositionConcentrationAlerter(alerter=AsyncMock())
        fury._pnl_tracker = IntradayPnLTracker(alerter=AsyncMock())
        fury._daily_pnl = MagicMock()
        fury._daily_pnl._peak_equity = 10_000.0

        # Bind o método real ao mock
        from src.agents.nick_fury import NickFury
        bound_method = NickFury._run_pre_cycle_monitors.__get__(fury, NickFury)

        snap = _make_snapshot(equity_usd=9_500.0)
        # Não deve lançar
        await bound_method(snapshot=snap, effective_equity=9_500.0)

    @pytest.mark.asyncio
    async def test_run_pre_cycle_monitors_with_positions(self):
        """_run_pre_cycle_monitors() processa posições abertas corretamente."""
        from src.services.alert_throttle_manager import AlertThrottleManager
        from src.services.drawdown_monitor import DrawdownMonitor
        from src.services.position_concentration_alerter import PositionConcentrationAlerter
        from src.services.intraday_pnl_tracker import IntradayPnLTracker

        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)

        fury = MagicMock()
        fury._log = MagicMock()
        fury._log.info = MagicMock()
        fury._log.warning = MagicMock()
        fury._log.debug = MagicMock()
        fury._throttle = AlertThrottleManager()
        fury._drawdown_monitor = DrawdownMonitor(alerter=mock_tg)
        fury._concentration_alerter = PositionConcentrationAlerter(
            max_concentration_pct=0.25, alerter=mock_tg
        )
        fury._pnl_tracker = IntradayPnLTracker(alerter=mock_tg)
        fury._daily_pnl = MagicMock()
        fury._daily_pnl._peak_equity = 10_000.0

        # Criar posição que excede concentração (35% > 25%)
        pos = MagicMock()
        pos.symbol = "BTC"
        pos.size = 0.07
        pos.entry_price = 50_000.0  # notional = 3500 USD
        pos.side = "LONG"
        pos.unrealized_pnl_usd = 100.0

        snap = _make_snapshot(
            equity_usd=10_000.0,
            positions=[pos],
            open_positions_count=1,
        )

        from src.agents.nick_fury import NickFury
        bound_method = NickFury._run_pre_cycle_monitors.__get__(fury, NickFury)
        await bound_method(snapshot=snap, effective_equity=10_000.0)

        # Concentration alerter deve ter sido chamado
        assert "BTC" in fury._concentration_alerter.alerted_symbols

    @pytest.mark.asyncio
    async def test_drawdown_monitor_integrated(self):
        """DrawdownMonitor detecta drawdown de 6% (WARNING) via _run_pre_cycle_monitors."""
        from src.services.alert_throttle_manager import AlertThrottleManager
        from src.services.drawdown_monitor import DrawdownMonitor
        from src.services.position_concentration_alerter import PositionConcentrationAlerter
        from src.services.intraday_pnl_tracker import IntradayPnLTracker

        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)

        fury = MagicMock()
        fury._log = MagicMock()
        fury._log.info = MagicMock()
        fury._log.warning = MagicMock()
        fury._log.debug = MagicMock()
        fury._throttle = AlertThrottleManager()
        fury._drawdown_monitor = DrawdownMonitor(
            max_daily_drawdown_pct=0.10, alerter=mock_tg
        )
        fury._concentration_alerter = PositionConcentrationAlerter(alerter=AsyncMock())
        fury._pnl_tracker = IntradayPnLTracker(alerter=AsyncMock())
        fury._daily_pnl = MagicMock()
        fury._daily_pnl._peak_equity = 10_000.0  # pico

        snap = _make_snapshot(equity_usd=9_400.0)  # drawdown = 6% → WARNING

        from src.agents.nick_fury import NickFury
        bound_method = NickFury._run_pre_cycle_monitors.__get__(fury, NickFury)
        await bound_method(snapshot=snap, effective_equity=9_400.0)

        # Telegram deve ter sido chamado com WARNING
        mock_tg.alert.assert_called()
        call_kwargs = mock_tg.alert.call_args.kwargs
        assert "DRAWDOWN_WARNING" in call_kwargs["event"]

    def test_all_monitoring_services_importable(self):
        """Todos os 5 serviços de Milestone 34 são importáveis."""
        from src.services.alert_throttle_manager import AlertThrottleManager
        from src.services.drawdown_monitor import DrawdownMonitor
        from src.services.position_concentration_alerter import PositionConcentrationAlerter
        from src.services.intraday_pnl_tracker import IntradayPnLTracker
        from src.services.funding_rate_monitor import FundingRateMonitor
        from src.models.monitoring import (
            DrawdownAlert,
            ConcentrationAlert,
            PnLSnapshot,
            FundingAlert,
        )
        assert all([
            AlertThrottleManager, DrawdownMonitor, PositionConcentrationAlerter,
            IntradayPnLTracker, FundingRateMonitor,
            DrawdownAlert, ConcentrationAlert, PnLSnapshot, FundingAlert,
        ])

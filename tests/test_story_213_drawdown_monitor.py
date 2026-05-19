"""
tests/test_story_213_drawdown_monitor.py
==========================================
Testes para Story 213 — DrawdownMonitor (Milestone 34: Monitoring & Alerting).

Cobre:
- Cálculo correto de drawdown
- Threshold WARNING (50% do limite)
- Threshold CRITICAL (80% do limite)
- Threshold KILL (100% do limite)
- Dedup por nível (cada nível só dispara uma vez)
- Nenhum alerta quando equity aumenta
- reset_session() limpa dedup
- Nunca lança exceção (absorção de erros)
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _make_monitor(limit_pct: float = 0.10, alerter=None):
    """Cria DrawdownMonitor com alerter mockado para não chamar Telegram."""
    from src.services.drawdown_monitor import DrawdownMonitor

    mock_alerter = alerter or AsyncMock()
    mock_alerter.alert = AsyncMock(return_value=True)
    return DrawdownMonitor(max_daily_drawdown_pct=limit_pct, alerter=mock_alerter)


# ───────────────────────────────────────────────────────────────────────────
# Story 213 — DrawdownMonitor
# ───────────────────────────────────────────────────────────────────────────

class TestStory213DrawdownMonitor:

    def test_import(self):
        from src.services.drawdown_monitor import DrawdownMonitor
        assert DrawdownMonitor is not None

    def test_model_import(self):
        from src.models.monitoring import DrawdownAlert
        assert DrawdownAlert is not None

    @pytest.mark.asyncio
    async def test_no_alert_when_equity_at_peak(self):
        monitor = _make_monitor(limit_pct=0.10)
        result = await monitor.check(current_equity=10_000.0, peak_equity=10_000.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_alert_when_equity_above_peak(self):
        monitor = _make_monitor(limit_pct=0.10)
        # equity acima do pico → sem drawdown
        result = await monitor.check(current_equity=10_500.0, peak_equity=10_000.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_warning_at_50_pct_of_limit(self):
        """Drawdown = 5%, limite = 10% → 50% do limite → WARNING."""
        monitor = _make_monitor(limit_pct=0.10)
        result = await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)
        assert result is not None
        assert result.level == "WARNING"
        assert pytest.approx(result.drawdown_pct, abs=0.01) == 5.0
        assert pytest.approx(result.pct_of_limit, abs=0.01) == 0.50

    @pytest.mark.asyncio
    async def test_critical_at_80_pct_of_limit(self):
        """Drawdown = 8%, limite = 10% → 80% do limite → CRITICAL."""
        monitor = _make_monitor(limit_pct=0.10)
        # 5% → WARNING primeiro
        await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)
        # 8% → CRITICAL
        result = await monitor.check(current_equity=9_200.0, peak_equity=10_000.0)
        assert result is not None
        assert result.level == "CRITICAL"

    @pytest.mark.asyncio
    async def test_kill_at_100_pct_of_limit(self):
        """Drawdown = 10%, limite = 10% → 100% do limite → KILL."""
        monitor = _make_monitor(limit_pct=0.10)
        await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)  # WARNING
        await monitor.check(current_equity=9_200.0, peak_equity=10_000.0)  # CRITICAL
        result = await monitor.check(current_equity=9_000.0, peak_equity=10_000.0)  # KILL
        assert result is not None
        assert result.level == "KILL"

    @pytest.mark.asyncio
    async def test_dedup_same_level(self):
        """Mesmo nível só dispara uma vez."""
        monitor = _make_monitor(limit_pct=0.10)
        first = await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)
        assert first is not None and first.level == "WARNING"

        second = await monitor.check(current_equity=9_400.0, peak_equity=10_000.0)
        # 6% → ainda WARNING, mas já foi disparado → None
        assert second is None

    @pytest.mark.asyncio
    async def test_reset_session_clears_dedup(self):
        """reset_session() permite que os alertas sejam disparados novamente."""
        monitor = _make_monitor(limit_pct=0.10)
        await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)  # WARNING
        monitor.reset_session()
        result = await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)
        assert result is not None
        assert result.level == "WARNING"

    @pytest.mark.asyncio
    async def test_never_raises_on_bad_input(self):
        """Inputs inválidos são absorvidos silenciosamente."""
        monitor = _make_monitor(limit_pct=0.10)
        result = await monitor.check(current_equity=0.0, peak_equity=0.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_telegram_called_on_alert(self):
        """TelegramAlerter.alert() é chamado quando um threshold é atingido."""
        mock_alerter = AsyncMock()
        mock_alerter.alert = AsyncMock(return_value=True)
        monitor = _make_monitor(limit_pct=0.10, alerter=mock_alerter)

        await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)
        mock_alerter.alert.assert_called_once()
        call_kwargs = mock_alerter.alert.call_args.kwargs
        assert "DRAWDOWN_WARNING" in call_kwargs["event"]

    @pytest.mark.asyncio
    async def test_telegram_error_absorbed(self):
        """Falha no Telegram não propaga para o caller."""
        mock_alerter = AsyncMock()
        mock_alerter.alert = AsyncMock(side_effect=RuntimeError("network error"))
        monitor = _make_monitor(limit_pct=0.10, alerter=mock_alerter)

        # Não deve lançar
        result = await monitor.check(current_equity=9_500.0, peak_equity=10_000.0)
        # Alert model ainda retorna mesmo que Telegram tenha falhado
        # (o alerta é criado antes de chamar Telegram)
        assert result is not None

    def test_drawdown_alert_pct_of_limit(self):
        """DrawdownAlert.pct_of_limit calcula corretamente."""
        from src.models.monitoring import DrawdownAlert
        alert = DrawdownAlert(
            level="WARNING",
            drawdown_pct=5.0,
            current_equity=9_500.0,
            peak_equity=10_000.0,
            loss_usd=500.0,
            limit_pct=10.0,
            threshold_pct=5.0,
        )
        assert pytest.approx(alert.pct_of_limit, abs=0.01) == 0.50

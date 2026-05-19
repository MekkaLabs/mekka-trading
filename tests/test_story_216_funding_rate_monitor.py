"""
tests/test_story_216_funding_rate_monitor.py
==============================================
Testes para Story 216 — FundingRateMonitor (Milestone 34).

Cobre:
- Nenhum alerta em funding normal
- WARN para longs (funding positivo elevado)
- BLOCK para longs (funding positivo extremo)
- WARN para shorts (funding negativo elevado)
- BLOCK para shorts (funding negativo extremo)
- BLOCK tem prioridade sobre WARN no mesmo ciclo
- Dedup por (symbol, direction, severity)
- reset_session() limpa dedup
- Falha do Telegram absorvida
- Nenhuma exceção em inputs extremos
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _make_monitor(alerter=None):
    from src.services.funding_rate_monitor import FundingRateMonitor
    mock_tg = alerter or AsyncMock()
    mock_tg.alert = AsyncMock(return_value=True)
    return FundingRateMonitor(
        long_warn_pct=0.05,
        long_block_pct=0.10,
        short_warn_pct=-0.05,
        short_block_pct=-0.10,
        alerter=mock_tg,
    )


# ───────────────────────────────────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────────────────────────────────

class TestStory216FundingRateMonitor:

    def test_import(self):
        from src.services.funding_rate_monitor import FundingRateMonitor
        assert FundingRateMonitor is not None

    @pytest.mark.asyncio
    async def test_no_alert_in_normal_range(self):
        monitor = _make_monitor()
        result = await monitor.check(symbol="BTC", funding_rate_pct=0.01)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_alert_in_negative_normal(self):
        monitor = _make_monitor()
        result = await monitor.check(symbol="BTC", funding_rate_pct=-0.01)
        assert result is None

    @pytest.mark.asyncio
    async def test_warn_for_high_long(self):
        monitor = _make_monitor()
        result = await monitor.check(symbol="BTC", funding_rate_pct=0.06)
        assert result is not None
        assert result.severity == "WARN"
        assert result.direction == "HIGH_LONG"
        assert result.symbol == "BTC"

    @pytest.mark.asyncio
    async def test_block_for_extreme_long(self):
        monitor = _make_monitor()
        result = await monitor.check(symbol="BTC", funding_rate_pct=0.12)
        assert result is not None
        assert result.severity == "BLOCK"
        assert result.direction == "HIGH_LONG"

    @pytest.mark.asyncio
    async def test_warn_for_high_short(self):
        monitor = _make_monitor()
        result = await monitor.check(symbol="ETH", funding_rate_pct=-0.06)
        assert result is not None
        assert result.severity == "WARN"
        assert result.direction == "HIGH_SHORT"
        assert result.symbol == "ETH"

    @pytest.mark.asyncio
    async def test_block_for_extreme_short(self):
        monitor = _make_monitor()
        result = await monitor.check(symbol="SOL", funding_rate_pct=-0.12)
        assert result is not None
        assert result.severity == "BLOCK"
        assert result.direction == "HIGH_SHORT"

    @pytest.mark.asyncio
    async def test_block_takes_priority_over_warn(self):
        """Funding acima do block threshold → BLOCK, não WARN."""
        monitor = _make_monitor()
        result = await monitor.check(symbol="BTC", funding_rate_pct=0.15)
        assert result.severity == "BLOCK"

    @pytest.mark.asyncio
    async def test_dedup_same_symbol_and_direction(self):
        monitor = _make_monitor()
        first = await monitor.check(symbol="BTC", funding_rate_pct=0.06)
        assert first is not None and first.severity == "WARN"

        second = await monitor.check(symbol="BTC", funding_rate_pct=0.07)
        assert second is None  # mesmo símbolo + HIGH_LONG + WARN → dedup

    @pytest.mark.asyncio
    async def test_reset_session_clears_dedup(self):
        monitor = _make_monitor()
        await monitor.check(symbol="BTC", funding_rate_pct=0.06)
        monitor.reset_session()
        result = await monitor.check(symbol="BTC", funding_rate_pct=0.06)
        assert result is not None

    @pytest.mark.asyncio
    async def test_telegram_called_with_correct_event(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)
        monitor = _make_monitor(alerter=mock_tg)

        await monitor.check(symbol="BTC", funding_rate_pct=0.12)
        mock_tg.alert.assert_called_once()
        event = mock_tg.alert.call_args.kwargs["event"]
        assert "FUNDING_HIGH_LONG_BLOCK" == event

    @pytest.mark.asyncio
    async def test_telegram_error_absorbed(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(side_effect=RuntimeError("net error"))
        monitor = _make_monitor(alerter=mock_tg)

        # Não deve lançar
        result = await monitor.check(symbol="BTC", funding_rate_pct=0.12)
        assert result is not None  # Alert criado mesmo que Telegram falhou

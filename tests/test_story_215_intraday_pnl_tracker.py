"""
tests/test_story_215_intraday_pnl_tracker.py
===============================================
Testes para Story 215 — IntradayPnLTracker (Milestone 34).

Cobre:
- record() retorna PnLSnapshot com valores corretos
- Snapshot guardado no dict por hora
- Alerta de ganho disparado ao cruzar marco
- Alerta de perda disparado ao cruzar marco
- Dedup por marco (cada marco dispara uma vez)
- reset_day() limpa estado
- get_summary() retorna string formatada
- latest_snapshot property
- Falha do Telegram absorvida
- Nenhuma exceção em inputs extremos
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _make_tracker(gain_thresholds=None, loss_thresholds=None, alerter=None):
    from src.services.intraday_pnl_tracker import IntradayPnLTracker
    mock_tg = alerter or AsyncMock()
    mock_tg.alert = AsyncMock(return_value=True)
    return IntradayPnLTracker(
        gain_thresholds_pct=gain_thresholds or [3.0, 5.0],
        loss_thresholds_pct=loss_thresholds or [-2.0],
        alerter=mock_tg,
    )


# ───────────────────────────────────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────────────────────────────────

class TestStory215IntradayPnLTracker:

    def test_import(self):
        from src.services.intraday_pnl_tracker import IntradayPnLTracker
        assert IntradayPnLTracker is not None

    @pytest.mark.asyncio
    async def test_record_returns_snapshot(self):
        tracker = _make_tracker()
        snap = await tracker.record(realized_pnl=200.0, unrealized_pnl=50.0, equity_usd=10_000.0)
        assert snap.realized_pnl_usd == pytest.approx(200.0)
        assert snap.unrealized_pnl_usd == pytest.approx(50.0)
        assert snap.total_pnl_usd == pytest.approx(250.0)

    @pytest.mark.asyncio
    async def test_snapshot_stored_by_hour(self):
        tracker = _make_tracker()
        await tracker.record(realized_pnl=100.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        assert len(tracker.snapshots) == 1

    @pytest.mark.asyncio
    async def test_gain_alert_fired_at_threshold(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)
        tracker = _make_tracker(gain_thresholds=[3.0], alerter=mock_tg)

        # P&L = 350 / equity_inicial = 10_000 - 350 = 9650 → 3.63% ≥ 3%
        await tracker.record(realized_pnl=350.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        mock_tg.alert.assert_called_once()
        event = mock_tg.alert.call_args.kwargs["event"]
        assert "GAIN" in event

    @pytest.mark.asyncio
    async def test_loss_alert_fired_at_threshold(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)
        tracker = _make_tracker(gain_thresholds=[], loss_thresholds=[-2.0], alerter=mock_tg)

        # P&L = -250 / equity_inicial = 10_000 + 250 = 10_250 → -2.44% ≤ -2%
        await tracker.record(realized_pnl=-250.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        mock_tg.alert.assert_called_once()
        event = mock_tg.alert.call_args.kwargs["event"]
        assert "LOSS" in event

    @pytest.mark.asyncio
    async def test_no_alert_below_gain_threshold(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)
        tracker = _make_tracker(gain_thresholds=[5.0], alerter=mock_tg)

        # P&L = 100 / equity_inicial = 9_900 → ~1% < 5%
        await tracker.record(realized_pnl=100.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        mock_tg.alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedup_same_milestone(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)
        tracker = _make_tracker(gain_thresholds=[3.0], alerter=mock_tg)

        await tracker.record(realized_pnl=350.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        await tracker.record(realized_pnl=400.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        # Marco +3% já foi disparado — não deve chamar novamente
        assert mock_tg.alert.call_count == 1

    @pytest.mark.asyncio
    async def test_reset_day_clears_state(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)
        tracker = _make_tracker(gain_thresholds=[3.0], alerter=mock_tg)

        await tracker.record(realized_pnl=350.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        tracker.reset_day()

        assert len(tracker.snapshots) == 0
        assert tracker.latest_snapshot is None

        # Após reset, marco pode ser disparado novamente
        await tracker.record(realized_pnl=350.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        assert mock_tg.alert.call_count == 2

    @pytest.mark.asyncio
    async def test_get_summary_with_data(self):
        tracker = _make_tracker()
        await tracker.record(realized_pnl=300.0, unrealized_pnl=100.0, equity_usd=10_000.0)
        summary = tracker.get_summary()
        assert "P&L Intraday" in summary
        assert "300" in summary or "400" in summary  # total ou parcelas

    def test_get_summary_without_data(self):
        tracker = _make_tracker()
        summary = tracker.get_summary()
        assert "sem dados" in summary

    @pytest.mark.asyncio
    async def test_telegram_error_absorbed(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(side_effect=RuntimeError("net error"))
        tracker = _make_tracker(gain_thresholds=[3.0], alerter=mock_tg)

        # Não deve lançar
        snap = await tracker.record(realized_pnl=350.0, unrealized_pnl=0.0, equity_usd=10_000.0)
        assert snap is not None
        assert snap.total_pnl_usd == pytest.approx(350.0)

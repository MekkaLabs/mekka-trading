"""
tests/test_story_214_position_concentration_alerter.py
=========================================================
Testes para Story 214 — PositionConcentrationAlerter (Milestone 34).

Cobre:
- Nenhum alerta quando concentração abaixo do limite
- Alerta quando posição única excede o limite
- Múltiplas posições — apenas as violadoras alertadas
- Dedup por símbolo (uma vez por sessão)
- reset_session() limpa dedup
- Equity zero não lança exceção
- Lista vazia de posições retorna lista vazia
- TelegramAlerter.alert() é chamado com event correto
- Falha no Telegram é absorvida
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _make_alerter(limit_pct: float = 0.25, telegram=None):
    from src.services.position_concentration_alerter import PositionConcentrationAlerter
    mock_tg = telegram or AsyncMock()
    mock_tg.alert = AsyncMock(return_value=True)
    return PositionConcentrationAlerter(max_concentration_pct=limit_pct, alerter=mock_tg)


# ───────────────────────────────────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────────────────────────────────

class TestStory214PositionConcentrationAlerter:

    def test_import(self):
        from src.services.position_concentration_alerter import PositionConcentrationAlerter
        assert PositionConcentrationAlerter is not None

    @pytest.mark.asyncio
    async def test_no_alert_below_limit(self):
        alerter = _make_alerter(limit_pct=0.25)
        positions = [{"symbol": "BTC", "notional_usd": 2000.0, "side": "LONG"}]
        alerts = await alerter.check(positions=positions, equity_usd=10_000.0)
        # 20% < 25% → sem alerta
        assert alerts == []

    @pytest.mark.asyncio
    async def test_alert_above_limit(self):
        alerter = _make_alerter(limit_pct=0.25)
        positions = [{"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"}]
        alerts = await alerter.check(positions=positions, equity_usd=10_000.0)
        # 30% > 25% → alerta
        assert len(alerts) == 1
        assert alerts[0].symbol == "BTC"
        assert pytest.approx(alerts[0].concentration_pct, abs=0.01) == 30.0
        assert alerts[0].side == "LONG"

    @pytest.mark.asyncio
    async def test_multiple_positions_only_violators_alerted(self):
        alerter = _make_alerter(limit_pct=0.25)
        positions = [
            {"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"},   # 30% → viola
            {"symbol": "ETH", "notional_usd": 1500.0, "side": "SHORT"},  # 15% → OK
            {"symbol": "SOL", "notional_usd": 4000.0, "side": "LONG"},   # 40% → viola
        ]
        alerts = await alerter.check(positions=positions, equity_usd=10_000.0)
        assert len(alerts) == 2
        symbols = {a.symbol for a in alerts}
        assert "BTC" in symbols
        assert "SOL" in symbols

    @pytest.mark.asyncio
    async def test_dedup_same_symbol(self):
        alerter = _make_alerter(limit_pct=0.25)
        positions = [{"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"}]
        first = await alerter.check(positions=positions, equity_usd=10_000.0)
        assert len(first) == 1

        second = await alerter.check(positions=positions, equity_usd=10_000.0)
        assert second == []  # dedup

    @pytest.mark.asyncio
    async def test_reset_session_clears_dedup(self):
        alerter = _make_alerter(limit_pct=0.25)
        positions = [{"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"}]
        await alerter.check(positions=positions, equity_usd=10_000.0)

        alerter.reset_session()
        second = await alerter.check(positions=positions, equity_usd=10_000.0)
        assert len(second) == 1

    @pytest.mark.asyncio
    async def test_empty_positions_returns_empty(self):
        alerter = _make_alerter(limit_pct=0.25)
        alerts = await alerter.check(positions=[], equity_usd=10_000.0)
        assert alerts == []

    @pytest.mark.asyncio
    async def test_zero_equity_returns_empty(self):
        alerter = _make_alerter(limit_pct=0.25)
        positions = [{"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"}]
        alerts = await alerter.check(positions=positions, equity_usd=0.0)
        assert alerts == []

    @pytest.mark.asyncio
    async def test_telegram_called_with_correct_event(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(return_value=True)
        alerter = _make_alerter(limit_pct=0.25, telegram=mock_tg)

        positions = [{"symbol": "ETH", "notional_usd": 3000.0, "side": "SHORT"}]
        await alerter.check(positions=positions, equity_usd=10_000.0)

        mock_tg.alert.assert_called_once()
        kwargs = mock_tg.alert.call_args.kwargs
        assert kwargs["event"] == "POSITION_CONCENTRATION"
        assert kwargs["symbol"] == "ETH"

    @pytest.mark.asyncio
    async def test_telegram_error_absorbed(self):
        mock_tg = AsyncMock()
        mock_tg.alert = AsyncMock(side_effect=RuntimeError("net error"))
        alerter = _make_alerter(limit_pct=0.25, telegram=mock_tg)

        positions = [{"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"}]
        alerts = await alerter.check(positions=positions, equity_usd=10_000.0)
        # Não deve lançar — mas alert model é retornado
        assert len(alerts) == 1

    def test_alerted_symbols_property(self):
        from src.services.position_concentration_alerter import PositionConcentrationAlerter
        alerter = PositionConcentrationAlerter(max_concentration_pct=0.25)
        assert alerter.alerted_symbols == frozenset()

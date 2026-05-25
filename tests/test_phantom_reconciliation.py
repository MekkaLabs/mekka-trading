"""Tests — IronMan.reconcile_phantom_positions (T0.3 fix, 2026-05-25).

Fecha o gap "DB-side phantom" identificado na auditoria de agentes.
Background: Risk Scanner (Domino) detectava o drift mas só propunha
ImprovementProposal — nenhuma reconciliação ativa do lado DB acontecia.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.iron_man import IronMan


def _trade(symbol: str, side: str, qty: float, is_paper: bool = False, status: str = "FILLED"):
    """Minimal stub of a TradeRecord-like row."""
    return SimpleNamespace(
        symbol=symbol,
        side=side,
        quantity=qty,
        is_paper=is_paper,
        status=status,
        raw={},
    )


def _exchange_position(symbol: str, contracts: float):
    return {"symbol": symbol, "contracts": contracts}


@pytest.mark.asyncio
async def test_paper_mode_is_noop():
    """Paper mode never reconciles — phantom logic is live-only."""
    with patch("src.agents.iron_man.settings") as fake_settings:
        fake_settings.paper_trading = True
        result = await IronMan().reconcile_phantom_positions()
    assert result == {"checked": 0, "phantom_closed": [], "errors": []}


@pytest.mark.asyncio
async def test_disabled_via_setting():
    """phantom_reconciliation_enabled=False short-circuits."""
    with patch("src.agents.iron_man.settings") as fake_settings:
        fake_settings.paper_trading = False
        fake_settings.phantom_reconciliation_enabled = False
        fake_settings.active_exchange = "binance"
        result = await IronMan().reconcile_phantom_positions()
    assert result == {"checked": 0, "phantom_closed": [], "errors": []}


@pytest.mark.asyncio
async def test_hyperliquid_skipped():
    """Hyperliquid uses different bookkeeping — skipped explicitly."""
    with patch("src.agents.iron_man.settings") as fake_settings:
        fake_settings.paper_trading = False
        fake_settings.phantom_reconciliation_enabled = True
        fake_settings.active_exchange = "hyperliquid"
        result = await IronMan().reconcile_phantom_positions()
    assert result == {"checked": 0, "phantom_closed": [], "errors": []}


@pytest.mark.asyncio
async def test_agreement_no_action():
    """DB and exchange agree (both have BTC LONG) → checked=1, no synthetic close."""
    fake_trades = [_trade("BTC", "long", 0.05)]
    fake_positions = [_exchange_position("BTC/USDT:USDT", 0.05)]

    fake_exchange = MagicMock()
    fake_exchange.fetch_positions = AsyncMock(return_value=fake_positions)
    im = IronMan()
    im._get_ccxt_exchange = AsyncMock(return_value=fake_exchange)

    with patch("src.agents.iron_man.settings") as fake_settings, patch(
        "src.persistence.repository.MekkaRepository.list_recent_trades",
        AsyncMock(return_value=fake_trades),
    ), patch("src.agents.iron_man.to_mekka", side_effect=lambda s: (s or "").split("/")[0]):
        fake_settings.paper_trading = False
        fake_settings.phantom_reconciliation_enabled = True
        fake_settings.active_exchange = "binance"
        result = await im.reconcile_phantom_positions()

    assert result["checked"] == 1
    assert result["phantom_closed"] == []
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_phantom_detected_and_closed():
    """DB has BTC LONG, exchange does not → synthetic close inserted."""
    fake_trades = [_trade("BTC", "long", 0.05)]
    fake_positions: list = []  # exchange has nothing

    fake_exchange = MagicMock()
    fake_exchange.fetch_positions = AsyncMock(return_value=fake_positions)
    im = IronMan()
    im._get_ccxt_exchange = AsyncMock(return_value=fake_exchange)

    saved_trades: list = []

    async def _capture_save_trade(execution_result):
        saved_trades.append(execution_result)
        return 999

    logged: list = []

    async def _capture_log_event(**kwargs):
        logged.append(kwargs)

    with patch("src.agents.iron_man.settings") as fake_settings, patch(
        "src.persistence.repository.MekkaRepository.list_recent_trades",
        AsyncMock(return_value=fake_trades),
    ), patch(
        "src.persistence.repository.MekkaRepository.save_trade",
        AsyncMock(side_effect=_capture_save_trade),
    ), patch(
        "src.persistence.repository.MekkaRepository.log_event",
        AsyncMock(side_effect=_capture_log_event),
    ), patch("src.agents.iron_man.to_mekka", side_effect=lambda s: (s or "").split("/")[0]):
        fake_settings.paper_trading = False
        fake_settings.phantom_reconciliation_enabled = True
        fake_settings.active_exchange = "binance"
        result = await im.reconcile_phantom_positions()

    assert result["checked"] == 1
    assert len(result["phantom_closed"]) == 1
    closed = result["phantom_closed"][0]
    assert closed["symbol"] == "BTC"
    assert closed["side"] == "LONG"
    assert closed["qty"] == 0.05
    assert result["errors"] == []

    # synthetic close persisted
    assert len(saved_trades) == 1
    trade = saved_trades[0]
    assert trade.symbol == "BTC"
    assert trade.side == "short"  # offset of LONG
    assert trade.quantity == 0.05
    assert trade.metadata["action"] == "phantom_reconciled"

    # audit event written
    assert any(e.get("event") == "PHANTOM_RECONCILED" for e in logged)


@pytest.mark.asyncio
async def test_phantom_short_detected_and_closed():
    """DB has BTC SHORT, exchange does not → synthetic close inserted as LONG."""
    fake_trades = [_trade("BTC", "short", 0.1)]
    fake_exchange = MagicMock()
    fake_exchange.fetch_positions = AsyncMock(return_value=[])
    im = IronMan()
    im._get_ccxt_exchange = AsyncMock(return_value=fake_exchange)
    saved: list = []

    async def _capture(t):
        saved.append(t)
        return 1

    with patch("src.agents.iron_man.settings") as fake_settings, patch(
        "src.persistence.repository.MekkaRepository.list_recent_trades",
        AsyncMock(return_value=fake_trades),
    ), patch(
        "src.persistence.repository.MekkaRepository.save_trade",
        AsyncMock(side_effect=_capture),
    ), patch(
        "src.persistence.repository.MekkaRepository.log_event", AsyncMock()
    ), patch("src.agents.iron_man.to_mekka", side_effect=lambda s: (s or "").split("/")[0]):
        fake_settings.paper_trading = False
        fake_settings.phantom_reconciliation_enabled = True
        fake_settings.active_exchange = "binance"
        result = await im.reconcile_phantom_positions()

    assert result["phantom_closed"][0]["side"] == "SHORT"
    assert saved[0].side == "long"  # offset of SHORT


@pytest.mark.asyncio
async def test_paper_trades_ignored():
    """Paper trades in DB are skipped — phantom logic is live-only."""
    fake_trades = [
        _trade("BTC", "long", 0.05, is_paper=True),
        _trade("ETH", "long", 1.0, is_paper=True),
    ]
    fake_exchange = MagicMock()
    fake_exchange.fetch_positions = AsyncMock(return_value=[])
    im = IronMan()
    im._get_ccxt_exchange = AsyncMock(return_value=fake_exchange)

    with patch("src.agents.iron_man.settings") as fake_settings, patch(
        "src.persistence.repository.MekkaRepository.list_recent_trades",
        AsyncMock(return_value=fake_trades),
    ):
        fake_settings.paper_trading = False
        fake_settings.phantom_reconciliation_enabled = True
        fake_settings.active_exchange = "binance"
        result = await im.reconcile_phantom_positions()

    # All trades were paper → no live db_open → no phantom check
    assert result["checked"] == 0
    assert result["phantom_closed"] == []


@pytest.mark.asyncio
async def test_fetch_positions_failure_records_error():
    """Network/auth failure on fetch_positions is captured, never raises."""
    fake_trades = [_trade("BTC", "long", 0.05)]
    fake_exchange = MagicMock()
    fake_exchange.fetch_positions = AsyncMock(side_effect=RuntimeError("network down"))
    im = IronMan()
    im._get_ccxt_exchange = AsyncMock(return_value=fake_exchange)

    with patch("src.agents.iron_man.settings") as fake_settings, patch(
        "src.persistence.repository.MekkaRepository.list_recent_trades",
        AsyncMock(return_value=fake_trades),
    ):
        fake_settings.paper_trading = False
        fake_settings.phantom_reconciliation_enabled = True
        fake_settings.active_exchange = "binance"
        result = await im.reconcile_phantom_positions()

    assert result["phantom_closed"] == []
    assert any("fetch_positions" in e for e in result["errors"])

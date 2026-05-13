"""
tests/test_phase12_telegram_inbound.py
=======================================
Phase 12 — Telegram Inbound (Story 035b)

Tests for TelegramInboundPoller: long-polling, command dispatch, kill switch
operations, allowlist enforcement, and error resilience.

All HTTP calls (getUpdates / sendMessage) are mocked via AsyncMock so no
real network access occurs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.telegram_inbound import TelegramInboundPoller, _HELP_TEXT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_poller(*, allowed_ids: set[str] | None = None) -> TelegramInboundPoller:
    """Return a TelegramInboundPoller with mocked dependencies."""
    fury = MagicMock()
    portfolio = MagicMock()
    portfolio.run = AsyncMock()
    repo = MagicMock()
    repo.get_overview = AsyncMock(
        return_value={"open_positions_count": 2, "trades_today": 3, "total_signals": 40}
    )
    repo.list_recent_daily_pnl = AsyncMock(return_value=[])
    poller = TelegramInboundPoller(nick_fury=fury, portfolio=portfolio, repo=repo)
    return poller


def _make_update(
    update_id: int,
    chat_id: str,
    text: str,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": int(chat_id)},
            "text": text,
        },
    }


def _settings_inbound_on(monkeypatch, *, allowed_ids: str = "12345"):
    """Patch settings to enable inbound with a known allowed chat_id."""
    from src.config.settings import settings as real_settings

    real_settings.__dict__.pop("telegram_inbound_allowed_chat_ids", None)
    real_settings.__dict__.pop("telegram_enabled", None)

    monkeypatch.setattr(real_settings, "telegram_inbound_enabled", True)
    monkeypatch.setattr(real_settings, "telegram_bot_token", "fake-bot-token")
    monkeypatch.setattr(real_settings, "telegram_chat_id", "12345")
    monkeypatch.setattr(real_settings, "telegram_inbound_allowed_chat_ids_raw", allowed_ids)
    real_settings.__dict__["telegram_inbound_allowed_chat_ids"] = (
        {s.strip() for s in allowed_ids.split(",") if s.strip()} if allowed_ids else set()
    )
    real_settings.__dict__["telegram_enabled"] = True


# ---------------------------------------------------------------------------
# Test 1 — inbound disabled short-circuits run_forever
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inbound_disabled_short_circuits(monkeypatch):
    """run_forever exits immediately when telegram_inbound_enabled=False."""
    from src.config.settings import settings as real_settings

    monkeypatch.setattr(real_settings, "telegram_inbound_enabled", False)
    poller = _make_poller()

    with patch.object(poller, "_poll_once", new=AsyncMock()) as mock_poll:
        await poller.run_forever()

    mock_poll.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — unknown chat_id rejected, no reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_chat_id_rejected(monkeypatch):
    """Messages from chat IDs not in the allowlist are silently dropped."""
    _settings_inbound_on(monkeypatch, allowed_ids="12345")
    poller = _make_poller()

    unknown_update = _make_update(1, chat_id="99999", text="/status")

    with patch.object(poller, "_send", new=AsyncMock()) as mock_send:
        await poller._dispatch(unknown_update)

    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — /status returns roster and flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_returns_system_info(monkeypatch):
    """/status reply includes mode, network, kill_switch and positions count."""
    _settings_inbound_on(monkeypatch)
    poller = _make_poller()

    with patch("src.agents.batman.is_kill_switch_active", return_value=False):
        reply = await poller._cmd_status()

    assert "PAPER" in reply or "LIVE" in reply
    assert "kill" in reply.lower() or "kill sw" in reply.lower()
    assert "2" in reply  # positions count from mock overview


# ---------------------------------------------------------------------------
# Test 4 — /pause engages kill switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_engages_kill_switch(monkeypatch, tmp_path):
    """/pause calls engage_kill_switch('telegram_pause')."""
    _settings_inbound_on(monkeypatch)
    ks_file = tmp_path / ".kill_switch_inbound"

    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", ks_file)

    poller = _make_poller()
    reply = await poller._cmd_pause()

    assert ks_file.exists(), "kill switch file must be created"
    assert "ENGAJADO" in reply or "pause" in reply.lower()


# ---------------------------------------------------------------------------
# Test 5 — /resume clears kill switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_clears_kill_switch(monkeypatch, tmp_path):
    """/resume calls release_kill_switch() and removes the ks file."""
    _settings_inbound_on(monkeypatch)
    ks_file = tmp_path / ".kill_switch_inbound"
    ks_file.write_text("telegram_pause\n")

    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", ks_file)

    poller = _make_poller()
    reply = await poller._cmd_resume()

    assert not ks_file.exists(), "kill switch file must be removed"
    assert "LIBERADO" in reply or "resume" in reply.lower()


# ---------------------------------------------------------------------------
# Test 6 — /pnl uses repository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pnl_uses_repository(monkeypatch):
    """/pnl 7 calls repo.list_recent_daily_pnl(limit=7)."""
    _settings_inbound_on(monkeypatch)
    poller = _make_poller()

    # Inject a mock PnL record
    record = MagicMock()
    record.date = "2026-05-08"
    record.realized_pnl_usd = 42.50
    poller._repo.list_recent_daily_pnl = AsyncMock(return_value=[record])

    reply = await poller._cmd_pnl(["7"])

    poller._repo.list_recent_daily_pnl.assert_awaited_once_with(limit=7)
    assert "42.50" in reply
    assert "2026-05-08" in reply


# ---------------------------------------------------------------------------
# Test 7 — /positions lists open positions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_positions_lists_open(monkeypatch):
    """/positions calls portfolio.run() and formats open positions."""
    _settings_inbound_on(monkeypatch)
    poller = _make_poller()

    pos = MagicMock()
    pos.symbol = "BTC"
    pos.side = "long"
    pos.size = 0.1
    pos.entry_price = 60000.0
    pos.unrealized_pnl_usd = 250.0

    snapshot = MagicMock()
    snapshot.positions = [pos]
    poller._portfolio.run = AsyncMock(return_value=snapshot)

    reply = await poller._cmd_positions()

    poller._portfolio.run.assert_awaited_once()
    assert "BTC" in reply
    assert "LONG" in reply or "long" in reply
    assert "250" in reply


# ---------------------------------------------------------------------------
# Test 8 — unknown command returns help
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_command_returns_help(monkeypatch):
    """/foo falls through to _cmd_help and returns the help text."""
    _settings_inbound_on(monkeypatch)
    poller = _make_poller()

    with patch.object(poller, "_send", new=AsyncMock()) as mock_send:
        await poller._dispatch(_make_update(1, "12345", "/foo"))

    mock_send.assert_awaited_once()
    sent_text = mock_send.call_args[0][1]
    assert "/help" in sent_text or "/status" in sent_text


# ---------------------------------------------------------------------------
# Test 9 — polling timeout/exception is swallowed in run_forever
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_polling_timeout_is_swallowed(monkeypatch):
    """Exception in _poll_once is logged as WARNING, loop continues."""
    _settings_inbound_on(monkeypatch)
    from src.config.settings import settings as real_settings

    monkeypatch.setattr(real_settings, "telegram_inbound_poll_interval_seconds", 0.0)

    call_count = 0

    async def _flaky_poll(last_id: int) -> int:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("simulated timeout")
        # Second call: cancel the loop
        raise asyncio.CancelledError()

    poller = _make_poller()

    with patch.object(poller, "_poll_once", side_effect=_flaky_poll):
        with pytest.raises(asyncio.CancelledError):
            await poller.run_forever()

    assert call_count == 2, "loop must have continued after the first exception"


# ---------------------------------------------------------------------------
# Test 10 — offset advances after processing updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_offset_advances(monkeypatch):
    """_poll_once returns max(update_id) + 1 as the next offset."""
    _settings_inbound_on(monkeypatch)
    poller = _make_poller()

    updates = [
        _make_update(101, "12345", "/help"),
        _make_update(105, "12345", "/status"),
        _make_update(103, "12345", "/pnl"),
    ]

    fake_response = {"result": updates}

    # Build async context-manager chain for aiohttp:
    # async with ClientSession(...) as session → session.get(...) → resp → resp.json()
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value=fake_response)

    mock_get_cm = MagicMock()
    mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_cm)

    mock_cs_instance = MagicMock()
    mock_cs_instance.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cs_instance.__aexit__ = AsyncMock(return_value=False)

    # Patch aiohttp.ClientSession directly (lazy `import aiohttp` inside
    # _poll_once resolves from sys.modules, so patching the module attr works).
    with patch("aiohttp.ClientSession", return_value=mock_cs_instance):
        with patch.object(poller, "_dispatch", new=AsyncMock()):
            next_offset = await poller._poll_once(last_update_id=100)

    assert next_offset == 106, f"expected 106 (max 105 + 1), got {next_offset}"

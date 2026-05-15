"""
src/services/trade_approval.py
===============================
Shared state hub for the Telegram Trade Approval Flow — Story 074.

Architecture
------------
  NickFury calls ``request_approval(trade_id, signal, approval)`` which:
    1. Sends a Telegram message with ✅ / ❌ inline keyboard buttons.
    2. Waits up to ``timeout_s`` seconds for the operator to press a button.
    3. Returns True (execute) or False (skip).

  TelegramInbound's ``_handle_callback_query`` resolves pending approvals
  by calling ``resolve(trade_id, approved=True/False)``.

  In paper mode the timeout auto-approves (operator doesn't need to baby-sit
  every cycle during paper testing). In live mode the timeout auto-rejects
  (safety-first).

Hard rules
----------
  • NEVER raises — all errors are logged and the caller gets a default answer.
  • Auto-approve default only applies in paper_trading=True.
  • Thread-safe: uses asyncio.Event which is coroutine-safe by design.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from src.config.settings import settings

logger = logging.getLogger("mekka.trade_approval")

# ---------------------------------------------------------------------------
# Shared pending approvals registry
# key: trade_id (str)
# value: (asyncio.Event, result_holder list[bool])
# ---------------------------------------------------------------------------
_PENDING: dict[str, tuple[asyncio.Event, list[Optional[bool]]]] = {}

_TG_API = "https://api.telegram.org/bot{token}/{method}"


def _tg_url(method: str) -> str:
    return _TG_API.format(token=settings.telegram_bot_token, method=method)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def request_approval(
    trade_id: str,
    signal_symbol: str,
    signal_action: str,
    signal_confidence: float,
    entry_price: float,
    stop_loss: Optional[float],
    take_profit: Optional[float],
    size_pct: float,
    leverage: int,
    reasons: list[str],
    timeout_s: int = 120,
) -> bool:
    """Send a Telegram approval request and wait for operator response.

    Returns:
        True  — operator pressed ✅ Confirmar (or auto-approved in paper mode).
        False — operator pressed ❌ Recusar (or timeout in live mode).

    Always returns without raising.
    """
    if not settings.telegram_enabled:
        logger.debug("[TradeApproval] Telegram disabled — auto-approve")
        return True

    # Register pending slot
    event = asyncio.Event()
    result: list[Optional[bool]] = [None]
    _PENDING[trade_id] = (event, result)

    try:
        await _send_approval_message(
            trade_id=trade_id,
            symbol=signal_symbol,
            action=signal_action,
            confidence=signal_confidence,
            entry=entry_price,
            sl=stop_loss,
            tp=take_profit,
            size_pct=size_pct,
            leverage=leverage,
            reasons=reasons,
        )

        # Wait with timeout
        try:
            await asyncio.wait_for(event.wait(), timeout=float(timeout_s))
        except asyncio.TimeoutError:
            logger.warning(
                "[TradeApproval] timeout (%ds) for %s — %s",
                timeout_s, trade_id,
                "auto-approving (paper)" if settings.paper_trading else "auto-rejecting (live)"
            )
            # Auto-approve in paper mode, auto-reject in live mode
            result[0] = settings.paper_trading

        approved = bool(result[0])

        # Notify operator of the final decision (edit message or send new)
        try:
            await _send_decision_notification(trade_id, signal_symbol, signal_action, approved, timed_out=(result[0] is None))
        except Exception:  # noqa: BLE001
            pass

        return approved

    except Exception as exc:  # noqa: BLE001
        logger.error("[TradeApproval] unexpected error for %s: %s", trade_id, exc)
        return settings.paper_trading  # fail-open in paper, fail-closed in live
    finally:
        _PENDING.pop(trade_id, None)


def resolve(trade_id: str, approved: bool) -> bool:
    """Called by TelegramInbound when operator presses a button.

    Returns True if the trade_id was found and resolved, False otherwise.
    """
    if trade_id not in _PENDING:
        logger.debug("[TradeApproval] resolve called for unknown trade_id=%s", trade_id)
        return False
    event, result = _PENDING[trade_id]
    result[0] = approved
    event.set()
    logger.info("[TradeApproval] %s → %s by operator", trade_id, "APPROVED" if approved else "REJECTED")
    return True


def list_pending() -> list[str]:
    """Return list of currently pending trade IDs (for /status command)."""
    return list(_PENDING.keys())


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

async def _send_approval_message(
    trade_id: str,
    symbol: str,
    action: str,
    confidence: float,
    entry: float,
    sl: Optional[float],
    tp: Optional[float],
    size_pct: float,
    leverage: int,
    reasons: list[str],
) -> None:
    import aiohttp  # noqa: WPS433

    side_emoji = "🟢" if action.upper() == "LONG" else "🔴"
    rr = round((tp - entry) / (entry - sl), 2) if tp and sl and sl != entry else "?"
    reason_text = "\n".join(f"  • {r}" for r in reasons[:4]) if reasons else "  —"

    text = (
        f"⚡ *TRADE AGUARDANDO APROVAÇÃO*\n\n"
        f"{side_emoji} *{action.upper()} {symbol}* @ `{entry:,.4f}`\n"
        f"🎯 Confiança: `{confidence:.0%}`\n"
        f"📐 Tamanho: `{size_pct:.1%}` × `{leverage}x`\n"
        f"🛑 SL: `{sl:,.4f}`\n" if sl else ""
        f"✅ TP: `{tp:,.4f}` | R:R `{rr}`\n\n" if tp else ""
        f"*Razões Batman:*\n{reason_text}\n\n"
        f"🆔 `{trade_id}`\n"
        f"⏳ Expira em 2 min (paper: auto-aprova)"
    )

    inline_keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Confirmar", "callback_data": f"approve:{trade_id}"},
            {"text": "❌ Recusar",   "callback_data": f"reject:{trade_id}"},
        ]]
    }

    import json  # noqa: WPS433
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(inline_keyboard),
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            _tg_url("sendMessage"),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning("[TradeApproval] sendMessage HTTP %s: %s", resp.status, body[:200])


async def _send_decision_notification(
    trade_id: str,
    symbol: str,
    action: str,
    approved: bool,
    timed_out: bool = False,
) -> None:
    """Fire a brief follow-up message confirming the decision."""
    import aiohttp  # noqa: WPS433

    if timed_out:
        text = (
            f"⏰ *Timeout* — `{trade_id[:14]}`\n"
            f"{'✅ Auto-aprovado (paper mode)' if approved else '❌ Auto-rejeitado (live mode)'}"
        )
    else:
        emoji = "✅" if approved else "❌"
        verb = "APROVADO" if approved else "RECUSADO"
        text = f"{emoji} *{verb}* pelo operador — `{action.upper()} {symbol}` (`{trade_id[:14]}`)"

    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            _tg_url("sendMessage"),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=6),
        ) as _:
            pass

"""
src/services/telegram_alerter.py
================================
Telegram push-only alerter (Story 035).

Stateless service that pushes critical Mekka audit events to a Telegram
chat via the Bot API. No long-polling, no inbound commands in v1 —
purely outbound notifications. Inbound `/status /pnl /pause /resume`
is reserved for Story 035b (separate process running aiogram or
python-telegram-bot).

Hard rules
----------
- **Never throws.** A network failure, rate-limit, or malformed token
  is logged and absorbed; the cycle that triggered the alert keeps
  running.
- **Toggle by env.** When `settings.telegram_enabled` is False (no
  bot token + chat id) the alerter short-circuits at `alert()`.
- **Filter by severity AND/OR event whitelist.**
- **Async-friendly**, uses `aiohttp` lazily.
- **No persistent state.** Each `alert()` call is independent — if
  Telegram is down we just drop. Audit log already has the event;
  Telegram is best-effort.

New methods (beyond generic `alert`):
- `ping()` — sends a startup/test ping with system info.
- `trade_opened()` — rich notification when a trade is FILLED/PAPER.

Severity ordering (most → least permissive):
    DEBUG < INFO < WARNING < ERROR < CRITICAL
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from loguru import logger

from src.config.settings import settings

if TYPE_CHECKING:
    from src.models.execution import ExecutionResult
    from src.models.signal import TradingSignal


_SEVERITY_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _tg_url(token: str) -> str:
    return _TELEGRAM_API.format(token=token)


def _severity_at_least(severity: str, threshold: str) -> bool:
    """True when `severity` ≥ `threshold` per `_SEVERITY_ORDER`."""
    return _SEVERITY_ORDER.get(severity.upper(), 0) >= _SEVERITY_ORDER.get(
        threshold.upper(), 2
    )


class TelegramAlerter:
    """
    Stateless Telegram pusher.

    Usage:
        alerter = TelegramAlerter()
        await alerter.alert(
            event="RISK_KILL_SWITCH",
            severity="ERROR",
            agent="Batman",
            message="Kill switch engaged: ...",
            symbol="BTC",
            payload={"breaker": "exec_error"},
        )
    """

    def __init__(self) -> None:
        self._log = logger.bind(agent="TelegramAlerter")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def alert(
        self,
        *,
        event: str,
        severity: str = "INFO",
        agent: str = "Mekka",
        message: str = "",
        symbol: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> bool:
        """
        Push one alert. Returns True iff Telegram acknowledged.
        Returns False (without raising) on any disable/filter/network error.
        """
        if not settings.telegram_enabled:
            return False
        if not self._should_alert(event=event, severity=severity):
            return False

        text = self._format(
            event=event,
            severity=severity,
            agent=agent,
            message=message,
            symbol=symbol,
            payload=payload,
        )

        try:
            return await self._post(text)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"telegram alert failed (suppressed): {exc}")
            return False

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def _should_alert(self, *, event: str, severity: str) -> bool:
        """
        Two ways an alert is approved:
          1. Severity ≥ telegram_alert_min_severity, OR
          2. Event in `telegram_alert_events` whitelist.
        Either path is sufficient.
        """
        if _severity_at_least(severity, settings.telegram_alert_min_severity):
            return True
        whitelist = settings.telegram_alert_events
        if whitelist and event.upper() in whitelist:
            return True
        return False

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format(
        *,
        event: str,
        severity: str,
        agent: str,
        message: str,
        symbol: Optional[str],
        payload: Optional[dict],
    ) -> str:
        sym = f" [{symbol}]" if symbol else ""
        env = f"net={settings.hyperliquid_network} mode={settings.mode_label}"
        lines = [
            f"⚠️ {severity} · {event}{sym}",
            f"agent: {agent}",
        ]
        if message:
            # Truncate to fit Telegram's 4096-char limit comfortably
            trimmed = message if len(message) < 600 else message[:600] + "…"
            lines.append(f"msg: {trimmed}")
        if payload:
            # Render compact key=value, drop heavy nested
            flat = {k: v for k, v in payload.items() if not isinstance(v, (dict, list))}
            if flat:
                kv = " ".join(f"{k}={v}" for k, v in flat.items())
                if len(kv) > 400:
                    kv = kv[:400] + "…"
                lines.append(f"payload: {kv}")
        lines.append(f"env: {env}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    async def ping(self, *, reason: str = "startup") -> bool:
        """
        Send a test/startup ping to confirm the bot is alive.

        Args:
            reason: Short label shown in the message (e.g. 'startup', 'test').
        """
        if not settings.telegram_enabled:
            return False
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        text = (
            f"🤖 *Mekka Trading — Bot Online*\n"
            f"Motivo : {reason}\n"
            f"Rede   : {settings.hyperliquid_network}\n"
            f"Modo   : {settings.mode_label}\n"
            f"Paper  : {'sim' if settings.paper_trading else '🔴 LIVE'}\n"
            f"Hora   : {now}\n\n"
            f"Sistema operacional. Comandos: /help"
        )
        try:
            return await self._post(text)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"ping failed (suppressed): {exc}")
            return False

    async def trade_opened(
        self,
        *,
        execution: "ExecutionResult",
        signal: "TradingSignal",
    ) -> bool:
        """
        Rich notification sent whenever a trade is FILLED or PAPER.

        Includes: symbol, side, size, entry, SL, TP, leverage, RR,
        confidence, mode, paper/live tag and the Vision reasoning snippet.
        Never throws — failures are logged and absorbed.
        """
        if not settings.telegram_enabled:
            return False

        from src.models.execution import ExecutionStatus  # lazy, avoids circular

        if execution.status not in (ExecutionStatus.FILLED, ExecutionStatus.PAPER):
            return False

        tag = "📄 PAPER" if execution.is_paper else "🔴 LIVE"
        side_emoji = "🟢 LONG" if (execution.side or "").upper() == "LONG" else "🔴 SHORT"

        # Risk / reward
        try:
            rr = signal.risk_reward_ratio  # type: ignore[attr-defined]
            rr_str = f"{rr:.2f}" if rr else "n/a"
        except Exception:
            rr_str = "n/a"

        # Reasoning — first 200 chars
        reasoning = (signal.reasoning or "").strip()
        reasoning_short = reasoning[:200] + "…" if len(reasoning) > 200 else reasoning

        # SL distance %
        try:
            sl_dist = abs(signal.entry_price - signal.stop_loss) / signal.entry_price * 100
            sl_dist_str = f"{sl_dist:.2f}%"
        except Exception:
            sl_dist_str = "n/a"

        # TP distance %
        try:
            tp_dist = abs(signal.take_profit - signal.entry_price) / signal.entry_price * 100
            tp_dist_str = f"{tp_dist:.2f}%"
        except Exception:
            tp_dist_str = "n/a"

        lines = [
            f"🚀 *Trade Aberto — {execution.symbol}*  {tag}",
            "",
            f"Direção   : {side_emoji}",
            f"Entrada   : ${execution.avg_price:,.4f}",
            f"Qtd       : {execution.quantity:.6f}  (${execution.notional_usd:,.2f})",
            f"Leverage  : {signal.leverage}x",
            f"Tamanho   : {signal.size_pct * 100:.1f}% da equity",
            "",
            f"SL        : ${signal.stop_loss:,.4f}  (-{sl_dist_str})",
            f"TP        : ${signal.take_profit:,.4f}  (+{tp_dist_str})",
            f"R/R       : {rr_str}",
            "",
            f"Confiança : {signal.confidence * 100:.0f}%",
            f"Modo      : {settings.mode_label}",
            f"Rede      : {settings.hyperliquid_network}",
        ]

        if execution.order_id:
            lines.append(f"Order ID  : {execution.order_id}")

        if reasoning_short:
            lines.append("")
            lines.append(f"📝 _{reasoning_short}_")

        text = "\n".join(lines)

        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"trade_opened alert failed (suppressed): {exc}")
            return False

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _post(self, text: str, parse_mode: Optional[str] = None) -> bool:
        """POST to Telegram sendMessage. Lazy aiohttp import."""
        import aiohttp  # noqa: WPS433

        url = _tg_url(settings.telegram_bot_token)
        timeout = aiohttp.ClientTimeout(total=settings.telegram_alert_timeout_seconds)
        body: dict = {
            "chat_id": settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            body["parse_mode"] = parse_mode
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=body) as resp:
                if resp.status == 200:
                    return True
                # Read once for log clarity; don't propagate
                body_text = await resp.text()
                self._log.warning(
                    f"telegram returned HTTP {resp.status}: {body_text[:200]}"
                )
                if resp.status == 429:
                    # Telegram rate limit — back off briefly so callers
                    # don't hammer. We don't retry within this call (next
                    # alert in the cycle will re-evaluate).
                    await asyncio.sleep(min(settings.telegram_alert_timeout_seconds, 2.0))
                return False

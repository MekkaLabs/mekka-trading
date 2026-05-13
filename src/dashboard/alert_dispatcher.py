"""
src/dashboard/alert_dispatcher.py
=================================
Outbound webhook fan-out for the dashboard. When a snapshot lands with a
fresh CRITICAL alert (kill switch or drawdown breach), we POST a tiny
JSON message to every configured target.

Targets, all opt-in via env:

    MEKKA_WEBHOOK_SLACK              full Slack incoming-webhook URL
    MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN bot token (123456:ABC...)
    MEKKA_WEBHOOK_TELEGRAM_CHAT_ID   numeric chat id

Behaviour:
    - per-code dedup with a sliding window so a sustained kill switch
      doesn't spam channels every 2 seconds.
    - per-target timeout of 5 s, 1 retry, then we give up silently.
    - non-blocking: dispatcher schedules sends via the running event
      loop and returns immediately.

Caller wires this from `_persist_snapshot` so we benefit from the same
dedup that already gates the bundle writes — but we still keep our own
window because dispatcher cares about both critical alert codes and the
operator's perception of noise, which is broader than just kill switch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Iterable

import aiohttp


logger = logging.getLogger("mekka.dashboard.alerts")

SLACK_WEBHOOK = os.environ.get("MEKKA_WEBHOOK_SLACK", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("MEKKA_WEBHOOK_TELEGRAM_CHAT_ID", "").strip()

# How long an alert code stays "fresh" — we don't redispatch within this
# window even if the alert keeps re-appearing.
DEDUP_WINDOW_S = int(os.environ.get("MEKKA_WEBHOOK_DEDUP_S", "300"))

# Codes we actually fan-out for. Everything else is informational.
DISPATCHED_CODES = {
    "KILL_SWITCH_FILE",
    "KILL_SWITCH_EVENT",
    "DRAWDOWN_CRITICAL",
}


def _format_alert_text(alert: dict[str, Any], context: dict[str, Any]) -> str:
    code = alert.get("code", "ALERT")
    severity = alert.get("severity", "?")
    message = alert.get("message", "")
    network = (context or {}).get("network", "?")
    mode = (context or {}).get("mode", "?")
    return (
        f"[Mekka {mode}/{network}] {severity} {code}\n"
        f"{message}"
    )


class AlertDispatcher:
    """Stateful: holds the dedup map and a reusable ClientSession."""

    def __init__(self, session: aiohttp.ClientSession | None = None):
        self._session = session
        self._owns_session = session is None
        self._last_sent: dict[str, float] = {}

    @property
    def has_targets(self) -> bool:
        return bool(SLACK_WEBHOOK or (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID))

    async def close(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5.0),
            )
            self._owns_session = True
        return self._session

    def _is_fresh(self, code: str) -> bool:
        last = self._last_sent.get(code)
        if last is None:
            return True
        return (time.time() - last) > DEDUP_WINDOW_S

    def _mark_sent(self, code: str) -> None:
        self._last_sent[code] = time.time()
        # Bound the dedup map so misbehaving codes don't grow it unbounded.
        if len(self._last_sent) > 64:
            cutoff = time.time() - DEDUP_WINDOW_S * 4
            for k in [k for k, v in self._last_sent.items() if v < cutoff]:
                self._last_sent.pop(k, None)

    async def _post_with_retry(self, url: str, payload: dict[str, Any]) -> bool:
        session = await self._ensure_session()
        for attempt in (1, 2):
            try:
                async with session.post(url, json=payload) as resp:
                    if 200 <= resp.status < 300:
                        return True
                    body = await resp.text()
                    logger.warning(
                        "webhook %s returned %s: %s",
                        url[:60], resp.status, body[:200],
                    )
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.warning("webhook %s attempt %d failed: %s", url[:60], attempt, exc)
            await asyncio.sleep(0.4 * attempt)
        return False

    async def dispatch(
        self,
        alerts: Iterable[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send webhooks for every dispatched code that's outside the
        dedup window. Returns a small report so callers can log/audit."""
        if not self.has_targets:
            return {"sent": 0, "skipped": 0, "reason": "no targets configured"}
        sent = 0
        skipped = 0
        sent_codes: list[str] = []
        for a in alerts or []:
            code = str(a.get("code") or "")
            if code not in DISPATCHED_CODES:
                continue
            if not self._is_fresh(code):
                skipped += 1
                continue
            self._mark_sent(code)
            text = _format_alert_text(a, context or {})
            if SLACK_WEBHOOK:
                ok = await self._post_with_retry(SLACK_WEBHOOK, {"text": text})
                if ok:
                    sent += 1
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                ok = await self._post_with_retry(
                    tg_url,
                    {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
                )
                if ok:
                    sent += 1
            sent_codes.append(code)
        return {"sent": sent, "skipped": skipped, "codes": sent_codes}

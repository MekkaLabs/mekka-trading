"""
src/dashboard/daily_reporter.py
================================
Daily PnL report — scheduled at 23:55 UTC every day.

Pulls today's PnL summary from ``MekkaRepository.get_pnl_summary`` (window=1)
plus all-time stats and formats a rich message for Slack and Telegram.

Design decisions
----------------
* One-shot per UTC calendar day — dedup via ``_last_report_date`` so even
  if the server restarts at 23:56 we don't double-send.
* Builds two payloads: Slack Block Kit (rich) and Telegram Markdown (text).
* Delegates HTTP fan-out to ``AlertDispatcher._post_with_retry`` (same session,
  same 5s timeout, same 1-retry policy) — no new HTTP machinery needed.
* ``send_daily_report()`` is also callable on-demand (REST endpoint / /report).

Env vars consumed (all optional — no report if both absent)
-----------------------------------------------------------
    MEKKA_WEBHOOK_SLACK              full Slack incoming-webhook URL
    MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN bot token (123456:ABC...)
    MEKKA_WEBHOOK_TELEGRAM_CHAT_ID   numeric chat id

New env var (optional):
    MEKKA_DAILY_REPORT_HOUR_UTC      hour to fire (0-23, default 23)
    MEKKA_DAILY_REPORT_MINUTE_UTC    minute to fire (0-59, default 55)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import aiohttp

from src.persistence.repository import MekkaRepository

if TYPE_CHECKING:
    from src.models.performance import PerformanceReport

logger = logging.getLogger("mekka.dashboard.daily_reporter")

# ── Config ────────────────────────────────────────────────────────────────────

SLACK_WEBHOOK = os.environ.get("MEKKA_WEBHOOK_SLACK", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("MEKKA_WEBHOOK_TELEGRAM_CHAT_ID", "").strip()

REPORT_HOUR_UTC = int(os.environ.get("MEKKA_DAILY_REPORT_HOUR_UTC", "23"))
REPORT_MINUTE_UTC = int(os.environ.get("MEKKA_DAILY_REPORT_MINUTE_UTC", "55"))


# ── Formatting helpers ─────────────────────────────────────────────────────────


def _pnl_emoji(pnl: float) -> str:
    if pnl > 0:
        return "🟢"
    if pnl < 0:
        return "🔴"
    return "⚪"


def _win_rate_str(win_rate: float | None) -> str:
    if win_rate is None:
        return "n/a"
    return f"{win_rate * 100:.1f}%"


def _dd_emoji(dd: float) -> str:
    if dd >= 0.10:
        return "🚨"
    if dd >= 0.05:
        return "⚠️"
    return "✅"


def build_telegram_message(
    today: dict,
    all_time: dict,
    date_str: str,
    perf: "PerformanceReport | None" = None,
) -> str:
    """Build Telegram Markdown (v1) text for the daily report.

    ``perf`` is an optional Deadpool PerformanceReport that, when present,
    adds Sortino, streaks, expectancy and the verdict to the message.
    """
    pnl = today.get("pnl_usd", 0.0)
    equity = today.get("latest_equity_usd", 0.0)
    trades = today.get("trades", 0)
    wins = today.get("wins", 0)
    losses = today.get("losses", 0)
    wr = today.get("win_rate")
    dd = today.get("max_drawdown_pct", 0.0)

    at_pnl = all_time.get("pnl_usd", 0.0)
    at_days = all_time.get("trading_days", 0)
    at_trades = all_time.get("trades", 0)
    at_wr = all_time.get("win_rate")

    emoji = _pnl_emoji(pnl)
    dd_e = _dd_emoji(dd)

    lines = [
        f"📊 *Mekka Daily Report — {date_str}*",
        "",
        f"{emoji} *PnL Hoje:* ${pnl:+.2f}",
        f"💰 *Equity:* ${equity:,.2f}",
        f"📈 *Trades:* {trades}  (W:{wins} L:{losses}  WR:{_win_rate_str(wr)})",
        f"{dd_e} *Drawdown:* {dd * 100:.2f}%",
        "",
        "─── All-time ───",
        f"Total PnL   : ${at_pnl:+.2f}",
        f"Dias activos: {at_days}",
        f"Trades total: {at_trades}",
        f"Win rate    : {_win_rate_str(at_wr)}",
    ]

    # ── Deadpool advanced metrics (Story 062) ────────────────────────
    if perf is not None:
        adv: list[str] = []

        sharpe_str = f"{perf.sharpe_estimate:.2f}" if perf.sharpe_estimate is not None else "n/a"
        sortino_str = f"{perf.sortino_estimate:.2f}" if perf.sortino_estimate is not None else "n/a"
        adv.append(f"Sharpe      : {sharpe_str}   Sortino: {sortino_str}")

        exp_str = f"${perf.expectancy_usd:+.2f}/trade" if perf.expectancy_usd is not None else "n/a"
        avg_w_str = f"${perf.avg_win_usd:.2f}" if perf.avg_win_usd is not None else "n/a"
        avg_l_str = f"${perf.avg_loss_usd:.2f}" if perf.avg_loss_usd is not None else "n/a"
        adv.append(f"Expectancy  : {exp_str}  (W avg:{avg_w_str}  L avg:{avg_l_str})")

        streak_cur = perf.current_streak
        if streak_cur > 0:
            streak_str = f"🟢 {streak_cur} vitórias seguidas"
        elif streak_cur < 0:
            streak_str = f"🔴 {abs(streak_cur)} perdas seguidas"
        else:
            streak_str = "neutro"
        adv.append(f"Streak atual: {streak_str}")
        adv.append(f"Máx. win streak: {perf.max_winning_streak}   Máx. loss streak: {perf.max_losing_streak}")

        # Verdict
        _VERDICT_EMOJI = {"READY": "✅", "NOT_READY": "⚠️", "INSUFFICIENT_DATA": "⏳"}
        v_emoji = _VERDICT_EMOJI.get(perf.verdict, "❓")
        adv.append(f"Veredicto   : {v_emoji} {perf.verdict}")

        if adv:
            lines += ["", "─── Deadpool Analytics ───"] + adv

    return "\n".join(lines)


def build_slack_blocks(today: dict, all_time: dict, date_str: str) -> dict:
    """Build Slack Block Kit payload for the daily report."""
    pnl = today.get("pnl_usd", 0.0)
    equity = today.get("latest_equity_usd", 0.0)
    trades = today.get("trades", 0)
    wins = today.get("wins", 0)
    losses = today.get("losses", 0)
    wr = today.get("win_rate")
    dd = today.get("max_drawdown_pct", 0.0)

    at_pnl = all_time.get("pnl_usd", 0.0)
    at_days = all_time.get("trading_days", 0)
    at_trades = all_time.get("trades", 0)
    at_wr = all_time.get("win_rate")

    emoji = _pnl_emoji(pnl)
    dd_e = _dd_emoji(dd)

    header = f"{emoji} Mekka Daily Report — {date_str}"

    fields_today = [
        {"type": "mrkdwn", "text": f"*PnL Hoje*\n${pnl:+.2f}"},
        {"type": "mrkdwn", "text": f"*Equity*\n${equity:,.2f}"},
        {"type": "mrkdwn", "text": f"*Trades*\n{trades}  (W:{wins} L:{losses})"},
        {"type": "mrkdwn", "text": f"*Win Rate*\n{_win_rate_str(wr)}"},
        {"type": "mrkdwn", "text": f"*Drawdown*\n{dd_e} {dd * 100:.2f}%"},
    ]

    fields_alltime = [
        {"type": "mrkdwn", "text": f"*All-time PnL*\n${at_pnl:+.2f}"},
        {"type": "mrkdwn", "text": f"*Dias activos*\n{at_days}"},
        {"type": "mrkdwn", "text": f"*Trades total*\n{at_trades}"},
        {"type": "mrkdwn", "text": f"*Win Rate AT*\n{_win_rate_str(at_wr)}"},
    ]

    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": header, "emoji": True},
            },
            {"type": "divider"},
            {"type": "section", "fields": fields_today},
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "All-time"},
                ],
            },
            {"type": "section", "fields": fields_alltime},
        ]
    }


# ── Core class ────────────────────────────────────────────────────────────────


class DailyReporter:
    """
    Sends daily PnL reports to Slack and/or Telegram.

    Usage — scheduled (server wires this):
        reporter = DailyReporter()
        asyncio.create_task(reporter.run_loop())

    Usage — on-demand (REST endpoint / /report Telegram command):
        reporter = DailyReporter()
        result = await reporter.send_daily_report(force=True)
    """

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        repo: type[MekkaRepository] = MekkaRepository,
    ) -> None:
        self._session = session
        self._owns_session = session is None
        self._repo = repo
        self._last_report_date: str | None = None  # "YYYY-MM-DD"

    @property
    def has_targets(self) -> bool:
        return bool(SLACK_WEBHOOK or (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID))

    async def close(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8.0),
            )
            self._owns_session = True
        return self._session

    async def _post_with_retry(self, url: str, payload: dict[str, Any]) -> bool:
        session = await self._ensure_session()
        for attempt in (1, 2):
            try:
                async with session.post(url, json=payload) as resp:
                    if 200 <= resp.status < 300:
                        return True
                    body = await resp.text()
                    logger.warning(
                        "daily_reporter webhook %s returned %s: %s",
                        url[:60],
                        resp.status,
                        body[:200],
                    )
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.warning(
                    "daily_reporter webhook %s attempt %d failed: %s",
                    url[:60],
                    attempt,
                    exc,
                )
            await asyncio.sleep(0.4 * attempt)
        return False

    async def send_daily_report(self, *, force: bool = False) -> dict[str, Any]:
        """
        Fetch today's PnL and push the report to all configured targets.

        Args:
            force: If True, skip the same-day dedup guard.

        Returns:
            dict with keys: date, sent_slack, sent_telegram, skipped, error
        """
        now_utc = datetime.now(timezone.utc)
        date_str = now_utc.strftime("%Y-%m-%d")

        # Dedup — don't send twice on the same day unless forced.
        if not force and self._last_report_date == date_str:
            logger.info("daily_reporter: report already sent for %s — skipping", date_str)
            return {"date": date_str, "sent_slack": False, "sent_telegram": False, "skipped": True}

        if not self.has_targets:
            logger.info("daily_reporter: no webhook targets configured — skipping")
            return {"date": date_str, "sent_slack": False, "sent_telegram": False, "skipped": True, "reason": "no targets"}

        # Fetch PnL data — today (window=1) + all-time
        try:
            summary = await asyncio.wait_for(
                self._repo.get_pnl_summary(window_days=1), timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("daily_reporter: get_pnl_summary timed out")
            return {"date": date_str, "sent_slack": False, "sent_telegram": False, "error": "db_timeout"}
        except Exception as exc:  # noqa: BLE001
            logger.error("daily_reporter: get_pnl_summary failed: %s", exc)
            return {"date": date_str, "sent_slack": False, "sent_telegram": False, "error": str(exc)}

        today_data = summary.get("window", {})
        all_time_data = summary.get("all_time", {})

        # ── Deadpool advanced metrics (Story 062) ──────────────────────────
        perf: "PerformanceReport | None" = None
        try:
            from src.agents.deadpool import Deadpool  # noqa: WPS433
            perf = await asyncio.wait_for(
                Deadpool(self._repo).run(window_days=30), timeout=10.0
            )
        except Exception as _exc:  # noqa: BLE001
            logger.warning("daily_reporter: Deadpool run failed (proceeding without): %s", _exc)

        sent_slack = False
        sent_telegram = False

        # ── Slack ──────────────────────────────────────────────────────────
        if SLACK_WEBHOOK:
            payload = build_slack_blocks(today_data, all_time_data, date_str)
            sent_slack = await self._post_with_retry(SLACK_WEBHOOK, payload)
            if sent_slack:
                logger.info("daily_reporter: Slack report sent for %s", date_str)
            else:
                logger.warning("daily_reporter: Slack send failed for %s", date_str)

        # ── Telegram ───────────────────────────────────────────────────────
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            text = build_telegram_message(today_data, all_time_data, date_str, perf=perf)
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            sent_telegram = await self._post_with_retry(
                tg_url,
                {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            if sent_telegram:
                logger.info("daily_reporter: Telegram report sent for %s", date_str)
            else:
                logger.warning("daily_reporter: Telegram send failed for %s", date_str)

        # Mark as sent only when at least one target succeeded.
        if sent_slack or sent_telegram:
            self._last_report_date = date_str

        return {
            "date": date_str,
            "sent_slack": sent_slack,
            "sent_telegram": sent_telegram,
            "skipped": False,
            "today_pnl_usd": today_data.get("pnl_usd"),
            "today_trades": today_data.get("trades"),
        }

    # ── Scheduler loop ────────────────────────────────────────────────────────

    async def run_loop(self) -> None:
        """
        Asyncio task: wait until REPORT_HOUR_UTC:REPORT_MINUTE_UTC each day,
        then call send_daily_report(). Absorbs all errors and loops forever.
        """
        logger.info(
            "daily_reporter: scheduler started — fires at %02d:%02d UTC",
            REPORT_HOUR_UTC,
            REPORT_MINUTE_UTC,
        )
        while True:
            try:
                await self._sleep_until_report_time()
                result = await self.send_daily_report()
                logger.info("daily_reporter: loop result: %s", result)
            except asyncio.CancelledError:
                logger.info("daily_reporter: loop cancelled — shutting down")
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("daily_reporter: unexpected error in loop: %s", exc)
                # Back off 1 min before retrying so we don't spin on a bad state.
                await asyncio.sleep(60)

    async def _sleep_until_report_time(self) -> None:
        """Sleep until the next REPORT_HOUR_UTC:REPORT_MINUTE_UTC wall clock."""
        now = datetime.now(timezone.utc)
        target = now.replace(
            hour=REPORT_HOUR_UTC,
            minute=REPORT_MINUTE_UTC,
            second=0,
            microsecond=0,
        )
        if target <= now:
            # Already past today's window — aim for tomorrow.
            from datetime import timedelta
            target += timedelta(days=1)

        wait_s = (target - now).total_seconds()
        logger.debug("daily_reporter: sleeping %.0f s until %s", wait_s, target.isoformat())
        await asyncio.sleep(wait_s)

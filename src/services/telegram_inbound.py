"""
src/services/telegram_inbound.py
=================================
Telegram inbound command handler (Story 035b).

Long-polling against api.telegram.org/getUpdates.  Dispatches operator
commands to internal handlers and sends replies via the same Bot API.

Supported commands
------------------
    /status     — system overview (mode, network, kill_switch, positions)
    /pnl [N]    — last N daily PnL records (default 7)
    /pause      — engage kill switch (source: telegram_pause)
    /resume     — release kill switch
    /positions  — list open positions from PortfolioManager
    /perf [N]   — Deadpool performance report (N days, default 30)
    /gates      — show H1–H6 mainnet gate status
    /help       — command reference

Security
--------
    Every inbound update is checked against
    ``settings.telegram_inbound_allowed_chat_ids``.  Updates from unknown
    chat IDs are silently dropped (log warning, no reply) — no information
    leakage via error messages.

Design decisions
----------------
    • Long-polling, NOT webhook.  Webhook requires TLS + public port —
      unnecessary friction for paper-trading ops.  See ADR-002 (Story doc).
    • Errors in ``_poll_once`` are logged as WARNING and the loop continues —
      same pattern as TelegramAlerter.
    • ``run_forever`` runs as an asyncio Task; it does NOT spawn threads.
    • Dependencies (NickFury, PortfolioManager, MekkaRepository) are injected
      at construction time so tests can mock them cleanly.

Usage (standalone)
------------------
    python -m src.services.telegram_inbound

Usage (integrated — optional, not required for v1)
------------------
    if settings.telegram_inbound_enabled:
        asyncio.create_task(poller.run_forever())
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from loguru import logger

from src.config.settings import settings
from src.persistence.repository import MekkaRepository

if TYPE_CHECKING:
    from src.agents.nick_fury import NickFury
    from src.agents.portfolio_manager import PortfolioManager

# Module-level sentinel — allows tests to patch via
# patch("src.services.telegram_inbound.Deadpool").
# The handlers check this first; if None, they do a lazy import.
Deadpool = None  # type: ignore[assignment]

_TG_API = "https://api.telegram.org/bot{token}/{method}"

_HELP_TEXT = (
    "Mekka Trading — comandos disponíveis:\n"
    "/status     — visão geral do sistema\n"
    "/pnl [N]    — últimos N dias de PnL (padrão: 7)\n"
    "/pause      — engaja kill switch\n"
    "/resume     — libera kill switch\n"
    "/positions  — posições abertas\n"
    "/perf [N]   — relatório Deadpool (N dias, padrão: 30)\n"
    "/gates      — status gates H1–H6 mainnet\n"
    "/mode [X]   — mostra ou muda modo (conservative/balanced/aggressive)\n"
    "/report     — envia relatório diário agora (Slack + Telegram)\n"
    "/ping       — testa conexão e exibe status do bot\n"
    "/help       — esta mensagem"
)


class TelegramInboundPoller:
    """
    Long-polling stateless poller against api.telegram.org/getUpdates.

    Dispatches operator commands to internal handlers.  Every reply is
    sent via Telegram sendMessage (same Bot API token as TelegramAlerter).
    """

    def __init__(
        self,
        *,
        nick_fury: "NickFury",
        portfolio: "PortfolioManager",
        repo: type[MekkaRepository] = MekkaRepository,
    ) -> None:
        self._fury = nick_fury
        self._portfolio = portfolio
        self._repo = repo
        self._log = logger.bind(agent="TelegramInbound")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """
        Entry point.  Exits immediately when
        ``settings.telegram_inbound_enabled`` is False.
        Loops forever otherwise, absorbing transient errors.
        """
        if not settings.telegram_inbound_enabled:
            self._log.info("telegram_inbound disabled — poller not started")
            return

        self._log.info(
            "TelegramInboundPoller starting "
            f"(poll_interval={settings.telegram_inbound_poll_interval_seconds}s)"
        )
        last_update_id = 0
        while True:
            try:
                last_update_id = await self._poll_once(last_update_id)
            except asyncio.CancelledError:
                self._log.info("TelegramInboundPoller cancelled — shutting down")
                raise
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"poll_once error (swallowed): {exc}")
            await asyncio.sleep(settings.telegram_inbound_poll_interval_seconds)

    async def _poll_once(self, last_update_id: int) -> int:
        """
        Call getUpdates with long-poll timeout.  Returns the next offset
        (highest update_id seen + 1), or ``last_update_id`` if no updates.
        """
        import aiohttp  # noqa: WPS433

        url = _TG_API.format(token=settings.telegram_bot_token, method="getUpdates")
        params = {
            "offset": last_update_id,
            "timeout": settings.telegram_inbound_long_poll_timeout_seconds,
            "allowed_updates": ["message"],
        }
        timeout = aiohttp.ClientTimeout(
            total=settings.telegram_inbound_long_poll_timeout_seconds + 5
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()

        updates = data.get("result", [])
        if not updates:
            return last_update_id

        for update in updates:
            await self._dispatch(update)

        max_id: int = max(u["update_id"] for u in updates)
        return max_id + 1

    async def _dispatch(self, update: dict) -> None:
        """
        Route one inbound update to the appropriate handler.
        Silently drops messages from chat IDs not in the allowlist.
        """
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text: str = (message.get("text") or "").strip()

        if not chat_id or not text:
            return

        allowed = settings.telegram_inbound_allowed_chat_ids
        if not allowed:
            # Fail-closed: no explicit allowlist configured.
            # Fall back to the primary TELEGRAM_CHAT_ID as the sole allowed ID.
            # This prevents any random chat_id from issuing commands when the
            # operator hasn't set TELEGRAM_INBOUND_ALLOWED_CHAT_IDS.
            primary = str(getattr(settings, "telegram_chat_id", "") or "").strip()
            if not primary or chat_id != primary:
                self._log.warning(
                    "inbound from chat_id=%r dropped — "
                    "TELEGRAM_INBOUND_ALLOWED_CHAT_IDS not set; "
                    "only TELEGRAM_CHAT_ID=%r is authorised",
                    chat_id,
                    primary or "(not configured)",
                )
                return
        elif chat_id not in allowed:
            self._log.warning(
                "inbound message from unknown chat_id=%r — dropped", chat_id
            )
            return

        parts = text.split()
        command = parts[0].lower().split("@")[0]  # strip @botname suffix
        args = parts[1:]

        handlers = {
            "/status": self._cmd_status,
            "/pnl": self._cmd_pnl,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/positions": self._cmd_positions,
            "/perf": self._cmd_perf,
            "/gates": self._cmd_gates,
            "/mode": self._cmd_mode,
            "/report": self._cmd_report,
            "/ping": self._cmd_ping,
            "/help": self._cmd_help,
        }

        handler = handlers.get(command)
        if handler is None:
            reply = await self._cmd_help()
        elif command in ("/pnl", "/perf", "/mode"):
            reply = await handler(args)  # type: ignore[call-arg]
        else:
            reply = await handler()  # type: ignore[call-arg]

        await self._send(chat_id, reply)

    # ------------------------------------------------------------------
    # Command handlers — each returns the reply string
    # ------------------------------------------------------------------

    async def _cmd_status(self) -> str:
        from src.agents.batman import is_kill_switch_active, read_kill_switch_metadata

        ks = is_kill_switch_active()
        try:
            overview = await self._repo.get_overview()
            positions_count = overview.get("open_positions_count", "?")
            trades_today = overview.get("trades_today", "?")
            total_signals = overview.get("total_signals", "?")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_status repo error: {exc}")
            positions_count = trades_today = total_signals = "?"

        if ks:
            meta = read_kill_switch_metadata()
            ks_reason = meta.get("reason", "unknown")
            ks_agent = meta.get("agent", "?")
            ks_ts = meta.get("timestamp_utc", "?")
            ks_str = f"🔴 ACTIVE\n  reason: {ks_reason}\n  by: {ks_agent} @ {ks_ts}"
        else:
            ks_str = "🟢 clear"

        return (
            f"📊 Mekka Trading — Status\n"
            f"Mode    : {settings.mode_label}\n"
            f"Network : {settings.hyperliquid_network.upper()}\n"
            f"Kill sw : {ks_str}\n"
            f"Positions: {positions_count}\n"
            f"Trades today: {trades_today}\n"
            f"Total signals: {total_signals}"
        )

    async def _cmd_pnl(self, args: list[str] | None = None) -> str:
        limit = 7
        if args:
            try:
                limit = max(1, min(int(args[0]), 90))
            except (ValueError, IndexError):
                pass

        try:
            rows = await self._repo.list_recent_daily_pnl(limit=limit)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_pnl repo error: {exc}")
            return f"⚠️ Erro ao buscar PnL: {exc}"

        if not rows:
            return "📈 Nenhum PnL registrado ainda."

        lines = [f"📈 Últimos {len(rows)} dia(s) de PnL:"]
        for r in rows:
            date = getattr(r, "date", "?")
            pnl = getattr(r, "realized_pnl_usd", None)
            pnl_str = f"${pnl:+.2f}" if pnl is not None else "n/a"
            lines.append(f"  {date}: {pnl_str}")
        return "\n".join(lines)

    async def _cmd_pause(self) -> str:
        from src.agents.batman import engage_kill_switch

        try:
            engage_kill_switch("telegram_pause")
            self._log.warning("Kill switch engaged via Telegram /pause")
            return "🔴 Kill switch ENGAJADO via /pause. Use /resume para liberar."
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"_cmd_pause failed: {exc}")
            return f"⚠️ Erro ao engajar kill switch: {exc}"

    async def _cmd_resume(self) -> str:
        from src.agents.batman import release_kill_switch

        try:
            release_kill_switch()
            # [A3] Reset safety-net breakers so a residual streak from before
            # the halt doesn't immediately retrip the kill switch.
            try:
                self._fury.reset_breakers()
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"reset_breakers failed (non-fatal): {exc}")
            self._log.warning("Kill switch released via Telegram /resume")
            return "🟢 Kill switch LIBERADO via /resume. Breakers resetados."
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"_cmd_resume failed: {exc}")
            return f"⚠️ Erro ao liberar kill switch: {exc}"

    async def _cmd_positions(self) -> str:
        try:
            snapshot = await self._portfolio.run()
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_positions portfolio error: {exc}")
            return f"⚠️ Erro ao buscar posições: {exc}"

        positions = getattr(snapshot, "positions", [])
        if not positions:
            return "📭 Nenhuma posição aberta."

        lines = [f"📋 Posições abertas ({len(positions)}):"]
        for p in positions:
            symbol = getattr(p, "symbol", "?")
            side = getattr(p, "side", "?")
            size = getattr(p, "size", "?")
            entry = getattr(p, "entry_price", "?")
            pnl = getattr(p, "unrealized_pnl_usd", None)
            pnl_str = f"PnL ${pnl:+.2f}" if pnl is not None else ""
            lines.append(f"  {symbol} {side.upper()} sz={size} @{entry} {pnl_str}")
        return "\n".join(lines)

    async def _cmd_perf(self, args: list[str] | None = None) -> str:
        """Run Deadpool and return a compact performance summary."""
        window = 30
        if args:
            try:
                window = max(1, min(int(args[0]), 365))
            except (ValueError, IndexError):
                pass

        try:
            _Deadpool = Deadpool
            if _Deadpool is None:
                from src.agents.deadpool import Deadpool as _Deadpool
            from src.models.performance import PerformanceVerdict

            dp = _Deadpool(repo=self._repo)
            rpt = await dp.run(window_days=window)

            verdict_icon = {
                PerformanceVerdict.READY: "🟢",
                PerformanceVerdict.NOT_READY: "🔴",
                PerformanceVerdict.INSUFFICIENT_DATA: "⚠️",
            }.get(rpt.verdict, "?")

            win_str = f"{rpt.win_rate_pct:.1f}%" if rpt.win_rate_pct is not None else "n/a"
            wr_rate = (
                f"{rpt.wolverine_sl_endorse_rate_pct:.1f}%"
                if rpt.wolverine_sl_endorse_rate_pct is not None else "n/a"
            )
            act_rate = (
                f"{rpt.signal_actionable_rate_pct:.1f}%"
                if rpt.signal_actionable_rate_pct is not None else "n/a"
            )
            sharpe_str = f"{rpt.sharpe_estimate:.2f}" if rpt.sharpe_estimate is not None else "n/a"

            notes_str = ""
            if rpt.notes:
                notes_str = "\nNotes:\n" + "\n".join(f"  • {n}" for n in rpt.notes[:3])

            return (
                f"{verdict_icon} Deadpool — {window}d Report\n"
                f"Verdict : {rpt.verdict.value}\n"
                f"Days    : {rpt.days_with_data}/{window}\n"
                f"Trades  : {rpt.total_trades} (W:{rpt.wins} L:{rpt.losses})\n"
                f"Win rate: {win_str}\n"
                f"PnL     : ${rpt.total_pnl_usd:+.2f} (avg ${rpt.avg_daily_pnl_usd:+.2f}/d)\n"
                f"Drawdown: {rpt.max_drawdown_pct:.2f}%\n"
                f"Sharpe  : {sharpe_str}\n"
                f"WolvEndorse: {wr_rate}  (H2 needs ≥70%)\n"
                f"Actionable : {act_rate}{notes_str}"
            )

        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_perf error: {exc}")
            return f"⚠️ Erro ao executar Deadpool: {exc}"

    async def _cmd_gates(self) -> str:
        """Show H1–H6 mainnet gate status."""
        from src.agents.batman import is_kill_switch_active
        from src.models.performance import PerformanceVerdict

        # H4 is always auto-satisfied (032b delivered 2026-05-11)
        h4 = "✅ DONE"

        # H2 — auto-check via Deadpool
        h2 = "⏳ checking…"
        try:
            _Deadpool = Deadpool
            if _Deadpool is None:
                from src.agents.deadpool import Deadpool as _Deadpool
            dp = _Deadpool(repo=self._repo)
            rpt = await dp.run(window_days=30)
            if rpt.verdict == PerformanceVerdict.INSUFFICIENT_DATA:
                h2 = f"⚠️ Insufficient data ({rpt.days_with_data}d)"
            elif rpt.wolverine_sl_endorse_rate_pct is None:
                h2 = "⚠️ No Wolverine data yet"
            elif rpt.wolverine_sl_endorse_rate_pct >= 70.0:
                h2 = f"✅ {rpt.wolverine_sl_endorse_rate_pct:.1f}% ≥ 70%"
            else:
                h2 = f"❌ {rpt.wolverine_sl_endorse_rate_pct:.1f}% < 70%"
        except Exception as exc:  # noqa: BLE001
            h2 = f"⚠️ Error: {exc}"

        return (
            "🛡️ Mainnet Gates — H1 to H6\n"
            "\n"
            f"[H1] Testnet ≥1 month no incident\n"
            f"     ☐ Operator must verify (see INCIDENT-PLAYBOOK.md)\n"
            f"\n"
            f"[H2] Wolverine SL ENDORSE ≥70%\n"
            f"     {h2}\n"
            f"\n"
            f"[H3] Vision Critic stable ≥1 week\n"
            f"     ☐ Operator must verify (check VISION_CRITIC_ENABLED logs)\n"
            f"\n"
            f"[H4] Story 032b (TS audit shim)\n"
            f"     {h4}\n"
            f"\n"
            f"[H5] Dedicated mainnet wallet\n"
            f"     ☐ Operator must create & confirm\n"
            f"\n"
            f"[H6] Wallet funded via real transfer\n"
            f"     ☐ Operator must confirm\n"
            f"\n"
            f"Once H1–H6 satisfied → fill docs/MAINNET-AUTHORIZATION.md"
        )

    async def _cmd_mode(self, args: list[str]) -> str:
        """
        /mode          — mostra modo atual
        /mode <nome>   — muda para conservative | balanced | aggressive
        """
        from src.config.runtime_mode import (
            PRESETS,
            VALID_MODES,
            get_mode,
            set_mode,
        )

        if not args:
            # Show current mode
            current = get_mode()
            preset = PRESETS[current]
            p = preset
            assets = ", ".join(p["trading_assets"])
            return (
                f"📊 Modo atual: {p['label']}\n"
                f"{p['description']}\n\n"
                f"• Posição máx: {p['max_position_size_pct']*100:.1f}%\n"
                f"• Leverage máx: {p['max_leverage']}x\n"
                f"• Drawdown máx: {p['max_daily_drawdown_pct']*100:.0f}%\n"
                f"• Trades/dia: {p['max_trades_per_day']}\n"
                f"• Ativos: {assets}\n\n"
                f"Use /mode conservative|balanced|aggressive para mudar."
            )

        target = args[0].lower()
        if target not in VALID_MODES:
            return (
                f"❌ Modo '{target}' desconhecido.\n"
                f"Modos válidos: {', '.join(VALID_MODES)}"
            )

        try:
            preset = set_mode(target)
            p = preset
            assets = ", ".join(p["trading_assets"])
            return (
                f"✅ Modo alterado para {p['label']}\n"
                f"{p['description']}\n\n"
                f"• Posição máx: {p['max_position_size_pct']*100:.1f}%\n"
                f"• Leverage máx: {p['max_leverage']}x\n"
                f"• Drawdown máx: {p['max_daily_drawdown_pct']*100:.0f}%\n"
                f"• Trades/dia: {p['max_trades_per_day']}\n"
                f"• Ativos: {assets}\n\n"
                f"Entra em vigor no próximo ciclo."
            )
        except Exception as exc:
            return f"⚠️ Erro ao mudar modo: {exc}"

    async def _cmd_ping(self) -> str:
        """
        /ping — testa a conexão com o bot e retorna status do sistema.
        """
        from src.services.telegram_alerter import TelegramAlerter
        alerter = TelegramAlerter()
        ok = await alerter.ping(reason="teste manual via /ping")
        if ok:
            return "✅ Ping enviado! Bot está online e respondendo."
        return "⚠️ Bot não conseguiu confirmar envio (verifique TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)."

    async def _cmd_report(self) -> str:
        """
        /report — dispara o relatório diário on-demand (força envio mesmo se já enviado hoje).
        """
        try:
            from src.dashboard.daily_reporter import DailyReporter
            reporter = DailyReporter(repo=self._repo)
            result = await reporter.send_daily_report(force=True)
            await reporter.close()

            if result.get("skipped"):
                reason = result.get("reason", "sem targets configurados")
                return f"⚠️ Relatório não enviado: {reason}"

            parts = []
            if result.get("sent_slack"):
                parts.append("Slack ✅")
            if result.get("sent_telegram"):
                parts.append("Telegram ✅")
            if not parts:
                return "⚠️ Nenhum webhook respondeu com sucesso."

            pnl = result.get("today_pnl_usd")
            trades = result.get("today_trades")
            pnl_str = f"  PnL hoje: ${pnl:+.2f}" if pnl is not None else ""
            trades_str = f"  Trades: {trades}" if trades is not None else ""
            return (
                f"📊 Relatório enviado para {', '.join(parts)}\n"
                f"Data: {result.get('date', '?')}"
                + (f"\n{pnl_str}" if pnl_str else "")
                + (f"\n{trades_str}" if trades_str else "")
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_report error: {exc}")
            return f"⚠️ Erro ao enviar relatório: {exc}"

    async def _cmd_help(self) -> str:
        return _HELP_TEXT

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _send(self, chat_id: str, text: str) -> bool:
        """Send a reply to chat_id. Returns True on success, False on error."""
        import aiohttp  # noqa: WPS433

        url = _TG_API.format(token=settings.telegram_bot_token, method="sendMessage")
        timeout = aiohttp.ClientTimeout(total=settings.telegram_alert_timeout_seconds)
        body = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=body) as resp:
                    return resp.status == 200
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_send failed (suppressed): {exc}")
            return False


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

async def _main() -> None:  # pragma: no cover
    from src.agents.nick_fury import NickFury
    from src.agents.portfolio_manager import PortfolioManager

    await MekkaRepository.initialize()
    poller = TelegramInboundPoller(
        nick_fury=NickFury(),
        portfolio=PortfolioManager(),
    )
    await poller.run_forever()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())

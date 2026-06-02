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
    "/mode [X]   — mostra ou muda modo de trading (conservative/balanced/aggressive)\n"
    "/opmode [X] — modo de operação (só TRADES): manual (você aprova) ou automatic\n"
    "/manual     — atalho: você aprova cada trade\n"
    "/auto       — atalho: trades executam sozinhos (gates de risco seguem ativos)\n"
    "/report     — envia relatório diário agora (Slack + Telegram)\n"
    "/ping       — testa conexão e exibe status do bot\n"
    "/risk       — painel de risco ao vivo (exposure, PnL, cooldowns, blacklist, ATR)\n"
    "/leaderboard [N] — top N símbolos por PnL (padrão: 5)\n"
    "/stats [N]  — estatísticas globais N dias (padrão: 30)\n"
    "/unblacklist [SYMBOL] — remove símbolo da blacklist manual\n"
    "/dryrun [on|off] — ativa/desativa modo dry-run (sem execução)\n"
    "/weekly     — envia relatório semanal agora (Deadpool 7 dias)\n"
    "/equity     — breakdown de equity (inicial + realizado + não realizado)\n"
    "/balance    — saldo live da exchange (Hyperliquid clearinghouse)\n"
    "—— Sistema ——\n"
    "/sistema    — status do runtime (ligado/desligado, uptime, ciclos)\n"
    "/ligar      — liga o sistema (inicia o runtime de trading)\n"
    "/desligar   — desliga o sistema (para o runtime; sem gasto de tokens)\n"
    "/reboot     — reinicia o sistema (desliga e liga)\n"
    "—— Melhorias ——\n"
    "/aprendizados [agente] — o que os agentes aprenderam (diário de memória)\n"
    "/melhorias  — lista propostas pendentes do conselho (Mekka)\n"
    "/aprovar <id>  — aprova proposta (envia ao dev) — sincroniza com o dashboard\n"
    "/reprovar <id> — reprova proposta — sincroniza com o dashboard\n"
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
        nick_fury: "NickFury | None" = None,
        portfolio: "PortfolioManager | None" = None,
        controller: object | None = None,
        repo: type[MekkaRepository] = MekkaRepository,
    ) -> None:
        # When the poller lives in the always-on control plane (so it can
        # turn the runtime on/off), fury/portfolio start as None and are
        # injected by the RuntimeController via set_runtime/clear_runtime.
        self._fury = nick_fury
        self._portfolio = portfolio
        self._controller = controller
        self._repo = repo
        self._log = logger.bind(agent="TelegramInbound")

    # -- runtime wiring (control-plane mode) ----------------------------
    def set_runtime(self, nick_fury: object, portfolio: object) -> None:
        """Called by RuntimeController when the runtime starts."""
        self._fury = nick_fury
        self._portfolio = portfolio

    def clear_runtime(self) -> None:
        """Called by RuntimeController when the runtime stops."""
        self._fury = None
        self._portfolio = None

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
            "allowed_updates": ["message", "callback_query"],  # Story 074: include inline button callbacks
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
        Handles both text messages AND callback_query (Story 074 inline buttons).
        """
        # ── Story 074: callback_query (inline keyboard button press) ──────
        callback_query = update.get("callback_query")
        if callback_query:
            await self._handle_callback_query(callback_query)
            return

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
            "/opmode": self._cmd_opmode,       # Operation Mode (manual/automatic)
            "/manual": self._cmd_opmode_manual,
            "/auto": self._cmd_opmode_auto,
            "/aprendizados": self._cmd_learnings,  # diário de aprendizado por agente
            "/report": self._cmd_report,
            "/ping": self._cmd_ping,
            "/risk": self._cmd_risk,
            "/leaderboard": self._cmd_leaderboard,
            "/stats": self._cmd_stats,
            "/unblacklist": self._cmd_unblacklist,
            "/dryrun": self._cmd_dryrun,
            "/weekly": self._cmd_weekly,       # Story 101
            "/equity": self._cmd_equity,       # Story 103
            "/balance": self._cmd_balance,     # Story 108
            # System control (RuntimeController) — control plane
            "/ligar": self._cmd_system_start,
            "/desligar": self._cmd_system_stop,
            "/reboot": self._cmd_system_reboot,
            "/sistema": self._cmd_system_status,
            # Improvement council (Mekka) — synced with the dashboard
            "/melhorias": self._cmd_improvements,
            "/aprovar": self._cmd_improve_accept,
            "/reprovar": self._cmd_improve_reject,
            "/help": self._cmd_help,
        }

        handler = handlers.get(command)
        if handler is None:
            reply = await self._cmd_help()
        elif command in ("/pnl", "/perf", "/mode", "/opmode", "/aprendizados", "/leaderboard", "/stats", "/unblacklist", "/dryrun", "/aprovar", "/reprovar"):
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

        try:
            from src.config.operation_mode import get_operation_mode
            _op = get_operation_mode()
            op_str = "🤖 AUTOMÁTICO" if _op == "automatic" else "🙋 MANUAL"
        except Exception:  # noqa: BLE001
            op_str = "?"

        return (
            f"📊 Mekka Trading — Status\n"
            f"Mode    : {settings.mode_label}\n"
            f"Operação: {op_str}\n"
            f"Network : {settings.hyperliquid_network.upper()}\n"
            f"Kill sw : {ks_str}\n"
            f"Positions: {positions_count}\n"
            f"Trades today: {trades_today}\n"
            f"Total signals: {total_signals}"
        )

    # -- system control (RuntimeController) -----------------------------
    async def _cmd_system_status(self) -> str:
        c = self._controller
        if c is None:
            return "⚠️ Controle de sistema indisponível neste processo."
        try:
            st = c.status()
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Erro ao ler status: {exc}"
        emoji = {"running": "🟢", "stopped": "🔴", "starting": "🟡", "stopping": "🟡"}.get(st.get("state"), "⚪")
        return (
            f"{emoji} Sistema: {st.get('state','?').upper()}\n"
            f"Uptime: {st.get('uptime_seconds',0)}s · Ciclos: {st.get('cycles',0)}\n"
            f"Modo: {st.get('mode','?')} · {'PAPER' if st.get('paper_trading') else 'LIVE'}\n"
            f"Comandos: /ligar /desligar /reboot"
        )

    async def _cmd_system_start(self) -> str:
        c = self._controller
        if c is None:
            return "⚠️ Controle de sistema indisponível."
        try:
            await c.start()
            return "🟢 Sistema LIGADO — o runtime de trading está rodando."
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Falha ao ligar: {exc}"

    async def _cmd_system_stop(self) -> str:
        c = self._controller
        if c is None:
            return "⚠️ Controle de sistema indisponível."
        try:
            await c.stop()
            return "🔴 Sistema DESLIGADO — runtime parado, sem novas chamadas de LLM (sem gasto de tokens)."
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Falha ao desligar: {exc}"

    async def _cmd_system_reboot(self) -> str:
        c = self._controller
        if c is None:
            return "⚠️ Controle de sistema indisponível."
        try:
            await c.reboot()
            return "🔄 Sistema REINICIADO — runtime parado e ligado novamente."
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Falha ao reiniciar: {exc}"

    # -- improvement council (Mekka) — synced with dashboard ------------
    async def _cmd_improvements(self) -> str:
        try:
            from src.agents.mekka import Mekka
            report = await Mekka().run(period_days=7)
            recs = getattr(report, "recommendations", []) or []
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Erro ao consultar o conselho: {exc}"
        pend = [r for r in recs if getattr(r, "status", "pending") == "pending"]
        if not pend:
            return "🛠️ Nenhuma proposta pendente no conselho de melhorias."
        lines = ["🛠️ Propostas pendentes (use /aprovar <id> ou /reprovar <id>):"]
        for r in pend[:8]:
            rid = getattr(r, "id", "?")
            title = getattr(r, "title", "(sem título)")
            area = getattr(r, "area", "")
            lines.append(f"• `{rid}` — {title} [{area}]")
        return "\n".join(lines)

    async def _cmd_improve_accept(self, args: list[str] | None = None) -> str:
        return await self._improve_decide(args, "accepted")

    async def _cmd_improve_reject(self, args: list[str] | None = None) -> str:
        return await self._improve_decide(args, "rejected")

    async def _improve_decide(self, args: list[str] | None, status: str) -> str:
        if not args:
            return "Uso: /aprovar <id>  ou  /reprovar <id> (veja os ids em /melhorias)."
        rec_id = args[0]
        try:
            from src.agents.mekka import Mekka
            mekka = Mekka()
            ok = mekka.record_decision(rec_id, status)
            # On accept, enqueue the dev brief (best-effort) — try to find the rec.
            if ok and status == "accepted":
                try:
                    report = await mekka.run(period_days=7)
                    for r in getattr(report, "recommendations", []) or []:
                        rd = r.to_dict() if hasattr(r, "to_dict") else dict(r)
                        if rec_id in (rd.get("id"), rd.get("rec_id")):
                            from src.services import improvement_queue
                            improvement_queue.enqueue_brief(rd)
                            break
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Erro ao registrar decisão: {exc}"
        if not ok:
            return f"⚠️ Não foi possível registrar `{rec_id}` (id inválido?)."
        verb = "aprovada ✅ (enviada ao dev)" if status == "accepted" else "reprovada ❌"
        return f"Proposta `{rec_id}` {verb}. Sincronizado com a Central de Melhorias do dashboard."

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
                if self._fury is not None:
                    self._fury.reset_breakers()
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"reset_breakers failed (non-fatal): {exc}")
            self._log.warning("Kill switch released via Telegram /resume")
            return "🟢 Kill switch LIBERADO via /resume. Breakers resetados."
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"_cmd_resume failed: {exc}")
            return f"⚠️ Erro ao liberar kill switch: {exc}"

    async def _cmd_positions(self) -> str:
        if self._portfolio is None:
            return "🔴 Sistema desligado — ligue com /ligar para consultar posições ao vivo."
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

    @staticmethod
    def _opmode_status_text(mode: str) -> str:
        """Renderiza o status do modo de operação."""
        if mode == "automatic":
            return (
                "🤖 Modo de operação: AUTOMÁTICO\n"
                "O sistema executa TRADES sozinho (gates de risco seguem ativos).\n\n"
                "• Trades: auto-executam após os gates do Batman\n"
                "• Melhorias: SEMPRE exigem sua aprovação (não muda com o modo)\n"
                "• Gates de risco/kill-switch/double-gate: SEGUEM ATIVOS\n\n"
                "Use /manual para aprovar os trades você mesmo."
            )
        return (
            "🙋 Modo de operação: MANUAL\n"
            "Você aprova cada TRADE via Telegram.\n\n"
            "• Trades: pedem sua confirmação antes do IronMan executar\n"
            "• Melhorias: sempre na fila aguardando sua aprovação\n\n"
            "Use /auto para os trades executarem sozinhos."
        )

    async def _cmd_opmode(self, args: list[str]) -> str:
        """
        /opmode            — mostra o modo de operação atual
        /opmode manual     — você aprova trades e melhorias
        /opmode automatic  — o sistema aprova sozinho
        """
        from src.config.operation_mode import (
            VALID_OPERATION_MODES,
            get_operation_mode,
            set_operation_mode,
        )

        if not args:
            return self._opmode_status_text(get_operation_mode())

        target = args[0].lower()
        if target in ("auto",):
            target = "automatic"
        if target not in VALID_OPERATION_MODES:
            return (
                f"❌ Modo de operação '{target}' desconhecido.\n"
                f"Válidos: {', '.join(VALID_OPERATION_MODES)} (ou /manual, /auto)"
            )
        try:
            new_mode = set_operation_mode(target)
            return "✅ " + self._opmode_status_text(new_mode)
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Erro ao mudar modo de operação: {exc}"

    async def _cmd_opmode_manual(self) -> str:
        """/manual — atalho para o modo de operação manual."""
        return await self._cmd_opmode(["manual"])

    async def _cmd_opmode_auto(self) -> str:
        """/auto — atalho para o modo de operação automático."""
        return await self._cmd_opmode(["automatic"])

    async def _cmd_learnings(self, args: list[str]) -> str:
        """
        /aprendizados            — resumo: quantas lições cada agente tem
        /aprendizados <agente>   — as lições mais relevantes do agente
        """
        from src.services.agent_learning_journal import recall, stats

        if args:
            agent = args[0]
            lessons = recall(agent, limit=8)
            if not lessons:
                return f"🧠 {agent} ainda não registrou aprendizados."
            lines = [f"🧠 Aprendizados de {agent} (top {len(lessons)}):"]
            for ls in lessons:
                conf = f"{float(ls.get('confidence', 0)) * 100:.0f}%"
                reinf = int(ls.get("reinforced_count", 1))
                rtag = f" ×{reinf}" if reinf > 1 else ""
                lines.append(f"• [{conf}{rtag}] {ls.get('lesson', '')}")
            return "\n".join(lines)

        data = stats()
        by_agent = (data or {}).get("by_agent", {})
        if not by_agent:
            return (
                "🧠 Nenhum aprendizado registrado ainda.\n"
                "Os agentes vão preenchendo conforme operam (Mentor, IronMan...).\n"
                "Use /aprendizados <agente> para ver os de um agente."
            )
        lines = ["🧠 Aprendizados por agente:"]
        for ag, info in list(by_agent.items())[:15]:
            lines.append(f"• {ag}: {info.get('lessons', 0)} lição(ões)")
        lines.append("\nUse /aprendizados <agente> para detalhes.")
        return "\n".join(lines)

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

    async def _cmd_weekly(self) -> str:
        """
        /weekly — dispara o relatório semanal Deadpool on-demand. Story 101.
        """
        try:
            from src.dashboard.daily_reporter import DailyReporter  # noqa: WPS433
            reporter = DailyReporter(repo=self._repo)
            result = await reporter.send_weekly_report(force=True)
            await reporter.close()

            if result.get("skipped"):
                return f"⚠️ Relatório semanal não enviado: {result.get('reason', 'sem targets')}"

            parts = []
            if result.get("sent_telegram"):
                parts.append("Telegram ✅")
            if result.get("sent_slack"):
                parts.append("Slack ✅")
            if not parts:
                return "⚠️ Nenhum webhook respondeu com sucesso."

            pnl_w = result.get("week_pnl_usd")
            trades_w = result.get("week_trades")
            pnl_str = f"\n  PnL semana: ${pnl_w:+.2f}" if pnl_w is not None else ""
            trades_str = f"\n  Trades: {trades_w}" if trades_w is not None else ""
            return (
                f"📅 Relatório semanal enviado para {', '.join(parts)}"
                f"\nSemana: {result.get('week', '?')}"
                f"{pnl_str}{trades_str}"
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_weekly error: {exc}")
            return f"⚠️ Erro ao enviar relatório semanal: {exc}"

    async def _cmd_equity(self) -> str:
        """
        /equity — breakdown de equity em tempo real. Story 103.
        Mostra: capital inicial + PnL realizado + PnL não realizado + equity total.
        """
        try:
            from src.dashboard.positions_provider import get_paper_equity_summary  # noqa: WPS433
            summary = await get_paper_equity_summary()
            initial = summary.get("initial_capital", 0.0)
            realized = summary.get("realized_pnl_usd", 0.0)
            unrealized = summary.get("unrealized_pnl_usd", 0.0)
            equity = summary.get("equity_usd", 0.0)
            r_emoji = "🟢" if realized >= 0 else "🔴"
            u_emoji = "🟢" if unrealized >= 0 else "🔴"
            e_emoji = "🟢" if equity >= initial else "🔴"
            return (
                f"💰 *Equity Breakdown*\n"
                f"\n"
                f"Capital inicial : ${initial:,.2f}\n"
                f"{r_emoji} PnL realizado  : ${realized:+,.2f}\n"
                f"{u_emoji} PnL n. realiz. : ${unrealized:+,.2f}\n"
                f"──────────────────\n"
                f"{e_emoji} *Equity total  : ${equity:,.2f}*\n"
                f"\n"
                f"Variação        : {((equity - initial) / max(initial, 1)) * 100:+.2f}%"
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_equity error: {exc}")
            return f"⚠️ Erro ao calcular equity: {exc}"

    async def _cmd_balance(self) -> str:
        """
        /balance — saldo live do Hyperliquid clearinghouse. Story 108.

        Chama a API REST do Hyperliquid info endpoint para obter o estado
        da conta: accountValue (equity), totalMarginUsed, withdrawable.
        Funciona apenas com ACTIVE_EXCHANGE=hyperliquid.
        """
        try:
            import aiohttp  # noqa: WPS433
            from src.config.settings import settings as _s  # noqa: WPS433

            _base = _s.hyperliquid_base_url  # e.g. https://api.hyperliquid-testnet.xyz
            _url = f"{_base}/info"
            _wallet = _s.hyperliquid_wallet_address

            _payload = {"type": "clearinghouseState", "user": _wallet}
            async with aiohttp.ClientSession() as _sess:
                async with _sess.post(
                    _url,
                    json=_payload,
                    timeout=aiohttp.ClientTimeout(total=8.0),
                ) as _resp:
                    if _resp.status != 200:
                        return f"⚠️ Hyperliquid API retornou HTTP {_resp.status}"
                    _data = await _resp.json()

            # Parse marginSummary
            _ms = _data.get("marginSummary") or {}
            _acv = float(_ms.get("accountValue") or 0.0)
            _tmu = float(_ms.get("totalMarginUsed") or 0.0)
            _wtd = float(_ms.get("withdrawable") or _data.get("withdrawable") or 0.0)
            _free = _acv - _tmu

            _net = _s.hyperliquid_network.upper()
            _eq_emoji = "🟢" if _acv > 0 else "⚪"
            _free_emoji = "🟢" if _free >= 0 else "🔴"

            return (
                f"🏦 *Hyperliquid Balance* ({_net})\n"
                f"\n"
                f"{_eq_emoji} Account value  : ${_acv:,.2f}\n"
                f"   Margin usado  : ${_tmu:,.2f}\n"
                f"{_free_emoji} Margem livre   : ${_free:,.2f}\n"
                f"   Withdrawable  : ${_wtd:,.2f}\n"
                f"\n"
                f"Carteira: `{_wallet[:8]}...{_wallet[-4:]}`"
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_balance error: {exc}")
            return f"⚠️ Erro ao consultar balance: {exc}"

    async def _cmd_stats(self, args: list[str] | None = None) -> str:
        """
        /stats [N] — estatísticas globais nos últimos N dias (padrão 30). Story 084.
        """
        window = 30
        if args:
            try:
                window = max(1, min(int(args[0]), 365))
            except (ValueError, IndexError):
                pass
        try:
            s = await self._repo.get_pnl_summary(window_days=window)
            w = s["window"]
            at = s["all_time"]
            eq = await self._repo.get_today_peak_equity()
            wr_w = f"{w['win_rate']*100:.1f}%" if w.get("win_rate") is not None else "n/a"
            wr_at = f"{at['win_rate']*100:.1f}%" if at.get("win_rate") is not None else "n/a"
            sh = s.get("sharpe_estimate")
            sh_str = f"{sh:.2f}" if sh is not None else "n/a"
            pnl_icon = "🟢" if w["pnl_usd"] >= 0 else "🔴"
            return (
                f"📊 Stats — últimos {window}d\n"
                f"PnL     : {pnl_icon} ${w['pnl_usd']:+.2f}\n"
                f"Trades  : {w['trades']} (↑{w['wins']} ↓{w['losses']})\n"
                f"Win rate: {wr_w}\n"
                f"Drawdown: {w['max_drawdown_pct']*100:.2f}%\n"
                f"Sharpe  : {sh_str}\n"
                f"Equity  : ${eq:,.2f}\n\n"
                f"All-time: ${at['pnl_usd']:+.2f} | {at['trades']} trades | WR={wr_at}"
            )
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Erro ao calcular stats: {exc}"

    async def _cmd_unblacklist(self, args: list[str] | None = None) -> str:
        """
        /unblacklist [SYMBOL] — remove um símbolo da auto-blacklist. Story 085.
        Se nenhum símbolo for passado, lista os símbolos em blacklist atualmente.
        """
        import json as _json  # noqa: WPS433
        from datetime import datetime, timezone  # noqa: WPS433
        from pathlib import Path  # noqa: WPS433

        data_dir = Path("data")
        now_utc = datetime.now(timezone.utc)

        if not args:
            # List active blacklists
            active = []
            if data_dir.exists():
                for bf in data_dir.glob(".blacklist_*.json"):
                    try:
                        bl = _json.loads(bf.read_text())
                        exp_str = bl.get("expires", "")
                        if exp_str:
                            exp_dt = datetime.fromisoformat(exp_str)
                            if exp_dt.tzinfo is None:
                                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            if now_utc < exp_dt:
                                rem_h = round((exp_dt - now_utc).total_seconds() / 3600, 1)
                                active.append(f"  🚫 {bl.get('symbol','?')} — expira em {rem_h}h")
                    except Exception:  # noqa: BLE001
                        pass
            if not active:
                return "✅ Nenhum símbolo em blacklist ativa."
            return "Símbolos em blacklist:\n" + "\n".join(active) + "\n\nUse /unblacklist SYMBOL para remover."

        symbol = args[0].upper().strip()
        bl_file = data_dir / f".blacklist_{symbol}.json"
        if not bl_file.exists():
            return f"ℹ️ {symbol} não está em blacklist (ou já expirou)."
        try:
            bl_file.unlink()
            self._log.warning("[Telegram] /unblacklist: %s removido da blacklist manualmente", symbol)
            return f"✅ {symbol} removido da blacklist. Próximo sinal será avaliado normalmente."
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Erro ao remover {symbol} da blacklist: {exc}"

    async def _cmd_dryrun(self, args: list[str] | None = None) -> str:
        """
        /dryrun [on|off] — ativa ou desativa o modo dry-run em runtime. Story 091.
        Dry-run = pipeline completo sem execução real de trades.
        """
        try:
            from src.config.runtime_mode import get_params, set_runtime_flag  # noqa: WPS433
        except ImportError:
            # Fallback: use settings directly via os.environ sentinel
            pass

        try:
            from src.config.settings import settings as _s  # noqa: WPS433
            import os  # noqa: WPS433
            if not args:
                current = os.environ.get("MEKKA_DRY_RUN", "0") == "1" or getattr(_s, "dry_run_mode", False)
                state = "ON 🚧" if current else "OFF ✅"
                return (
                    f"🔬 Dry-Run Mode: {state}\n"
                    "Em dry-run, sinais são gerados e validados mas NÃO executados.\n"
                    "Use /dryrun on|off para alternar."
                )
            target = args[0].lower()
            if target == "on":
                os.environ["MEKKA_DRY_RUN"] = "1"
                self._log.warning("[Telegram] Dry-run mode ENABLED via /dryrun on")
                return "🚧 Dry-Run ATIVADO — trades serão simulados mas não executados."
            elif target == "off":
                os.environ.pop("MEKKA_DRY_RUN", None)
                self._log.warning("[Telegram] Dry-run mode DISABLED via /dryrun off")
                return "✅ Dry-Run DESATIVADO — trades serão executados normalmente."
            else:
                return "❌ Use /dryrun on ou /dryrun off."
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Erro no dry-run toggle: {exc}"

    async def _cmd_leaderboard(self, args: list[str] | None = None) -> str:
        """
        /leaderboard [N] — top N símbolos por PnL total (padrão 5, máx 15).
        Story 081.
        """
        limit = 5
        days = 90
        if args:
            try:
                limit = max(1, min(int(args[0]), 15))
            except (ValueError, IndexError):
                pass
            if len(args) > 1:
                try:
                    days = max(7, min(int(args[1]), 365))
                except (ValueError, IndexError):
                    pass

        try:
            items = await self._repo.list_symbol_stats(lookback_days=days)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_cmd_leaderboard error: {exc}")
            return f"⚠️ Erro ao buscar leaderboard: {exc}"

        if not items:
            return f"🏆 Leaderboard ({days}d): nenhum trade registrado ainda."

        top = items[:limit]
        lines = [f"🏆 Top {len(top)} Símbolos — últimos {days}d\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, item in enumerate(top):
            icon = medals[i] if i < 3 else f"  {i+1}."
            wr = f"{item['win_rate']*100:.1f}%" if item.get("win_rate") is not None else "n/a"
            pnl = item.get("total_pnl_usd", 0)
            sign = "+" if pnl >= 0 else ""
            sharpe = f" Sharpe={item['sharpe']:.2f}" if item.get("sharpe") is not None else ""
            lines.append(
                f"{icon} {item['symbol']}: {sign}${pnl:.2f} "
                f"({item['trades']} trades, WR={wr}{sharpe})"
            )

        # Summary footer
        total_pnl = sum(x.get("total_pnl_usd", 0) for x in items)
        total_trades = sum(x.get("trades", 0) for x in items)
        sign_t = "+" if total_pnl >= 0 else ""
        lines.append(f"\nTotal geral: {sign_t}${total_pnl:.2f} em {total_trades} trades ({len(items)} símbolos)")
        return "\n".join(lines)

    async def _cmd_risk(self) -> str:
        """
        /risk — painel de risco ao vivo: exposure, PnL diário, cooldowns,
        blacklist e ATR por ativo. Story 078.
        """
        import json as _json  # noqa: WPS433
        from datetime import datetime, timezone, timedelta  # noqa: WPS433
        from pathlib import Path  # noqa: WPS433

        now_utc = datetime.now(timezone.utc)
        lines: list[str] = ["🛡️ Mekka — Painel de Risco\n"]

        # ── Exposure ──────────────────────────────────────────────────
        try:
            _positions = await self._repo.list_paper_filled_trades(limit=500)
            from collections import defaultdict  # noqa: WPS433
            _lq: dict = defaultdict(float)
            _sq: dict = defaultdict(float)
            _ln: dict = defaultdict(float)
            _sn: dict = defaultdict(float)
            for t in _positions:
                sym = (t.symbol or "").upper()
                qty = float(t.quantity or 0)
                price = float(t.avg_price or 0)
                if (t.side or "long").lower() == "long":
                    _lq[sym] += qty; _ln[sym] += qty * price
                else:
                    _sq[sym] += qty; _sn[sym] += qty * price
            _notional = 0.0
            for sym in set(_lq) | set(_sq):
                net = _lq[sym] - _sq[sym]
                if net > 1e-8:
                    _notional += _ln[sym]
                elif net < -1e-8:
                    _notional += _sn[sym]
            _equity = await self._repo.get_today_peak_equity()
            _cap = _equity * settings.max_portfolio_exposure_pct
            _used_pct = round(_notional / _cap * 100, 1) if _cap > 0 else 0.0
            _icon = "🟢" if _used_pct < 60 else ("🟡" if _used_pct < 85 else "🔴")
            lines.append(
                f"📊 Exposure: {_icon} ${_notional:,.0f} / ${_cap:,.0f} "
                f"({_used_pct}% de {settings.max_portfolio_exposure_pct*100:.0f}% equity)"
            )
        except Exception as _e:  # noqa: BLE001
            lines.append(f"📊 Exposure: ⚠️ erro ({_e})")

        # ── Daily PnL ─────────────────────────────────────────────────
        try:
            _pnl = await self._repo.get_today_pnl_usd()
            _eq = _equity if "_equity" in dir() else await self._repo.get_today_peak_equity()
            _pnl_pct = round(_pnl / _eq * 100, 2) if _eq > 0 else 0.0
            _kill = settings.max_daily_drawdown_pct * 100
            _target = settings.daily_profit_target_pct * 100
            _pnl_icon = "🟢" if _pnl >= 0 else ("🟡" if _pnl_pct > -_kill / 2 else "🔴")
            lines.append(
                f"💰 PnL hoje: {_pnl_icon} ${_pnl:+.2f} ({_pnl_pct:+.2f}%) "
                f"| target +{_target:.0f}% | kill -{_kill:.0f}%"
            )
        except Exception as _e:  # noqa: BLE001
            lines.append(f"💰 PnL hoje: ⚠️ erro ({_e})")

        # ── Cooldowns ─────────────────────────────────────────────────
        cooldown_lines: list[str] = []
        if settings.reentry_cooldown_minutes > 0:
            try:
                for _sym in settings.trading_assets:
                    _sl_time = await self._repo.get_last_sl_close_time(
                        symbol=_sym, lookback_minutes=settings.reentry_cooldown_minutes
                    )
                    if _sl_time is not None:
                        _ts = _sl_time if _sl_time.tzinfo else _sl_time.replace(tzinfo=timezone.utc)
                        _elapsed = (now_utc - _ts).total_seconds() / 60
                        _remaining = max(0.0, settings.reentry_cooldown_minutes - _elapsed)
                        cooldown_lines.append(f"  ⏳ {_sym}: {_remaining:.0f}min restantes")
            except Exception:  # noqa: BLE001
                pass
        if cooldown_lines:
            lines.append("🔒 Cooldowns:\n" + "\n".join(cooldown_lines))
        else:
            lines.append("🔒 Cooldowns: nenhum")

        # ── Blacklist ─────────────────────────────────────────────────
        bl_lines: list[str] = []
        try:
            _data_dir = Path("data")
            if _data_dir.exists():
                for _bl_file in _data_dir.glob(".blacklist_*.json"):
                    try:
                        _bl = _json.loads(_bl_file.read_text())
                        _exp_str = _bl.get("expires", "")
                        if _exp_str:
                            _exp_dt = datetime.fromisoformat(_exp_str)
                            if _exp_dt.tzinfo is None:
                                _exp_dt = _exp_dt.replace(tzinfo=timezone.utc)
                            if now_utc < _exp_dt:
                                _rem_h = round((_exp_dt - now_utc).total_seconds() / 3600, 1)
                                _hits = _bl.get("consecutive_sl_hits", 0)
                                bl_lines.append(
                                    f"  🚫 {_bl.get('symbol','?')}: "
                                    f"{_hits}× SL, expira em {_rem_h}h"
                                )
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
        if bl_lines:
            lines.append("🚫 Blacklist:\n" + "\n".join(bl_lines))
        else:
            lines.append("🚫 Blacklist: nenhum símbolo banido")

        # ── ATR ───────────────────────────────────────────────────────
        if settings.atr_sizing_enabled:
            try:
                from src.analytics.atr import compute_atr_pct as _atr_fn  # noqa: WPS433
                atr_parts: list[str] = []
                for _sym in settings.trading_assets:
                    try:
                        _atr_v = await _atr_fn(_sym, lookback=settings.atr_lookback_candles)
                        _atr_s = f"{_atr_v:.2f}%" if _atr_v is not None else "n/a"
                        atr_parts.append(f"{_sym}={_atr_s}")
                    except Exception:  # noqa: BLE001
                        atr_parts.append(f"{_sym}=err")
                if atr_parts:
                    lines.append("📐 ATR: " + "  ".join(atr_parts))
            except Exception:  # noqa: BLE001
                pass

        lines.append(f"\n🕒 {now_utc.strftime('%H:%M:%S UTC')}")
        return "\n".join(lines)

    async def _cmd_help(self) -> str:
        return _HELP_TEXT

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _handle_callback_query(self, callback_query: dict) -> None:
        """
        Story 074 / Story 127 — Handle inline keyboard button presses (trade approval).

        Routes to one of two paths based on callback_data prefix:

        • Classic (Story 074): "approve:<trade_id>" | "reject:<trade_id>"
          → resolves asyncio.Event via trade_approval.resolve()

        • LangGraph (Story 127): "lg_approve:<thread_id>:<trade_id>" | "lg_reject:..."
          → resumes LangGraph graph via graph.ainvoke(Command(resume=...))
          → cleans up interrupt_registry when cycle completes

        Always answers the callback query to dismiss the Telegram loading spinner.
        """
        import aiohttp  # noqa: WPS433

        cq_id = callback_query.get("id", "")
        cq_from = callback_query.get("from") or {}
        cq_chat_id = str((callback_query.get("message") or {}).get("chat", {}).get("id", ""))
        data: str = callback_query.get("data", "")

        # Security: verify sender is in allowlist
        sender_id = str(cq_from.get("id", ""))
        allowed = settings.telegram_inbound_allowed_chat_ids
        if not allowed:
            allowed = {settings.telegram_chat_id}
        if sender_id not in allowed and cq_chat_id not in allowed:
            self._log.warning("[TradeApproval] callback from unknown sender=%s — dropped", sender_id)
            return

        # Answer the callback query (removes the spinner)
        try:
            url_answer = _TG_API.format(token=settings.telegram_bot_token, method="answerCallbackQuery")
            async with aiohttp.ClientSession() as session:
                await session.post(url_answer, json={"callback_query_id": cq_id, "text": "✅ Recebido"})
        except Exception:  # noqa: BLE001
            pass

        if not data or ":" not in data:
            return

        # ── Story 127 — LangGraph interrupt/resume path ──────────────────
        if data.startswith("lg_approve:") or data.startswith("lg_reject:"):
            await self._handle_lg_callback(data)
            return

        # ── Improvement council inline buttons ───────────────────────────
        # callback_data: "improve_approve:<rec_id>" | "improve_reject:<rec_id>"
        if data.startswith("improve_approve:") or data.startswith("improve_reject:"):
            await self._handle_improvement_callback(data, cq_chat_id)
            return

        # ── Story 074 — Classic asyncio.Event path ───────────────────────
        action_str, trade_id = data.split(":", 1)
        approved = action_str.strip().lower() == "approve"

        try:
            from src.services.trade_approval import resolve as _resolve  # noqa: WPS433
            resolved = _resolve(trade_id, approved)
            if not resolved:
                self._log.debug("[TradeApproval] trade_id %s not found (expired?)", trade_id)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("[TradeApproval] resolve error: %s", exc)

    async def _handle_improvement_callback(self, data: str, chat_id: str) -> None:
        """Handle inline keyboard for improvement-council proposals.

        callback_data format:
          "improve_approve:<rec_id>" → marca como aceita + enfileira brief
          "improve_reject:<rec_id>"  → marca como rejeitada

        Reaproveita a mesma lógica de _improve_decide para manter UI consistente
        com os comandos /aprovar e /reprovar.
        """
        parts = data.split(":", 1)
        if len(parts) != 2:
            return
        action_prefix, rec_id = parts
        status = "accepted" if action_prefix == "improve_approve" else "rejected"
        # Reusa o helper de decisão — já lida com erros e enqueue do brief.
        reply = await self._improve_decide([rec_id], status)
        # Resposta concisa ao operador no chat onde ele clicou.
        try:
            await self._send(chat_id, reply)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("[ImproveCallback] send reply failed: %s", exc)

    async def _handle_lg_callback(self, data: str) -> None:
        """
        Story 127 — Resume a LangGraph graph that was paused via interrupt().

        callback_data format: "lg_approve:<thread_id>:<trade_id>"
                           or "lg_reject:<thread_id>:<trade_id>"

        1. Lookup the compiled graph in interrupt_registry by thread_id.
        2. Call graph.ainvoke(Command(resume=approved), config).
        3. If graph completes (no more pending nodes), clean up registry + saver.
        4. If graph interrupted again (another symbol needs approval), leave
           registry intact — next operator response will resume it again.
        """
        parts = data.split(":", 2)
        if len(parts) != 3:
            self._log.warning("[LG:callback] Malformed lg callback data: %r", data)
            return

        action_prefix, thread_id, trade_id = parts
        approved = action_prefix == "lg_approve"

        self._log.info(
            "[LG:callback] %s trade_id=%s thread_id=%s",
            "APPROVED" if approved else "REJECTED", trade_id, thread_id,
        )

        try:
            from src.langgraph.interrupt_registry import get_graph, unregister  # noqa: WPS433
        except ImportError:
            self._log.warning("[LG:callback] interrupt_registry not available")
            return

        graph = get_graph(thread_id)
        if graph is None:
            self._log.warning(
                "[LG:callback] thread_id=%s not in registry (process restarted?). "
                "Trade approval dropped — cycle may need manual intervention.",
                thread_id,
            )
            return

        config = {"configurable": {"thread_id": thread_id}}

        try:
            from langgraph.types import Command  # noqa: WPS433
            # Resume the graph with the operator's decision
            await graph.ainvoke(Command(resume=approved), config=config)

            # Check if graph completed or interrupted again (next symbol)
            try:
                current_state = await graph.aget_state(config)
                is_interrupted_again = bool(current_state.next)
            except Exception as _state_exc:
                self._log.debug(f"[LG:callback] aget_state failed: {_state_exc}")
                is_interrupted_again = False

            if is_interrupted_again:
                self._log.info(
                    "[LG:callback] thread_id=%s: grafo pausado novamente "
                    "(próximo símbolo aguardando aprovação)", thread_id,
                )
                # Keep registry intact — next button press will resume again
            else:
                self._log.info(
                    "[LG:callback] thread_id=%s: ciclo LangGraph completo — "
                    "limpando registry", thread_id,
                )
                saver = unregister(thread_id)
                if saver is not None:
                    try:
                        await saver.conn.close()
                    except Exception as _close_exc:
                        self._log.debug("[LG:callback] saver.conn.close error: %s", _close_exc)

        except Exception as exc:  # noqa: BLE001
            self._log.warning("[LG:callback] graph.ainvoke(Command) error: %s", exc)

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

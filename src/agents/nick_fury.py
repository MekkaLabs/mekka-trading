"""
src/agents/nick_fury.py
=======================
Nick Fury — Mission Commander

The top-level orchestrator. For each symbol in `settings.trading_assets`
he runs the full pipeline:

   ProfessorX (parallel analysis fan-out)
        ↓
   Vision (LLM strategic decision)
        ↓
   Batman (deterministic risk gate)
        ↓
   Iron Man (paper or live execution)
        ↓
   MekkaRepository (signal + trade + audit persistence)

Two loops are exposed:
  • run_main_cycle() — runs one full pass over all assets (intended for
    `settings.main_loop_interval_seconds`, default 4h)
  • run_monitor_cycle() — light-weight position monitor (intended for
    `settings.monitor_interval_seconds`, default 5m). Currently logs
    open positions; a richer monitor will land in a follow-up story.

Equity and open-positions are sourced from Portfolio Manager every
cycle (Story 026). The optional `equity_usd` argument on
`run_main_cycle` overrides Portfolio Manager when provided (used by the
CLI `--equity` flag and by tests).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from src.agents.base import AgentError, BaseAgent
from src.agents.batman import Batman, engage_kill_switch, is_kill_switch_active
from src.agents.iron_man import IronMan
from src.agents.portfolio_manager import PortfolioManager
from src.agents.professor_x import ProfessorX
from src.agents.vision import Vision
from src.config.settings import settings
from src.models.execution import ExecutionResult, ExecutionStatus
from src.models.orchestration import CycleReport  # re-exported below for back-compat
from src.models.portfolio import EquitySnapshot, EquitySource
from src.models.recovery import RecoveryPlan
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal
from src.persistence.repository import MekkaRepository
from src.services.breakers import ConsecutiveBreaker
from src.services.daily_pnl_writer import DailyPnLWriter


# ---------------------------------------------------------------------------
# Default starting equity (USD) — used only when both Portfolio Manager and
# the CLI `--equity` override are unavailable. Kept for backward-compatibility
# with code that called `run_main_cycle()` with the old default.
# ---------------------------------------------------------------------------
_DEFAULT_EQUITY_USD = 10_000.0


# `CycleReport` is now a Pydantic model living in
# `src/models/orchestration.py`. It is imported above and re-exported
# here so any existing `from src.agents.nick_fury import CycleReport`
# continues to work without changes.
__all__ = ["NickFury", "CycleReport", "run_forever"]


class NickFury(BaseAgent[list[CycleReport]]):
    """Mission Commander — top-level orchestrator."""

    def __init__(self) -> None:
        super().__init__(
            codename="NickFury",
            role="Mission Commander — global pipeline orchestrator",
        )
        self._professor = ProfessorX()
        self._vision = Vision()
        self._batman = Batman()
        self._ironman = IronMan()
        self._portfolio = PortfolioManager()
        self._daily_pnl = DailyPnLWriter()
        # Story 029a — Safety Net breakers
        self._exec_error_breaker = ConsecutiveBreaker(
            name="exec_error",
            threshold=settings.max_consecutive_exec_errors,
        )
        self._vision_fallback_breaker = ConsecutiveBreaker(
            name="vision_fallback",
            threshold=settings.max_consecutive_vision_fallbacks,
        )
        # Story 138 — Circuit Breaker Matrix (gaps)
        from src.services.breakers import RateWindowBreaker, StalePriceDetector, SpreadBreaker  # noqa: WPS433
        self._llm_error_breaker = RateWindowBreaker(
            name="llm_error_rate",
            window=settings.llm_error_rate_window,
            max_error_rate=settings.llm_error_rate_threshold,
        )
        # One stale-price detector per symbol — created lazily per symbol in _cycle_for_symbol
        self._stale_price_detectors: dict[str, Any] = {}
        # One spread breaker per symbol — created lazily
        self._spread_breakers: dict[str, Any] = {}
        self._StalePriceDetector = StalePriceDetector  # keep ref for lazy init
        self._SpreadBreaker = SpreadBreaker             # keep ref for lazy init
        # Story 140 — DEGRADED_MODE formal state machine (NORMAL ↔ DEGRADED)
        from src.services.degraded_mode import get_degraded_mode_manager  # noqa: WPS433
        self._degraded_mode = get_degraded_mode_manager(
            recovery_cycles=settings.degraded_mode_recovery_cycles
        )
        # Story 030 — Wolverine recovery agent (used in monitor cycle)
        from src.agents.wolverine import Wolverine
        self._wolverine = Wolverine()
        # Story 031 — Vision Critic (off by default; used per cycle when on)
        from src.agents.vision_critic import VisionCritic
        self._vision_critic = VisionCritic()
        # Story 035 — Telegram alerter (push only). Toggle via env.
        from src.services.telegram_alerter import TelegramAlerter
        self._telegram = TelegramAlerter()
        # Story 218 — Monitoring & Alerting (Milestone 34) — wiring dos 4 monitores.
        # Compartilham a instância de TelegramAlerter para não criar múltiplas sessões HTTP.
        from src.services.alert_throttle_manager import AlertThrottleManager
        from src.services.drawdown_monitor import DrawdownMonitor
        from src.services.position_concentration_alerter import PositionConcentrationAlerter
        from src.services.intraday_pnl_tracker import IntradayPnLTracker
        from src.services.funding_rate_monitor import FundingRateMonitor
        self._throttle = AlertThrottleManager()
        self._drawdown_monitor = DrawdownMonitor(alerter=self._telegram)
        self._concentration_alerter = PositionConcentrationAlerter(alerter=self._telegram)
        self._pnl_tracker = IntradayPnLTracker(alerter=self._telegram)
        self._funding_monitor = FundingRateMonitor(alerter=self._telegram)
        # Story 049 — DailyPerformanceWriter: once-per-day Deadpool snapshot
        from src.services.daily_performance_writer import DailyPerformanceWriter
        self._perf_writer = DailyPerformanceWriter()
        # Story 129 — Layer 1 subgraph compilado, injetado por make_checkpointed_graph().
        # None = fallback para ProfessorX.run() com asyncio.gather (modo clássico).
        self._layer1_graph: Any = None
        # Story 131 — VisionMoA: 3 LLMs em paralelo + orchestrator consenso.
        # Instanciado apenas se vision_moa_enabled=True para evitar 3 LLMClients
        # desnecessários quando MoA está desligado.
        self._vision_moa: Optional[Any] = None
        if settings.vision_moa_enabled:
            try:
                from src.agents.vision_moa import VisionMoA  # noqa: WPS433
                self._vision_moa = VisionMoA()
                self._log.info("[NickFury] VisionMoA enabled (Story 131)")
            except Exception as _moa_exc:  # noqa: BLE001
                self._log.warning(f"[NickFury] VisionMoA init failed (disabled): {_moa_exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Start the persistence layer and emit a boot audit event."""
        await MekkaRepository.initialize()

        # Restore peak_equity from DB so a mid-day restart does not hide
        # intra-day drawdown from Batman's daily drawdown guard (Story 057).
        try:
            persisted_peak = await MekkaRepository.get_today_peak_equity()
            if persisted_peak > 0:
                self._daily_pnl._peak_equity = persisted_peak
                self._log.info(
                    f"[NickFury] Restored peak_equity from DB: ${persisted_peak:,.2f}"
                )
        except Exception as _exc:
            self._log.warning(f"[NickFury] Could not restore peak_equity: {_exc}")

        await MekkaRepository.log_event(
            agent="NickFury",
            event="BOOT",
            severity="INFO",
            message=settings.summary(),
            payload={
                "mode": settings.mode_label,
                "network": settings.hyperliquid_network,
                "assets": settings.trading_assets,
            },
        )
        self._log.info("[NickFury] Pipeline initialized")

    def reset_breakers(self) -> None:
        """
        Reset all ConsecutiveBreakers and rate/stale breakers to zero.
        Call after releasing the kill switch (/resume) to prevent immediate
        retrip due to residual streak from before the halt.
        """
        self._exec_error_breaker.reset()
        self._vision_fallback_breaker.reset()
        # Story 138 — reset sliding-window and stale breakers
        self._llm_error_breaker.reset()
        for det in self._stale_price_detectors.values():
            det.reset()
        for sb in self._spread_breakers.values():
            sb.reset()
        # Story 140 — reset DEGRADED_MODE state machine so operator /resume
        # brings the system fully back to NORMAL even if still recovering.
        from src.services.degraded_mode import (  # noqa: WPS433
            get_degraded_mode_manager as _gdm,
            reset_degraded_mode_manager as _rdm,
        )
        _rdm()
        self._degraded_mode = _gdm(recovery_cycles=settings.degraded_mode_recovery_cycles)
        self._log.info("[NickFury] All circuit breakers + DEGRADED_MODE reset after kill switch release")

    async def shutdown(self) -> None:
        """Close exchange connections held by sub-agents."""
        await self._professor.close()
        await self._vision.close()
        # Story 131 — fechar VisionMoA se ativo (4 LLMClients internos)
        if self._vision_moa is not None:
            try:
                await self._vision_moa.close()
            except Exception:  # noqa: BLE001
                pass
        await MekkaRepository.log_event(
            agent="NickFury",
            event="SHUTDOWN",
            severity="INFO",
            message="Pipeline shutdown clean",
        )
        self._log.info("[NickFury] Pipeline shutdown clean")

    async def _run(  # type: ignore[override]
        self,
        equity_usd: Optional[float] = None,
    ) -> list[CycleReport]:
        """One full pass across all configured assets."""
        return await self.run_main_cycle(equity_usd=equity_usd)

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------

    async def run_main_cycle(
        self,
        equity_usd: Optional[float] = None,
    ) -> list[CycleReport]:
        """
        Run one full pass across all configured assets.

        Equity is sourced from Portfolio Manager every cycle. Pass
        `equity_usd` to override (used by CLI `--equity` and by tests).
        """
        if is_kill_switch_active():
            self._log.warning("[NickFury] Kill switch ACTIVE — main cycle skipped")
            await MekkaRepository.log_event(
                agent="NickFury",
                event="CYCLE_SKIPPED",
                severity="WARNING",
                message="Kill switch active",
            )
            # Story 035 — push the kill-switch event so the operator
            # actually hears about it.
            await self._telegram.alert(
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                agent="NickFury",
                message="Kill switch active — main cycle skipped",
                payload={"source": "pre_cycle_check"},
            )
            # [A4] Best-effort equity snapshot while halted so daily_pnl
            # remains queryable and Batman's next drawdown read sees fresh data.
            try:
                ks_snapshot = await self._portfolio.run()
                ks_trades_today = await MekkaRepository.count_trades_today()
                ks_equity = (
                    equity_usd if equity_usd is not None else ks_snapshot.equity_usd
                )
                await self._daily_pnl.record_cycle(
                    equity_usd=ks_equity,
                    trades_count_today=ks_trades_today,
                    snapshot=ks_snapshot,
                )
            except Exception as exc:  # noqa: BLE001
                self._log.warning(
                    f"[NickFury] KS: daily_pnl halted-snapshot failed: {exc}"
                )
            return []

        # Read portfolio state for Batman's risk checks
        drawdown = await MekkaRepository.get_today_drawdown_pct()
        trades_today = await MekkaRepository.count_trades_today()

        # ── Story 067 — Daily PnL Auto-pause / Auto-kill ──────────────────
        # Check today's realized PnL against profit target and drawdown cap.
        try:
            today_pnl_usd = await MekkaRepository.get_today_pnl_usd()
            _equity_for_pct = equity_usd or settings.paper_initial_equity
            if _equity_for_pct and _equity_for_pct > 0:
                today_pnl_pct = today_pnl_usd / _equity_for_pct

                # Auto-pause: daily profit target reached → stop new signals
                if today_pnl_pct >= settings.daily_profit_target_pct:
                    self._log.warning(
                        f"[NickFury] Daily profit target reached "
                        f"({today_pnl_pct*100:.2f}% ≥ {settings.daily_profit_target_pct*100:.1f}%) "
                        "— pausing new signals for today"
                    )
                    await MekkaRepository.log_event(
                        agent="NickFury",
                        event="DAILY_PROFIT_TARGET_REACHED",
                        severity="INFO",
                        message=(
                            f"Daily PnL +${today_pnl_usd:.2f} ({today_pnl_pct*100:.2f}%) "
                            f"≥ target {settings.daily_profit_target_pct*100:.1f}% — cycle skipped"
                        ),
                        payload={"today_pnl_usd": today_pnl_usd, "today_pnl_pct": today_pnl_pct},
                    )
                    try:
                        await self._telegram.alert(
                            event="DAILY_PROFIT_TARGET_REACHED",
                            severity="INFO",
                            agent="NickFury",
                            message=(
                                f"🎯 Meta diária atingida: +${today_pnl_usd:.2f} "
                                f"({today_pnl_pct*100:.2f}%). "
                                "Novos sinais pausados pelo restante do dia."
                            ),
                            payload={},
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    return []

                # Auto-kill: daily drawdown cap triggered → engage kill switch
                if drawdown >= settings.max_daily_drawdown_pct:
                    self._log.error(
                        f"[NickFury] Daily drawdown cap hit "
                        f"({drawdown*100:.2f}% ≥ {settings.max_daily_drawdown_pct*100:.1f}%) "
                        "— engaging kill switch"
                    )
                    await MekkaRepository.log_event(
                        agent="NickFury",
                        event="DAILY_DRAWDOWN_KILL_SWITCH",
                        severity="CRITICAL",
                        message=(
                            f"Daily drawdown {drawdown*100:.2f}% ≥ cap "
                            f"{settings.max_daily_drawdown_pct*100:.1f}% — kill switch engaged"
                        ),
                        payload={"drawdown_pct": drawdown},
                    )
                    try:
                        await self._telegram.alert(
                            event="DAILY_DRAWDOWN_KILL_SWITCH",
                            severity="CRITICAL",
                            agent="NickFury",
                            message=(
                                f"🛑 DRAWDOWN DIÁRIO: {drawdown*100:.2f}% ≥ "
                                f"{settings.max_daily_drawdown_pct*100:.1f}%. "
                                "Kill switch acionado automaticamente."
                            ),
                            payload={},
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        engage_kill_switch()
                    except Exception:  # noqa: BLE001
                        pass
                    return []
        except Exception as _pnl_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury] Daily PnL gate skipped: {_pnl_exc}")

        # Snapshot account equity + open positions once per cycle
        snapshot: EquitySnapshot = await self._portfolio.run()
        await MekkaRepository.log_event(
            agent="PortfolioManager",
            event=f"SNAPSHOT_{snapshot.source.value}",
            severity="INFO" if not snapshot.is_degraded else "WARNING",
            message=snapshot.summary(),
            payload={
                "equity_usd": snapshot.equity_usd,
                "open_positions": snapshot.open_positions_count,
                "is_paper": snapshot.is_paper,
                "error": snapshot.error,
            },
        )

        # CLI override wins over Portfolio Manager. Otherwise use snapshot.
        effective_equity = (
            equity_usd if equity_usd is not None else snapshot.equity_usd
        )
        open_positions = snapshot.open_positions_count

        # Story 029a — start running notional from existing positions in
        # the snapshot. Each new paper/live execution this cycle adds to it.
        running_notional_usd = sum(
            p.size * p.entry_price for p in (snapshot.positions or [])
        )

        # Story 218 — run pre-cycle monitors (drawdown, concentration, intraday PnL).
        # Best-effort: falhas nunca interrompem o ciclo principal.
        await self._run_pre_cycle_monitors(snapshot=snapshot, effective_equity=effective_equity)

        # Runtime mode — hot-reload sem nunca ampliar a lista definida no .env.
        # O operador pode reduzir/ordenar ativos via TRADING_ASSETS e o preset
        # do runtime_mode só atua como filtro adicional, não como expansão.
        from src.config.runtime_mode import get_params as _get_mode_params
        _configured_assets = list(settings.trading_assets)
        _mode_assets = _get_mode_params().get("trading_assets", _configured_assets)
        _active_assets = [sym for sym in _configured_assets if sym in _mode_assets]
        if not _active_assets:
            _active_assets = _configured_assets

        # Story 050 — Altcoins validation: filter out symbols not available on
        # the current exchange (prevents CYCLE_ERROR spam for unknown pairs).
        try:
            _validated = await self._professor.validate_symbols(_active_assets)
            if len(_validated) < len(_active_assets):
                _skipped = [s for s in _active_assets if s not in _validated]
                self._log.warning(
                    f"[NickFury] Symbols not available on exchange — skipping: {_skipped}"
                )
                await MekkaRepository.log_event(
                    agent="NickFury",
                    event="SYMBOLS_SKIPPED",
                    severity="WARNING",
                    message=f"Not available on exchange: {_skipped}",
                    payload={"skipped": _skipped, "active": _validated},
                )
            _active_assets = _validated
        except Exception as _val_exc:  # noqa: BLE001
            self._log.warning(
                f"[NickFury] Symbol validation failed (using full list): {_val_exc}"
            )

        # [Story 057] Snapshot of current positions for Batman's correlation gate.
        # Updated intra-cycle as new positions are opened so Batman sees the
        # running state, not just the state at cycle start.
        _current_positions = list(snapshot.positions or [])

        # Story 145 — Opportunity Scanner: quick pre-scan to prioritize symbols.
        # If enabled, only the top-N scoring symbols proceed to deep Layer 1 analysis.
        # Fails silently — if scanner errors, fall back to full list.
        if settings.opportunity_scan_enabled and len(_active_assets) > 1:
            try:
                from src.services.opportunity_scanner import run_pre_scan  # noqa: WPS433
                # Build basic market data from stale-price detectors (no extra I/O)
                _scan_data: dict = {}
                for _sym in _active_assets:
                    _det = self._stale_price_detectors.get(_sym)
                    _scan_data[_sym] = {
                        "is_stale": _det.is_stale if _det and hasattr(_det, "is_stale") else False,
                        "price": _det.last_price if _det else 0.0,
                    }
                _pre_scan = run_pre_scan(
                    symbols=_active_assets,
                    market_data=_scan_data,
                    top_n=settings.opportunity_scan_top_n,
                    min_score=settings.opportunity_scan_min_score,
                )
                self._log.info(_pre_scan.summary())
                if _pre_scan.selected:
                    _active_assets = _pre_scan.selected
                    await MekkaRepository.log_event(
                        agent="NickFury",
                        event="OPPORTUNITY_PRESCAN",
                        severity="INFO",
                        message=_pre_scan.summary(),
                        payload={
                            "selected": _pre_scan.selected,
                            "skipped": _pre_scan.skipped,
                            "top_scores": {
                                s.symbol: s.score for s in _pre_scan.scores[:5]
                            },
                        },
                    )
            except Exception as _scan_exc:  # noqa: BLE001
                self._log.warning(f"[NickFury] OpportunityScanner failed (using full list): {_scan_exc}")

        reports: list[CycleReport] = []
        for symbol in _active_assets:
            try:
                report = await self._cycle_for_symbol(
                    symbol=symbol,
                    equity_usd=effective_equity,
                    current_drawdown_pct=drawdown,
                    trades_today=trades_today,
                    open_positions=open_positions,
                    running_notional_usd=running_notional_usd,
                    current_positions=_current_positions,  # [Story 057]
                )
                reports.append(report)
                if report.is_executed():
                    trades_today += 1
                    # A new paper/live position increases the count for the
                    # remainder of this cycle so Batman sees the running total.
                    open_positions += 1
                    if report.execution is not None:
                        running_notional_usd += report.execution.notional_usd
                    # [Story 057] Update correlation snapshot so the next symbol
                    # in this cycle sees the newly opened position.
                    try:
                        from src.models.portfolio import PositionSummary as _PS  # noqa: WPS433
                        _new_pos = _PS(
                            symbol=symbol,
                            side=report.signal.action.value.lower() if report.signal else "long",
                            size=report.execution.quantity if report.execution else 0.0,
                            entry_price=report.execution.avg_price if report.execution else 0.0,
                        )
                        _current_positions.append(_new_pos)
                    except Exception:
                        pass  # correlation gate degrades gracefully

                # Story 029a — observe safety-net breakers per cycle outcome
                await self._check_breakers(report=report)
            except Exception as exc:  # noqa: BLE001
                self._log.exception(f"[NickFury] {symbol} cycle crashed: {exc}")
                reports.append(CycleReport(symbol=symbol, error=str(exc)))
                await MekkaRepository.log_event(
                    agent="NickFury",
                    event="CYCLE_ERROR",
                    severity="ERROR",
                    symbol=symbol,
                    message=str(exc),
                )
                # Story 035 — best-effort Telegram push (filtered internally)
                await self._telegram.alert(
                    event="CYCLE_ERROR",
                    severity="ERROR",
                    agent="NickFury",
                    symbol=symbol,
                    message=str(exc),
                )

        # End-of-cycle Daily PnL upsert. Uses the *effective* equity
        # (CLI override wins over snapshot, same hierarchy used for
        # Iron Man sizing) and `trades_today` count after this cycle so
        # Batman's next read of get_today_drawdown_pct sees fresh data.
        try:
            await self._daily_pnl.record_cycle(
                equity_usd=effective_equity,
                trades_count_today=trades_today,
                snapshot=snapshot,
            )
        except Exception as exc:  # noqa: BLE001
            # Persistence failure must not break the main cycle return value.
            self._log.error(f"[NickFury] daily_pnl record_cycle failed: {exc}")

        # Story 049 — fire DailyPerformanceWriter once per UTC day (no-op if already ran)
        try:
            import asyncio as _asyncio  # noqa: WPS433
            _asyncio.create_task(self._perf_writer.maybe_run(), name="daily_perf_writer")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[NickFury] daily_perf_writer task failed to start: {exc}")

        return reports

    # ------------------------------------------------------------------
    # Story 126 — LangGraph checkpointed cycle
    # ------------------------------------------------------------------

    async def run_with_checkpointing(
        self,
        equity_usd: Optional[float] = None,
    ) -> list:
        """
        Versão checkpointed do ciclo principal usando LangGraph + AsyncSqliteSaver.

        Cada símbolo é um super-step com checkpoint automático entre eles.
        Se o processo morrer durante o símbolo N, na próxima execução o ciclo
        retoma do símbolo N (via resume do thread_id salvo no SQLite).

        Story 127: quando TELEGRAM_TRADE_APPROVAL_ENABLED=true, o nó
        process_symbol_node faz interrupt() ao chegar na aprovação de trade.
        graph.ainvoke() retorna com o grafo em estado "interrupted". O ciclo
        continua quando TelegramInbound recebe a resposta do operador e chama
        graph.ainvoke(Command(resume=approved), config). O estado é durável
        no SQLite — sobrevive a restarts do processo.

        Retorna lista de dicts (CycleReport.model_dump()) em vez de CycleReport
        — necessário porque o estado do grafo deve ser JSON-serializável.

        Ativado por: python3 run.py --langgraph
        """
        from src.langgraph.cycle_graph import make_checkpointed_graph, make_initial_state
        from src.langgraph.interrupt_registry import register, unregister  # Story 127

        effective_equity = equity_usd or 0.0
        initial_state = make_initial_state(equity_usd=effective_equity)
        thread_id = initial_state["cycle_id"]  # UUID único por ciclo

        self._log.info(
            f"[NickFury:LG] Iniciando ciclo checkpointed — thread_id={thread_id}"
        )

        graph, saver = await make_checkpointed_graph(self)

        # Story 127 — registrar grafo para que TelegramInbound possa resumir
        # interrupts de aprovação de trade sem precisar recriar o grafo.
        register(thread_id, graph, saver)

        config = {"configurable": {"thread_id": thread_id}}

        try:
            final_state = await graph.ainvoke(initial_state, config=config)
            reports = final_state.get("reports", [])

            # Story 127 — verificar se o grafo foi interrompido aguardando aprovação
            try:
                current_graph_state = await graph.aget_state(config)
                is_interrupted = bool(current_graph_state.next)
            except Exception as _state_exc:
                self._log.debug(f"[NickFury:LG] aget_state check failed: {_state_exc}")
                is_interrupted = False

            if is_interrupted:
                self._log.info(
                    f"[NickFury:LG] Ciclo {thread_id} PAUSADO aguardando aprovação Telegram. "
                    "TelegramInbound retomará quando operador responder. "
                    "Estado durável no SQLite."
                )
                # Não fechar o saver — TelegramInbound precisa dele para resume.
                # unregister() + saver.conn.close() serão feitos pelo TelegramInbound
                # após o ciclo completar (ver _handle_callback_query).
                return reports  # retorna reports parciais (pode ser [])
            else:
                self._log.info(
                    f"[NickFury:LG] Ciclo {thread_id} completo — "
                    f"{len(reports)} reports, "
                    f"símbolos: {final_state.get('symbols_completed', [])}"
                )
                return reports

        except Exception as exc:
            self._log.exception(f"[NickFury:LG] Ciclo {thread_id} falhou: {exc}")
            raise
        finally:
            # Só fecha saver e desregistra se o grafo NÃO está interrupted.
            # Se interrupted, o saver precisa sobreviver para o TelegramInbound.
            try:
                current_graph_state = await graph.aget_state(config)
                if not current_graph_state.next:
                    unregister(thread_id)
                    await saver.conn.close()
            except Exception:
                # Em caso de erro no finally, fechar preventivamente
                try:
                    unregister(thread_id)
                    await saver.conn.close()
                except Exception:
                    pass

    async def _cycle_for_symbol(
        self,
        symbol: str,
        equity_usd: float,
        current_drawdown_pct: float,
        trades_today: int,
        open_positions: int = 0,
        running_notional_usd: float = 0.0,
        current_positions: list | None = None,  # [Story 057] correlation gate
        lg_thread_id: Optional[str] = None,      # [Story 127] set when running under LangGraph
        layer1_graph: Optional[Any] = None,      # [Story 129] Layer 1 subgraph compilado
    ) -> CycleReport:
        # Story 136 — MekkaEventBus: lazy import + fail-silent publish helpers
        _cycle_id = lg_thread_id or f"classic:{symbol}"
        _ts_start = datetime.now(timezone.utc).isoformat()

        # Story 151 — Performance Benchmarks: start cycle measurement
        try:
            from src.services.pipeline_benchmark import get_pipeline_benchmark  # noqa: WPS433
            _bench = get_pipeline_benchmark()
            _bench_token = _bench.start_cycle(symbol=symbol, cycle_id=_cycle_id)
        except Exception as _bench_init_exc:  # noqa: BLE001
            _bench = None
            _bench_token = None
            logger.debug(f"[NickFury] PipelineBenchmark init skipped: {_bench_init_exc}")

        # Story 165 — CycleEventLog: init append-only event log for this cycle.
        # Fail-silent: _cel remains None if unavailable; all .emit() calls guarded.
        _cel = None
        try:
            from src.services.cycle_event_log import get_cycle_event_log, CycleEventType as _CET  # noqa: WPS433
            _cel = get_cycle_event_log()
        except Exception as _cel_init_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:165] CycleEventLog init skipped: {_cel_init_exc}")

        def _cel_emit(event_type: Any, **kwargs: Any) -> None:  # noqa: ANN401
            """Fail-silent CycleEventLog emit."""
            try:
                if _cel is not None:
                    _cel.emit(event_type, symbol=symbol, cycle_id=_cycle_id, **kwargs)
            except Exception as _ce_exc:  # noqa: BLE001
                logger.debug(f"[NickFury:165] CycleEventLog emit skipped: {_ce_exc}")

        # Emit CYCLE_START
        _cel_emit(_CET.CYCLE_START if _cel else None, equity_usd=equity_usd, timestamp=_ts_start)

        # Story 195 — CycleAgentState: state machine formal por símbolo.
        # OpenHands AgentState pattern: enum IDLE→SCANNING→ANALYZING→SIGNALING→...→FINISHED.
        # Permite que o dashboard consulte o estado exato de cada símbolo em tempo real.
        # Fails silently.
        _state195 = None
        try:
            from src.services.cycle_agent_state import (  # noqa: WPS433
                get_cycle_agent_state_machine as _get_state_machine,
                CycleAgentStateEnum as _CAS,
            )
            _state195 = _get_state_machine()
            _state195.transition(symbol, _CAS.SCANNING, cycle_id=str(_cycle_id))
        except Exception as _s195_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:195] CycleAgentState init skipped: {_s195_exc}")

        # Story 196 — CycleEventSource: tag de origem para eventos do CycleEventLog.
        # OpenHands EventSource pattern: USER / AGENT / ENVIRONMENT.
        # Aqui: NICKFURY, VISION, BATMAN, IRONMAN, SYSTEM para cada bloco.
        # Fails silently.
        _tagger196 = None
        try:
            from src.services.cycle_event_source import (  # noqa: WPS433
                get_event_source_tagger as _get_tagger,
                CycleEventSource as _CES,
            )
            _tagger196 = _get_tagger()
            _tagger196.tag(
                event_type="CYCLE_START",
                symbol=symbol,
                cycle_id=str(_cycle_id),
                source=_CES.NICKFURY,
                payload={"equity_usd": equity_usd},
            )
        except Exception as _t196_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:196] CycleEventSource init skipped: {_t196_exc}")

        # Story 197 — CycleBatchedExporter: acumula eventos para export em lote.
        # OpenHands BatchedWebHook pattern: buffer + flush periódico para webhook externo.
        # Fails silently.
        _exporter197 = None
        try:
            from src.services.cycle_batched_exporter import get_cycle_batched_exporter  # noqa: WPS433
            _exporter197 = get_cycle_batched_exporter()
            _exporter197.add({
                "event_type": "CYCLE_START", "symbol": symbol,
                "cycle_id": str(_cycle_id), "source": "NICKFURY",
                "equity_usd": equity_usd,
            })
        except Exception as _e197_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:197] CycleBatchedExporter init skipped: {_e197_exc}")

        # Stories 198-202 — OpenHands Wave 2: ConversationMemory, ArtifactStore,
        # ActionRiskAnalyzer, StateResetter. Fails silently.
        _conv_mem198 = None
        try:
            from src.services.cycle_conversation_memory import get_cycle_conversation_memory  # noqa: WPS433
            _conv_mem198 = get_cycle_conversation_memory()
        except Exception as _e198_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:198] CycleConversationMemory init skipped: {_e198_exc}")

        _artifact_store200 = None
        try:
            from src.services.cycle_artifact_store import (  # noqa: WPS433
                get_cycle_artifact_store as _get_artifact_store,
                ArtifactType as _AT,
            )
            _artifact_store200 = _get_artifact_store()
        except Exception as _e200_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:200] CycleArtifactStore init skipped: {_e200_exc}")

        _risk_analyzer201 = None
        try:
            from src.services.cycle_action_risk_analyzer import (  # noqa: WPS433
                get_cycle_action_risk_analyzer as _get_risk_analyzer,
            )
            _risk_analyzer201 = _get_risk_analyzer()
        except Exception as _e201_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:201] CycleActionRiskAnalyzer init skipped: {_e201_exc}")

        _resetter202 = None
        try:
            from src.services.cycle_state_resetter import (  # noqa: WPS433
                get_cycle_state_resetter as _get_resetter,
                ResetScope as _RS,
            )
            _resetter202 = _get_resetter()
            _resetter202.reset(_RS.CYCLE_START, symbol=symbol, cycle_id=str(_cycle_id))
        except Exception as _e202_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:202] CycleStateResetter CYCLE_START skipped: {_e202_exc}")

        # Stories 208-212 — LangGraph Patterns: StateGraph, ConditionalRouter,
        # Checkpointer, ParallelBranch, GraphInterrupt. Fails silently.
        _state_graph208 = None
        try:
            from src.services.cycle_state_graph import build_default_mekka_graph  # noqa: WPS433
            _state_graph208 = build_default_mekka_graph()
            logger.debug(f"[NickFury:208] CycleStateGraph compiled for {symbol}")
        except Exception as _e208_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:208] CycleStateGraph init skipped: {_e208_exc}")

        _router209 = None
        try:
            from src.services.cycle_conditional_router import build_vision_router  # noqa: WPS433
            _router209 = build_vision_router(fallback="batman")
            logger.debug(f"[NickFury:209] CycleConditionalRouter ready ({_router209.summary()['rules_count']} rules)")
        except Exception as _e209_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:209] CycleConditionalRouter init skipped: {_e209_exc}")

        _checkpointer210 = None
        try:
            from src.services.cycle_graph_checkpointer import get_cycle_graph_checkpointer  # noqa: WPS433
            _checkpointer210 = get_cycle_graph_checkpointer()
        except Exception as _e210_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:210] CycleGraphCheckpointer init skipped: {_e210_exc}")

        _parallel211 = None
        try:
            from src.services.cycle_parallel_branch import get_cycle_parallel_branch  # noqa: WPS433
            _parallel211 = get_cycle_parallel_branch()
        except Exception as _e211_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:211] CycleParallelBranch init skipped: {_e211_exc}")

        _interrupt212 = None
        try:
            from src.services.cycle_graph_interrupt import get_cycle_graph_interrupt  # noqa: WPS433
            _interrupt212 = get_cycle_graph_interrupt()
            # Expira interrupts pendentes de ciclos anteriores
            _expired = _interrupt212.auto_expire_pending()
            if _expired:
                logger.debug(f"[NickFury:212] auto-expired {_expired} pending interrupts")
        except Exception as _e212_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:212] CycleGraphInterrupt init skipped: {_e212_exc}")

        # Stories 203, 206, 207 — AutoGen / CrewAI Wave 1 integrations.
        # GroupChatManager (203), PipelineOrchestrator (206), AgentBackstory (207).
        # Fails silently.
        _group_chat203 = None
        try:
            from src.services.cycle_group_chat import get_cycle_group_chat_manager  # noqa: WPS433
            _group_chat203 = get_cycle_group_chat_manager()
        except Exception as _e203_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:203] GroupChatManager init skipped: {_e203_exc}")

        _pipeline206 = None
        try:
            from src.services.cycle_pipeline_orchestrator import get_cycle_pipeline_orchestrator  # noqa: WPS433
            _pipeline206 = get_cycle_pipeline_orchestrator()
        except Exception as _e206_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:206] PipelineOrchestrator init skipped: {_e206_exc}")

        try:
            from src.services.mekka_agent_backstory import get_mekka_agent_backstory  # noqa: WPS433
            _backstory207 = get_mekka_agent_backstory()
            _bs_extra = f"symbol={symbol}, equity_usd={equity_usd}"
            _ = _backstory207.build_system_prompt("NICKFURY", _bs_extra)
            logger.debug(f"[NickFury:207] AgentBackstory NICKFURY prompt ready")
        except Exception as _e207_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:207] AgentBackstory init skipped: {_e207_exc}")

        # Story 166 — AgentStepGuard: per-cycle stuck loop + MAX_ITERATIONS protection.
        # Creates a fresh guard for this cycle — checks after Vision and after Batman.
        # Fails silently — _guard remains None; all check() calls are guarded.
        _guard = None
        try:
            from src.services.agent_step_guard import NickFuryStepGuard  # noqa: WPS433
            _guard = NickFuryStepGuard.for_cycle(symbol=symbol, cycle_id=_cycle_id)
        except Exception as _guard_init_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:166] AgentStepGuard init skipped: {_guard_init_exc}")

        def _guard_check(fn_name: str, result: Any) -> bool:  # noqa: ANN401
            """Returns True if cycle should abort (stuck or max iterations exceeded)."""
            try:
                if _guard is None:
                    return False
                _step_rec, _should_abort = _guard.check(function_name=fn_name, result=result)
                if _should_abort:
                    logger.warning(
                        f"[NickFury:166] {symbol} {fn_name} — step guard abort "
                        f"(stuck={_guard.is_stuck()}, "
                        f"max={_guard.is_max_iterations_exceeded()}, "
                        f"step={_step_rec.step_number})"
                    )
                    _cel_emit(_CET.STUCK_LOOP if _cel else None, fn=fn_name, step=_step_rec.step_number)
                return _should_abort
            except Exception as _g_exc:  # noqa: BLE001
                logger.debug(f"[NickFury:166] step guard check skipped: {_g_exc}")
                return False

        async def _emit(topic: str, payload: dict) -> None:
            """Fail-silent event publish."""
            try:
                from src.services.event_bus import get_event_bus  # noqa: WPS433
                await get_event_bus().publish(topic, payload)
            except Exception as _eb_exc:  # noqa: BLE001
                logger.debug(f"[NickFury] EventBus publish skipped: {_eb_exc}")

        await _emit("cycle.start", {
            "cycle_id": _cycle_id, "symbol": symbol, "timestamp": _ts_start,
        })

        # Story 138 — LLM error rate gate: if breaker is already tripped, skip cycle
        if self._llm_error_breaker.is_tripped:
            self._log.warning(
                f"[NickFury] {symbol} LLM error rate too high "
                f"({self._llm_error_breaker.error_rate:.1%} >= "
                f"{settings.llm_error_rate_threshold:.1%}) — skipping cycle"
            )
            return CycleReport(
                symbol=symbol,
                error=f"LLM error rate circuit breaker tripped: {self._llm_error_breaker.summary()}",
            )

        # Story 140 — DEGRADED_MODE: skip new entries when system is degraded.
        # Existing positions continue to be managed by Cyclops/Wolverine in the
        # monitor cycle. Recovery happens automatically after `recovery_cycles`
        # consecutive successful Vision calls (see observe_success below).
        if self._degraded_mode.is_degraded:
            self._log.warning(
                f"[NickFury] {symbol} DEGRADED_MODE active "
                f"({self._degraded_mode.reason}) — "
                f"recovery {self._degraded_mode.recovery_progress} — skipping new entry"
            )
            return CycleReport(
                symbol=symbol,
                error=f"DEGRADED_MODE: {self._degraded_mode.reason}",
            )

        # Story 251 — Cycle Checkpoint: init store para save/restore de etapas do ciclo.
        # Fail-silent: _cp251 permanece None se o serviço não estiver disponível.
        _cp251 = None
        try:
            from src.services.cycle_checkpoint import get_cycle_checkpoint_store  # noqa: WPS433
            _cp251 = get_cycle_checkpoint_store()
        except Exception as _cp251_init_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:251] CycleCheckpointStore init skipped: {_cp251_init_exc}")

        # 1. Analysis fan-out
        # Story 129 — usa Layer 1 LangGraph subgraph quando disponível (modo --langgraph).
        # Fallback para ProfessorX.run() com asyncio.gather quando não disponível.
        # Story 251 — tenta restaurar análise do checkpoint antes de chamar ProfessorX.
        _analysis251_restored = False
        if _cp251 is not None:
            try:
                _cp251_analysis_data = await _cp251.load(str(_cycle_id), symbol, "ANALYSIS")
                if _cp251_analysis_data:
                    from src.models.market_analysis import MarketAnalysis  # noqa: WPS433
                    analysis = MarketAnalysis(**_cp251_analysis_data)
                    _analysis251_restored = True
                    logger.debug(
                        f"[NickFury:251] {symbol} ANALYSIS restored from checkpoint "
                        f"(cycle={_cycle_id})"
                    )
            except Exception as _cp251_load_exc:  # noqa: BLE001
                logger.debug(f"[NickFury:251] ANALYSIS checkpoint load skipped: {_cp251_load_exc}")

        if not _analysis251_restored:
            try:
                if layer1_graph is not None and lg_thread_id is not None:
                    from src.langgraph.layer1_graph import run_layer1_subgraph  # noqa: WPS433
                    analysis = await run_layer1_subgraph(
                        graph=layer1_graph,
                        symbol=symbol,
                        cycle_id=lg_thread_id,
                    )
                else:
                    analysis = await self._professor.run(symbol=symbol)
            except AgentError as exc:
                return CycleReport(symbol=symbol, error=f"Analysis failed: {exc}")

            # Story 251 — salva checkpoint ANALYSIS após ProfessorX concluir.
            if _cp251 is not None:
                try:
                    _analysis_payload = {}
                    if hasattr(analysis, "model_dump"):
                        _analysis_payload = analysis.model_dump()
                    elif hasattr(analysis, "dict"):
                        _analysis_payload = analysis.dict()
                    if _analysis_payload:
                        await _cp251.save(str(_cycle_id), symbol, "ANALYSIS", _analysis_payload)
                except Exception as _cp251_save_exc:  # noqa: BLE001
                    logger.debug(f"[NickFury:251] ANALYSIS checkpoint save skipped: {_cp251_save_exc}")

        # Story 138 — Stale price check: lazy init detector per symbol
        if symbol not in self._stale_price_detectors:
            self._stale_price_detectors[symbol] = self._StalePriceDetector(
                name=f"stale_{symbol}",
                window=settings.stale_price_window,
                min_variation_pct=settings.stale_price_min_variation_pct,
            )
        _price_now = analysis.price if analysis else 0.0
        if _price_now > 0 and self._stale_price_detectors[symbol].observe(_price_now):
            self._log.warning(
                f"[NickFury] {symbol} stale price detected "
                f"({self._stale_price_detectors[symbol].summary()}) — skipping cycle"
            )
            await _emit("agent.error", {
                "cycle_id": _cycle_id, "symbol": symbol,
                "agent": "StalePriceDetector", "error": "stale_price",
            })
            return CycleReport(symbol=symbol, error=f"Stale price: {_price_now}")

        # Story 165 — ANALYSIS_DONE
        _cel_emit(
            _CET.ANALYSIS_DONE if _cel else None,
            price=round(_price_now, 4),
            volatility=getattr(analysis, "volatility", None),
        )

        # Story 195 — transition: SCANNING → ANALYZING
        try:
            if _state195 is not None:
                _state195.transition(symbol, _CAS.ANALYZING, cycle_id=str(_cycle_id))
        except Exception as _s195a_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:195] state ANALYZING transition skipped: {_s195a_exc}")

        # Story 196 — tag ANALYSIS_DONE with source=NICKFURY
        try:
            if _tagger196 is not None:
                _tagger196.tag(
                    event_type="ANALYSIS_DONE", symbol=symbol,
                    cycle_id=str(_cycle_id), source=_CES.NICKFURY,
                    payload={"price": round(_price_now, 4)},
                )
        except Exception as _t196a_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:196] source tag ANALYSIS_DONE skipped: {_t196a_exc}")

        # Story 197 — add ANALYSIS_DONE to exporter batch
        try:
            if _exporter197 is not None:
                _exporter197.add({
                    "event_type": "ANALYSIS_DONE", "symbol": symbol,
                    "cycle_id": str(_cycle_id), "source": "NICKFURY",
                    "price": round(_price_now, 4),
                })
        except Exception as _e197a_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:197] batch ANALYSIS_DONE skipped: {_e197a_exc}")

        # Story 188 — CycleTrajectory: start trajectory + record ANALYSIS_DONE step.
        # SWE-agent Trajectory/StepOutput: each cycle step is recorded as (stage, input, output).
        # Forms an immutable audit trail per cycle — used for debug, replay and latency metrics.
        # Fails silently.
        _traj188 = None
        try:
            from src.services.cycle_trajectory import get_trajectory_store as _get_traj  # noqa: WPS433
            _traj188 = _get_traj().start_cycle(symbol, cycle_id=str(_cycle_id))
            _get_traj().record_step(
                str(_cycle_id), stage="ANALYSIS_DONE",
                input_summary=f"symbol={symbol}",
                output_summary=f"price={_price_now:.4f}",
            )
        except Exception as _t188_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:188] CycleTrajectory start skipped: {_t188_exc}")

        # Story 192 — MarketEnvironmentSnapshot: capture market state after analysis.
        # SWE-agent Environment State Capture: env state captured between steps for context.
        # Used by Vision (block injection), IncrementalCycleSkip (precise diff), Trajectory.
        # Fails silently.
        try:
            from src.services.market_environment_snapshot import get_env_snapshot_store  # noqa: WPS433
            get_env_snapshot_store().capture(symbol, analysis=analysis, cycle_id=str(_cycle_id))
        except Exception as _snap192_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:192] EnvSnapshot capture skipped: {_snap192_exc}")

        # Story 218 — FundingRateMonitor: alerta proativo de funding extremo.
        # Chamado após analysis (BlackPanther fornece funding_rate no MarketAnalysis).
        # Throttle: WARN=2h, BLOCK=1h por símbolo. Absorve falhas silenciosamente.
        try:
            _fr = getattr(analysis, "funding_rate", None)
            if _fr is not None:
                _fr_pct = float(_fr) * 100  # MarketAnalysis armazena como decimal
                _fr_key = f"FUNDING_{symbol}"
                _cooldown_fr = 3600.0  # 1h para qualquer nível de funding
                if self._throttle.is_allowed(_fr_key, cooldown_seconds=_cooldown_fr):
                    _fr_alert = await self._funding_monitor.check(
                        symbol=symbol,
                        funding_rate_pct=_fr_pct,
                    )
                    if _fr_alert is not None:
                        self._throttle.record_sent(_fr_key)
        except Exception as _fr218_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:218] FundingRateMonitor skipped: {_fr218_exc}")

        # Story 189 — CycleBudgetGuard: check LLM cost budget before Vision.
        # SWE-agent max_cost done_status: exit gracefully when budget exceeded.
        # Here: force HOLD instead of blocking — pipeline continues, just no LLM call.
        # Fails silently — executes Vision normally if guard unavailable.
        _budget_skipped = False
        try:
            from src.services.cycle_budget_guard import get_cycle_budget_guard  # noqa: WPS433
            _bskip, _breason = get_cycle_budget_guard().should_skip_vision(symbol)
            if _bskip:
                _budget_skipped = True
                self._log.warning(f"[NickFury:189] CycleBudgetGuard → HOLD: {_breason}")
        except Exception as _bg189_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:189] CycleBudgetGuard check skipped: {_bg189_exc}")

        # Story 195 — transition: ANALYZING → SIGNALING (antes do Vision)
        try:
            if _state195 is not None:
                _state195.transition(symbol, _CAS.SIGNALING, cycle_id=str(_cycle_id))
        except Exception as _s195b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:195] state SIGNALING transition skipped: {_s195b_exc}")

        # 2. Vision strategic decision
        # Story 131 — MoA path: 3 LLMs em paralelo quando vision_moa_enabled=True.
        # Fallback silencioso para Vision clássico se VisionMoA indisponível ou falhar.
        # Story 138+140 — try/except/finally garante que o breaker e o DEGRADED_MODE
        # são atualizados MESMO quando Vision lança exceção (o `finally` sempre roda).
        # Story 151 — Benchmark Vision stage start

        # Story 174 — MekkaKernel pre-invocation hook (filter chain fires antes do Vision)
        try:
            from src.services.mekka_kernel import get_mekka_kernel as _get_kernel174
            _k174 = _get_kernel174()
            if _k174._filter_chain is not None:
                await _k174.invoke(
                    "vision", "generate_signal",
                    symbol=symbol,
                    cycle_id=str(_cycle_id),
                    model=settings.openai_model,
                )
        except Exception as _k174_exc:
            self._log.debug(f"[NickFury:174] kernel pre-vision hook skipped: {_k174_exc}")

        # Story 184 — TypedCycleMessage: emit ANALYSIS_DONE message antes de Vision.
        # MetaGPT Message pattern: cause_by=ANALYSIS_DONE, send_to=Vision.
        # Torna o pipeline introspectável — qualquer observer vê o roteamento.
        # Fails silently — pipeline não depende desta emissão.
        try:
            from src.models.cycle_message import CycleMessage as _CM184  # noqa: WPS433
            _msg184 = _CM184.from_analysis(
                symbol=symbol,
                analysis=analysis,
                cycle_id=str(_cycle_id),
            )
            self._log.debug(_msg184.to_log_line())
        except Exception as _cm184_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:184] TypedCycleMessage ANALYSIS_DONE skipped: {_cm184_exc}")

        # Story 187 — IncrementalCycleSkip: skip Vision LLM call se nada material mudou.
        # MetaGPT Incremental Development: compara estado atual com checkpoint anterior;
        # se preço/regime estáveis dentro dos thresholds → reusa último sinal.
        # Económico: evita LLM call quando mercado está flat.
        # Fails silently — executa Vision normalmente se guard indisponível.
        _incremental_skipped = False
        _incremental_last_signal = None
        try:
            from src.services.cycle_incremental_guard import get_cycle_incremental_guard  # noqa: WPS433
            _ig187 = get_cycle_incremental_guard()
            _price187 = float(analysis.price) if analysis and analysis.price else 0.0
            _regime187_str = ""
            try:
                _meta187 = getattr(analysis, "signal_metadata", None) or {}
                _regime187_str = _meta187.get("market_regime", "UNKNOWN")
            except Exception:  # noqa: BLE001
                _regime187_str = "UNKNOWN"
            _skip187, _skip_reason = _ig187.should_skip(
                symbol, current_price=_price187, current_regime=_regime187_str
            )
            if _skip187:
                _incremental_last_signal = _ig187.get_last_signal(symbol)
                if _incremental_last_signal is not None:
                    _incremental_skipped = True
                    _ig187.register_skip(symbol)
                    self._log.debug(f"[NickFury:187] IncrementalCycleSkip → {_skip_reason}")
        except Exception as _ig187_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:187] IncrementalCycleSkip check skipped: {_ig187_exc}")

        # Story 251 — tenta restaurar sinal do checkpoint antes de chamar Vision.
        _signal251_restored = False
        _signal251_cached: Any = None
        if _cp251 is not None:
            try:
                _cp251_signal_data = await _cp251.load(str(_cycle_id), symbol, "SIGNAL")
                if _cp251_signal_data:
                    from src.models.signal import TradingSignal as _TS251  # noqa: WPS433
                    _signal251_cached = _TS251(**_cp251_signal_data)
                    _signal251_restored = True
                    logger.debug(
                        f"[NickFury:251] {symbol} SIGNAL restored from checkpoint "
                        f"(cycle={_cycle_id})"
                    )
            except Exception as _cp251_sig_load_exc:  # noqa: BLE001
                logger.debug(f"[NickFury:251] SIGNAL checkpoint load skipped: {_cp251_sig_load_exc}")

        _vision_stage_start = __import__("time").monotonic()
        _vision_error = False
        try:
            if _signal251_restored and _signal251_cached is not None:
                # Story 251 — reutiliza sinal restaurado do checkpoint (Vision já rodou)
                signal = _signal251_cached
            elif _budget_skipped:
                # Story 189 — CycleBudgetGuard: força HOLD sem LLM call
                from src.models.signal import TradingSignal  # noqa: WPS433
                signal = TradingSignal(
                    action=TradeAction.HOLD,
                    confidence=0.0,
                    reasoning="Budget limit exceeded — Vision skipped (Story 189)",
                )
            elif _incremental_skipped and _incremental_last_signal is not None:
                # Story 187 — reutiliza sinal anterior (IncrementalCycleSkip)
                signal = _incremental_last_signal
            elif self._vision_moa is not None:
                try:
                    signal = await self._vision_moa.run(analysis=analysis)
                except Exception as _moa_run_exc:  # noqa: BLE001
                    self._log.warning(
                        f"[NickFury] VisionMoA.run() failed: {_moa_run_exc} — "
                        "falling back to single Vision"
                    )
                    signal = await self._vision.run(analysis=analysis)
            else:
                signal = await self._vision.run(analysis=analysis)
        except Exception:
            _vision_error = True
            raise
        finally:
            # Story 138 — observe LLM result in sliding-window breaker.
            # Runs regardless of success/failure so the window is always correct.
            self._llm_error_breaker.observe(_vision_error)
            # Story 140 — update DEGRADED_MODE state based on this observation.
            try:
                if _vision_error and self._llm_error_breaker.is_tripped:
                    # LLM error rate crossed threshold → enter DEGRADED_MODE
                    _was_new_degradation = self._degraded_mode.trigger(
                        f"LLM error rate {self._llm_error_breaker.error_rate:.1%} "
                        f">= {settings.llm_error_rate_threshold:.1%}"
                    )
                    if _was_new_degradation:
                        logger.warning(
                            f"[NickFury] {symbol} DEGRADED_MODE triggered — "
                            f"{self._degraded_mode.summary()}"
                        )
                        await _emit("system.degraded", {
                            "cycle_id": _cycle_id, "symbol": symbol,
                            "reason": self._degraded_mode.reason,
                            "trigger_count": self._degraded_mode.trigger_count,
                        })
                elif not _vision_error and self._degraded_mode.is_degraded:
                    # Successful Vision call while degraded → count toward recovery
                    _now_recovered = self._degraded_mode.observe_success()
                    if _now_recovered:
                        logger.info(
                            f"[NickFury] {symbol} DEGRADED_MODE → RECOVERED — "
                            f"{self._degraded_mode.summary()}"
                        )
                        await _emit("system.recovered", {
                            "cycle_id": _cycle_id, "symbol": symbol,
                            "trigger_count": self._degraded_mode.trigger_count,
                        })
            except Exception as _dmode_exc:  # noqa: BLE001
                logger.debug(f"[NickFury] DEGRADED_MODE state update failed: {_dmode_exc}")
            # Story 151 — Record Vision stage elapsed
            if _bench_token is not None:
                _bench_token.stages["vision"] = __import__("time").monotonic() - _vision_stage_start

        # Story 251 — salva checkpoint SIGNAL após Vision concluir (apenas se rodou normalmente).
        # Não salva quando: sinal foi restaurado, budget skipped, incremental skipped, ou erro.
        if (
            _cp251 is not None
            and not _signal251_restored
            and not _budget_skipped
            and not (_incremental_skipped and _incremental_last_signal is not None)
            and not _vision_error
        ):
            try:
                _signal_payload: dict = {}
                if hasattr(signal, "model_dump"):
                    _signal_payload = signal.model_dump()
                elif hasattr(signal, "dict"):
                    _signal_payload = signal.dict()  # type: ignore[attr-defined]
                if _signal_payload:
                    await _cp251.save(str(_cycle_id), symbol, "SIGNAL", _signal_payload)
            except Exception as _cp251_sig_save_exc:  # noqa: BLE001
                logger.debug(f"[NickFury:251] SIGNAL checkpoint save skipped: {_cp251_sig_save_exc}")

        # 2b. Vision Reflection Loop — Story 130 (supersedes Story 031 one-shot).
        # Iterative Vision↔VisionCritic loop (AutoGen Reflection pattern).
        # Converges early on ENDORSE; max_rounds cap prevents infinite LLM cost.
        # When vision_reflection_max_rounds=1, behavior is identical to Story 031.
        # Fails silently — the initial signal stands on any error.
        if settings.vision_critic_enabled:
            try:
                signal, _reflection_rounds = await self._vision_reflection_loop(
                    analysis=analysis,
                    initial_signal=signal,
                    symbol=symbol,
                )
                if _reflection_rounds > 1:
                    self._log.info(
                        f"[NickFury] {symbol} reflection used {_reflection_rounds} rounds"
                    )
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"[NickFury] reflection loop failed: {exc}")

        # Story 188 — CycleTrajectory: record VISION_SIGNAL step.
        # Fail-silent.
        try:
            from src.services.cycle_trajectory import get_trajectory_store as _get_traj188b  # noqa: WPS433
            _sig_summary = ""
            try:
                _sig_summary = f"action={signal.action.value} conf={signal.confidence:.0%}"
            except Exception:  # noqa: BLE001
                pass
            _skip_tag = "(incremental)" if _incremental_skipped else ("(budget_hold)" if _budget_skipped else "")
            _get_traj188b().record_step(
                str(_cycle_id), stage="VISION_SIGNAL",
                input_summary=f"regime={_regime187_str if '_regime187_str' in dir() else '?'}",
                output_summary=_sig_summary,
                ok=not _budget_skipped,
                observation=_skip_tag,
            )
            # Registra custo da chamada Vision (se não foi skipped)
            if not _incremental_skipped and not _budget_skipped:
                from src.services.cycle_budget_guard import get_cycle_budget_guard  # noqa: WPS433
                get_cycle_budget_guard().record_cost(symbol, estimated_cost_usd=0.002, cycle_id=str(_cycle_id))
        except Exception as _t188b_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:188] CycleTrajectory VISION_SIGNAL skipped: {_t188b_exc}")

        # Story 187 — IncrementalCycleGuard: update checkpoint após Vision completar.
        # Deve rodar SEMPRE que Vision executou normalmente (não skipped) para que
        # o próximo ciclo tenha dados frescos para decidir se pode skipar.
        # Fail-silent: erro no update não afeta o pipeline.
        if not _incremental_skipped:
            try:
                from src.services.cycle_incremental_guard import get_cycle_incremental_guard  # noqa: WPS433
                _price_up187 = float(analysis.price) if analysis and analysis.price else 0.0
                _meta_up187 = getattr(analysis, "signal_metadata", None) or {}
                _regime_up187 = _meta_up187.get("market_regime", "UNKNOWN")
                get_cycle_incremental_guard().update(
                    symbol=symbol,
                    price=_price_up187,
                    regime=_regime_up187,
                    signal=signal,
                )
            except Exception as _up187_exc:  # noqa: BLE001
                self._log.debug(f"[NickFury:187] IncrementalCycleGuard.update skipped: {_up187_exc}")

        # Story 184 — TypedCycleMessage: emit SIGNAL_EMITTED após Vision completar.
        # MetaGPT Message pattern: cause_by=SIGNAL_EMITTED, send_to=Batman.
        # Fail-silent.
        try:
            from src.models.cycle_message import CycleMessage as _CM184b  # noqa: WPS433
            _msg184b = _CM184b.from_signal(
                symbol=symbol,
                signal=signal,
                cycle_id=str(_cycle_id),
            )
            self._log.debug(_msg184b.to_log_line())
        except Exception as _cm184b_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:184] TypedCycleMessage SIGNAL_EMITTED skipped: {_cm184b_exc}")

        # Story 179 — AutoSignalLinter: auto-fix geometria do sinal (Aider auto-lint pattern).
        # Diferente do SignalValidator (Story 168) que *bloqueia*, o linter *corrige*:
        # clamp confidence, swap SL/TP invertidos, fix entry_price <= 0, clamp leverage.
        # Executado ANTES do StepGuard para que o hash de comparação use o sinal corrigido.
        # Fail-silent: qualquer erro → sinal original preservado.
        _lint_result_191 = None
        try:
            from src.services.auto_signal_linter import get_auto_signal_linter  # noqa: WPS433
            _lint_price = float(analysis.price) if analysis and analysis.price else None
            _linter = get_auto_signal_linter()
            signal = _linter.lint_and_log(signal, last_price=_lint_price, symbol=symbol)
            # Captura o LintResult para o ObservationFeedbackLoop (Story 191)
            _lint_result_191 = getattr(_linter, "_last_result", None)
        except Exception as _lint179_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:179] AutoSignalLinter skipped: {_lint179_exc}")

        # Story 191 — ObservationFeedbackLoop: record lint corrections for next Vision cycle.
        # SWE-agent ACI guardrails: linter output fed back as observation for next turn.
        # Here: if signal had geometry fixes, record them so Vision sees them next cycle.
        # Fail-silent.
        try:
            if _lint_result_191 is not None:
                _was_fixed = getattr(_lint_result_191, "was_fixed", False)
                if _was_fixed:
                    from src.services.observation_feedback_loop import get_observation_feedback_loop  # noqa: WPS433
                    _obs_count = get_observation_feedback_loop().record_from_lint_result(
                        symbol=symbol,
                        lint_result=_lint_result_191,
                        cycle_id=str(_cycle_id),
                    )
                    self._log.debug(f"[NickFury:191] ObservationFeedbackLoop: {_obs_count} obs recorded for {symbol}")
        except Exception as _obs191_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:191] ObservationFeedbackLoop record skipped: {_obs191_exc}")

        # Story 166 — StepGuard check after Vision
        if _guard_check("Vision.run", f"{signal.action.value}:{round(signal.confidence, 2)}"):
            return CycleReport(symbol=symbol, error="AgentStepGuard: Vision stuck/max-iterations")

        signal_id = await MekkaRepository.save_signal(signal)

        # Story 198 — CycleConversationMemory: registra par user/assistant deste ciclo.
        # OpenHands ConversationMemory: centraliza histórico de janela de contexto por símbolo.
        # Fails silently.
        try:
            if _conv_mem198 is not None:
                _user_prompt_198 = str(getattr(analysis, "summary", "") or symbol)
                _asst_reply_198 = f"{signal.action.value}:{round(signal.confidence, 3)}"
                _conv_mem198.add_turn(
                    symbol=symbol,
                    cycle_id=str(_cycle_id),
                    user_prompt=_user_prompt_198,
                    assistant_reply=_asst_reply_198,
                )
        except Exception as _e198b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:198] ConversationMemory add_turn skipped: {_e198b_exc}")

        # Story 136 — Publish vision.signal event
        await _emit("vision.signal", {
            "cycle_id": _cycle_id, "symbol": symbol,
            "action": signal.action.value, "confidence": signal.confidence,
            "signal_id": signal_id,
        })

        # Story 063 — Episodic Memory: record actionable signals so Batman/Vision
        # can query historical win-rates for similar patterns in future cycles.
        # Only record LONG/SHORT (not HOLD). Fails silently — never breaks cycle.
        if signal.action != TradeAction.HOLD and signal.is_actionable:
            try:
                from src.persistence.agent_memory import AgentMemoryStore as _AMS  # noqa: WPS433
                _chart = analysis.chart if analysis else None
                _rsi = _chart.rsi_14 if _chart else None
                _trend = _chart.trend.value if _chart else "NEUTRAL"
                _vol_elev = bool(_chart.volume_spike) if _chart else False
                # Cache RSI + trend into signal metadata so Batman can re-read them
                if signal.metadata is None:
                    signal = signal.model_copy(update={"metadata": {}})
                _meta_update = dict(signal.metadata)
                _meta_update.update({
                    "rsi": round(_rsi, 1) if _rsi is not None else None,
                    "trend": _trend,
                })
                signal = signal.model_copy(update={"metadata": _meta_update})
                await _AMS.record_signal(
                    symbol=symbol,
                    action=signal.action.value,
                    rsi=_rsi,
                    trend=_trend,
                    volume_elevated=_vol_elev,
                    confidence=signal.confidence,
                    signal_id=signal_id,
                )
            except Exception as _mem_exc:  # noqa: BLE001
                self._log.debug(f"[NickFury] Episodic memory record skipped: {_mem_exc}")

        # Story 163 — Signal Metadata Pipeline: auto-inject market_regime + cap_tier
        # before Batman so gates 5b/5c work without manual metadata population.
        # Reads chart data (already in memory) + AssetClassifier (stateless, no I/O).
        # Fails silently — Batman's gates fall open when metadata is absent.
        try:
            from src.services.asset_classifier import (  # noqa: WPS433
                AssetClassifier as _AC,
                MarketRegimeDetector as _MRD,
            )
            _chart163 = analysis.chart if analysis else None
            _btc_trend = _chart163.trend.value if _chart163 else "NEUTRAL"
            _btc_rsi = float(_chart163.rsi_14) if _chart163 and _chart163.rsi_14 is not None else 50.0
            _btc_atr_pct = float(_chart163.atr_pct) if _chart163 and hasattr(_chart163, "atr_pct") and _chart163.atr_pct is not None else 0.02

            _regime_result = _MRD().detect(
                btc_trend=_btc_trend,
                btc_rsi=_btc_rsi,
                btc_atr_pct=_btc_atr_pct,
            )
            _cap_tier_result = _AC().cap_tier(symbol=symbol)

            # Ensure metadata dict exists
            if signal.metadata is None:
                signal = signal.model_copy(update={"metadata": {}})
            _m163 = dict(signal.metadata)
            # Only set if not already provided (preserve manual overrides)
            _m163.setdefault("market_regime", _regime_result.regime.value)
            _m163.setdefault("cap_tier", _cap_tier_result.value)
            signal = signal.model_copy(update={"metadata": _m163})
            self._log.debug(
                f"[NickFury:163] {symbol} metadata → "
                f"regime={_m163['market_regime']} cap={_m163['cap_tier']}"
            )
        except Exception as _meta163_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:163] metadata pipeline skipped: {_meta163_exc}")

        # Story 165 — SIGNAL_EMITTED
        _cel_emit(
            _CET.SIGNAL_EMITTED if _cel else None,
            action=signal.action.value,
            confidence=signal.confidence,
            entry_price=signal.entry_price,
            signal_id=getattr(signal, "id", None),
        )

        # Story 167 — SignalChangeLog: diff between this signal and previous cycle's signal.
        # Records structured SEARCH/REPLACE diff in the rolling window per symbol.
        # Alerts via Telegram when action flips (LONG→SHORT or vice-versa).
        # Fails silently — never breaks the trading cycle.
        try:
            from src.services.signal_changelog import get_signal_changelog  # noqa: WPS433
            _scl = get_signal_changelog()
            _prev_signal = None
            _prev_records = _scl.get_recent(symbol=symbol, n=1)
            if _prev_records:
                # Reconstruct a duck-typed prev signal from the last ChangeRecord
                _prev_record = _prev_records[-1]
                # get_last_change gives us the ChangeRecord but not the raw signal;
                # we record this signal now and compare on the next cycle.
            _change_record = _scl.record(
                symbol=symbol,
                prev=None,        # first cycle: all-new
                curr=signal,
                curr_cycle_id=_cycle_id,
            )
            # On action flip (LONG↔SHORT): log prominently + push Telegram alert
            if _change_record.has_action_change:
                _commit_msg = _change_record.commit_message()
                self._log.info(f"[NickFury:167] ACTION FLIP {symbol}: {_commit_msg}")
                await MekkaRepository.log_event(
                    agent="NickFury",
                    event="SIGNAL_FLIP",
                    severity="WARNING",
                    symbol=symbol,
                    message=_commit_msg,
                    payload=_change_record.to_dict(),
                )
                try:
                    await self._telegram.alert(
                        event="SIGNAL_FLIP",
                        severity="WARNING",
                        agent="Vision",
                        symbol=symbol,
                        message=_commit_msg,
                        payload={"diff": _change_record.to_search_replace_block()[:500]},
                    )
                except Exception:  # noqa: BLE001
                    pass
            else:
                self._log.debug(
                    f"[NickFury:167] {symbol} changelog: "
                    f"{_change_record.to_audit_line()}"
                )
        except Exception as _scl_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:167] SignalChangeLog skipped: {_scl_exc}")

        # Story 167 — ContextWindowTracker: record Vision prompt stage token usage.
        # Estimates tokens used by the analysis prompt for this cycle.
        # Fails silently.
        try:
            from src.services.context_window_tracker import get_context_window_tracker  # noqa: WPS433
            _cwt = get_context_window_tracker()
            _cwt.start_cycle(
                cycle_id=_cycle_id,
                symbol=symbol,
                model=settings.openai_model,
            )
            # Record analysis prompt (already converted to string by analysis.to_prompt())
            _analysis_prompt_approx = str(analysis) if analysis else ""
            _cwt.record_stage(
                cycle_id=_cycle_id,
                stage_name="vision_analysis_prompt",
                content=_analysis_prompt_approx,
                model=settings.openai_model,
                symbol=symbol,
            )
            # Record signal output
            _cwt.record_stage(
                cycle_id=_cycle_id,
                stage_name="vision_signal_output",
                content=signal.reasoning or "",
                model=settings.openai_model,
                symbol=symbol,
            )
            _is_near = _cwt.check_limit(cycle_id=_cycle_id)
            if _is_near:
                self._log.warning(
                    f"[NickFury:167] {symbol} context window near limit — "
                    f"{_cwt.cycle_summary(_cycle_id).get('usage_pct', 0):.1%}"
                )
        except Exception as _cwt_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:167] ContextWindowTracker skipped: {_cwt_exc}")

        # Story 168 — SignalValidator: linter-on-edit pré-Batman (SWE-agent pattern).
        # Validates signal geometry, R:R, confidence, total risk before Batman runs.
        # Hard block on errors; warnings are logged but cycle continues.
        # Fail-open: any internal exception → validator skipped, Batman runs normally.
        try:
            from src.services.signal_validator import get_signal_validator  # noqa: WPS433
            _sv_result = get_signal_validator().validate(signal)
            if not _sv_result.is_valid:
                self._log.warning(
                    f"[NickFury:168] {symbol} signal validation FAILED — "
                    f"{_sv_result.error_summary}"
                )
                _cel_emit(_CET.RISK_VERDICT if _cel else None,
                          verdict="VALIDATOR_BLOCKED", approved=False,
                          reasons=[_sv_result.error_summary])
                await MekkaRepository.log_event(
                    agent="SignalValidator",
                    event="SIGNAL_INVALID",
                    severity="WARNING",
                    symbol=symbol,
                    message=_sv_result.error_summary,
                    payload=_sv_result.to_dict(),
                )
                # Story 176 — Telegram alert quando sinal inválido
                try:
                    _sv_action = signal.action.value if signal and signal.action else "UNKNOWN"
                    _sv_conf = f"{signal.confidence:.0%}" if signal and signal.confidence else "?"
                    await self._telegram.alert(
                        event="SIGNAL_INVALID",
                        symbol=symbol,
                        message=(
                            f"⚠️ *SignalValidator bloqueou sinal* [{symbol}]\n"
                            f"Action: `{_sv_action}` | Confiança: `{_sv_conf}`\n"
                            f"Motivo: {_sv_result.error_summary}"
                        ),
                    )
                except Exception as _sv176_exc:
                    self._log.debug(f"[NickFury:176] Telegram SIGNAL_INVALID skipped: {_sv176_exc}")
                return CycleReport(
                    symbol=symbol,
                    signal=signal,
                    error=f"SignalValidator: {_sv_result.error_summary}",
                )
            if _sv_result.has_warnings:
                self._log.debug(
                    f"[NickFury:168] {symbol} signal warnings: "
                    + "; ".join(_sv_result.warnings)
                )
        except Exception as _sv_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:168] SignalValidator skipped: {_sv_exc}")

        # Story 195 — transition: SIGNALING → LINTING → RISK_CHECK (antes do Batman)
        try:
            if _state195 is not None:
                _state195.transition(symbol, _CAS.LINTING, cycle_id=str(_cycle_id))
                _state195.transition(symbol, _CAS.RISK_CHECK, cycle_id=str(_cycle_id))
        except Exception as _s195c_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:195] state RISK_CHECK transition skipped: {_s195c_exc}")

        # Story 196 — tag SIGNAL_EMITTED with source=VISION
        try:
            if _tagger196 is not None:
                _tagger196.tag(
                    event_type="SIGNAL_EMITTED", symbol=symbol,
                    cycle_id=str(_cycle_id), source=_CES.VISION,
                    payload={
                        "action": signal.action.value,
                        "confidence": round(signal.confidence, 3),
                    },
                )
        except Exception as _t196b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:196] source tag SIGNAL_EMITTED skipped: {_t196b_exc}")

        # Story 197 — add SIGNAL_EMITTED to exporter batch
        try:
            if _exporter197 is not None:
                _exporter197.add({
                    "event_type": "SIGNAL_EMITTED", "symbol": symbol,
                    "cycle_id": str(_cycle_id), "source": "VISION",
                    "action": signal.action.value,
                    "confidence": round(signal.confidence, 3),
                })
        except Exception as _e197b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:197] batch SIGNAL_EMITTED skipped: {_e197b_exc}")

        # Story 200 — CycleArtifactStore: persiste REASONING do Vision para audit.
        # OpenHands InMemoryFileStore: put(path, content).
        # Fails silently.
        try:
            if _artifact_store200 is not None:
                _artifact_store200.put(
                    symbol=symbol,
                    cycle_id=str(_cycle_id),
                    artifact_type=_AT.REASONING,
                    content={
                        "action": signal.action.value,
                        "confidence": round(signal.confidence, 3),
                        "reasoning": getattr(signal, "reasoning", ""),
                    },
                )
        except Exception as _e200b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:200] ArtifactStore REASONING skipped: {_e200b_exc}")

        # Stories 208/209/210 — LangGraph: checkpointer pós-sinal + router condicional.
        # Salva estado do ciclo após Vision; roda router para logar próximo destino.
        # Fails silently.
        try:
            if _checkpointer210 is not None:
                _cp_state = {
                    "symbol": symbol,
                    "cycle_id": str(_cycle_id),
                    "signal": {
                        "action": signal.action.value,
                        "confidence": round(signal.confidence, 3),
                    },
                }
                _cp_id = _checkpointer210.save(str(_cycle_id), "vision", _cp_state)
                logger.debug(f"[NickFury:210] checkpoint saved: vision/{_cp_id}")
        except Exception as _e210b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:210] Checkpointer post-vision skipped: {_e210b_exc}")

        try:
            if _router209 is not None:
                _router_state = {
                    "signal": {
                        "action": signal.action.value,
                        "confidence": signal.confidence,
                    }
                }
                _next209 = _router209.route(_router_state)
                logger.debug(f"[NickFury:209] ConditionalRouter → {_next209} (action={signal.action.value})")
        except Exception as _e209b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:209] ConditionalRouter skipped: {_e209b_exc}")

        # Story 201 — CycleActionRiskAnalyzer: avalia risco antes do Batman gate.
        # OpenHands SecurityAnalyzer: classifica ação em LOW/MEDIUM/HIGH.
        # HIGH → loga aviso (bloquear via Batman é responsabilidade do risk gate).
        # Fails silently.
        try:
            if _risk_analyzer201 is not None:
                _regime_str = getattr(analysis, "regime", "UNKNOWN")
                if hasattr(_regime_str, "value"):
                    _regime_str = _regime_str.value
                _notional = float(getattr(signal, "position_size_usd", 0.0) or 0.0)
                _leverage = float(getattr(signal, "leverage", 1.0) or 1.0)
                _risk_assessment = _risk_analyzer201.analyze(
                    action_type=signal.action.value,
                    symbol=symbol,
                    notional=_notional,
                    leverage=_leverage,
                    regime=str(_regime_str),
                    confidence=signal.confidence,
                )
                if _risk_assessment.blocked:
                    logger.warning(
                        f"[NickFury:201] RiskAnalyzer HIGH block: {symbol} "
                        f"{signal.action.value} — {_risk_assessment.reason}"
                    )
        except Exception as _e201b_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:201] RiskAnalyzer skipped: {_e201b_exc}")

        # 3. Batman risk gate
        # Story 151 — Benchmark Batman stage
        _batman_stage_start = __import__("time").monotonic()
        approval = await self._batman.run(
            signal=signal,
            volatility=analysis.volatility,
            liquidity=analysis.liquidity,
            current_drawdown_pct=current_drawdown_pct,
            open_positions=open_positions,
            trades_today=trades_today,
            running_notional_usd=running_notional_usd,
            equity_usd=equity_usd,
            current_positions=current_positions or [],  # [Story 057] correlation gate
            analysis=analysis,  # [Story 247] Flash divergence gate 3r
        )

        # Story 151 — Record Batman stage elapsed
        if _bench_token is not None:
            _bench_token.stages["batman"] = __import__("time").monotonic() - _batman_stage_start

        await MekkaRepository.log_event(
            agent="Batman",
            event=f"RISK_{approval.verdict.value}",
            severity="INFO" if approval.is_executable else "WARNING",
            symbol=symbol,
            message=approval.summary(),
            payload={
                "reasons": approval.reasons,
                "breached": approval.breached_limits,
            },
        )

        # Story 165 — RISK_VERDICT
        _cel_emit(
            _CET.RISK_VERDICT if _cel else None,
            verdict=approval.verdict.value,
            approved=approval.is_executable,
            reasons=approval.reasons[:3] if approval.reasons else [],
        )

        # Story 166 — StepGuard check after Batman
        if _guard_check("Batman.run", approval.verdict.value):
            return CycleReport(symbol=symbol, error="AgentStepGuard: Batman stuck/max-iterations")

        # Story 136 — Publish batman.gate event
        await _emit("batman.gate", {
            "cycle_id": _cycle_id, "symbol": symbol,
            "verdict": approval.verdict.value, "approved": approval.is_executable,
            "reasons": approval.reasons,
        })
        # Story 035 — only KILL_SWITCH triggers a push by default
        if approval.verdict == RiskVerdict.KILL_SWITCH:
            await self._telegram.alert(
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                agent="Batman",
                symbol=symbol,
                message=approval.summary(),
                payload={"breached": approval.breached_limits},
            )

        if not approval.is_executable:
            return CycleReport(symbol=symbol, signal=signal, approval=approval)

        # ── Story 074 / Story 127 — Telegram Trade Approval ─────────────
        # Request operator confirmation via Telegram before IronMan executes.
        # Story 127 adds LangGraph interrupt() path when lg_thread_id is set.
        # Falls open: any non-BaseException error skips the gate and proceeds.
        if settings.telegram_trade_approval_enabled:
            try:
                import uuid as _uuid  # noqa: WPS433
                _trade_id = f"T-{_uuid.uuid4().hex[:10].upper()}"

                if lg_thread_id is not None:
                    # ── Story 127 — LangGraph interrupt path ──────────────
                    # Send approval message first (with lg_ buttons so
                    # TelegramInbound can route to the LangGraph resume path).
                    try:
                        from src.services.trade_approval import send_lg_approval_message as _send_lg  # noqa: WPS433
                        await _send_lg(
                            trade_id=_trade_id,
                            thread_id=lg_thread_id,
                            signal_symbol=symbol,
                            signal_action=signal.action.value,
                            signal_confidence=signal.confidence,
                            entry_price=signal.entry_price,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                            size_pct=approval.adjusted_size_pct,
                            leverage=approval.adjusted_leverage,
                            reasons=approval.reasons,
                            timeout_s=settings.telegram_trade_approval_timeout_s,
                        )
                    except Exception as _msg_exc:  # noqa: BLE001
                        self._log.warning("[NickFury:LG] Approval message failed (non-fatal): %s", _msg_exc)

                    # Suspend graph execution — NodeInterrupt (BaseException) propagates
                    # upward, bypassing the outer except Exception handler below.
                    # On resume via Command(resume=True/False), returns approved value.
                    from langgraph.types import interrupt as _lg_interrupt  # noqa: WPS433
                    _approved = _lg_interrupt({
                        "trade_id": _trade_id,
                        "thread_id": lg_thread_id,
                        "symbol": symbol,
                        "action": signal.action.value,
                        "confidence": signal.confidence,
                        "entry_price": signal.entry_price,
                    })
                else:
                    # ── Story 074 — Classic asyncio.Event path ────────────
                    from src.services.trade_approval import request_approval as _req_approval  # noqa: WPS433
                    _approved = await _req_approval(
                        trade_id=_trade_id,
                        signal_symbol=symbol,
                        signal_action=signal.action.value,
                        signal_confidence=signal.confidence,
                        entry_price=signal.entry_price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        size_pct=approval.adjusted_size_pct,
                        leverage=approval.adjusted_leverage,
                        reasons=approval.reasons,
                        timeout_s=settings.telegram_trade_approval_timeout_s,
                    )

                if not _approved:
                    await MekkaRepository.log_event(
                        agent="NickFury",
                        event="TRADE_APPROVAL_REJECTED",
                        severity="INFO",
                        symbol=symbol,
                        message=(
                            f"[074/127] Trade {_trade_id} rejected by operator "
                            f"(or timeout in live mode)"
                        ),
                        payload={"trade_id": _trade_id, "symbol": symbol, "action": signal.action.value},
                    )
                    return CycleReport(symbol=symbol, signal=signal, approval=approval)
            except Exception as _appr_exc:  # noqa: BLE001
                # Note: NodeInterrupt inherits from BaseException — NOT caught here.
                self._log.warning("[NickFury] Trade approval gate error (skipped): %s", _appr_exc)

        # 4. Iron Man execution
        execution = await self._ironman.run(
            signal=signal,
            approval=approval,
            equity_usd=equity_usd,
        )
        await MekkaRepository.save_trade(execution=execution, signal_id=signal_id)

        await MekkaRepository.log_event(
            agent="IronMan",
            event=f"EXEC_{execution.status.value}",
            severity="INFO" if execution.status in (
                ExecutionStatus.FILLED,
                ExecutionStatus.PARTIAL,
                ExecutionStatus.PAPER,
            ) else "WARNING",
            symbol=symbol,
            message=execution.summary(),
            payload={"is_paper": execution.is_paper},
        )
        # Story 035 — push on ERROR / REJECTED outcomes
        if execution.status in (ExecutionStatus.ERROR, ExecutionStatus.REJECTED):
            await self._telegram.alert(
                event=f"EXEC_{execution.status.value}",
                severity="ERROR",
                agent="IronMan",
                symbol=symbol,
                message=execution.summary(),
                payload={"error": execution.error or "", "is_paper": execution.is_paper},
            )
        # Rich trade-opened notification for every FILLED / PAPER execution
        elif execution.status in (ExecutionStatus.FILLED, ExecutionStatus.PAPER):
            await self._telegram.trade_opened(execution=execution, signal=signal)

        # Story 165 — EXECUTION_DONE
        _cel_emit(
            _CET.EXECUTION_DONE if _cel else None,
            status=execution.status.value,
            is_paper=execution.is_paper,
            order_id=getattr(execution, "order_id", None),
        )

        # Story 136 — Publish ironman.exec + cycle.end events
        await _emit("ironman.exec", {
            "cycle_id": _cycle_id, "symbol": symbol,
            "status": execution.status.value, "is_paper": execution.is_paper,
            "order_id": getattr(execution, "order_id", None),
        })
        _ts_end = datetime.now(timezone.utc).isoformat()
        await _emit("cycle.end", {
            "cycle_id": _cycle_id, "symbol": symbol,
            "timestamp": _ts_end, "outcome": execution.status.value,
        })

        # Story 165 — CYCLE_END
        _cel_emit(
            _CET.CYCLE_END if _cel else None,
            outcome=execution.status.value,
            timestamp=_ts_end,
        )

        # Story 195 — transition: EXECUTING → FINISHED
        try:
            if _state195 is not None:
                _state195.transition(symbol, _CAS.EXECUTING, cycle_id=str(_cycle_id))
                _state195.transition(symbol, _CAS.FINISHED, cycle_id=str(_cycle_id))
                _state195.transition(symbol, _CAS.IDLE, cycle_id=str(_cycle_id))  # ready for next cycle
        except Exception as _s195d_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:195] state FINISHED transition skipped: {_s195d_exc}")

        # Story 196 — tag CYCLE_END with source=NICKFURY
        try:
            if _tagger196 is not None:
                _tagger196.tag(
                    event_type="CYCLE_END", symbol=symbol,
                    cycle_id=str(_cycle_id), source=_CES.NICKFURY,
                    payload={"outcome": execution.status.value},
                )
        except Exception as _t196c_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:196] source tag CYCLE_END skipped: {_t196c_exc}")

        # Story 197 — add CYCLE_END to batch + flush se batch cheio
        try:
            if _exporter197 is not None:
                _exporter197.add({
                    "event_type": "CYCLE_END", "symbol": symbol,
                    "cycle_id": str(_cycle_id), "source": "NICKFURY",
                    "outcome": execution.status.value,
                })
                _exporter197.maybe_flush()  # flush automático se batch_size atingido
        except Exception as _e197c_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:197] batch/flush CYCLE_END skipped: {_e197c_exc}")

        # Story 200 — CycleArtifactStore: persiste artefatos do ciclo para audit trail.
        # OpenHands InMemoryFileStore: put(path, content) com path canônico.
        # Fails silently.
        try:
            if _artifact_store200 is not None:
                _artifact_store200.put(
                    symbol=symbol,
                    cycle_id=str(_cycle_id),
                    artifact_type=_AT.SIGNAL,
                    content={
                        "action": signal.action.value if signal else "HOLD",
                        "confidence": getattr(signal, "confidence", 0.0),
                        "outcome": execution.status.value,
                    },
                    metadata={"source": "NICKFURY", "milestone": "31"},
                )
        except Exception as _e200c_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:200] ArtifactStore CYCLE_END skipped: {_e200c_exc}")

        # Story 202 — CycleStateResetter: CYCLE_END flush + cleanup.
        # OpenHands AgentController.reset(): flush batch + prepare for next cycle.
        # Fails silently.
        try:
            if _resetter202 is not None:
                _resetter202.reset(_RS.CYCLE_END, symbol=symbol, cycle_id=str(_cycle_id))
        except Exception as _e202c_exc:  # noqa: BLE001
            logger.debug(f"[NickFury:202] CycleStateResetter CYCLE_END skipped: {_e202c_exc}")

        # Story 151 — Close benchmark measurement for this full cycle
        try:
            if _bench is not None and _bench_token is not None:
                _bench.end_cycle(_bench_token)
        except Exception as _bench_end_exc:  # noqa: BLE001
            logger.debug(f"[NickFury] PipelineBenchmark end_cycle skipped: {_bench_end_exc}")

        return CycleReport(
            symbol=symbol,
            signal=signal,
            approval=approval,
            execution=execution,
        )

    # ------------------------------------------------------------------
    # Story 130 — Vision Reflection Loop (AutoGen Reflection pattern)
    # ------------------------------------------------------------------

    async def _vision_reflection_loop(
        self,
        analysis: "MarketAnalysis",  # type: ignore[name-defined]
        initial_signal: TradingSignal,
        symbol: str,
    ) -> tuple[TradingSignal, int]:
        """
        Iterative Vision↔VisionCritic reflection loop.

        Inspired by AutoGen's Reflection pattern (Coder↔Reviewer):
          Round 1: VisionCritic evaluates the initial Vision signal.
          Round 2+: If critic returns AMEND/REJECT, Vision revises its
            signal with the critique appended to the context.
          Early exit: loop breaks as soon as critic returns ENDORSE.
          Last round: applies the critique mechanically via apply_critique()
            rather than calling Vision again (avoid infinite-cost spiral).

        Returns (final_signal, rounds_used). Never throws — always returns
        at minimum the initial_signal if all rounds fail.
        """
        from src.agents.vision_critic import apply_critique  # noqa: WPS433
        from src.models.critique import CritiqueAction  # noqa: WPS433
        from src.models.market_data import MarketAnalysis  # noqa: WPS433

        max_rounds = settings.vision_reflection_max_rounds
        signal = initial_signal

        for round_num in range(1, max_rounds + 1):
            try:
                critique = await self._vision_critic.run(
                    analysis=analysis,
                    signal=signal,
                )

                # Audit every round
                await MekkaRepository.log_event(
                    agent="VisionCritic",
                    event=f"REFLECTION_R{round_num}_{critique.action.value}",
                    severity="INFO",
                    symbol=symbol,
                    message=critique.summary(),
                    payload={
                        **critique.to_audit_payload(),
                        "reflection_round": round_num,
                        "max_rounds": max_rounds,
                    },
                )

                # Converged — critic is satisfied, exit early
                if critique.action == CritiqueAction.ENDORSE:
                    self._log.info(
                        f"[Reflection] {symbol} converged at round {round_num} "
                        f"(ENDORSE delta={critique.confidence_delta:.2f})"
                    )
                    break

                # Last round — apply critique mechanically, no more LLM calls
                if round_num == max_rounds:
                    if critique.is_actionable():
                        signal = apply_critique(signal=signal, critique=critique)
                    self._log.info(
                        f"[Reflection] {symbol} max_rounds={max_rounds} reached, "
                        f"critique applied mechanically"
                    )
                    break

                # Round N < max_rounds — give Vision a chance to revise
                critique_context = (
                    f"=== Vision Critic Feedback (Round {round_num} of {max_rounds}) ===\n"
                    f"Verdict    : {critique.action.value}\n"
                    f"Delta      : {critique.confidence_delta:.2f}\n"
                    f"Reasoning  : {critique.reasoning}\n\n"
                    "Revise your trading signal taking this feedback into account. "
                    "Keep your best judgment — only change if the critique is valid. "
                    "Output a single JSON object (same schema as before)."
                )
                revised = await self._vision.revise(
                    analysis=analysis,
                    critique_context=critique_context,
                    round_num=round_num,
                )
                signal = revised

            except Exception as exc:  # noqa: BLE001
                # Critic or Vision revision must NEVER break the outer cycle.
                self._log.warning(
                    f"[Reflection] {symbol} round {round_num} failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                break  # fail-silent: use last known good signal

        return signal, round_num

    # ------------------------------------------------------------------
    # Monitoring & Alerting (Story 218 — Milestone 34)
    # ------------------------------------------------------------------

    async def _run_pre_cycle_monitors(
        self,
        snapshot: EquitySnapshot,
        effective_equity: float,
    ) -> None:
        """
        Executa os 3 monitores de portfólio antes do loop de símbolos.

        Monitores:
          - DrawdownMonitor    (Story 213) — alerta em 50%/80%/100% do limite
          - PositionConcentrationAlerter (Story 214) — alerta por símbolo acima do limite
          - IntradayPnLTracker (Story 215) — snapshot horário + alertas em marcos

        FundingRateMonitor (Story 216) é chamado dentro de _cycle_for_symbol()
        pois precisa do MarketAnalysis (BlackPanther) por símbolo.

        AlertThrottleManager (Story 217) usado como gate antes de cada monitor.
        Cada chamada absorve exceções — nunca interrompe o ciclo principal.
        """
        # ── DrawdownMonitor ────────────────────────────────────────────
        try:
            _peak = getattr(self._daily_pnl, "_peak_equity", 0.0) or effective_equity
            _dd_key = "DRAWDOWN_CHECK"
            # Throttle: verificar a cada 5 minutos no máximo (300s)
            if self._throttle.is_allowed(_dd_key, cooldown_seconds=300.0):
                _dd_alert = await self._drawdown_monitor.check(
                    current_equity=effective_equity,
                    peak_equity=_peak,
                )
                self._throttle.record_sent(_dd_key)
                if _dd_alert is not None:
                    self._log.info(
                        f"[NickFury:213] DrawdownMonitor: {_dd_alert.level} "
                        f"{_dd_alert.drawdown_pct:.2f}%"
                    )
        except Exception as _dd218_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:218] DrawdownMonitor skipped: {_dd218_exc}")

        # ── PositionConcentrationAlerter ───────────────────────────────
        try:
            _positions = snapshot.positions or []
            if _positions and effective_equity > 0:
                _pos_dicts = [
                    {
                        "symbol": p.symbol,
                        "notional_usd": p.size * p.entry_price,
                        "side": getattr(p, "side", "UNKNOWN"),
                    }
                    for p in _positions
                ]
                _conc_alerts = await self._concentration_alerter.check(
                    positions=_pos_dicts,
                    equity_usd=effective_equity,
                )
                for _ca in _conc_alerts:
                    self._log.warning(
                        f"[NickFury:214] Concentração: {_ca.symbol} "
                        f"{_ca.concentration_pct:.1f}% > {_ca.limit_pct:.1f}%"
                    )
        except Exception as _conc218_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:218] ConcentrationAlerter skipped: {_conc218_exc}")

        # ── IntradayPnLTracker ─────────────────────────────────────────
        try:
            # PnL realizado vem do daily_pnl_writer; não-realizado do snapshot
            _realized = getattr(self._daily_pnl, "_realized_pnl_today", 0.0) or 0.0
            _unrealized = sum(
                getattr(p, "unrealized_pnl_usd", 0.0)
                for p in (snapshot.positions or [])
            )
            await self._pnl_tracker.record(
                realized_pnl=_realized,
                unrealized_pnl=_unrealized,
                equity_usd=effective_equity,
            )
        except Exception as _pnl218_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury:218] IntradayPnLTracker skipped: {_pnl218_exc}")

    # ------------------------------------------------------------------
    # Safety net (Story 029a)
    # ------------------------------------------------------------------

    async def _check_breakers(self, report: CycleReport) -> None:
        """
        Feed cycle outcome to the safety-net breakers and engage the kill
        switch if either trips. Called once per symbol after the cycle.
        """
        # 1. Iron Man consecutive ERROR breaker
        is_exec_error = (
            report.execution is not None
            and report.execution.status == ExecutionStatus.ERROR
        )
        if self._exec_error_breaker.observe(is_exec_error):
            reason = (
                f"{self._exec_error_breaker.threshold} consecutive Iron Man "
                f"ERROR executions — kill switch engaged"
            )
            engage_kill_switch(reason)
            await MekkaRepository.log_event(
                agent="NickFury",
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                symbol=report.symbol,
                message=reason,
                payload={"breaker": "exec_error", "trips_lifetime": self._exec_error_breaker.trip_count},
            )

        # 2. Vision consecutive HOLD-fallback breaker
        is_vision_fallback = (
            report.signal is not None
            and report.signal.action == TradeAction.HOLD
            and bool((report.signal.metadata or {}).get("fallback", False))
        )
        if self._vision_fallback_breaker.observe(is_vision_fallback):
            reason = (
                f"{self._vision_fallback_breaker.threshold} consecutive Vision "
                f"HOLD-fallbacks — LLM degraded, kill switch engaged"
            )
            engage_kill_switch(reason)
            await MekkaRepository.log_event(
                agent="NickFury",
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                symbol=report.symbol,
                message=reason,
                payload={"breaker": "vision_fallback", "trips_lifetime": self._vision_fallback_breaker.trip_count},
            )

    # ------------------------------------------------------------------
    # Market price helper (for Wolverine real-time drawdown)
    # ------------------------------------------------------------------

    async def _fetch_current_mids(self, symbols: list[str]) -> dict[str, float]:
        """
        Fetch last mid-prices for ``symbols`` from Hyperliquid public REST.
        Uses the ``/info`` endpoint (no auth required) so it works in both
        paper and live modes. Returns an empty dict on any failure — Wolverine
        degrades gracefully when prices are absent.
        """
        if not symbols:
            return {}
        try:
            import aiohttp  # noqa: WPS433
            url = settings.hyperliquid_base_url + "/info"
            payload = {"type": "allMids"}
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        return {}
                    data: dict = await resp.json()
            result: dict[str, float] = {}
            for sym in symbols:
                raw = data.get(sym) or data.get(f"{sym}-USD")
                if raw is not None:
                    try:
                        result[sym] = float(raw)
                    except (TypeError, ValueError):
                        pass
            return result
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                f"[NickFury] _fetch_current_mids failed (Wolverine will use entry_price): {exc}"
            )
            return {}

    # ------------------------------------------------------------------
    # Monitor cycle
    # ------------------------------------------------------------------

    async def run_monitor_cycle(self) -> dict:
        """
        Monitor cycle (Story 030). Reads current portfolio state via
        Portfolio Manager and lets Wolverine produce a RecoveryPlan.

        Wolverine is **read-only** on the exchange. The plan is logged
        to `audit_log` so the operator and the dashboard can see what
        Wolverine intended; actually modifying SL/TP on Hyperliquid is
        a future story (Iron Man integration).

        If the kill switch is already engaged, the cycle short-circuits.
        If Wolverine itself engages the kill switch (intraday drawdown
        breach), the audit event records that.
        """
        if is_kill_switch_active():
            return {"status": "halted", "reason": "kill_switch"}

        # Pull a fresh snapshot so Wolverine sees current positions.
        try:
            snapshot = await self._portfolio.run()
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[NickFury] monitor: portfolio.run failed: {exc}")
            await MekkaRepository.log_event(
                agent="NickFury",
                event="CYCLE_ERROR",
                severity="ERROR",
                message=f"monitor: portfolio.run failed: {exc}",
            )
            return {"status": "error", "reason": str(exc)}

        # [A1] Fetch real-time prices so Wolverine can compute actual
        # unrealized PnL for each open position (vs. always seeing 0).
        open_symbols = [p.symbol for p in (snapshot.positions or [])]
        current_prices = await self._fetch_current_mids(open_symbols)

        # Wolverine reasons over the snapshot with live prices.
        try:
            plan = await self._wolverine.run(
                snapshot=snapshot,
                current_prices=current_prices or None,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.exception(f"[NickFury] monitor: wolverine.run failed: {exc}")
            await MekkaRepository.log_event(
                agent="Wolverine",
                event="CYCLE_ERROR",
                severity="ERROR",
                message=f"wolverine.run failed: {exc}",
            )
            return {"status": "error", "reason": str(exc)}

        # Persist the plan as an audit event.
        await MekkaRepository.log_event(
            agent="Wolverine",
            event="MONITOR_RECOVERY_PLAN",
            severity="WARNING" if plan.kill_switch_engaged else "INFO",
            message=plan.summary(),
            payload=plan.to_audit_payload(),
        )
        # Stories 035 / 059 — rich Telegram alert when kill switch fires
        if plan.kill_switch_engaged:
            asyncio.create_task(self._telegram.wolverine_kill_switch(
                intraday_drawdown_pct=plan.intraday_drawdown_pct,
                positions_count=len(plan.positions),
                notes=plan.notes,
                is_paper=settings.paper_trading,
            ))

        # [C1] Execute actionable positions — Wolverine reasons, IronMan acts.
        actions_taken = 0
        if plan.needs_action:
            actions_taken = await self._execute_recovery_plan(plan, current_prices)

        # [C2] Run Cyclops — SL/TP monitor for paper positions
        cyclops_triggered = 0
        try:
            from src.agents.cyclops import Cyclops  # noqa: WPS433
            cyclops = Cyclops()
            cyclops_triggered = await cyclops.run(current_prices=current_prices)
        except Exception as _exc:
            self._log.warning(f"[NickFury] Cyclops skipped: {_exc}")

        # [C3] Live SL guardian — Cyclops is paper-only, so in live mode this is
        # the safety net that guarantees no open position is left without a
        # reduce-only stop on the venue (re-places a missing/cancelled stop and
        # alerts). No-op in paper mode and on Hyperliquid.
        sl_guardian: dict = {}
        if not settings.paper_trading:
            try:
                from src.agents.iron_man import IronMan  # noqa: WPS433
                sl_guardian = await IronMan().ensure_stops_for_open_positions()
                if sl_guardian.get("replaced") or sl_guardian.get("errors"):
                    await MekkaRepository.log_event(
                        agent="IronMan",
                        event="SL_GUARDIAN",
                        severity="WARNING",
                        message=(
                            f"SL guardian: checked={sl_guardian.get('checked')} "
                            f"protected={sl_guardian.get('protected')} "
                            f"replaced={len(sl_guardian.get('replaced') or [])} "
                            f"errors={len(sl_guardian.get('errors') or [])}"
                        ),
                        payload=sl_guardian,
                    )
            except Exception as _exc:  # noqa: BLE001
                self._log.warning(f"[NickFury] SL guardian skipped: {_exc}")

        return {
            "status": "halted" if plan.kill_switch_engaged else "ok",
            "positions_monitored": len(plan.positions),
            "intraday_drawdown_pct": plan.intraday_drawdown_pct,
            "kill_switch_engaged": plan.kill_switch_engaged,
            "recovery_actions_taken": actions_taken,
            "cyclops_triggered": cyclops_triggered,
            "sl_guardian": sl_guardian,
        }

    async def _execute_recovery_plan(
        self,
        plan: RecoveryPlan,
        current_prices: dict[str, float],
    ) -> int:
        """[C1] Execute actionable positions from a Wolverine RecoveryPlan.

        For CLOSE / EMERGENCY_CLOSE: create an offsetting paper trade that
        nets out the position. For SCALE_OUT: close 50% of the position.
        For TIGHTEN_STOP / TRAIL_STOP (Story 058): modify the stop-loss (and
        optionally take-profit) on the exchange (live) or in the DB (paper,
        so Cyclops honours the new price on the next monitor cycle).

        Returns the count of positions where an action was taken.
        """
        from src.models.recovery import RecoveryAction  # noqa: WPS433

        _SL_MODIFY_ACTIONS = {RecoveryAction.TIGHTEN_STOP, RecoveryAction.TRAIL_STOP}
        _ACTIONABLE = {
            RecoveryAction.CLOSE,
            RecoveryAction.EMERGENCY_CLOSE,
            RecoveryAction.SCALE_OUT,
            RecoveryAction.TIGHTEN_STOP,
            RecoveryAction.TRAIL_STOP,
        }
        actions_taken = 0

        for pos_update in plan.positions:
            if pos_update.action not in _ACTIONABLE:
                continue

            symbol = pos_update.symbol.upper()
            mark = (
                current_prices.get(symbol)
                or current_prices.get(symbol.upper())
                or pos_update.entry_price
            )

            # ----------------------------------------------------------------
            # [Story 058] TIGHTEN_STOP / TRAIL_STOP — modify SL/TP in place
            # ----------------------------------------------------------------
            if pos_update.action in _SL_MODIFY_ACTIONS:
                new_sl = pos_update.new_stop_loss
                new_tp = pos_update.new_take_profit

                if new_sl is None:
                    self._log.warning(
                        f"[Wolverine/C1] {pos_update.action.value} for {symbol}: "
                        "no new_stop_loss provided — skipping"
                    )
                    continue

                try:
                    if settings.paper_trading:
                        # Paper: update raw metadata so Cyclops uses the new SL
                        updated = await MekkaRepository.update_trade_sl_tp(
                            symbol=symbol, new_sl=new_sl, new_tp=new_tp
                        )
                        status_msg = f"paper_updated_{updated}_records"
                    else:
                        # Live: cancel old bracket orders and place new ones via IronMan
                        modify_result = await self._ironman.modify_sl_tp(
                            symbol=symbol,
                            side=pos_update.side,
                            quantity=pos_update.size,
                            new_sl=new_sl,
                            new_tp=new_tp,
                        )
                        status_msg = modify_result.get("status", "unknown")

                    await MekkaRepository.log_event(
                        agent="Wolverine",
                        event="SL_MODIFIED",
                        severity="INFO",
                        symbol=symbol,
                        message=(
                            f"[C1] {pos_update.action.value}: SL→{new_sl:,.4f} "
                            f"{'TP→' + f'{new_tp:,.4f}' if new_tp else ''} "
                            f"({pos_update.reason}) [{status_msg}]"
                        ),
                        payload={
                            "action": pos_update.action.value,
                            "symbol": symbol,
                            "new_sl": new_sl,
                            "new_tp": new_tp,
                            "reason": pos_update.reason,
                            "mark_price": mark,
                            "status": status_msg,
                        },
                    )
                    actions_taken += 1
                    self._log.info(
                        f"[Wolverine/C1] {pos_update.action.value} executed — "
                        f"{symbol} SL→{new_sl:,.4f}"
                        + (f" TP→{new_tp:,.4f}" if new_tp else "")
                    )
                    # [Story 059] Telegram alert
                    from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                    asyncio.create_task(TelegramAlerter().wolverine_action(
                        action=pos_update.action.value,
                        symbol=symbol,
                        side=pos_update.side,
                        entry_price=pos_update.entry_price,
                        mark_price=mark,
                        size=pos_update.size,
                        unrealized_pnl_usd=pos_update.unrealized_pnl_usd,
                        reason=pos_update.reason,
                        new_sl=new_sl,
                        new_tp=new_tp,
                        is_paper=settings.paper_trading,
                    ))
                except Exception as _exc:  # noqa: BLE001
                    self._log.error(
                        f"[Wolverine/C1] {pos_update.action.value} failed for {symbol}: {_exc}"
                    )
                continue  # don't fall through to the close/scale-out branch

            # Determine close quantity
            if pos_update.action == RecoveryAction.SCALE_OUT:
                close_qty = round(pos_update.size * 0.5, 8)  # close half
            else:
                close_qty = pos_update.size  # close all

            if close_qty < 1e-8:
                continue

            # Opposite side = close direction
            close_side = "short" if pos_update.side.lower() == "long" else "long"

            if settings.paper_trading:
                # Paper: insert offsetting trade directly
                import uuid  # noqa: WPS433
                from src.models.execution import ExecutionResult, ExecutionStatus  # noqa: WPS433

                close_result = ExecutionResult(
                    symbol=symbol,
                    status=ExecutionStatus.PAPER,
                    is_paper=True,
                    side=close_side,
                    quantity=close_qty,
                    avg_price=round(mark, 6),
                    notional_usd=round(close_qty * mark, 2),
                    order_id=f"WOLVERINE-CLOSE-{uuid.uuid4().hex[:10]}",
                    metadata={
                        "triggered_by": "wolverine",
                        "action": pos_update.action.value,
                        "reason": pos_update.reason,
                        "mark_price": mark,
                    },
                )
                try:
                    await MekkaRepository.save_trade(execution=close_result)
                    await MekkaRepository.log_event(
                        agent="Wolverine",
                        event="RECOVERY_ACTION_TAKEN",
                        severity="WARNING",
                        symbol=symbol,
                        message=(
                            f"[C1] {pos_update.action.value}: closed {close_qty:.6f} {symbol} "
                            f"@ {mark:,.4f} ({pos_update.reason})"
                        ),
                        payload={
                            "action": pos_update.action.value,
                            "symbol": symbol,
                            "close_qty": close_qty,
                            "close_price": mark,
                            "reason": pos_update.reason,
                        },
                    )
                    actions_taken += 1
                    self._log.warning(
                        f"[Wolverine/C1] {pos_update.action.value} executed — "
                        f"{close_qty:.6f} {symbol} @ {mark:,.4f}"
                    )
                    # [Story 059] Telegram alert
                    from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                    asyncio.create_task(TelegramAlerter().wolverine_action(
                        action=pos_update.action.value,
                        symbol=symbol,
                        side=pos_update.side,
                        entry_price=pos_update.entry_price,
                        mark_price=mark,
                        size=pos_update.size,
                        unrealized_pnl_usd=pos_update.unrealized_pnl_usd,
                        reason=pos_update.reason,
                        close_qty=close_qty,
                        is_paper=True,
                    ))
                except Exception as _exc:  # noqa: BLE001
                    self._log.error(f"[Wolverine/C1] save_trade failed for {symbol}: {_exc}")
            else:
                # Live: delegate to IronMan via a synthetic close signal
                try:
                    from src.models.signal import TradeAction, TradingSignal  # noqa: WPS433
                    from src.models.risk import RiskApproval, RiskVerdict  # noqa: WPS433

                    close_action = (
                        TradeAction.SHORT if pos_update.side.lower() == "long" else TradeAction.LONG
                    )
                    close_signal = TradingSignal(
                        symbol=symbol,
                        action=close_action,
                        confidence=1.0,
                        entry_price=mark,
                        stop_loss=mark * (0.99 if close_action == TradeAction.LONG else 1.01),
                        take_profit=mark * (1.01 if close_action == TradeAction.LONG else 0.99),
                        size_pct=0.0,
                        leverage=pos_update.leverage,
                        reasoning=f"Wolverine {pos_update.action.value}: {pos_update.reason}",
                    )
                    approval = RiskApproval(
                        verdict=RiskVerdict.APPROVED,
                        adjusted_size_pct=close_qty * mark / max(float(settings.paper_equity_usd), 1),
                        adjusted_leverage=pos_update.leverage,
                        reasons=["wolverine_recovery"],
                        breached_limits=[],
                    )
                    exec_result = await self._ironman.run(
                        signal=close_signal,
                        approval=approval,
                        equity_usd=float(settings.paper_equity_usd),
                    )
                    await MekkaRepository.save_trade(execution=exec_result)
                    actions_taken += 1
                    # [Story 059] Telegram alert
                    from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                    asyncio.create_task(TelegramAlerter().wolverine_action(
                        action=pos_update.action.value,
                        symbol=symbol,
                        side=pos_update.side,
                        entry_price=pos_update.entry_price,
                        mark_price=mark,
                        size=pos_update.size,
                        unrealized_pnl_usd=pos_update.unrealized_pnl_usd,
                        reason=pos_update.reason,
                        close_qty=close_qty,
                        is_paper=False,
                    ))
                except Exception as _exc:  # noqa: BLE001
                    self._log.error(
                        f"[Wolverine/C1] live close failed for {symbol}: {_exc}"
                    )

        return actions_taken


# ---------------------------------------------------------------------------
# Convenience: long-running scheduler loop
# ---------------------------------------------------------------------------


async def run_forever(equity_usd: Optional[float] = None) -> None:
    """
    Run main + monitor cycles forever using settings intervals.

    Wakes up every monitor_interval_seconds; runs main cycle every
    main_loop_interval_seconds (rounded to monitor ticks).

    `equity_usd` is an optional override (CLI `--equity`). When None,
    Portfolio Manager sources equity from Hyperliquid (or from the
    paper-fallback when credentials are missing).
    """
    fury = NickFury()
    await fury.initialize()

    monitor_interval = settings.monitor_interval_seconds
    main_interval = settings.main_loop_interval_seconds
    last_main_at = 0.0

    try:
        while True:
            now = asyncio.get_event_loop().time()
            if now - last_main_at >= main_interval:
                logger.info("[NickFury] Starting main cycle")
                await fury.run_main_cycle(equity_usd=equity_usd)
                last_main_at = now
            else:
                await fury.run_monitor_cycle()
            await asyncio.sleep(monitor_interval)
    except asyncio.CancelledError:
        logger.info("[NickFury] Loop cancelled — shutting down")
    finally:
        await fury.shutdown()

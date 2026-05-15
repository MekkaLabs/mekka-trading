"""
src/langgraph/cycle_graph.py
============================
Story 126 — LangGraph StateGraph com AsyncSqliteSaver envolvendo o ciclo NickFury.

Benefícios:
  - Durable execution: se Vision crashar no símbolo N, retoma do símbolo N
    (não do início do ciclo).
  - State inspection: o estado entre nós fica gravado no SQLite e pode ser
    inspecionado por Deadpool ou pelo dashboard.
  - Base para Story 127 (interrupt Telegram) e Story 129 (Layer 1 subgraph).

Arquitetura do grafo:
  START → preflight ─── (skip_reason?) ──> finalize → END
                     └── (normal) ──────> process_symbol ─┐
                                               ↑            │ (self-loop por símbolo)
                                               └────────────┘
                                               │ (symbols_remaining vazio)
                                               └──> finalize → END

Nota de design:
  - NickFury e seus agentes são capturados por CLOSURE — nunca ficam no estado.
  - Apenas tipos JSON-serializáveis fluem no MekkaCycleState.
  - O AsyncSqliteSaver cria suas próprias tabelas no mesmo DB SQLite
    (checkpoints, checkpoint_blobs, checkpoint_writes) — sem conflito com
    as tabelas de MekkaRepository.
  - Thread ID: UUID único por ciclo (sem auto-resume por ora — Story 127+).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from langgraph.graph import StateGraph, START, END

from src.langgraph.state import MekkaCycleState

if TYPE_CHECKING:
    # Evita import circular — NickFury importa cycle_graph, não vice-versa.
    from src.agents.nick_fury import NickFury


# ---------------------------------------------------------------------------
# Builder: recebe a instância de NickFury e devolve o grafo compilado
# ---------------------------------------------------------------------------

def build_cycle_graph(fury: "NickFury"):
    """
    Constrói o StateGraph que envolve o ciclo NickFury.

    Parâmetros:
        fury: Instância já inicializada de NickFury. Os agentes são
              capturados por closure nos nós — não armazenados no estado.

    Retorna:
        builder (StateGraph não compilado). O chamador é responsável por
        compilar com o checkpointer:
            graph = build_cycle_graph(fury).compile(checkpointer=saver)
    """

    # ------------------------------------------------------------------ #
    # Nó 1 — Preflight                                                    #
    # ------------------------------------------------------------------ #

    async def preflight_node(state: MekkaCycleState) -> dict:
        """
        Verificações pré-ciclo:
          - Kill switch
          - Drawdown diário ≥ cap → abort
          - Daily profit target atingido → abort
          - Busca equity (Portfolio Manager)
          - Valida símbolos na exchange
        """
        from src.agents.batman import is_kill_switch_active
        from src.config.settings import settings
        from src.config.runtime_mode import get_params as _gp
        from src.persistence.repository import MekkaRepository

        # ── Kill switch ──────────────────────────────────────────────────
        if is_kill_switch_active():
            logger.warning("[LG:preflight] Kill switch ACTIVE — ciclo abortado")
            await MekkaRepository.log_event(
                agent="NickFury",
                event="CYCLE_SKIPPED_LG",
                severity="WARNING",
                message="Kill switch active (LangGraph cycle)",
            )
            return {"skip_reason": "kill_switch"}

        # ── Drawdown diário ──────────────────────────────────────────────
        drawdown = await MekkaRepository.get_today_drawdown_pct()
        if drawdown >= settings.max_daily_drawdown_pct:
            logger.warning(
                f"[LG:preflight] Drawdown diário {drawdown*100:.2f}% ≥ cap "
                f"{settings.max_daily_drawdown_pct*100:.1f}% — ciclo abortado"
            )
            return {"skip_reason": f"daily_drawdown:{drawdown:.4f}", "drawdown_pct": drawdown}

        # ── Daily profit target ──────────────────────────────────────────
        try:
            today_pnl = await MekkaRepository.get_today_pnl_usd()
            eq = state["equity_usd"] or settings.paper_initial_equity
            if eq > 0 and (today_pnl / eq) >= settings.daily_profit_target_pct:
                logger.info("[LG:preflight] Daily profit target atingido — ciclo pausado")
                return {"skip_reason": "daily_profit_target_reached"}
        except Exception as _exc:
            logger.debug(f"[LG:preflight] Daily PnL gate skipped: {_exc}")

        # ── Portfolio snapshot ───────────────────────────────────────────
        snapshot = await fury._portfolio.run()
        effective_equity = (
            state["equity_usd"] if state["equity_usd"] > 0
            else snapshot.equity_usd
        )
        trades_today = await MekkaRepository.count_trades_today()
        running_notional = sum(
            p.size * p.entry_price for p in (snapshot.positions or [])
        )

        await MekkaRepository.log_event(
            agent="PortfolioManager",
            event=f"SNAPSHOT_{snapshot.source.value}_LG",
            severity="INFO",
            message=snapshot.summary(),
            payload={"equity_usd": snapshot.equity_usd},
        )

        # ── Validação de símbolos ────────────────────────────────────────
        assets = list(_gp().get("trading_assets", settings.trading_assets))
        try:
            assets = await fury._professor.validate_symbols(assets)
        except Exception as _exc:
            logger.warning(f"[LG:preflight] Symbol validation failed: {_exc}")

        logger.info(
            f"[LG:preflight] OK — equity=${effective_equity:,.2f} "
            f"symbols={assets} drawdown={drawdown*100:.2f}%"
        )
        return {
            "equity_usd": effective_equity,
            "symbols_remaining": assets,
            "drawdown_pct": drawdown,
            "trades_today": trades_today,
            "open_positions": snapshot.open_positions_count,
            "running_notional_usd": running_notional,
        }

    # ------------------------------------------------------------------ #
    # Nó 2 — Process Symbol (self-loop)                                  #
    # ------------------------------------------------------------------ #

    async def process_symbol_node(state: MekkaCycleState) -> dict:
        """
        Processa UM símbolo por invocação — o primeiro de symbols_remaining.
        LangGraph faz checkpoint após cada saída deste nó.
        Se crashar, retoma do início do nó com o mesmo símbolono topo da fila.
        """
        if not state["symbols_remaining"]:
            return {}  # guard: não deveria chegar aqui vazio

        symbol = state["symbols_remaining"][0]
        remaining = list(state["symbols_remaining"][1:])

        logger.info(
            f"[LG:process_symbol] {symbol} "
            f"({len(state['symbols_completed'])+1}/"
            f"{len(state['symbols_completed'])+len(state['symbols_remaining'])})"
        )

        try:
            report = await fury._cycle_for_symbol(
                symbol=symbol,
                equity_usd=state["equity_usd"],
                current_drawdown_pct=state["drawdown_pct"],
                trades_today=state["trades_today"],
                open_positions=state["open_positions"],
                running_notional_usd=state["running_notional_usd"],
                # Story 127: passa thread_id para que interrupt() inclua na payload
                # e TelegramInbound possa localizar o grafo pelo thread_id.
                # NodeInterrupt (BaseException) propagará naturalmente sem ser
                # capturado pelo except Exception abaixo.
                lg_thread_id=state["cycle_id"],
                # Story 129: Layer 1 subgraph para fan-out com checkpoints por agente.
                # None = fallback para ProfessorX.run() com asyncio.gather.
                layer1_graph=getattr(fury, "_layer1_graph", None),
            )

            # Observa safety-net breakers (Story 029a)
            try:
                await fury._check_breakers(report=report)
            except Exception as _exc:
                logger.debug(f"[LG:process_symbol] breaker check error: {_exc}")

            report_dict = report.model_dump(mode="json")
            executed = report.is_executed()
            new_trades = state["trades_today"] + (1 if executed else 0)
            new_positions = state["open_positions"] + (1 if executed else 0)
            new_notional = state["running_notional_usd"] + (
                report.execution.notional_usd
                if executed and report.execution
                else 0.0
            )

        except Exception as exc:
            from src.persistence.repository import MekkaRepository
            logger.exception(f"[LG:process_symbol] {symbol} crashed: {exc}")
            await MekkaRepository.log_event(
                agent="NickFury",
                event="CYCLE_ERROR_LG",
                severity="ERROR",
                symbol=symbol,
                message=str(exc),
            )
            try:
                await fury._telegram.alert(
                    event="CYCLE_ERROR",
                    severity="ERROR",
                    agent="NickFury",
                    symbol=symbol,
                    message=str(exc),
                )
            except Exception:
                pass
            report_dict = {"symbol": symbol, "error": str(exc)}
            new_trades = state["trades_today"]
            new_positions = state["open_positions"]
            new_notional = state["running_notional_usd"]

        return {
            "symbols_remaining": remaining,
            "symbols_completed": state["symbols_completed"] + [symbol],
            "reports": [report_dict],  # reducer Annotated[list, add] faz append
            "trades_today": new_trades,
            "open_positions": new_positions,
            "running_notional_usd": new_notional,
        }

    # ------------------------------------------------------------------ #
    # Nó 3 — Finalize                                                     #
    # ------------------------------------------------------------------ #

    async def finalize_node(state: MekkaCycleState) -> dict:
        """
        Fecha o ciclo: grava daily PnL, emite audit CYCLE_COMPLETE_LG,
        dispara DailyPerformanceWriter (fire-and-forget).
        """
        from src.persistence.repository import MekkaRepository
        import asyncio

        try:
            snapshot = await fury._portfolio.run()
            await fury._daily_pnl.record_cycle(
                equity_usd=state["equity_usd"],
                trades_count_today=state["trades_today"],
                snapshot=snapshot,
            )
        except Exception as exc:
            logger.error(f"[LG:finalize] daily_pnl record_cycle failed: {exc}")

        await MekkaRepository.log_event(
            agent="NickFury",
            event="CYCLE_COMPLETE_LG",
            severity="INFO",
            message=(
                f"[LangGraph] Ciclo {state['cycle_id']} completo: "
                f"{len(state['symbols_completed'])} símbolos, "
                f"{len(state['reports'])} reports"
                + (f" | skip: {state['skip_reason']}" if state.get("skip_reason") else "")
            ),
            payload={
                "cycle_id": state["cycle_id"],
                "symbols_completed": state["symbols_completed"],
                "reports_count": len(state["reports"]),
                "skip_reason": state.get("skip_reason"),
                "equity_usd": state["equity_usd"],
                "trades_today": state["trades_today"],
            },
        )

        # DailyPerformanceWriter (fire-and-forget — falha silenciosamente)
        try:
            asyncio.create_task(fury._perf_writer.maybe_run(), name="daily_perf_writer_lg")
        except Exception as exc:
            logger.debug(f"[LG:finalize] perf_writer task: {exc}")

        logger.info(
            f"[LG:finalize] Ciclo {state['cycle_id']} finalizado. "
            f"Símbolos: {state['symbols_completed']}"
        )
        return {}

    # ------------------------------------------------------------------ #
    # Roteamento condicional                                              #
    # ------------------------------------------------------------------ #

    def after_preflight(state: MekkaCycleState) -> str:
        """Vai para finalize se houve skip, senão processa o primeiro símbolo."""
        if state.get("skip_reason"):
            return "finalize"
        return "process_symbol"

    def after_process_symbol(state: MekkaCycleState) -> str:
        """Self-loop enquanto houver símbolos; vai para finalize quando acabar."""
        if state["symbols_remaining"]:
            return "process_symbol"
        return "finalize"

    # ------------------------------------------------------------------ #
    # Montagem do grafo                                                   #
    # ------------------------------------------------------------------ #

    builder = StateGraph(MekkaCycleState)
    builder.add_node("preflight", preflight_node)
    builder.add_node("process_symbol", process_symbol_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "preflight")
    builder.add_conditional_edges(
        "preflight",
        after_preflight,
        {"process_symbol": "process_symbol", "finalize": "finalize"},
    )
    builder.add_conditional_edges(
        "process_symbol",
        after_process_symbol,
        {"process_symbol": "process_symbol", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)

    return builder


# ---------------------------------------------------------------------------
# Factory: cria o saver e compila o grafo — chamado por NickFury/run.py
# ---------------------------------------------------------------------------

async def make_checkpointed_graph(fury: "NickFury"):
    """
    Cria AsyncSqliteSaver apontando para o mesmo DB do projeto e compila o
    grafo. Retorna (graph, saver).

    Story 128: também cria e aquece o SemanticEpisodicStore, injetando-o em
    fury._vision._semantic_store. Vision usará busca semântica por embedding
    em vez da busca SQL por bucket. Falha silenciosamente se OpenAI unavailable.

    O saver precisa ser mantido vivo enquanto o grafo estiver rodando.
    Use como context manager em produção ou mantenha referência.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from src.config.settings import settings

    db_path = settings.sqlite_db_path
    conn = await aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(conn)
    # Cria as tabelas checkpoints/checkpoint_blobs/checkpoint_writes se não existirem
    await saver.setup()

    # ── Story 128 — Memória Semântica ──────────────────────────────────────
    # Cria o store, aquece a partir do SQLite e injeta em Vision.
    # Falha silenciosamente: se OpenAI indisponível, Vision usa fallback SQL.
    try:
        from src.langgraph.semantic_memory import SemanticEpisodicStore  # noqa: WPS433
        _sem_store = SemanticEpisodicStore(model="text-embedding-3-small")
        n_loaded = await _sem_store.warm_up_from_db(limit=500)
        fury._vision._semantic_store = _sem_store
        logger.info(
            f"[LG:graph] SemanticEpisodicStore pronto — {n_loaded} memórias indexadas"
        )
    except Exception as _sem_exc:
        logger.warning(
            f"[LG:graph] SemanticEpisodicStore indisponível (Vision usará SQL): {_sem_exc}"
        )

    # ── Story 129 — Layer 1 Subgraph ───────────────────────────────────────
    # Compila o Layer 1 subgrafo com o mesmo saver (shared SQLite checkpoint).
    # Thread IDs do subgrafo usam namespace "{cycle_id}:{symbol}:l1" — sem
    # conflito com o ciclo principal. Falha silenciosamente: se não disponível,
    # process_symbol_node usa ProfessorX.run() via asyncio.gather (fallback).
    try:
        from src.langgraph.layer1_graph import build_layer1_graph  # noqa: WPS433
        _layer1_graph = build_layer1_graph(fury._professor).compile(checkpointer=saver)
        fury._layer1_graph = _layer1_graph
        logger.info("[LG:graph] Layer 1 subgraph compilado — fan-out com checkpoints por agente")
    except Exception as _l1_exc:
        fury._layer1_graph = None  # type: ignore[attr-defined]
        logger.warning(
            f"[LG:graph] Layer 1 subgraph indisponível (ProfessorX usará asyncio.gather): {_l1_exc}"
        )

    graph = build_cycle_graph(fury).compile(checkpointer=saver)
    return graph, saver


def make_initial_state(equity_usd: float) -> MekkaCycleState:
    """Estado inicial para uma nova invocação do grafo."""
    return MekkaCycleState(
        cycle_id=str(uuid.uuid4()),
        equity_usd=equity_usd,
        symbols_remaining=[],   # preenchido pelo nó preflight
        symbols_completed=[],
        reports=[],
        skip_reason=None,
        open_positions=0,
        trades_today=0,
        drawdown_pct=0.0,
        running_notional_usd=0.0,
        error=None,
    )

"""
src/langgraph/layer1_graph.py
=================================
Story 129 — Layer 1 Parallel Subgraph.

Substitui o asyncio.gather() interno do ProfessorX por um LangGraph StateGraph
com fan-out verdadeiro. Cada agente da Layer 1 é um nó independente — o
checkpointer salva o estado após cada conclusão, permitindo retomar de qualquer
agente específico após um crash.

Topologia:
  START → superman_node
             ├── sentiment_node (DoctorStrange)  ─┐
             ├── onchain_node   (BlackPanther)     │
             ├── thor_node      (Thor)             ├── spiderman_node → assemble_node → END
             ├── aquaman_node   (Aquaman)          │
             └── flash_node     (Flash)           ─┘

Benefícios vs asyncio.gather() puro:
  • Checkpoint por agente: se Thor crasha, o LangGraph retoma apenas Thor sem
    re-rodar Superman e os outros que já concluíram.
  • Visibilidade: estado de cada agente persistido no SQLite entre super-steps.
  • Extensibilidade: adicionar novos agentes = adicionar nós + edges.

Fail-safe:
  • Superman failure → chart=None, assemble retorna analysis=None.
    _run_layer1_subgraph() detecta e levanta AgentError → CycleReport com erro.
  • Qualquer outro agente → error acumulado, campo fica None, MarketAnalysis
    é construído com campos opcionais ausentes (Vision faz HOLD por pre-flight).

Serialização:
  Todos os campos do Layer1State são JSON-serializáveis (dicts, listas, None).
  Pydantic models são convertidos via .model_dump(mode="json") nos nós.
  assemble_node reconstrói MarketAnalysis via .model_validate().

Thread ID por invocação: "{cycle_id}:{symbol}:l1" — namespace isolado do
ciclo principal no mesmo SQLite. Sem conflito de chaves.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any, Optional

from loguru import logger
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from src.agents.professor_x import ProfessorX


# ---------------------------------------------------------------------------
# Layer 1 State
# ---------------------------------------------------------------------------

class Layer1State(TypedDict):
    """
    Estado JSON-serializável que flui pelo subgrafo Layer 1.

    Campos superman_* preenchidos pelo superman_node.
    Campos paralelos preenchidos independentemente pelos nós de fan-out.
    analysis preenchido pelo assemble_node — None se Superman falhar.
    errors acumula mensagens de erro via reducer operator.add.
    """

    symbol: str

    # ── Superman (serial — outros dependem do chart) ────────────────────────
    chart: Optional[dict]              # MarketData.model_dump(mode="json")
    confirmation_chart: Optional[dict] # MarketData para confirmation TF

    # ── Fan-out paralelo ────────────────────────────────────────────────────
    sentiment: Optional[dict]          # SentimentData
    onchain: Optional[dict]            # OnchainData
    volatility: Optional[dict]         # VolatilityData
    liquidity: Optional[dict]          # LiquidityData
    momentum: Optional[dict]           # MomentumSignal

    # ── SpiderMan (serial — depende de chart + onchain) ─────────────────────
    anomaly: Optional[dict]            # AnomalyReport

    # ── Errors (reducer: acumula) ───────────────────────────────────────────
    errors: Annotated[list[str], operator.add]

    # ── Saída final ─────────────────────────────────────────────────────────
    analysis: Optional[dict]           # MarketAnalysis.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_layer1_graph(professor: "ProfessorX") -> StateGraph:
    """
    Constrói o StateGraph que envolve o fan-out da Layer 1.

    Parâmetros:
        professor: Instância já inicializada de ProfessorX. Os agentes são
                   capturados por closure nos nós — não armazenados no estado.

    Retorna:
        builder (StateGraph não compilado). O chamador é responsável por compilar:
            graph = build_layer1_graph(professor).compile(checkpointer=saver)
    """

    # ------------------------------------------------------------------ #
    # Nó 1 — Superman (serial, obrigatório)                               #
    # ------------------------------------------------------------------ #

    async def superman_node(state: Layer1State) -> dict:
        """
        Executa Superman no primary TF (obrigatório) e opcionalmente no
        confirmation TF (best-effort). Falha fatal → chart=None.
        """
        from src.config.settings import settings as _settings  # noqa: WPS433

        symbol = state["symbol"]

        # Lazy init Superman (detém conexão CCXT)
        if professor._superman is None:
            from src.agents.superman import Superman  # noqa: WPS433
            professor._superman = Superman()

        # Primary TF (obrigatório)
        try:
            chart = await professor._superman.run(symbol=symbol)
            chart_dict = chart.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[L1:superman] {symbol} primary chart failed: {exc}")
            return {
                "chart": None,
                "confirmation_chart": None,
                "errors": [f"Superman:{exc}"],
            }

        # Confirmation TF (best-effort)
        conf_chart_dict: Optional[dict] = None
        conf_tf = _settings.confirmation_timeframe
        if conf_tf and conf_tf != _settings.primary_timeframe:
            try:
                conf = await professor._superman.run(symbol=symbol, timeframe=conf_tf)
                conf_chart_dict = conf.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[L1:superman] {symbol} confirmation TF failed: {exc}")

        logger.debug(f"[L1:superman] {symbol} chart ready")
        return {
            "chart": chart_dict,
            "confirmation_chart": conf_chart_dict,
            "errors": [],
        }

    # ------------------------------------------------------------------ #
    # Nó 2a — DoctorStrange (sentiment, best-effort)                      #
    # ------------------------------------------------------------------ #

    async def sentiment_node(state: Layer1State) -> dict:
        symbol = state["symbol"]
        try:
            data = await professor._strange.run(symbol=symbol)
            return {"sentiment": data.model_dump(mode="json"), "errors": []}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[L1:sentiment] {symbol} failed: {exc}")
            return {"sentiment": None, "errors": [f"DoctorStrange:{exc}"]}

    # ------------------------------------------------------------------ #
    # Nó 2b — BlackPanther (onchain, best-effort)                         #
    # ------------------------------------------------------------------ #

    async def onchain_node(state: Layer1State) -> dict:
        symbol = state["symbol"]
        try:
            data = await professor._panther.run(symbol=symbol)
            return {"onchain": data.model_dump(mode="json"), "errors": []}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[L1:onchain] {symbol} failed: {exc}")
            return {"onchain": None, "errors": [f"BlackPanther:{exc}"]}

    # ------------------------------------------------------------------ #
    # Nó 2c — Thor (volatility, best-effort)                              #
    # ------------------------------------------------------------------ #

    async def thor_node(state: Layer1State) -> dict:
        symbol = state["symbol"]
        chart_dict = state.get("chart")
        if chart_dict is None:
            return {"volatility": None, "errors": []}  # Superman falhou, skip

        try:
            from src.models.market_data import MarketData  # noqa: WPS433
            chart = MarketData.model_validate(chart_dict)
            data = await professor._thor.run(market_data=chart)
            return {"volatility": data.model_dump(mode="json"), "errors": []}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[L1:thor] {symbol} failed: {exc}")
            return {"volatility": None, "errors": [f"Thor:{exc}"]}

    # ------------------------------------------------------------------ #
    # Nó 2d — Aquaman (liquidity, best-effort)                            #
    # ------------------------------------------------------------------ #

    async def aquaman_node(state: Layer1State) -> dict:
        symbol = state["symbol"]
        try:
            data = await professor._aquaman.run(symbol=symbol)
            return {"liquidity": data.model_dump(mode="json"), "errors": []}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[L1:aquaman] {symbol} failed: {exc}")
            return {"liquidity": None, "errors": [f"Aquaman:{exc}"]}

    # ------------------------------------------------------------------ #
    # Nó 2e — Flash (momentum, best-effort)                               #
    # ------------------------------------------------------------------ #

    async def flash_node(state: Layer1State) -> dict:
        symbol = state["symbol"]
        chart_dict = state.get("chart")
        if chart_dict is None:
            return {"momentum": None, "errors": []}  # Superman falhou, skip

        try:
            from src.models.market_data import MarketData  # noqa: WPS433
            chart = MarketData.model_validate(chart_dict)
            recent_prices = chart.recent_closes or []
            data = await professor._flash.run(
                symbol=symbol,
                recent_prices=recent_prices,
            )
            return {"momentum": data.model_dump(mode="json"), "errors": []}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[L1:flash] {symbol} failed: {exc}")
            return {"momentum": None, "errors": [f"Flash:{exc}"]}

    # ------------------------------------------------------------------ #
    # Nó 3 — SpiderMan (serial, depende de chart + onchain)               #
    # ------------------------------------------------------------------ #

    async def spiderman_node(state: Layer1State) -> dict:
        symbol = state["symbol"]
        chart_dict = state.get("chart")
        if chart_dict is None:
            return {"anomaly": None, "errors": []}  # sem chart, skip

        try:
            from src.models.market_data import MarketData, OnchainData  # noqa: WPS433
            chart = MarketData.model_validate(chart_dict)
            onchain_dict = state.get("onchain")
            onchain = OnchainData.model_validate(onchain_dict) if onchain_dict else None
            data = await professor._spider.run(
                symbol=symbol,
                market_data=chart,
                onchain_data=onchain,
            )
            return {"anomaly": data.model_dump(mode="json"), "errors": []}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[L1:spiderman] {symbol} failed: {exc}")
            return {"anomaly": None, "errors": [f"SpiderMan:{exc}"]}

    # ------------------------------------------------------------------ #
    # Nó 4 — Assemble (fan-in final)                                      #
    # ------------------------------------------------------------------ #

    async def assemble_node(state: Layer1State) -> dict:
        """
        Constrói MarketAnalysis a partir dos campos do estado.
        Se Superman falhou (chart=None), devolve analysis=None.
        """
        symbol = state["symbol"]
        chart_dict = state.get("chart")

        if chart_dict is None:
            errors = state.get("errors", [])
            logger.error(
                f"[L1:assemble] {symbol} chart absent — cannot build analysis. "
                f"Errors: {errors}"
            )
            return {"analysis": None}

        try:
            from src.models.market_data import (  # noqa: WPS433
                AnomalyReport,
                LiquidityData,
                MarketAnalysis,
                MarketData,
                OnchainData,
                SentimentData,
                VolatilityData,
            )
            from src.models.signal import MomentumSignal  # noqa: WPS433

            def _safe_validate(model_cls, data_dict):
                """Valida um dict como Pydantic model, retorna None em caso de falha."""
                if data_dict is None:
                    return None
                try:
                    return model_cls.model_validate(data_dict)
                except Exception as _exc:
                    logger.warning(
                        f"[L1:assemble] {model_cls.__name__} validate failed: {_exc}"
                    )
                    return None

            chart = MarketData.model_validate(chart_dict)
            conf_dict = state.get("confirmation_chart")
            confirmation_chart = (
                MarketData.model_validate(conf_dict) if conf_dict else None
            )

            analysis = MarketAnalysis(
                chart=chart,
                confirmation_chart=confirmation_chart,
                sentiment=_safe_validate(SentimentData, state.get("sentiment")),
                onchain=_safe_validate(OnchainData, state.get("onchain")),
                volatility=_safe_validate(VolatilityData, state.get("volatility")),
                liquidity=_safe_validate(LiquidityData, state.get("liquidity")),
                anomaly=_safe_validate(AnomalyReport, state.get("anomaly")),
                momentum=_safe_validate(MomentumSignal, state.get("momentum")),
            )

            errors = state.get("errors", [])
            if errors:
                logger.info(
                    f"[L1:assemble] {symbol} partial analysis "
                    f"({len(errors)} agent errors): {errors}"
                )
            else:
                logger.info(f"[L1:assemble] {symbol} full analysis assembled")

            return {"analysis": analysis.model_dump(mode="json")}

        except Exception as exc:  # noqa: BLE001
            logger.error(f"[L1:assemble] {symbol} assembly failed: {exc}")
            return {"analysis": None, "errors": [f"assemble:{exc}"]}

    # ------------------------------------------------------------------ #
    # Montagem do grafo                                                   #
    # ------------------------------------------------------------------ #

    builder = StateGraph(Layer1State)

    # Nós
    builder.add_node("superman", superman_node)
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("onchain", onchain_node)
    builder.add_node("thor", thor_node)
    builder.add_node("aquaman", aquaman_node)
    builder.add_node("flash", flash_node)
    builder.add_node("spiderman", spiderman_node)
    builder.add_node("assemble", assemble_node)

    # START → superman (serial, obrigatório)
    builder.add_edge(START, "superman")

    # Fan-out: superman → 5 agentes paralelos
    builder.add_edge("superman", "sentiment")
    builder.add_edge("superman", "onchain")
    builder.add_edge("superman", "thor")
    builder.add_edge("superman", "aquaman")
    builder.add_edge("superman", "flash")

    # Fan-in: todos os 5 → spiderman (aguarda conclusão de todos)
    builder.add_edge("sentiment", "spiderman")
    builder.add_edge("onchain", "spiderman")
    builder.add_edge("thor", "spiderman")
    builder.add_edge("aquaman", "spiderman")
    builder.add_edge("flash", "spiderman")

    # spiderman → assemble → END
    builder.add_edge("spiderman", "assemble")
    builder.add_edge("assemble", END)

    return builder


# ---------------------------------------------------------------------------
# Helper: invocar o subgrafo e devolver MarketAnalysis
# ---------------------------------------------------------------------------

async def run_layer1_subgraph(
    graph: Any,
    symbol: str,
    cycle_id: str,
) -> "MarketAnalysis":  # type: ignore[name-defined]
    """
    Invoca o Layer 1 subgrafo compilado e devolve um MarketAnalysis.

    Thread ID: "{cycle_id}:{symbol}:l1" — namespace isolado do ciclo principal.

    Levanta AgentError se Superman falhar (chart=None no estado final).
    """
    from src.agents.base import AgentError  # noqa: WPS433
    from src.models.market_data import MarketAnalysis  # noqa: WPS433

    l1_thread_id = f"{cycle_id}:{symbol}:l1"
    config = {"configurable": {"thread_id": l1_thread_id}}

    initial_state: Layer1State = {
        "symbol": symbol,
        "chart": None,
        "confirmation_chart": None,
        "sentiment": None,
        "onchain": None,
        "volatility": None,
        "liquidity": None,
        "momentum": None,
        "anomaly": None,
        "errors": [],
        "analysis": None,
    }

    final_state = await graph.ainvoke(initial_state, config=config)
    analysis_dict = final_state.get("analysis")

    if analysis_dict is None:
        errors = final_state.get("errors", [])
        raise AgentError(
            f"Layer 1 subgraph failed for {symbol}: "
            + ("; ".join(errors) if errors else "chart=None (Superman failed)")
        )

    return MarketAnalysis.model_validate(analysis_dict)

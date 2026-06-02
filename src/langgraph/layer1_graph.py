"""
src/langgraph/layer1_graph.py
=================================
Story 129 — Layer 1 Parallel Subgraph.
Story 135 — Adaptive Layer 1 Routing (Hierarchical Process).

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

try:
    from langgraph.graph import END, START, StateGraph
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    END = START = None  # type: ignore[assignment]
    StateGraph = Any  # type: ignore[assignment]
    _LANGGRAPH_AVAILABLE = False

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

    # ── Story 135 — Adaptive Routing ────────────────────────────────────────
    skip_set: Optional[list[str]]      # nós a pular neste ciclo (None = rodar tudo)

    # ── Saída final ─────────────────────────────────────────────────────────
    analysis: Optional[dict]           # MarketAnalysis.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Story 135 — Adaptive Routing helpers
# ---------------------------------------------------------------------------

# Regime labels detectados pelo chart (VolatilityData.regime ou derivado do ATR)
_REGIME_EXTREME = "EXTREME"
_REGIME_HIGH    = "HIGH"
_REGIME_LOW     = "LOW"
_REGIME_NORMAL  = "NORMAL"


def _classify_regime(chart_dict: Optional[dict]) -> str:
    """
    Deriva o regime de volatilidade a partir do dict do chart (MarketData).

    Usa `atr_pct` quando disponível: > 5% → EXTREME, > 2% → HIGH,
    < 0.5% → LOW, caso contrário NORMAL.

    Fallback: se chart ausente ou campo não encontrado → NORMAL.
    """
    if chart_dict is None:
        return _REGIME_NORMAL
    atr_pct = chart_dict.get("atr_pct") or chart_dict.get("atr_percent")
    if atr_pct is None:
        # Tenta derivar do trend_strength ou regime se presentes
        regime = chart_dict.get("regime")
        if regime in (_REGIME_EXTREME, _REGIME_HIGH, _REGIME_LOW, _REGIME_NORMAL):
            return regime
        return _REGIME_NORMAL
    atr_pct = float(atr_pct)
    if atr_pct > 5.0:
        return _REGIME_EXTREME
    if atr_pct > 2.0:
        return _REGIME_HIGH
    if atr_pct < 0.5:
        return _REGIME_LOW
    return _REGIME_NORMAL


def _decide_skip_set(chart_dict: Optional[dict]) -> list[str]:
    """
    Story 135 — Hierarquia de roteamento por regime.

    Retorna lista de nomes de nós a pular neste ciclo. Regras:

    NORMAL   → [] (todos os agentes)
    HIGH     → ["flash"] (intra-candle momentum pouco útil em alta vol)
    EXTREME  → ["sentiment", "flash"] (macro irrelevante em vol extrema)
    LOW      → ["onchain", "flash"] (whale flow e momentum irrelevantes em flat)

    Carrega overrides de settings via `layer1_routing_*_skip` se configurado.
    Retorna lista vazia se layer1_routing_enabled=False (routing desabilitado).
    """
    try:
        from src.config.settings import settings as _s  # noqa: WPS433
        if not getattr(_s, "layer1_routing_enabled", False):
            return []
    except Exception:  # noqa: BLE001
        return []

    regime = _classify_regime(chart_dict)

    try:
        from src.config.settings import settings as _s  # noqa: WPS433
        skip_field = f"layer1_routing_{regime.lower()}_skip"
        skip_raw = getattr(_s, skip_field, None)
        if skip_raw is not None:
            # CSV de nomes de nós, ex: "sentiment,flash"
            return [n.strip() for n in skip_raw.split(",") if n.strip()]
    except Exception:  # noqa: BLE001
        pass

    # Defaults embutidos
    defaults: dict[str, list[str]] = {
        _REGIME_NORMAL:  [],
        _REGIME_HIGH:    ["flash"],
        _REGIME_EXTREME: ["sentiment", "flash"],
        _REGIME_LOW:     ["onchain", "flash"],
    }
    return defaults.get(regime, [])


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
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError(
            "LangGraph is not installed. Install 'langgraph' to use the Layer 1 subgraph."
        )

    # ------------------------------------------------------------------ #
    # Nó 1 — Superman (serial, obrigatório)                               #
    # ------------------------------------------------------------------ #

    async def superman_node(state: Layer1State) -> dict:
        """
        Executa Superman no primary TF (obrigatório) e opcionalmente no
        confirmation TF (best-effort). Falha fatal → chart=None.

        Scalp mode override: quando o modo ativo é 'scalp' (ou variante),
        usa scalp_primary_timeframe / scalp_confirmation_timeframe do preset
        (ex: 5m + 1m) em vez do default 4h+1h do settings.
        """
        from src.config.settings import settings as _settings  # noqa: WPS433
        from src.config.runtime_mode import get_params as _get_mode_params  # noqa: WPS433

        symbol = state["symbol"]

        # Mode-aware timeframes: scalp override OR settings defaults
        try:
            _mp = _get_mode_params()
            primary_tf = _mp.get("scalp_primary_timeframe") or _settings.primary_timeframe
            conf_tf = _mp.get("scalp_confirmation_timeframe") or _settings.confirmation_timeframe
        except Exception:
            primary_tf = _settings.primary_timeframe
            conf_tf = _settings.confirmation_timeframe

        # Lazy init Superman (detém conexão CCXT)
        if professor._superman is None:
            from src.agents.superman import Superman  # noqa: WPS433
            professor._superman = Superman()

        # Primary TF (obrigatório)
        try:
            chart = await professor._superman.run(symbol=symbol, timeframe=primary_tf)
            chart_dict = chart.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[L1:superman] {symbol} primary chart ({primary_tf}) failed: {exc}")
            return {
                "chart": None,
                "confirmation_chart": None,
                "errors": [f"Superman:{exc}"],
            }

        # Confirmation TF (best-effort)
        conf_chart_dict: Optional[dict] = None
        if conf_tf and conf_tf != primary_tf:
            try:
                conf = await professor._superman.run(symbol=symbol, timeframe=conf_tf)
                conf_chart_dict = conf.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[L1:superman] {symbol} confirmation TF ({conf_tf}) failed: {exc}")

        logger.debug(f"[L1:superman] {symbol} chart ready")
        return {
            "chart": chart_dict,
            "confirmation_chart": conf_chart_dict,
            "errors": [],
        }

    # ------------------------------------------------------------------ #
    # Nó 1b — Routing (Story 135 — Adaptive Layer 1 Routing)             #
    # ------------------------------------------------------------------ #

    async def routing_node(state: Layer1State) -> dict:
        """
        Story 135 — Decide quais agentes pular baseado no regime de mercado.

        Analisa o chart do Superman (atr_pct) para classificar o regime:
        EXTREME / HIGH / LOW / NORMAL. Escreve skip_set no estado.

        Se layer1_routing_enabled=False, skip_set=[] (todos rodando).
        """
        chart_dict = state.get("chart")
        skip = _decide_skip_set(chart_dict)
        if skip:
            logger.info(
                f"[L1:routing] {state['symbol']} regime="
                f"{_classify_regime(chart_dict)} — skipping: {skip}"
            )
        return {"skip_set": skip, "errors": []}

    # ------------------------------------------------------------------ #
    # Nó 2a — DoctorStrange (sentiment, best-effort)                      #
    # ------------------------------------------------------------------ #

    async def sentiment_node(state: Layer1State) -> dict:
        symbol = state["symbol"]
        # Story 135 — skip if routing decided
        if "sentiment" in (state.get("skip_set") or []):
            logger.debug(f"[L1:sentiment] {symbol} skipped by routing")
            return {"sentiment": None, "errors": []}
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
        # Story 135 — skip if routing decided
        if "onchain" in (state.get("skip_set") or []):
            logger.debug(f"[L1:onchain] {symbol} skipped by routing")
            return {"onchain": None, "errors": []}
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
        # Story 135 — skip if routing decided
        if "thor" in (state.get("skip_set") or []):
            logger.debug(f"[L1:thor] {symbol} skipped by routing")
            return {"volatility": None, "errors": []}
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
        # Story 135 — skip if routing decided
        if "aquaman" in (state.get("skip_set") or []):
            logger.debug(f"[L1:aquaman] {symbol} skipped by routing")
            return {"liquidity": None, "errors": []}
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
        # Story 135 — skip if routing decided
        if "flash" in (state.get("skip_set") or []):
            logger.debug(f"[L1:flash] {symbol} skipped by routing")
            return {"momentum": None, "errors": []}
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

            # Scalp Mode (2026-05-28) — injeta trading_mode atual para que
            # Vision possa renderizar prompt mode-aware. Fail-silent: se
            # runtime_mode indisponível, mantém "" (retrocompat).
            try:
                from src.config.runtime_mode import get_mode as _get_mode  # noqa: WPS433
                _current_mode = _get_mode()
            except Exception:
                _current_mode = ""

            analysis = MarketAnalysis(
                chart=chart,
                confirmation_chart=confirmation_chart,
                sentiment=_safe_validate(SentimentData, state.get("sentiment")),
                onchain=_safe_validate(OnchainData, state.get("onchain")),
                volatility=_safe_validate(VolatilityData, state.get("volatility")),
                liquidity=_safe_validate(LiquidityData, state.get("liquidity")),
                anomaly=_safe_validate(AnomalyReport, state.get("anomaly")),
                momentum=_safe_validate(MomentumSignal, state.get("momentum")),
                trading_mode=_current_mode,
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
    builder.add_node("routing", routing_node)   # Story 135 — Adaptive Routing
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("onchain", onchain_node)
    builder.add_node("thor", thor_node)
    builder.add_node("aquaman", aquaman_node)
    builder.add_node("flash", flash_node)
    builder.add_node("spiderman", spiderman_node)
    builder.add_node("assemble", assemble_node)

    # START → superman (serial, obrigatório)
    builder.add_edge(START, "superman")

    # Story 135: superman → routing → fan-out
    # routing_node escreve skip_set no estado; nós secundários checam antes de rodar
    builder.add_edge("superman", "routing")

    # Fan-out: routing → 5 agentes paralelos
    builder.add_edge("routing", "sentiment")
    builder.add_edge("routing", "onchain")
    builder.add_edge("routing", "thor")
    builder.add_edge("routing", "aquaman")
    builder.add_edge("routing", "flash")

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

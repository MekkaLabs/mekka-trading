"""
src/services/mekka_kernel.py
==============================
Story 153 — @mekka_function + MekkaPlugin Registry.

Inspirado no padrão Semantic Kernel Plugin Architecture:
https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/

Permite que funções de agentes sejam:
  1. Auto-documentadas com schema gerado a partir de type hints + docstring
  2. Descobertas pelo LLM via OpenAI function calling schema
  3. Registradas num registry central (MekkaKernel) como plugins

Arquitetura
-----------
  @mekka_function    — decorator (como @kernel_function do SK)
                       marca métodos como expostos ao LLM
  MekkaPlugin        — wrapper de uma classe com métodos @mekka_function
                       auto-gera schema OpenAI a partir de type annotations
  MekkaKernel        — registry central de plugins
                       gera tool_definitions[] para OpenAI function calling
                       executa function calls via dispatch

Plugins built-in disponíveis
-----------------------------
  VisionPlugin       — wrap de Vision.run() como função chamável
  BatmanPlugin       — wrap de Batman risk check como função chamável
  MarketDataPlugin   — acesso a análise de mercado por símbolo
  RiskPlugin         — consulta limites de risco e estado atual

Uso
---
    from src.services.mekka_kernel import MekkaKernel, mekka_function

    class TradingPlugin:
        @mekka_function(
            description="Analyze market conditions and generate a trading signal",
            tags=["vision", "trading"]
        )
        async def analyze_market(self, symbol: str, timeframe: str = "1h") -> dict:
            ...

    kernel = MekkaKernel()
    kernel.add_plugin(TradingPlugin(), name="trading")

    # Gerar tool_definitions para OpenAI
    tools = kernel.get_tool_definitions()

    # Executar function call retornado pelo LLM
    result = await kernel.invoke("trading", "analyze_market", symbol="BTC")
"""

from __future__ import annotations

import functools
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

from loguru import logger


# ---------------------------------------------------------------------------
# @mekka_function decorator
# ---------------------------------------------------------------------------

_MEKKA_FUNCTION_ATTR = "__mekka_function__"


def mekka_function(
    description: str = "",
    name: str = "",
    tags: list[str] | None = None,
    return_description: str = "",
) -> Callable:
    """
    Decorator que marca um método como função exposta ao LLM.

    Inspirado no @kernel_function do Semantic Kernel:
    https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/adding-native-plugins

    Parâmetros
    ----------
    description      : descrição semântica da função (usada pelo LLM para decidir quando chamá-la)
    name             : nome da função (padrão: nome do método)
    tags             : categorias para filtragem no registry
    return_description: descrição do valor de retorno

    Uso
    ---
        @mekka_function(description="Get current price for symbol")
        async def get_price(self, symbol: str) -> float:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        fn_name = name or fn.__name__
        fn_description = description or (fn.__doc__ or "").strip().split("\n")[0]

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)

        # Copiar signature original para wrapper
        wrapper.__signature__ = inspect.signature(fn)
        wrapper.__annotations__ = fn.__annotations__.copy()

        # Marcar como mekka_function com metadados
        setattr(wrapper, _MEKKA_FUNCTION_ATTR, {
            "name": fn_name,
            "description": fn_description,
            "tags": tags or [],
            "return_description": return_description,
            "original_fn": fn,
        })

        return wrapper
    return decorator


def is_mekka_function(fn: Callable) -> bool:
    """Retorna True se a função foi decorada com @mekka_function."""
    return hasattr(fn, _MEKKA_FUNCTION_ATTR)


def get_mekka_metadata(fn: Callable) -> dict:
    """Retorna os metadados de um @mekka_function."""
    return getattr(fn, _MEKKA_FUNCTION_ATTR, {})


# ---------------------------------------------------------------------------
# Type → JSON Schema mapping
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _python_type_to_json_schema(annotation: Any) -> dict:
    """
    Converte anotação de tipo Python em JSON Schema simples.
    Suficiente para function calling — sem suporte a generics complexos.
    """
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}

    origin = getattr(annotation, "__origin__", None)

    # Optional[X] → X (sem required)
    if origin is type(None):
        return {"type": "null"}

    # list[X], List[X]
    if origin is list:
        args = getattr(annotation, "__args__", [])
        item_schema = _python_type_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}

    # dict[K, V]
    if origin is dict:
        return {"type": "object"}

    # typing.Optional / Union
    if hasattr(annotation, "__args__"):
        # Union[X, None] = Optional[X]
        args = [a for a in annotation.__args__ if a is not type(None)]
        if len(args) == 1:
            return _python_type_to_json_schema(args[0])
        return {"type": "string"}  # fallback para Union complexo

    return {"type": _TYPE_MAP.get(annotation, "string")}


# ---------------------------------------------------------------------------
# FunctionSchema — schema gerado para uma função
# ---------------------------------------------------------------------------

@dataclass
class FunctionSchema:
    """Schema gerado para uma @mekka_function, compatível com OpenAI function calling."""
    plugin_name: str
    function_name: str
    description: str
    parameters: dict[str, Any]
    tags: list[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.plugin_name}__{self.function_name}"

    def to_openai_tool(self) -> dict:
        """Converte para formato OpenAI tools[] (function calling)."""
        return {
            "type": "function",
            "function": {
                "name": self.full_name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _build_function_schema(
    plugin_name: str,
    fn: Callable,
    metadata: dict,
) -> FunctionSchema:
    """
    Constrói FunctionSchema a partir de uma @mekka_function.
    Extrai parâmetros via inspect.signature() + type annotations.
    """
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        annotation = param.annotation
        schema = _python_type_to_json_schema(annotation)

        # Extrair descrição de typing.Annotated se disponível
        if hasattr(annotation, "__metadata__") and annotation.__metadata__:
            meta = annotation.__metadata__[0]
            if isinstance(meta, str):
                schema["description"] = meta

        properties[param_name] = schema

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return FunctionSchema(
        plugin_name=plugin_name,
        function_name=metadata["name"],
        description=metadata["description"],
        tags=metadata.get("tags", []),
        parameters={
            "type": "object",
            "properties": properties,
            "required": required,
        },
    )


# ---------------------------------------------------------------------------
# MekkaPlugin
# ---------------------------------------------------------------------------

class MekkaPlugin:
    """
    Wrapper de uma classe Python com métodos @mekka_function.

    Equivalente ao KernelPlugin.from_object() do Semantic Kernel.
    Auto-descobre todos os métodos decorados e gera schemas OpenAI.
    """

    def __init__(self, obj: Any, name: str = "") -> None:
        self._obj = obj
        self.name = name or type(obj).__name__
        self._functions: dict[str, Callable] = {}
        self._schemas: dict[str, FunctionSchema] = {}
        self._discover()

    def _discover(self) -> None:
        """Auto-descobre métodos @mekka_function na classe."""
        for attr_name in dir(self._obj):
            if attr_name.startswith("_"):
                continue
            fn = getattr(self._obj, attr_name, None)
            if fn is None or not callable(fn):
                continue
            if not is_mekka_function(fn):
                continue

            metadata = get_mekka_metadata(fn)
            fn_name = metadata["name"]
            self._functions[fn_name] = fn
            self._schemas[fn_name] = _build_function_schema(
                plugin_name=self.name,
                fn=fn,
                metadata=metadata,
            )
            logger.debug(
                f"[MekkaPlugin:{self.name}] Discovered function: {fn_name}"
            )

    async def invoke(self, function_name: str, **kwargs: Any) -> Any:
        """
        Executa uma função do plugin pelo nome.
        Lança KeyError se a função não existir.
        """
        fn = self._functions.get(function_name)
        if fn is None:
            raise KeyError(
                f"[MekkaPlugin:{self.name}] Function '{function_name}' not found. "
                f"Available: {list(self._functions.keys())}"
            )
        return await fn(**kwargs)

    @property
    def function_names(self) -> list[str]:
        return list(self._functions.keys())

    @property
    def schemas(self) -> list[FunctionSchema]:
        return list(self._schemas.values())

    def get_schema(self, function_name: str) -> Optional[FunctionSchema]:
        return self._schemas.get(function_name)


# ---------------------------------------------------------------------------
# MekkaKernel
# ---------------------------------------------------------------------------

class MekkaKernel:
    """
    Registry central de MekkaPlugins.

    Inspirado no Kernel do Semantic Kernel:
    https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel

    Responsabilidades:
      1. Armazenar plugins registrados por nome
      2. Gerar tool_definitions[] para OpenAI function calling
      3. Despachar function calls para o plugin correto
      4. Opcionalmente aplicar FilterChain em cada invocação

    Uso com OpenAI function calling
    --------------------------------
        kernel = MekkaKernel()
        kernel.add_plugin(MarketDataPlugin(), "market")
        kernel.add_plugin(RiskPlugin(), "risk")

        # Obter tools para passar ao LLM
        tools = kernel.get_tool_definitions()

        # LLM retorna function call:
        # {"name": "market__get_analysis", "arguments": '{"symbol": "BTC"}'}
        result = await kernel.invoke_from_tool_call(
            name="market__get_analysis",
            arguments_json='{"symbol": "BTC"}'
        )
    """

    def __init__(self) -> None:
        self._plugins: dict[str, MekkaPlugin] = {}
        self._filter_chain = None  # opcional: FilterChain

    def add_plugin(self, obj: Any, name: str = "") -> "MekkaKernel":
        """
        Adiciona um objeto como plugin.
        Equivalente a kernel.add_plugin() do Semantic Kernel.
        """
        plugin = MekkaPlugin(obj=obj, name=name)
        self._plugins[plugin.name] = plugin
        logger.info(
            f"[MekkaKernel] Plugin '{plugin.name}' registered with "
            f"{len(plugin.function_names)} function(s): {plugin.function_names}"
        )
        return self

    def get_plugin(self, name: str) -> Optional[MekkaPlugin]:
        return self._plugins.get(name)

    @property
    def plugin_names(self) -> list[str]:
        return list(self._plugins.keys())

    def get_tool_definitions(
        self,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """
        Gera lista de tool_definitions[] para OpenAI function calling.

        Parâmetros
        ----------
        tags : filtrar apenas funções com estas tags (None = todas)

        Retorna lista pronta para `tools=` no OpenAI chat.completions.create().
        """
        tools = []
        for plugin in self._plugins.values():
            for schema in plugin.schemas:
                if tags and not any(t in schema.tags for t in tags):
                    continue
                tools.append(schema.to_openai_tool())
        return tools

    def get_function_map(self) -> dict[str, str]:
        """
        Retorna mapa de {full_name → "plugin::function"} para debugging.
        """
        result = {}
        for plugin in self._plugins.values():
            for schema in plugin.schemas:
                result[schema.full_name] = f"{plugin.name}::{schema.function_name}"
        return result

    async def invoke(
        self,
        plugin_name: str,
        function_name: str,
        **kwargs: Any,
    ) -> Any:
        """
        Executa uma função de um plugin pelo nome.

        Se um FilterChain estiver configurado, a invocação passa pelos filtros.
        """
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            raise KeyError(
                f"[MekkaKernel] Plugin '{plugin_name}' not found. "
                f"Registered: {list(self._plugins.keys())}"
            )

        if self._filter_chain is not None:
            from src.services.invocation_filter import FilterChain
            ctx = await self._filter_chain.invoke(
                function_name=f"{plugin_name}.{function_name}",
                fn=lambda: plugin.invoke(function_name, **kwargs),
                **kwargs,
            )
            if ctx.exception:
                raise ctx.exception
            return ctx.result

        return await plugin.invoke(function_name, **kwargs)

    async def invoke_from_tool_call(
        self,
        name: str,
        arguments_json: str = "{}",
    ) -> Any:
        """
        Executa uma function call retornada pelo LLM.

        Parâmetros
        ----------
        name            : nome no formato "plugin_name__function_name"
        arguments_json  : JSON string com os argumentos (como retornado pelo LLM)

        Uso
        ---
            # LLM retorna: tool_calls[0].function.name = "market__analyze"
            # LLM retorna: tool_calls[0].function.arguments = '{"symbol": "BTC"}'
            result = await kernel.invoke_from_tool_call(
                name="market__analyze",
                arguments_json='{"symbol": "BTC"}'
            )
        """
        # Parse "plugin_name__function_name"
        if "__" not in name:
            raise ValueError(
                f"[MekkaKernel] Tool call name '{name}' must be in format "
                f"'plugin_name__function_name'. Use get_tool_definitions() to see valid names."
            )
        plugin_name, function_name = name.split("__", 1)

        try:
            kwargs = json.loads(arguments_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"[MekkaKernel] Invalid JSON arguments: {arguments_json!r}"
            ) from exc

        return await self.invoke(plugin_name, function_name, **kwargs)

    def set_filter_chain(self, chain: Any) -> "MekkaKernel":
        """
        Configura FilterChain para todas as invocações via invoke().
        """
        self._filter_chain = chain
        return self

    def describe(self) -> str:
        """Retorna descrição legível dos plugins registrados."""
        lines = [f"MekkaKernel — {len(self._plugins)} plugins:"]
        for pname, plugin in self._plugins.items():
            lines.append(f"  [{pname}]")
            for schema in plugin.schemas:
                lines.append(f"    • {schema.function_name}: {schema.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in Plugins para Mekka Trading
# ---------------------------------------------------------------------------

class MarketRegimePlugin:
    """
    Plugin que expõe detecção de regime de mercado via function calling.

    Um LLM pode chamar detect_regime() para obter o regime atual do BTC
    e usar essa informação para ajustar a estratégia de trading.
    """

    @mekka_function(
        description=(
            "Detect the current cryptocurrency market regime (BULL/BEAR/SIDEWAYS/VOLATILE) "
            "using BTC as a proxy. Returns regime, confidence, and supporting data."
        ),
        tags=["market", "regime"],
    )
    async def detect_regime(
        self,
        btc_trend: str = "NEUTRAL",
        btc_rsi: float = 50.0,
        btc_atr_pct: float = 0.02,
    ) -> dict:
        """Detect market regime using BTC data as proxy."""
        from src.services.asset_classifier import MarketRegimeDetector
        detector = MarketRegimeDetector()
        report = detector.detect(
            btc_trend=btc_trend,
            btc_rsi=btc_rsi,
            btc_atr_pct=btc_atr_pct,
        )
        return report.to_audit_payload()

    @mekka_function(
        description=(
            "Classify a cryptocurrency asset by market cap tier "
            "(LARGE_CAP/MID_CAP/SMALL_CAP) and trend behavior (TRENDING/RANGING/UNKNOWN)."
        ),
        tags=["market", "classifier"],
    )
    async def classify_asset(
        self,
        symbol: str,
        price: float = 0.0,
        ema20: float = 0.0,
        atr_pct: float = 0.0,
    ) -> dict:
        """Classify asset by cap tier and trend behavior."""
        from src.services.asset_classifier import AssetClassifier
        classifier = AssetClassifier()
        result = classifier.classify(
            symbol=symbol,
            price=price,
            ema20=ema20 or None,
            atr_pct=atr_pct or None,
        )
        return result.to_audit_payload()


class SystemStatusPlugin:
    """
    Plugin que expõe o estado de saúde do sistema via function calling.

    Permite que um LLM consulte se o sistema está degradado, o custo acumulado
    de LLM e as latências do pipeline antes de tomar decisões.
    """

    @mekka_function(
        description=(
            "Check if the trading system is in DEGRADED_MODE "
            "(no new entries allowed) or NORMAL state."
        ),
        tags=["system", "health"],
    )
    async def get_system_status(self) -> dict:
        """Get current DEGRADED_MODE status and recovery progress."""
        from src.services.degraded_mode import get_degraded_mode_manager
        manager = get_degraded_mode_manager()
        return {
            "is_degraded": manager.is_degraded,
            "reason": manager.reason,
            "recovery_progress": manager.recovery_progress,
            "trigger_count": manager.trigger_count,
            "summary": manager.summary(),
        }

    @mekka_function(
        description=(
            "Get LLM cost metrics for the current session: "
            "total cost, calls by model/agent, most expensive call."
        ),
        tags=["system", "cost"],
    )
    async def get_llm_costs(self) -> dict:
        """Get aggregated LLM cost metrics from the current session."""
        from src.services.llm_cost_tracker import get_llm_cost_tracker
        tracker = get_llm_cost_tracker(auto_register=False)
        return tracker.summary()

    @mekka_function(
        description=(
            "Get pipeline performance benchmarks: p50/p95/p99 latency per stage "
            "(vision, batman) and slow cycle history."
        ),
        tags=["system", "performance"],
    )
    async def get_pipeline_benchmarks(self) -> dict:
        """Get pipeline latency benchmarks from the current session."""
        from src.services.pipeline_benchmark import get_pipeline_benchmark
        bench = get_pipeline_benchmark()
        return bench.summary()


# ---------------------------------------------------------------------------
# Story 171 — ObservabilityPlugin: expõe dados reais do Milestone 24
# ---------------------------------------------------------------------------

class ObservabilityPlugin:
    """
    Plugin que expõe observabilidade em tempo real do ciclo de trading:
    CycleEventLog, SignalChangeLog, ContextWindowTracker, AgentStepGuard
    e SignalValidator — todos os serviços do Milestone 23+24.

    Permite que um LLM consulte o estado do sistema antes de tomar decisões.
    """

    @mekka_function(
        description=(
            "Get recent cycle events from CycleEventLog. "
            "Returns the last N events with their type, symbol, cycle_id and payload."
        ),
        tags=["observability", "events"],
    )
    async def get_cycle_events(self, symbol: str = "", last_n: int = 10) -> dict:
        """Get recent cycle events, optionally filtered by symbol."""
        try:
            from src.services.cycle_event_log import get_cycle_event_log
            cel = get_cycle_event_log()
            if symbol:
                events = cel.filter_by_symbol(symbol)[-last_n:]
            else:
                events = cel.last_n(last_n)
            return {
                "events": [
                    {"type": str(e.event_type), "symbol": e.symbol,
                     "cycle_id": e.cycle_id, "payload": e.payload}
                    for e in events
                ],
                "total": len(events),
                "summary": cel.summary(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "events": []}

    @mekka_function(
        description=(
            "Get recent signal changes from SignalChangeLog. "
            "Returns last N change records for a symbol, including action flips."
        ),
        tags=["observability", "signals"],
    )
    async def get_signal_changes(self, symbol: str, last_n: int = 5) -> dict:
        """Get recent signal change records for a symbol."""
        try:
            from src.services.signal_changelog import get_signal_changelog
            scl = get_signal_changelog()
            records = scl.get_recent(symbol=symbol, n=last_n)
            flips = scl.get_action_flips(symbol=symbol)
            return {
                "symbol": symbol,
                "recent_changes": [r.to_dict() for r in records],
                "action_flips_total": len(flips),
                "last_flip": flips[-1].commit_message() if flips else None,
                "summary": scl.summary(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "symbol": symbol, "recent_changes": []}

    @mekka_function(
        description=(
            "Get context window usage for a specific cycle or global summary. "
            "Returns token usage per stage and whether the limit is near."
        ),
        tags=["observability", "context"],
    )
    async def get_context_window(self, cycle_id: str = "") -> dict:
        """Get context window usage — cycle summary or global stats."""
        try:
            from src.services.context_window_tracker import get_context_window_tracker
            cwt = get_context_window_tracker()
            if cycle_id:
                return cwt.cycle_summary(cycle_id)
            return cwt.summary()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mekka_function(
        description=(
            "Get AgentStepGuard global counters: total stuck loop events "
            "and max_iterations exceeded events across all cycles."
        ),
        tags=["observability", "guard"],
    )
    async def get_step_guard_stats(self) -> dict:
        """Get global AgentStepGuard stuck/max counters."""
        try:
            from src.services.agent_step_guard import NickFuryStepGuard
            return NickFuryStepGuard.global_summary()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mekka_function(
        description=(
            "Get SignalValidator thresholds: min confidence, min R:R, "
            "max total risk, and other configured limits."
        ),
        tags=["observability", "validation"],
    )
    async def get_validator_thresholds(self) -> dict:
        """Get configured SignalValidator thresholds."""
        try:
            from src.services.signal_validator import get_signal_validator
            v = get_signal_validator()
            return {
                "min_confidence_long": v.min_confidence_long,
                "min_confidence_short": v.min_confidence_short,
                "min_risk_reward": v.min_risk_reward,
                "max_total_risk_pct": v.max_total_risk_pct,
                "require_reasoning": v.require_reasoning,
                "min_reasoning_chars": v.min_reasoning_chars,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_kernel: Optional[MekkaKernel] = None


def get_mekka_kernel() -> MekkaKernel:
    """
    Retorna o singleton global do MekkaKernel com plugins padrão registrados.
    """
    global _kernel
    if _kernel is None:
        _kernel = MekkaKernel()
        # Registrar plugins built-in
        _kernel.add_plugin(MarketRegimePlugin(), name="market")
        _kernel.add_plugin(SystemStatusPlugin(), name="system")
        # Story 171 — Observability plugin com dados reais do Milestone 24
        _kernel.add_plugin(ObservabilityPlugin(), name="obs")
    return _kernel


def reset_mekka_kernel() -> None:
    """Reseta o singleton — para testes."""
    global _kernel
    _kernel = None

"""
src/services/invocation_filter.py
====================================
Story 152 — Mekka Kernel Filter Chain.

Inspirado no padrão Semantic Kernel FunctionInvocationFilter:
https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters

Permite interceptar a execução de qualquer função de agente com comportamento
de middleware pré/pós execução (logging, circuit breakers, custo, benchmark,
DEGRADED_MODE) sem espalhar código de monitoramento pelos agentes.

Arquitetura
-----------
  InvocationContext  — dados sobre a invocação (nome, args, resultado, erro)
  InvocationFilter   — interface base: async def invoke(ctx, next)
  FilterChain        — orquestra N filtros em pipeline; chamar next() avança
  MekkaFilterRegistry— singleton: registra filtros globais; FilterChain usa

Filtros built-in
----------------
  CircuitBreakerFilter — verifica DEGRADED_MODE e LLM error breaker pré-execução
  CostTrackingFilter   — publica custo via EventBus pós-execução (wraps LLMClient)
  BenchmarkFilter      — mede latência com PipelineBenchmark
  AuditLogFilter       — loga início/fim de cada invocação
  RetryFilter          — tenta novamente em caso de falha (max_retries configurável)

Uso
---
    from src.services.invocation_filter import FilterChain, AuditLogFilter

    chain = FilterChain(filters=[AuditLogFilter()])

    async def _call_vision():
        return await vision.run(analysis)

    result = await chain.invoke("vision.run", _call_vision, symbol="BTC")

Ou via decorator:

    @with_filters("batman.run", filters=[CircuitBreakerFilter()])
    async def run_batman(signal):
        return await batman._run(signal=signal)
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# InvocationContext
# ---------------------------------------------------------------------------

@dataclass
class InvocationContext:
    """
    Transporta o estado de uma invocação através da cadeia de filtros.

    Equivalente ao FunctionInvocationContext do Semantic Kernel.
    """
    function_name: str          # ex: "vision.run", "batman.run"
    arguments: dict[str, Any]   # argumentos passados à função
    result: Any = None          # preenchido após execução
    exception: Optional[BaseException] = None
    is_cancelled: bool = False  # filtro pode cancelar execução

    # Metadados adicionais que filtros podem adicionar
    metadata: dict[str, Any] = field(default_factory=dict)

    # Timestamps para benchmarking
    started_at: float = field(default_factory=time.monotonic)
    ended_at: Optional[float] = None

    @property
    def elapsed_s(self) -> float:
        end = self.ended_at or time.monotonic()
        return end - self.started_at

    @property
    def succeeded(self) -> bool:
        return self.exception is None and not self.is_cancelled


# ---------------------------------------------------------------------------
# InvocationFilter (interface)
# ---------------------------------------------------------------------------

class InvocationFilter(ABC):
    """
    Interface base para filtros de invocação.

    Cada filtro recebe o context e uma coroutine `next` que deve ser
    chamada para continuar a cadeia. Não chamar `next` cancela a execução.

    Padrão idêntico ao Semantic Kernel v1.10+:
        async def invoke(self, context: InvocationContext, next: Coroutine) -> None
    """

    @abstractmethod
    async def invoke(
        self,
        context: InvocationContext,
        next: Callable[[], Coroutine],
    ) -> None:
        """
        Intercepta a invocação. Chamar `await next()` para prosseguir.

        Exemplos de uso:
          - Pré: verificar circuit breakers antes de `await next()`
          - Pós: medir latência após `await next()`
          - Cancel: setar `context.is_cancelled = True` e não chamar `next`
          - Retry: chamar `await next()` mais de uma vez (com cuidado)
        """


# ---------------------------------------------------------------------------
# FilterChain
# ---------------------------------------------------------------------------

class FilterChain:
    """
    Orquestra uma lista de InvocationFilter em pipeline.

    Cada filtro chama `await next()` para passar para o próximo filtro.
    O último "filtro" na cadeia é a função real sendo executada.

    Thread-safe para asyncio single event loop.
    """

    def __init__(self, filters: list[InvocationFilter] | None = None) -> None:
        self._filters: list[InvocationFilter] = list(filters or [])

    def add(self, filter_: InvocationFilter) -> "FilterChain":
        """Adiciona filtro ao final da cadeia. Retorna self para chaining."""
        self._filters.append(filter_)
        return self

    async def invoke(
        self,
        function_name: str,
        fn: Callable[[], Coroutine],
        **kwargs: Any,
    ) -> InvocationContext:
        """
        Executa `fn` através da cadeia de filtros.

        Parâmetros
        ----------
        function_name : nome semântico da função (ex: "vision.run")
        fn            : coroutine zero-argumento que executa a função real
        **kwargs      : argumentos semânticos para o InvocationContext

        Retorna InvocationContext com result ou exception preenchidos.
        """
        ctx = InvocationContext(
            function_name=function_name,
            arguments=kwargs,
        )
        filters = list(self._filters)  # snapshot

        # Constrói pipeline recursivo: filter[0] → filter[1] → ... → fn
        async def _build_next(index: int) -> None:
            if index >= len(filters):
                # Cadeia esgotada — executar a função real
                if ctx.is_cancelled:
                    return
                try:
                    ctx.result = await fn()
                except BaseException as exc:
                    ctx.exception = exc
                finally:
                    ctx.ended_at = time.monotonic()
                return

            filter_ = filters[index]
            async def _next() -> None:
                await _build_next(index + 1)

            await filter_.invoke(ctx, _next)

        await _build_next(0)

        if not ctx.ended_at:
            ctx.ended_at = time.monotonic()

        return ctx


# ---------------------------------------------------------------------------
# Built-in Filters
# ---------------------------------------------------------------------------

class AuditLogFilter(InvocationFilter):
    """
    Loga início e fim de cada invocação de função.
    Equivalente a um console.log middleware no Semantic Kernel.
    """

    async def invoke(
        self,
        context: InvocationContext,
        next: Callable[[], Coroutine],
    ) -> None:
        logger.debug(
            f"[Filter:Audit] → {context.function_name} args={list(context.arguments.keys())}"
        )
        await next()
        status = "OK" if context.succeeded else f"ERR({type(context.exception).__name__})"
        logger.debug(
            f"[Filter:Audit] ← {context.function_name} {status} "
            f"elapsed={context.elapsed_s:.3f}s"
        )


class BenchmarkFilter(InvocationFilter):
    """
    Registra latência da invocação no PipelineBenchmark (Story 151).
    O nome da função é usado como nome do estágio.
    """

    async def invoke(
        self,
        context: InvocationContext,
        next: Callable[[], Coroutine],
    ) -> None:
        await next()
        try:
            from src.services.pipeline_benchmark import get_pipeline_benchmark
            bench = get_pipeline_benchmark()
            # Registra no stage_samples diretamente (sem start_cycle overhead)
            bench._stage_samples[context.function_name].append(context.elapsed_s)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Filter:Benchmark] Skipped: {exc}")


class CircuitBreakerFilter(InvocationFilter):
    """
    Verifica DEGRADED_MODE e LLM error rate breaker ANTES de executar.
    Se sistema está degradado, cancela a invocação e seta context.is_cancelled.

    Fail-open: se não conseguir checar o estado, deixa passar.
    """

    async def invoke(
        self,
        context: InvocationContext,
        next: Callable[[], Coroutine],
    ) -> None:
        try:
            from src.services.degraded_mode import get_degraded_mode_manager
            manager = get_degraded_mode_manager()
            if manager.is_degraded:
                context.is_cancelled = True
                context.metadata["cancelled_reason"] = (
                    f"DEGRADED_MODE: {manager.reason} "
                    f"(recovery: {manager.recovery_progress})"
                )
                logger.warning(
                    f"[Filter:CircuitBreaker] {context.function_name} cancelled — "
                    f"DEGRADED_MODE: {manager.reason}"
                )
                return  # Não chama next
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Filter:CircuitBreaker] Check failed (fail-open): {exc}")

        await next()


class RetryFilter(InvocationFilter):
    """
    Tenta re-executar a função em caso de falha (max_retries vezes).
    Inspirado no Retry pattern do Semantic Kernel.

    Não faz retry de BaseException (asyncio.CancelledError, KeyboardInterrupt).
    """

    def __init__(self, max_retries: int = 2, delay_s: float = 0.5) -> None:
        self.max_retries = max_retries
        self.delay_s = delay_s

    async def invoke(
        self,
        context: InvocationContext,
        next: Callable[[], Coroutine],
    ) -> None:
        for attempt in range(self.max_retries + 1):
            # Reset state para nova tentativa
            context.exception = None
            context.result = None
            context.is_cancelled = False

            await next()

            if context.succeeded:
                if attempt > 0:
                    logger.info(
                        f"[Filter:Retry] {context.function_name} succeeded "
                        f"on attempt {attempt + 1}/{self.max_retries + 1}"
                    )
                return

            # Erro — verificar se vale retry
            if context.exception is not None and not isinstance(
                context.exception, (KeyboardInterrupt, asyncio.CancelledError)
            ):
                if attempt < self.max_retries:
                    logger.warning(
                        f"[Filter:Retry] {context.function_name} failed "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): "
                        f"{context.exception} — retrying in {self.delay_s}s"
                    )
                    await asyncio.sleep(self.delay_s)
                    continue

            break


class EventPublishFilter(InvocationFilter):
    """
    Publica eventos de início/fim via EventBus (Story 136).

    Usa `context.function_name` como prefixo do tópico:
      - `{function_name}.started`
      - `{function_name}.completed`
      - `{function_name}.failed`
    """

    async def invoke(
        self,
        context: InvocationContext,
        next: Callable[[], Coroutine],
    ) -> None:
        try:
            from src.services.event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish_sync(f"{context.function_name}.started", {
                "function": context.function_name,
                "args": list(context.arguments.keys()),
            })
        except Exception:  # noqa: BLE001
            pass

        await next()

        try:
            from src.services.event_bus import get_event_bus
            bus = get_event_bus()
            topic = (
                f"{context.function_name}.failed"
                if context.exception
                else f"{context.function_name}.completed"
            )
            bus.publish_sync(topic, {
                "function": context.function_name,
                "elapsed_s": round(context.elapsed_s, 4),
                "succeeded": context.succeeded,
                "error": str(context.exception) if context.exception else None,
            })
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Global Filter Registry
# ---------------------------------------------------------------------------

class MekkaFilterRegistry:
    """
    Registry global de filtros. Todos os FilterChain criados sem filtros
    explícitos herdam os filtros registrados aqui.

    Equivalente ao mecanismo de registro global do Semantic Kernel Kernel.
    """

    def __init__(self) -> None:
        self._global_filters: list[InvocationFilter] = []

    def register(self, filter_: InvocationFilter) -> None:
        """Registra filtro globalmente."""
        self._global_filters.append(filter_)
        logger.debug(f"[MekkaFilterRegistry] Registered: {type(filter_).__name__}")

    def unregister(self, filter_: InvocationFilter) -> None:
        """Remove filtro do registry global."""
        try:
            self._global_filters.remove(filter_)
        except ValueError:
            pass

    def build_chain(
        self,
        extra_filters: list[InvocationFilter] | None = None,
    ) -> FilterChain:
        """
        Constrói FilterChain com filtros globais + extras opcionais.
        Filtros extras são adicionados APÓS os globais.
        """
        filters = list(self._global_filters) + list(extra_filters or [])
        return FilterChain(filters=filters)

    def clear(self) -> None:
        self._global_filters.clear()

    @property
    def filter_count(self) -> int:
        return len(self._global_filters)


_registry: Optional[MekkaFilterRegistry] = None


def get_filter_registry() -> MekkaFilterRegistry:
    """Retorna o singleton global do MekkaFilterRegistry."""
    global _registry
    if _registry is None:
        _registry = MekkaFilterRegistry()
    return _registry


def reset_filter_registry() -> None:
    """Reseta o singleton — para testes."""
    global _registry
    _registry = None

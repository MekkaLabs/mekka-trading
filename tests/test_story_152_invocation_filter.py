"""
tests/test_story_152_invocation_filter.py
==========================================
Story 152 — Mekka Kernel Filter Chain.

Testa o pipeline de filtros inspirado no Semantic Kernel FunctionInvocationFilter:
InvocationContext, FilterChain, filtros built-in (Audit, Benchmark, CircuitBreaker,
Retry, EventPublish) e o MekkaFilterRegistry.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# InvocationContext
# ---------------------------------------------------------------------------

class TestInvocationContext:
    def test_initial_state(self):
        from src.services.invocation_filter import InvocationContext
        ctx = InvocationContext(function_name="test.fn", arguments={"a": 1})
        assert ctx.function_name == "test.fn"
        assert ctx.result is None
        assert ctx.exception is None
        assert not ctx.is_cancelled

    def test_succeeded_true_when_no_error(self):
        from src.services.invocation_filter import InvocationContext
        ctx = InvocationContext(function_name="test.fn", arguments={})
        ctx.result = "ok"
        assert ctx.succeeded

    def test_succeeded_false_when_exception(self):
        from src.services.invocation_filter import InvocationContext
        ctx = InvocationContext(function_name="test.fn", arguments={})
        ctx.exception = ValueError("boom")
        assert not ctx.succeeded

    def test_elapsed_s_positive(self):
        from src.services.invocation_filter import InvocationContext
        import time
        ctx = InvocationContext(function_name="test.fn", arguments={})
        time.sleep(0.01)
        ctx.ended_at = time.monotonic()
        assert ctx.elapsed_s >= 0.005


# ---------------------------------------------------------------------------
# FilterChain — basic
# ---------------------------------------------------------------------------

class TestFilterChain:
    @pytest.mark.asyncio
    async def test_runs_function_without_filters(self):
        from src.services.invocation_filter import FilterChain
        chain = FilterChain()
        ctx = await chain.invoke("fn", lambda: _coro("result"))
        assert ctx.result == "result"
        assert ctx.succeeded

    @pytest.mark.asyncio
    async def test_captures_exception(self):
        from src.services.invocation_filter import FilterChain

        async def _fail():
            raise RuntimeError("test error")

        chain = FilterChain()
        ctx = await chain.invoke("fn", _fail)
        assert ctx.exception is not None
        assert isinstance(ctx.exception, RuntimeError)

    @pytest.mark.asyncio
    async def test_filter_runs_pre_and_post(self):
        from src.services.invocation_filter import FilterChain, InvocationFilter, InvocationContext
        from typing import Callable, Coroutine

        calls = []

        class TrackingFilter(InvocationFilter):
            async def invoke(self, ctx: InvocationContext, next: Callable) -> None:
                calls.append("pre")
                await next()
                calls.append("post")

        chain = FilterChain(filters=[TrackingFilter()])
        await chain.invoke("fn", lambda: _coro("ok"))
        assert calls == ["pre", "post"]

    @pytest.mark.asyncio
    async def test_filter_can_cancel_execution(self):
        from src.services.invocation_filter import FilterChain, InvocationFilter, InvocationContext
        from typing import Callable

        class CancelFilter(InvocationFilter):
            async def invoke(self, ctx: InvocationContext, next: Callable) -> None:
                ctx.is_cancelled = True
                # NOT calling next

        executed = []

        async def _fn():
            executed.append(True)
            return "ran"

        chain = FilterChain(filters=[CancelFilter()])
        ctx = await chain.invoke("fn", _fn)
        assert ctx.is_cancelled
        assert len(executed) == 0  # função não foi executada

    @pytest.mark.asyncio
    async def test_multiple_filters_run_in_order(self):
        from src.services.invocation_filter import FilterChain, InvocationFilter, InvocationContext
        from typing import Callable

        order = []

        def make_filter(n):
            class F(InvocationFilter):
                async def invoke(self, ctx: InvocationContext, next: Callable) -> None:
                    order.append(f"pre-{n}")
                    await next()
                    order.append(f"post-{n}")
            return F()

        chain = FilterChain(filters=[make_filter(1), make_filter(2), make_filter(3)])
        await chain.invoke("fn", lambda: _coro("ok"))
        assert order == ["pre-1", "pre-2", "pre-3", "post-3", "post-2", "post-1"]

    @pytest.mark.asyncio
    async def test_filter_can_override_result(self):
        from src.services.invocation_filter import FilterChain, InvocationFilter, InvocationContext
        from typing import Callable

        class OverrideFilter(InvocationFilter):
            async def invoke(self, ctx: InvocationContext, next: Callable) -> None:
                await next()
                ctx.result = "overridden"  # SK pattern: override result post-execution

        chain = FilterChain(filters=[OverrideFilter()])
        ctx = await chain.invoke("fn", lambda: _coro("original"))
        assert ctx.result == "overridden"


# ---------------------------------------------------------------------------
# AuditLogFilter
# ---------------------------------------------------------------------------

class TestAuditLogFilter:
    @pytest.mark.asyncio
    async def test_does_not_block_execution(self):
        from src.services.invocation_filter import FilterChain, AuditLogFilter
        chain = FilterChain(filters=[AuditLogFilter()])
        ctx = await chain.invoke("fn", lambda: _coro("ok"))
        assert ctx.result == "ok"

    @pytest.mark.asyncio
    async def test_passes_through_exception(self):
        from src.services.invocation_filter import FilterChain, AuditLogFilter

        async def _fail():
            raise ValueError("audit test")

        chain = FilterChain(filters=[AuditLogFilter()])
        ctx = await chain.invoke("fn", _fail)
        assert ctx.exception is not None


# ---------------------------------------------------------------------------
# RetryFilter
# ---------------------------------------------------------------------------

class TestRetryFilter:
    @pytest.mark.asyncio
    async def test_no_retry_on_success(self):
        from src.services.invocation_filter import FilterChain, RetryFilter

        calls = []
        async def _fn():
            calls.append(1)
            return "ok"

        chain = FilterChain(filters=[RetryFilter(max_retries=2, delay_s=0)])
        ctx = await chain.invoke("fn", _fn)
        assert len(calls) == 1
        assert ctx.result == "ok"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        from src.services.invocation_filter import FilterChain, RetryFilter

        calls = []
        async def _fn():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("fail")
            return "ok"

        chain = FilterChain(filters=[RetryFilter(max_retries=3, delay_s=0)])
        ctx = await chain.invoke("fn", _fn)
        assert ctx.result == "ok"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        from src.services.invocation_filter import FilterChain, RetryFilter

        calls = []
        async def _fn():
            calls.append(1)
            raise RuntimeError("always fail")

        chain = FilterChain(filters=[RetryFilter(max_retries=2, delay_s=0)])
        ctx = await chain.invoke("fn", _fn)
        assert ctx.exception is not None
        assert len(calls) == 3  # 1 initial + 2 retries


# ---------------------------------------------------------------------------
# CircuitBreakerFilter
# ---------------------------------------------------------------------------

class TestCircuitBreakerFilter:
    @pytest.mark.asyncio
    async def test_passes_when_normal(self):
        from src.services.invocation_filter import FilterChain, CircuitBreakerFilter
        from src.services.degraded_mode import reset_degraded_mode_manager

        reset_degraded_mode_manager()
        chain = FilterChain(filters=[CircuitBreakerFilter()])
        ctx = await chain.invoke("fn", lambda: _coro("ok"))
        assert ctx.result == "ok"
        assert not ctx.is_cancelled

    @pytest.mark.asyncio
    async def test_cancels_when_degraded(self):
        from src.services.invocation_filter import FilterChain, CircuitBreakerFilter
        from src.services.degraded_mode import get_degraded_mode_manager, reset_degraded_mode_manager

        reset_degraded_mode_manager()
        manager = get_degraded_mode_manager()
        manager.trigger("chaos test")

        executed = []
        async def _fn():
            executed.append(True)
            return "should not run"

        chain = FilterChain(filters=[CircuitBreakerFilter()])
        ctx = await chain.invoke("fn", _fn)

        assert ctx.is_cancelled
        assert len(executed) == 0
        assert "DEGRADED_MODE" in ctx.metadata.get("cancelled_reason", "")

        reset_degraded_mode_manager()


# ---------------------------------------------------------------------------
# MekkaFilterRegistry
# ---------------------------------------------------------------------------

class TestMekkaFilterRegistry:
    def setup_method(self):
        from src.services.invocation_filter import reset_filter_registry
        reset_filter_registry()

    def teardown_method(self):
        from src.services.invocation_filter import reset_filter_registry
        reset_filter_registry()

    def test_empty_registry(self):
        from src.services.invocation_filter import get_filter_registry
        r = get_filter_registry()
        assert r.filter_count == 0

    def test_register_filter(self):
        from src.services.invocation_filter import get_filter_registry, AuditLogFilter
        r = get_filter_registry()
        r.register(AuditLogFilter())
        assert r.filter_count == 1

    def test_build_chain_includes_global_filters(self):
        from src.services.invocation_filter import get_filter_registry, AuditLogFilter
        r = get_filter_registry()
        r.register(AuditLogFilter())
        r.register(AuditLogFilter())
        chain = r.build_chain()
        assert len(chain._filters) == 2

    def test_build_chain_with_extras(self):
        from src.services.invocation_filter import get_filter_registry, AuditLogFilter, RetryFilter
        r = get_filter_registry()
        r.register(AuditLogFilter())
        chain = r.build_chain(extra_filters=[RetryFilter()])
        assert len(chain._filters) == 2  # 1 global + 1 extra

    def test_singleton(self):
        from src.services.invocation_filter import get_filter_registry
        r1 = get_filter_registry()
        r2 = get_filter_registry()
        assert r1 is r2


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _coro(value):
    return value

"""
tests/test_story_153_mekka_kernel.py
======================================
Story 153 — @mekka_function + MekkaPlugin Registry.

Testa o decorator @mekka_function, MekkaPlugin auto-discovery,
MekkaKernel plugin registry, geração de tool_definitions OpenAI,
e dispatch de function calls.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# @mekka_function decorator
# ---------------------------------------------------------------------------

class TestMekkaFunctionDecorator:
    def test_marks_function(self):
        from src.services.mekka_kernel import mekka_function, is_mekka_function

        @mekka_function(description="test fn")
        async def my_fn(symbol: str) -> str:
            return symbol

        assert is_mekka_function(my_fn)

    def test_stores_description(self):
        from src.services.mekka_kernel import mekka_function, get_mekka_metadata

        @mekka_function(description="Get market price")
        async def get_price(symbol: str) -> float:
            return 100.0

        meta = get_mekka_metadata(get_price)
        assert meta["description"] == "Get market price"

    def test_uses_function_name_by_default(self):
        from src.services.mekka_kernel import mekka_function, get_mekka_metadata

        @mekka_function(description="test")
        async def analyze_symbol(symbol: str) -> dict:
            return {}

        meta = get_mekka_metadata(analyze_symbol)
        assert meta["name"] == "analyze_symbol"

    def test_custom_name_override(self):
        from src.services.mekka_kernel import mekka_function, get_mekka_metadata

        @mekka_function(description="test", name="custom_name")
        async def original_fn() -> str:
            return ""

        meta = get_mekka_metadata(original_fn)
        assert meta["name"] == "custom_name"

    def test_tags_stored(self):
        from src.services.mekka_kernel import mekka_function, get_mekka_metadata

        @mekka_function(description="test", tags=["trading", "vision"])
        async def my_fn() -> None:
            pass

        meta = get_mekka_metadata(my_fn)
        assert "trading" in meta["tags"]
        assert "vision" in meta["tags"]

    def test_undecorated_function_not_marked(self):
        from src.services.mekka_kernel import is_mekka_function

        async def plain_fn():
            pass

        assert not is_mekka_function(plain_fn)

    @pytest.mark.asyncio
    async def test_decorated_function_still_callable(self):
        from src.services.mekka_kernel import mekka_function

        @mekka_function(description="test")
        async def add(a: int, b: int) -> int:
            return a + b

        result = await add(2, 3)
        assert result == 5


# ---------------------------------------------------------------------------
# MekkaPlugin auto-discovery
# ---------------------------------------------------------------------------

class _SamplePlugin:
    """Plugin de teste com 2 funções decoradas e 1 não-decorada."""

    def __init__(self):
        from src.services.mekka_kernel import mekka_function
        # Não é possível usar decorators em métodos dentro do método,
        # então criamos as funções fora e as adicionamos aqui
        pass

    # As funções são definidas abaixo como métodos de classe


def _make_plugin_class():
    """Cria classe plugin dinâmica com @mekka_function."""
    from src.services.mekka_kernel import mekka_function

    class TradingPlugin:
        @mekka_function(description="Analyze trading signal", tags=["trading"])
        async def analyze(self, symbol: str, confidence: float = 0.7) -> dict:
            return {"symbol": symbol, "confidence": confidence}

        @mekka_function(description="Get current risk status", tags=["risk"])
        async def get_risk(self) -> dict:
            return {"ok": True}

        async def _private_method(self):
            return "not exposed"

        async def plain_method(self):
            return "also not exposed"

    return TradingPlugin


class TestMekkaPlugin:
    def test_discovers_decorated_functions(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        assert "analyze" in plugin.function_names
        assert "get_risk" in plugin.function_names

    def test_does_not_expose_plain_methods(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        assert "plain_method" not in plugin.function_names
        assert "_private_method" not in plugin.function_names

    def test_schema_generated_for_each_function(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        schemas = plugin.schemas
        assert len(schemas) == 2

    def test_schema_has_correct_description(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        schema = plugin.get_schema("analyze")
        assert schema.description == "Analyze trading signal"

    def test_schema_properties_from_type_hints(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        schema = plugin.get_schema("analyze")
        props = schema.parameters["properties"]
        assert "symbol" in props
        assert "confidence" in props
        assert props["symbol"]["type"] == "string"
        assert props["confidence"]["type"] == "number"

    def test_required_params_without_default(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        schema = plugin.get_schema("analyze")
        assert "symbol" in schema.parameters["required"]
        assert "confidence" not in schema.parameters["required"]

    @pytest.mark.asyncio
    async def test_invoke_function(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        result = await plugin.invoke("analyze", symbol="BTC", confidence=0.85)
        assert result["symbol"] == "BTC"

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_raises(self):
        from src.services.mekka_kernel import MekkaPlugin
        cls = _make_plugin_class()
        plugin = MekkaPlugin(cls(), name="trading")
        with pytest.raises(KeyError):
            await plugin.invoke("nonexistent")


# ---------------------------------------------------------------------------
# MekkaKernel
# ---------------------------------------------------------------------------

class TestMekkaKernel:
    def setup_method(self):
        from src.services.mekka_kernel import reset_mekka_kernel
        reset_mekka_kernel()

    def teardown_method(self):
        from src.services.mekka_kernel import reset_mekka_kernel
        reset_mekka_kernel()

    def _make_kernel(self):
        from src.services.mekka_kernel import MekkaKernel
        cls = _make_plugin_class()
        kernel = MekkaKernel()
        kernel.add_plugin(cls(), name="trading")
        return kernel

    def test_add_plugin_registers(self):
        kernel = self._make_kernel()
        assert "trading" in kernel.plugin_names

    def test_get_tool_definitions(self):
        kernel = self._make_kernel()
        tools = kernel.get_tool_definitions()
        assert len(tools) == 2
        tool_names = [t["function"]["name"] for t in tools]
        assert "trading__analyze" in tool_names
        assert "trading__get_risk" in tool_names

    def test_tool_definition_format(self):
        kernel = self._make_kernel()
        tools = kernel.get_tool_definitions()
        tool = next(t for t in tools if "analyze" in t["function"]["name"])
        assert tool["type"] == "function"
        assert "parameters" in tool["function"]
        assert "description" in tool["function"]

    def test_filter_tools_by_tag(self):
        kernel = self._make_kernel()
        trading_tools = kernel.get_tool_definitions(tags=["trading"])
        assert len(trading_tools) == 1
        assert "analyze" in trading_tools[0]["function"]["name"]

    @pytest.mark.asyncio
    async def test_invoke_plugin_function(self):
        kernel = self._make_kernel()
        result = await kernel.invoke("trading", "analyze", symbol="ETH")
        assert result["symbol"] == "ETH"

    @pytest.mark.asyncio
    async def test_invoke_unknown_plugin_raises(self):
        kernel = self._make_kernel()
        with pytest.raises(KeyError):
            await kernel.invoke("unknown_plugin", "fn")

    @pytest.mark.asyncio
    async def test_invoke_from_tool_call(self):
        kernel = self._make_kernel()
        import json
        result = await kernel.invoke_from_tool_call(
            name="trading__analyze",
            arguments_json=json.dumps({"symbol": "SOL"}),
        )
        assert result["symbol"] == "SOL"

    @pytest.mark.asyncio
    async def test_invoke_from_tool_call_invalid_format(self):
        kernel = self._make_kernel()
        with pytest.raises(ValueError, match="format"):
            await kernel.invoke_from_tool_call(name="no_separator")

    @pytest.mark.asyncio
    async def test_invoke_from_tool_call_invalid_json(self):
        kernel = self._make_kernel()
        with pytest.raises(ValueError, match="JSON"):
            await kernel.invoke_from_tool_call(
                name="trading__analyze",
                arguments_json="{invalid_json}",
            )

    def test_describe(self):
        kernel = self._make_kernel()
        desc = kernel.describe()
        assert "trading" in desc
        assert "analyze" in desc


# ---------------------------------------------------------------------------
# Built-in Plugins
# ---------------------------------------------------------------------------

class TestBuiltinPlugins:
    def setup_method(self):
        from src.services.mekka_kernel import reset_mekka_kernel
        reset_mekka_kernel()

    def teardown_method(self):
        from src.services.mekka_kernel import reset_mekka_kernel
        reset_mekka_kernel()

    def test_market_plugin_registered(self):
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        assert "market" in kernel.plugin_names

    def test_system_plugin_registered(self):
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        assert "system" in kernel.plugin_names

    @pytest.mark.asyncio
    async def test_detect_regime_callable(self):
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        result = await kernel.invoke(
            "market", "detect_regime",
            btc_trend="BULLISH", btc_rsi=65.0, btc_atr_pct=0.02
        )
        assert "regime" in result
        assert result["regime"] == "BULL"

    @pytest.mark.asyncio
    async def test_classify_asset_callable(self):
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        result = await kernel.invoke(
            "market", "classify_asset",
            symbol="BTC", price=50000.0
        )
        assert "cap_tier" in result
        assert result["cap_tier"] == "LARGE_CAP"

    @pytest.mark.asyncio
    async def test_get_system_status_callable(self):
        from src.services.mekka_kernel import get_mekka_kernel
        from src.services.degraded_mode import reset_degraded_mode_manager
        reset_degraded_mode_manager()
        kernel = get_mekka_kernel()
        result = await kernel.invoke("system", "get_system_status")
        assert "is_degraded" in result
        assert result["is_degraded"] is False

    def test_tool_definitions_include_builtin_plugins(self):
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        tools = kernel.get_tool_definitions()
        names = [t["function"]["name"] for t in tools]
        assert "market__detect_regime" in names
        assert "market__classify_asset" in names
        assert "system__get_system_status" in names
        assert "system__get_llm_costs" in names
        assert "system__get_pipeline_benchmarks" in names

    def test_singleton_returns_same_kernel(self):
        from src.services.mekka_kernel import get_mekka_kernel
        k1 = get_mekka_kernel()
        k2 = get_mekka_kernel()
        assert k1 is k2

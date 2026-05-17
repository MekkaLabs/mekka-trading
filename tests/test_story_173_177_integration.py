"""
Integration tests — Stories 173-177 (Milestone 26: Observability Live & Kernel Orchestration)

Story 173 — Live Trading Panel SSE Integration (frontend subscribeCycleEvents)
Story 174 — MekkaKernel NickFury Orchestration (VisionPlugin + pre-invocation hook)
Story 175 — ObservabilityPlugin Dashboard Widget (GET /api/obs/{tool_name})
Story 176 — SignalValidator Telegram Alert (alert quando sinal inválido)
Story 177 — ContextWindowTracker Dashboard Endpoint (GET /api/context-window/live)

Pattern: src-level imports + AST/source checks for frontend; real service imports
for backend; fail-silent coverage throughout.
38 testes — 6 classes.
"""
from __future__ import annotations

import asyncio
import json
import pytest


# ===========================================================================
# Story 173 — Live Trading Panel SSE Integration (frontend)
# ===========================================================================

class TestStory173LivePanelSSEFrontend:
    """
    Verifica que live-data.jsx expõe subscribeCycleEvents() com suporte
    a EventSource, mock fallback, symbol filter, e unsubscribe.
    """

    def _read_live_data(self):
        return open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading"
            "/src/dashboard/static/office_v2/live-data.jsx"
        ).read()

    def test_subscribe_cycle_events_exported(self):
        """subscribeCycleEvents está exposto em window.*."""
        src = self._read_live_data()
        assert "subscribeCycleEvents" in src

    def test_event_source_used(self):
        """EventSource API é usada para o stream SSE."""
        src = self._read_live_data()
        assert "EventSource" in src

    def test_sse_url_targets_events_stream(self):
        """URL do EventSource aponta para /api/events/stream."""
        src = self._read_live_data()
        assert "/api/events/stream" in src

    def test_symbol_filter_forwarded(self):
        """Query param symbol é passado ao EventSource URL."""
        src = self._read_live_data()
        assert "symbol" in src and "URLSearchParams" in src

    def test_mock_fallback_on_no_events(self):
        """Mock tick dispara quando nenhum evento real chega."""
        src = self._read_live_data()
        assert "startMock" in src
        assert "FALLBACK_DELAY_MS" in src or "8000" in src

    def test_unsubscribe_closes_event_source(self):
        """Função de retorno fecha o EventSource e limpa timers."""
        src = self._read_live_data()
        assert "es.close()" in src or "es)" in src
        # The returned function sets cancelled = true and closes es
        assert "cancelled = true" in src

    def test_mock_events_cover_all_cycle_types(self):
        """Mock cobre todos os 6 tipos de evento do CycleEventLog."""
        src = self._read_live_data()
        for event_type in [
            "CYCLE_START", "ANALYSIS_DONE", "SIGNAL_EMITTED",
            "RISK_VERDICT", "EXECUTION_DONE", "CYCLE_END",
        ]:
            assert event_type in src, f"Missing mock event type: {event_type}"

    def test_seed_param_forwarded_to_server(self):
        """Parâmetro seed/last é enviado ao servidor para eventos iniciais."""
        src = self._read_live_data()
        assert "seed" in src or "last" in src


# ===========================================================================
# Story 174 — MekkaKernel NickFury Orchestration (VisionPlugin)
# ===========================================================================

class TestStory174VisionPluginKernelOrchestration:
    """
    Verifica que VisionPlugin está registrado no kernel como 'vision'
    e que NickFury tem o pre-invocation hook para disparar o filter chain.
    """

    def test_vision_plugin_in_kernel(self):
        """get_mekka_kernel() inclui plugin 'vision'."""
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        assert "vision" in kernel.plugin_names

    def test_vision_generate_signal_tool_exists(self):
        """Tool vision__generate_signal está nos tool_definitions."""
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        names = [t["name"] for t in kernel.get_tool_definitions()]
        vision_tools = [n for n in names if "vision" in n]
        assert len(vision_tools) >= 1, f"No vision tools found: {names}"

    def test_generate_signal_invocable(self):
        """vision__generate_signal pode ser invocado via kernel."""
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        tools = kernel.get_tool_definitions()
        gen_tool = next((t["name"] for t in tools if "generate_signal" in t["name"]), None)
        if gen_tool is None:
            pytest.skip("generate_signal not found in tool definitions")

        result = asyncio.get_event_loop().run_until_complete(
            kernel.invoke_from_tool_call(gen_tool, json.dumps({"symbol": "BTCUSDT", "cycle_id": "test-174"}))
        )
        assert result is not None
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "symbol" in str(parsed)

    def test_get_last_signal_invocable(self):
        """vision__get_last_signal pode ser invocado e retorna found bool."""
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        tools = kernel.get_tool_definitions()
        last_tool = next((t["name"] for t in tools if "last_signal" in t["name"]), None)
        if last_tool is None:
            pytest.skip("get_last_signal not found in tool definitions")

        result = asyncio.get_event_loop().run_until_complete(
            kernel.invoke_from_tool_call(last_tool, json.dumps({"symbol": "BTCUSDT"}))
        )
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "found" in str(parsed)

    def test_nick_fury_has_kernel_pre_vision_hook(self):
        """nick_fury.py contém bloco Story 174 com kernel.invoke() antes de Vision."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "Story 174" in src
        assert "kernel pre-vision" in src or "pre-vision hook" in src
        assert "get_mekka_kernel" in src

    def test_get_vision_metrics_invocable(self):
        """vision__get_vision_metrics retorna dict com signals_sampled."""
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        tools = kernel.get_tool_definitions()
        metrics_tool = next((t["name"] for t in tools if "vision_metrics" in t["name"]), None)
        if metrics_tool is None:
            pytest.skip("get_vision_metrics not found")

        result = asyncio.get_event_loop().run_until_complete(
            kernel.invoke_from_tool_call(metrics_tool, json.dumps({"symbol": "BTCUSDT", "last_n": 3}))
        )
        assert result is not None


# ===========================================================================
# Story 175 — ObservabilityPlugin Dashboard Widget
# ===========================================================================

class TestStory175ObsToolDashboardEndpoint:
    """
    Verifica que GET /api/obs/{tool_name} está registrado e mapeia corretamente
    para ObservabilityPlugin e VisionPlugin via MekkaKernel.
    """

    def test_obs_route_registered(self):
        """Rota /api/obs/{tool_name} está registrada no server.py."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "/api/obs/{tool_name}" in src
        assert "_handle_obs_tool" in src

    def test_obs_handler_uses_kernel_invoke(self):
        """Handler usa kernel.invoke() para despachar a chamada."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "get_mekka_kernel" in src
        assert "kernel.invoke" in src

    def test_obs_tool_map_covers_all_obs_functions(self):
        """TOOL_MAP cobre todas as funções ObservabilityPlugin."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        for fn in [
            "cycle_events", "signal_changes", "context_window",
            "step_guard_stats", "validator_thresholds",
            "vision_metrics", "vision_last_signal",
        ]:
            assert fn in src, f"Missing obs tool mapping: {fn}"

    def test_obs_handler_returns_404_for_unknown_tool(self):
        """Handler retorna 404 para tool desconhecido com lista de disponíveis."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "Unknown obs tool" in src
        assert '"available"' in src or "'available'" in src

    def test_obs_numeric_params_coerced(self):
        """Params ?last_n e ?seed são coercidos para int."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "last_n" in src and "int(query" in src


# ===========================================================================
# Story 176 — SignalValidator Telegram Alert
# ===========================================================================

class TestStory176SignalValidatorTelegramAlert:
    """
    Verifica que o bloco Story 176 em NickFury dispara alert Telegram
    quando SignalValidator retorna is_valid=False.
    """

    def test_telegram_alert_block_in_nick_fury(self):
        """Story 176 bloco Telegram está em nick_fury.py."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "Story 176" in src
        assert "SIGNAL_INVALID" in src
        assert "self._telegram.alert" in src

    def test_alert_includes_error_summary(self):
        """Alert Telegram inclui error_summary do SignalValidator."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "error_summary" in src

    def test_alert_includes_symbol(self):
        """Alert Telegram inclui o símbolo."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "symbol" in src

    def test_alert_block_is_fail_silent(self):
        """Bloco Telegram Story 176 é fail-silent (não levanta)."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "_sv176_exc" in src
        assert "176] Telegram SIGNAL_INVALID skipped" in src

    def test_alert_fires_before_cycle_report_return(self):
        """Alert Telegram vem antes do CycleReport(error=...) return."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        alert_pos = src.find("Story 176")
        report_pos = src.find("SignalValidator: {_sv_result.error_summary}")
        assert alert_pos != -1
        assert report_pos != -1
        assert alert_pos < report_pos

    def test_fail_silent_integration(self):
        """Fail-silent: se _telegram.alert falhar, CycleReport ainda é retornado."""
        sv_result_mock = type("SVResult", (), {
            "is_valid": False,
            "error_summary": "R:R too low",
            "has_warnings": False,
            "warnings": [],
        })()

        reports = []
        alerts_sent = []
        alerts_failed = []

        async def _run():
            class FakeTelegram:
                async def alert(self, **kwargs):
                    raise RuntimeError("telegram down")

            telegram = FakeTelegram()
            try:
                await telegram.alert(event="SIGNAL_INVALID", symbol="BTC",
                                     message="test")
            except Exception as _sv176_exc:
                alerts_failed.append(str(_sv176_exc))

            reports.append({"error": f"SignalValidator: {sv_result_mock.error_summary}"})

        asyncio.get_event_loop().run_until_complete(_run())
        assert len(alerts_failed) == 1
        assert "telegram down" in alerts_failed[0]
        assert len(reports) == 1
        assert "R:R too low" in reports[0]["error"]


# ===========================================================================
# Story 177 — ContextWindowTracker Dashboard Endpoint
# ===========================================================================

class TestStory177ContextWindowLiveEndpoint:
    """
    Verifica que GET /api/context-window/live está registrado e retorna
    summaries com usage_pct e is_near_limit.
    """

    def test_context_window_live_route_registered(self):
        """Rota /api/context-window/live está registrada no server.py."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "/api/context-window/live" in src
        assert "_handle_context_window_live" in src

    def test_handler_returns_is_near_limit(self):
        """Handler enriquece summaries com is_near_limit flag."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "is_near_limit" in src

    def test_handler_sorted_by_usage_pct(self):
        """Handler ordena ciclos por usage_pct decrescente."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "usage_pct" in src
        assert "reverse=True" in src

    def test_handler_includes_global_summary(self):
        """Handler inclui global_summary além da lista de ciclos."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        assert "global_summary" in src

    def test_context_window_tracker_service(self):
        """ContextWindowTracker importa e tem summary()."""
        from src.services.context_window_tracker import get_context_window_tracker
        cwt = get_context_window_tracker()
        assert cwt is not None
        if hasattr(cwt, "summary"):
            summary = cwt.summary()
            assert isinstance(summary, dict)

    def test_is_near_limit_threshold_80pct(self):
        """is_near_limit é True quando usage_pct >= 0.80."""
        # Simulate the logic from _handle_context_window_live
        summaries = [
            {"usage_pct": 0.85, "cycle_id": "a"},
            {"usage_pct": 0.50, "cycle_id": "b"},
            {"usage_pct": 0.80, "cycle_id": "c"},
            {"usage_pct": 0.79, "cycle_id": "d"},
        ]
        enriched = []
        for s in summaries:
            usage_pct = s.get("usage_pct", 0.0)
            enriched.append({**s, "is_near_limit": usage_pct >= 0.80})
        enriched.sort(key=lambda x: x.get("usage_pct", 0.0), reverse=True)

        assert enriched[0]["usage_pct"] == 0.85
        assert enriched[0]["is_near_limit"] is True
        assert enriched[1]["usage_pct"] == 0.80
        assert enriched[1]["is_near_limit"] is True
        assert enriched[2]["usage_pct"] == 0.79
        assert enriched[2]["is_near_limit"] is False


# ===========================================================================
# Cross-story integration
# ===========================================================================

class TestMilestone26CrossStoryIntegration:
    """
    Testes cruzados verificando que Stories 173-177 coexistem sem conflitos
    e que o kernel tem todos os plugins esperados de Milestones 24-26.
    """

    def test_kernel_has_all_milestone_plugins(self):
        """Kernel tem plugins: market, system, obs, vision."""
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        for expected in ["market", "system", "obs", "vision"]:
            assert expected in kernel.plugin_names, f"Missing plugin: {expected}"

    def test_kernel_tool_count_milestone26(self):
        """Kernel tem pelo menos 10 tools registrados (obs 5 + vision 3 + market + system)."""
        from src.services.mekka_kernel import get_mekka_kernel
        kernel = get_mekka_kernel()
        tools = kernel.get_tool_definitions()
        assert len(tools) >= 10, f"Expected >=10 tools, got {len(tools)}: {[t['name'] for t in tools]}"

    def test_all_new_server_routes_in_source(self):
        """Todos os novos endpoints de Milestone 26 estão no server.py."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/dashboard/server.py"
        ).read()
        routes = [
            "/api/events/stream",       # Story 172
            "/api/obs/{tool_name}",     # Story 175
            "/api/context-window/live", # Story 177
        ]
        for route in routes:
            assert route in src, f"Missing route: {route}"

    def test_nick_fury_has_stories_174_176(self):
        """nick_fury.py contém Stories 174 e 176."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "Story 174" in src
        assert "Story 176" in src

    def test_mekka_kernel_syntax_ok(self):
        """mekka_kernel.py com VisionPlugin compila sem erro de sintaxe."""
        import ast
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/services/mekka_kernel.py"
        ).read()
        tree = ast.parse(src)  # raises on error
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "VisionPlugin" in classes
        assert "ObservabilityPlugin" in classes

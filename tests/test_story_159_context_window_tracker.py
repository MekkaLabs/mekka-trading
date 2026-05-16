"""
tests/test_story_159_context_window_tracker.py
================================================
Story 159 — ContextWindowTracker: Pipeline Context Window Management.

Inspirado no ContextWindowManager do SWE-agent:
  "The LLM Controller handles context window management, prompt injection,
   and output parsing."
  "last_n_observations: drops all but the most recent N observations."
  "if output length < 10,000 characters → full output; else → truncate"

Testa:
- _estimate_tokens: str, list, dict, int, empty
- CycleWindow: total_tokens, token_limit, usage_pct, is_near_limit, to_dict
- ContextWindowTracker.start_cycle: criação, eviction FIFO, fail-silent
- ContextWindowTracker.record_stage: contagem tokens, auto-create cycle
- ContextWindowTracker.check_limit: True/False por pct, ciclo não existente
- ContextWindowTracker.cycle_summary: found=True/False, to_dict shape
- ContextWindowTracker.get_top_consumers: ordenação por tokens
- ContextWindowTracker.summary: distribuição por stage, near_limit, top
- ContextWindowTracker.compress_history: SWE-agent last_n_observations
- MODEL_TOKEN_LIMITS: modelos conhecidos presentes
- Singleton: get/reset
- Fail-silent: nunca levanta exceção
"""

from __future__ import annotations


def _load_modules():
    """Carrega ContextWindowTracker mockando loguru e EventBus."""
    import sys
    import types
    import importlib.util

    # Mock loguru
    if 'loguru' not in sys.modules:
        loguru_mod = types.ModuleType('loguru')
        class FL:
            def warning(self, *a, **k): pass
            def debug(self, *a, **k): pass
            def error(self, *a, **k): pass
            def info(self, *a, **k): pass
        loguru_mod.logger = FL()
        sys.modules['loguru'] = loguru_mod

    # Mock src.services.event_bus
    src_mod = types.ModuleType('src')
    src_services = types.ModuleType('src.services')
    src_event_bus = types.ModuleType('src.services.event_bus')
    class FakeEventBus:
        def publish(self, event, payload): pass
    src_event_bus.get_event_bus = lambda: FakeEventBus()
    sys.modules.setdefault('src', src_mod)
    sys.modules.setdefault('src.services', src_services)
    sys.modules['src.services.event_bus'] = src_event_bus

    # Load context_window_tracker
    spec = importlib.util.spec_from_file_location(
        'ctx_tracker',
        'src/services/context_window_tracker.py',
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules['ctx_tracker'] = mod
    spec.loader.exec_module(mod)

    # Reset singleton for isolation
    mod.reset_context_window_tracker()
    return mod


# ---------------------------------------------------------------------------
# TestEstimateTokens
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_string_estimate(self):
        mod = _load_modules()
        est = mod._estimate_tokens("a" * 400)
        assert 90 <= est <= 110  # ~100 tokens

    def test_empty_string(self):
        mod = _load_modules()
        # string vazia → max(1, 0//4) = 1 (mínimo)
        est = mod._estimate_tokens("")
        assert est >= 0

    def test_int_passthrough(self):
        mod = _load_modules()
        # int é interpretado como já sendo token count
        assert mod._estimate_tokens(42) == 42

    def test_list_estimate(self):
        mod = _load_modules()
        data = list(range(100))
        est = mod._estimate_tokens(data)
        assert est > 0  # JSON dump de 100 ints > 0 tokens

    def test_dict_estimate(self):
        mod = _load_modules()
        data = {"key": "value", "num": 42}
        est = mod._estimate_tokens(data)
        assert est > 0

    def test_fail_silent(self):
        mod = _load_modules()
        # Objeto não-serializável → deve retornar 0 ou valor seguro
        result = mod._estimate_tokens(object())
        assert isinstance(result, int) and result >= 0


# ---------------------------------------------------------------------------
# TestCycleWindow
# ---------------------------------------------------------------------------

class TestCycleWindow:
    def test_total_tokens_empty(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC")
        assert w.total_tokens == 0

    def test_total_tokens_sum(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="gpt-4o")
        w.stages.append(mod.StageRecord("stage_a", 100))
        w.stages.append(mod.StageRecord("stage_b", 200))
        assert w.total_tokens == 300

    def test_token_limit_known_model(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="gpt-4o")
        assert w.token_limit == 128_000

    def test_token_limit_default_model(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="unknown_model_xyz")
        assert w.token_limit == mod.MODEL_TOKEN_LIMITS["_default"]

    def test_usage_pct_zero_when_empty(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="gpt-4o")
        assert w.usage_pct == 0.0

    def test_usage_pct_calculates(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="gpt-4o")
        w.stages.append(mod.StageRecord("s", 64_000))
        assert abs(w.usage_pct - 0.5) < 0.01

    def test_is_near_limit_false(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="gpt-4o")
        w.stages.append(mod.StageRecord("s", 1_000))
        assert w.is_near_limit(warn_pct=0.80) is False

    def test_is_near_limit_true(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="gpt-4o")
        # 110k of 128k = ~86% > 80%
        w.stages.append(mod.StageRecord("s", 110_000))
        assert w.is_near_limit(warn_pct=0.80) is True

    def test_to_dict_shape(self):
        mod = _load_modules()
        w = mod.CycleWindow(cycle_id="c1", symbol="BTC", model="gpt-4o")
        w.stages.append(mod.StageRecord("vision", 1000))
        d = w.to_dict()
        assert d["cycle_id"] == "c1"
        assert d["symbol"] == "BTC"
        assert d["total_tokens_approx"] == 1000
        assert "usage_pct" in d
        assert "stages" in d
        assert len(d["stages"]) == 1
        assert d["stages"][0]["name"] == "vision"


# ---------------------------------------------------------------------------
# TestContextWindowTrackerStartCycle
# ---------------------------------------------------------------------------

class TestContextWindowTrackerStartCycle:
    def test_start_cycle_creates_window(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        w = tracker.start_cycle("c1", symbol="BTC")
        assert w.cycle_id == "c1"
        assert w.symbol == "BTC"

    def test_start_cycle_uses_model(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        w = tracker.start_cycle("c1", symbol="ETH", model="claude-sonnet-4-6")
        assert w.model == "claude-sonnet-4-6"

    def test_start_cycle_evicts_oldest_at_capacity(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker(max_cycles=3)
        tracker.start_cycle("c1", symbol="A")
        tracker.start_cycle("c2", symbol="B")
        tracker.start_cycle("c3", symbol="C")
        assert "c1" in tracker._cycles
        tracker.start_cycle("c4", symbol="D")
        # c1 deve ter sido evictado
        assert "c1" not in tracker._cycles
        assert "c4" in tracker._cycles

    def test_start_cycle_fail_silent(self):
        """start_cycle não deve levantar exceção mesmo com argumento inválido."""
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        # Não deve levantar
        w = tracker.start_cycle(None, symbol=None)
        assert w is not None


# ---------------------------------------------------------------------------
# TestContextWindowTrackerRecordStage
# ---------------------------------------------------------------------------

class TestContextWindowTrackerRecordStage:
    def test_record_stage_returns_tokens(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tokens = tracker.record_stage("c1", "vision", "a" * 400)
        assert 90 <= tokens <= 110

    def test_record_stage_auto_creates_cycle(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tracker.record_stage("c2", "professor_x", "analysis text" * 10)
        assert "c2" in tracker._cycles

    def test_record_stage_accumulates(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tracker.start_cycle("c3", symbol="BTC")
        tracker.record_stage("c3", "stage_a", "a" * 400)
        tracker.record_stage("c3", "stage_b", "b" * 400)
        summary = tracker.cycle_summary("c3")
        assert summary["total_tokens_approx"] >= 100  # ao menos 2×~100

    def test_record_stage_increments_total(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        before = tracker._total_stages_recorded
        tracker.record_stage("c1", "s1", "text")
        tracker.record_stage("c1", "s2", "text")
        assert tracker._total_stages_recorded == before + 2

    def test_record_stage_fail_silent(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        result = tracker.record_stage(None, None, object())
        assert isinstance(result, int)  # retorna 0 sem levantar


# ---------------------------------------------------------------------------
# TestContextWindowTrackerCheckLimit
# ---------------------------------------------------------------------------

class TestContextWindowTrackerCheckLimit:
    def test_check_limit_false_for_small_cycle(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tracker.start_cycle("c1", symbol="BTC", model="gpt-4o")
        tracker.record_stage("c1", "s", "small text")
        assert tracker.check_limit("c1") is False

    def test_check_limit_true_near_capacity(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker(warn_pct=0.80)
        tracker.start_cycle("c1", symbol="BTC", model="gpt-4o")
        # Adicionar ~110k tokens de um modelo com 128k limit
        tracker.record_stage("c1", "s", 110_000)  # int = já é token count
        assert tracker.check_limit("c1") is True

    def test_check_limit_false_for_unknown_cycle(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        assert tracker.check_limit("nonexistent_cycle") is False

    def test_check_limit_custom_pct(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker(warn_pct=0.80)
        tracker.start_cycle("c1", symbol="BTC", model="gpt-4o")
        tracker.record_stage("c1", "s", 70_000)
        # 70k/128k = 54% — abaixo de 80%
        assert tracker.check_limit("c1", warn_pct=0.80) is False
        # Acima de 50%
        assert tracker.check_limit("c1", warn_pct=0.50) is True


# ---------------------------------------------------------------------------
# TestContextWindowTrackerCycleSummary
# ---------------------------------------------------------------------------

class TestContextWindowTrackerCycleSummary:
    def test_summary_found_true(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tracker.start_cycle("c1", symbol="BTC")
        tracker.record_stage("c1", "vision", "text" * 50)
        s = tracker.cycle_summary("c1")
        assert s["found"] is True
        assert s["cycle_id"] == "c1"

    def test_summary_not_found(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        s = tracker.cycle_summary("nonexistent")
        assert s["found"] is False
        assert s["cycle_id"] == "nonexistent"

    def test_summary_has_stages(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tracker.start_cycle("c1", symbol="ETH")
        tracker.record_stage("c1", "stage_a", "data" * 100)
        tracker.record_stage("c1", "stage_b", "data" * 100)
        s = tracker.cycle_summary("c1")
        assert len(s["stages"]) == 2


# ---------------------------------------------------------------------------
# TestContextWindowTrackerTopConsumers
# ---------------------------------------------------------------------------

class TestContextWindowTrackerTopConsumers:
    def test_top_consumers_ordered_desc(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tracker.start_cycle("small", symbol="A")
        tracker.record_stage("small", "s", 100)
        tracker.start_cycle("large", symbol="B")
        tracker.record_stage("large", "s", 50_000)
        tracker.start_cycle("medium", symbol="C")
        tracker.record_stage("medium", "s", 10_000)
        top = tracker.get_top_consumers(n=3)
        assert top[0]["total_tokens_approx"] >= top[1]["total_tokens_approx"]
        assert top[1]["total_tokens_approx"] >= top[2]["total_tokens_approx"]

    def test_top_consumers_respects_n(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        for i in range(5):
            tracker.start_cycle(f"c{i}", symbol="X")
            tracker.record_stage(f"c{i}", "s", i * 1000)
        top = tracker.get_top_consumers(n=2)
        assert len(top) == 2

    def test_top_consumers_empty_tracker(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        assert tracker.get_top_consumers() == []


# ---------------------------------------------------------------------------
# TestContextWindowTrackerSummary
# ---------------------------------------------------------------------------

class TestContextWindowTrackerSummary:
    def test_summary_empty_tracker(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        s = tracker.summary()
        assert s["total_cycles_tracked"] == 0
        assert s["total_stages_recorded"] == 0
        assert s["top_consumers"] == []

    def test_summary_with_data(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker()
        tracker.start_cycle("c1", symbol="BTC", model="gpt-4o")
        tracker.record_stage("c1", "vision_prompt", "a" * 4000)
        tracker.record_stage("c1", "vision_response", "b" * 2000)
        s = tracker.summary()
        assert s["total_cycles_tracked"] == 1
        assert s["total_stages_recorded"] == 2
        assert "vision_prompt" in s["stage_token_distribution"]
        assert "vision_response" in s["stage_token_distribution"]
        assert len(s["top_consumers"]) == 1

    def test_summary_near_limit_detected(self):
        mod = _load_modules()
        tracker = mod.ContextWindowTracker(warn_pct=0.80)
        tracker.start_cycle("c1", symbol="BTC", model="gpt-4o")
        tracker.record_stage("c1", "s", 110_000)  # int = token count direto
        s = tracker.summary()
        assert len(s["near_limit_cycles"]) == 1
        assert s["near_limit_cycles"][0]["cycle_id"] == "c1"


# ---------------------------------------------------------------------------
# TestCompressHistory
# ---------------------------------------------------------------------------

class TestCompressHistory:
    def test_short_list_unchanged(self):
        mod = _load_modules()
        history = [{"event_type": "A", "payload": "big"} for _ in range(3)]
        result = mod.ContextWindowTracker.compress_history(history, keep_last_n=5)
        assert result == history

    def test_old_payload_removed(self):
        mod = _load_modules()
        history = [
            {"event_type": f"E{i}", "symbol": "BTC", "payload": "x" * 200}
            for i in range(8)
        ]
        result = mod.ContextWindowTracker.compress_history(history, keep_last_n=3)
        # Observações antigas (0-4): sem payload
        for evt in result[:-3]:
            assert "payload" not in evt
        # Recentes (5-7): com payload
        for evt in result[-3:]:
            assert "payload" in evt

    def test_old_events_keep_metadata(self):
        mod = _load_modules()
        history = [
            {"event_type": "CYCLE_START", "symbol": "BTC", "cycle_id": "c1", "payload": "big"}
            for _ in range(6)
        ]
        result = mod.ContextWindowTracker.compress_history(history, keep_last_n=2)
        for evt in result[:-2]:
            assert "event_type" in evt
            assert "symbol" in evt
            assert "_compressed" in evt

    def test_length_preserved(self):
        mod = _load_modules()
        history = [{"event_type": f"E{i}", "payload": "x"} for i in range(10)]
        result = mod.ContextWindowTracker.compress_history(history, keep_last_n=3)
        assert len(result) == 10

    def test_empty_history(self):
        mod = _load_modules()
        assert mod.ContextWindowTracker.compress_history([], keep_last_n=5) == []

    def test_fail_silent(self):
        mod = _load_modules()
        result = mod.ContextWindowTracker.compress_history("not_a_list", keep_last_n=3)
        assert result is not None


# ---------------------------------------------------------------------------
# TestModelTokenLimits
# ---------------------------------------------------------------------------

class TestModelTokenLimits:
    def test_gpt4o_limit(self):
        mod = _load_modules()
        assert mod.MODEL_TOKEN_LIMITS.get("gpt-4o") == 128_000

    def test_claude_sonnet_limit(self):
        mod = _load_modules()
        assert mod.MODEL_TOKEN_LIMITS.get("claude-sonnet-4-6") == 200_000

    def test_claude_opus_limit(self):
        mod = _load_modules()
        assert mod.MODEL_TOKEN_LIMITS.get("claude-opus-4-6") == 200_000

    def test_default_limit_exists(self):
        mod = _load_modules()
        assert "_default" in mod.MODEL_TOKEN_LIMITS
        assert mod.MODEL_TOKEN_LIMITS["_default"] > 0


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_returns_instance(self):
        mod = _load_modules()
        t = mod.get_context_window_tracker()
        assert isinstance(t, mod.ContextWindowTracker)

    def test_same_instance_repeated_calls(self):
        mod = _load_modules()
        mod.reset_context_window_tracker()
        t1 = mod.get_context_window_tracker()
        t2 = mod.get_context_window_tracker()
        assert t1 is t2

    def test_reset_creates_new_instance(self):
        mod = _load_modules()
        t1 = mod.get_context_window_tracker()
        mod.reset_context_window_tracker()
        t2 = mod.get_context_window_tracker()
        assert t1 is not t2

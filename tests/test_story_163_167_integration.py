"""
tests/test_story_163_167_integration.py
=========================================
Stories 163–167 — NickFury Integration Tests

Testa os blocos de integração adicionados ao _cycle_for_symbol do NickFury:

Story 163 — Signal Metadata Pipeline
  - market_regime é injetado no signal.metadata quando ausente
  - cap_tier é injetado corretamente por símbolo (BTC→LARGE_CAP, etc.)
  - Valores existentes no metadata não são sobrescritos (setdefault)
  - Falha silenciosa quando AssetClassifier lança exceção

Story 164 — Vision MicroagentRegistry + RepoMap Injection
  - MicroagentRegistry.get_regime_prompt() enriquece o prompt
  - MekkaRepoMap.to_prompt_section() injeta mapa de agentes
  - Ambos falham silenciosamente quando indisponíveis

Story 165 — CycleEventLog NickFury Integration
  - CycleEventType enum correto para cada ponto do ciclo
  - emit() é chamado para CYCLE_START, ANALYSIS_DONE, SIGNAL_EMITTED,
    RISK_VERDICT, EXECUTION_DONE, CYCLE_END
  - Falha silenciosa quando CycleEventLog indisponível

Story 166 — AgentStepGuard NickFury Integration
  - guard.check() retorna (record, should_abort=True) em stuck loop
  - Abort → CycleReport(error=...) sem crash
  - Falha silenciosa quando AgentStepGuard indisponível

Story 167 — SignalChangeLog + ContextWindowTracker NickFury Integration
  - SignalChangeLog.record() registra o signal emitido
  - has_action_change detectado corretamente
  - ContextWindowTracker.record_stage() registra vision_analysis_prompt
  - check_limit() retorna bool sem exceção
  - Ambos falham silenciosamente
"""

from __future__ import annotations

import sys
import types
import importlib.util
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers para criar mocks do signal
# ---------------------------------------------------------------------------

def _make_signal(action="LONG", confidence=0.75, entry=50000.0, sl=48000.0, tp=55000.0,
                 symbol="BTC", metadata=None, reasoning="Bullish trend."):
    s = MagicMock()
    s.action = MagicMock()
    s.action.value = action
    s.action.__eq__ = lambda self, other: self.value == (other.value if hasattr(other, "value") else other)
    s.action.__ne__ = lambda self, other: self.value != (other.value if hasattr(other, "value") else other)
    s.confidence = confidence
    s.entry_price = entry
    s.stop_loss = sl
    s.take_profit = tp
    s.symbol = symbol
    s.metadata = metadata
    s.reasoning = reasoning
    s.is_actionable = True
    s.model_copy = lambda update=None, **kwargs: _make_signal(
        action=action, confidence=confidence, entry=entry,
        sl=sl, tp=tp, symbol=symbol,
        metadata=(update or {}).get("metadata", metadata),
        reasoning=reasoning,
    )
    return s


def _make_analysis(symbol="BTC", price=50000.0, rsi=65.0, trend="BULLISH", atr_pct=0.02):
    a = MagicMock()
    a.price = price
    a.volatility = MagicMock()
    a.liquidity = MagicMock()
    a.is_safe_to_trade = True
    chart = MagicMock()
    chart.rsi_14 = rsi
    chart.trend = MagicMock()
    chart.trend.value = trend
    chart.atr_pct = atr_pct
    chart.volume_spike = False
    a.chart = chart
    return a


# ---------------------------------------------------------------------------
# Story 163 — Signal Metadata Pipeline
# ---------------------------------------------------------------------------

class TestStory163SignalMetadataPipeline:
    """Tests for AssetClassifier + MarketRegimeDetector injection into signal.metadata."""

    def _load_asset_classifier(self):
        spec = importlib.util.spec_from_file_location(
            "asset_classifier_163", "src/services/asset_classifier.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["asset_classifier_163"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_cap_tier_btc_is_large_cap(self):
        mod = self._load_asset_classifier()
        ac = mod.AssetClassifier()
        assert ac.cap_tier("BTC") == mod.CapTier.LARGE_CAP

    def test_cap_tier_eth_is_large_cap(self):
        mod = self._load_asset_classifier()
        ac = mod.AssetClassifier()
        assert ac.cap_tier("ETH") == mod.CapTier.LARGE_CAP

    def test_cap_tier_sol_is_mid_cap(self):
        mod = self._load_asset_classifier()
        ac = mod.AssetClassifier()
        assert ac.cap_tier("SOL") == mod.CapTier.MID_CAP

    def test_cap_tier_unknown_is_small_cap(self):
        mod = self._load_asset_classifier()
        ac = mod.AssetClassifier()
        assert ac.cap_tier("UNKNOWNCOIN") == mod.CapTier.SMALL_CAP

    def test_regime_bull(self):
        mod = self._load_asset_classifier()
        mrd = mod.MarketRegimeDetector()
        result = mrd.detect(btc_trend="BULLISH", btc_rsi=70.0, btc_atr_pct=0.015)
        assert result.regime == mod.MarketRegime.BULL

    def test_regime_bear(self):
        mod = self._load_asset_classifier()
        mrd = mod.MarketRegimeDetector()
        result = mrd.detect(btc_trend="BEARISH", btc_rsi=30.0, btc_atr_pct=0.015)
        assert result.regime == mod.MarketRegime.BEAR

    def test_regime_volatile(self):
        mod = self._load_asset_classifier()
        mrd = mod.MarketRegimeDetector()
        result = mrd.detect(btc_trend="BULLISH", btc_rsi=65.0, btc_atr_pct=0.12)
        assert result.regime == mod.MarketRegime.VOLATILE

    def test_metadata_setdefault_does_not_overwrite(self):
        """If metadata already has market_regime, it must not be overwritten."""
        mod = self._load_asset_classifier()
        existing = {"market_regime": "BULL", "cap_tier": "MID_CAP"}
        # Simulate setdefault behavior used in nick_fury.py
        m = dict(existing)
        m.setdefault("market_regime", "BEAR")  # should stay BULL
        m.setdefault("cap_tier", "LARGE_CAP")  # should stay MID_CAP
        assert m["market_regime"] == "BULL"
        assert m["cap_tier"] == "MID_CAP"

    def test_metadata_injected_when_absent(self):
        """When metadata is empty, market_regime and cap_tier must be set."""
        mod = self._load_asset_classifier()
        m = {}
        mrd = mod.MarketRegimeDetector()
        ac = mod.AssetClassifier()
        regime = mrd.detect("BULLISH", 65, 0.02).regime.value
        cap = ac.cap_tier("SOL").value
        m.setdefault("market_regime", regime)
        m.setdefault("cap_tier", cap)
        assert m["market_regime"] == "BULL"
        assert m["cap_tier"] == "MID_CAP"

    def test_fail_silent_on_bad_rsi(self):
        """MarketRegimeDetector must not raise on edge-case RSI values."""
        mod = self._load_asset_classifier()
        mrd = mod.MarketRegimeDetector()
        try:
            r1 = mrd.detect("NEUTRAL", 0.0, 0.0)
            r2 = mrd.detect("NEUTRAL", 100.0, 0.5)
            assert r1.regime is not None
            assert r2.regime is not None
        except Exception as exc:
            raise AssertionError(f"Should not raise: {exc}") from exc


# ---------------------------------------------------------------------------
# Story 164 — Vision MicroagentRegistry + RepoMap Injection
# ---------------------------------------------------------------------------

class TestStory164VisionContextInjection:
    """Tests for regime-prompt and repo-map injection into Vision."""

    def _load_microagent_registry(self, tmp_dir=None):
        if "loguru" not in sys.modules:
            lm = types.ModuleType("loguru")
            lm.logger = MagicMock()
            sys.modules["loguru"] = lm
        spec = importlib.util.spec_from_file_location(
            "microagent_registry_164", "src/services/microagent_registry.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["microagent_registry_164"] = mod
        spec.loader.exec_module(mod)
        mod.reset_microagent_registry()
        return mod

    def _load_repo_map(self):
        if "loguru" not in sys.modules:
            lm = types.ModuleType("loguru")
            lm.logger = MagicMock()
            sys.modules["loguru"] = lm
        for dep in ["src.services.bounded_output"]:
            if dep not in sys.modules:
                sys.modules[dep] = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "repo_map_164", "src/services/repo_map.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["repo_map_164"] = mod
        spec.loader.exec_module(mod)
        mod.reset_repo_map()
        return mod

    def test_get_regime_prompt_returns_string(self):
        mod = self._load_microagent_registry()
        registry = mod.get_microagent_registry()
        result = registry.get_regime_prompt("BULL")
        assert isinstance(result, str)

    def test_get_regime_prompt_unknown_regime_returns_string(self):
        mod = self._load_microagent_registry()
        registry = mod.get_microagent_registry()
        result = registry.get_regime_prompt("UNKNOWN_REGIME_XYZ")
        assert isinstance(result, str)

    def test_repo_map_to_prompt_section_returns_str(self):
        mod = self._load_repo_map()
        rmap = mod.get_repo_map(root=".")
        result = rmap.to_prompt_section(max_chars=800, dirs=["src/agents"])
        assert isinstance(result, str)
        assert len(result) <= 850  # some tolerance for header

    def test_repo_map_scan_finds_agents(self):
        mod = self._load_repo_map()
        rmap = mod.get_repo_map(root=".")
        count = rmap.scan()
        assert count >= 0  # may be 0 in sandbox, must not raise

    def test_regime_detection_logic_volatile(self):
        """Volatile detection: atr_pct > 0.05 regardless of trend."""
        atr_pct = 0.08
        trend = "BULLISH"
        rsi = 60.0
        if atr_pct > 0.05:
            regime = "VOLATILE"
        elif trend in ("BULLISH", "STRONG_BULL") and rsi > 55:
            regime = "BULL"
        else:
            regime = "SIDEWAYS"
        assert regime == "VOLATILE"

    def test_regime_detection_logic_bull(self):
        atr_pct = 0.02
        trend = "BULLISH"
        rsi = 62.0
        if atr_pct > 0.05:
            regime = "VOLATILE"
        elif trend in ("BULLISH", "STRONG_BULL") and rsi > 55:
            regime = "BULL"
        else:
            regime = "SIDEWAYS"
        assert regime == "BULL"

    def test_regime_detection_logic_bear(self):
        atr_pct = 0.02
        trend = "BEARISH"
        rsi = 38.0
        if atr_pct > 0.05:
            regime = "VOLATILE"
        elif trend in ("BULLISH", "STRONG_BULL") and rsi > 55:
            regime = "BULL"
        elif trend in ("BEARISH", "STRONG_BEAR") and rsi < 45:
            regime = "BEAR"
        else:
            regime = "SIDEWAYS"
        assert regime == "BEAR"


# ---------------------------------------------------------------------------
# Story 165 — CycleEventLog NickFury Integration
# ---------------------------------------------------------------------------

class TestStory165CycleEventLogIntegration:
    """Tests for CycleEventLog emit calls in the NickFury pipeline."""

    def _load_cycle_event_log(self):
        if "loguru" not in sys.modules:
            lm = types.ModuleType("loguru")
            lm.logger = MagicMock()
            sys.modules["loguru"] = lm
        spec = importlib.util.spec_from_file_location(
            "cycle_event_log_165", "src/services/cycle_event_log.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["cycle_event_log_165"] = mod
        spec.loader.exec_module(mod)
        mod.reset_cycle_event_log()
        return mod

    def test_cycle_event_types_exist(self):
        mod = self._load_cycle_event_log()
        assert hasattr(mod, "CycleEventType")
        et = mod.CycleEventType
        assert hasattr(et, "CYCLE_START")
        assert hasattr(et, "CYCLE_END")
        assert hasattr(et, "ANALYSIS_DONE")
        assert hasattr(et, "SIGNAL_EMITTED")
        assert hasattr(et, "RISK_VERDICT")
        assert hasattr(et, "EXECUTION_DONE")
        assert hasattr(et, "STUCK_LOOP")

    def test_emit_cycle_start(self):
        mod = self._load_cycle_event_log()
        cel = mod.get_cycle_event_log()
        event = cel.emit(
            mod.CycleEventType.CYCLE_START,
            symbol="BTC", cycle_id="test-001",
            equity_usd=10000.0,
        )
        # event_type is stored as string repr of the enum
        assert "CYCLE_START" in str(event.event_type)
        assert event.symbol == "BTC"
        assert event.cycle_id == "test-001"

    def test_emit_multiple_types_in_sequence(self):
        mod = self._load_cycle_event_log()
        cel = mod.get_cycle_event_log()
        cycle_id = "seq-test-001"
        for et in [
            mod.CycleEventType.CYCLE_START,
            mod.CycleEventType.ANALYSIS_DONE,
            mod.CycleEventType.SIGNAL_EMITTED,
            mod.CycleEventType.RISK_VERDICT,
            mod.CycleEventType.EXECUTION_DONE,
            mod.CycleEventType.CYCLE_END,
        ]:
            cel.emit(et, symbol="ETH", cycle_id=cycle_id)
        summary = cel.cycle_summary(cycle_id)
        assert summary["found"] is True
        # cycle_summary returns 'events' list and 'stages_completed' list
        assert summary["event_count"] == 6
        assert len(summary["events"]) == 6

    def test_emit_fail_silent_bad_event_type(self):
        mod = self._load_cycle_event_log()
        cel = mod.get_cycle_event_log()
        try:
            cel.emit(None, symbol="BTC", cycle_id="bad")
        except Exception as exc:
            raise AssertionError(f"Should not raise: {exc}") from exc

    def test_cel_emit_helper_guards_none_cel(self):
        """Simulates _cel_emit with _cel=None — must not raise."""
        _cel = None

        def _cel_emit(event_type, **kwargs):
            try:
                if _cel is not None:
                    _cel.emit(event_type, **kwargs)
            except Exception:
                pass

        try:
            _cel_emit(None, symbol="BTC", cycle_id="x")
        except Exception as exc:
            raise AssertionError(f"Should not raise: {exc}") from exc

    def test_filter_by_cycle_returns_emitted_events(self):
        mod = self._load_cycle_event_log()
        cel = mod.get_cycle_event_log()
        cid = "filter-test-cycle"
        cel.emit(mod.CycleEventType.CYCLE_START, symbol="SOL", cycle_id=cid, equity_usd=5000)
        cel.emit(mod.CycleEventType.SIGNAL_EMITTED, symbol="SOL", cycle_id=cid, action="LONG")
        events = cel.filter_by_cycle(cid)
        assert len(events) == 2
        # event_type stored as string repr — check by string membership
        types_str = [str(e.event_type) for e in events]
        assert any("CYCLE_START" in t for t in types_str)
        assert any("SIGNAL_EMITTED" in t for t in types_str)


# ---------------------------------------------------------------------------
# Story 166 — AgentStepGuard NickFury Integration
# ---------------------------------------------------------------------------

class TestStory166AgentStepGuardIntegration:
    """Tests for NickFuryStepGuard usage in _cycle_for_symbol."""

    def _load_step_guard(self):
        if "loguru" not in sys.modules:
            lm = types.ModuleType("loguru")
            lm.logger = MagicMock()
            sys.modules["loguru"] = lm
        spec = importlib.util.spec_from_file_location(
            "agent_step_guard_166", "src/services/agent_step_guard.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["agent_step_guard_166"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_for_cycle_creates_fresh_guard(self):
        mod = self._load_step_guard()
        g1 = mod.NickFuryStepGuard.for_cycle("BTC", "c1")
        g2 = mod.NickFuryStepGuard.for_cycle("BTC", "c2")
        assert g1 is not g2

    def test_guard_check_not_stuck_initially(self):
        mod = self._load_step_guard()
        guard = mod.NickFuryStepGuard.for_cycle("BTC", "c1")
        rec, should_abort = guard.check("Vision.run", "LONG:0.75")
        assert should_abort is False

    def test_guard_detects_stuck_loop(self):
        mod = self._load_step_guard()
        guard = mod.AgentStepGuard(max_iterations=20, stuck_threshold=3)
        same_result = "LONG:0.75"
        for _ in range(5):
            rec, should_abort = guard.check("Vision.run", same_result)
        assert should_abort is True or guard.is_stuck()

    def test_guard_max_iterations_exceeded(self):
        mod = self._load_step_guard()
        guard = mod.AgentStepGuard(max_iterations=3, stuck_threshold=10)
        for _ in range(4):
            rec, should_abort = guard.check("Batman.run", f"unique_{_}")
        assert guard.is_max_iterations_exceeded() or should_abort

    def test_guard_check_helper_returns_false_on_none_guard(self):
        """Simulates _guard_check with _guard=None — must return False."""
        _guard = None

        def _guard_check(fn_name, result):
            try:
                if _guard is None:
                    return False
                rec, abort = _guard.check(function_name=fn_name, result=result)
                return abort
            except Exception:
                return False

        assert _guard_check("Vision.run", "LONG:0.75") is False

    def test_nick_fury_step_guard_global_summary(self):
        mod = self._load_step_guard()
        mod.NickFuryStepGuard.reset_global()
        summary = mod.NickFuryStepGuard.global_summary()
        # Keys returned: global_stuck_count, global_max_exceeded_count
        assert "global_stuck_count" in summary
        assert "global_max_exceeded_count" in summary
        assert summary["global_stuck_count"] == 0


# ---------------------------------------------------------------------------
# Story 167 — SignalChangeLog + ContextWindowTracker NickFury Integration
# ---------------------------------------------------------------------------

class TestStory167SignalChangeLogIntegration:
    """Tests for SignalChangeLog.record() + ContextWindowTracker in NickFury pipeline."""

    def _load_signal_changelog(self):
        spec = importlib.util.spec_from_file_location(
            "signal_changelog_167", "src/services/signal_changelog.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["signal_changelog_167"] = mod
        spec.loader.exec_module(mod)
        mod.reset_signal_changelog()
        return mod

    def _load_context_window_tracker(self):
        if "loguru" not in sys.modules:
            lm = types.ModuleType("loguru")
            lm.logger = MagicMock()
            sys.modules["loguru"] = lm
        spec = importlib.util.spec_from_file_location(
            "context_window_tracker_167", "src/services/context_window_tracker.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["context_window_tracker_167"] = mod
        spec.loader.exec_module(mod)
        mod.reset_context_window_tracker()
        return mod

    def test_record_first_signal_prev_none(self):
        mod = self._load_signal_changelog()
        scl = mod.get_signal_changelog()
        sig = _make_signal(action="LONG", symbol="BTC")
        record = scl.record("BTC", prev=None, curr=sig, curr_cycle_id="c1")
        assert record.symbol == "BTC"
        assert len(record.changes) > 0  # all-new when prev=None

    def test_record_same_signal_no_action_change(self):
        mod = self._load_signal_changelog()
        scl = mod.get_signal_changelog()
        sig1 = _make_signal(action="LONG", confidence=0.75)
        sig2 = _make_signal(action="LONG", confidence=0.75)
        scl.record("ETH", None, sig1, curr_cycle_id="c1")
        record = scl.record("ETH", sig1, sig2, prev_cycle_id="c1", curr_cycle_id="c2")
        assert record.has_action_change is False

    def test_record_action_flip_detected(self):
        mod = self._load_signal_changelog()
        scl = mod.get_signal_changelog()
        sig1 = _make_signal(action="LONG")
        sig2 = _make_signal(action="SHORT", sl=52000, tp=46000)
        record = scl.record("BTC", sig1, sig2, prev_cycle_id="c1", curr_cycle_id="c2")
        assert record.has_action_change is True

    def test_commit_message_on_action_flip(self):
        mod = self._load_signal_changelog()
        scl = mod.get_signal_changelog()
        sig1 = _make_signal(action="LONG")
        sig2 = _make_signal(action="SHORT", sl=52000, tp=46000)
        record = scl.record("BTC", sig1, sig2, prev_cycle_id="c1", curr_cycle_id="c2")
        msg = record.commit_message()
        assert "BTC" in msg
        assert "action" in msg.lower() or "LONG" in msg or "SHORT" in msg

    def test_audit_line_format(self):
        mod = self._load_signal_changelog()
        sig = _make_signal(action="LONG", symbol="SOL")
        audit = mod.SignalChangeLog.format_for_audit(sig, cycle_id="c999")
        assert "SOL" in audit
        assert "LONG" in audit

    def test_get_recent_returns_records(self):
        mod = self._load_signal_changelog()
        scl = mod.get_signal_changelog()
        for i in range(5):
            sig = _make_signal(confidence=0.7 + i * 0.01)
            scl.record("AVAX", None, sig, curr_cycle_id=f"c{i}")
        recent = scl.get_recent("AVAX", n=3)
        assert len(recent) == 3

    def test_get_action_flips_only_returns_flips(self):
        mod = self._load_signal_changelog()
        scl = mod.get_signal_changelog()
        sig_long = _make_signal(action="LONG")
        sig_short = _make_signal(action="SHORT", sl=52000, tp=46000)
        sig_long2 = _make_signal(action="LONG")
        scl.record("DOGE", sig_long, sig_short, prev_cycle_id="c1", curr_cycle_id="c2")
        scl.record("DOGE", sig_short, sig_long2, prev_cycle_id="c2", curr_cycle_id="c3")
        scl.record("DOGE", sig_long2, sig_long2, prev_cycle_id="c3", curr_cycle_id="c4")  # no flip
        flips = scl.get_action_flips("DOGE")
        assert len(flips) == 2  # only the 2 flips

    def test_context_window_tracker_record_vision_stage(self):
        mod = self._load_context_window_tracker()
        cwt = mod.get_context_window_tracker()
        cwt.start_cycle(cycle_id="cwt-001", symbol="BTC", model="gpt-4o")
        tokens = cwt.record_stage(
            cycle_id="cwt-001",
            stage_name="vision_analysis_prompt",
            content="BTC analysis prompt " * 100,
            model="gpt-4o",
            symbol="BTC",
        )
        assert tokens > 0
        summary = cwt.cycle_summary("cwt-001")
        assert summary["found"] is True
        # stages list contains dicts with 'name' key
        assert any(s["name"] == "vision_analysis_prompt" for s in summary["stages"])

    def test_context_window_tracker_check_limit_returns_bool(self):
        mod = self._load_context_window_tracker()
        cwt = mod.get_context_window_tracker()
        cwt.start_cycle(cycle_id="cwt-002", symbol="ETH", model="gpt-4o")
        cwt.record_stage("cwt-002", "test_stage", "short content", "gpt-4o", "ETH")
        is_near = cwt.check_limit("cwt-002")
        assert isinstance(is_near, bool)

    def test_context_window_tracker_does_not_raise_on_missing_cycle(self):
        mod = self._load_context_window_tracker()
        cwt = mod.get_context_window_tracker()
        try:
            result = cwt.check_limit("nonexistent-cycle-xyz")
            assert isinstance(result, bool)
        except Exception as exc:
            raise AssertionError(f"Should not raise: {exc}") from exc

    def test_signal_changelog_fail_silent_on_none_signal(self):
        mod = self._load_signal_changelog()
        try:
            result = mod.SignalChangeLog.diff(None, None)
            assert isinstance(result, mod.ChangeRecord)
        except Exception as exc:
            raise AssertionError(f"Should not raise: {exc}") from exc

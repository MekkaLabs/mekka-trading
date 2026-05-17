"""
tests/test_story_183_187_integration.py
========================================
Testes de integração — Milestone 28: MetaGPT Patterns (Stories 183–187).

Cobertura:
  Story 183 — RoleWorkingMemory  (MetaGPT RoleContext.rc.memory)
  Story 184 — TypedCycleMessage  (MetaGPT Message routing)
  Story 185 — CycleSOP           (MetaGPT SOP declarativo)
  Story 186 — SignalOutcomeMemory (MetaGPT LongTermMemory + similarity search)
  Story 187 — IncrementalCycleSkip (MetaGPT Incremental Development)
  Cross-story — integração end-to-end
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ===========================================================================
# Story 183 — RoleWorkingMemory
# ===========================================================================

class TestStory183RoleWorkingMemory:
    """RoleWorkingMemory: janela deslizante de ciclos por símbolo."""

    def test_import(self):
        from src.services.role_working_memory import (
            RoleWorkingMemory,
            CycleRecord,
            get_role_working_memory,
            reset_role_working_memory,
        )
        assert RoleWorkingMemory
        assert CycleRecord
        reset_role_working_memory()

    def test_record_and_get_recent(self):
        from src.services.role_working_memory import RoleWorkingMemory

        mem = RoleWorkingMemory(max_per_symbol=5)
        mem.record("BTC", action="LONG", confidence=0.75, regime="VOLATILE", outcome_pnl=120.0)
        mem.record("BTC", action="SHORT", confidence=0.60, regime="BEAR", outcome_pnl=-30.0)

        records = mem.get_recent("BTC", limit=5)
        assert len(records) == 2
        assert records[-1].action == "SHORT"
        assert records[0].action == "LONG"

    def test_sliding_window_max(self):
        """Janela não ultrapassa max_per_symbol."""
        from src.services.role_working_memory import RoleWorkingMemory

        mem = RoleWorkingMemory(max_per_symbol=3)
        for i in range(5):
            mem.record("ETH", action="LONG", confidence=0.7, outcome_pnl=float(i))

        records = mem.get_recent("ETH", limit=10)
        assert len(records) == 3

    def test_prompt_block_format(self):
        """Bloco gerado contém cabeçalho, linhas e nota."""
        from src.services.role_working_memory import RoleWorkingMemory

        mem = RoleWorkingMemory()
        mem.record("BTC", action="LONG", confidence=0.80, regime="BULL", outcome_pnl=200.0)
        mem.record("BTC", action="HOLD", confidence=0.55, regime="SIDEWAYS", outcome_pnl=0.0)

        block = mem.get_prompt_block("BTC", limit=5)
        assert "Recent Trade History" in block
        assert "LONG" in block
        assert "HOLD" in block
        assert "recent mistakes" in block

    def test_prompt_block_empty_for_unknown_symbol(self):
        """Símbolos sem histórico retornam string vazia."""
        from src.services.role_working_memory import RoleWorkingMemory

        mem = RoleWorkingMemory()
        assert mem.get_prompt_block("UNKNOWN_COIN") == ""

    def test_resolve_outcome(self):
        """resolve_outcome atualiza o registro pendente mais recente."""
        from src.services.role_working_memory import RoleWorkingMemory

        mem = RoleWorkingMemory()
        mem.record("SOL", action="LONG", confidence=0.70, outcome_pnl=None)
        ok = mem.resolve_outcome("SOL", outcome_pnl=55.0)
        assert ok is True

        records = mem.get_recent("SOL")
        assert records[-1].outcome_pnl == 55.0

    def test_summary(self):
        from src.services.role_working_memory import RoleWorkingMemory

        mem = RoleWorkingMemory()
        mem.record("BTC", action="LONG", confidence=0.75, outcome_pnl=100.0)
        s = mem.summary()
        assert s["symbols_tracked"] == 1
        assert s["total_records"] == 1

    def test_vision_block_present_in_vision_py(self):
        """vision.py deve conter o bloco Story 183 RoleWorkingMemory."""
        src = open("src/agents/vision.py").read()
        assert "Story 183" in src
        assert "RoleWorkingMemory" in src
        assert "get_prompt_block" in src


# ===========================================================================
# Story 184 — TypedCycleMessage
# ===========================================================================

class TestStory184TypedCycleMessage:
    """TypedCycleMessage: mensagem tipada com roteamento entre estágios."""

    def test_import(self):
        from src.models.cycle_message import CycleMessage, CycleStage
        assert CycleMessage
        assert CycleStage

    def test_from_signal_factory(self):
        from src.models.cycle_message import CycleMessage, CycleStage

        class FakeSignal:
            def model_dump(self):
                return {"action": "LONG", "confidence": 0.75}

        msg = CycleMessage.from_signal(
            symbol="BTC",
            signal=FakeSignal(),
            cycle_id="c001",
        )
        assert msg.stage == CycleStage.SIGNAL_EMITTED
        assert msg.symbol == "BTC"
        assert msg.payload_type == "TradingSignal"
        assert "LONG" in msg.payload_json

    def test_from_analysis_factory(self):
        from src.models.cycle_message import CycleMessage, CycleStage

        class FakeAnalysis:
            def model_dump(self):
                return {"symbol": "ETH", "price": 3200.0}

        msg = CycleMessage.from_analysis(
            symbol="ETH",
            analysis=FakeAnalysis(),
            cycle_id="c002",
        )
        assert msg.stage == CycleStage.ANALYSIS_DONE
        assert "Vision" in msg.recipients

    def test_cycle_start_and_end(self):
        from src.models.cycle_message import CycleMessage, CycleStage

        start = CycleMessage.cycle_start("BTC", cycle_id="c003")
        assert start.stage == CycleStage.CYCLE_START

        end = CycleMessage.cycle_end("BTC", cycle_id="c003", success=True)
        assert end.stage == CycleStage.CYCLE_END
        assert end.get_payload()["success"] is True

    def test_cycle_skipped(self):
        from src.models.cycle_message import CycleMessage, CycleStage

        msg = CycleMessage.cycle_skipped("BTC", reason="price_stable")
        assert msg.stage == CycleStage.CYCLE_SKIPPED
        assert "price_stable" in msg.payload_json

    def test_to_log_line(self):
        from src.models.cycle_message import CycleMessage

        msg = CycleMessage.cycle_start("BTC", cycle_id="c001")
        log = msg.to_log_line()
        assert "CycleMessage" in log
        assert "BTC" in log

    def test_to_dict(self):
        from src.models.cycle_message import CycleMessage

        msg = CycleMessage.cycle_start("BTC")
        d = msg.to_dict()
        assert d["symbol"] == "BTC"
        assert "stage" in d

    def test_nick_fury_block_present(self):
        """nick_fury.py deve conter Story 184 TypedCycleMessage."""
        src = open("src/agents/nick_fury.py").read()
        assert "Story 184" in src
        assert "TypedCycleMessage" in src
        assert "CycleMessage" in src


# ===========================================================================
# Story 185 — CycleSOP
# ===========================================================================

class TestStory185CycleSOP:
    """CycleSOP: especificação declarativa do pipeline."""

    def test_import(self):
        from src.services.cycle_sop import CycleSOP, SOPStage, get_cycle_sop, reset_cycle_sop
        assert CycleSOP
        assert SOPStage
        reset_cycle_sop()

    def test_stages_count(self):
        from src.services.cycle_sop import CycleSOP
        sop = CycleSOP()
        assert len(sop.stages) >= 8  # pelo menos 8 estágios

    def test_required_stages_present(self):
        from src.services.cycle_sop import CycleSOP
        sop = CycleSOP()
        names = {s.name for s in sop.stages}
        assert "MARKET_ANALYSIS" in names
        assert "VISION_SIGNAL" in names
        assert "RISK_ASSESSMENT" in names
        assert "EXECUTION" in names

    def test_vision_signal_is_skippable(self):
        """VISION_SIGNAL deve ser marcado como skippable (IncrementalCycleSkip)."""
        from src.services.cycle_sop import CycleSOP
        sop = CycleSOP()
        stage = sop.get_stage("VISION_SIGNAL")
        assert stage is not None
        assert stage.skippable is True

    def test_risk_assessment_not_skippable(self):
        """RISK_ASSESSMENT nunca pode ser skipado."""
        from src.services.cycle_sop import CycleSOP
        sop = CycleSOP()
        stage = sop.get_stage("RISK_ASSESSMENT")
        assert stage is not None
        assert stage.skippable is False

    def test_to_prompt_section(self):
        from src.services.cycle_sop import CycleSOP
        sop = CycleSOP()
        section = sop.to_prompt_section()
        assert "Mekka Trading Cycle SOP" in section
        assert "VISION_SIGNAL" in section
        assert "EXECUTION" in section

    def test_to_dict(self):
        from src.services.cycle_sop import CycleSOP
        sop = CycleSOP()
        d = sop.to_dict()
        assert d["total_stages"] >= 8
        assert "stages" in d
        assert d["skippable_count"] >= 1

    def test_singleton(self):
        from src.services.cycle_sop import get_cycle_sop, reset_cycle_sop
        reset_cycle_sop()
        a = get_cycle_sop()
        b = get_cycle_sop()
        assert a is b


# ===========================================================================
# Story 186 — SignalOutcomeMemory
# ===========================================================================

class TestStory186SignalOutcomeMemory:
    """SignalOutcomeMemory: LongTermMemory com similarity search."""

    def test_import(self):
        from src.services.signal_outcome_memory import (
            SignalOutcomeMemory,
            OutcomeRecord,
            get_signal_outcome_memory,
            reset_signal_outcome_memory,
        )
        assert SignalOutcomeMemory
        assert OutcomeRecord
        reset_signal_outcome_memory()

    def test_record_and_find_similar(self):
        from src.services.signal_outcome_memory import SignalOutcomeMemory

        mem = SignalOutcomeMemory()
        mem.record("BTC", regime="VOLATILE", action="LONG", confidence=0.80, pnl_usd=150.0)
        mem.record("BTC", regime="VOLATILE", action="LONG", confidence=0.70, pnl_usd=-50.0)
        mem.record("BTC", regime="BULL", action="SHORT", confidence=0.65, pnl_usd=80.0)

        similar = mem.find_similar("BTC", regime="VOLATILE", action="LONG", top_n=3)
        # Os dois VOLATILE+LONG devem ter score máximo
        assert len(similar) >= 2
        assert all(r.action == "LONG" for r in similar[:2])

    def test_similarity_score_exact_match(self):
        from src.services.signal_outcome_memory import OutcomeRecord

        rec = OutcomeRecord(
            symbol="BTC", regime="VOLATILE", action="LONG",
            confidence=0.8, pnl_usd=100.0
        )
        score = rec.similarity_score("VOLATILE", "LONG")
        assert score == 1.0  # 0.6 (regime) + 0.4 (action) = 1.0

    def test_similarity_score_partial_regime(self):
        from src.services.signal_outcome_memory import OutcomeRecord

        rec = OutcomeRecord(
            symbol="BTC", regime="STRONG_BULL", action="LONG",
            confidence=0.8, pnl_usd=100.0
        )
        score = rec.similarity_score("BULL", "LONG")
        # regime partial match = 0.3, action match = 0.4 → 0.7
        assert score == pytest.approx(0.7, abs=0.01) if _pytest_available() else score == 0.7

    def test_prompt_block_format(self):
        from src.services.signal_outcome_memory import SignalOutcomeMemory

        mem = SignalOutcomeMemory()
        mem.record("BTC", regime="VOLATILE", action="LONG", confidence=0.75, pnl_usd=200.0)
        block = mem.get_prompt_block("BTC", regime="VOLATILE", action="LONG")
        assert "Past Performance" in block
        assert "VOLATILE" in block
        assert "Win rate" in block

    def test_prompt_block_empty_no_history(self):
        from src.services.signal_outcome_memory import SignalOutcomeMemory

        mem = SignalOutcomeMemory()
        assert mem.get_prompt_block("NEWCOIN", regime="BULL", action="LONG") == ""

    def test_win_rate(self):
        from src.services.signal_outcome_memory import SignalOutcomeMemory

        mem = SignalOutcomeMemory()
        mem.record("BTC", regime="BULL", action="LONG", confidence=0.8, pnl_usd=100.0)
        mem.record("BTC", regime="BULL", action="LONG", confidence=0.7, pnl_usd=-50.0)
        wr = mem.win_rate("BTC", action="LONG")
        assert wr == 0.5

    def test_rotation_max_records(self):
        """Não deve ultrapassar max_records."""
        from src.services.signal_outcome_memory import SignalOutcomeMemory

        mem = SignalOutcomeMemory(max_records=5)
        for i in range(8):
            mem.record("BTC", regime="BULL", action="LONG", confidence=0.7, pnl_usd=float(i))

        assert len(mem._records) == 5

    def test_vision_block_present_in_vision_py(self):
        """vision.py deve conter Story 186 SignalOutcomeMemory."""
        src = open("src/agents/vision.py").read()
        assert "Story 186" in src
        assert "SignalOutcomeMemory" in src
        assert "get_prompt_block" in src


def _pytest_available():
    try:
        import pytest
        return True
    except ImportError:
        return False


# ===========================================================================
# Story 187 — IncrementalCycleSkip
# ===========================================================================

class TestStory187IncrementalCycleSkip:
    """IncrementalCycleGuard: skip Vision LLM call se nada material mudou."""

    def test_import(self):
        from src.services.cycle_incremental_guard import (
            IncrementalCycleGuard,
            CycleCheckpoint,
            get_cycle_incremental_guard,
            reset_cycle_incremental_guard,
        )
        assert IncrementalCycleGuard
        assert CycleCheckpoint
        reset_cycle_incremental_guard()

    def test_no_checkpoint_no_skip(self):
        from src.services.cycle_incremental_guard import IncrementalCycleGuard

        guard = IncrementalCycleGuard()
        skip, reason = guard.should_skip("BTC", current_price=50000.0)
        assert skip is False
        assert "no_checkpoint" in reason

    def test_skip_when_stable(self):
        """Skip quando preço e regime não mudaram materialmente."""
        from src.services.cycle_incremental_guard import IncrementalCycleGuard

        class FakeSignal:
            action = "LONG"
            confidence = 0.75

        guard = IncrementalCycleGuard(price_threshold_pct=0.005, max_signal_age_s=300.0)
        guard.update("BTC", price=50000.0, regime="VOLATILE", signal=FakeSignal())

        # Preço mudou apenas 0.1% (< 0.5%)
        skip, reason = guard.should_skip("BTC", current_price=50050.0, current_regime="VOLATILE")
        assert skip is True
        assert "incremental_skip" in reason

    def test_no_skip_when_price_moved(self):
        """Não skipa quando preço variou acima do threshold."""
        from src.services.cycle_incremental_guard import IncrementalCycleGuard

        class FakeSignal:
            pass

        guard = IncrementalCycleGuard(price_threshold_pct=0.002)
        guard.update("BTC", price=50000.0, regime="BULL", signal=FakeSignal())

        # Preço subiu 1% (> 0.2%)
        skip, reason = guard.should_skip("BTC", current_price=50500.0, current_regime="BULL")
        assert skip is False
        assert "price_moved" in reason

    def test_no_skip_when_regime_changed(self):
        """Não skipa quando regime mudou."""
        from src.services.cycle_incremental_guard import IncrementalCycleGuard

        class FakeSignal:
            pass

        guard = IncrementalCycleGuard()
        guard.update("ETH", price=3000.0, regime="BULL", signal=FakeSignal())

        skip, reason = guard.should_skip("ETH", current_price=3000.0, current_regime="VOLATILE")
        assert skip is False
        assert "regime_changed" in reason

    def test_no_skip_when_expired(self):
        """Não skipa quando checkpoint expirou."""
        import time
        from src.services.cycle_incremental_guard import IncrementalCycleGuard, CycleCheckpoint

        class FakeSignal:
            pass

        guard = IncrementalCycleGuard(max_signal_age_s=0.01)
        guard.update("BTC", price=50000.0, regime="BULL", signal=FakeSignal())

        time.sleep(0.05)  # Deixa expirar
        skip, reason = guard.should_skip("BTC", current_price=50000.0, current_regime="BULL")
        assert skip is False
        assert "expired" in reason

    def test_skip_rate(self):
        from src.services.cycle_incremental_guard import IncrementalCycleGuard

        guard = IncrementalCycleGuard()
        # 2 checks sem checkpoint → 0 skips
        guard.should_skip("BTC", 50000.0)
        guard.should_skip("BTC", 50000.0)
        assert guard.skip_rate == 0.0

    def test_summary(self):
        from src.services.cycle_incremental_guard import IncrementalCycleGuard

        guard = IncrementalCycleGuard()
        s = guard.summary()
        assert "skip_rate" in s
        assert "price_threshold_pct" in s
        assert "checkpoints" in s

    def test_nick_fury_block_present(self):
        """nick_fury.py deve conter Story 187 IncrementalCycleSkip."""
        src = open("src/agents/nick_fury.py").read()
        assert "Story 187" in src
        assert "IncrementalCycleSkip" in src
        assert "incremental_skipped" in src


# ===========================================================================
# Cross-Story Integration — Milestone 28
# ===========================================================================

class TestMilestone28CrossStoryIntegration:
    """Testes de integração cross-story para o Milestone 28."""

    def test_all_new_services_importable(self):
        """Todos os 4 novos serviços devem importar sem erro."""
        from src.services.role_working_memory import get_role_working_memory
        from src.models.cycle_message import CycleMessage
        from src.services.cycle_sop import get_cycle_sop
        from src.services.signal_outcome_memory import get_signal_outcome_memory
        from src.services.cycle_incremental_guard import get_cycle_incremental_guard
        assert all([
            get_role_working_memory,
            CycleMessage,
            get_cycle_sop,
            get_signal_outcome_memory,
            get_cycle_incremental_guard,
        ])

    def test_vision_py_has_all_stories_183_186(self):
        """vision.py deve ter blocos para Stories 183 e 186."""
        src = open("src/agents/vision.py").read()
        for story in ["183", "186"]:
            assert f"Story {story}" in src, f"Story {story} ausente em vision.py"

    def test_nick_fury_py_has_stories_184_185_187(self):
        """nick_fury.py deve ter blocos para Stories 184 e 187."""
        src = open("src/agents/nick_fury.py").read()
        for story in ["184", "187"]:
            assert f"Story {story}" in src, f"Story {story} ausente em nick_fury.py"

    def test_dashboard_routes_registered(self):
        """server.py deve registrar as 3 novas rotas do Milestone 28."""
        src = open("src/dashboard/server.py").read()
        assert "/api/cycle-sop" in src
        assert "/api/working-memory" in src
        assert "/api/incremental-guard" in src

    def test_working_memory_and_outcome_memory_interact(self):
        """RoleWorkingMemory e SignalOutcomeMemory operam independentemente no mesmo símbolo."""
        from src.services.role_working_memory import RoleWorkingMemory
        from src.services.signal_outcome_memory import SignalOutcomeMemory

        wm = RoleWorkingMemory()
        om = SignalOutcomeMemory()

        wm.record("BTC", action="LONG", confidence=0.75, regime="VOLATILE", outcome_pnl=100.0)
        om.record("BTC", regime="VOLATILE", action="LONG", confidence=0.75, pnl_usd=100.0)

        # Ambos funcionam sem conflito
        assert len(wm.get_recent("BTC")) == 1
        assert len(om.find_similar("BTC", "VOLATILE", "LONG")) == 1

    def test_sop_and_incremental_guard_are_consistent(self):
        """CycleSOP lista VISION_SIGNAL como skippable — coerente com IncrementalCycleGuard."""
        from src.services.cycle_sop import CycleSOP
        from src.services.cycle_incremental_guard import IncrementalCycleGuard

        sop = CycleSOP()
        guard = IncrementalCycleGuard()

        # SOP declara VISION_SIGNAL como skippable
        vision_stage = sop.get_stage("VISION_SIGNAL")
        assert vision_stage.skippable is True

        # Guard começa sem checkpoints (nunca skipa na primeira vez)
        skip, _ = guard.should_skip("BTC", 50000.0)
        assert skip is False

    def test_cycle_message_wraps_all_stages(self):
        """CycleMessage pode representar todos os CycleStage."""
        from src.models.cycle_message import CycleMessage, CycleStage

        for stage in CycleStage:
            msg = CycleMessage(
                stage=stage,
                symbol="BTC",
                cycle_id="test",
                payload_json="{}",
            )
            assert msg.stage == stage
            assert msg.to_log_line()

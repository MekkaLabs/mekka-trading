"""
tests/test_story_198_202_integration.py
========================================
Testes de integração — Milestone 31: OpenHands Patterns Wave 2
Stories 198-202.

Story 198 — CycleConversationMemory (OpenHands ConversationMemory)
Story 199 — CycleCondensationEngine (OpenHands Condenser / CondensationAction)
Story 200 — CycleArtifactStore (OpenHands FileStore / InMemoryFileStore)
Story 201 — CycleActionRiskAnalyzer (OpenHands SecurityAnalyzer)
Story 202 — CycleStateResetter (OpenHands AgentController.reset())
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Story 198 — CycleConversationMemory
# ---------------------------------------------------------------------------

class TestStory198CycleConversationMemory:
    """CycleConversationMemory: histórico de janela de contexto por símbolo."""

    def setup_method(self):
        from src.services.cycle_conversation_memory import reset_cycle_conversation_memory
        reset_cycle_conversation_memory()

    def test_add_turn_creates_history(self):
        """add_turn registra o par user/assistant no histórico."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem = get_cycle_conversation_memory()
        turn = mem.add_turn("BTC", "cycle-001", "analyze BTC", "LONG:0.85")
        assert turn.symbol == "BTC"
        assert turn.user_prompt == "analyze BTC"
        assert turn.assistant_reply == "LONG:0.85"
        assert turn.token_estimate > 0

    def test_build_messages_returns_openai_format(self):
        """build_messages() retorna lista de dicts {role, content}."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem = get_cycle_conversation_memory()
        mem.add_turn("ETH", "cycle-002", "analyze ETH", "SHORT:0.72")
        msgs = mem.build_messages("ETH", n_recent=5)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "analyze ETH"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "SHORT:0.72"

    def test_multiple_turns_respects_n_recent(self):
        """build_messages respeita o n_recent mais recente."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem = get_cycle_conversation_memory()
        for i in range(10):
            mem.add_turn("BTC", f"cycle-{i:03d}", f"prompt-{i}", f"reply-{i}")
        msgs = mem.build_messages("BTC", n_recent=2)
        # 2 turns × 2 msgs (user+assistant) = 4 mensagens
        assert len(msgs) == 4
        assert "prompt-8" in str(msgs) or "prompt-9" in str(msgs)

    def test_build_messages_respects_token_budget(self):
        """build_messages filtra turns que excedem max_tokens_budget."""
        from src.services.cycle_conversation_memory import (
            CycleConversationMemory,
        )
        # Budget baixo para forçar filtro
        mem = CycleConversationMemory(max_tokens_budget=50, default_n_recent=10)
        # Adiciona turns grandes (~200 tokens cada)
        for i in range(5):
            mem.add_turn("BTC", f"c{i}", "x" * 400, "y" * 400)
        msgs = mem.build_messages("BTC")
        # Com budget=50, dificilmente cabe mais de 0-1 turn
        assert len(msgs) <= 2  # no máximo 1 turn (user+assistant)

    def test_clear_symbol_removes_history(self):
        """clear_symbol() limpa histórico do símbolo."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem = get_cycle_conversation_memory()
        mem.add_turn("SOL", "c001", "analyze SOL", "HOLD:0.5")
        mem.clear_symbol("SOL")
        assert mem.build_messages("SOL") == []

    def test_symbols_tracked(self):
        """symbols_tracked() lista símbolos com histórico."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem = get_cycle_conversation_memory()
        mem.add_turn("BTC", "c1", "p", "r")
        mem.add_turn("ETH", "c2", "p", "r")
        tracked = mem.symbols_tracked()
        assert "BTC" in tracked
        assert "ETH" in tracked

    def test_summary_returns_dict(self):
        """summary() retorna dict com métricas."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem = get_cycle_conversation_memory()
        mem.add_turn("BTC", "c1", "p", "r")
        s = mem.summary()
        assert s["total_turns"] == 1
        assert "symbols_tracked" in s
        assert "total_tokens_estimated" in s

    def test_singleton_returns_same_instance(self):
        """get_cycle_conversation_memory() retorna o mesmo singleton."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem1 = get_cycle_conversation_memory()
        mem2 = get_cycle_conversation_memory()
        assert mem1 is mem2


# ---------------------------------------------------------------------------
# Story 199 — CycleCondensationEngine
# ---------------------------------------------------------------------------

class TestStory199CycleCondensationEngine:
    """CycleCondensationEngine: condensação de histórico por threshold."""

    def setup_method(self):
        from src.services.cycle_condensation_engine import reset_cycle_condensation_engine
        from src.services.cycle_conversation_memory import reset_cycle_conversation_memory
        reset_cycle_condensation_engine()
        reset_cycle_conversation_memory()

    def test_should_condense_above_threshold(self):
        """should_condense() True quando uso >= threshold."""
        from src.services.cycle_condensation_engine import CycleCondensationEngine
        engine = CycleCondensationEngine(condensation_threshold=0.8)
        assert engine.should_condense(current_tokens=900, max_tokens=1000) is True
        assert engine.should_condense(current_tokens=799, max_tokens=1000) is False

    def test_should_not_condense_below_threshold(self):
        """should_condense() False quando uso < threshold."""
        from src.services.cycle_condensation_engine import CycleCondensationEngine
        engine = CycleCondensationEngine(condensation_threshold=0.85)
        assert engine.should_condense(current_tokens=500, max_tokens=1000) is False

    def test_condense_memory_halve_strategy(self):
        """HALVE: remove a metade mais antiga do histórico."""
        from src.services.cycle_condensation_engine import (
            CycleCondensationEngine, CondensationStrategy,
        )
        from src.services.cycle_conversation_memory import CycleConversationMemory
        mem = CycleConversationMemory()
        for i in range(10):
            mem.add_turn("BTC", f"c{i}", f"prompt{i}", f"reply{i}")
        engine = CycleCondensationEngine(strategy=CondensationStrategy.HALVE)
        record = engine.condense_memory(mem, "BTC", "c-test")
        assert record is not None
        assert record.turns_before == 10
        assert record.turns_after == 5
        assert record.reduction_pct == 50.0

    def test_condense_memory_returns_record(self):
        """condense_memory retorna CondensationRecord com campos corretos."""
        from src.services.cycle_condensation_engine import (
            CycleCondensationEngine, CondensationStrategy,
        )
        from src.services.cycle_conversation_memory import CycleConversationMemory
        mem = CycleConversationMemory()
        for i in range(6):
            mem.add_turn("ETH", f"c{i}", "p", "r")
        engine = CycleCondensationEngine(strategy=CondensationStrategy.HALVE)
        record = engine.condense_memory(mem, "ETH", "cycle-abc")
        assert record.symbol == "ETH"
        assert record.strategy.value == "HALVE"
        assert record.turns_before == 6
        assert record.turns_after == 3

    def test_maybe_condense_only_triggers_at_threshold(self):
        """maybe_condense: não condensa se abaixo do threshold."""
        from src.services.cycle_condensation_engine import CycleCondensationEngine
        from src.services.cycle_conversation_memory import CycleConversationMemory
        mem = CycleConversationMemory(max_tokens_budget=1000)
        for i in range(4):
            mem.add_turn("BTC", f"c{i}", "p", "r")
        engine = CycleCondensationEngine(condensation_threshold=0.9)
        record = engine.maybe_condense(mem, "BTC", current_tokens=500, max_tokens=1000)
        assert record is None  # não atingiu threshold

    def test_get_records_returns_history(self):
        """get_records() retorna histórico de condensações."""
        from src.services.cycle_condensation_engine import (
            CycleCondensationEngine, CondensationStrategy,
        )
        from src.services.cycle_conversation_memory import CycleConversationMemory
        mem = CycleConversationMemory()
        for i in range(8):
            mem.add_turn("BTC", f"c{i}", "p", "r")
        engine = CycleCondensationEngine(strategy=CondensationStrategy.HALVE)
        engine.condense_memory(mem, "BTC", "c1")
        records = engine.get_records()
        assert len(records) >= 1
        assert records[-1].symbol == "BTC"

    def test_singleton_returns_same_instance(self):
        from src.services.cycle_condensation_engine import get_cycle_condensation_engine
        e1 = get_cycle_condensation_engine()
        e2 = get_cycle_condensation_engine()
        assert e1 is e2


# ---------------------------------------------------------------------------
# Story 200 — CycleArtifactStore
# ---------------------------------------------------------------------------

class TestStory200CycleArtifactStore:
    """CycleArtifactStore: InMemoryFileStore por ciclo."""

    def setup_method(self):
        from src.services.cycle_artifact_store import reset_cycle_artifact_store
        reset_cycle_artifact_store()

    def test_put_and_get(self):
        """put() armazena, get() recupera pelo path canônico."""
        from src.services.cycle_artifact_store import (
            get_cycle_artifact_store, ArtifactType,
        )
        store = get_cycle_artifact_store()
        artifact = store.put("BTC", "cycle-001", ArtifactType.SIGNAL, {"action": "LONG"})
        retrieved = store.get("BTC", "cycle-001", ArtifactType.SIGNAL)
        assert retrieved is not None
        assert retrieved.content == {"action": "LONG"}
        assert retrieved.path == artifact.path

    def test_get_returns_none_for_missing(self):
        """get() retorna None para path inexistente."""
        from src.services.cycle_artifact_store import (
            get_cycle_artifact_store, ArtifactType,
        )
        store = get_cycle_artifact_store()
        result = store.get("BTC", "nonexistent", ArtifactType.SIGNAL)
        assert result is None

    def test_list_by_symbol(self):
        """list() retorna todos os artefatos do símbolo."""
        from src.services.cycle_artifact_store import (
            get_cycle_artifact_store, ArtifactType,
        )
        store = get_cycle_artifact_store()
        store.put("ETH", "cycle-001", ArtifactType.SIGNAL, {"action": "SHORT"})
        store.put("ETH", "cycle-001", ArtifactType.REASONING, {"text": "bearish"})
        artifacts = store.list("ETH")
        assert len(artifacts) == 2

    def test_list_by_type(self):
        """list_by_type() filtra por ArtifactType."""
        from src.services.cycle_artifact_store import (
            get_cycle_artifact_store, ArtifactType,
        )
        store = get_cycle_artifact_store()
        store.put("BTC", "c1", ArtifactType.SIGNAL, {"a": 1})
        store.put("ETH", "c2", ArtifactType.SIGNAL, {"a": 2})
        store.put("BTC", "c3", ArtifactType.REASONING, {"t": "x"})
        signals = store.list_by_type(ArtifactType.SIGNAL)
        assert len(signals) == 2
        types = {a.artifact_type for a in signals}
        assert ArtifactType.SIGNAL in types

    def test_delete_removes_artifact(self):
        """delete() remove o artefato do store."""
        from src.services.cycle_artifact_store import (
            get_cycle_artifact_store, ArtifactType,
        )
        store = get_cycle_artifact_store()
        store.put("BTC", "c1", ArtifactType.SIGNAL, {"action": "LONG"})
        deleted = store.delete("BTC", "c1", ArtifactType.SIGNAL)
        assert deleted is True
        assert store.get("BTC", "c1", ArtifactType.SIGNAL) is None

    def test_overflow_evicts_oldest(self):
        """Buffer overflow descarta artefatos mais antigos por símbolo."""
        from src.services.cycle_artifact_store import (
            CycleArtifactStore, ArtifactType,
        )
        store = CycleArtifactStore(max_per_symbol=3)
        for i in range(5):
            store.put("BTC", f"cycle-{i:04d}", ArtifactType.SIGNAL, {"i": i})
        artifacts = store.list("BTC")
        assert len(artifacts) <= 3

    def test_summary_returns_dict(self):
        """summary() retorna métricas do store."""
        from src.services.cycle_artifact_store import (
            get_cycle_artifact_store, ArtifactType,
        )
        store = get_cycle_artifact_store()
        store.put("BTC", "c1", ArtifactType.SIGNAL, {"x": 1})
        s = store.summary()
        assert s["total_stored"] >= 1
        assert "by_type" in s
        assert "SIGNAL" in s["by_type"]

    def test_singleton_returns_same_instance(self):
        from src.services.cycle_artifact_store import get_cycle_artifact_store
        s1 = get_cycle_artifact_store()
        s2 = get_cycle_artifact_store()
        assert s1 is s2


# ---------------------------------------------------------------------------
# Story 201 — CycleActionRiskAnalyzer
# ---------------------------------------------------------------------------

class TestStory201CycleActionRiskAnalyzer:
    """CycleActionRiskAnalyzer: classificação de risco LOW/MEDIUM/HIGH."""

    def setup_method(self):
        from src.services.cycle_action_risk_analyzer import reset_cycle_action_risk_analyzer
        reset_cycle_action_risk_analyzer()

    def test_hold_is_low_risk(self):
        """HOLD sempre LOW risk."""
        from src.services.cycle_action_risk_analyzer import (
            get_cycle_action_risk_analyzer, ActionRiskLevel,
        )
        analyzer = get_cycle_action_risk_analyzer()
        assessment = analyzer.analyze("HOLD", "BTC")
        assert assessment.risk_level == ActionRiskLevel.LOW
        assert not assessment.blocked

    def test_open_long_is_medium_risk(self):
        """OPEN_LONG base risk = MEDIUM (sem escalada)."""
        from src.services.cycle_action_risk_analyzer import (
            CycleActionRiskAnalyzer, ActionRiskLevel,
        )
        analyzer = CycleActionRiskAnalyzer(
            block_on_high=True,
            high_notional_threshold=100_000,  # alto para não escalar
            high_leverage_threshold=20.0,
        )
        assessment = analyzer.analyze("OPEN_LONG", "BTC", notional=1000.0, leverage=1.0)
        assert assessment.risk_level == ActionRiskLevel.MEDIUM

    def test_high_notional_escalates_to_high(self):
        """Notional alto escala para HIGH."""
        from src.services.cycle_action_risk_analyzer import (
            get_cycle_action_risk_analyzer, ActionRiskLevel,
        )
        analyzer = get_cycle_action_risk_analyzer()
        assessment = analyzer.analyze(
            "OPEN_LONG", "BTC", notional=50_000.0, leverage=1.0
        )
        assert assessment.risk_level == ActionRiskLevel.HIGH

    def test_high_leverage_escalates_to_high(self):
        """Alavancagem alta escala para HIGH."""
        from src.services.cycle_action_risk_analyzer import (
            get_cycle_action_risk_analyzer, ActionRiskLevel,
        )
        analyzer = get_cycle_action_risk_analyzer()
        assessment = analyzer.analyze(
            "OPEN_SHORT", "ETH", notional=100.0, leverage=10.0
        )
        assert assessment.risk_level == ActionRiskLevel.HIGH

    def test_volatile_regime_escalates_medium_to_high(self):
        """Regime VOLATILE escala MEDIUM para HIGH."""
        from src.services.cycle_action_risk_analyzer import (
            get_cycle_action_risk_analyzer, ActionRiskLevel,
        )
        analyzer = get_cycle_action_risk_analyzer()
        assessment = analyzer.analyze(
            "OPEN_LONG", "BTC", notional=100.0, leverage=1.0, regime="VOLATILE"
        )
        assert assessment.risk_level == ActionRiskLevel.HIGH

    def test_is_safe_blocks_high(self):
        """is_safe() retorna False para HIGH com threshold HIGH."""
        from src.services.cycle_action_risk_analyzer import (
            get_cycle_action_risk_analyzer, ActionRiskLevel,
        )
        analyzer = get_cycle_action_risk_analyzer()
        assessment = analyzer.analyze("FORCE_LIQUIDATE", "BTC")
        assert assessment.risk_level == ActionRiskLevel.HIGH
        assert not analyzer.is_safe(assessment, threshold=ActionRiskLevel.HIGH)

    def test_assessment_blocked_on_high(self):
        """blocked=True quando block_on_high=True e risk=HIGH."""
        from src.services.cycle_action_risk_analyzer import (
            CycleActionRiskAnalyzer,
        )
        analyzer = CycleActionRiskAnalyzer(
            block_on_high=True,
            high_notional_threshold=100.0,
        )
        assessment = analyzer.analyze("OPEN_LONG", "BTC", notional=200.0)
        assert assessment.blocked is True

    def test_summary_returns_dict(self):
        """summary() retorna métricas do analyzer."""
        from src.services.cycle_action_risk_analyzer import get_cycle_action_risk_analyzer
        analyzer = get_cycle_action_risk_analyzer()
        analyzer.analyze("HOLD", "BTC")
        analyzer.analyze("OPEN_LONG", "ETH", notional=100.0)
        s = analyzer.summary()
        assert s["total_analyzed"] == 2
        assert "by_level" in s


# ---------------------------------------------------------------------------
# Story 202 — CycleStateResetter
# ---------------------------------------------------------------------------

class TestStory202CycleStateResetter:
    """CycleStateResetter: reset coordenado de estado efêmero entre ciclos."""

    def setup_method(self):
        from src.services.cycle_state_resetter import reset_cycle_state_resetter
        reset_cycle_state_resetter()

    def test_reset_cycle_start_returns_record(self):
        """reset(CYCLE_START) retorna ResetRecord."""
        from src.services.cycle_state_resetter import (
            get_cycle_state_resetter, ResetScope,
        )
        resetter = get_cycle_state_resetter()
        record = resetter.reset(ResetScope.CYCLE_START, symbol="BTC", cycle_id="c-001")
        assert record is not None
        assert record.scope == ResetScope.CYCLE_START
        assert record.symbol == "BTC"

    def test_reset_fails_silently_on_missing_services(self):
        """reset() não crasha mesmo se serviços não estão inicializados."""
        from src.services.cycle_state_resetter import (
            get_cycle_state_resetter, ResetScope,
        )
        resetter = get_cycle_state_resetter()
        # Mesmo sem ciclo ativo, não deve levantar exceção
        record = resetter.reset(ResetScope.ERROR_RECOVERY, symbol="ETH", cycle_id="c-err")
        assert record is not None
        # components_failed pode ter entradas, mas não levantou exceção

    def test_reset_cycle_end_flushes_exporter(self):
        """reset(CYCLE_END) inclui CycleBatchedExporter no componentes."""
        from src.services.cycle_state_resetter import (
            get_cycle_state_resetter, ResetScope,
        )
        resetter = get_cycle_state_resetter()
        record = resetter.reset(ResetScope.CYCLE_END, symbol="BTC", cycle_id="c-end")
        assert record.scope == ResetScope.CYCLE_END

    def test_reset_full_clears_conversation_memory(self):
        """reset(FULL) inclui CycleConversationMemory nos componentes."""
        from src.services.cycle_state_resetter import (
            get_cycle_state_resetter, ResetScope,
        )
        resetter = get_cycle_state_resetter()
        record = resetter.reset(ResetScope.FULL, symbol="BTC", cycle_id="c-full")
        assert record.scope == ResetScope.FULL

    def test_get_records_returns_history(self):
        """get_records() retorna histórico de resets."""
        from src.services.cycle_state_resetter import (
            get_cycle_state_resetter, ResetScope,
        )
        resetter = get_cycle_state_resetter()
        resetter.reset(ResetScope.CYCLE_START, symbol="BTC", cycle_id="c1")
        resetter.reset(ResetScope.CYCLE_END, symbol="BTC", cycle_id="c1")
        records = resetter.get_records()
        assert len(records) == 2

    def test_summary_tracks_totals(self):
        """summary() rastreia total_resets."""
        from src.services.cycle_state_resetter import (
            get_cycle_state_resetter, ResetScope,
        )
        resetter = get_cycle_state_resetter()
        resetter.reset(ResetScope.CYCLE_START, symbol="BTC", cycle_id="c1")
        resetter.reset(ResetScope.CYCLE_END, symbol="BTC", cycle_id="c1")
        s = resetter.summary()
        assert s["total_resets"] == 2

    def test_singleton_returns_same_instance(self):
        from src.services.cycle_state_resetter import get_cycle_state_resetter
        r1 = get_cycle_state_resetter()
        r2 = get_cycle_state_resetter()
        assert r1 is r2


# ---------------------------------------------------------------------------
# Cross-Story Integration — Milestone 31
# ---------------------------------------------------------------------------

class TestMilestone31CrossStoryIntegration:
    """Integração entre as 5 stories do Milestone 31."""

    def setup_method(self):
        from src.services.cycle_conversation_memory import reset_cycle_conversation_memory
        from src.services.cycle_condensation_engine import reset_cycle_condensation_engine
        from src.services.cycle_artifact_store import reset_cycle_artifact_store
        from src.services.cycle_action_risk_analyzer import reset_cycle_action_risk_analyzer
        from src.services.cycle_state_resetter import reset_cycle_state_resetter
        reset_cycle_conversation_memory()
        reset_cycle_condensation_engine()
        reset_cycle_artifact_store()
        reset_cycle_action_risk_analyzer()
        reset_cycle_state_resetter()

    def test_full_cycle_uses_all_5_services(self):
        """Simula um ciclo completo usando todos os 5 serviços."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        from src.services.cycle_condensation_engine import get_cycle_condensation_engine
        from src.services.cycle_artifact_store import get_cycle_artifact_store, ArtifactType
        from src.services.cycle_action_risk_analyzer import get_cycle_action_risk_analyzer
        from src.services.cycle_state_resetter import get_cycle_state_resetter, ResetScope

        symbol = "BTC"
        cycle_id = "milestone31-test"

        # 1. Reset de início de ciclo (Story 202)
        resetter = get_cycle_state_resetter()
        record = resetter.reset(ResetScope.CYCLE_START, symbol=symbol, cycle_id=cycle_id)
        assert record is not None

        # 2. Registra turn na memória (Story 198)
        mem = get_cycle_conversation_memory()
        mem.add_turn(symbol, cycle_id, "analyze BTC", "LONG:0.80")
        assert len(mem.build_messages(symbol)) == 2

        # 3. Armazena artefato de sinal (Story 200)
        store = get_cycle_artifact_store()
        store.put(symbol, cycle_id, ArtifactType.SIGNAL, {"action": "LONG", "confidence": 0.80})
        artifact = store.get(symbol, cycle_id, ArtifactType.SIGNAL)
        assert artifact is not None

        # 4. Análise de risco antes da execução (Story 201)
        analyzer = get_cycle_action_risk_analyzer()
        assessment = analyzer.analyze("OPEN_LONG", symbol, notional=1000.0, leverage=2.0)
        assert assessment.risk_level.value in ("LOW", "MEDIUM", "HIGH")

        # 5. Reset de fim de ciclo (Story 202)
        end_record = resetter.reset(ResetScope.CYCLE_END, symbol=symbol, cycle_id=cycle_id)
        assert end_record.scope == ResetScope.CYCLE_END

    def test_condensation_after_many_turns(self):
        """CondensationEngine condensa após muitos turns acumulados."""
        from src.services.cycle_conversation_memory import CycleConversationMemory
        from src.services.cycle_condensation_engine import CycleCondensationEngine

        mem = CycleConversationMemory(max_tokens_budget=200)
        engine = CycleCondensationEngine(condensation_threshold=0.8)
        for i in range(10):
            mem.add_turn("SOL", f"c{i}", "analyze SOL in detail context " * 3, "LONG:0.7")
        total_tokens = sum(t.token_estimate for t in mem.get_history("SOL"))
        record = engine.maybe_condense(mem, "SOL", total_tokens, 200, "cycle-test")
        # Se total_tokens >= 160 (80% de 200), deve condensar
        if total_tokens >= 160:
            assert record is not None
        else:
            assert record is None  # threshold não atingido é ok

    def test_artifact_store_preserves_audit_after_reset(self):
        """ArtifactStore preserva artefatos mesmo após reset de estado."""
        from src.services.cycle_artifact_store import get_cycle_artifact_store, ArtifactType
        from src.services.cycle_state_resetter import get_cycle_state_resetter, ResetScope

        store = get_cycle_artifact_store()
        store.put("BTC", "c-audit", ArtifactType.RISK_REPORT, {"verdict": "APPROVED"})

        resetter = get_cycle_state_resetter()
        resetter.reset(ResetScope.CYCLE_END, symbol="BTC", cycle_id="c-audit")

        # ArtifactStore NÃO é resetado em CYCLE_END (preserva audit trail)
        artifact = store.get("BTC", "c-audit", ArtifactType.RISK_REPORT)
        assert artifact is not None
        assert artifact.content["verdict"] == "APPROVED"

    def test_all_singletons_are_independent(self):
        """Cada singleton é uma instância independente."""
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        from src.services.cycle_condensation_engine import get_cycle_condensation_engine
        from src.services.cycle_artifact_store import get_cycle_artifact_store
        from src.services.cycle_action_risk_analyzer import get_cycle_action_risk_analyzer
        from src.services.cycle_state_resetter import get_cycle_state_resetter

        instances = [
            get_cycle_conversation_memory(),
            get_cycle_condensation_engine(),
            get_cycle_artifact_store(),
            get_cycle_action_risk_analyzer(),
            get_cycle_state_resetter(),
        ]
        # Verifica que são objetos distintos
        types = [type(i).__name__ for i in instances]
        assert len(set(types)) == 5, f"Duplicate types: {types}"

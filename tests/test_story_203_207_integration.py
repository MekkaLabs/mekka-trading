"""
tests/test_story_203_207_integration.py
========================================
Testes de integração — Milestone 32: AutoGen / CrewAI Patterns
Stories 203-207.

Story 203 — CycleGroupChatManager (AutoGen GroupChat + GroupChatManager)
Story 204 — MekkaConversationSession (AutoGen ConversableAgent.initiate_chat)
Story 205 — CycleTaskDefinition (CrewAI Task + expected_output)
Story 206 — CyclePipelineOrchestrator (CrewAI Process + Crew.kickoff)
Story 207 — MekkaAgentBackstory (CrewAI Agent.backstory)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Story 203 — CycleGroupChatManager
# ---------------------------------------------------------------------------

class TestStory203CycleGroupChatManager:
    """GroupChat multi-agente com speaker selection round_robin."""

    def setup_method(self):
        from src.services.cycle_group_chat import reset_cycle_group_chat_manager
        reset_cycle_group_chat_manager()

    def test_add_participant_and_run_round(self):
        """add_participant + run_round gera mensagens de todos os participantes."""
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        manager = get_cycle_group_chat_manager()
        manager.add_participant("vision", "analyst", lambda ctx, hist: f"LONG for {ctx['symbol']}")
        manager.add_participant("batman", "risk_guardian", lambda ctx, hist: "APPROVE: risk ok")
        msgs = manager.run_round("BTC", "c-001", context={"action": "LONG", "confidence": 0.80})
        assert len(msgs) >= 2
        agent_ids = {m.agent_id for m in msgs}
        assert "vision" in agent_ids
        assert "batman" in agent_ids

    def test_messages_contain_symbol(self):
        """Mensagens contêm o símbolo correto."""
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        manager = get_cycle_group_chat_manager()
        manager.add_participant("vision", "analyst")
        msgs = manager.run_round("ETH", "c-002")
        assert all(m.symbol == "ETH" for m in msgs)

    def test_round_robin_selection(self):
        """Round-robin distribui turnos igualmente."""
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        manager = get_cycle_group_chat_manager()
        manager.add_participant("a1", "role1")
        manager.add_participant("a2", "role2")
        msgs = manager.run_round("BTC", "c-003", max_round=2)
        speakers = [m.agent_id for m in msgs]
        # Com 2 participantes e 2 rounds, cada um fala 2x = 4 msgs
        assert len(speakers) == 4

    def test_get_consensus_majority_vote(self):
        """get_consensus() retorna majority_vote correto."""
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        manager = get_cycle_group_chat_manager()
        # 2 LONG e 1 SHORT → majority = LONG
        manager.add_participant("v1", "r1", lambda ctx, h: "LONG signal detected")
        manager.add_participant("v2", "r2", lambda ctx, h: "LONG confirmed")
        manager.add_participant("v3", "r3", lambda ctx, h: "SHORT signal weak")
        manager.run_round("BTC", "c-004")
        consensus = manager.get_consensus("BTC")
        assert consensus["majority_vote"] == "LONG"
        assert consensus["vote_counts"]["LONG"] >= 2

    def test_no_participants_returns_empty(self):
        """run_round sem participantes retorna lista vazia."""
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        manager = get_cycle_group_chat_manager()
        msgs = manager.run_round("BTC", "c-empty")
        assert msgs == []

    def test_summary_returns_dict(self):
        """summary() retorna métricas do manager."""
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        manager = get_cycle_group_chat_manager()
        manager.add_participant("vision", "analyst")
        manager.run_round("BTC", "c-s1")
        s = manager.summary()
        assert s["total_sessions"] == 1
        assert "participants" in s

    def test_singleton_returns_same_instance(self):
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        m1 = get_cycle_group_chat_manager()
        m2 = get_cycle_group_chat_manager()
        assert m1 is m2


# ---------------------------------------------------------------------------
# Story 204 — MekkaConversationSession
# ---------------------------------------------------------------------------

class TestStory204MekkaConversationSession:
    """Sessão de conversa estruturada com término automático."""

    def setup_method(self):
        from src.services.mekka_conversation_session import reset_conversation_sessions
        reset_conversation_sessions()

    def test_run_basic_session(self):
        """run() executa conversa e retorna SessionSummary."""
        from src.services.mekka_conversation_session import MekkaConversationSession
        session = MekkaConversationSession(
            initiator_id="Vision",
            recipient_id="Critic",
            max_turns=2,
        )
        summary = session.run(
            initiator_fn=lambda msg, hist: f"revised: {msg[:20]}",
            recipient_fn=lambda msg, hist: "ENDORSE: signal is valid",
            initial_msg="Analyze BTC: LONG signal",
            symbol="BTC",
            cycle_id="c-001",
        )
        assert summary.turn_count <= 2
        assert summary.symbol == "BTC"
        assert len(summary.turns) >= 1

    def test_termination_msg_ends_early(self):
        """is_termination_msg para a conversa antes de max_turns."""
        from src.services.mekka_conversation_session import (
            MekkaConversationSession, TerminationReason,
        )
        session = MekkaConversationSession(
            initiator_id="A",
            recipient_id="B",
            max_turns=5,
            is_termination_msg=lambda msg: "ENDORSE" in msg,
        )
        summary = session.run(
            initiator_fn=lambda msg, hist: "continue",
            recipient_fn=lambda msg, hist: "ENDORSE: approved",
            initial_msg="start",
        )
        assert summary.termination_reason == TerminationReason.TERMINATION_MSG
        assert summary.turn_count == 1  # para no primeiro ENDORSE

    def test_max_turns_termination(self):
        """Termina em MAX_TURNS quando is_termination_msg nunca dispara."""
        from src.services.mekka_conversation_session import (
            MekkaConversationSession, TerminationReason,
        )
        session = MekkaConversationSession(max_turns=3)
        summary = session.run(
            initiator_fn=lambda msg, hist: "keep going",
            recipient_fn=lambda msg, hist: "no termination here",
            initial_msg="start",
        )
        assert summary.termination_reason == TerminationReason.MAX_TURNS
        assert summary.turn_count == 3

    def test_last_msg_summary_method(self):
        """summary_method='last_msg' retorna a última reply."""
        from src.services.mekka_conversation_session import MekkaConversationSession
        session = MekkaConversationSession(max_turns=2, summary_method="last_msg")
        summary = session.run(
            initiator_fn=lambda msg, hist: "follow up",
            recipient_fn=lambda msg, hist: f"reply turn {len(hist)+1}",
            initial_msg="start",
        )
        assert "reply" in summary.summary.lower()

    def test_carryover_injects_context(self):
        """carryover injeta contexto no início da conversa."""
        from src.services.mekka_conversation_session import MekkaConversationSession
        received_msgs = []
        session = MekkaConversationSession(
            max_turns=1,
            carryover=["Previous context: BTC bullish"],
        )
        session.run(
            initiator_fn=lambda msg, hist: "ok",
            recipient_fn=lambda msg, hist: received_msgs.append(msg) or "reply",
            initial_msg="new prompt",
        )
        assert any("Previous context" in m for m in received_msgs)

    def test_get_recent_sessions(self):
        """get_recent_sessions() retorna histórico de sessões."""
        from src.services.mekka_conversation_session import get_conversation_session
        session = get_conversation_session("Vision", "Critic", max_turns=1)
        session.run(
            initiator_fn=lambda msg, hist: "ok",
            recipient_fn=lambda msg, hist: "done",
            initial_msg="test",
            symbol="BTC",
        )
        recent = session.get_recent_sessions(symbol="BTC")
        assert len(recent) == 1


# ---------------------------------------------------------------------------
# Story 205 — CycleTaskDefinition
# ---------------------------------------------------------------------------

class TestStory205CycleTaskDefinition:
    """CycleTaskRunner: execução sequencial de tasks declarativas."""

    def setup_method(self):
        from src.services.cycle_task_definition import reset_cycle_task_runner
        reset_cycle_task_runner()

    def test_register_and_run_task(self):
        """register + run executa a task e retorna CycleTaskResult."""
        from src.services.cycle_task_definition import (
            get_cycle_task_runner, CycleTaskDefinition, TaskAgentRole, TaskStatus,
        )
        runner = get_cycle_task_runner()
        task = CycleTaskDefinition(
            task_id="analysis",
            description="Analisar BTC",
            expected_output="price_change, volume_spike",
            agent_role=TaskAgentRole.NICKFURY,
        )
        runner.register(task)
        result = runner.run(
            "analysis",
            context={"symbol": "BTC"},
            executor_fn=lambda t, ctx: {"price_change": 2.5, "volume_spike": True},
        )
        assert result.status == TaskStatus.COMPLETED
        assert result.raw_output["price_change"] == 2.5

    def test_failed_task_returns_failed_status(self):
        """Executor que levanta exceção retorna status FAILED."""
        from src.services.cycle_task_definition import (
            get_cycle_task_runner, CycleTaskDefinition, TaskAgentRole, TaskStatus,
        )
        runner = get_cycle_task_runner()
        task = CycleTaskDefinition(
            task_id="fail_task",
            description="Task que falha",
            expected_output="never",
            agent_role=TaskAgentRole.SYSTEM,
        )
        runner.register(task)
        result = runner.run(
            "fail_task",
            executor_fn=lambda t, ctx: (_ for _ in ()).throw(RuntimeError("intentional fail")),
        )
        assert result.status == TaskStatus.FAILED

    def test_validator_fn_rejects_bad_output(self):
        """validator_fn que retorna False marca resultado como FAILED."""
        from src.services.cycle_task_definition import (
            get_cycle_task_runner, CycleTaskDefinition, TaskAgentRole, TaskStatus,
        )
        runner = get_cycle_task_runner()
        task = CycleTaskDefinition(
            task_id="validated",
            description="Task com validação",
            expected_output="output must be dict",
            agent_role=TaskAgentRole.VISION,
            validator_fn=lambda output: isinstance(output, dict),
        )
        runner.register(task)
        result = runner.run(
            "validated",
            executor_fn=lambda t, ctx: "this is not a dict",
        )
        assert result.status == TaskStatus.FAILED
        assert not result.validation_passed

    def test_run_chain_propagates_context(self):
        """run_chain() encadeia outputs como contexto."""
        from src.services.cycle_task_definition import (
            get_cycle_task_runner, CycleTaskDefinition, TaskAgentRole,
        )
        runner = get_cycle_task_runner()
        runner.register(CycleTaskDefinition("t1", "Task 1", "out", TaskAgentRole.NICKFURY))
        runner.register(CycleTaskDefinition("t2", "Task 2", "out", TaskAgentRole.VISION,
                                            context_task_ids=["t1"]))
        captured = {}
        def exec_t2(task, ctx):
            captured["has_t1"] = "context_t1" in ctx
            return ctx
        results = runner.run_chain(
            ["t1", "t2"],
            context={"symbol": "BTC"},
            executors={"t1": lambda t, ctx: {"result": "analysis_done"},
                       "t2": exec_t2},
        )
        assert len(results) == 2
        assert captured.get("has_t1") is True

    def test_run_unregistered_task_returns_failed(self):
        """Tentar executar task não registrada retorna FAILED."""
        from src.services.cycle_task_definition import (
            get_cycle_task_runner, TaskStatus,
        )
        runner = get_cycle_task_runner()
        result = runner.run("nonexistent_task")
        assert result.status == TaskStatus.FAILED

    def test_summary_tracks_totals(self):
        """summary() rastreia tasks registradas e executadas."""
        from src.services.cycle_task_definition import (
            get_cycle_task_runner, CycleTaskDefinition, TaskAgentRole,
        )
        runner = get_cycle_task_runner()
        runner.register(CycleTaskDefinition("t1", "d", "o", TaskAgentRole.SYSTEM))
        runner.run("t1", executor_fn=lambda t, ctx: "done")
        s = runner.summary()
        assert s["registered_tasks"] == 1
        assert s["total_executed"] == 1


# ---------------------------------------------------------------------------
# Story 206 — CyclePipelineOrchestrator
# ---------------------------------------------------------------------------

class TestStory206CyclePipelineOrchestrator:
    """CyclePipelineOrchestrator: kickoff sequential e hierarchical."""

    def setup_method(self):
        from src.services.cycle_pipeline_orchestrator import reset_cycle_pipeline_orchestrator
        reset_cycle_pipeline_orchestrator()

    def test_sequential_kickoff_runs_all_stages(self):
        """kickoff sequential executa todos os stages em ordem."""
        from src.services.cycle_pipeline_orchestrator import (
            get_cycle_pipeline_orchestrator, PipelineStage, PipelineProcess,
            PipelineStageStatus,
        )
        orch = get_cycle_pipeline_orchestrator()
        order = []
        orch.register_stage(PipelineStage("s1", "Stage 1", "NICKFURY",
                                          executor_fn=lambda ctx: order.append("s1") or {"s": 1}))
        orch.register_stage(PipelineStage("s2", "Stage 2", "VISION",
                                          executor_fn=lambda ctx: order.append("s2") or {"s": 2}))
        output = orch.kickoff("BTC", "c-001", process=PipelineProcess.SEQUENTIAL)
        assert output.success is True
        assert order == ["s1", "s2"]
        assert "s1" in output.completed_stages
        assert "s2" in output.completed_stages

    def test_sequential_passes_output_as_context(self):
        """Stage 2 recebe output_s1 como contexto."""
        from src.services.cycle_pipeline_orchestrator import (
            get_cycle_pipeline_orchestrator, PipelineStage, PipelineProcess,
        )
        orch = get_cycle_pipeline_orchestrator()
        orch.register_stage(PipelineStage("s1", "Stage 1", "NICKFURY",
                                          executor_fn=lambda ctx: {"result": "analysis"}))
        received = {}
        def s2_exec(ctx):
            received.update(ctx)
            return {"done": True}
        orch.register_stage(PipelineStage("s2", "Stage 2", "VISION", executor_fn=s2_exec))
        orch.kickoff("BTC", "c-002", process=PipelineProcess.SEQUENTIAL)
        assert "output_s1" in received
        assert received["output_s1"]["result"] == "analysis"

    def test_hierarchical_skips_ironman_on_hold(self):
        """Hierárquico pula IRONMAN quando action=HOLD."""
        from src.services.cycle_pipeline_orchestrator import (
            get_cycle_pipeline_orchestrator, PipelineStage, PipelineProcess,
            PipelineStageStatus,
        )
        orch = get_cycle_pipeline_orchestrator()
        orch.register_stage(PipelineStage("vision", "Vision", "VISION",
                                          executor_fn=lambda ctx: {"action": "HOLD"}))
        orch.register_stage(PipelineStage("ironman", "IronMan", "IRONMAN",
                                          executor_fn=lambda ctx: {"order": "placed"},
                                          required=False))
        output = orch.kickoff("BTC", "c-h1", process=PipelineProcess.HIERARCHICAL)
        ironman_result = next(r for r in output.stage_results if r.stage_id == "ironman")
        assert ironman_result.status == PipelineStageStatus.SKIPPED

    def test_failed_required_stage_marks_output_failed(self):
        """Stage required que falha → output.success=False."""
        from src.services.cycle_pipeline_orchestrator import (
            get_cycle_pipeline_orchestrator, PipelineStage, PipelineProcess,
        )
        orch = get_cycle_pipeline_orchestrator()
        orch.register_stage(PipelineStage("fail_stage", "Fail", "SYSTEM",
                                          executor_fn=lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")),
                                          required=True))
        output = orch.kickoff("BTC", "c-f1", process=PipelineProcess.SEQUENTIAL)
        assert output.success is False
        assert "fail_stage" in output.failed_stages

    def test_summary_tracks_kickoffs(self):
        """summary() rastreia total_kickoffs."""
        from src.services.cycle_pipeline_orchestrator import (
            get_cycle_pipeline_orchestrator, PipelineStage,
        )
        orch = get_cycle_pipeline_orchestrator()
        orch.register_stage(PipelineStage("s", "S", "SYSTEM", executor_fn=lambda ctx: "ok"))
        orch.kickoff("BTC", "c1")
        orch.kickoff("ETH", "c2")
        s = orch.summary()
        assert s["total_kickoffs"] == 2

    def test_singleton_returns_same_instance(self):
        from src.services.cycle_pipeline_orchestrator import get_cycle_pipeline_orchestrator
        o1 = get_cycle_pipeline_orchestrator()
        o2 = get_cycle_pipeline_orchestrator()
        assert o1 is o2


# ---------------------------------------------------------------------------
# Story 207 — MekkaAgentBackstory
# ---------------------------------------------------------------------------

class TestStory207MekkaAgentBackstory:
    """MekkaAgentBackstory: role + goal + backstory por agente."""

    def setup_method(self):
        from src.services.mekka_agent_backstory import reset_mekka_agent_backstory
        reset_mekka_agent_backstory()

    def test_default_personas_loaded(self):
        """Personas padrão (VISION, BATMAN, NICKFURY, IRONMAN) são carregadas."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        agents = backstory.list_agents()
        for expected in ["VISION", "BATMAN", "NICKFURY", "IRONMAN"]:
            assert expected in agents

    def test_build_system_prompt_contains_role_and_goal(self):
        """build_system_prompt contém Role e Goal do agente."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        prompt = backstory.build_system_prompt("VISION")
        assert "Role" in prompt
        assert "Goal" in prompt
        assert "Background" in prompt

    def test_build_system_prompt_with_extra_context(self):
        """extra_context é injetado no prompt."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        prompt = backstory.build_system_prompt("VISION", extra_context="BTC regime: BULL")
        assert "BTC regime: BULL" in prompt
        assert "Current Context" in prompt

    def test_unknown_agent_returns_minimal_prompt(self):
        """Agente desconhecido retorna prompt mínimo sem crash."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        prompt = backstory.build_system_prompt("UNKNOWN_AGENT")
        assert len(prompt) > 0
        assert "UNKNOWN_AGENT" in prompt

    def test_update_backstory_adds_performance_note(self):
        """update_backstory() adiciona nota ao backstory dinâmico."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        success = backstory.update_backstory("VISION", "Acerto de 82% nas últimas 20 decisões")
        assert success is True
        persona = backstory.get_persona("VISION")
        assert len(persona.performance_notes) == 1
        assert "82%" in persona.performance_notes[0]

    def test_performance_notes_appear_in_prompt(self):
        """Notas de performance aparecem no system prompt."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        backstory.update_backstory("BATMAN", "Zerou 3 trades ruins esta semana")
        prompt = backstory.build_system_prompt("BATMAN")
        assert "Recent Performance" in prompt
        assert "Zerou 3 trades ruins" in prompt

    def test_register_custom_persona(self):
        """register() adiciona persona customizado."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        backstory.register(
            agent_id="HAWKEYE",
            role="Scalping Specialist",
            goal="Identify short-term momentum trades",
            backstory="Expert in 1m-5m chart patterns",
        )
        persona = backstory.get_persona("HAWKEYE")
        assert persona is not None
        assert persona.role == "Scalping Specialist"

    def test_summary_returns_all_agents(self):
        """summary() retorna todos os agentes registrados."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        backstory = get_mekka_agent_backstory()
        s = backstory.summary()
        assert s["total_personas"] >= 4
        assert "VISION" in s["personas"]


# ---------------------------------------------------------------------------
# Cross-Story Integration — Milestone 32
# ---------------------------------------------------------------------------

class TestMilestone32CrossStoryIntegration:
    """Integração entre as 5 stories do Milestone 32."""

    def setup_method(self):
        from src.services.cycle_group_chat import reset_cycle_group_chat_manager
        from src.services.mekka_conversation_session import reset_conversation_sessions
        from src.services.cycle_task_definition import reset_cycle_task_runner
        from src.services.cycle_pipeline_orchestrator import reset_cycle_pipeline_orchestrator
        from src.services.mekka_agent_backstory import reset_mekka_agent_backstory
        reset_cycle_group_chat_manager()
        reset_conversation_sessions()
        reset_cycle_task_runner()
        reset_cycle_pipeline_orchestrator()
        reset_mekka_agent_backstory()

    def test_backstory_enriches_group_chat_participant(self):
        """Backstory do Vision alimenta a opinion_fn do GroupChat."""
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        backstory = get_mekka_agent_backstory()
        manager = get_cycle_group_chat_manager()

        def vision_opinion(ctx, hist):
            prompt = backstory.build_system_prompt("VISION")
            # Simula: usa backstory para dar opinião
            return f"[VISION] Based on my role as '{prompt[:30]}...': LONG"

        manager.add_participant("VISION", "analyst", vision_opinion)
        msgs = manager.run_round("BTC", "c-001", context={"action": "LONG", "confidence": 0.80})
        assert len(msgs) >= 1
        assert "LONG" in msgs[0].content

    def test_pipeline_uses_task_definitions(self):
        """Pipeline Orchestrator usa CycleTaskDefinition para validar outputs."""
        from src.services.cycle_task_definition import (
            get_cycle_task_runner, CycleTaskDefinition, TaskAgentRole,
        )
        from src.services.cycle_pipeline_orchestrator import (
            get_cycle_pipeline_orchestrator, PipelineStage,
        )
        runner = get_cycle_task_runner()
        orch = get_cycle_pipeline_orchestrator()

        # Registra task com validação
        task = CycleTaskDefinition(
            task_id="vision_signal",
            description="Gerar sinal Vision",
            expected_output="dict com action e confidence",
            agent_role=TaskAgentRole.VISION,
            validator_fn=lambda o: isinstance(o, dict) and "action" in o,
        )
        runner.register(task)

        # Stage do pipeline usa o runner
        def vision_stage(ctx):
            result = runner.run(
                "vision_signal",
                context=ctx,
                executor_fn=lambda t, c: {"action": "LONG", "confidence": 0.80},
            )
            return result.raw_output if result.is_successful else None

        orch.register_stage(PipelineStage("vision", "Vision Stage", "VISION",
                                          executor_fn=vision_stage))
        output = orch.kickoff("BTC", "c-combo")
        assert output.success is True

    def test_conversation_session_with_termination(self):
        """ConversationSession termina antecipadamente com ENDORSE."""
        from src.services.mekka_conversation_session import (
            MekkaConversationSession, TerminationReason,
        )
        session = MekkaConversationSession(
            initiator_id="Vision",
            recipient_id="Batman",
            max_turns=5,
            is_termination_msg=lambda msg: "APPROVE" in msg,
        )
        summary = session.run(
            initiator_fn=lambda msg, hist: "Signal: LONG BTC 0.85",
            recipient_fn=lambda msg, hist: "APPROVE: risk within limits",
            initial_msg="Validate this signal",
            symbol="BTC",
            cycle_id="c-conv",
        )
        assert summary.termination_reason == TerminationReason.TERMINATION_MSG
        assert summary.turn_count == 1

    def test_all_singletons_independent(self):
        """Todos os singletons do Milestone 32 são instâncias distintas."""
        from src.services.cycle_group_chat import get_cycle_group_chat_manager
        from src.services.cycle_task_definition import get_cycle_task_runner
        from src.services.cycle_pipeline_orchestrator import get_cycle_pipeline_orchestrator
        from src.services.mekka_agent_backstory import get_mekka_agent_backstory
        instances = [
            get_cycle_group_chat_manager(),
            get_cycle_task_runner(),
            get_cycle_pipeline_orchestrator(),
            get_mekka_agent_backstory(),
        ]
        types = [type(i).__name__ for i in instances]
        assert len(set(types)) == 4, f"Duplicate types: {types}"

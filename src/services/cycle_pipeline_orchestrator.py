"""
src/services/cycle_pipeline_orchestrator.py
=============================================
Story 206 — CyclePipelineOrchestrator: orquestrador de pipeline com processo
sequencial ou hierárquico, inspirado no Process + Crew.kickoff() do CrewAI.

Inspirado no padrão CrewAI Process + Crew.kickoff()
(crewAIInc/crewAI, docs.crewai.com/how-to/sequential-process):
  "Process.sequential: tasks are executed one after the other in order.
   Each task's output becomes available to subsequent tasks as context.
   Ideal for linear, step-by-step workflows.

   Process.hierarchical: a manager agent is automatically assigned to
   coordinate planning, delegation, and validation. The manager can
   re-assign tasks, skip steps, or request clarification.

   crew.kickoff(inputs={...}) starts execution and returns CrewOutput
   with final output, token_usage, and task_outputs."

No CrewAI:
  Crew(agents, tasks, process=Process.sequential|hierarchical).kickoff()
  Crew retorna CrewOutput: final output + token_usage + task_outputs list.
  Manager agent (em hierarchical) pode delegar tasks para outros agentes.
  Tasks são encadeadas: output de task N injeta em context de task N+1.

No Mekka, o equivalente é:
  CyclePipelineOrchestrator encapsula a execução do pipeline completo:
    SEQUENTIAL: Analysis → Vision → Batman → IronMan (padrão atual)
    HIERARCHICAL: NickFury (manager) coordena → pode pular steps ou
                  re-executar Vision com contexto adicional
  kickoff(symbol, cycle_id, inputs) retorna PipelineOutput com
  resultados por etapa, duração total e status geral.

Arquitetura
-----------
  PipelineProcess     — enum SEQUENTIAL / HIERARCHICAL
  PipelineStage       — uma etapa do pipeline com executor
  PipelineOutput      — resultado completo do kickoff()
  CyclePipelineOrchestrator
    ├── register_stage(stage)
    ├── kickoff(symbol, cycle_id, inputs, process) → PipelineOutput
    ├── _run_sequential(symbol, cycle_id, inputs) → PipelineOutput
    ├── _run_hierarchical(symbol, cycle_id, inputs) → PipelineOutput
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# PipelineProcess
# ---------------------------------------------------------------------------

class PipelineProcess(str, Enum):
    """
    Modo de execução do pipeline.

    Mapeamento com CrewAI Process:
      SEQUENTIAL   ←→ Process.sequential (padrão)
      HIERARCHICAL ←→ Process.hierarchical (manager coordena)
    """
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"


# ---------------------------------------------------------------------------
# PipelineStageStatus
# ---------------------------------------------------------------------------

class PipelineStageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# PipelineStage — uma etapa do pipeline
# ---------------------------------------------------------------------------

@dataclass
class PipelineStage:
    """
    Etapa do pipeline com executor e metadados.

    Equivalente a um Task + Agent pair no CrewAI:
    o agente executa a task, o output alimenta a próxima etapa.
    """
    stage_id: str
    description: str
    agent_role: str           # ex: "VISION", "BATMAN", "IRONMAN"
    executor_fn: Optional[Callable[[Dict[str, Any]], Any]] = None
    required: bool = True     # se False, pode ser pulado em HIERARCHICAL
    timeout_s: float = 60.0

    def execute(self, context: Dict[str, Any]) -> Any:
        """Executa a etapa com o contexto fornecido."""
        if self.executor_fn is not None:
            return self.executor_fn(context)
        return context  # passthrough


# ---------------------------------------------------------------------------
# PipelineStageResult — resultado de uma etapa
# ---------------------------------------------------------------------------

@dataclass
class PipelineStageResult:
    """Resultado de uma etapa de pipeline."""
    stage_id: str
    agent_role: str
    status: PipelineStageStatus
    output: Any = None
    error_msg: str = ""
    duration_ms: float = 0.0
    skipped_reason: str = ""

    @property
    def is_successful(self) -> bool:
        return self.status in (PipelineStageStatus.COMPLETED, PipelineStageStatus.SKIPPED)

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id,
            "agent_role": self.agent_role,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "error_msg": self.error_msg,
            "skipped_reason": self.skipped_reason,
            "is_successful": self.is_successful,
        }


# ---------------------------------------------------------------------------
# PipelineOutput — resultado do kickoff()
# ---------------------------------------------------------------------------

@dataclass
class PipelineOutput:
    """
    Output completo de um kickoff().

    Equivalente ao CrewOutput do CrewAI:
    final_output + task_outputs + token_usage.
    """
    symbol: str
    cycle_id: str
    process: PipelineProcess
    stage_results: List[PipelineStageResult]
    final_output: Any = None
    total_duration_ms: float = 0.0
    success: bool = True
    error_msg: str = ""

    @property
    def completed_stages(self) -> List[str]:
        return [r.stage_id for r in self.stage_results if r.status == PipelineStageStatus.COMPLETED]

    @property
    def failed_stages(self) -> List[str]:
        return [r.stage_id for r in self.stage_results if r.status == PipelineStageStatus.FAILED]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "process": self.process.value,
            "success": self.success,
            "total_duration_ms": self.total_duration_ms,
            "completed_stages": self.completed_stages,
            "failed_stages": self.failed_stages,
            "stage_results": [r.to_dict() for r in self.stage_results],
        }


# ---------------------------------------------------------------------------
# CyclePipelineOrchestrator
# ---------------------------------------------------------------------------

class CyclePipelineOrchestrator:
    """
    Orquestra o pipeline de trading como sequência de stages declarativas.

    Padrão CrewAI Crew.kickoff() + Process.sequential/hierarchical:
    - Registra stages (agente + executor) em ordem
    - kickoff() executa o pipeline e retorna PipelineOutput
    - SEQUENTIAL: cada stage recebe o output da anterior como contexto
    - HIERARCHICAL: NickFury (manager) pode pular stages ou re-executar
    - Fail-silent: falha em stage não-required não trava o pipeline

    Uso:
        orch = get_cycle_pipeline_orchestrator()
        orch.register_stage(PipelineStage("analysis", "Análise de mercado", "NICKFURY", fn))
        orch.register_stage(PipelineStage("vision", "Decisão estratégica", "VISION", fn))
        output = orch.kickoff("BTC", cycle_id, inputs={"equity": 10000})
    """

    def __init__(
        self,
        default_process: PipelineProcess = PipelineProcess.SEQUENTIAL,
        max_outputs_stored: int = 50,
    ) -> None:
        self.default_process = default_process
        self.max_outputs_stored = max_outputs_stored

        self._stages: List[PipelineStage] = []
        self._stage_index: Dict[str, PipelineStage] = {}
        self._outputs: List[PipelineOutput] = []
        self._total_kickoffs: int = 0
        self._total_failures: int = 0

    def register_stage(self, stage: PipelineStage) -> None:
        """Registra uma etapa no pipeline (na ordem de registro)."""
        self._stages.append(stage)
        self._stage_index[stage.stage_id] = stage
        logger.debug(
            f"[PipelineOrch] stage registered: {stage.stage_id} ({stage.agent_role}) "
            f"— {stage.description[:50]}"
        )

    def kickoff(
        self,
        symbol: str,
        cycle_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        process: Optional[PipelineProcess] = None,
    ) -> PipelineOutput:
        """
        Executa o pipeline completo.

        Args:
            symbol:   Símbolo do ativo
            cycle_id: ID do ciclo
            inputs:   Dados de entrada (equity_usd, regime, etc.)
            process:  Modo de execução (override do default)

        Returns:
            PipelineOutput com resultados por stage.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        proc = process or self.default_process
        ctx = dict(inputs or {})
        ctx.update({"symbol": sym, "cycle_id": cycle_id})

        if proc == PipelineProcess.HIERARCHICAL:
            output = self._run_hierarchical(sym, cycle_id, ctx)
        else:
            output = self._run_sequential(sym, cycle_id, ctx)

        self._outputs.append(output)
        if len(self._outputs) > self.max_outputs_stored:
            self._outputs = self._outputs[-self.max_outputs_stored:]
        self._total_kickoffs += 1
        if not output.success:
            self._total_failures += 1

        logger.debug(
            f"[PipelineOrch] kickoff {sym} | process={proc.value} | "
            f"success={output.success} | {len(output.completed_stages)}/{len(self._stages)} stages"
        )
        return output

    def _run_sequential(
        self,
        symbol: str,
        cycle_id: str,
        context: Dict[str, Any],
    ) -> PipelineOutput:
        """
        Execução sequencial: cada stage recebe contexto + output anterior.

        Equivalente a Process.sequential do CrewAI.
        """
        t_start = time.monotonic()
        stage_results: List[PipelineStageResult] = []
        current_context = dict(context)
        last_output: Any = None

        for stage in self._stages:
            t_stage = time.monotonic()
            try:
                output = stage.execute(current_context)
                status = PipelineStageStatus.COMPLETED
                last_output = output
                # Propaga output para próxima stage como contexto
                current_context[f"output_{stage.stage_id}"] = output
                error_msg = ""
            except Exception as exc:  # noqa: BLE001
                output = None
                error_msg = str(exc)
                if stage.required:
                    status = PipelineStageStatus.FAILED
                    logger.debug(f"[PipelineOrch] stage '{stage.stage_id}' FAILED: {exc}")
                else:
                    status = PipelineStageStatus.SKIPPED
                    logger.debug(f"[PipelineOrch] optional stage '{stage.stage_id}' skipped: {exc}")

            stage_results.append(PipelineStageResult(
                stage_id=stage.stage_id,
                agent_role=stage.agent_role,
                status=status,
                output=output,
                error_msg=error_msg,
                duration_ms=(time.monotonic() - t_stage) * 1000,
            ))

        failed = [r for r in stage_results if r.status == PipelineStageStatus.FAILED]
        success = len([r for r in stage_results if r.stage_id in
                       [s.stage_id for s in self._stages if s.required]
                       and r.status == PipelineStageStatus.FAILED]) == 0

        return PipelineOutput(
            symbol=symbol,
            cycle_id=cycle_id,
            process=PipelineProcess.SEQUENTIAL,
            stage_results=stage_results,
            final_output=last_output,
            total_duration_ms=(time.monotonic() - t_start) * 1000,
            success=success,
            error_msg="; ".join(r.error_msg for r in failed if r.error_msg),
        )

    def _run_hierarchical(
        self,
        symbol: str,
        cycle_id: str,
        context: Dict[str, Any],
    ) -> PipelineOutput:
        """
        Execução hierárquica: manager (NickFury) coordena delegação.

        No modo hierárquico, stages não-required podem ser puladas
        com base no contexto (ex: sinal HOLD → skip IronMan).
        Equivalente a Process.hierarchical do CrewAI.
        """
        t_start = time.monotonic()
        stage_results: List[PipelineStageResult] = []
        current_context = dict(context)
        last_output: Any = None

        for stage in self._stages:
            t_stage = time.monotonic()

            # Manager decision: pular stages opcionais se contexto indica
            if not stage.required:
                # Ex: se action=HOLD, pula IronMan
                action = str(current_context.get("action", "")).upper()
                if action == "HOLD" and stage.agent_role == "IRONMAN":
                    stage_results.append(PipelineStageResult(
                        stage_id=stage.stage_id,
                        agent_role=stage.agent_role,
                        status=PipelineStageStatus.SKIPPED,
                        skipped_reason="manager decision: HOLD → skip execution",
                        duration_ms=(time.monotonic() - t_stage) * 1000,
                    ))
                    continue

            try:
                output = stage.execute(current_context)
                status = PipelineStageStatus.COMPLETED
                last_output = output
                current_context[f"output_{stage.stage_id}"] = output
                # Extrai action se disponível no output (para decisão do manager)
                if isinstance(output, dict) and "action" in output:
                    current_context["action"] = output["action"]
                error_msg = ""
            except Exception as exc:  # noqa: BLE001
                output = None
                error_msg = str(exc)
                status = PipelineStageStatus.FAILED if stage.required else PipelineStageStatus.SKIPPED
                logger.debug(
                    f"[PipelineOrch:hierarchical] stage '{stage.stage_id}' "
                    f"{status.value}: {exc}"
                )

            stage_results.append(PipelineStageResult(
                stage_id=stage.stage_id,
                agent_role=stage.agent_role,
                status=status,
                output=output,
                error_msg=error_msg,
                duration_ms=(time.monotonic() - t_stage) * 1000,
            ))

        failed_required = [
            r for r in stage_results
            if r.status == PipelineStageStatus.FAILED
            and self._stage_index.get(r.stage_id, PipelineStage("", "", "", required=True)).required
        ]
        success = len(failed_required) == 0

        return PipelineOutput(
            symbol=symbol,
            cycle_id=cycle_id,
            process=PipelineProcess.HIERARCHICAL,
            stage_results=stage_results,
            final_output=last_output,
            total_duration_ms=(time.monotonic() - t_start) * 1000,
            success=success,
            error_msg="; ".join(r.error_msg for r in failed_required if r.error_msg),
        )

    def get_recent_outputs(self, symbol: Optional[str] = None, limit: int = 5) -> List[PipelineOutput]:
        """Retorna outputs recentes, opcionalmente filtrados por símbolo."""
        outputs = self._outputs
        if symbol:
            sym = symbol.upper()
            outputs = [o for o in outputs if o.symbol == sym]
        return outputs[-limit:]

    def list_stages(self) -> List[str]:
        return [s.stage_id for s in self._stages]

    def summary(self) -> dict:
        return {
            "stages": self.list_stages(),
            "default_process": self.default_process.value,
            "total_kickoffs": self._total_kickoffs,
            "total_failures": self._total_failures,
            "outputs_stored": len(self._outputs),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_orchestrator: Optional[CyclePipelineOrchestrator] = None


def get_cycle_pipeline_orchestrator() -> CyclePipelineOrchestrator:
    """Retorna o singleton global do CyclePipelineOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        try:
            from src.config.settings import settings
            proc_raw = getattr(settings, "pipeline_process", "sequential")
            try:
                proc = PipelineProcess(proc_raw.lower())
            except (ValueError, AttributeError):
                proc = PipelineProcess.SEQUENTIAL
        except Exception:  # noqa: BLE001
            proc = PipelineProcess.SEQUENTIAL
        _orchestrator = CyclePipelineOrchestrator(default_process=proc)
    return _orchestrator


def reset_cycle_pipeline_orchestrator() -> None:
    """Reseta o singleton — para testes."""
    global _orchestrator
    _orchestrator = None

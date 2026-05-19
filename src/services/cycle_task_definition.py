"""
src/services/cycle_task_definition.py
=======================================
Story 205 — CycleTaskDefinition: tarefa estruturada com expected_output e
validação, inspirada no Task do CrewAI.

Inspirado no padrão CrewAI Task (crewAIInc/crewAI, docs.crewai.com/concepts/tasks):
  "A Task is the fundamental work unit in CrewAI. Each task includes:
     description:     What needs to be done
     expected_output: What the result should look like (natural language spec)
     agent:           Which agent is responsible
     context:         List of tasks whose outputs are provided as context
     output_json:     Pydantic model for structured output
     callback:        Function called when task completes
   Tasks output is chained: task2.context=[task1] means task2 receives
   task1's output as part of its context. This enables sequential pipelines
   where each step builds on the previous."

No CrewAI:
  Task objects são criados declarativamente e passados para Crew().
  O agente executa a task, o output é validado contra expected_output_json
  (se configurado) e o resultado é propagado para tasks dependentes.
  output_file: persiste o resultado em disco.

No Mekka, o equivalente é:
  CycleTaskDefinition declara cada etapa do pipeline com:
    - description: o que deve ser feito
    - expected_output: spec do resultado esperado (JSON schema ou descrição)
    - agent_role: qual agente executa (NICKFURY, VISION, BATMAN, IRONMAN)
    - validator_fn: valida o output antes de propagar
  CycleTaskRunner executa tasks em cadeia, passando outputs como contexto.

Arquitetura
-----------
  TaskAgentRole       — enum NICKFURY / VISION / BATMAN / IRONMAN / SYSTEM
  TaskStatus          — enum PENDING / RUNNING / COMPLETED / FAILED / SKIPPED
  CycleTaskDefinition — definição declarativa de uma task
  CycleTaskResult     — resultado de uma execução de task
  CycleTaskRunner
    ├── register(task) → str (task_id)
    ├── run(task_id, context, executor_fn) → CycleTaskResult
    ├── run_chain(task_ids, context, executors) → List[CycleTaskResult]
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# TaskAgentRole
# ---------------------------------------------------------------------------

class TaskAgentRole(str, Enum):
    """
    Papel do agente responsável por executar a task.

    Mapeamento com CrewAI Agent:
      NICKFURY ←→ manager / orchestrator
      VISION   ←→ LLM analyst (researcher)
      BATMAN   ←→ risk expert (validator)
      IRONMAN  ←→ executor (code runner)
      SYSTEM   ←→ tool/service call
    """
    NICKFURY = "NICKFURY"
    VISION = "VISION"
    BATMAN = "BATMAN"
    IRONMAN = "IRONMAN"
    SYSTEM = "SYSTEM"


# ---------------------------------------------------------------------------
# TaskStatus
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# CycleTaskDefinition — declaração da task
# ---------------------------------------------------------------------------

@dataclass
class CycleTaskDefinition:
    """
    Definição declarativa de uma task do pipeline.

    Equivalente ao Task do CrewAI:
    description + expected_output + agent + context tasks.
    """
    task_id: str
    description: str
    expected_output: str                   # spec do resultado esperado
    agent_role: TaskAgentRole
    context_task_ids: List[str] = field(default_factory=list)  # tasks que fornecem contexto
    validator_fn: Optional[Callable[[Any], bool]] = None        # valida o output
    timeout_s: float = 30.0
    async_execution: bool = False

    def validate_output(self, output: Any) -> bool:
        """Valida o output contra o validator_fn ou aceita tudo."""
        if self.validator_fn is not None:
            try:
                return bool(self.validator_fn(output))
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[TaskDef:{self.task_id}] validator error: {exc}")
                return False
        return True


# ---------------------------------------------------------------------------
# CycleTaskResult — resultado de uma execução
# ---------------------------------------------------------------------------

@dataclass
class CycleTaskResult:
    """
    Resultado de uma execução de task.

    Equivalente ao TaskOutput do CrewAI:
    raw_output + pydantic_output + status + agent.
    """
    task_id: str
    agent_role: TaskAgentRole
    status: TaskStatus
    raw_output: Any = None
    error_msg: str = ""
    validation_passed: bool = True
    context_used: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def is_successful(self) -> bool:
        return self.status == TaskStatus.COMPLETED and self.validation_passed

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_role": self.agent_role.value,
            "status": self.status.value,
            "validation_passed": self.validation_passed,
            "error_msg": self.error_msg,
            "duration_ms": self.duration_ms,
            "is_successful": self.is_successful,
        }


# ---------------------------------------------------------------------------
# CycleTaskRunner
# ---------------------------------------------------------------------------

class CycleTaskRunner:
    """
    Executa tasks declarativas em sequência, passando outputs como contexto.

    Padrão CrewAI Task + Process.sequential:
    - Registra tasks com IDs únicos
    - run(task_id, context, executor_fn): executa uma task e valida o output
    - run_chain(task_ids, context, executors): pipeline sequencial
    - Contexto encadeado: output de task N alimenta contexto de task N+1
    - Fail-silent: falha em uma task não trava as demais

    Uso:
        runner = get_cycle_task_runner()
        analysis_task = CycleTaskDefinition(
            task_id="analysis",
            description="Analisar dados de mercado do BTC",
            expected_output="Dict com price_change, volume_spike, regime",
            agent_role=TaskAgentRole.NICKFURY,
        )
        runner.register(analysis_task)
        result = runner.run("analysis", context={...}, executor_fn=run_analysis)
    """

    def __init__(self, max_results_per_task: int = 50) -> None:
        self.max_results_per_task = max_results_per_task
        self._tasks: Dict[str, CycleTaskDefinition] = {}
        self._results: Dict[str, List[CycleTaskResult]] = {}
        self._total_executed: int = 0
        self._total_failed: int = 0

    def register(self, task: CycleTaskDefinition) -> str:
        """Registra uma task. Retorna o task_id."""
        self._tasks[task.task_id] = task
        logger.debug(
            f"[TaskRunner] registered: {task.task_id} ({task.agent_role.value}) "
            f"— {task.description[:60]}"
        )
        return task.task_id

    def get_task(self, task_id: str) -> Optional[CycleTaskDefinition]:
        return self._tasks.get(task_id)

    def run(
        self,
        task_id: str,
        context: Optional[Dict[str, Any]] = None,
        executor_fn: Optional[Callable[[CycleTaskDefinition, Dict[str, Any]], Any]] = None,
        previous_results: Optional[Dict[str, CycleTaskResult]] = None,
    ) -> CycleTaskResult:
        """
        Executa uma task com o contexto fornecido.

        Args:
            task_id:          ID da task a executar
            context:          Contexto base (symbol, cycle_id, etc.)
            executor_fn:      Função que executa a task (task_def, ctx) → output
            previous_results: Resultados de tasks anteriores (para contexto encadeado)

        Returns:
            CycleTaskResult com output e status.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return CycleTaskResult(
                task_id=task_id,
                agent_role=TaskAgentRole.SYSTEM,
                status=TaskStatus.FAILED,
                error_msg=f"Task '{task_id}' not registered",
            )

        t_start = time.monotonic()
        ctx = dict(context or {})

        # Injeta contexto das tasks dependentes
        context_used: List[str] = []
        if previous_results:
            for dep_id in task.context_task_ids:
                if dep_id in previous_results and previous_results[dep_id].is_successful:
                    ctx[f"context_{dep_id}"] = previous_results[dep_id].raw_output
                    context_used.append(dep_id)

        try:
            if executor_fn is not None:
                raw_output = executor_fn(task, ctx)
            else:
                # Default: retorna contexto como output (passthrough)
                raw_output = ctx

            validation_passed = task.validate_output(raw_output)
            status = TaskStatus.COMPLETED if validation_passed else TaskStatus.FAILED
            error_msg = "" if validation_passed else "output validation failed"

        except Exception as exc:  # noqa: BLE001
            raw_output = None
            validation_passed = False
            status = TaskStatus.FAILED
            error_msg = str(exc)
            logger.debug(f"[TaskRunner] task '{task_id}' failed: {exc}")

        result = CycleTaskResult(
            task_id=task_id,
            agent_role=task.agent_role,
            status=status,
            raw_output=raw_output,
            error_msg=error_msg,
            validation_passed=validation_passed,
            context_used=context_used,
            duration_ms=(time.monotonic() - t_start) * 1000,
        )

        # Armazena resultado
        if task_id not in self._results:
            self._results[task_id] = []
        self._results[task_id].append(result)
        if len(self._results[task_id]) > self.max_results_per_task:
            self._results[task_id] = self._results[task_id][-self.max_results_per_task:]

        self._total_executed += 1
        if not result.is_successful:
            self._total_failed += 1

        logger.debug(
            f"[TaskRunner] {task_id} → {status.value} "
            f"({result.duration_ms:.1f}ms, valid={validation_passed})"
        )
        return result

    def run_chain(
        self,
        task_ids: List[str],
        context: Optional[Dict[str, Any]] = None,
        executors: Optional[Dict[str, Callable]] = None,
    ) -> List[CycleTaskResult]:
        """
        Executa uma cadeia de tasks em sequência.

        Output de cada task alimenta o contexto das seguintes.
        Fail-silent: task com falha não interrompe a chain.

        Args:
            task_ids:  Ordem de execução das tasks
            context:   Contexto base
            executors: Dict task_id → executor_fn

        Returns:
            Lista de CycleTaskResult, um por task.
        """
        results: Dict[str, CycleTaskResult] = {}
        chain_results: List[CycleTaskResult] = []
        execs = executors or {}

        for task_id in task_ids:
            result = self.run(
                task_id=task_id,
                context=context,
                executor_fn=execs.get(task_id),
                previous_results=results,
            )
            results[task_id] = result
            chain_results.append(result)

        return chain_results

    def get_results(self, task_id: str, limit: int = 10) -> List[CycleTaskResult]:
        """Retorna resultados históricos de uma task."""
        return self._results.get(task_id, [])[-limit:]

    def list_registered(self) -> List[str]:
        return list(self._tasks.keys())

    def summary(self) -> dict:
        return {
            "registered_tasks": len(self._tasks),
            "total_executed": self._total_executed,
            "total_failed": self._total_failed,
            "task_ids": self.list_registered(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_runner: Optional[CycleTaskRunner] = None


def get_cycle_task_runner() -> CycleTaskRunner:
    """Retorna o singleton global do CycleTaskRunner."""
    global _runner
    if _runner is None:
        _runner = CycleTaskRunner()
    return _runner


def reset_cycle_task_runner() -> None:
    """Reseta o singleton — para testes."""
    global _runner
    _runner = None

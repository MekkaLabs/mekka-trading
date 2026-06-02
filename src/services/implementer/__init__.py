"""
src/services/implementer/
==========================
Implementer Squad — agentes que IMPLEMENTAM melhorias aceitas pelo operador.

Fluxo geral:

  1. Worker periódico (``worker.py``) lê fila ``improvement_queue.json``
  2. ``Router`` escolhe o agente vertical (backend/frontend/dashboard/agents)
  3. O agente escolhe a CAMADA:
       - DeterministicImplementer (mecânico, $0)
       - LLMImplementer (Claude Sonnet, ~$0.10-2/IMP)
       - RecipeImplementer (fallback — escreve recipe pro humano)
  4. Tudo acontece em branch ``imp/IMP-xxxxxx`` (worktree-safe)
  5. Após sucesso → atualiza ``dev_state`` queued → in_dev → pr_open
  6. Bridge dispara write-back automático no vault (nota de review)

Safety:
  - ``safety.PROTECTED_PATHS`` bloqueia settings.py, batman.py, iron_man.py,
    .env, .env.example
  - ``safety.MAX_FILES_PER_IMP = 5``, ``MAX_LINES_PER_IMP = 500``
  - ``cost.DailyCostCap`` impede runaway de gastos LLM
  - Sempre branch local — NUNCA push (delegado a @devops)
"""

from .base import ImplementerResult, ImplementerStatus
from .router import route_implementer

__all__ = ["ImplementerResult", "ImplementerStatus", "route_implementer"]

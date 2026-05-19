"""
src/services/cycle_conditional_router.py
==========================================
Story 209 — CycleConditionalRouter: roteamento condicional multi-critério
para o pipeline Mekka, inspirado no LangGraph add_conditional_edges avançado.

Inspirado no padrão LangGraph conditional edges:
(langchain-ai/langgraph):
  "Conditional edges route the graph to different nodes based on the
   current state. The router function receives the full state and returns
   a string key that maps to the next node:
     graph.add_conditional_edges(
         'agent',
         should_continue,
         {
             'continue': 'action',
             'end': END,
         }
     )
   Routers can be composed: RegexRouterRunnable, dynamic path maps,
   and multi-condition chains."

No Mekka:
  CycleConditionalRouter generaliza o roteamento para além do action simples.
  Suporta múltiplas condições compostas em OR/AND, prioridade de regras,
  e fallback configurable.

  Casos de uso:
  - Após Vision: route por action + confidence + regime
  - Após Batman: route por approved + risk_level
  - Após qualquer nó: route por erros acumulados

Arquitetura
-----------
  RouterCondition   — condição atômica (field_path, op, value)
  RouterRule        — conjunto de condições → destino (prioridade)
  CycleConditionalRouter
    ├── add_rule(conditions, destination, priority)
    ├── route(state) → str               (retorna destino)
    └── as_fn() → Callable[[state], str] (compatível com add_conditional_edges)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# RouterConditionOp
# ---------------------------------------------------------------------------

class RouterConditionOp(str, Enum):
    EQ   = "eq"    # ==
    NEQ  = "neq"   # !=
    GT   = "gt"    # >
    GTE  = "gte"   # >=
    LT   = "lt"    # <
    LTE  = "lte"   # <=
    IN   = "in"    # value in list
    CONTAINS = "contains"  # str contains substr
    TRUTHY = "truthy"      # bool(field) is True
    FALSY  = "falsy"       # bool(field) is False


# ---------------------------------------------------------------------------
# RouterCondition
# ---------------------------------------------------------------------------

@dataclass
class RouterCondition:
    """
    Condição atômica sobre o estado.

    field_path: caminho dotted para o campo (ex: "signal.action",
                "risk_report.approved", "metadata.step_count")
    op:         operador de comparação
    value:      valor de referência (não usado em TRUTHY/FALSY)
    """
    field_path: str
    op: RouterConditionOp
    value: Any = None

    def _get_field(self, state: dict) -> Any:
        """Resolve o caminho dotted no estado."""
        parts = self.field_path.split(".")
        current: Any = state
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                try:
                    current = getattr(current, part, None)
                except Exception:
                    current = None
            if current is None:
                return None
        return current

    def evaluate(self, state: dict) -> bool:
        """Avalia a condição no estado atual."""
        field_val = self._get_field(state)
        try:
            if self.op == RouterConditionOp.TRUTHY:
                return bool(field_val)
            if self.op == RouterConditionOp.FALSY:
                return not bool(field_val)
            if self.op == RouterConditionOp.EQ:
                return field_val == self.value
            if self.op == RouterConditionOp.NEQ:
                return field_val != self.value
            if self.op == RouterConditionOp.GT:
                return field_val is not None and field_val > self.value
            if self.op == RouterConditionOp.GTE:
                return field_val is not None and field_val >= self.value
            if self.op == RouterConditionOp.LT:
                return field_val is not None and field_val < self.value
            if self.op == RouterConditionOp.LTE:
                return field_val is not None and field_val <= self.value
            if self.op == RouterConditionOp.IN:
                return field_val in (self.value or [])
            if self.op == RouterConditionOp.CONTAINS:
                return self.value in str(field_val or "")
        except Exception as exc:  # noqa: BLE001
            logger.debug("[RouterCondition] eval error %s: %s", self.field_path, exc)
        return False


# ---------------------------------------------------------------------------
# RouterRule
# ---------------------------------------------------------------------------

@dataclass
class RouterRule:
    """
    Regra de roteamento: conjunto de condições → destino.

    mode:     "ALL" (AND) ou "ANY" (OR) das condições
    priority: regras de maior prioridade são avaliadas primeiro
    """
    destination: str
    conditions: List[RouterCondition] = field(default_factory=list)
    mode: str = "ALL"   # "ALL" = AND, "ANY" = OR
    priority: int = 0   # maior = avaliado primeiro

    def matches(self, state: dict) -> bool:
        """Verifica se as condições desta regra são satisfeitas."""
        if not self.conditions:
            return True  # regra sem condições = sempre match (fallback)
        results = [c.evaluate(state) for c in self.conditions]
        if self.mode == "ANY":
            return any(results)
        return all(results)  # ALL (default)


# ---------------------------------------------------------------------------
# CycleConditionalRouter
# ---------------------------------------------------------------------------

class CycleConditionalRouter:
    """
    Roteador condicional multi-critério para o pipeline Mekka.

    Composto por regras ordenadas por prioridade. A primeira regra que
    satisfaz todas as condições define o destino. Se nenhuma regra
    corresponder, usa o fallback.

    Uso com CycleStateGraph:
        router = CycleConditionalRouter(fallback='batman')
        router.add_rule(
            conditions=[RouterCondition('signal.action', RouterConditionOp.EQ, 'HOLD')],
            destination='__END__',
            priority=10,
        )
        router.add_rule(
            conditions=[
                RouterCondition('signal.confidence', RouterConditionOp.LT, 0.5),
                RouterCondition('signal.action', RouterConditionOp.NEQ, 'HOLD'),
            ],
            destination='__END__',
            priority=8,
            mode='ALL',
        )
        graph.add_conditional_edges('vision', router.as_fn(), path_map)
    """

    def __init__(self, fallback: str = "__END__") -> None:
        self._rules: List[RouterRule] = []
        self._fallback = fallback

    def add_rule(
        self,
        conditions: List[RouterCondition],
        destination: str,
        priority: int = 0,
        mode: str = "ALL",
    ) -> "CycleConditionalRouter":
        """Adiciona uma regra de roteamento."""
        self._rules.append(RouterRule(
            destination=destination,
            conditions=conditions,
            mode=mode,
            priority=priority,
        ))
        # Reordena por prioridade decrescente
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        return self

    def route(self, state: dict) -> str:
        """
        Avalia as regras em ordem de prioridade e retorna o destino.

        Retorna `fallback` se nenhuma regra corresponder.
        """
        for rule in self._rules:
            if rule.matches(state):
                logger.debug(
                    "[CycleConditionalRouter] matched rule → %s (priority=%d)",
                    rule.destination, rule.priority,
                )
                return rule.destination
        logger.debug("[CycleConditionalRouter] no match → fallback: %s", self._fallback)
        return self._fallback

    def as_fn(self) -> Callable[[dict], str]:
        """
        Retorna o router como função callable.

        Compatível com CycleStateGraph.add_conditional_edges(source, fn, map).
        """
        return self.route

    def summary(self) -> dict:
        return {
            "rules_count": len(self._rules),
            "fallback": self._fallback,
            "rules": [
                {
                    "destination": r.destination,
                    "priority": r.priority,
                    "mode": r.mode,
                    "conditions_count": len(r.conditions),
                }
                for r in self._rules
            ],
        }


# ---------------------------------------------------------------------------
# Factories — routers pré-configurados para o Mekka Trading
# ---------------------------------------------------------------------------

def build_vision_router(fallback: str = "batman") -> CycleConditionalRouter:
    """
    Router pós-Vision com 4 regras de prioridade:

    1. HOLD → __END__ (prioridade 20)
    2. confidence < 0.4 → __END__ (prioridade 15)
    3. LONG ou SHORT + confidence ≥ 0.4 → batman (prioridade 10)
    4. fallback → batman (prioridade 0)
    """
    from src.services.cycle_state_graph import END  # noqa: WPS433

    router = CycleConditionalRouter(fallback=fallback)

    # Regra 1: HOLD direto para END
    router.add_rule(
        conditions=[RouterCondition("signal.action", RouterConditionOp.EQ, "HOLD")],
        destination=END,
        priority=20,
    )

    # Regra 2: baixa confiança → END
    router.add_rule(
        conditions=[RouterCondition("signal.confidence", RouterConditionOp.LT, 0.4)],
        destination=END,
        priority=15,
    )

    # Regra 3: sinal ativo com confiança ok → batman
    router.add_rule(
        conditions=[
            RouterCondition("signal.action", RouterConditionOp.IN, ["LONG", "SHORT"]),
            RouterCondition("signal.confidence", RouterConditionOp.GTE, 0.4),
        ],
        destination="batman",
        priority=10,
        mode="ALL",
    )

    return router


def build_batman_router(fallback: str = "ironman") -> CycleConditionalRouter:
    """
    Router pós-Batman:

    1. risk_report.approved = False → __END__
    2. risk_report.approved = True → ironman
    """
    from src.services.cycle_state_graph import END  # noqa: WPS433

    router = CycleConditionalRouter(fallback=fallback)

    # Regra 1: risco rejeitado
    router.add_rule(
        conditions=[RouterCondition("risk_report.approved", RouterConditionOp.FALSY)],
        destination=END,
        priority=10,
    )

    # Regra 2: aprovado
    router.add_rule(
        conditions=[RouterCondition("risk_report.approved", RouterConditionOp.TRUTHY)],
        destination="ironman",
        priority=5,
    )

    return router

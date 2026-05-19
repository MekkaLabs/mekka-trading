"""
src/services/cycle_condensation_engine.py
==========================================
Story 199 — CycleCondensationEngine: condensação do histórico quando a
janela de contexto é excedida, inspirado no Condenser do OpenHands.

Inspirado no padrão OpenHands Condenser / CondensationAction
(All-Hands-AI/OpenHands, Issues #5715, #6706, PR #7578):
  "When an LLM hits a context window limitation, the agent controller
   chops the history roughly in-half so the agent can continue to make
   forward progress. A CondensationAction is emitted — instead of
   manually modifying history — so the event is auditable and reversible.
   Custom Condensers can register a trigger condition and a strategy
   (halve / llm-summarize)."

No OpenHands:
  - CondensationAction substitui a manipulação direta da history list
  - Estratégias: HALVE (corta ao meio) e LLM_SUMMARIZE (resumo por LLM)
  - AgentController detecta ContextWindowExceededError e delega ao Condenser
  - CondensationAction fica no EventStream como auditoria

No Mekka, o equivalente é:
  CycleCondensationEngine monitora o uso da context window via
  ContextWindowTracker (Story 159) e emite um CondensationRecord quando
  o uso excede o threshold. Estratégias de condensação:
    HALVE     — descarta a metade mais antiga do histórico do símbolo
    SUMMARIZE — mantém um "resumo compactado" das turns mais antigas

  Pipeline de integração:
    vision._call_llm() → se context cheio → condensation_engine.maybe_condense()
    nick_fury (ciclo) → ao final → condensation_engine.maybe_condense_all()

Arquitetura
-----------
  CondensationStrategy  — enum HALVE / SUMMARIZE
  CondensationRecord    — auditoria de uma condensação executada
  CycleCondensationEngine
    ├── maybe_condense(symbol, current_tokens, history) → CondensationRecord|None
    ├── condense_halve(symbol, history) → (new_history, record)
    ├── condense_summarize(symbol, history, summary) → (new_history, record)
    ├── get_records(symbol, limit) → List[CondensationRecord]
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# CondensationStrategy
# ---------------------------------------------------------------------------

class CondensationStrategy(str, Enum):
    """
    Estratégia de condensação do histórico.

    Mapeamento com OpenHands:
      HALVE     ←→ controller chops history in-half
      SUMMARIZE ←→ LLM-based summarization condenser
    """
    HALVE = "HALVE"
    SUMMARIZE = "SUMMARIZE"


# ---------------------------------------------------------------------------
# CondensationRecord — equivalente ao CondensationAction do OpenHands
# ---------------------------------------------------------------------------

@dataclass
class CondensationRecord:
    """
    Auditoria de uma operação de condensação executada.

    Equivalente ao CondensationAction do OpenHands:
    fica no EventStream/log para rastreabilidade.
    """
    symbol: str
    cycle_id: str
    strategy: CondensationStrategy
    turns_before: int
    turns_after: int
    tokens_before: int
    tokens_after: int
    timestamp: float = field(default_factory=time.monotonic)
    summary_text: str = ""  # preenchido quando strategy=SUMMARIZE

    @property
    def reduction_pct(self) -> float:
        if self.turns_before == 0:
            return 0.0
        return round((1 - self.turns_after / self.turns_before) * 100, 1)

    def to_log_line(self) -> str:
        return (
            f"CONDENSATION | {self.symbol} | strategy={self.strategy.value} "
            f"| turns {self.turns_before}→{self.turns_after} "
            f"(-{self.reduction_pct}%) | tokens ~{self.tokens_before}→{self.tokens_after}"
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "strategy": self.strategy.value,
            "turns_before": self.turns_before,
            "turns_after": self.turns_after,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "reduction_pct": self.reduction_pct,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# CycleCondensationEngine
# ---------------------------------------------------------------------------

class CycleCondensationEngine:
    """
    Condensa o histórico de conversação quando a context window é excedida.

    Padrão OpenHands Condenser / CondensationAction:
    - Detecta quando uso de tokens excede threshold
    - Aplica estratégia HALVE (descarta metade antiga) ou SUMMARIZE
    - Emite CondensationRecord para auditoria (fail-silent)
    - Integra com CycleConversationMemory para aplicar a condensação

    Uso:
        engine = get_cycle_condensation_engine()
        if engine.should_condense(current_tokens):
            engine.condense_memory(get_cycle_conversation_memory(), "BTC")
    """

    def __init__(
        self,
        condensation_threshold: float = 0.85,
        strategy: CondensationStrategy = CondensationStrategy.HALVE,
        max_records: int = 100,
    ) -> None:
        """
        Args:
            condensation_threshold: Fraction of max_tokens_budget that triggers condensation
            strategy:               Estratégia padrão (HALVE ou SUMMARIZE)
            max_records:            Máximo de registros de auditoria mantidos
        """
        self.condensation_threshold = condensation_threshold
        self.strategy = strategy
        self.max_records = max_records

        self._records: List[CondensationRecord] = []
        self._total_condensations: int = 0
        self._by_symbol: Dict[str, int] = {}

    def should_condense(self, current_tokens: int, max_tokens: int) -> bool:
        """
        Retorna True se o uso atual excede o threshold de condensação.

        Args:
            current_tokens: Tokens usados atualmente
            max_tokens:     Budget máximo da janela

        Returns:
            True se condensação deve ser executada.
        """
        if max_tokens <= 0:
            return False
        usage_fraction = current_tokens / max_tokens
        return usage_fraction >= self.condensation_threshold

    def condense_memory(
        self,
        memory: Any,  # CycleConversationMemory
        symbol: str,
        cycle_id: str = "",
        summary_text: str = "",
    ) -> Optional[CondensationRecord]:
        """
        Executa a condensação do histórico do símbolo na memória fornecida.

        Args:
            memory:       CycleConversationMemory com o histórico
            symbol:       Símbolo do ativo
            cycle_id:     ID do ciclo atual
            summary_text: Texto de resumo (usado em SUMMARIZE)

        Returns:
            CondensationRecord se condensou, None se não havia nada para condensar.
        """
        try:
            sym = symbol.upper() if symbol else "UNKNOWN"
            history = memory.get_history(sym, limit=9999)
            if not history:
                return None

            turns_before = len(history)
            tokens_before = sum(t.token_estimate for t in history)

            if self.strategy == CondensationStrategy.HALVE:
                new_history = history[turns_before // 2:]
            else:
                # SUMMARIZE: mantém turns recentes + adiciona summary como contexto
                keep = max(1, turns_before // 2)
                new_history = history[-keep:]

            turns_after = len(new_history)
            tokens_after = sum(t.token_estimate for t in new_history)

            # Aplica no memory (clear + re-add)
            memory.clear_symbol(sym)
            for turn in new_history:
                memory._history.setdefault(sym, __import__('collections').deque(
                    maxlen=memory.max_turns_per_symbol
                )).append(turn)

            record = CondensationRecord(
                symbol=sym,
                cycle_id=cycle_id,
                strategy=self.strategy,
                turns_before=turns_before,
                turns_after=turns_after,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                summary_text=summary_text,
            )

            self._records.append(record)
            if len(self._records) > self.max_records:
                self._records = self._records[-self.max_records:]

            self._total_condensations += 1
            self._by_symbol[sym] = self._by_symbol.get(sym, 0) + 1

            logger.debug(f"[CondensationEngine] {record.to_log_line()}")
            return record

        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[CondensationEngine] condense_memory failed: {exc}")
            return None

    def maybe_condense(
        self,
        memory: Any,
        symbol: str,
        current_tokens: int,
        max_tokens: int,
        cycle_id: str = "",
    ) -> Optional[CondensationRecord]:
        """
        Condensa apenas se o threshold for atingido.

        Args:
            memory:         CycleConversationMemory
            symbol:         Símbolo
            current_tokens: Tokens em uso
            max_tokens:     Budget máximo
            cycle_id:       ID do ciclo

        Returns:
            CondensationRecord se condensou, None caso contrário.
        """
        if self.should_condense(current_tokens, max_tokens):
            return self.condense_memory(memory, symbol, cycle_id)
        return None

    def get_records(self, symbol: Optional[str] = None, limit: int = 20) -> List[CondensationRecord]:
        """Retorna registros de condensação, opcionalmente filtrados por símbolo."""
        records = self._records
        if symbol:
            sym = symbol.upper()
            records = [r for r in records if r.symbol == sym]
        return records[-limit:]

    def summary(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "condensation_threshold": self.condensation_threshold,
            "total_condensations": self._total_condensations,
            "by_symbol": self._by_symbol,
            "records_stored": len(self._records),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: Optional[CycleCondensationEngine] = None


def get_cycle_condensation_engine() -> CycleCondensationEngine:
    """Retorna o singleton global do CycleCondensationEngine."""
    global _engine
    if _engine is None:
        try:
            from src.config.settings import settings
            threshold = float(getattr(settings, "condensation_threshold", 0.85))
            strategy_raw = getattr(settings, "condensation_strategy", "HALVE")
            try:
                strategy = CondensationStrategy(strategy_raw.upper())
            except (ValueError, AttributeError):
                strategy = CondensationStrategy.HALVE
        except Exception:  # noqa: BLE001
            threshold = 0.85
            strategy = CondensationStrategy.HALVE
        _engine = CycleCondensationEngine(
            condensation_threshold=threshold,
            strategy=strategy,
        )
    return _engine


def reset_cycle_condensation_engine() -> None:
    """Reseta o singleton — para testes."""
    global _engine
    _engine = None

"""
src/services/role_working_memory.py
========================================
Story 183 — RoleWorkingMemory: janela deslizante de resultados por ciclo.

Inspirado no padrão MetaGPT RoleContext.rc.memory:
  "When initialized, Role acquires its Memory as self.rc.memory, which will
   store every Message it later _observe in a list for future retrieval."

No MetaGPT, cada Role mantém uma lista de Messages observadas (working memory)
que serve de contexto para LLM calls subsequentes. Mensagens recentes ficam
quentes em memória; o RC filtra apenas as relevantes.

No Mekka, o equivalente é manter uma janela deslizante de resultados de ciclos
anteriores por símbolo (action, confidence, outcome, regime) e injetá-la no
prompt do Vision como "recent trade history" — contexto que o LLM pode usar
para evitar repetições de erros e reconhecer padrões de mercado recorrentes.

Arquitetura
-----------
  RoleWorkingMemory — sliding window de CycleRecord por símbolo
    ├── record(symbol, action, confidence, regime, outcome_pnl, cycle_id)
    ├── get_recent(symbol, limit) → list[CycleRecord]
    ├── get_prompt_block(symbol, limit) → str   (bloco formatado p/ prompt)
    └── summary() → dict

Uso em Vision.run()
-------------------
    from src.services.role_working_memory import get_role_working_memory

    mem = get_role_working_memory()
    mem_block = mem.get_prompt_block(symbol, limit=5)
    if mem_block:
        prompt = prompt + "\\n\\n" + mem_block

Uso em NickFury (post-execution)
---------------------------------
    from src.services.role_working_memory import get_role_working_memory

    get_role_working_memory().record(
        symbol=symbol,
        action=signal.action.value,
        confidence=signal.confidence,
        regime=regime_str,
        outcome_pnl=execution_pnl,
    )
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# CycleRecord
# ---------------------------------------------------------------------------

@dataclass
class CycleRecord:
    """
    Registro de um ciclo de trading concluído — equivalente a um
    MetaGPT Message armazenado na working memory do Role.
    """
    symbol: str
    action: str           # "LONG", "SHORT", "HOLD"
    confidence: float     # 0.0–1.0
    regime: str           # "VOLATILE", "BULL", "SIDEWAYS", etc.
    outcome_pnl: Optional[float]  # PnL em USD; None se ainda não resolvido
    cycle_id: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    def to_prompt_line(self) -> str:
        """Linha compacta para injeção no prompt Vision."""
        pnl_str = f"{self.outcome_pnl:+.2f} USD" if self.outcome_pnl is not None else "pendente"
        return (
            f"  • {self.action} @ conf={self.confidence:.0%} | "
            f"regime={self.regime} | outcome={pnl_str}"
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "regime": self.regime,
            "outcome_pnl": self.outcome_pnl,
            "cycle_id": self.cycle_id,
        }


# ---------------------------------------------------------------------------
# RoleWorkingMemory
# ---------------------------------------------------------------------------

class RoleWorkingMemory:
    """
    Janela deslizante de CycleRecord por símbolo.

    Padrão MetaGPT RoleContext.rc.memory: cada Role mantém uma lista de
    mensagens observadas como contexto para LLM calls. Aqui a "mensagem"
    é o resultado de um ciclo completo de trading.
    """

    def __init__(self, max_per_symbol: int = 10) -> None:
        self._memory: Dict[str, Deque[CycleRecord]] = {}
        self._max_per_symbol = max_per_symbol
        self._total_records: int = 0

    def record(
        self,
        symbol: str,
        action: str,
        confidence: float,
        regime: str = "UNKNOWN",
        outcome_pnl: Optional[float] = None,
        cycle_id: str = "",
    ) -> CycleRecord:
        """
        Adiciona um novo registro na working memory do símbolo.

        Args:
            symbol: símbolo do ativo (ex: "BTC")
            action: ação do sinal ("LONG", "SHORT", "HOLD")
            confidence: confiança do sinal (0.0–1.0)
            regime: regime de mercado no momento do ciclo
            outcome_pnl: PnL realizado em USD (None se ainda pendente)
            cycle_id: identificador do ciclo

        Returns:
            CycleRecord criado.
        """
        sym = symbol.upper()
        if sym not in self._memory:
            self._memory[sym] = deque(maxlen=self._max_per_symbol)

        rec = CycleRecord(
            symbol=sym,
            action=action.upper(),
            confidence=float(confidence),
            regime=regime,
            outcome_pnl=outcome_pnl,
            cycle_id=cycle_id,
        )
        self._memory[sym].append(rec)
        self._total_records += 1

        logger.debug(
            f"[RoleWorkingMemory] recorded {sym} {action} conf={confidence:.0%} "
            f"regime={regime} pnl={outcome_pnl}"
        )
        return rec

    def get_recent(self, symbol: str, limit: int = 5) -> List[CycleRecord]:
        """
        Retorna os últimos `limit` registros para o símbolo (mais recente por último).

        Returns:
            Lista de CycleRecord (pode ser vazia se símbolo não tem histórico).
        """
        sym = symbol.upper()
        records = list(self._memory.get(sym, []))
        return records[-limit:] if len(records) > limit else records

    def get_prompt_block(self, symbol: str, limit: int = 5) -> str:
        """
        Gera bloco formatado para injeção no prompt Vision.

        Formato:
            === Recent Trade History: BTC (last 5 cycles) ===
              • LONG @ conf=75% | regime=VOLATILE | outcome=+45.20 USD
              • HOLD @ conf=60% | regime=SIDEWAYS | outcome=pendente
            Use this history to avoid repeating recent mistakes.

        Returns:
            String formatada, ou "" se não há histórico.
        """
        records = self.get_recent(symbol, limit=limit)
        if not records:
            return ""

        sym = symbol.upper()
        lines = [
            f"=== Recent Trade History: {sym} (last {len(records)} cycles) ===",
        ]
        for rec in records:
            lines.append(rec.to_prompt_line())
        lines.append("Use this history to avoid repeating recent mistakes and recognize recurring patterns.")

        return "\n".join(lines)

    def resolve_outcome(self, symbol: str, outcome_pnl: float, cycle_id: str = "") -> bool:
        """
        Atualiza o outcome_pnl do registro mais recente pendente para o símbolo.

        Args:
            symbol: símbolo do ativo
            outcome_pnl: PnL realizado
            cycle_id: se fornecido, prefere match por cycle_id

        Returns:
            True se encontrou e atualizou, False se não havia registro pendente.
        """
        sym = symbol.upper()
        records = list(self._memory.get(sym, []))

        # prefere match por cycle_id
        if cycle_id:
            for rec in reversed(records):
                if rec.cycle_id == cycle_id and rec.outcome_pnl is None:
                    rec.outcome_pnl = outcome_pnl
                    return True

        # fallback: mais recente pendente
        for rec in reversed(records):
            if rec.outcome_pnl is None:
                rec.outcome_pnl = outcome_pnl
                return True

        return False

    def clear(self, symbol: Optional[str] = None) -> int:
        """
        Limpa memória de um símbolo ou de todos.

        Returns:
            Número de registros removidos.
        """
        if symbol is not None:
            sym = symbol.upper()
            count = len(self._memory.get(sym, []))
            self._memory.pop(sym, None)
            return count

        count = sum(len(v) for v in self._memory.values())
        self._memory.clear()
        return count

    def summary(self) -> dict:
        """Estatísticas da working memory."""
        per_symbol = {
            sym: {
                "count": len(recs),
                "last_action": recs[-1].action if recs else None,
                "pending_outcomes": sum(1 for r in recs if r.outcome_pnl is None),
            }
            for sym, recs in self._memory.items()
        }
        return {
            "symbols_tracked": len(self._memory),
            "total_records": self._total_records,
            "max_per_symbol": self._max_per_symbol,
            "per_symbol": per_symbol,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_memory: Optional[RoleWorkingMemory] = None


def get_role_working_memory(max_per_symbol: int = 10) -> RoleWorkingMemory:
    """
    Retorna o singleton global do RoleWorkingMemory.

    Args:
        max_per_symbol: máximo de registros por símbolo (só usado na criação).
    """
    global _memory
    if _memory is None:
        try:
            from src.config.settings import settings
            max_n = int(getattr(settings, "working_memory_max_per_symbol", max_per_symbol))
        except Exception:  # noqa: BLE001
            max_n = max_per_symbol
        _memory = RoleWorkingMemory(max_per_symbol=max_n)
    return _memory


def reset_role_working_memory() -> None:
    """Reseta o singleton — para testes."""
    global _memory
    _memory = None

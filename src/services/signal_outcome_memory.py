"""
src/services/signal_outcome_memory.py
========================================
Story 186 — SignalOutcomeMemory: memória de longo prazo com recuperação por similaridade.

Inspirado no padrão MetaGPT LongTermMemory:
  "MetaGPT's memory system includes Long-term Memory (persistent storage
   capabilities and similarity search) and Brain Memory (summarization and
   relevance checking). recover_memory() loads existing history; add() stores
   new entries; persist() writes to disk."

No MetaGPT, LongTermMemory usa FAISS para busca semântica por embedding.
No Mekka, o equivalente lightweight é uma memória de outcomes de sinais que
usa score de similaridade baseado em regime + action (sem vetores, sem FAISS)
— leve, sem dependências externas, mas poderoso o suficiente para recuperar
"o que aconteceu quando tínhamos um sinal LONG em regime VOLATILE antes?"

Vision recebe os top-N resultados similares como contexto de "past performance"
para calibrar confiança e evitar repetição de erros em condições similares.

Arquitetura
-----------
  OutcomeRecord — entrada da memória (symbol, regime, action, confidence, pnl, timestamp)
  SignalOutcomeMemory
    ├── record(symbol, regime, action, confidence, pnl_usd, trade_id)
    ├── find_similar(symbol, regime, action, top_n) → list[OutcomeRecord]
    ├── get_prompt_block(symbol, regime, action) → str
    ├── win_rate(symbol, action, regime) → float
    └── summary() → dict

Uso em Vision.run()
-------------------
    from src.services.signal_outcome_memory import get_signal_outcome_memory

    mem = get_signal_outcome_memory()
    past_block = mem.get_prompt_block(symbol, regime=_regime, action="LONG")
    if past_block:
        prompt = prompt + "\\n\\n" + past_block
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# OutcomeRecord
# ---------------------------------------------------------------------------

@dataclass
class OutcomeRecord:
    """
    Registro de um sinal com seu outcome realizado.
    Equivalente a um Message no LongTermMemory do MetaGPT.
    """
    symbol: str
    regime: str           # "VOLATILE", "BULL", "SIDEWAYS", etc.
    action: str           # "LONG", "SHORT", "HOLD"
    confidence: float     # 0.0–1.0
    pnl_usd: float        # PnL realizado em USD
    trade_id: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    def similarity_score(self, regime: str, action: str) -> float:
        """
        Score de similaridade [0, 1] entre este registro e uma query (regime, action).

        Lógica:
          - regime match exato:    +0.6
          - regime match parcial   +0.3  (ex: BULL vs STRONG_BULL)
          - action match exato:    +0.4

        Retorna score entre 0.0 e 1.0.
        """
        score = 0.0

        # Action match
        if self.action.upper() == action.upper():
            score += 0.4

        # Regime match
        self_reg = self.regime.upper()
        query_reg = regime.upper()
        if self_reg == query_reg:
            score += 0.6
        elif self_reg in query_reg or query_reg in self_reg:
            # ex: "BULL" ↔ "STRONG_BULL", "BEAR" ↔ "STRONG_BEAR"
            score += 0.3

        return score

    def to_prompt_line(self) -> str:
        outcome = f"{self.pnl_usd:+.2f} USD"
        return (
            f"  • {self.action} @ conf={self.confidence:.0%} | "
            f"regime={self.regime} → {outcome}"
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "regime": self.regime,
            "action": self.action,
            "confidence": self.confidence,
            "pnl_usd": self.pnl_usd,
            "trade_id": self.trade_id,
        }


# ---------------------------------------------------------------------------
# SignalOutcomeMemory
# ---------------------------------------------------------------------------

class SignalOutcomeMemory:
    """
    Memória de longo prazo de outcomes de sinais com recuperação por similaridade.

    Padrão MetaGPT LongTermMemory: armazena histórico persistente e recupera
    entradas relevantes por score de similaridade (aqui: regime + action).
    """

    def __init__(self, max_records: int = 500) -> None:
        self._records: List[OutcomeRecord] = []
        self._max_records = max_records
        self._total_stored: int = 0

    def record(
        self,
        symbol: str,
        regime: str,
        action: str,
        confidence: float,
        pnl_usd: float,
        trade_id: str = "",
    ) -> OutcomeRecord:
        """
        Armazena um novo outcome na memória.

        Args:
            symbol: símbolo do ativo
            regime: regime de mercado durante o sinal
            action: ação do sinal ("LONG", "SHORT", "HOLD")
            confidence: confiança original do sinal
            pnl_usd: PnL realizado em USD
            trade_id: ID do trade para dedup

        Returns:
            OutcomeRecord criado.
        """
        rec = OutcomeRecord(
            symbol=symbol.upper(),
            regime=regime.upper(),
            action=action.upper(),
            confidence=float(confidence),
            pnl_usd=float(pnl_usd),
            trade_id=trade_id,
        )
        self._records.append(rec)
        self._total_stored += 1

        # Rotação: descarta os mais antigos
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

        logger.debug(
            f"[SignalOutcomeMemory] stored {symbol} {action} "
            f"regime={regime} pnl={pnl_usd:+.2f}"
        )
        return rec

    def find_similar(
        self,
        symbol: str,
        regime: str,
        action: str,
        top_n: int = 3,
        min_score: float = 0.3,
    ) -> List[OutcomeRecord]:
        """
        Recupera top-N registros mais similares por (regime, action).

        Padrão MetaGPT LongTermMemory: similarity search sem FAISS —
        usa score computado localmente por características discretas.

        Args:
            symbol: limita busca ao símbolo (vazio = todos)
            regime: regime de mercado da query
            action: ação da query
            top_n: máximo de resultados
            min_score: score mínimo para inclusão

        Returns:
            Lista de OutcomeRecord ordenada por score decrescente.
        """
        sym = symbol.upper()
        candidates = [r for r in self._records if not sym or r.symbol == sym]

        scored = [
            (r, r.similarity_score(regime, action))
            for r in candidates
        ]
        scored = [(r, s) for r, s in scored if s >= min_score]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [r for r, _ in scored[:top_n]]

    def get_prompt_block(
        self,
        symbol: str,
        regime: str = "UNKNOWN",
        action: str = "LONG",
        top_n: int = 3,
    ) -> str:
        """
        Gera bloco formatado para injeção no prompt Vision.

        Formato:
            === Past Performance: BTC (similar conditions) ===
            Conditions matched: VOLATILE + LONG
              • LONG @ conf=80% | regime=VOLATILE → +120.50 USD
              • LONG @ conf=65% | regime=VOLATILE → -45.20 USD
            Win rate in similar conditions: 50.0%

        Returns:
            String formatada, ou "" se não há histórico suficiente.
        """
        similar = self.find_similar(symbol, regime, action, top_n=top_n)
        if not similar:
            return ""

        sym = symbol.upper()
        lines = [
            f"=== Past Performance: {sym} (similar conditions) ===",
            f"Conditions matched: {regime.upper()} + {action.upper()}",
        ]
        for rec in similar:
            lines.append(rec.to_prompt_line())

        # Win rate
        wins = sum(1 for r in similar if r.pnl_usd > 0)
        win_rate = wins / len(similar) * 100
        lines.append(f"Win rate in similar conditions: {win_rate:.1f}%")
        lines.append("Consider this historical performance when setting confidence.")

        return "\n".join(lines)

    def win_rate(self, symbol: str, action: str = "", regime: str = "") -> float:
        """
        Taxa de acerto para o símbolo (opcionalmente filtrado por action e regime).

        Returns:
            Float 0.0–1.0, ou 0.0 se não há registros.
        """
        sym = symbol.upper()
        recs = [r for r in self._records if r.symbol == sym]
        if action:
            recs = [r for r in recs if r.action == action.upper()]
        if regime:
            recs = [r for r in recs if r.regime == regime.upper()]

        if not recs:
            return 0.0
        return sum(1 for r in recs if r.pnl_usd > 0) / len(recs)

    def summary(self) -> dict:
        """Estatísticas da memória de outcomes."""
        if not self._records:
            return {
                "total_records": 0,
                "total_stored": self._total_stored,
                "symbols": [],
                "overall_win_rate": 0.0,
            }

        symbols = list({r.symbol for r in self._records})
        wins = sum(1 for r in self._records if r.pnl_usd > 0)
        return {
            "total_records": len(self._records),
            "total_stored": self._total_stored,
            "max_records": self._max_records,
            "symbols": symbols,
            "overall_win_rate": round(wins / len(self._records), 3),
            "avg_pnl": round(sum(r.pnl_usd for r in self._records) / len(self._records), 2),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_memory: Optional[SignalOutcomeMemory] = None


def get_signal_outcome_memory(max_records: int = 500) -> SignalOutcomeMemory:
    """
    Retorna o singleton global do SignalOutcomeMemory.

    Args:
        max_records: máximo de registros em memória (só usado na criação).
    """
    global _memory
    if _memory is None:
        try:
            from src.config.settings import settings
            max_n = int(getattr(settings, "outcome_memory_max_records", max_records))
        except Exception:  # noqa: BLE001
            max_n = max_records
        _memory = SignalOutcomeMemory(max_records=max_n)
    return _memory


def reset_signal_outcome_memory() -> None:
    """Reseta o singleton — para testes."""
    global _memory
    _memory = None

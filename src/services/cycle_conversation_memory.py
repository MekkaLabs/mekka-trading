"""
src/services/cycle_conversation_memory.py
==========================================
Story 198 — CycleConversationMemory: gerenciamento da janela de contexto
por símbolo, inspirado no ConversationMemory do OpenHands.

Inspirado no padrão OpenHands ConversationMemory
(All-Hands-AI/OpenHands, PR #7008):
  "Helper class that manages the agent's context window.
   Works with state/state.history or condensed_history and figures out
   the contents of the context window — which events fit, which are
   pruned, and how the messages list is built for each LLM call."

No OpenHands:
  ConversationMemory é inicializado com state/condensed_history e
  constrói a lista de mensagens enviada ao LLM. CodeActAgent migrou de
  chamar message_utils diretamente para usar ConversationMemory como
  helper, permitindo que lógica de janela fique centralizada e testável.

No Mekka, o equivalente é:
  CycleConversationMemory mantém um histórico por símbolo de mensagens
  relevantes para o Vision (signal+regime+outcome). Fornece
  `build_messages(n_recent)` que retorna a fatia de histórico que cabe
  na janela de contexto configurada, e `add_turn()` para registrar cada
  par user/assistant do ciclo.

  Integra com ContextWindowTracker (Story 159) para conhecer o espaço
  disponível sem repetir a lógica de contagem.

Arquitetura
-----------
  MessageTurn       — par (user_prompt, assistant_reply) de um ciclo
  CycleConversationMemory
    ├── add_turn(symbol, user_prompt, assistant_reply, cycle_id)
    ├── build_messages(symbol, n_recent) → List[dict]
    ├── get_history(symbol, limit) → List[MessageTurn]
    ├── clear_symbol(symbol)
    └── summary() → dict
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# MessageTurn — par user/assistant de um ciclo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MessageTurn:
    """
    Par de mensagens (user + assistant) de um único ciclo de análise.

    Equivalente a um par de eventos no ConversationMemory do OpenHands:
    - user_prompt: contexto enviado ao Vision (regime, price, candles, …)
    - assistant_reply: resposta estruturada do Vision (LONG/SHORT/HOLD + reasoning)
    """
    symbol: str
    cycle_id: str
    user_prompt: str
    assistant_reply: str
    timestamp: float = field(default_factory=time.monotonic)
    token_estimate: int = 0  # estimativa simples: len(prompt+reply) // 4

    @classmethod
    def create(cls, symbol: str, cycle_id: str, user_prompt: str, assistant_reply: str) -> "MessageTurn":
        """Cria um MessageTurn com estimativa de tokens."""
        tokens = (len(user_prompt) + len(assistant_reply)) // 4
        return cls(
            symbol=symbol.upper() if symbol else "",
            cycle_id=cycle_id,
            user_prompt=user_prompt,
            assistant_reply=assistant_reply,
            token_estimate=tokens,
        )

    def to_openai_messages(self) -> List[dict]:
        """Serializa para formato de mensagens OpenAI/Anthropic."""
        return [
            {"role": "user", "content": self.user_prompt},
            {"role": "assistant", "content": self.assistant_reply},
        ]


# ---------------------------------------------------------------------------
# CycleConversationMemory
# ---------------------------------------------------------------------------

class CycleConversationMemory:
    """
    Gerencia a janela de contexto de conversação por símbolo.

    Padrão OpenHands ConversationMemory:
    - Centraliza a lógica de "o que cabe na context window"
    - Mantém histórico por símbolo (deque com max_turns_per_symbol)
    - build_messages() retorna a fatia de histórico que cabe no budget
    - Agente (Vision) consome o resultado em vez de gerenciar janela direto

    Uso:
        mem = get_cycle_conversation_memory()
        mem.add_turn("BTC", cycle_id, user_prompt, assistant_reply)
        msgs = mem.build_messages("BTC", n_recent=3)
        # msgs é lista de dicts {role, content} pronta para LLM
    """

    def __init__(
        self,
        max_turns_per_symbol: int = 20,
        max_tokens_budget: int = 8000,
        default_n_recent: int = 5,
    ) -> None:
        self.max_turns_per_symbol = max_turns_per_symbol
        self.max_tokens_budget = max_tokens_budget
        self.default_n_recent = default_n_recent

        # histórico por símbolo
        self._history: Dict[str, Deque[MessageTurn]] = {}
        self._total_turns: int = 0
        self._total_tokens_estimated: int = 0

    def add_turn(
        self,
        symbol: str,
        cycle_id: str,
        user_prompt: str,
        assistant_reply: str,
    ) -> MessageTurn:
        """
        Registra um par user/assistant no histórico do símbolo.

        Args:
            symbol:          Símbolo do ativo (ex: "BTC")
            cycle_id:        ID do ciclo
            user_prompt:     Prompt enviado ao Vision
            assistant_reply: Resposta do Vision

        Returns:
            MessageTurn criado.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        if sym not in self._history:
            self._history[sym] = deque(maxlen=self.max_turns_per_symbol)

        turn = MessageTurn.create(sym, cycle_id, user_prompt, assistant_reply)
        self._history[sym].append(turn)
        self._total_turns += 1
        self._total_tokens_estimated += turn.token_estimate

        logger.debug(
            f"[ConversationMemory] {sym} — turn added "
            f"(~{turn.token_estimate} tokens, total={len(self._history[sym])})"
        )
        return turn

    def build_messages(
        self,
        symbol: str,
        n_recent: Optional[int] = None,
    ) -> List[dict]:
        """
        Constrói a lista de mensagens para o LLM, respeitando max_tokens_budget.

        Retorna os n_recent turns mais recentes que cabem no budget de tokens.
        Formato: lista de dicts {"role": "user"/"assistant", "content": "..."}

        Args:
            symbol:   Símbolo do ativo
            n_recent: Número máximo de turns (default: self.default_n_recent)

        Returns:
            Lista de mensagens OpenAI/Anthropic-compatible.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        n = n_recent if n_recent is not None else self.default_n_recent

        history = list(self._history.get(sym, []))
        recent = history[-n:] if len(history) > n else history

        # filtra por budget de tokens (do mais recente para o mais antigo)
        selected: List[MessageTurn] = []
        budget_remaining = self.max_tokens_budget
        for turn in reversed(recent):
            if turn.token_estimate <= budget_remaining:
                selected.insert(0, turn)
                budget_remaining -= turn.token_estimate
            else:
                break  # para na primeira turn que não cabe

        messages: List[dict] = []
        for turn in selected:
            messages.extend(turn.to_openai_messages())

        logger.debug(
            f"[ConversationMemory] {sym} — build_messages: "
            f"{len(selected)} turns, ~{self.max_tokens_budget - budget_remaining} tokens"
        )
        return messages

    def get_history(self, symbol: str, limit: int = 10) -> List[MessageTurn]:
        """Retorna os turns mais recentes para o símbolo."""
        sym = symbol.upper() if symbol else "UNKNOWN"
        history = list(self._history.get(sym, []))
        return history[-limit:]

    def clear_symbol(self, symbol: str) -> None:
        """Limpa o histórico de um símbolo (ex: após reset de ciclo)."""
        sym = symbol.upper() if symbol else "UNKNOWN"
        if sym in self._history:
            self._history[sym].clear()
            logger.debug(f"[ConversationMemory] {sym} — history cleared")

    def clear_all(self) -> None:
        """Limpa todo o histórico (usado em reset global)."""
        self._history.clear()
        logger.debug("[ConversationMemory] all history cleared")

    def symbols_tracked(self) -> List[str]:
        """Lista os símbolos com histórico."""
        return [sym for sym, h in self._history.items() if len(h) > 0]

    def summary(self) -> dict:
        return {
            "symbols_tracked": len(self.symbols_tracked()),
            "total_turns": self._total_turns,
            "total_tokens_estimated": self._total_tokens_estimated,
            "max_turns_per_symbol": self.max_turns_per_symbol,
            "max_tokens_budget": self.max_tokens_budget,
            "per_symbol": {
                sym: len(h) for sym, h in self._history.items()
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_memory: Optional[CycleConversationMemory] = None


def get_cycle_conversation_memory() -> CycleConversationMemory:
    """Retorna o singleton global do CycleConversationMemory."""
    global _memory
    if _memory is None:
        try:
            from src.config.settings import settings
            max_turns = int(getattr(settings, "conversation_memory_max_turns", 20))
            max_tokens = int(getattr(settings, "conversation_memory_max_tokens", 8000))
            n_recent = int(getattr(settings, "conversation_memory_n_recent", 5))
        except Exception:  # noqa: BLE001
            max_turns = 20
            max_tokens = 8000
            n_recent = 5
        _memory = CycleConversationMemory(
            max_turns_per_symbol=max_turns,
            max_tokens_budget=max_tokens,
            default_n_recent=n_recent,
        )
    return _memory


def reset_cycle_conversation_memory() -> None:
    """Reseta o singleton — para testes."""
    global _memory
    _memory = None

"""
src/services/mekka_conversation_session.py
============================================
Story 204 — MekkaConversationSession: sessão de conversa estruturada com
término automático, inspirada no ConversableAgent.initiate_chat() do AutoGen.

Inspirado no padrão AutoGen ConversableAgent.initiate_chat()
(microsoft/autogen, autogen 0.2 + stable):
  "initiate_chat(recipient, message, max_turns, summary_method,
   is_termination_msg, carryover)
   — starts a structured conversation between two (or more) agents.
   Terminates when:
     a) max_turns is reached
     b) is_termination_msg(message) returns True
     c) human_input_mode = TERMINATE
   summary_method: 'last_msg' | 'reflection_with_llm' | callable
   carryover: appends previous conversation as context for next chat"

No AutoGen:
  O agente A inicia a conversa com initiate_chat(agente_B, message="...")
  O recipient (agente B) responde, A responde a B, e assim sucessivamente.
  A conversa termina por max_turns ou is_termination_msg.
  summary_method='last_msg' retorna a última mensagem como resumo da sessão.
  carryover=[...] injeta contexto de sessões anteriores.

No Mekka, o equivalente é:
  MekkaConversationSession encapsula uma troca estruturada entre dois
  "participantes" (ex: Vision ↔ VisionCritic, ou Vision ↔ Batman).
  Suporta:
    - max_turns: limita o número de trocas
    - is_termination_msg: função de callback para término antecipado
    - summary_method: 'last_msg' ou callable
    - carryover: contexto de sessões anteriores injetado no início

  Integra com CycleConversationMemory (Story 198) para persistir histórico.

Arquitetura
-----------
  SessionRole         — enum INITIATOR / RECIPIENT
  ConversationTurn    — uma troca de mensagem + resposta
  SessionSummary      — resultado da sessão (turns, summary, termination_reason)
  MekkaConversationSession
    ├── add_turn(initiator_msg, recipient_reply) → ConversationTurn
    ├── is_terminated() → bool
    ├── get_summary() → SessionSummary
    ├── run(initiator_fn, recipient_fn, initial_msg) → SessionSummary
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# SessionRole
# ---------------------------------------------------------------------------

class SessionRole(str, Enum):
    """
    Papel de um participante na sessão.

    Mapeamento com AutoGen ConversableAgent:
      INITIATOR ←→ agente que chama initiate_chat()
      RECIPIENT ←→ agente que recebe e responde
    """
    INITIATOR = "INITIATOR"
    RECIPIENT = "RECIPIENT"


# ---------------------------------------------------------------------------
# TerminationReason
# ---------------------------------------------------------------------------

class TerminationReason(str, Enum):
    MAX_TURNS = "MAX_TURNS"
    TERMINATION_MSG = "TERMINATION_MSG"
    INITIATOR_TERMINATE = "INITIATOR_TERMINATE"
    ERROR = "ERROR"
    NOT_TERMINATED = "NOT_TERMINATED"


# ---------------------------------------------------------------------------
# ConversationTurn
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    """
    Uma troca completa: mensagem do initiator + resposta do recipient.

    Equivalente a um par de mensagens em AutoGen:
    (initiator_msg, recipient_reply) em uma sessão initiate_chat().
    """
    turn_number: int
    initiator_msg: str
    recipient_reply: str
    initiator_id: str = "A"
    recipient_id: str = "B"
    terminated_by_recipient: bool = False
    timestamp: float = field(default_factory=time.monotonic)

    def to_openai_messages(self) -> List[dict]:
        return [
            {"role": "user", "content": self.initiator_msg, "name": self.initiator_id},
            {"role": "assistant", "content": self.recipient_reply, "name": self.recipient_id},
        ]


# ---------------------------------------------------------------------------
# SessionSummary
# ---------------------------------------------------------------------------

@dataclass
class SessionSummary:
    """
    Resultado de uma sessão de conversa.

    Equivalente ao retorno de initiate_chat() no AutoGen:
    summary (str), chat_history (list), cost (dict).
    """
    initiator_id: str
    recipient_id: str
    turns: List[ConversationTurn]
    termination_reason: TerminationReason
    summary: str
    symbol: str
    cycle_id: str
    duration_ms: float = 0.0

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def last_msg(self) -> str:
        if self.turns:
            return self.turns[-1].recipient_reply
        return ""

    def to_dict(self) -> dict:
        return {
            "initiator_id": self.initiator_id,
            "recipient_id": self.recipient_id,
            "turn_count": self.turn_count,
            "termination_reason": self.termination_reason.value,
            "summary": self.summary,
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "duration_ms": self.duration_ms,
            "last_msg": self.last_msg,
        }


# ---------------------------------------------------------------------------
# MekkaConversationSession
# ---------------------------------------------------------------------------

class MekkaConversationSession:
    """
    Sessão de conversa estruturada entre dois participantes.

    Padrão AutoGen ConversableAgent.initiate_chat():
    - max_turns: limita o número de trocas
    - is_termination_msg: término antecipado quando condição é atendida
    - summary_method: 'last_msg' ou callable → produz resumo da sessão
    - carryover: contexto de sessões anteriores injetado no início
    - Fail-silent: erros em initiator_fn/recipient_fn não travam o pipeline

    Uso:
        session = MekkaConversationSession(
            initiator_id="Vision",
            recipient_id="VisionCritic",
            max_turns=3,
            is_termination_msg=lambda msg: "ENDORSE" in msg,
        )
        summary = session.run(
            initiator_fn=lambda msg, hist: vision_call(msg),
            recipient_fn=lambda msg, hist: critic_call(msg),
            initial_msg="Analyze BTC: ...",
        )
    """

    def __init__(
        self,
        initiator_id: str = "A",
        recipient_id: str = "B",
        max_turns: int = 3,
        is_termination_msg: Optional[Callable[[str], bool]] = None,
        summary_method: str = "last_msg",  # 'last_msg' ou callable
        carryover: Optional[List[str]] = None,
        max_sessions_stored: int = 20,
    ) -> None:
        self.initiator_id = initiator_id
        self.recipient_id = recipient_id
        self.max_turns = max_turns
        self.is_termination_msg = is_termination_msg
        self.summary_method = summary_method
        self.carryover = carryover or []
        self.max_sessions_stored = max_sessions_stored

        self._sessions: List[SessionSummary] = []
        self._total_sessions: int = 0
        self._total_turns: int = 0

    def run(
        self,
        initiator_fn: Callable[[str, List[ConversationTurn]], str],
        recipient_fn: Callable[[str, List[ConversationTurn]], str],
        initial_msg: str,
        symbol: str = "",
        cycle_id: str = "",
    ) -> SessionSummary:
        """
        Executa a sessão de conversa.

        Args:
            initiator_fn: Função do agente iniciador (msg, history) → resposta
            recipient_fn: Função do agente receptor (msg, history) → resposta
            initial_msg:  Primeira mensagem do initiator
            symbol:       Símbolo do ativo
            cycle_id:     ID do ciclo

        Returns:
            SessionSummary com histórico e resumo da sessão.
        """
        t_start = time.monotonic()
        sym = symbol.upper() if symbol else ""
        turns: List[ConversationTurn] = []
        termination_reason = TerminationReason.NOT_TERMINATED
        current_msg = initial_msg

        # Injeta carryover como contexto inicial
        if self.carryover:
            current_msg = "\n".join(self.carryover) + "\n\n" + current_msg

        for turn_num in range(1, self.max_turns + 1):
            # Recipient responde
            try:
                recipient_reply = recipient_fn(current_msg, turns)
            except Exception as exc:  # noqa: BLE001
                recipient_reply = f"[{self.recipient_id}] error: {exc}"
                termination_reason = TerminationReason.ERROR

            turn = ConversationTurn(
                turn_number=turn_num,
                initiator_msg=current_msg,
                recipient_reply=recipient_reply,
                initiator_id=self.initiator_id,
                recipient_id=self.recipient_id,
            )
            turns.append(turn)

            logger.debug(
                f"[ConvSession] {self.initiator_id}→{self.recipient_id} "
                f"turn={turn_num} | reply: {recipient_reply[:60]}"
            )

            # Verifica termination condition
            if (
                self.is_termination_msg is not None
                and self.is_termination_msg(recipient_reply)
            ):
                termination_reason = TerminationReason.TERMINATION_MSG
                turn.terminated_by_recipient = True
                logger.debug(
                    f"[ConvSession] terminated by is_termination_msg at turn {turn_num}"
                )
                break

            # Initiator responde ao recipient (para a próxima iteração)
            if turn_num < self.max_turns:
                try:
                    current_msg = initiator_fn(recipient_reply, turns)
                except Exception as exc:  # noqa: BLE001
                    current_msg = f"[{self.initiator_id}] error: {exc}"
        else:
            termination_reason = TerminationReason.MAX_TURNS

        # Gera summary
        if callable(self.summary_method):
            try:
                summary_text = self.summary_method(turns)
            except Exception:  # noqa: BLE001
                summary_text = turns[-1].recipient_reply if turns else ""
        else:
            # 'last_msg' (default AutoGen)
            summary_text = turns[-1].recipient_reply if turns else ""

        session = SessionSummary(
            initiator_id=self.initiator_id,
            recipient_id=self.recipient_id,
            turns=turns,
            termination_reason=termination_reason,
            summary=summary_text,
            symbol=sym,
            cycle_id=cycle_id,
            duration_ms=(time.monotonic() - t_start) * 1000,
        )

        self._sessions.append(session)
        if len(self._sessions) > self.max_sessions_stored:
            self._sessions = self._sessions[-self.max_sessions_stored:]
        self._total_sessions += 1
        self._total_turns += len(turns)

        logger.debug(
            f"[ConvSession] {sym} session done: {len(turns)} turns, "
            f"reason={termination_reason.value}, summary={summary_text[:60]}"
        )
        return session

    def get_recent_sessions(self, symbol: Optional[str] = None, limit: int = 5) -> List[SessionSummary]:
        """Retorna sessões recentes, opcionalmente filtradas por símbolo."""
        sessions = self._sessions
        if symbol:
            sym = symbol.upper()
            sessions = [s for s in sessions if s.symbol == sym]
        return sessions[-limit:]

    def summary(self) -> dict:
        return {
            "initiator_id": self.initiator_id,
            "recipient_id": self.recipient_id,
            "max_turns": self.max_turns,
            "total_sessions": self._total_sessions,
            "total_turns": self._total_turns,
            "summary_method": str(self.summary_method),
        }


# ---------------------------------------------------------------------------
# Factory / Singleton gerenciado por par de agentes
# ---------------------------------------------------------------------------

_sessions: Dict[str, MekkaConversationSession] = {}


def get_conversation_session(
    initiator_id: str = "Vision",
    recipient_id: str = "VisionCritic",
    max_turns: int = 3,
    is_termination_msg: Optional[Callable[[str], bool]] = None,
) -> MekkaConversationSession:
    """
    Retorna (ou cria) uma sessão de conversa para o par de agentes.

    A sessão é keyed por 'initiator_id:recipient_id'.
    """
    key = f"{initiator_id}:{recipient_id}"
    if key not in _sessions:
        _sessions[key] = MekkaConversationSession(
            initiator_id=initiator_id,
            recipient_id=recipient_id,
            max_turns=max_turns,
            is_termination_msg=is_termination_msg,
        )
    return _sessions[key]


def reset_conversation_sessions() -> None:
    """Reseta todas as sessões — para testes."""
    global _sessions
    _sessions = {}

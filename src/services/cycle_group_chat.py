"""
src/services/cycle_group_chat.py
==================================
Story 203 — CycleGroupChatManager: roundtable multi-agente com speaker
selection, inspirado no GroupChat + GroupChatManager do AutoGen.

Inspirado no padrão AutoGen GroupChat / GroupChatManager
(microsoft/autogen, autogen.agentchat.groupchat):
  "A group chat is orchestrated by a GroupChatManager. In each step,
   the manager selects an agent to speak (auto/manual/random/round_robin
   or a custom function). The selected agent speaks and the message is
   broadcast to ALL other agents in the group. This allows multi-agent
   discussion before a final decision."

No AutoGen:
  - GroupChat(agents, messages, max_round, speaker_selection_method)
  - GroupChatManager gerencia o turno, transmite mensagens
  - Métodos de seleção: 'auto' (LLM decide), 'round_robin', 'random', custom fn
  - Cada agente pode ver o histórico completo da discussão
  - A conversa termina quando max_round é atingido ou por is_termination_msg

No Mekka, o equivalente é:
  CycleGroupChatManager permite que múltiplos agentes (Vision, Batman,
  VisionCritic) "discutam" um ciclo antes da decisão final de NickFury.
  Cada participante contribui uma "opinion" que vai para o buffer compartilhado.
  O manager seleciona o próximo speaker via round_robin ou custom function.

  Útil para: regime uncertain → pede opiniões antes de sinalizar
             alto risco → Batman + Vision discutem antes de bloquear

Arquitetura
-----------
  SpeakerSelectionMethod  — ROUND_ROBIN / RANDOM / CUSTOM
  GroupChatMessage        — mensagem de um participante no roundtable
  CycleGroupChat          — buffer de mensagens + participantes
  CycleGroupChatManager
    ├── add_participant(agent_id, role, opinion_fn)
    ├── run_round(symbol, cycle_id, context) → List[GroupChatMessage]
    ├── select_next_speaker() → str
    ├── get_consensus(symbol) → dict
    └── summary() → dict
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# SpeakerSelectionMethod
# ---------------------------------------------------------------------------

class SpeakerSelectionMethod(str, Enum):
    """
    Método de seleção do próximo speaker.

    Mapeamento com AutoGen GroupChat speaker_selection_method:
      ROUND_ROBIN ←→ 'round_robin' (padrão quando LLM não disponível)
      RANDOM      ←→ 'random'
      CUSTOM      ←→ custom function (recebe groupchat.messages, retorna agent_id)
    """
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# GroupChatMessage — mensagem de um participante
# ---------------------------------------------------------------------------

@dataclass
class GroupChatMessage:
    """
    Mensagem de um participante no roundtable.

    Equivalente a uma entrada em groupchat.messages do AutoGen:
    sender + content + timestamp.
    """
    agent_id: str
    role: str
    content: str
    symbol: str
    cycle_id: str
    round_number: int = 0
    timestamp: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "content": self.content,
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "round_number": self.round_number,
        }


# ---------------------------------------------------------------------------
# CycleGroupParticipant — wrapper de participante
# ---------------------------------------------------------------------------

@dataclass
class CycleGroupParticipant:
    """
    Participante do GroupChat.

    Equivalente a um ConversableAgent registrado no GroupChat do AutoGen.
    opinion_fn: função síncrona que recebe (context, history) e retorna str.
    """
    agent_id: str
    role: str  # ex: "vision_analyst", "risk_guardian", "critic"
    opinion_fn: Optional[Callable[[Dict[str, Any], List[GroupChatMessage]], str]] = None

    def get_opinion(
        self,
        context: Dict[str, Any],
        history: List[GroupChatMessage],
    ) -> str:
        """Obtém a opinião do participante dado o contexto atual."""
        if self.opinion_fn is not None:
            try:
                return self.opinion_fn(context, history)
            except Exception as exc:  # noqa: BLE001
                return f"[{self.agent_id}] opinion error: {exc}"
        # Fallback: resumo simples do contexto
        symbol = context.get("symbol", "?")
        action = context.get("action", "HOLD")
        confidence = context.get("confidence", 0.0)
        return f"[{self.agent_id}:{self.role}] {symbol} → {action} (conf={confidence:.2f})"


# ---------------------------------------------------------------------------
# CycleGroupChat — buffer compartilhado de mensagens
# ---------------------------------------------------------------------------

class CycleGroupChat:
    """
    Buffer compartilhado de mensagens do roundtable.

    Equivalente ao GroupChat do AutoGen: mantém messages[] e agents[].
    """

    def __init__(
        self,
        max_round: int = 3,
        selection_method: SpeakerSelectionMethod = SpeakerSelectionMethod.ROUND_ROBIN,
        max_history: int = 200,
    ) -> None:
        self.max_round = max_round
        self.selection_method = selection_method
        self.max_history = max_history

        self._participants: Dict[str, CycleGroupParticipant] = {}
        self._messages: List[GroupChatMessage] = []
        self._current_round: int = 0
        self._speaker_index: int = 0  # para round_robin

    def add_participant(self, participant: CycleGroupParticipant) -> None:
        """Registra um participante no roundtable."""
        self._participants[participant.agent_id] = participant
        logger.debug(f"[GroupChat] participant added: {participant.agent_id} ({participant.role})")

    def remove_participant(self, agent_id: str) -> None:
        """Remove um participante."""
        self._participants.pop(agent_id, None)

    @property
    def participants(self) -> List[CycleGroupParticipant]:
        return list(self._participants.values())

    @property
    def messages(self) -> List[GroupChatMessage]:
        return list(self._messages)

    def append_message(self, msg: GroupChatMessage) -> None:
        """Adiciona mensagem ao buffer compartilhado."""
        self._messages.append(msg)
        if len(self._messages) > self.max_history:
            self._messages = self._messages[-self.max_history:]

    def select_next_speaker(self) -> Optional[CycleGroupParticipant]:
        """
        Seleciona o próximo speaker conforme o método configurado.

        Returns:
            CycleGroupParticipant ou None se não houver participantes.
        """
        participants = self.participants
        if not participants:
            return None

        if self.selection_method == SpeakerSelectionMethod.RANDOM:
            return random.choice(participants)

        # ROUND_ROBIN (default e CUSTOM fallback)
        idx = self._speaker_index % len(participants)
        self._speaker_index += 1
        return participants[idx]

    def clear(self) -> None:
        """Limpa mensagens e reseta round counter."""
        self._messages.clear()
        self._current_round = 0
        self._speaker_index = 0


# ---------------------------------------------------------------------------
# CycleGroupChatManager
# ---------------------------------------------------------------------------

class CycleGroupChatManager:
    """
    Orquestra o roundtable multi-agente no pipeline Mekka.

    Padrão AutoGen GroupChatManager:
    - Gerencia turnos de fala (round_robin / random / custom)
    - Broadcast: cada mensagem vai para o buffer compartilhado
    - run_round() executa um ciclo completo de discussão
    - get_consensus() sintetiza a opinião majoritária dos participantes

    Uso:
        manager = get_cycle_group_chat_manager()
        manager.add_participant("vision", "analyst", vision_opinion_fn)
        manager.add_participant("batman", "risk_guardian", batman_opinion_fn)
        messages = manager.run_round("BTC", cycle_id, context={...})
        consensus = manager.get_consensus("BTC")
    """

    def __init__(
        self,
        max_round: int = 3,
        selection_method: SpeakerSelectionMethod = SpeakerSelectionMethod.ROUND_ROBIN,
        max_sessions_per_symbol: int = 10,
    ) -> None:
        self.max_round = max_round
        self.selection_method = selection_method
        self.max_sessions_per_symbol = max_sessions_per_symbol

        self._chat = CycleGroupChat(max_round=max_round, selection_method=selection_method)
        # Histórico de sessões por símbolo: symbol → list of rounds
        self._sessions: Dict[str, List[List[GroupChatMessage]]] = {}
        self._total_rounds: int = 0
        self._total_sessions: int = 0

    def add_participant(
        self,
        agent_id: str,
        role: str,
        opinion_fn: Optional[Callable] = None,
    ) -> None:
        """Registra um participante no roundtable."""
        participant = CycleGroupParticipant(
            agent_id=agent_id,
            role=role,
            opinion_fn=opinion_fn,
        )
        self._chat.add_participant(participant)

    def remove_participant(self, agent_id: str) -> None:
        """Remove um participante."""
        self._chat.remove_participant(agent_id)

    def run_round(
        self,
        symbol: str,
        cycle_id: str,
        context: Optional[Dict[str, Any]] = None,
        max_round: Optional[int] = None,
    ) -> List[GroupChatMessage]:
        """
        Executa um ciclo completo de discussão.

        Cada participante fala uma vez por round, até max_round rounds.
        Mensagens são broadcast para o buffer compartilhado.

        Args:
            symbol:    Símbolo do ativo
            cycle_id:  ID do ciclo
            context:   Contexto da discussão (action, confidence, regime, etc.)
            max_round: Número de rounds (override do default)

        Returns:
            Lista de GroupChatMessage geradas nesta sessão.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        ctx = context or {}
        ctx["symbol"] = sym
        n_rounds = max_round or self.max_round

        self._chat.clear()
        session_messages: List[GroupChatMessage] = []

        for round_num in range(1, n_rounds + 1):
            participants = self._chat.participants
            if not participants:
                break

            # Todos os participantes falam neste round
            for _ in range(len(participants)):
                speaker = self._chat.select_next_speaker()
                if speaker is None:
                    break

                try:
                    content = speaker.get_opinion(ctx, self._chat.messages)
                except Exception as exc:  # noqa: BLE001
                    content = f"[{speaker.agent_id}] error: {exc}"

                msg = GroupChatMessage(
                    agent_id=speaker.agent_id,
                    role=speaker.role,
                    content=content,
                    symbol=sym,
                    cycle_id=cycle_id,
                    round_number=round_num,
                )
                self._chat.append_message(msg)
                session_messages.append(msg)
                logger.debug(
                    f"[GroupChat] round={round_num} speaker={speaker.agent_id} "
                    f"| {content[:80]}"
                )

            self._total_rounds += 1

        # Armazena sessão por símbolo
        if sym not in self._sessions:
            self._sessions[sym] = []
        self._sessions[sym].append(session_messages)
        if len(self._sessions[sym]) > self.max_sessions_per_symbol:
            self._sessions[sym] = self._sessions[sym][-self.max_sessions_per_symbol:]

        self._total_sessions += 1
        logger.debug(
            f"[GroupChat] session complete: {sym} | "
            f"{len(session_messages)} messages in {n_rounds} rounds"
        )
        return session_messages

    def get_consensus(
        self,
        symbol: str,
        limit: int = 1,
    ) -> Dict[str, Any]:
        """
        Sintetiza a opinião da última sessão como consenso.

        Conta votos por ação (LONG/SHORT/HOLD) nas mensagens mais recentes.

        Args:
            symbol: Símbolo do ativo
            limit:  Número de sessões recentes a considerar

        Returns:
            Dict com majority_vote, vote_counts, messages_count.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        sessions = self._sessions.get(sym, [])
        if not sessions:
            return {"majority_vote": "HOLD", "vote_counts": {}, "messages_count": 0}

        recent_msgs = []
        for session in sessions[-limit:]:
            recent_msgs.extend(session)

        vote_counts: Dict[str, int] = {"LONG": 0, "SHORT": 0, "HOLD": 0}
        for msg in recent_msgs:
            content_upper = msg.content.upper()
            if "LONG" in content_upper:
                vote_counts["LONG"] += 1
            elif "SHORT" in content_upper:
                vote_counts["SHORT"] += 1
            else:
                vote_counts["HOLD"] += 1

        majority = max(vote_counts, key=lambda k: vote_counts[k])
        return {
            "majority_vote": majority,
            "vote_counts": vote_counts,
            "messages_count": len(recent_msgs),
        }

    def get_recent_session(self, symbol: str) -> List[GroupChatMessage]:
        """Retorna as mensagens da última sessão para o símbolo."""
        sym = symbol.upper() if symbol else "UNKNOWN"
        sessions = self._sessions.get(sym, [])
        return sessions[-1] if sessions else []

    def summary(self) -> dict:
        return {
            "participants": [p.agent_id for p in self._chat.participants],
            "total_sessions": self._total_sessions,
            "total_rounds": self._total_rounds,
            "selection_method": self.selection_method.value,
            "max_round": self.max_round,
            "symbols_tracked": list(self._sessions.keys()),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: Optional[CycleGroupChatManager] = None


def get_cycle_group_chat_manager() -> CycleGroupChatManager:
    """Retorna o singleton global do CycleGroupChatManager."""
    global _manager
    if _manager is None:
        try:
            from src.config.settings import settings
            max_round = int(getattr(settings, "group_chat_max_round", 3))
            method_raw = getattr(settings, "group_chat_selection", "round_robin")
            try:
                method = SpeakerSelectionMethod(method_raw.lower())
            except (ValueError, AttributeError):
                method = SpeakerSelectionMethod.ROUND_ROBIN
        except Exception:  # noqa: BLE001
            max_round = 3
            method = SpeakerSelectionMethod.ROUND_ROBIN
        _manager = CycleGroupChatManager(max_round=max_round, selection_method=method)
    return _manager


def reset_cycle_group_chat_manager() -> None:
    """Reseta o singleton — para testes."""
    global _manager
    _manager = None

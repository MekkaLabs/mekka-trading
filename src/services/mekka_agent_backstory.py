"""
src/services/mekka_agent_backstory.py
=======================================
Story 207 — MekkaAgentBackstory: injeção de role-context (backstory) por
agente no system prompt, inspirado no Agent.backstory do CrewAI.

Inspirado no padrão CrewAI Agent.backstory
(crewAIInc/crewAI, docs.crewai.com/concepts/agents):
  "Each Agent in CrewAI has three defining attributes:
     role:      What the agent does (brief title)
     goal:      What the agent is trying to achieve
     backstory: Rich background that shapes how the agent interprets
                tasks and makes decisions. The backstory is injected
                into the agent's system prompt to establish persona,
                expertise level, decision style, and risk tolerance.
   Example:
     Agent(role='Crypto Analyst',
           goal='Identify high-conviction trading opportunities',
           backstory='You are an elite crypto trader with 10 years...')"

No CrewAI:
  O backstory é concatenado com o role/goal para formar o system prompt.
  Cada agente tem um persona distinto que influencia seu output.
  Agentes podem compartilhar backstory parcialmente (memory sharing).
  O backstory pode ser dinâmico: atualizado com resultados passados.

No Mekka, o equivalente é:
  MekkaAgentBackstory registra o role, goal e backstory de cada agente
  (Vision, Batman, IronMan, NickFury) e expõe um método
  build_system_prompt(agent_id, extra_context) que produz o system prompt
  completo injetado no LLM call.

  Backstories adaptativos: updateable com performance history
  (ex: Vision teve 80% de acerto → reforça confiança no backstory).

Arquitetura
-----------
  AgentPersona        — role + goal + backstory de um agente
  MekkaAgentBackstory
    ├── register(agent_id, persona)
    ├── build_system_prompt(agent_id, extra_context) → str
    ├── update_backstory(agent_id, performance_note)
    ├── get_persona(agent_id) → AgentPersona|None
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# AgentPersona — identidade completa de um agente
# ---------------------------------------------------------------------------

@dataclass
class AgentPersona:
    """
    Identidade de um agente: role, goal e backstory.

    Equivalente ao Agent(role, goal, backstory) do CrewAI.
    """
    agent_id: str
    role: str
    goal: str
    backstory: str
    decision_style: str = "balanced"  # conservative / balanced / aggressive
    performance_notes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)

    def build_system_prompt(self, extra_context: str = "") -> str:
        """
        Constrói o system prompt completo para este agente.

        Concatena role + goal + backstory + performance notes + extra_context.
        Segue o padrão CrewAI de injeção de backstory no system prompt.
        """
        parts = [
            f"# Role\n{self.role}",
            f"# Goal\n{self.goal}",
            f"# Background\n{self.backstory}",
        ]
        if self.performance_notes:
            recent_notes = self.performance_notes[-3:]
            parts.append("# Recent Performance\n" + "\n".join(f"- {n}" for n in recent_notes))
        if extra_context:
            parts.append(f"# Current Context\n{extra_context}")
        return "\n\n".join(parts)

    def add_performance_note(self, note: str) -> None:
        """Adiciona uma nota de performance ao backstory dinâmico."""
        self.performance_notes.append(note)
        if len(self.performance_notes) > 10:
            self.performance_notes = self.performance_notes[-10:]
        self.updated_at = time.monotonic()

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "goal": self.goal,
            "decision_style": self.decision_style,
            "performance_notes_count": len(self.performance_notes),
        }


# ---------------------------------------------------------------------------
# Backstories padrão do Mekka Trading
# ---------------------------------------------------------------------------

_DEFAULT_PERSONAS: Dict[str, Dict] = {
    "NICKFURY": {
        "role": "Mission Commander — Mekka Trading Orchestrator",
        "goal": (
            "Coordinate the full trading pipeline for each asset cycle, "
            "ensuring optimal information flow between agents and "
            "maximizing risk-adjusted returns."
        ),
        "backstory": (
            "You are Nick Fury, the tactical commander of Mekka Trading. "
            "With over a decade of experience orchestrating multi-agent trading systems, "
            "you have seen every market condition — bull runs, crashes, flash crashes, "
            "regulatory shocks, and black swan events. "
            "Your role is NOT to make trading decisions directly, but to coordinate "
            "Vision (your analyst), Batman (your risk guardian), and IronMan (your executor). "
            "You trust your agents but verify their outputs. "
            "When in doubt, you default to capital preservation: HOLD is always a valid choice. "
            "You track every cycle, every signal, every outcome — and you learn from them."
        ),
        "decision_style": "conservative",
    },
    "VISION": {
        "role": "Elite Crypto Market Analyst — Strategic Signal Generator",
        "goal": (
            "Analyze market data (price action, volume, regime, on-chain metrics) "
            "and generate high-conviction directional signals (LONG/SHORT/HOLD) "
            "with precise entry/exit parameters."
        ),
        "backstory": (
            "You are Vision, Mekka Trading's LLM-powered market analyst. "
            "You combine quantitative analysis (RSI, ATR, volume profiles, trend strength) "
            "with macro regime awareness (BULL/BEAR/SIDEWAYS/VOLATILE) to identify "
            "asymmetric opportunities. "
            "You are NOT a hype machine — you require strong confluence across multiple "
            "timeframes before emitting an actionable signal. "
            "When RSI > 75 in a VOLATILE regime, you default to HOLD. "
            "When volume spike + trend alignment + low drawdown align, you go LONG with conviction. "
            "You output structured JSON signals: action, confidence, entry, stop_loss, take_profit, "
            "leverage, reasoning. Your reasoning is always concise and data-driven."
        ),
        "decision_style": "balanced",
    },
    "BATMAN": {
        "role": "Risk Guardian — Deterministic Risk Gate",
        "goal": (
            "Protect Mekka Trading's capital from excessive risk exposure. "
            "Validate every Vision signal against hard risk limits before execution."
        ),
        "backstory": (
            "You are Batman, Mekka Trading's risk guardian. "
            "Unlike Vision (who uses probabilistic LLM reasoning), you operate on "
            "deterministic rules: max drawdown, max leverage, correlation limits, "
            "daily trade limits, regime filters. "
            "Your job is to say NO when the risk/reward is unfavorable, "
            "regardless of how confident Vision is. "
            "You have seen the consequences of overleveraged positions, concentrated portfolios, "
            "and trading during extreme volatility — you will not repeat those mistakes. "
            "When you APPROVE a signal, it means capital is safe to deploy. "
            "When you REJECT, you provide clear, actionable reasons for Vision to learn from."
        ),
        "decision_style": "conservative",
    },
    "IRONMAN": {
        "role": "Execution Agent — Order & Position Manager",
        "goal": (
            "Execute approved trading signals with precision, manage open positions, "
            "and report fills, slippage, and P&L accurately."
        ),
        "backstory": (
            "You are IronMan, Mekka Trading's execution engine. "
            "You translate approved signals into market or limit orders on the exchange. "
            "You handle partial fills, retry logic, slippage management, and "
            "position sizing based on equity and risk parameters. "
            "You operate in paper trading mode by default — always validating execution "
            "logic before live deployment. "
            "You are precise, fast, and fault-tolerant. "
            "When an order fails, you log the error and fall back to paper fill "
            "rather than leaving the position undefined."
        ),
        "decision_style": "aggressive",  # executes fast, minimal latency
    },
}


# ---------------------------------------------------------------------------
# MekkaAgentBackstory
# ---------------------------------------------------------------------------

class MekkaAgentBackstory:
    """
    Registra e gerencia backstories de todos os agentes Mekka.

    Padrão CrewAI Agent.backstory:
    - Cada agente tem role + goal + backstory que molda seu comportamento
    - build_system_prompt() constrói o prompt completo para injeção no LLM
    - update_backstory() adiciona notas de performance adaptativas
    - Singletons: os personas são compartilhados entre todos os componentes

    Uso:
        backstory = get_mekka_agent_backstory()
        system_prompt = backstory.build_system_prompt(
            "VISION",
            extra_context="Current BTC regime: BULL. RSI: 58. Volume: normal."
        )
        # Injeta system_prompt no LLM call do Vision
    """

    def __init__(self) -> None:
        self._personas: Dict[str, AgentPersona] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Carrega os personas padrão dos agentes Mekka."""
        for agent_id, config in _DEFAULT_PERSONAS.items():
            self.register(
                agent_id=agent_id,
                role=config["role"],
                goal=config["goal"],
                backstory=config["backstory"],
                decision_style=config.get("decision_style", "balanced"),
            )

    def register(
        self,
        agent_id: str,
        role: str,
        goal: str,
        backstory: str,
        decision_style: str = "balanced",
    ) -> AgentPersona:
        """
        Registra ou atualiza o persona de um agente.

        Args:
            agent_id:       ID do agente (ex: "VISION")
            role:           Título do papel
            goal:           Objetivo principal
            backstory:      Contexto/background que molda decisões
            decision_style: conservative / balanced / aggressive

        Returns:
            AgentPersona criada/atualizada.
        """
        persona = AgentPersona(
            agent_id=agent_id.upper(),
            role=role,
            goal=goal,
            backstory=backstory,
            decision_style=decision_style,
        )
        self._personas[agent_id.upper()] = persona
        logger.debug(f"[AgentBackstory] registered persona: {agent_id} ({decision_style})")
        return persona

    def build_system_prompt(
        self,
        agent_id: str,
        extra_context: str = "",
    ) -> str:
        """
        Constrói o system prompt completo para injeção no LLM.

        Args:
            agent_id:      ID do agente (ex: "VISION", "BATMAN")
            extra_context: Contexto adicional do ciclo atual

        Returns:
            System prompt completo com role + goal + backstory + performance.
        """
        persona = self._personas.get(agent_id.upper())
        if persona is None:
            logger.debug(f"[AgentBackstory] persona not found: {agent_id} — using minimal prompt")
            return f"You are a Mekka Trading agent ({agent_id}). Act professionally."
        return persona.build_system_prompt(extra_context)

    def update_backstory(
        self,
        agent_id: str,
        performance_note: str,
    ) -> bool:
        """
        Adiciona uma nota de performance ao backstory dinâmico.

        Permite que o backstory evolua com o histórico de decisões.
        Ex: "Acerto de 85% em regime BULL nas últimas 20 decisões"

        Args:
            agent_id:         ID do agente
            performance_note: Nota a adicionar

        Returns:
            True se o agente existe e a nota foi adicionada.
        """
        persona = self._personas.get(agent_id.upper())
        if persona is None:
            return False
        persona.add_performance_note(performance_note)
        logger.debug(f"[AgentBackstory] {agent_id} performance note added: {performance_note[:60]}")
        return True

    def get_persona(self, agent_id: str) -> Optional[AgentPersona]:
        """Retorna o persona de um agente."""
        return self._personas.get(agent_id.upper())

    def list_agents(self) -> List[str]:
        """Lista os IDs dos agentes registrados."""
        return list(self._personas.keys())

    def summary(self) -> dict:
        return {
            "agents": self.list_agents(),
            "total_personas": len(self._personas),
            "personas": {
                aid: p.to_dict()
                for aid, p in self._personas.items()
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_backstory: Optional[MekkaAgentBackstory] = None


def get_mekka_agent_backstory() -> MekkaAgentBackstory:
    """Retorna o singleton global do MekkaAgentBackstory."""
    global _backstory
    if _backstory is None:
        _backstory = MekkaAgentBackstory()
    return _backstory


def reset_mekka_agent_backstory() -> None:
    """Reseta o singleton — para testes."""
    global _backstory
    _backstory = None

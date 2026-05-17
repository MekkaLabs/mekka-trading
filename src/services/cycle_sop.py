"""
src/services/cycle_sop.py
========================================
Story 185 — CycleSOP: especificação declarativa do pipeline de ciclo.

Inspirado no padrão MetaGPT SOP (Standard Operating Procedure):
  "SOPs are modeled after efficient human workflows and encoded as sequences
   of prompts, critical for guiding agent actions, clearly defining
   responsibilities, and establishing standards for intermediate outputs."

No MetaGPT, o SOP define a sequência de estágios (ProductManager → Architect →
Engineer → QA) com entradas/saídas tipadas e condições de skip para cada etapa.
Code = SOP(Team) — o pipeline é o produto, os agentes são os trabalhadores.

No Mekka, o equivalente é o CycleSOP que descreve formalmente os estágios do
_cycle_for_symbol: quais são, em que ordem, quais são suas pré-condições e
outputs esperados. Isso torna o pipeline auditável, testável e documentado —
qualquer dashboard pode serializar o SOP para mostrar o "estado atual do ciclo".

Arquitetura
-----------
  SOPStage — definição de um estágio (nome, agente, input_type, output_type, skippable)
  CycleSOP  — coleção ordenada de SOPStages com helpers de inspeção
    ├── stages            — lista de SOPStage em ordem de execução
    ├── get_stage(name)   — lookup por nome
    ├── to_prompt_section() → str   (bloco legível para dashboards/logs)
    └── to_dict()           → dict

Uso
---
    from src.services.cycle_sop import get_cycle_sop

    sop = get_cycle_sop()
    print(sop.to_prompt_section())
    # Para dashboards: GET /api/cycle-sop
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# SOPStage
# ---------------------------------------------------------------------------

@dataclass
class SOPStage:
    """
    Definição de um estágio no SOP do ciclo de trading.

    Espelha o conceito MetaGPT de "Role + Action" onde cada estágio tem
    um agente responsável, input definido, output esperado e condição de skip.
    """
    name: str
    agent: str                    # ex: "NickFury", "Vision", "Batman", "IronMan"
    description: str
    input_type: str               # tipo de dado de entrada
    output_type: str              # tipo de dado de saída
    skippable: bool = False       # True = pode ser pulado por IncrementalCycleSkip
    dependencies: List[str] = field(default_factory=list)  # estágios que devem preceder

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "agent": self.agent,
            "description": self.description,
            "input_type": self.input_type,
            "output_type": self.output_type,
            "skippable": self.skippable,
            "dependencies": self.dependencies,
        }

    def to_prompt_line(self) -> str:
        skip_tag = " [skippable]" if self.skippable else ""
        return (
            f"  {self.name:<22} [{self.agent}]{skip_tag}\n"
            f"    {self.description}\n"
            f"    Input: {self.input_type} → Output: {self.output_type}"
        )


# ---------------------------------------------------------------------------
# CycleSOP
# ---------------------------------------------------------------------------

class CycleSOP:
    """
    Standard Operating Procedure do ciclo de trading Mekka.

    Padrão MetaGPT: Code = SOP(Team). O pipeline inteiro é descrito
    declarativamente como uma sequência de estágios com agentes, tipos
    e condições de skip — auditável e serializável.
    """

    def __init__(self) -> None:
        self._stages: List[SOPStage] = self._build_stages()

    def _build_stages(self) -> List[SOPStage]:
        """Define a sequência canônica de estágios do ciclo Mekka."""
        return [
            SOPStage(
                name="OPPORTUNITY_SCAN",
                agent="NickFury",
                description="Pré-scan de oportunidade via OpportunityScanner antes de alocar recursos.",
                input_type="symbol: str",
                output_type="bool (opportunity_found)",
                skippable=True,
                dependencies=[],
            ),
            SOPStage(
                name="MARKET_ANALYSIS",
                agent="ProfessorX",
                description="Coleta dados de mercado: preço, indicadores técnicos, sentimento, OI.",
                input_type="symbol: str",
                output_type="MarketAnalysis",
                skippable=False,
                dependencies=["OPPORTUNITY_SCAN"],
            ),
            SOPStage(
                name="VISION_SIGNAL",
                agent="Vision",
                description="LLM gera TradingSignal com action/confidence/SL/TP/reasoning. "
                            "Opcionalmente usa ArchitectEditor (Story 178) e TradeAnnotationWatcher (Story 180).",
                input_type="MarketAnalysis",
                output_type="TradingSignal",
                skippable=True,  # IncrementalCycleSkip (Story 187) pode reutilizar último sinal
                dependencies=["MARKET_ANALYSIS"],
            ),
            SOPStage(
                name="SIGNAL_LINT",
                agent="NickFury",
                description="AutoSignalLinter corrige geometria do sinal (clamp, swap, fallback).",
                input_type="TradingSignal",
                output_type="TradingSignal (linted)",
                skippable=True,
                dependencies=["VISION_SIGNAL"],
            ),
            SOPStage(
                name="SIGNAL_VALIDATION",
                agent="NickFury",
                description="SignalValidator verifica R:R, leverage, confidence — rejeita se inválido.",
                input_type="TradingSignal",
                output_type="ValidationResult",
                skippable=False,
                dependencies=["SIGNAL_LINT"],
            ),
            SOPStage(
                name="RISK_ASSESSMENT",
                agent="Batman",
                description="Aplica gates de risco: equity, regime (gate 5b), cap_tier (gate 5c), "
                            "kill switch, daily PnL.",
                input_type="TradingSignal + RiskContext",
                output_type="RiskApproval",
                skippable=False,
                dependencies=["SIGNAL_VALIDATION"],
            ),
            SOPStage(
                name="HUMAN_APPROVAL",
                agent="NickFury",
                description="Solicita aprovação humana via Telegram se configurado (LG interrupt).",
                input_type="RiskApproval (APPROVED)",
                output_type="bool (approved)",
                skippable=True,
                dependencies=["RISK_ASSESSMENT"],
            ),
            SOPStage(
                name="EXECUTION",
                agent="IronMan",
                description="Envia ordem para exchange (Bybit/Hyperliquid) e aguarda confirmação.",
                input_type="TradingSignal + RiskApproval",
                output_type="ExecutionResult",
                skippable=False,
                dependencies=["HUMAN_APPROVAL"],
            ),
            SOPStage(
                name="OUTCOME_RECORD",
                agent="NickFury",
                description="Registra resultado na AgentMemoryStore, RoleWorkingMemory (Story 183) "
                            "e SignalChangeLog. Atualiza equity dinâmica.",
                input_type="ExecutionResult",
                output_type="void",
                skippable=True,
                dependencies=["EXECUTION"],
            ),
        ]

    @property
    def stages(self) -> List[SOPStage]:
        return list(self._stages)

    def get_stage(self, name: str) -> Optional[SOPStage]:
        """Lookup por nome (case-insensitive)."""
        name_up = name.upper()
        for s in self._stages:
            if s.name.upper() == name_up:
                return s
        return None

    def skippable_stages(self) -> List[SOPStage]:
        """Retorna estágios que podem ser pulados pelo IncrementalCycleSkip."""
        return [s for s in self._stages if s.skippable]

    def to_prompt_section(self) -> str:
        """
        Bloco formatado para uso em dashboards, logs e testes.

        Formato:
            === Mekka Trading Cycle SOP ===
            Sequência de 9 estágios executados por ciclo de símbolo.

              OPPORTUNITY_SCAN    [NickFury] [skippable]
                Pre-scan...
                Input: symbol → Output: bool
              ...
        """
        lines = [
            "=== Mekka Trading Cycle SOP ===",
            f"Sequência de {len(self._stages)} estágios executados por ciclo de símbolo.",
            "",
        ]
        for stage in self._stages:
            lines.append(stage.to_prompt_line())
            lines.append("")

        return "\n".join(lines).rstrip()

    def to_dict(self) -> dict:
        return {
            "version": "1.0",
            "total_stages": len(self._stages),
            "skippable_count": len(self.skippable_stages()),
            "stages": [s.to_dict() for s in self._stages],
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_sop: Optional[CycleSOP] = None


def get_cycle_sop() -> CycleSOP:
    """Retorna o singleton global do CycleSOP."""
    global _sop
    if _sop is None:
        _sop = CycleSOP()
    return _sop


def reset_cycle_sop() -> None:
    """Reseta o singleton — para testes."""
    global _sop
    _sop = None

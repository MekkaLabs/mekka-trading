"""
src/prompt_engineering/models.py
================================
Modelos Pydantic para o agente Prometheus.

Todos os outputs são tipados — facilita testes e integração com outras
ferramentas (CLI, CI workflow, dashboards futuros).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AuditDimension(str, Enum):
    """As 4 dimensões do scorecard P.R.O.M.P.T."""

    CLARITY = "clarity"                # P-Purpose, R-Role, O-Output bem definidos
    HALLUCINATION_RISK = "hallucination_risk"  # M-Method anti-alucinação
    TESTABILITY = "testability"        # T-Test critério verificável
    PROMPT_COVERAGE = "prompt_coverage"  # Cobertura geral P.R.O.M.P.T.


class DimensionScore(BaseModel):
    """Score 0-10 por dimensão + diagnóstico."""

    dimension: AuditDimension
    score: int = Field(ge=0, le=10)
    findings: list[str] = Field(default_factory=list)


class Scorecard(BaseModel):
    """
    Scorecard P.R.O.M.P.T. completo para um prompt.

    `score_total` é a soma das 4 dimensões (0-40).
    """

    scorecard_version: str = "1.0"
    audited_at: datetime = Field(default_factory=datetime.utcnow)
    dimensions: list[DimensionScore]
    score_total: int = Field(ge=0, le=40)
    recommendations: list[str] = Field(default_factory=list)

    def by_dimension(self, dim: AuditDimension) -> Optional[DimensionScore]:
        for d in self.dimensions:
            if d.dimension == dim:
                return d
        return None

    @property
    def health(self) -> str:
        """Etiqueta resumida do score total."""
        if self.score_total >= 32:
            return "EXCELLENT"
        if self.score_total >= 24:
            return "GOOD"
        if self.score_total >= 16:
            return "NEEDS_WORK"
        return "CRITICAL"


class ExtractedPrompt(BaseModel):
    """Resultado da extração de um prompt de um arquivo Python."""

    source_file: str            # caminho relativo ao repo
    variable_name: str          # ex: "_SYSTEM_PROMPT"
    line_number: int            # linha do assignment
    content: str                # texto literal do prompt
    fingerprint: str            # SHA-256 16 hex (mesmo formato do prompt_registry)
    detected_role: str = ""     # "system" | "user" | "pre_reasoning" | "" (heurística)


class PromptRecord(BaseModel):
    """
    Entrada no catálogo persistente.

    Combina ExtractedPrompt + Scorecard + metadata de versionamento.
    """

    name: str                              # ex: "vision_system_prompt"
    fingerprint: str                       # SHA-256 16 hex
    extracted: ExtractedPrompt
    scorecard: Optional[Scorecard] = None
    compatible_models: list[str] = Field(default_factory=list)
    notes: str = ""
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_audited_at: Optional[datetime] = None

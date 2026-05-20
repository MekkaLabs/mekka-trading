"""Galactus — Premortem Specialist / Devourer of Ideas.

Galactus is the counterpoint to Beast (who proposes improvements) and Jean
Grey (who remembers). Where they build, Galactus *devours*: he runs a
premortem on every proposal — "assume this shipped and failed catastrophically;
why?" — and only ideas that survive his hunger reach Mekka consolidated and
hardened.

He is read-only and never executes anything. His verdicts are advisory: the
operator (and Mekka's consolidation) decides what actually happens.

Design (mirrors Beast / Jean Grey):
  - No LLM dependency in the MVP: premortem is heuristic, driven by the
    proposal's area criticality, claimed impact, and evidence strength, plus
    area-specific failure-mode templates. An optional LLM enhancement hook is
    a deliberate Phase-2 follow-up.
  - Domain-agnostic: works for trading/ops proposals (Beast) AND dev-squad
    proposals (backend/frontend/dashboard/design), so the same premortem lens
    applies across the whole continuous-improvement council.
  - Fail-silent: any error degrades to a conservative verdict, never crashes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from src.agents.base import BaseAgent

# ---------------------------------------------------------------------------
# Risk model
# ---------------------------------------------------------------------------

# How catastrophic is a failure in this area? Areas that touch real money or
# the execution path are CRITICAL — Galactus is hungriest there.
_AREA_CRITICALITY = {
    # trading / ops (heroes)
    "risk_gates": "CRITICAL", "risk": "CRITICAL", "execution": "CRITICAL",
    "trading": "CRITICAL", "signal_quality": "HIGH", "latency": "HIGH",
    "infra": "HIGH",
    # dev squads
    "backend": "HIGH", "security": "CRITICAL", "data": "HIGH",
    "frontend": "MODERATE", "dashboard": "MODERATE", "design": "MODERATE",
    "ux": "MODERATE", "docs": "LOW",
}
_DEFAULT_CRITICALITY = "MODERATE"

_IMPACT_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
_CRIT_WEIGHT = {"CRITICAL": 3, "HIGH": 2, "MODERATE": 1, "LOW": 0}

# Area-specific failure modes Galactus always probes. Generic ones apply to
# everything; specific ones layer on top when the area matches.
_GENERIC_FAILURE_MODES = [
    ("Rollout sem rollback", "Mudança aplicada sem caminho de reversão claro.",
     "Definir plano de rollback e feature flag antes de aplicar."),
    ("Evidência insuficiente", "A proposta não comprova o problema com dados.",
     "Anexar métrica/baseline antes/depois e critério de sucesso mensurável."),
]
_AREA_FAILURE_MODES: dict[str, list[tuple[str, str, str]]] = {
    "risk_gates": [
        ("Afrouxa um gate de risco", "Relaxar limites pode liberar trades perigosos.",
         "Validar em paper/testnet com cenários de stress (Hulk/stress_inject) antes de mainnet."),
        ("Bypassa o Batman", "Qualquer caminho que pule o risk manager é inaceitável em mainnet.",
         "Garantir que Batman → IronMan permaneça obrigatório; Modo Deus só em paper/testnet."),
    ],
    "execution": [
        ("Ordem duplicada / race", "Dois caminhos de execução podem emitir ordens repetidas.",
         "Idempotência por recommendation_id + lock no /api/trade/*."),
        ("Mínimos da exchange", "Notional abaixo do mínimo da corretora falha silenciosamente.",
         "Validar min order size por símbolo antes de enviar."),
    ],
    "signal_quality": [
        ("Overfitting ao passado", "Otimizar para o histórico recente degrada no futuro.",
         "Validar out-of-sample / walk-forward antes de promover."),
    ],
    "latency": [
        ("Otimização prematura", "Ganho de latência pode adicionar complexidade frágil.",
         "Medir gargalo real (profiling) antes de reescrever."),
    ],
    "security": [
        ("Nova superfície de ataque", "Mudança pode expor endpoint/credencial.",
         "Threat model + revisão de auth/CSP antes de merge."),
    ],
    "frontend": [
        ("Regressão visual / acessibilidade", "Mudança de UI pode quebrar layout/contraste.",
         "Checar light+dark, mobile e leitores de tela."),
    ],
    "dashboard": [
        ("Bloqueia o event loop", "Trabalho pesado no handler trava o servidor async.",
         "Rodar CPU-bound em asyncio.to_thread."),
    ],
}


@dataclass
class FailureMode:
    mode: str
    likelihood: str   # "HIGH" | "MEDIUM" | "LOW"
    mitigation: str


@dataclass
class PremortemVerdict:
    """Galactus' premortem on a single proposal."""

    proposal_title: str
    area: str
    verdict: str          # "DEVOURED" | "NEEDS_HARDENING" | "SURVIVES"
    hunger_score: float   # 0..100 — how badly Galactus wants to devour it (risk)
    failure_modes: list[FailureMode] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "proposal_title": self.proposal_title,
            "area": self.area,
            "verdict": self.verdict,
            "hunger_score": round(self.hunger_score, 1),
            "failure_modes": [
                {"mode": f.mode, "likelihood": f.likelihood, "mitigation": f.mitigation}
                for f in self.failure_modes
            ],
            "rationale": self.rationale,
        }


@dataclass
class PremortemReport:
    generated_at: str
    verdicts: list[PremortemVerdict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def devoured(self) -> list[PremortemVerdict]:
        return [v for v in self.verdicts if v.verdict == "DEVOURED"]

    @property
    def survived(self) -> list[PremortemVerdict]:
        return [v for v in self.verdicts if v.verdict == "SURVIVES"]

    def verdict_for(self, title: str) -> Optional[PremortemVerdict]:
        for v in self.verdicts:
            if v.proposal_title == title:
                return v
        return None

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "total": len(self.verdicts),
            "devoured": len(self.devoured),
            "survived": len(self.survived),
            "needs_hardening": sum(1 for v in self.verdicts if v.verdict == "NEEDS_HARDENING"),
            "verdicts": [v.to_dict() for v in self.verdicts],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Galactus(BaseAgent[PremortemReport]):
    """Premortem specialist — devours weak ideas so only hardened ones survive."""

    def __init__(self) -> None:
        super().__init__(
            "Galactus",
            "Premortem Specialist — devourer of ideas, counterpoint to Beast & Jean Grey",
        )

    async def _run(self, proposals: Optional[list] = None) -> PremortemReport:  # type: ignore[override]
        report = PremortemReport(generated_at=datetime.now(timezone.utc).isoformat())
        for raw in (proposals or []):
            try:
                report.verdicts.append(self._premortem(self._as_dict(raw)))
            except Exception as exc:  # noqa: BLE001 — fail-silent per proposal
                self._log.warning(f"[Galactus] premortem failed: {exc}")
                report.errors.append(str(exc))
        self._log.info(
            f"[Galactus] devoured {len(report.devoured)}/{len(report.verdicts)} "
            f"proposals (premortem)"
        )
        return report

    @staticmethod
    def _as_dict(raw: Any) -> dict:
        """Accept ImprovementProposal, dict, or anything with the fields."""
        if isinstance(raw, dict):
            return raw
        return {
            "title": getattr(raw, "title", "Proposta"),
            "description": getattr(raw, "description", ""),
            "impact": getattr(raw, "impact", "MEDIUM"),
            "area": getattr(raw, "area", "infra"),
            "evidence": getattr(raw, "evidence", ""),
        }

    def _premortem(self, p: dict) -> PremortemVerdict:
        title = str(p.get("title") or "Proposta")
        area = str(p.get("area") or "infra").lower()
        impact = str(p.get("impact") or "MEDIUM").upper()
        evidence = str(p.get("evidence") or "").strip()

        criticality = _AREA_CRITICALITY.get(area, _DEFAULT_CRITICALITY)

        # ── Hunger score (0..100) ───────────────────────────────────────
        # Higher = riskier = Galactus hungrier. Components:
        #   impact (claimed blast radius) + area criticality + evidence gap.
        impact_w = _IMPACT_WEIGHT.get(impact, 2)          # 1..3
        crit_w = _CRIT_WEIGHT.get(criticality, 1)         # 0..3
        evidence_gap = 0 if len(evidence) >= 40 else (1 if evidence else 2)  # 0..2
        # Normalize to 0..100. Max raw = 3 + 3 + 2 = 8.
        hunger = round((impact_w + crit_w + evidence_gap) / 8.0 * 100, 1)

        # ── Failure modes ───────────────────────────────────────────────
        modes: list[FailureMode] = []
        for mode, desc, mit in _AREA_FAILURE_MODES.get(area, []):
            modes.append(FailureMode(mode=f"{mode} — {desc}", likelihood="MEDIUM", mitigation=mit))
        for mode, desc, mit in _GENERIC_FAILURE_MODES:
            lk = "HIGH" if (mode.startswith("Evidência") and evidence_gap >= 1) else "LOW"
            modes.append(FailureMode(mode=f"{mode} — {desc}", likelihood=lk, mitigation=mit))

        # ── Verdict ─────────────────────────────────────────────────────
        if criticality == "CRITICAL" and evidence_gap >= 2:
            verdict = "DEVOURED"
            rationale = (
                f"Área CRÍTICA ({area}) sem evidência sólida — Galactus devora. "
                "Traga dados/baseline antes de propor de novo."
            )
        elif hunger >= 70:
            verdict = "NEEDS_HARDENING"
            rationale = (
                f"Alto risco (hunger {hunger:.0f}) em área {criticality.lower()}. "
                "Só sobrevive com as mitigações listadas + validação em paper/testnet."
            )
        elif hunger >= 45:
            verdict = "NEEDS_HARDENING"
            rationale = (
                f"Risco moderado (hunger {hunger:.0f}). Aplicar mitigações reduz a fome."
            )
        else:
            verdict = "SURVIVES"
            rationale = (
                f"Baixo risco (hunger {hunger:.0f}) e área {criticality.lower()}. "
                "Sobrevive ao premortem — pode seguir com cuidado padrão."
            )

        return PremortemVerdict(
            proposal_title=title,
            area=area,
            verdict=verdict,
            hunger_score=hunger,
            failure_modes=modes,
            rationale=rationale,
        )

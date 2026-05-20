"""Mekka — Continuous-Improvement Commander & Consolidator.

Mekka is the leader of the improvement council. He is the hero the system is
named after: a future super-hero with the greatest technological powers and
decisive, accurate judgement. He does not generate raw ideas himself — he
*consolidates* the council:

    Beast       → proposes improvements (data-driven, from the audit trail)
    Jean Grey   → supplies memory / vault context
    Galactus    → premortems every proposal (devours the weak ones)
        ↓
    Mekka       → consolidates proposal + context + premortem into a single
                  ranked recommendation, with a clear decision, for each of
                  two domains:
                    • trading/ops heroes  (risk, execution, signals, latency)
                    • dev squads          (backend, frontend, dashboard, design)
        ↓
    Operator    → accepts / rejects in the "Central de Melhorias" panel.

Mekka is read-only with respect to trading. The only state he writes is the
operator's accept/reject decisions (data/improvement_decisions.json) and an
optional human/agent-curated proposal inbox (data/improvement_inbox.json).
Both are runtime artifacts (gitignored).

Fail-silent: any sub-source error degrades gracefully to an empty/partial
council rather than crashing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.agents.base import BaseAgent
from src.agents.galactus import Galactus, PremortemVerdict

# ---------------------------------------------------------------------------
# Paths (runtime state — gitignored)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DECISIONS_FILE = _DATA_DIR / "improvement_decisions.json"
_INBOX_FILE = _DATA_DIR / "improvement_inbox.json"

# Map a proposal area to one of the two improvement domains.
_TRADING_AREAS = {
    "risk_gates", "risk", "execution", "trading", "signal_quality", "latency",
}
_DEV_AREAS = {
    "backend", "frontend", "dashboard", "design", "ux", "security", "data",
    "infra", "docs",
}


def _domain_for(area: str) -> str:
    a = (area or "").lower()
    if a in _TRADING_AREAS:
        return "trading-ops"
    if a in _DEV_AREAS:
        return "dev-squad"
    return "dev-squad"  # default: most non-trading work is dev


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CouncilRecommendation:
    """A single consolidated recommendation Mekka presents to the operator."""

    id: str
    title: str
    domain: str           # "trading-ops" | "dev-squad"
    area: str
    impact: str           # HIGH | MEDIUM | LOW
    source: str           # "beast" | "inbox" | ...
    description: str
    evidence: str
    premortem_verdict: str       # SURVIVES | NEEDS_HARDENING | DEVOURED
    premortem_hunger: float
    mitigations: list[str]
    decision: str         # RECOMMEND | RECOMMEND_WITH_MITIGATION | REJECT | DEFER
    priority: str         # P1 | P2 | P3
    rationale: str
    status: str = "pending"   # operator: pending | accepted | rejected
    decided_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "domain": self.domain,
            "area": self.area,
            "impact": self.impact,
            "source": self.source,
            "description": self.description,
            "evidence": self.evidence,
            "premortem": {
                "verdict": self.premortem_verdict,
                "hunger": round(self.premortem_hunger, 1),
                "mitigations": self.mitigations,
            },
            "decision": self.decision,
            "priority": self.priority,
            "rationale": self.rationale,
            "status": self.status,
            "decided_at": self.decided_at,
        }


@dataclass
class MekkaCouncilReport:
    generated_at: str
    recommendations: list[CouncilRecommendation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        recs = [r.to_dict() for r in self.recommendations]
        return {
            "generated_at": self.generated_at,
            "summary": {
                "total": len(recs),
                "pending": sum(1 for r in recs if r["status"] == "pending"),
                "accepted": sum(1 for r in recs if r["status"] == "accepted"),
                "rejected": sum(1 for r in recs if r["status"] == "rejected"),
                "trading_ops": sum(1 for r in recs if r["domain"] == "trading-ops"),
                "dev_squad": sum(1 for r in recs if r["domain"] == "dev-squad"),
                "recommended": sum(1 for r in recs if r["decision"].startswith("RECOMMEND")),
                "rejected_by_council": sum(1 for r in recs if r["decision"] == "REJECT"),
            },
            "recommendations": recs,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Mekka(BaseAgent[MekkaCouncilReport]):
    """Commander of the continuous-improvement council."""

    def __init__(self) -> None:
        super().__init__(
            "Mekka",
            "Continuous-Improvement Commander — consolidates Beast, Jean Grey & Galactus",
        )

    # -- public entry ----------------------------------------------------

    async def _run(self, period_days: int = 7) -> MekkaCouncilReport:  # type: ignore[override]
        report = MekkaCouncilReport(generated_at=datetime.now(timezone.utc).isoformat())

        # 1) Gather raw proposals: Beast (trading/ops) + curated inbox (any domain).
        proposals: list[dict] = []
        try:
            proposals.extend(await self._beast_proposals(period_days))
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mekka] Beast source failed: {exc}")
            report.errors.append(f"beast: {exc}")
        try:
            proposals.extend(self._inbox_proposals())
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mekka] inbox source failed: {exc}")
            report.errors.append(f"inbox: {exc}")

        if not proposals:
            self._log.info("[Mekka] no proposals to consolidate")
            return report

        # 2) Galactus premortem on the whole batch.
        premortem_by_title: dict[str, PremortemVerdict] = {}
        try:
            galactus_report = await Galactus().run(proposals)
            premortem_by_title = {
                v.proposal_title: v for v in galactus_report.verdicts
            }
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mekka] Galactus premortem failed: {exc}")
            report.errors.append(f"galactus: {exc}")

        # 3) Load persisted operator decisions to preserve accept/reject state.
        decisions = self._load_decisions()

        # 4) Consolidate.
        for p in proposals:
            rec = self._consolidate(p, premortem_by_title.get(str(p.get("title"))))
            persisted = decisions.get(rec.id)
            if persisted:
                rec.status = persisted.get("status", "pending")
                rec.decided_at = persisted.get("decided_at")
            report.recommendations.append(rec)

        # Rank: pending first, then by priority (P1>P2>P3), then hunger desc.
        _prio = {"P1": 0, "P2": 1, "P3": 2}
        report.recommendations.sort(
            key=lambda r: (
                0 if r.status == "pending" else 1,
                _prio.get(r.priority, 3),
                -r.premortem_hunger,
            )
        )
        self._log.info(
            f"[Mekka] consolidated {len(report.recommendations)} recommendations "
            f"({report.to_dict()['summary']['pending']} pendentes)"
        )
        return report

    # -- proposal sources ------------------------------------------------

    async def _beast_proposals(self, period_days: int) -> list[dict]:
        from src.agents.beast import Beast
        beast_report = await Beast().run(period_days=period_days)
        out: list[dict] = []
        for p in beast_report.proposals:
            out.append({
                "title": p.title, "description": p.description,
                "impact": p.impact, "area": p.area, "evidence": p.evidence,
                "source": "beast", "suggested_story": p.suggested_story,
            })
        return out

    def _inbox_proposals(self) -> list[dict]:
        """Human/agent-curated proposals (any domain). Optional file —
        absent inbox just yields nothing."""
        if not _INBOX_FILE.exists():
            return []
        try:
            data = json.loads(_INBOX_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = data if isinstance(data, list) else data.get("proposals", [])
        out: list[dict] = []
        for it in items or []:
            if not isinstance(it, dict) or not it.get("title"):
                continue
            out.append({
                "title": it["title"],
                "description": it.get("description", ""),
                "impact": str(it.get("impact", "MEDIUM")).upper(),
                "area": str(it.get("area", "infra")).lower(),
                "evidence": it.get("evidence", ""),
                "source": it.get("source", "inbox"),
                "suggested_story": it.get("suggested_story"),
            })
        return out

    # -- consolidation ---------------------------------------------------

    @staticmethod
    def _rec_id(title: str, area: str) -> str:
        return hashlib.sha256(f"{area}::{title}".encode("utf-8")).hexdigest()[:12]

    def _consolidate(
        self, p: dict, pm: Optional[PremortemVerdict]
    ) -> CouncilRecommendation:
        title = str(p.get("title") or "Proposta")
        area = str(p.get("area") or "infra").lower()
        impact = str(p.get("impact") or "MEDIUM").upper()
        domain = _domain_for(area)

        verdict = pm.verdict if pm else "SURVIVES"
        hunger = pm.hunger_score if pm else 0.0
        mitigations = [fm.mitigation for fm in pm.failure_modes] if pm else []

        # Mekka's decision = Galactus verdict tempered by impact.
        if verdict == "DEVOURED":
            decision = "REJECT"
            rationale = (
                "Galactus devorou: risco alto sem lastro suficiente. "
                "Mekka recomenda NÃO seguir até trazer evidência/mitigação."
            )
        elif verdict == "NEEDS_HARDENING":
            decision = "RECOMMEND_WITH_MITIGATION"
            rationale = (
                "Mekka aprova condicionalmente: seguir SOMENTE com as mitigações "
                "do Galactus e validação em paper/testnet antes de produção."
            )
        else:  # SURVIVES
            decision = "RECOMMEND"
            rationale = (
                "Sobreviveu ao premortem do Galactus. Mekka recomenda seguir "
                "com o cuidado padrão de revisão/teste."
            )

        # Priority from impact + hunger.
        if impact == "HIGH" and decision != "REJECT":
            priority = "P1"
        elif impact == "MEDIUM" or hunger >= 50:
            priority = "P2"
        else:
            priority = "P3"

        return CouncilRecommendation(
            id=self._rec_id(title, area),
            title=title,
            domain=domain,
            area=area,
            impact=impact,
            source=str(p.get("source") or "beast"),
            description=str(p.get("description") or ""),
            evidence=str(p.get("evidence") or ""),
            premortem_verdict=verdict,
            premortem_hunger=hunger,
            mitigations=mitigations,
            decision=decision,
            priority=priority,
            rationale=rationale,
        )

    # -- operator decisions (persisted) ---------------------------------

    def _load_decisions(self) -> dict[str, dict]:
        if not _DECISIONS_FILE.exists():
            return {}
        try:
            return json.loads(_DECISIONS_FILE.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            return {}

    def record_decision(self, rec_id: str, status: str) -> bool:
        """Persist an operator accept/reject. Returns True on success.

        ``status`` must be 'accepted' or 'rejected' (or 'pending' to reset).
        """
        if status not in ("accepted", "rejected", "pending"):
            return False
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            decisions = self._load_decisions()
            decisions[rec_id] = {
                "status": status,
                "decided_at": datetime.now(timezone.utc).isoformat(),
            }
            _DECISIONS_FILE.write_text(
                json.dumps(decisions, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return True
        except OSError as exc:
            self._log.warning(f"[Mekka] could not persist decision: {exc}")
            return False

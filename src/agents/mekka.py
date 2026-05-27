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
    "infra", "docs", "memory", "research", "measurement",
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

        # Continuous Improvement Department scanners (each isolated: one failing
        # scanner never blocks the others). All read-only / fail-silent.
        for src_name, coro in (
            ("code_auditor", self._code_auditor_proposals()),
            ("risk_scanner", self._risk_scanner_proposals(period_days)),
            ("ops_scanner", self._ops_scanner_proposals(period_days)),
            ("memory_scanner", self._memory_scanner_proposals()),
            ("vault_scanner", self._vault_scanner_proposals()),
            ("agents_scanner", self._agents_scanner_proposals()),
            ("backend_scanner", self._backend_scanner_proposals()),
            ("frontend_scanner", self._frontend_scanner_proposals()),
            ("dashboard_scanner", self._dashboard_scanner_proposals()),
            ("ice_man", self._ice_man_proposals()),
            ("sage", self._sage_proposals()),
        ):
            try:
                proposals.extend(await coro)
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"[Mekka] {src_name} source failed: {exc}")
                report.errors.append(f"{src_name}: {exc}")

        if not proposals:
            self._log.info("[Mekka] no proposals to consolidate")
            return report

        # 1.5) Dedup semântico Jaccard (P0.4 — 2026-05-27).
        # Sem isso, 9 scanners propondo coisas parecidas geram ruído O(n).
        # Jaccard >= 0.6 entre tokens normalizados do (title + description).
        # Mantém a primeira ocorrência e descarta as duplicatas.
        before_dedup = len(proposals)
        proposals = self._dedup_semantic(proposals, threshold=0.6)
        dedup_removed = before_dedup - len(proposals)
        if dedup_removed > 0:
            self._log.info(f"[Mekka] dedup removed {dedup_removed} duplicate proposals")
            report.errors.append(f"dedup_info: removed {dedup_removed}")

        # 1.6) Memória de rejeição (P0.5 — 2026-05-27).
        # Se uma proposta foi rejeitada >=2x no histórico de decisions,
        # suprime auto (operador não quer ver de novo).
        rejected_ids = self._chronically_rejected_ids(min_rejections=2)
        if rejected_ids:
            kept: list[dict] = []
            suppressed = 0
            for p in proposals:
                # Pre-computa rec_id sem consolidar (mesmo hash)
                pre_id = self._preview_rec_id(p)
                if pre_id in rejected_ids:
                    suppressed += 1
                    continue
                kept.append(p)
            if suppressed > 0:
                self._log.info(
                    f"[Mekka] suppressed {suppressed} chronically-rejected proposals"
                )
                report.errors.append(f"suppressed_rejected: {suppressed}")
            proposals = kept

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

    async def _code_auditor_proposals(self) -> list[dict]:
        """CodeAuditor — repo technical-debt scanner (dev-squad)."""
        from src.agents.code_auditor import CodeAuditor
        out: list[dict] = []
        for p in await CodeAuditor().scan():
            out.append({
                "title": p.title, "description": p.description,
                "impact": p.impact, "area": p.area, "evidence": p.evidence,
                "source": "code_auditor", "suggested_story": p.suggested_story,
            })
        return out

    async def _risk_scanner_proposals(self, period_days: int) -> list[dict]:
        """RiskScanner — risk-posture scanner (trading-ops)."""
        from src.agents.risk_scanner import RiskScanner
        out: list[dict] = []
        for p in await RiskScanner().scan(period_days=period_days):
            out.append({
                "title": p.title, "description": p.description,
                "impact": p.impact, "area": p.area, "evidence": p.evidence,
                "source": "risk_scanner", "suggested_story": p.suggested_story,
            })
        return out

    async def _ops_scanner_proposals(self, period_days: int) -> list[dict]:
        """OpsScanner — operational-health scanner (dev-squad/infra)."""
        from src.agents.ops_scanner import OpsScanner
        out: list[dict] = []
        for p in await OpsScanner().scan(period_days=period_days):
            out.append({
                "title": p.title, "description": p.description,
                "impact": p.impact, "area": p.area, "evidence": p.evidence,
                "source": "ops_scanner", "suggested_story": p.suggested_story,
            })
        return out

    async def _memory_scanner_proposals(self) -> list[dict]:
        """MemoryScanner — Jean Grey now *proposes* from vault health."""
        from src.agents.jean_grey import JeanGrey
        out: list[dict] = []
        for p in await JeanGrey().scan_proposals():
            out.append({
                "title": p.title, "description": p.description,
                "impact": p.impact, "area": p.area, "evidence": p.evidence,
                "source": "memory_scanner", "suggested_story": p.suggested_story,
            })
        return out

    async def _vault_scanner_proposals(self) -> list[dict]:
        """VaultScanner — lê CONTEÚDO das notas do vault e extrai sinais
        acionáveis (TODOs, FIXMEs, ADRs em proposta, "deveria/falta").
        Complementa o MemoryScanner que só vê health (links/duplicados)."""
        try:
            from src.services.vault_scanner import scan_proposals as _vs
            return _vs(max_proposals=30)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mekka] vault_scanner failed (non-fatal): {exc}")
            return []

    async def _agents_scanner_proposals(self) -> list[dict]:
        """AgentsScanner — vertical para `src/agents/`."""
        return self._run_vertical_scanner("agents_scanner",
                                          "src.agents.agents_scanner", max_n=20)

    async def _backend_scanner_proposals(self) -> list[dict]:
        """BackendScanner — vertical para `src/services/` e `src/models/`."""
        return self._run_vertical_scanner("backend_scanner",
                                          "src.agents.backend_scanner", max_n=15)

    async def _frontend_scanner_proposals(self) -> list[dict]:
        """FrontendScanner — vertical para `src/dashboard/static/`."""
        return self._run_vertical_scanner("frontend_scanner",
                                          "src.agents.frontend_scanner", max_n=15)

    async def _dashboard_scanner_proposals(self) -> list[dict]:
        """DashboardScanner — vertical para `src/dashboard/` (Python backend)."""
        return self._run_vertical_scanner("dashboard_scanner",
                                          "src.agents.dashboard_scanner", max_n=15)

    def _run_vertical_scanner(
        self, source_name: str, module_path: str, max_n: int = 15,
    ) -> list[dict]:
        """Roda um scanner vertical e converte propostas para o formato do
        council. DRY — vale pra todos os scanners verticais
        (agents/backend/frontend/dashboard)."""
        try:
            import importlib
            mod = importlib.import_module(module_path)
            raw = mod.scan_proposals(max_proposals=max_n)
            out = []
            for p in raw:
                out.append({
                    "title": p.title,
                    "description": p.description,
                    "impact": p.impact,
                    "area": p.area,
                    "evidence": p.evidence,
                    "source": source_name,
                    "suggested_story": p.suggested_story,
                })
            return out
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mekka] {source_name} failed (non-fatal): {exc}")
            return []

    async def _ice_man_proposals(self) -> list[dict]:
        """Ice Man — external research scanner (dependency freshness/CVEs)."""
        from src.agents.ice_man import IceMan
        out: list[dict] = []
        for p in await IceMan().scan():
            out.append({
                "title": p.title, "description": p.description,
                "impact": p.impact, "area": p.area, "evidence": p.evidence,
                "source": "ice_man", "suggested_story": p.suggested_story,
            })
        return out

    async def _sage_proposals(self) -> list[dict]:
        """Sage — measurement loop (regression detection vs baseline)."""
        from src.agents.sage import Sage
        out: list[dict] = []
        for p in await Sage().scan():
            out.append({
                "title": p.title, "description": p.description,
                "impact": p.impact, "area": p.area, "evidence": p.evidence,
                "source": "sage", "suggested_story": p.suggested_story,
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

    @staticmethod
    def _preview_rec_id(p: dict) -> str:
        """Mesma fórmula de `_rec_id` mas a partir do proposal raw (sem
        passar por `_consolidate`). Usado pra checar rejection memory."""
        title = str(p.get("title") or "Proposta")
        area = str(p.get("area") or "infra").lower()
        return hashlib.sha256(f"{area}::{title}".encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokens normalizados para Jaccard (sem dependência externa).
        Lowercase + alfanumérico + dedup; remove stopwords mínimas."""
        import re
        STOP = {
            "the", "a", "an", "o", "a", "os", "as", "de", "da", "do",
            "em", "para", "por", "com", "que", "é", "ser", "ter",
            "and", "or", "of", "to", "in", "for", "with", "as", "on", "at",
            "vault", "memory", "agent", "agente",  # palavras quase universais nos titles
        }
        tokens = re.findall(r"[a-z0-9_]{3,}", (text or "").lower())
        return {t for t in tokens if t not in STOP}

    @classmethod
    def _jaccard(cls, a: str, b: str) -> float:
        ta, tb = cls._tokenize(a), cls._tokenize(b)
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        union = len(ta | tb)
        return inter / union if union else 0.0

    @classmethod
    def _dedup_semantic(
        cls, proposals: list[dict], threshold: float = 0.6
    ) -> list[dict]:
        """Remove proposals com Jaccard >= threshold contra alguma já mantida.
        Preserva ordem e o primeiro de cada cluster (geralmente o de fonte mais
        confiável vinda primeiro). Compara title+description."""
        kept: list[dict] = []
        for p in proposals:
            text_p = (str(p.get("title", "")) + " " + str(p.get("description", "")))
            duplicate = False
            for q in kept:
                text_q = (str(q.get("title", "")) + " " + str(q.get("description", "")))
                if cls._jaccard(text_p, text_q) >= threshold:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(p)
        return kept

    def _chronically_rejected_ids(self, min_rejections: int = 2) -> set[str]:
        """rec_ids que aparecem como 'rejected' >= N vezes no histórico.
        Hoje `decisions.json` tem 1 entry por rec_id (último estado), então
        usamos o fato de que 'rejected' significa o operador escolheu não
        manter. Em iteração futura podemos manter contador de rejections
        em entry separada."""
        decisions = self._load_decisions()
        rejected = {rec_id for rec_id, v in decisions.items()
                    if v.get("status") == "rejected"}
        return rejected

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

    def record_decision(
        self, rec_id: str, status: str, rec: dict | None = None
    ) -> bool:
        """Persist an operator accept/reject. Returns True on success.

        ``status`` must be 'accepted' or 'rejected' (or 'pending' to reset).

        When ``status == 'accepted'`` and a ``rec`` dict is provided, a
        structured dev brief is enqueued for the AIOS dev-squad via
        :func:`src.services.improvement_queue.enqueue_brief`. The enqueue is
        best-effort and never affects the decision's success status.
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
        except OSError as exc:
            self._log.warning(f"[Mekka] could not persist decision: {exc}")
            return False

        # On accept, enqueue a dev brief (lazy import to avoid import cycles).
        if status == "accepted" and rec is not None:
            try:
                from src.services import improvement_queue
                improvement_queue.enqueue_brief(rec)
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"[Mekka] could not enqueue brief: {exc}")

            # P0.3 — Bridge hook: snapshot Sage BEFORE para attribution.
            # Fire-and-forget; nunca afeta retorno. Pre-2026-05-27: silent debug
            # ocultou que aceitações em handlers HTTP nunca disparavam o snapshot
            # (DeprecationWarning + RuntimeError em get_event_loop sem loop ativo).
            # Agora: tenta running-loop, depois novo thread com asyncio.run().
            try:
                import asyncio
                import threading
                from src.services.improvement_memory_bridge import on_improvement_accepted
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(on_improvement_accepted(rec_id))
                except RuntimeError:
                    # Sem event-loop ativo (ex: CLI). Roda em thread dedicada
                    # para não criar loop no thread principal.
                    def _run_bridge() -> None:
                        try:
                            asyncio.run(on_improvement_accepted(rec_id))
                        except Exception as inner_exc:  # noqa: BLE001
                            self._log.warning(
                                f"[Mekka] bridge on_accepted thread failed: {inner_exc}"
                            )
                    threading.Thread(
                        target=_run_bridge, name=f"bridge-accept-{rec_id[:8]}", daemon=True
                    ).start()
            except Exception as exc:  # noqa: BLE001
                # Warning (não debug) porque silence quebrou o loop inteiro
                self._log.warning(f"[Mekka] bridge on_accepted no-op: {exc}")

            # Write-back loop — opt-in: registra IMP aceita no daily do vault
            # canônico. Apenas escreve se IMPROVEMENT_VAULT_WRITER_ENABLED=true.
            # Fail-silent + throttled internamente — nunca afeta retorno.
            try:
                from src.services import improvement_vault_writer
                if improvement_vault_writer.is_writer_enabled():
                    written = improvement_vault_writer.append_accepted_daily(rec)
                    if written:
                        self._log.info(
                            f"[Mekka] IMP-{rec_id} → vault daily: {written.name}"
                        )
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"[Mekka] vault writer (accepted) no-op: {exc}")

        return True

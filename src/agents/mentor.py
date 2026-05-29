"""
src/agents/mentor.py
====================
Mentor — Charles Xavier (T1 fix, 2026-05-25).

Closes the learning loop that Beast left open. Beast produces English-language
ImprovementProposals and emits them to Telegram for a human to read. Mentor
goes one step further: it reads RESOLVED agent_memories (WIN/LOSS/NEUTRAL),
recent Batman rejections, and Beast proposals, and distills them into
**typed parameter suggestions** — concrete deltas to settings (e.g.
"raise min_confidence from 0.65 to 0.70 because win_rate=22% in last 14
trades").

Hard rules
----------
  • READ-ONLY by default. Mentor NEVER mutates settings.py.
  • Output is a list[ParameterSuggestion] with `can_auto_apply` flag.
  • Each suggestion has evidence (numbers backing the proposal) so the
    operator can sanity-check before applying.
  • Conservative: bias toward TIGHTENING risk (raise gates, lower size)
    over loosening it. Loosening always requires can_auto_apply=False.
  • Fails silently — never blocks any other cycle.

Background — `~/.claude/projects/.../memory/project-memory-orphan-writers.md`:
The 4 memory writer gaps were fixed in 2026-05-25 (commit 57bdc96), so for
the first time Mentor has actual resolved outcomes to learn from. Before
this, agent_memories had 0 resolved rows.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.base import BaseAgent


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ParameterSuggestion:
    """A concrete parameter delta backed by evidence.

    Use `to_env_line()` to get an env override line ready to paste into
    `.env`. The operator owns the final apply — Mentor only proposes.
    """

    parameter_name: str          # settings field name, e.g. "min_confidence"
    current_value: Any           # current value as observed
    suggested_value: Any         # the new value Mentor recommends
    direction: str               # "tighten" | "loosen" | "shift"
    reason: str                  # human-readable why
    evidence: dict[str, Any]     # supporting numbers (win_rate, n, period, ...)
    confidence: float = 0.5      # Mentor's confidence in this suggestion [0.0, 1.0]
    can_auto_apply: bool = False # True only when tightening + high confidence
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_env_line(self) -> str:
        """Produces something like ``MEKKA_MIN_CONFIDENCE=0.70``."""
        env_name = f"MEKKA_{self.parameter_name.upper()}"
        return f"{env_name}={self.suggested_value}"

    def to_dict(self) -> dict:
        return {
            "parameter_name": self.parameter_name,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "direction": self.direction,
            "reason": self.reason,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 3),
            "can_auto_apply": self.can_auto_apply,
            "env_override": self.to_env_line(),
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class MentorReport:
    """A bundle of suggestions + observation summary."""

    generated_at: datetime
    suggestions: list[ParameterSuggestion]
    observation_summary: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return len(self.suggestions) == 0

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "suggestions": [s.to_dict() for s in self.suggestions],
            "observation_summary": self.observation_summary,
        }


# ---------------------------------------------------------------------------
# Heuristic thresholds — easy to tune as the system learns
# ---------------------------------------------------------------------------

_MIN_TRADES_FOR_LEARNING = 8           # below this, Mentor stays silent
_LOW_WIN_RATE_THRESHOLD = 0.35         # < 35% triggers tighten suggestion
_HIGH_WIN_RATE_THRESHOLD = 0.65        # > 65% with N≥20 triggers loosen suggestion
_RECENT_REJECTIONS_WINDOW = 30         # last N Batman gate events
_HIGH_REJECTION_RATE = 0.80            # > 80% rejections → suggest loosening gates
_CONFIDENCE_STEP = 0.05                # how much to raise min_confidence per nudge
_DD_NEAR_LIMIT_RATIO = 0.7             # if dd ≥ 70% of limit → suggest tighter cap


# ---------------------------------------------------------------------------
# Mentor agent
# ---------------------------------------------------------------------------


class Mentor(BaseAgent[MentorReport]):
    """Charles Xavier — pattern distiller and parameter-delta proposer.

    Usage:
        report = await Mentor().run()
        for s in report.suggestions:
            print(s.to_dict())
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Mentor",
            role="Charles Xavier — distills resolved outcomes into parameter deltas",
        )

    async def _run(self) -> MentorReport:  # type: ignore[override]
        suggestions: list[ParameterSuggestion] = []
        summary: dict[str, Any] = {
            "resolved_outcomes": 0,
            "rejections_observed": 0,
        }

        # ── 1. Win-rate based confidence calibration ────────────────────
        try:
            wr_data = await self._collect_winrate_evidence()
            summary["resolved_outcomes"] = wr_data.get("n", 0)
            summary["win_rate"] = wr_data.get("win_rate")
            s = self._suggest_min_confidence_from_winrate(wr_data)
            if s is not None:
                suggestions.append(s)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mentor] win-rate analysis skipped: {exc}")

        # ── 2. Rejection-rate based gate calibration ────────────────────
        try:
            rej_data = await self._collect_rejection_evidence()
            summary["rejections_observed"] = rej_data.get("n", 0)
            summary["rejection_rate"] = rej_data.get("rejection_rate")
            s = self._suggest_from_rejection_rate(rej_data)
            if s is not None:
                suggestions.append(s)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mentor] rejection analysis skipped: {exc}")

        # ── 3. Drawdown proximity → tighter daily cap ───────────────────
        try:
            dd_data = await self._collect_drawdown_evidence()
            summary["drawdown_today_pct"] = dd_data.get("drawdown_pct")
            s = self._suggest_drawdown_tightening(dd_data)
            if s is not None:
                suggestions.append(s)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Mentor] drawdown analysis skipped: {exc}")

        report = MentorReport(
            generated_at=datetime.now(timezone.utc),
            suggestions=suggestions,
            observation_summary=summary,
        )

        # Best-effort audit so the dashboard can show the history.
        try:
            await self._audit_suggestions(report)
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[Mentor] audit skipped: {exc}")

        return report

    # ── Evidence collectors ───────────────────────────────────────────

    async def _collect_winrate_evidence(self) -> dict[str, Any]:
        """Pull resolved (non-PENDING) agent_memories and compute win rate."""
        from sqlalchemy import select  # noqa: WPS433

        from src.persistence.db import get_session  # noqa: WPS433
        from src.persistence.models import AgentMemoryRecord  # noqa: WPS433

        out: dict[str, Any] = {"n": 0, "wins": 0, "losses": 0, "neutral": 0, "win_rate": None}
        try:
            async with get_session() as session:
                stmt = (
                    select(AgentMemoryRecord)
                    .where(AgentMemoryRecord.outcome.in_(("WIN", "LOSS", "NEUTRAL")))
                    .order_by(AgentMemoryRecord.timestamp.desc())
                    .limit(100)
                )
                rows = (await session.execute(stmt)).scalars().all()
        except Exception:  # noqa: BLE001
            return out
        counts = Counter((r.outcome or "").upper() for r in rows)
        wins = counts.get("WIN", 0)
        losses = counts.get("LOSS", 0)
        neutral = counts.get("NEUTRAL", 0)
        n = wins + losses + neutral
        out.update({"n": n, "wins": wins, "losses": losses, "neutral": neutral})
        if (wins + losses) > 0:
            out["win_rate"] = wins / (wins + losses)
        return out

    async def _collect_rejection_evidence(self) -> dict[str, Any]:
        """Pull recent Batman RISK_REJECTED events and compute rate."""
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        out: dict[str, Any] = {"n": 0, "rejected": 0, "rejection_rate": None}
        try:
            audits = await MekkaRepository.list_recent_audit(limit=200)
        except Exception:  # noqa: BLE001
            return out
        relevant = [
            r for r in audits or []
            if (r.event or "") in ("RISK_REJECTED", "SIGNAL_FLIP", "TRADE_NOW_EXECUTED")
        ]
        n = min(len(relevant), _RECENT_REJECTIONS_WINDOW)
        if n == 0:
            return out
        sample = relevant[:n]
        rejected = sum(1 for r in sample if (r.event or "") == "RISK_REJECTED")
        out.update({"n": n, "rejected": rejected, "rejection_rate": rejected / n})
        return out

    async def _collect_drawdown_evidence(self) -> dict[str, Any]:
        """Read today's drawdown vs the configured daily limit."""
        from src.config.settings import settings  # noqa: WPS433
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        out: dict[str, Any] = {"drawdown_pct": None, "limit_pct": None}
        try:
            dd = float(await MekkaRepository.get_today_drawdown_pct() or 0.0)
        except Exception:  # noqa: BLE001
            return out
        limit = float(getattr(settings, "max_daily_drawdown_pct", 0.10) or 0.10)
        out.update({"drawdown_pct": dd, "limit_pct": limit})
        return out

    # ── Suggestion synthesizers ───────────────────────────────────────

    def _suggest_min_confidence_from_winrate(
        self, wr: dict[str, Any]
    ) -> Optional[ParameterSuggestion]:
        from src.config.settings import settings  # noqa: WPS433

        n = wr.get("n", 0)
        wr_rate = wr.get("win_rate")
        if n < _MIN_TRADES_FOR_LEARNING or wr_rate is None:
            return None
        current = float(getattr(settings, "min_confidence", 0.65) or 0.65)

        if wr_rate < _LOW_WIN_RATE_THRESHOLD:
            new = round(min(current + _CONFIDENCE_STEP, 0.95), 2)
            if new == current:
                return None
            conf = min(0.95, 0.4 + (n / 50.0))  # more samples = more confidence
            return ParameterSuggestion(
                parameter_name="min_confidence",
                current_value=current,
                suggested_value=new,
                direction="tighten",
                reason=(
                    f"Win rate {wr_rate:.0%} em {n} trades resolvidos está abaixo "
                    f"de {_LOW_WIN_RATE_THRESHOLD:.0%}. Aumentar min_confidence "
                    f"força Vision a só agir com sinais mais fortes."
                ),
                evidence=wr,
                confidence=round(conf, 2),
                can_auto_apply=True,  # tightening is always safe
            )

        if wr_rate > _HIGH_WIN_RATE_THRESHOLD and n >= 20:
            new = round(max(current - _CONFIDENCE_STEP, 0.50), 2)
            if new == current:
                return None
            return ParameterSuggestion(
                parameter_name="min_confidence",
                current_value=current,
                suggested_value=new,
                direction="loosen",
                reason=(
                    f"Win rate {wr_rate:.0%} em {n} trades resolvidos é forte. "
                    f"Reduzir min_confidence em {_CONFIDENCE_STEP} captura mais "
                    f"oportunidades — APROVAÇÃO HUMANA recomendada antes de aplicar."
                ),
                evidence=wr,
                confidence=0.4,
                can_auto_apply=False,  # loosening always needs human review
            )

        return None

    def _suggest_from_rejection_rate(
        self, rej: dict[str, Any]
    ) -> Optional[ParameterSuggestion]:
        """If Batman is rejecting almost everything, gates may be too tight
        for current market — surface for human review (never auto-loosens)."""
        n = rej.get("n", 0)
        rate = rej.get("rejection_rate")
        if n < _MIN_TRADES_FOR_LEARNING or rate is None:
            return None
        if rate < _HIGH_REJECTION_RATE:
            return None
        from src.config.settings import settings  # noqa: WPS433

        current = float(getattr(settings, "min_confidence", 0.65) or 0.65)
        new = round(max(current - _CONFIDENCE_STEP, 0.50), 2)
        if new == current:
            return None
        return ParameterSuggestion(
            parameter_name="min_confidence",
            current_value=current,
            suggested_value=new,
            direction="loosen",
            reason=(
                f"Batman rejeitou {rej['rejected']}/{n} sinais recentes "
                f"({rate:.0%}). Gates podem estar apertados para o regime atual. "
                f"Revise manualmente — Mentor não solta gates automaticamente."
            ),
            evidence=rej,
            confidence=0.35,
            can_auto_apply=False,
        )

    def _suggest_drawdown_tightening(
        self, dd: dict[str, Any]
    ) -> Optional[ParameterSuggestion]:
        ratio = 0.0
        limit = dd.get("limit_pct")
        current_dd = dd.get("drawdown_pct")
        if not limit or current_dd is None or limit <= 0:
            return None
        ratio = current_dd / limit
        if ratio < _DD_NEAR_LIMIT_RATIO:
            return None
        new_limit = round(max(limit * 0.5, 0.02), 4)
        if new_limit >= limit:
            return None
        return ParameterSuggestion(
            parameter_name="max_daily_drawdown_pct",
            current_value=limit,
            suggested_value=new_limit,
            direction="tighten",
            reason=(
                f"Drawdown hoje {current_dd:.2%} está em {ratio:.0%} do limite "
                f"({limit:.2%}). Apertar o cap diário evita que uma sequência "
                f"ruim consuma todo o teto antes do operador notar."
            ),
            evidence=dd,
            confidence=0.7,
            can_auto_apply=True,  # tightening risk caps is safe
        )

    # ── Audit ─────────────────────────────────────────────────────────

    async def _audit_suggestions(self, report: MentorReport) -> None:
        # INV-11 (2026-05-29): emite SEMPRE um evento ao rodar — antes só
        # logávamos quando havia sugestão, então auditoria via audit_log
        # mostrava 0 eventos em 7 dias mesmo com Mentor rodando. Agora:
        #   - MENTOR_SUGGESTED (INFO) → quando há sugestões
        #   - MENTOR_RAN (DEBUG)       → quando rodou e não tinha o que sugerir
        # Ambos carregam o observation_summary pro dashboard refletir saúde.
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        if report.is_empty:
            try:
                await MekkaRepository.log_event(
                    agent="Mentor",
                    event="MENTOR_RAN",
                    severity="DEBUG",
                    message=(
                        f"Mentor rodou sem sugestões (obs: {report.observation_summary})"
                    ),
                    payload={
                        "observation": report.observation_summary,
                        "n_suggestions": 0,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                self._log.debug(f"[Mentor] MENTOR_RAN emit skipped: {exc}")
            return

        await MekkaRepository.log_event(
            agent="Mentor",
            event="MENTOR_SUGGESTED",
            severity="INFO",
            message=(
                f"Mentor propôs {len(report.suggestions)} ajuste(s) de parâmetro "
                f"(obs: {report.observation_summary})"
            ),
            payload={
                "suggestions": [s.to_dict() for s in report.suggestions],
                "observation": report.observation_summary,
            },
        )

        # P1.8 (2026-05-27) — Mentor → IMP automático.
        # Suggestions com can_auto_apply=True E confidence>=0.7 viram entry
        # no inbox.json (visível no próximo Mekka._run como proposal).
        # Fechamos o gap: ParameterSuggestion deixa de ser uma ilha
        # (Telegram only) e entra no governance via Mekka council.
        # Fail-silent — nunca afeta o ciclo do Mentor.
        try:
            high_conf_auto = [
                s for s in report.suggestions
                if s.can_auto_apply and s.confidence >= 0.7
            ]
            if high_conf_auto:
                self._enqueue_in_inbox(high_conf_auto)
                # Write-back loop: registra cada sugestão high-conf no vault.
                # Opt-in via MENTOR_VAULT_WRITER_ENABLED. Fail-silent.
                try:
                    from src.services import trading_vault_writer as _tvw
                    for s in high_conf_auto:
                        _tvw.record_mentor_suggestion({
                            "target": s.parameter_name,
                            "current_value": s.current_value,
                            "suggested_value": s.suggested_value,
                            "confidence": s.confidence,
                            "n_samples": s.evidence_n,
                            "reason": s.rationale,
                            "metric": getattr(s, "metric", "win_rate"),
                            "scope": getattr(s, "scope", "global"),
                            "can_auto_apply": s.can_auto_apply,
                        })
                except Exception as exc_vault:  # noqa: BLE001
                    import logging
                    logging.getLogger("mekka.mentor").debug(
                        f"[Mentor] vault writer no-op: {exc_vault}"
                    )
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger("mekka.mentor").debug(
                f"[Mentor] inbox enqueue no-op: {exc}"
            )

    @staticmethod
    def _enqueue_in_inbox(suggestions: list) -> int:
        """Adiciona suggestions ao data/improvement_inbox.json.
        Cada uma vira uma proposal-shaped dict pro Mekka council.
        Idempotente: dedup por parameter_name (mantém o mais recente)."""
        import json
        from pathlib import Path
        from datetime import datetime, timezone

        inbox = Path(__file__).resolve().parents[2] / "data" / "improvement_inbox.json"
        try:
            inbox.parent.mkdir(parents=True, exist_ok=True)
            current = []
            if inbox.exists():
                try:
                    current = json.loads(inbox.read_text(encoding="utf-8")) or []
                except Exception:  # noqa: BLE001
                    current = []
            # Dedup por parameter_name
            existing_params = {
                e.get("parameter_name") for e in current
                if e.get("source") == "mentor"
            }
            added = 0
            for s in suggestions:
                if s.parameter_name in existing_params:
                    continue
                current.append({
                    "title": (
                        f"Mentor: {s.parameter_name} "
                        f"{s.current_value} → {s.suggested_value}"
                    ),
                    "description": s.rationale,
                    "impact": "MEDIUM" if s.confidence >= 0.8 else "LOW",
                    "area": "calibration",
                    "evidence": (
                        f"win_rate, n={s.evidence_n}, period={s.evidence_period}, "
                        f"mentor_conf={s.confidence:.2f}"
                    ),
                    "source": "mentor",
                    "suggested_story": f"Aplicar {s.parameter_name}={s.suggested_value}",
                    "parameter_name": s.parameter_name,
                    "env_line": s.to_env_line(),
                    "_mentor_ts": datetime.now(timezone.utc).isoformat(),
                })
                added += 1
            if added > 0:
                inbox.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
            return added
        except OSError:
            return 0

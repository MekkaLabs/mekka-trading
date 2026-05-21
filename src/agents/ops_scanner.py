"""
src/agents/ops_scanner.py
=========================
OpsScanner — Continuous Improvement Department, dev-squad/infra scanner.

Read-only, fail-silent auditor of *operational health* from the audit stream
and the runtime log. Surfaces stability proposals:

  • Recurring errors  — ERROR/CRITICAL events clustered by agent+event
  • Agent failures    — CYCLE_ERROR / agent crashes in the window
  • Log exceptions    — repeated tracebacks in the dashboard runtime log

Never restarts services or mutates state — it only reads and proposes.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.ops_scanner")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_CANDIDATES = (
    _REPO_ROOT / "logs" / "dashboard_runtime.log",
    Path("/tmp/mekka_dashboard.log"),
)
_LOG_TAIL_BYTES = 400_000  # only scan the recent tail


def _aware(dt) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class OpsScanner:
    """Ops/infra scanner. ``proposals = await OpsScanner().scan()``."""

    async def scan(self, period_days: int = 7) -> list[ImprovementProposal]:
        out: list[ImprovementProposal] = []
        for fn in (self._scan_audit_errors, self._scan_agent_failures, self._scan_log_exceptions):
            try:
                out.extend(await fn(period_days))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[OpsScanner] %s failed: %s", getattr(fn, "__name__", fn), exc)
        return out

    async def _recent_events(self, period_days: int):
        from src.persistence.repository import MekkaRepository  # noqa: WPS433
        rows = await MekkaRepository.list_recent_audit(limit=1000)
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        return [r for r in rows if r.timestamp and (_aware(r.timestamp) or cutoff) >= cutoff]

    async def _scan_audit_errors(self, period_days: int) -> list[ImprovementProposal]:
        events = await self._recent_events(period_days)
        clusters: Counter = Counter()
        for r in events:
            sev = (r.severity or "").upper()
            if sev not in ("ERROR", "CRITICAL"):
                continue
            clusters[f"{r.agent}:{r.event}"] += 1
        if not clusters:
            return []
        out: list[ImprovementProposal] = []
        for key, n in clusters.most_common(3):
            if n < 3:
                continue
            agent, _, event = key.partition(":")
            out.append(ImprovementProposal(
                title=f"Erro recorrente: {agent}/{event} ({n}×)",
                description=(
                    f"O evento {event} do agente {agent} ocorreu {n}× como ERROR/CRITICAL "
                    "no período. Erros recorrentes corroem confiabilidade — investigar e tratar."
                ),
                impact="HIGH" if n >= 10 else "MEDIUM",
                area="infra",
                evidence=f"{agent}/{event}: {n} ocorrências ERROR/CRITICAL em {period_days}d.",
                suggested_story=f"Tratar erro recorrente {agent}/{event}",
            ))
        return out

    async def _scan_agent_failures(self, period_days: int) -> list[ImprovementProposal]:
        events = await self._recent_events(period_days)
        fails: Counter = Counter()
        for r in events:
            if (r.event or "").upper() == "CYCLE_ERROR":
                fails[r.agent or "?"] += 1
        if not fails:
            return []
        agent, n = fails.most_common(1)[0]
        if n < 3:
            return []
        return [ImprovementProposal(
            title=f"Agente {agent} falhou {n}× no ciclo",
            description=(
                f"{agent} acumulou {n} CYCLE_ERROR no período. Estabilizar o agente "
                "(timeouts, validação de entrada, fail-safe) para não degradar o ciclo."
            ),
            impact="MEDIUM",
            area="backend",
            evidence=f"{agent}: {n} CYCLE_ERROR em {period_days}d.",
            suggested_story=f"Estabilizar {agent} contra CYCLE_ERROR",
        )]

    async def _scan_log_exceptions(self, period_days: int) -> list[ImprovementProposal]:
        log_path = next((p for p in _LOG_CANDIDATES if p.exists()), None)
        if log_path is None:
            return []
        try:
            size = log_path.stat().st_size
            with log_path.open("r", encoding="utf-8", errors="ignore") as fh:
                if size > _LOG_TAIL_BYTES:
                    fh.seek(size - _LOG_TAIL_BYTES)
                text = fh.read()
        except OSError:
            return []
        # Count distinct exception types in tracebacks.
        exc_types: Counter = Counter()
        for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_.]*Error|.*Exception):", text, re.MULTILINE):
            exc_types[m.group(1).split(".")[-1]] += 1
        if not exc_types:
            return []
        top, n = exc_types.most_common(1)[0]
        if n < 3:
            return []
        return [ImprovementProposal(
            title=f"Exceção recorrente no log: {top} ({n}×)",
            description=(
                f"`{log_path.name}` registra {top} {n}× no trecho recente. "
                "Tratar a causa raiz reduz ruído e risco operacional."
            ),
            impact="MEDIUM" if n < 10 else "HIGH",
            area="infra",
            evidence=f"{top}: {n} ocorrências no tail de {log_path.name}.",
            suggested_story=f"Tratar exceção {top} no runtime",
        )]

"""
src/agents/sage.py
==================
Sage — Continuous Improvement Department, measurement loop.

Sage (Tessa) is the X-Man whose mind works like a computer, continuously
computing statistics. Here she **closes the loop** of the department: instead
of only proposing changes, she *measures whether the system is getting better
or worse over time* and feeds that back as evidence.

How it works (v1 — system-level baseline tracking):
  1. Each run, snapshot key health metrics (win rate, profit factor, errors in
     the last 24h, closed-trade count) into ``data/sage_baselines.json``.
  2. Compare the current snapshot to the recent baseline (mean of prior runs).
  3. Emit an ``ImprovementProposal`` when a metric **regresses** beyond a
     threshold — so the council sees "we got worse" with hard numbers.
  4. Expose a department KPI summary via ``kpi()`` (proposals accepted/delivered).

Read-only w.r.t. the trading system; the only file it writes is its own
baseline history under ``data/``. Fail-silent — never raises.

Future extension (design §4): attribute baselines to *specific delivered
improvements* (before/after a given change) rather than system-wide.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.sage")

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_BASELINES_FILE = _DATA_DIR / "sage_baselines.json"
_DECISIONS_FILE = _DATA_DIR / "improvement_decisions.json"
_MAX_SNAPSHOTS = 200
_WINRATE_DROP_PP = 10.0     # percentage points
_ERROR_SPIKE_MULT = 2.0     # current errors >= mult × baseline mean
_MIN_CLOSED_FOR_WR = 10


def _aware(dt) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Sage:
    """Measurement-loop agent. ``proposals = await Sage().scan()``."""

    async def scan(self) -> list[ImprovementProposal]:
        try:
            snap = await self._snapshot()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Sage] snapshot failed: %s", exc)
            return []
        history = self._load_history()
        proposals = self._detect_regressions(snap, history)
        # Persist AFTER comparing so we compare against prior runs only.
        self._append(history, snap)
        return proposals

    # ------------------------------------------------------------------
    # Metric snapshot
    # ------------------------------------------------------------------
    async def _snapshot(self) -> dict:
        from src.persistence.repository import MekkaRepository  # noqa: WPS433
        now = datetime.now(timezone.utc)

        # Trade outcomes (closed trades carry pnl_usd).
        wins = losses = 0
        gross_win = gross_loss = 0.0
        try:
            trades = await MekkaRepository.list_recent_trades(limit=200)
            for t in trades:
                pnl = getattr(t, "pnl_usd", None)
                if pnl is None:
                    continue
                if pnl >= 0:
                    wins += 1
                    gross_win += pnl
                else:
                    losses += 1
                    gross_loss += abs(pnl)
        except Exception:  # noqa: BLE001
            pass
        closed = wins + losses
        win_rate = (wins / closed * 100.0) if closed else None
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None

        # Errors in the last 24h.
        errors_24h = 0
        try:
            rows = await MekkaRepository.list_recent_audit(limit=1000)
            cutoff = now - timedelta(hours=24)
            for r in rows:
                if (r.severity or "").upper() not in ("ERROR", "CRITICAL"):
                    continue
                ts = _aware(r.timestamp)
                if ts and ts >= cutoff:
                    errors_24h += 1
        except Exception:  # noqa: BLE001
            pass

        return {
            "ts": now.isoformat(),
            "win_rate": round(win_rate, 2) if win_rate is not None else None,
            "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
            "closed_trades": closed,
            "errors_24h": errors_24h,
        }

    # ------------------------------------------------------------------
    # Regression detection vs recent baseline
    # ------------------------------------------------------------------
    def _detect_regressions(self, snap: dict, history: list[dict]) -> list[ImprovementProposal]:
        prior = history[-5:]  # recent baseline window
        if not prior:
            return []  # first run — only establish the baseline
        out: list[ImprovementProposal] = []

        # Win-rate regression
        wr_prior = [s["win_rate"] for s in prior if s.get("win_rate") is not None]
        if snap.get("win_rate") is not None and wr_prior and snap.get("closed_trades", 0) >= _MIN_CLOSED_FOR_WR:
            base = sum(wr_prior) / len(wr_prior)
            if base - snap["win_rate"] >= _WINRATE_DROP_PP:
                out.append(ImprovementProposal(
                    title=f"Regressão de win rate: {base:.0f}% → {snap['win_rate']:.0f}%",
                    description=(
                        "O win rate caiu vs. a linha de base recente. Investigar mudanças "
                        "recentes (sinal/execução/risco) que possam ter degradado o resultado."
                    ),
                    impact="HIGH",
                    area="measurement",
                    evidence=f"baseline {base:.1f}% → atual {snap['win_rate']:.1f}% ({snap['closed_trades']} trades fechados).",
                    suggested_story="Investigar regressão de win rate (medição Sage)",
                ))

        # Error spike
        err_prior = [s.get("errors_24h", 0) for s in prior]
        base_err = (sum(err_prior) / len(err_prior)) if err_prior else 0.0
        if snap.get("errors_24h", 0) >= 5 and base_err > 0 and snap["errors_24h"] >= _ERROR_SPIKE_MULT * base_err:
            out.append(ImprovementProposal(
                title=f"Pico de erros: {snap['errors_24h']} em 24h (base {base_err:.0f})",
                description=(
                    "Erros/críticos nas últimas 24h subiram bem acima da base. "
                    "Estabilidade degradou — investigar a causa recente."
                ),
                impact="MEDIUM",
                area="measurement",
                evidence=f"errors_24h={snap['errors_24h']} vs baseline média {base_err:.1f}.",
                suggested_story="Investigar pico de erros (medição Sage)",
            ))
        return out

    # ------------------------------------------------------------------
    # Department KPI (for dashboards / reporting)
    # ------------------------------------------------------------------
    def kpi(self) -> dict:
        """Lightweight department throughput KPI from the operator decisions."""
        out = {"accepted": 0, "rejected": 0, "pending": 0, "total_decided": 0}
        try:
            if _DECISIONS_FILE.exists():
                decisions = json.loads(_DECISIONS_FILE.read_text(encoding="utf-8")) or {}
                for v in decisions.values():
                    st = (v or {}).get("status", "pending")
                    if st in out:
                        out[st] += 1
                out["total_decided"] = out["accepted"] + out["rejected"]
        except Exception:  # noqa: BLE001
            pass
        out["acceptance_rate"] = (
            round(out["accepted"] / out["total_decided"] * 100, 1)
            if out["total_decided"] else None
        )
        return out

    # ------------------------------------------------------------------
    # Baseline history persistence
    # ------------------------------------------------------------------
    def _load_history(self) -> list[dict]:
        try:
            if _BASELINES_FILE.exists():
                data = json.loads(_BASELINES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:  # noqa: BLE001
            pass
        return []

    def _append(self, history: list[dict], snap: dict) -> None:
        try:
            history.append(snap)
            if len(history) > _MAX_SNAPSHOTS:
                history = history[-_MAX_SNAPSHOTS:]
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _BASELINES_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Sage] could not persist baseline: %s", exc)

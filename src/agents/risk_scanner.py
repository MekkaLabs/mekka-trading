"""
src/agents/risk_scanner.py
==========================
RiskScanner — Continuous Improvement Department, trading-ops scanner.

Read-only, fail-silent auditor of *risk posture* over the recent window. It
surfaces safety/stability proposals from the audit stream and daily PnL state:

  • Kill switch       — engaged now, or fired repeatedly in the window
  • Daily drawdown    — approaching the configured max_daily_drawdown_pct
  • Batman rejections — which gate rejects most (execution friction vs. real risk)

Never engages/releases the kill switch and never proposes touching the safety
gates (settings.py double-gate, kill switch) — those are L1-L4 protected.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from src.agents.beast import ImprovementProposal
from src.config.settings import settings

logger = logging.getLogger("mekka.risk_scanner")


def _aware(dt) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class RiskScanner:
    """Trading-ops risk scanner. ``proposals = await RiskScanner().scan()``."""

    async def scan(self, period_days: int = 7) -> list[ImprovementProposal]:
        out: list[ImprovementProposal] = []
        for fn in (self._scan_kill_switch, self._scan_drawdown,
                   self._scan_batman_rejections, self._scan_concentration):
            try:
                out.extend(await fn(period_days))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[RiskScanner] %s failed: %s", getattr(fn, "__name__", fn), exc)
        return out

    async def _recent_events(self, period_days: int):
        from src.persistence.repository import MekkaRepository  # noqa: WPS433
        rows = await MekkaRepository.list_recent_audit(limit=1000)
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        return [r for r in rows if r.timestamp and (_aware(r.timestamp) or cutoff) >= cutoff]

    async def _scan_kill_switch(self, period_days: int) -> list[ImprovementProposal]:
        from src.agents.batman import is_kill_switch_active  # noqa: WPS433
        events = await self._recent_events(period_days)
        # Count REAL engages only — an event whose name marks a kill, or whose
        # payload explicitly records kill_switch_engaged=True. (A broad payload
        # substring match over-counts every halted-cycle reference.)
        def _is_real_fire(r) -> bool:
            name = (r.event or "").upper()
            if "KILL" in name:
                return True
            pl = r.payload or {}
            return isinstance(pl, dict) and pl.get("kill_switch_engaged") is True
        ks_events = [r for r in events if _is_real_fire(r)]
        active = False
        try:
            active = is_kill_switch_active()
        except Exception:  # noqa: BLE001
            pass
        if active:
            return [ImprovementProposal(
                title="Kill switch ATIVO — investigar causa raiz",
                description=(
                    "O kill switch está engatado agora. Trading está halted. "
                    "Investigar o gatilho (drawdown/erro) antes de liberar."
                ),
                impact="HIGH",
                area="risk",
                evidence=f"is_kill_switch_active()=True; {len(ks_events)} eventos de kill no período.",
                suggested_story="Diagnosticar e documentar causa do kill switch",
            )]
        if len(ks_events) >= 2:
            return [ImprovementProposal(
                title=f"Kill switch disparou {len(ks_events)}× em {period_days}d",
                description=(
                    "Disparos repetidos do kill switch indicam fragilidade de risco "
                    "ou thresholds mal calibrados. Revisar gatilhos e limites."
                ),
                impact="MEDIUM",
                area="risk",
                evidence=f"{len(ks_events)} eventos de kill switch no período.",
                suggested_story="Revisar calibração dos gatilhos de kill switch",
            )]
        return []

    async def _scan_concentration(self, period_days: int) -> list[ImprovementProposal]:
        """Flag risk concentration: too much equity in one symbol, or high
        aggregate gross exposure vs equity. Read-only snapshot via Portfolio
        Manager; fail-silent (skips if snapshot unavailable)."""
        try:
            from src.agents.portfolio_manager import PortfolioManager  # noqa: WPS433
            snap = await PortfolioManager().run()
        except Exception:  # noqa: BLE001
            return []
        equity = float(getattr(snap, "equity_usd", 0.0) or 0.0)
        positions = list(getattr(snap, "positions", []) or [])
        if equity <= 0 or not positions:
            return []

        notionals: list[tuple[str, float]] = []
        for p in positions:
            notional = abs(float(getattr(p, "size", 0.0) or 0.0)) * float(getattr(p, "entry_price", 0.0) or 0.0)
            if notional > 0:
                notionals.append((getattr(p, "symbol", "?"), notional))
        if not notionals:
            return []

        gross = sum(n for _, n in notionals)
        top_sym, top_n = max(notionals, key=lambda t: t[1])
        top_pct = top_n / equity * 100.0
        gross_pct = gross / equity * 100.0

        # Single-symbol concentration > 50% of equity, or gross exposure > 150%.
        if top_pct >= 50.0:
            return [ImprovementProposal(
                title=f"Concentração: {top_sym} = {top_pct:.0f}% do equity",
                description=(
                    f"A posição em {top_sym} representa {top_pct:.0f}% do equity "
                    f"(${top_n:,.0f} / ${equity:,.0f}). Concentração elevada amplia o "
                    "risco idiossincrático — avaliar diversificação ou redução."
                ),
                impact="HIGH" if top_pct >= 80 else "MEDIUM",
                area="risk",
                evidence=f"{top_sym} notional ${top_n:,.0f} = {top_pct:.1f}% do equity ${equity:,.0f}.",
                suggested_story="Revisar concentração de posição por símbolo",
            )]
        if gross_pct >= 150.0:
            return [ImprovementProposal(
                title=f"Exposição bruta alta: {gross_pct:.0f}% do equity",
                description=(
                    f"Exposição agregada (${gross:,.0f}) é {gross_pct:.0f}% do equity. "
                    "Alavancagem efetiva elevada — avaliar redução de tamanho/posições."
                ),
                impact="MEDIUM",
                area="risk",
                evidence=f"gross ${gross:,.0f} / equity ${equity:,.0f} = {gross_pct:.0f}%.",
                suggested_story="Revisar exposição bruta agregada",
            )]
        return []

    async def _scan_drawdown(self, period_days: int) -> list[ImprovementProposal]:
        from src.persistence.repository import MekkaRepository  # noqa: WPS433
        try:
            dd = float(await MekkaRepository.get_today_drawdown_pct() or 0.0)
        except Exception:  # noqa: BLE001
            return []
        limit = float(getattr(settings, "max_daily_drawdown_pct", 0.10) or 0.10)
        if limit <= 0:
            return []
        ratio = dd / limit
        if ratio < 0.6:
            return []
        impact = "HIGH" if ratio >= 0.85 else "MEDIUM"
        return [ImprovementProposal(
            title=f"Drawdown diário em {dd*100:.1f}% (limite {limit*100:.1f}%)",
            description=(
                "Drawdown do dia próximo do limite de halt. Avaliar redução de "
                "tamanho/exposição ou pausa preventiva antes de bater o teto."
            ),
            impact=impact,
            area="risk",
            evidence=f"drawdown={dd*100:.2f}% / limite={limit*100:.1f}% (uso {ratio*100:.0f}%).",
            suggested_story="Revisar sizing/exposição para folga de drawdown",
        )]

    async def _scan_batman_rejections(self, period_days: int) -> list[ImprovementProposal]:
        events = await self._recent_events(period_days)
        reasons: Counter = Counter()
        total = 0
        for r in events:
            if (r.event or "").upper() != "RISK_REJECTED":
                continue
            payload = r.payload or {}
            rs = payload.get("breached") or payload.get("reasons") or payload.get("reason")
            items = rs if isinstance(rs, list) else ([rs] if rs else [])
            # A HOLD signal is NOT execution friction — Batman correctly does
            # not execute HOLDs. Skip those so they don't masquerade as a risk
            # gate problem (they dominate the count and produce a false signal).
            real = [str(x) for x in items if "HOLD" not in str(x).upper()]
            if not real:
                continue
            total += 1
            for x in real:
                reasons[x] += 1
        if total < 5 or not reasons:
            return []
        top, top_n = reasons.most_common(1)[0]
        if top_n < 3:
            return []
        return [ImprovementProposal(
            title=f"Batman rejeita majoritariamente por '{top}'",
            description=(
                f"De {total} rejeições no período, '{top}' domina ({top_n}×). "
                "Se for fricção de execução (não risco real), recalibrar o gate; "
                "se for risco real, ajustar a geração de sinal a montante."
            ),
            impact="MEDIUM",
            area="risk_gates",
            evidence=f"{total} RISK_REJECTED; top motivo '{top}' = {top_n}×.",
            suggested_story=f"Investigar gate Batman '{top}'",
        )]

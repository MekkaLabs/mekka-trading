"""
src/agents/beast.py
===================
Beast — Continuous System Improvement Agent (Story 248)

Dr. Hank McCoy (Beast) — the brilliant scientist of the X-Men.
Read-only analyst that periodically audits the Mekka Trading system,
identifies improvement opportunities, and sends structured proposals
to the operator via Telegram. Beast NEVER modifies the system directly —
all decisions are made by the human operator.

Responsibilities
----------------
- Analyze recent trade outcomes, PnL, and gate statistics
- Identify patterns: which agents are underperforming, which gates fire too often
- Cross-reference signal quality vs. execution quality
- Propose concrete, actionable improvements (story candidates)
- Send weekly (or on-demand) reports via Telegram

Guiding principles
------------------
1. Read-only: Beast observes, analyzes, proposes — never executes.
2. Evidence-based: every proposal backed by measurable data.
3. Prioritized: proposals ranked by estimated impact (HIGH/MEDIUM/LOW).
4. Non-disruptive: runs out-of-band from the main trading cycle.
5. Fail-silent: any error → log and return empty proposals, never crash.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger

from src.agents.base import BaseAgent
from src.config.settings import settings


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ImprovementProposal:
    """A single, concrete improvement proposal from Beast."""

    title: str
    description: str
    impact: str  # "HIGH" | "MEDIUM" | "LOW"
    area: str    # "signal_quality" | "risk_gates" | "latency" | "ux" | "infra"
    evidence: str
    suggested_story: Optional[str] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_telegram_block(self) -> str:
        impact_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(self.impact, "⚪")
        lines = [
            f"{impact_emoji} *{self.impact}* — {self.title}",
            f"📁 Área: {self.area}",
            f"📝 {self.description}",
            f"📊 Evidência: {self.evidence}",
        ]
        if self.suggested_story:
            lines.append(f"💡 Story sugerida: {self.suggested_story}")
        return "\n".join(lines)


@dataclass
class BeastReport:
    """Full analysis report produced by Beast."""

    generated_at: datetime
    period_days: int
    proposals: list[ImprovementProposal]
    stats_summary: dict[str, Any]
    total_trades_analyzed: int = 0
    system_health_score: float = 0.0  # 0-100

    @property
    def high_priority(self) -> list[ImprovementProposal]:
        return [p for p in self.proposals if p.impact == "HIGH"]

    @property
    def is_empty(self) -> bool:
        return len(self.proposals) == 0


# ---------------------------------------------------------------------------
# Beast agent
# ---------------------------------------------------------------------------

class Beast(BaseAgent[BeastReport]):
    """
    Beast — Continuous System Improvement Analyst.

    Usage (one-shot):
        report = await Beast().run(period_days=7)

    The report contains prioritized ImprovementProposals. Beast also
    sends the report to Telegram automatically if telegram_enabled=True.
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Beast",
            role="Continuous System Improvement Analyst — read-only auditor",
        )

    async def _run(self, period_days: int = 7) -> BeastReport:  # type: ignore[override]
        """
        Analyze the system over the last `period_days` days and return a BeastReport.
        All analysis is read-only. Fails gracefully — returns empty report on error.
        """
        since = datetime.now(timezone.utc) - timedelta(days=period_days)
        proposals: list[ImprovementProposal] = []
        stats: dict[str, Any] = {}
        total_trades = 0

        # ── 1. Audit trade outcomes ────────────────────────────────────────
        try:
            trade_stats = await self._analyze_trades(since)
            stats.update(trade_stats)
            total_trades = trade_stats.get("total_trades", 0)
            proposals.extend(await self._propose_from_trades(trade_stats))
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Beast] Trade audit skipped: {exc}")

        # ── 2. Audit Batman gate firing patterns ──────────────────────────
        try:
            gate_stats = await self._analyze_batman_gates(since)
            stats["gates"] = gate_stats
            proposals.extend(await self._propose_from_gates(gate_stats))
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Beast] Gate audit skipped: {exc}")

        # ── 3. Audit agent latency ─────────────────────────────────────────
        try:
            latency_stats = await self._analyze_latency(since)
            stats["latency"] = latency_stats
            proposals.extend(await self._propose_from_latency(latency_stats))
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Beast] Latency audit skipped: {exc}")

        # ── 4. Audit signal quality (Vision accuracy) ─────────────────────
        try:
            signal_stats = await self._analyze_signal_quality(since)
            stats["signal_quality"] = signal_stats
            proposals.extend(await self._propose_from_signal_quality(signal_stats))
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Beast] Signal quality audit skipped: {exc}")

        # ── Sort by priority ──────────────────────────────────────────────
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        proposals.sort(key=lambda p: priority_order.get(p.impact, 3))

        health_score = self._compute_health_score(stats)

        report = BeastReport(
            generated_at=datetime.now(timezone.utc),
            period_days=period_days,
            proposals=proposals,
            stats_summary=stats,
            total_trades_analyzed=total_trades,
            system_health_score=health_score,
        )

        self._log.info(
            f"[Beast] Analysis complete — {len(proposals)} proposals "
            f"({len(report.high_priority)} HIGH), "
            f"health_score={health_score:.0f}/100, "
            f"trades_analyzed={total_trades}"
        )

        # ── Send to Telegram ──────────────────────────────────────────────
        await self._send_report(report)

        return report

    # -----------------------------------------------------------------------
    # Analysis methods (read-only, all fail-open)
    # -----------------------------------------------------------------------

    async def _analyze_trades(self, since: datetime) -> dict[str, Any]:
        """Query trade history from repository and compute basic PnL stats."""
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433
            trades = await MekkaRepository.get_closed_trades_since(since)
            if not trades:
                return {"total_trades": 0}

            wins = [t for t in trades if getattr(t, "pnl_usd", 0) > 0]
            losses = [t for t in trades if getattr(t, "pnl_usd", 0) <= 0]
            total_pnl = sum(getattr(t, "pnl_usd", 0) for t in trades)
            win_rate = len(wins) / len(trades) if trades else 0.0

            avg_win = (sum(t.pnl_usd for t in wins) / len(wins)) if wins else 0.0
            avg_loss = (sum(t.pnl_usd for t in losses) / len(losses)) if losses else 0.0
            profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

            # Per-symbol breakdown
            symbols: dict[str, dict] = {}
            for t in trades:
                sym = getattr(t, "symbol", "UNKNOWN")
                if sym not in symbols:
                    symbols[sym] = {"count": 0, "pnl": 0.0}
                symbols[sym]["count"] += 1
                symbols[sym]["pnl"] += getattr(t, "pnl_usd", 0)

            return {
                "total_trades": len(trades),
                "win_rate": win_rate,
                "total_pnl_usd": total_pnl,
                "profit_factor": profit_factor,
                "avg_win_usd": avg_win,
                "avg_loss_usd": avg_loss,
                "symbols": symbols,
            }
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[Beast] _analyze_trades error: {exc}")
            return {"total_trades": 0, "error": str(exc)}

    async def _analyze_batman_gates(self, since: datetime) -> dict[str, Any]:
        """Count how often each Batman gate fires (rejects)."""
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433
            events = await MekkaRepository.get_events_since(
                agent="Batman", event="GATE_REJECTED", since=since
            )
            gate_counts: dict[str, int] = {}
            for ev in events:
                payload = getattr(ev, "payload", {}) or {}
                gate_id = payload.get("gate_id", "unknown")
                gate_counts[gate_id] = gate_counts.get(gate_id, 0) + 1

            total_rejections = sum(gate_counts.values())
            return {
                "total_rejections": total_rejections,
                "gate_counts": gate_counts,
                "most_active_gate": max(gate_counts, key=gate_counts.get) if gate_counts else None,
            }
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[Beast] _analyze_batman_gates error: {exc}")
            return {"total_rejections": 0, "error": str(exc)}

    async def _analyze_latency(self, since: datetime) -> dict[str, Any]:
        """Check pipeline benchmark stats for latency outliers."""
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433
            events = await MekkaRepository.get_events_since(
                agent="ProfessorX", event="CYCLE_COMPLETE", since=since
            )
            if not events:
                return {}

            durations = []
            for ev in events:
                payload = getattr(ev, "payload", {}) or {}
                dur = payload.get("duration_ms") or payload.get("elapsed_ms")
                if dur is not None:
                    durations.append(float(dur))

            if not durations:
                return {}

            durations.sort()
            n = len(durations)
            p50 = durations[n // 2]
            p95 = durations[int(n * 0.95)]
            p99 = durations[int(n * 0.99)]

            return {
                "samples": n,
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99,
                "max_ms": durations[-1],
            }
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[Beast] _analyze_latency error: {exc}")
            return {"error": str(exc)}

    async def _analyze_signal_quality(self, since: datetime) -> dict[str, Any]:
        """Evaluate how often Vision's signal confidence ≥ 0.65 leads to profitable trades."""
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433
            trades = await MekkaRepository.get_closed_trades_since(since)
            if not trades:
                return {}

            high_conf = [t for t in trades if getattr(t, "confidence", 0) >= 0.65]
            low_conf = [t for t in trades if getattr(t, "confidence", 0) < 0.65]

            def win_rate(lst):
                wins = [t for t in lst if getattr(t, "pnl_usd", 0) > 0]
                return len(wins) / len(lst) if lst else 0.0

            return {
                "high_confidence_win_rate": win_rate(high_conf),
                "low_confidence_win_rate": win_rate(low_conf),
                "high_conf_count": len(high_conf),
                "low_conf_count": len(low_conf),
            }
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[Beast] _analyze_signal_quality error: {exc}")
            return {"error": str(exc)}

    # -----------------------------------------------------------------------
    # Proposal generators
    # -----------------------------------------------------------------------

    async def _propose_from_trades(self, stats: dict) -> list[ImprovementProposal]:
        proposals = []
        win_rate = stats.get("win_rate", None)
        profit_factor = stats.get("profit_factor", None)
        total = stats.get("total_trades", 0)

        if total < 5:
            return []  # insufficient data

        if win_rate is not None and win_rate < 0.45:
            proposals.append(ImprovementProposal(
                title="Win rate abaixo de 45% — revisar filtros de entrada",
                description=(
                    f"Win rate atual: {win_rate:.0%}. Considere aumentar "
                    "min_confidence_threshold ou revisar os parâmetros do Vision."
                ),
                impact="HIGH",
                area="signal_quality",
                evidence=f"Win rate={win_rate:.0%} em {total} trades nos últimos {stats.get('period_days', 7)} dias",
                suggested_story="Story 250 — Recalibrar thresholds de confiança do Vision",
            ))

        if profit_factor is not None and profit_factor < 1.2:
            proposals.append(ImprovementProposal(
                title="Profit factor baixo — revisar relação risco/retorno",
                description=(
                    f"Profit factor: {profit_factor:.2f}. "
                    "Considere aumentar min_risk_reward_ratio ou ajustar TP/SL strategy."
                ),
                impact="HIGH",
                area="signal_quality",
                evidence=f"Profit factor={profit_factor:.2f}, avg_win={stats.get('avg_win_usd', 0):.2f} USD, "
                         f"avg_loss={stats.get('avg_loss_usd', 0):.2f} USD",
                suggested_story="Story 251 — Otimizar relação risco/retorno nos gates do Batman",
            ))

        # Symbol concentration check
        symbols = stats.get("symbols", {})
        if symbols:
            dominant = max(symbols, key=lambda s: abs(symbols[s]["pnl"]))
            dom_pnl = symbols[dominant]["pnl"]
            total_pnl = stats.get("total_pnl_usd", 0)
            if total != 0 and abs(dom_pnl) > abs(total_pnl) * 0.7:
                proposals.append(ImprovementProposal(
                    title=f"Alta concentração em {dominant} — diversificar portfólio",
                    description=(
                        f"{dominant} representa >70% do PnL total. "
                        "Considere ajustar os pesos por símbolo ou aumentar os ativos monitorados."
                    ),
                    impact="MEDIUM",
                    area="risk_gates",
                    evidence=f"{dominant} PnL: {dom_pnl:+.2f} USD, total: {total_pnl:+.2f} USD",
                ))

        return proposals

    async def _propose_from_gates(self, stats: dict) -> list[ImprovementProposal]:
        proposals = []
        gate_counts = stats.get("gate_counts", {})
        total_rejections = stats.get("total_rejections", 0)

        if not gate_counts or total_rejections == 0:
            return []

        # If any single gate fires more than 40% of all rejections → investigate
        for gate_id, count in gate_counts.items():
            pct = count / total_rejections
            if pct > 0.40 and count >= 5:
                proposals.append(ImprovementProposal(
                    title=f"Gate {gate_id} muito ativo — possível miscalibração",
                    description=(
                        f"Gate {gate_id} responsável por {pct:.0%} de todas as rejeições "
                        f"({count} de {total_rejections}). Verifique se o threshold está correto."
                    ),
                    impact="MEDIUM",
                    area="risk_gates",
                    evidence=f"Gate {gate_id}: {count} rejeições ({pct:.0%} do total)",
                    suggested_story=f"Story 252 — Recalibrar gate {gate_id} no Batman",
                ))

        return proposals

    async def _propose_from_latency(self, stats: dict) -> list[ImprovementProposal]:
        proposals = []
        p95 = stats.get("p95_ms")
        p99 = stats.get("p99_ms")

        if p95 is not None and p95 > 5000:
            proposals.append(ImprovementProposal(
                title="Latência P95 acima de 5s — otimizar pipeline",
                description=(
                    f"P95 de latência: {p95:.0f}ms. "
                    "Considere habilitar cycle_parallel_enabled ou revisar agentes lentos."
                ),
                impact="MEDIUM",
                area="latency",
                evidence=f"P95={p95:.0f}ms, P99={p99:.0f}ms" if p99 else f"P95={p95:.0f}ms",
                suggested_story="Story 246 — Ativar CycleParallelBranch para execução paralela",
            ))

        if p99 is not None and p99 > 15000:
            proposals.append(ImprovementProposal(
                title="Latência P99 crítica (>15s) — investigar gargalos",
                description=(
                    f"P99 de latência: {p99:.0f}ms. "
                    "Possíveis causas: LLM timeout, exchange API lenta, ou agente bloqueante."
                ),
                impact="HIGH",
                area="latency",
                evidence=f"P99={p99:.0f}ms",
            ))

        return proposals

    async def _propose_from_signal_quality(self, stats: dict) -> list[ImprovementProposal]:
        proposals = []
        hc_wr = stats.get("high_confidence_win_rate")
        lc_wr = stats.get("low_confidence_win_rate")
        hc_count = stats.get("high_conf_count", 0)
        lc_count = stats.get("low_conf_count", 0)

        if hc_wr is not None and hc_count >= 5 and hc_wr < 0.50:
            proposals.append(ImprovementProposal(
                title="Alta confiança do Vision não está convertendo — revisar calibração",
                description=(
                    f"Trades com confiança ≥ 0.65 têm win rate de apenas {hc_wr:.0%}. "
                    "O Vision pode estar superestimando confiança — considere adicionar "
                    "SignalOutcomeMemory ou ajustar o temperature do LLM."
                ),
                impact="HIGH",
                area="signal_quality",
                evidence=f"High-conf win rate={hc_wr:.0%} em {hc_count} trades",
                suggested_story="Story 253 — Calibrar confiança do Vision via outcome feedback",
            ))

        if lc_wr is not None and lc_count >= 5 and lc_wr > 0.60:
            proposals.append(ImprovementProposal(
                title="Trades de baixa confiança performando melhor que os de alta",
                description=(
                    f"Low-conf win rate {lc_wr:.0%} > high-conf {hc_wr:.0%}. "
                    "Pode indicar que o threshold de confiança está muito alto e filtrando "
                    "bons trades. Considere reduzir min_confidence_threshold."
                ),
                impact="MEDIUM",
                area="signal_quality",
                evidence=f"Low-conf win rate={lc_wr:.0%} ({lc_count} trades) vs "
                         f"high-conf win rate={hc_wr:.0%} ({hc_count} trades)",
            ))

        return proposals

    # -----------------------------------------------------------------------
    # Health score
    # -----------------------------------------------------------------------

    def _compute_health_score(self, stats: dict) -> float:
        """
        Heuristic health score 0-100 based on available stats.
        Higher = healthier system.
        """
        score = 70.0  # baseline

        # Win rate
        wr = stats.get("win_rate")
        if wr is not None:
            if wr >= 0.55:
                score += 15
            elif wr >= 0.45:
                score += 5
            else:
                score -= 20

        # Profit factor
        pf = stats.get("profit_factor")
        if pf is not None:
            if pf >= 1.5:
                score += 10
            elif pf >= 1.2:
                score += 5
            elif pf < 1.0:
                score -= 15

        # Latency
        latency = stats.get("latency", {})
        p95 = latency.get("p95_ms")
        if p95 is not None:
            if p95 > 10000:
                score -= 10
            elif p95 < 2000:
                score += 5

        return max(0.0, min(100.0, score))

    # -----------------------------------------------------------------------
    # Telegram reporting
    # -----------------------------------------------------------------------

    async def _send_report(self, report: BeastReport) -> None:
        """Send the analysis report to Telegram. Fails silently."""
        if not settings.telegram_enabled:
            self._log.info("[Beast] Telegram disabled — report not sent.")
            return

        try:
            from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
            alerter = TelegramAlerter()

            health_emoji = "🟢" if report.system_health_score >= 70 else (
                "🟡" if report.system_health_score >= 50 else "🔴"
            )

            header = (
                f"🧬 *Beast — Relatório de Melhorias*\n"
                f"📅 Período: últimos {report.period_days} dias\n"
                f"{health_emoji} Saúde do sistema: {report.system_health_score:.0f}/100\n"
                f"📊 Trades analisados: {report.total_trades_analyzed}\n"
                f"💡 Propostas: {len(report.proposals)} "
                f"({len(report.high_priority)} críticas)\n"
            )

            if report.is_empty:
                await alerter.alert(
                    event="BEAST_REPORT",
                    severity="INFO",
                    agent="Beast",
                    message=header + "\n✅ Nenhuma melhoria crítica identificada.",
                )
                return

            # Send header + top 5 proposals (avoid Telegram message size limit)
            top_proposals = report.proposals[:5]
            proposal_blocks = "\n\n".join(p.to_telegram_block() for p in top_proposals)
            remaining = len(report.proposals) - len(top_proposals)
            footer = f"\n\n_+{remaining} propostas adicionais não exibidas._" if remaining > 0 else ""

            full_message = f"{header}\n{proposal_blocks}{footer}"

            await alerter.alert(
                event="BEAST_REPORT",
                severity="WARNING" if report.high_priority else "INFO",
                agent="Beast",
                message=full_message,
            )

            self._log.info(f"[Beast] Report sent to Telegram ({len(top_proposals)} proposals shown)")

        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[Beast] Telegram send failed (suppressed): {exc}")

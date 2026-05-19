"""
src/services/divergence_alerter.py
=====================================
DivergenceAlerter — Story 231 (Milestone 37: Live Performance Tracking).

Detecta e categoriza divergências entre performance real e backtest,
retornando um relatório estruturado com severidade e recomendações.

Uso::

    alerter = DivergenceAlerter()
    result  = await alerter.check(symbol="BTC", backtest=summary)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from src.models.backtest import BacktestSummary
from src.services.performance_tracker import PerformanceTracker


class DivergenceAlerter:
    """
    Verifica divergências entre real e backtest e gera alertas acionáveis.

    Níveis de severidade
    --------------------
    - LOW    : delta leve, monitorar
    - MEDIUM : divergência significativa, revisar parâmetros
    - HIGH   : divergência crítica, considerar pausar operações
    """

    def __init__(self) -> None:
        self._log = logger.bind(service="DivergenceAlerter")

    async def check(
        self,
        symbol: str,
        backtest: Optional[BacktestSummary] = None,
        window_days: int = 30,
    ) -> dict:
        """
        Verifica divergências e retorna relatório JSON-safe.

        Returns:
            Dict com: symbol, status, alerts, snapshot, generated_at
        """
        tracker  = PerformanceTracker()
        snapshot = await tracker.compare(
            symbol=symbol,
            backtest=backtest,
            window_days=window_days,
        )

        alerts = []
        for note in snapshot.notes:
            severity = self._classify_severity(note, snapshot)
            alerts.append({
                "severity":       severity,
                "message":        note,
                "recommendation": self._recommendation(severity, note),
            })

        # Alerta positivo se performance real supera backtest
        if snapshot.alpha_pnl_usd > 500 and not alerts:
            alerts.append({
                "severity":       "INFO",
                "message":        f"Performance real supera backtest em ${snapshot.alpha_pnl_usd:+,.0f} (alfa positivo)",
                "recommendation": "Continuar estratégia atual",
            })

        self._log.info(
            f"DivergenceAlerter: {symbol} "
            f"status={snapshot.status} alertas={len(alerts)}"
        )

        return {
            "symbol":      symbol,
            "status":      snapshot.status,
            "alert_count": len(alerts),
            "alerts":      alerts,
            "snapshot":    snapshot.to_dict(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_severity(note: str, snapshot) -> str:
        note_lower = note.lower()
        if "drawdown" in note_lower:
            dd_ratio = (
                snapshot.real_max_dd_pct / snapshot.bt_max_dd_pct
                if snapshot.bt_max_dd_pct > 0 else 1.0
            )
            if dd_ratio >= 3.0:
                return "HIGH"
            if dd_ratio >= 2.0:
                return "MEDIUM"
            return "LOW"
        if "win rate" in note_lower:
            delta = abs(snapshot.delta_win_rate)
            if delta >= 30:
                return "HIGH"
            if delta >= 20:
                return "MEDIUM"
            return "LOW"
        if "sharpe" in note_lower:
            delta = abs(snapshot.delta_sharpe)
            if delta >= 2.0:
                return "HIGH"
            if delta >= 1.5:
                return "MEDIUM"
            return "LOW"
        return "LOW"

    @staticmethod
    def _recommendation(severity: str, note: str) -> str:
        note_lower = note.lower()
        if severity == "HIGH":
            if "drawdown" in note_lower:
                return "Revisar stop-loss imediatamente. Considerar reduzir tamanho de posição ou pausar operações."
            if "win rate" in note_lower:
                return "Sinal de degradação severa. Revisar qualidade dos sinais Vision e condições de mercado."
            return "Divergência crítica. Pausar operações e revisar pipeline completo."
        if severity == "MEDIUM":
            if "drawdown" in note_lower:
                return "Monitorar drawdown de perto. Avaliar ajuste do stop-loss."
            if "win rate" in note_lower:
                return "Revisar parâmetros de filtragem do Vision. Checar regime atual."
            return "Revisar métricas do backtest e comparar com condições atuais de mercado."
        return "Monitorar. Divergência leve pode ser ruído estatístico."

"""
src/services/drawdown_monitor.py
=================================
DrawdownMonitor — Story 213 (Milestone 34: Monitoring & Alerting).

Monitora o drawdown intraday e dispara alertas Telegram em 3 níveis
escalonados, com dedup por nível para evitar spam ao operador.

Níveis de alerta
----------------
  WARNING   50 % do limite diário — aviso antecipado
  CRITICAL  80 % do limite diário — urgência moderada
  KILL     100 % do limite diário — recomenda acionar kill switch

Design
------
- Stateless em disco: estado reset a cada instância (paper-trading-first).
- Cada nível dispara **uma única vez por sessão** (dedup interno por set).
- Nunca lança exceção para o caller — erros são logados e absorvidos.
- Não depende de PortfolioManager nem IronMan: recebe equity/peak via args.
- Integração Telegram via TelegramAlerter.alert() (método genérico).

Uso típico em NickFury.run_main_cycle()
----------------------------------------
    snapshot = await portfolio_manager.snapshot()
    alert = await drawdown_monitor.check(
        current_equity=snapshot.equity_usd,
        peak_equity=snapshot.peak_equity_usd,
    )
    # alert é None se não há novo alerta a disparar
"""

from __future__ import annotations

from typing import Optional, Set

from loguru import logger

from src.config.settings import settings
from src.models.monitoring import DrawdownAlert

# Emojis por nível
_LEVEL_EMOJI = {
    "WARNING": "⚠️",
    "CRITICAL": "🔴",
    "KILL": "🚨",
}

# Severidade Telegram por nível
_LEVEL_SEVERITY = {
    "WARNING": "WARNING",
    "CRITICAL": "ERROR",
    "KILL": "CRITICAL",
}

# Fração do limite diário que ativa cada nível
_THRESHOLDS: list[tuple[str, float]] = [
    ("KILL", 1.00),      # 100 %
    ("CRITICAL", 0.80),  # 80 %
    ("WARNING", 0.50),   # 50 %
]


class DrawdownMonitor:
    """
    Monitor de drawdown intraday com alertas escalonados por Telegram.

    Args:
        max_daily_drawdown_pct: Limite diário como decimal (0.10 = 10 %).
                                Padrão: settings.max_daily_drawdown_pct.
        alerter: Instância de TelegramAlerter. Se None, cria uma nova.

    Example::

        monitor = DrawdownMonitor()
        alert = await monitor.check(current_equity=9200.0, peak_equity=10_000.0)
        # drawdown = 8 %, limite = 10 % → 80 % → CRITICAL
    """

    def __init__(
        self,
        max_daily_drawdown_pct: Optional[float] = None,
        alerter=None,  # TelegramAlerter — typed loosely to avoid circular
    ) -> None:
        self._limit_pct: float = (
            max_daily_drawdown_pct
            if max_daily_drawdown_pct is not None
            else settings.max_daily_drawdown_pct
        )
        self._fired: Set[str] = set()  # níveis já disparados nesta sessão
        self._alerter = alerter
        self._log = logger.bind(service="DrawdownMonitor")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def check(
        self,
        current_equity: float,
        peak_equity: float,
    ) -> Optional[DrawdownAlert]:
        """
        Avalia o drawdown atual e dispara alerta Telegram se necessário.

        Retorna:
            DrawdownAlert — se um novo nível foi atingido e alertado.
            None          — se nenhum threshold novo foi cruzado.

        Nunca lança exceção.
        """
        try:
            return await self._check_internal(current_equity, peak_equity)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"DrawdownMonitor.check() error (suppressed): {exc}")
            return None

    def reset_session(self) -> None:
        """
        Reseta o dedup para uma nova sessão de trading (novo dia UTC).
        Chamado por NickFury na virada de dia.
        """
        self._fired.clear()
        self._log.info("DrawdownMonitor: dedup resetado para nova sessão")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _check_internal(
        self,
        current_equity: float,
        peak_equity: float,
    ) -> Optional[DrawdownAlert]:
        if peak_equity <= 0 or current_equity <= 0:
            return None

        loss_usd = peak_equity - current_equity
        if loss_usd <= 0:
            # Equity acima do pico — sem drawdown
            return None

        drawdown_pct = loss_usd / peak_equity * 100
        limit_pct = self._limit_pct * 100  # converter para %

        # Percorrer thresholds do mais alto para o mais baixo
        for level, fraction in _THRESHOLDS:
            threshold_pct = limit_pct * fraction
            if drawdown_pct >= threshold_pct and level not in self._fired:
                alert = DrawdownAlert(
                    level=level,
                    drawdown_pct=round(drawdown_pct, 3),
                    current_equity=current_equity,
                    peak_equity=peak_equity,
                    loss_usd=round(loss_usd, 2),
                    limit_pct=limit_pct,
                    threshold_pct=round(threshold_pct, 3),
                )
                self._fired.add(level)
                await self._send_telegram(alert)
                self._log.warning(
                    f"Drawdown {level}: {drawdown_pct:.2f}% "
                    f"(threshold {threshold_pct:.2f}%, limite {limit_pct:.2f}%)"
                )
                return alert

        return None

    async def _send_telegram(self, alert: DrawdownAlert) -> None:
        """Envia alerta via TelegramAlerter. Absorve falhas."""
        try:
            alerter = self._alerter or self._get_default_alerter()
            emoji = _LEVEL_EMOJI[alert.level]
            severity = _LEVEL_SEVERITY[alert.level]

            kill_note = ""
            if alert.level == "KILL":
                kill_note = " | ⛔ Considere acionar ./scripts/kill.sh"

            message = (
                f"{emoji} Drawdown {alert.drawdown_pct:.2f}% "
                f"({alert.pct_of_limit * 100:.0f}% do limite diário{kill_note})"
            )

            await alerter.alert(
                event=f"DRAWDOWN_{alert.level}",
                severity=severity,
                agent="DrawdownMonitor",
                message=message,
                payload={
                    "equity": f"${alert.current_equity:,.2f}",
                    "pico": f"${alert.peak_equity:,.2f}",
                    "perda": f"-${alert.loss_usd:,.2f}",
                    "drawdown": f"{alert.drawdown_pct:.2f}%",
                    "limite": f"{alert.limit_pct:.1f}%",
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"DrawdownMonitor._send_telegram error (suppressed): {exc}")

    @staticmethod
    def _get_default_alerter():
        from src.services.telegram_alerter import TelegramAlerter  # lazy, avoid circular
        return TelegramAlerter()

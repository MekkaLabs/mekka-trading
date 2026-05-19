"""
src/services/intraday_pnl_tracker.py
======================================
IntradayPnLTracker — Story 215 (Milestone 34: Monitoring & Alerting).

Rastreia P&L intraday com snapshots por hora UTC e dispara alertas Telegram
quando o P&L cruza marcos configuráveis (ganho ou perda).

Design
------
- Estado em memória: dict ``{hour_utc: PnLSnapshot}`` — reseta na virada do dia.
- Marcos de alerta deduplicados por marco (cada marco dispara uma vez por dia).
- ``record()`` é o único método de escrita — nunca acessa disco.
- Alertas via TelegramAlerter.alert() (método genérico).
- Nunca lança exceção: erros são logados e absorvidos.
- ``get_summary()`` retorna string pronta para o comando /intraday.

Marcos padrão
-------------
  Ganho: +3 %, +5 %, +10 %
  Perda: -2 %, -5 %

Uso típico
----------
    tracker = IntradayPnLTracker()
    snap = await tracker.record(
        realized_pnl=500.0,
        unrealized_pnl=200.0,
        equity_usd=10_000.0,
    )
    # Se P&L atingiu +3% → alerta Telegram enviado automaticamente
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from loguru import logger

from src.config.settings import settings
from src.models.monitoring import PnLSnapshot

# Marcos padrão de alerta
_DEFAULT_GAIN_THRESHOLDS_PCT: List[float] = [3.0, 5.0, 10.0]
_DEFAULT_LOSS_THRESHOLDS_PCT: List[float] = [-2.0, -5.0]


class IntradayPnLTracker:
    """
    Rastreia P&L intraday com snapshots horários e alertas em marcos configuráveis.

    Args:
        gain_thresholds_pct: Marcos de ganho em % (ex: [3.0, 5.0, 10.0]).
        loss_thresholds_pct: Marcos de perda em % (ex: [-2.0, -5.0]).
        alerter: Instância de TelegramAlerter. Se None, cria uma nova (lazy).

    Example::

        tracker = IntradayPnLTracker()
        snap = await tracker.record(
            realized_pnl=350.0,
            unrealized_pnl=150.0,
            equity_usd=10_000.0,
        )
    """

    def __init__(
        self,
        gain_thresholds_pct: Optional[List[float]] = None,
        loss_thresholds_pct: Optional[List[float]] = None,
        alerter=None,
    ) -> None:
        self._gain_thresholds: List[float] = (
            gain_thresholds_pct
            if gain_thresholds_pct is not None
            else _DEFAULT_GAIN_THRESHOLDS_PCT
        )
        self._loss_thresholds: List[float] = (
            loss_thresholds_pct
            if loss_thresholds_pct is not None
            else _DEFAULT_LOSS_THRESHOLDS_PCT
        )
        # Snapshots indexados por hora UTC
        self._snapshots: Dict[int, PnLSnapshot] = {}
        # Marcos já alertados neste dia (ex: "GAIN_3", "LOSS_-2")
        self._fired_milestones: set[str] = set()
        self._alerter = alerter
        self._log = logger.bind(service="IntradayPnLTracker")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def record(
        self,
        realized_pnl: float,
        unrealized_pnl: float,
        equity_usd: float,
    ) -> PnLSnapshot:
        """
        Registra snapshot do P&L atual e verifica marcos de alerta.

        Args:
            realized_pnl: P&L realizado em USD (trades fechados no dia).
            unrealized_pnl: P&L não-realizado em USD (posições abertas).
            equity_usd: Equity atual em USD.

        Returns:
            PnLSnapshot registrado.

        Nunca lança exceção.
        """
        try:
            return await self._record_internal(realized_pnl, unrealized_pnl, equity_usd)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"IntradayPnLTracker.record() error (suppressed): {exc}")
            # Retorna snapshot mínimo para não quebrar callers
            now = datetime.now(timezone.utc)
            return PnLSnapshot(
                hour=now.hour,
                realized_pnl_usd=realized_pnl,
                unrealized_pnl_usd=unrealized_pnl,
                total_pnl_usd=realized_pnl + unrealized_pnl,
                equity_usd=equity_usd,
            )

    def get_summary(self) -> str:
        """
        Retorna resumo formatado do P&L intraday para o comando /intraday.

        Example output::

            📊 P&L Intraday — 14:00 UTC
            Realizado  : +$350.00
            Não-real.  : +$120.00
            Total      : +$470.00  (+4.70%)
            Snapshots  : 14 horas registradas
        """
        if not self._snapshots:
            return "📊 P&L Intraday — sem dados ainda"

        # Pega o snapshot mais recente
        latest_hour = max(self._snapshots.keys())
        snap = self._snapshots[latest_hour]
        now_str = f"{latest_hour:02d}:00 UTC"

        pnl_sign = "+" if snap.total_pnl_usd >= 0 else ""
        pnl_pct_sign = "+" if snap.total_pnl_pct >= 0 else ""

        lines = [
            f"📊 *P&L Intraday — {now_str}*",
            "",
            f"Realizado  : {pnl_sign}${snap.realized_pnl_usd:,.2f}",
            f"Não-real.  : {pnl_sign}${snap.unrealized_pnl_usd:,.2f}",
            f"Total      : {pnl_sign}${snap.total_pnl_usd:,.2f}  ({pnl_pct_sign}{snap.total_pnl_pct:.2f}%)",
            f"Snapshots  : {len(self._snapshots)} hora(s) registrada(s)",
        ]
        return "\n".join(lines)

    def reset_day(self) -> None:
        """Reseta snapshots e marcos para novo dia UTC."""
        self._snapshots.clear()
        self._fired_milestones.clear()
        self._log.info("IntradayPnLTracker: resetado para novo dia UTC")

    @property
    def snapshots(self) -> Dict[int, PnLSnapshot]:
        """Snapshots indexados por hora UTC (read-only view)."""
        return dict(self._snapshots)

    @property
    def latest_snapshot(self) -> Optional[PnLSnapshot]:
        """Snapshot mais recente ou None se sem dados."""
        if not self._snapshots:
            return None
        return self._snapshots[max(self._snapshots.keys())]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _record_internal(
        self,
        realized_pnl: float,
        unrealized_pnl: float,
        equity_usd: float,
    ) -> PnLSnapshot:
        now = datetime.now(timezone.utc)
        total_pnl = realized_pnl + unrealized_pnl

        snap = PnLSnapshot(
            hour=now.hour,
            realized_pnl_usd=realized_pnl,
            unrealized_pnl_usd=unrealized_pnl,
            total_pnl_usd=total_pnl,
            equity_usd=equity_usd,
        )
        self._snapshots[now.hour] = snap

        # Calcular P&L % para verificar marcos
        if equity_usd > 0:
            base_equity = equity_usd - total_pnl
            if base_equity > 0:
                pnl_pct = total_pnl / base_equity * 100
                await self._check_milestones(pnl_pct, snap)

        return snap

    async def _check_milestones(self, pnl_pct: float, snap: PnLSnapshot) -> None:
        """Verifica e dispara alertas de marcos de ganho e perda."""
        # Marcos de ganho (do menor para o maior)
        for threshold in sorted(self._gain_thresholds):
            key = f"GAIN_{threshold}"
            if pnl_pct >= threshold and key not in self._fired_milestones:
                self._fired_milestones.add(key)
                await self._send_telegram_milestone(
                    pnl_pct=pnl_pct,
                    threshold=threshold,
                    snap=snap,
                    is_gain=True,
                )
                self._log.info(f"Marco de P&L atingido: +{threshold}% (atual: {pnl_pct:.2f}%)")

        # Marcos de perda (do menos negativo para o mais negativo)
        for threshold in sorted(self._loss_thresholds, reverse=True):
            key = f"LOSS_{threshold}"
            if pnl_pct <= threshold and key not in self._fired_milestones:
                self._fired_milestones.add(key)
                await self._send_telegram_milestone(
                    pnl_pct=pnl_pct,
                    threshold=threshold,
                    snap=snap,
                    is_gain=False,
                )
                self._log.warning(f"Marco de perda atingido: {threshold}% (atual: {pnl_pct:.2f}%)")

    async def _send_telegram_milestone(
        self,
        pnl_pct: float,
        threshold: float,
        snap: PnLSnapshot,
        is_gain: bool,
    ) -> None:
        """Envia alerta de marco de P&L via Telegram. Absorve falhas."""
        try:
            alerter = self._alerter or self._get_default_alerter()
            emoji = "🟢" if is_gain else "🔴"
            sign = "+" if is_gain else ""
            severity = "INFO" if is_gain else "WARNING"
            event = f"INTRADAY_PNL_{'GAIN' if is_gain else 'LOSS'}_{abs(threshold):.0f}PCT"

            await alerter.alert(
                event=event,
                severity=severity,
                agent="IntradayPnLTracker",
                message=(
                    f"{emoji} P&L intraday atingiu {sign}{pnl_pct:.2f}% "
                    f"(marco: {sign}{threshold:.0f}%)"
                ),
                payload={
                    "realizado": f"${snap.realized_pnl_usd:+,.2f}",
                    "nao_realizado": f"${snap.unrealized_pnl_usd:+,.2f}",
                    "total": f"${snap.total_pnl_usd:+,.2f}",
                    "pct": f"{pnl_pct:+.2f}%",
                    "hora_utc": f"{snap.hour:02d}:00",
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"IntradayPnLTracker._send_telegram_milestone error (suppressed): {exc}")

    @staticmethod
    def _get_default_alerter():
        from src.services.telegram_alerter import TelegramAlerter  # lazy import
        return TelegramAlerter()

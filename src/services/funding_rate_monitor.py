"""
src/services/funding_rate_monitor.py
======================================
FundingRateMonitor — Story 216 (Milestone 34: Monitoring & Alerting).

Monitora a taxa de funding de Hyperliquid e dispara alertas Telegram quando
atingir níveis extremos (WARN ou BLOCK), independente de haver um trade ativo.

Motivação
---------
Batman bloqueia trades quando funding é extremo — mas só verifica durante um
ciclo de sinal. Este serviço alerta o operador *proativamente* sobre condições
de funding anormais, mesmo sem trade em curso.

Thresholds (reutilizados de settings)
--------------------------------------
  funding_long_warn_pct   (ex: 0.05%)  — funding positivo elevado → WARN (HIGH_LONG)
  funding_long_block_pct  (ex: 0.10%)  — funding positivo extremo → BLOCK (HIGH_LONG)
  funding_short_warn_pct  (ex: -0.05%) — funding negativo elevado → WARN (HIGH_SHORT)
  funding_short_block_pct (ex: -0.10%) — funding negativo extremo → BLOCK (HIGH_SHORT)

Design
------
- Stateless: dedup por (symbol, direction, severity) — uma vez por sessão.
- Retorna o nível mais alto atingido (BLOCK > WARN).
- Nunca lança exceção: erros são logados e absorvidos.
- Independente do Batman — não compartilha estado com ele.
- Integração Telegram via TelegramAlerter.alert().

Uso típico
----------
    # Chamado em NickFury após BlackPanther.analyze() retornar funding_rate
    alert = await funding_monitor.check(symbol="BTC", funding_rate_pct=funding_rate)
"""

from __future__ import annotations

from typing import Optional, Set

from loguru import logger

from src.config.settings import settings
from src.models.monitoring import FundingAlert


class FundingRateMonitor:
    """
    Monitora funding rates e emite alertas Telegram em níveis WARN e BLOCK.

    Args:
        long_warn_pct: Threshold WARN para longs (funding positivo).
                       Padrão: settings.funding_long_warn_pct.
        long_block_pct: Threshold BLOCK para longs (funding positivo extremo).
                        Padrão: settings.funding_long_block_pct.
        short_warn_pct: Threshold WARN para shorts (funding negativo).
                        Padrão: settings.funding_short_warn_pct.
        short_block_pct: Threshold BLOCK para shorts (funding negativo extremo).
                         Padrão: settings.funding_short_block_pct.
        alerter: Instância de TelegramAlerter. Se None, cria uma nova (lazy).

    Example::

        monitor = FundingRateMonitor()
        alert = await monitor.check(symbol="BTC", funding_rate_pct=0.12)
        # 0.12% > 0.10% (block) → FundingAlert(severity="BLOCK", direction="HIGH_LONG")
    """

    def __init__(
        self,
        long_warn_pct: Optional[float] = None,
        long_block_pct: Optional[float] = None,
        short_warn_pct: Optional[float] = None,
        short_block_pct: Optional[float] = None,
        alerter=None,
    ) -> None:
        self._long_warn = long_warn_pct if long_warn_pct is not None else settings.funding_long_warn_pct
        self._long_block = long_block_pct if long_block_pct is not None else settings.funding_long_block_pct
        self._short_warn = short_warn_pct if short_warn_pct is not None else settings.funding_short_warn_pct
        self._short_block = short_block_pct if short_block_pct is not None else settings.funding_short_block_pct
        # Dedup: set de strings "{symbol}:{direction}:{severity}"
        self._fired: Set[str] = set()
        self._alerter = alerter
        self._log = logger.bind(service="FundingRateMonitor")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def check(
        self,
        symbol: str,
        funding_rate_pct: float,
    ) -> Optional[FundingAlert]:
        """
        Verifica a taxa de funding e dispara alerta Telegram se extrema.

        Args:
            symbol: Par de trading (ex: "BTC", "ETH").
            funding_rate_pct: Taxa de funding em % por 8h (ex: 0.12 para 0.12%/8h).

        Returns:
            FundingAlert — se um novo nível foi atingido.
            None         — se dentro dos limites normais ou já alertado.

        Nunca lança exceção.
        """
        try:
            return await self._check_internal(symbol, funding_rate_pct)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"FundingRateMonitor.check() error (suppressed): {exc}")
            return None

    def reset_session(self) -> None:
        """Reseta dedup para nova sessão (novo dia UTC ou reinício)."""
        self._fired.clear()
        self._log.info("FundingRateMonitor: dedup resetado para nova sessão")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _check_internal(
        self,
        symbol: str,
        funding_rate_pct: float,
    ) -> Optional[FundingAlert]:
        # Verificar longs excessivos (funding positivo alto)
        if funding_rate_pct >= self._long_block:
            return await self._maybe_fire(
                symbol=symbol,
                funding_rate_pct=funding_rate_pct,
                direction="HIGH_LONG",
                severity="BLOCK",
                threshold_pct=self._long_block,
            )
        if funding_rate_pct >= self._long_warn:
            return await self._maybe_fire(
                symbol=symbol,
                funding_rate_pct=funding_rate_pct,
                direction="HIGH_LONG",
                severity="WARN",
                threshold_pct=self._long_warn,
            )

        # Verificar shorts excessivos (funding negativo)
        if funding_rate_pct <= self._short_block:
            return await self._maybe_fire(
                symbol=symbol,
                funding_rate_pct=funding_rate_pct,
                direction="HIGH_SHORT",
                severity="BLOCK",
                threshold_pct=self._short_block,
            )
        if funding_rate_pct <= self._short_warn:
            return await self._maybe_fire(
                symbol=symbol,
                funding_rate_pct=funding_rate_pct,
                direction="HIGH_SHORT",
                severity="WARN",
                threshold_pct=self._short_warn,
            )

        return None  # Funding dentro dos limites normais

    async def _maybe_fire(
        self,
        symbol: str,
        funding_rate_pct: float,
        direction: str,
        severity: str,
        threshold_pct: float,
    ) -> Optional[FundingAlert]:
        """Dispara alerta se não foi deduplicado."""
        dedup_key = f"{symbol}:{direction}:{severity}"
        if dedup_key in self._fired:
            return None

        alert = FundingAlert(
            symbol=symbol,
            funding_rate_pct=round(funding_rate_pct, 4),
            direction=direction,  # type: ignore[arg-type]
            severity=severity,    # type: ignore[arg-type]
            threshold_pct=round(threshold_pct, 4),
        )
        self._fired.add(dedup_key)
        await self._send_telegram(alert)
        self._log.warning(
            f"Funding extremo: {symbol} {funding_rate_pct:+.4f}% "
            f"[{direction} / {severity}] threshold={threshold_pct:+.4f}%"
        )
        return alert

    async def _send_telegram(self, alert: FundingAlert) -> None:
        """Envia alerta via TelegramAlerter. Absorve falhas."""
        try:
            alerter = self._alerter or self._get_default_alerter()

            is_high_long = alert.direction == "HIGH_LONG"
            is_block = alert.severity == "BLOCK"

            emoji = "🚨" if is_block else "⚠️"
            sev_label = "BLOQUEIO" if is_block else "AVISO"
            direction_label = (
                "longs sobrecomprados" if is_high_long else "shorts sobrevendidos"
            )
            implication = (
                "Longs em risco de liquidação" if is_high_long
                else "Shorts em risco de squeeze"
            )

            tg_severity = "ERROR" if is_block else "WARNING"

            await alerter.alert(
                event=f"FUNDING_{alert.direction}_{alert.severity}",
                severity=tg_severity,
                agent="FundingRateMonitor",
                message=(
                    f"{emoji} Funding extremo em {alert.symbol} [{sev_label}]\n"
                    f"Taxa: {alert.funding_rate_pct:+.4f}%/8h ({direction_label})\n"
                    f"⚡ {implication}"
                ),
                symbol=alert.symbol,
                payload={
                    "funding": f"{alert.funding_rate_pct:+.4f}%",
                    "threshold": f"{alert.threshold_pct:+.4f}%",
                    "direcao": alert.direction,
                    "nivel": alert.severity,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"FundingRateMonitor._send_telegram error (suppressed): {exc}")

    @staticmethod
    def _get_default_alerter():
        from src.services.telegram_alerter import TelegramAlerter  # lazy import
        return TelegramAlerter()

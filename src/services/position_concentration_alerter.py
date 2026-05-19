"""
src/services/position_concentration_alerter.py
================================================
PositionConcentrationAlerter — Story 214 (Milestone 34: Monitoring & Alerting).

Monitora se alguma posição aberta representa mais que `max_concentration_pct`
da equity atual e dispara alerta Telegram com detalhes.

Motivação
---------
Batman verifica concentração *antes* da abertura. Mas após a abertura,
a equity pode cair e a posição passar a ser desproporcional ao portfólio.
Este serviço monitora continuamente o rácio posição/equity intraday.

Design
------
- Stateless: dedup por símbolo — uma vez alertado por sessão, silencia.
- Aceita lista de dicts {symbol, notional_usd, side} — desacoplado dos
  Pydantic models de execution para uso flexível.
- Nunca lança exceção: erros são logados e absorvidos.
- Integração Telegram via TelegramAlerter.alert() (método genérico).

Uso típico
----------
    positions = portfolio_manager.open_positions_as_dicts()
    snapshot  = await portfolio_manager.snapshot()
    alerts = await concentration_alerter.check(
        positions=positions,
        equity_usd=snapshot.equity_usd,
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from loguru import logger

from src.config.settings import settings
from src.models.monitoring import ConcentrationAlert


class PositionConcentrationAlerter:
    """
    Monitora concentração de posições individuais em relação à equity atual.

    Args:
        max_concentration_pct: Limite de concentração por posição como decimal
                               (0.25 = 25 % da equity). Padrão: settings.max_position_size_pct.
        alerter: Instância de TelegramAlerter. Se None, cria uma nova (lazy).

    Example::

        alerter = PositionConcentrationAlerter(max_concentration_pct=0.25)
        alerts = await alerter.check(
            positions=[{"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"}],
            equity_usd=10_000.0,
        )
    """

    def __init__(
        self,
        max_concentration_pct: Optional[float] = None,
        alerter=None,
    ) -> None:
        self._limit_pct: float = (
            max_concentration_pct
            if max_concentration_pct is not None
            else settings.max_position_size_pct
        )
        self._alerted_symbols: Set[str] = set()
        self._alerter = alerter
        self._log = logger.bind(service="PositionConcentrationAlerter")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def check(
        self,
        positions: List[Dict[str, Any]],
        equity_usd: float,
    ) -> List[ConcentrationAlert]:
        """
        Verifica concentração de cada posição aberta.

        Args:
            positions: Lista de dicts com chaves:
                       ``symbol`` (str), ``notional_usd`` (float), ``side`` (str, opcional).
            equity_usd: Equity atual em USD.

        Returns:
            Lista de ConcentrationAlert para posições que ultrapassaram o limite.
            Lista vazia se tudo dentro do limite ou equity inválida.

        Nunca lança exceção.
        """
        try:
            return await self._check_internal(positions, equity_usd)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"PositionConcentrationAlerter.check() error (suppressed): {exc}")
            return []

    def reset_session(self) -> None:
        """Reseta dedup para nova sessão de trading (novo dia UTC)."""
        self._alerted_symbols.clear()
        self._log.info("PositionConcentrationAlerter: dedup resetado para nova sessão")

    @property
    def alerted_symbols(self) -> Set[str]:
        """Conjunto de símbolos já alertados nesta sessão (read-only view)."""
        return frozenset(self._alerted_symbols)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _check_internal(
        self,
        positions: List[Dict[str, Any]],
        equity_usd: float,
    ) -> List[ConcentrationAlert]:
        if equity_usd <= 0 or not positions:
            return []

        limit_pct = self._limit_pct * 100  # converter para %
        fired: List[ConcentrationAlert] = []

        for pos in positions:
            symbol = str(pos.get("symbol", "UNKNOWN"))
            notional = float(pos.get("notional_usd", 0.0))
            side = str(pos.get("side", "UNKNOWN")).upper()

            if notional <= 0:
                continue

            concentration_pct = notional / equity_usd * 100

            if concentration_pct > limit_pct and symbol not in self._alerted_symbols:
                alert = ConcentrationAlert(
                    symbol=symbol,
                    position_notional_usd=round(notional, 2),
                    equity_usd=round(equity_usd, 2),
                    concentration_pct=round(concentration_pct, 2),
                    limit_pct=round(limit_pct, 2),
                    side=side,
                )
                self._alerted_symbols.add(symbol)
                await self._send_telegram(alert)
                self._log.warning(
                    f"Concentração: {symbol} {concentration_pct:.1f}% > {limit_pct:.1f}% "
                    f"(${notional:,.0f} / ${equity_usd:,.0f})"
                )
                fired.append(alert)

        return fired

    async def _send_telegram(self, alert: ConcentrationAlert) -> None:
        """Envia alerta via TelegramAlerter. Absorve falhas."""
        try:
            alerter = self._alerter or self._get_default_alerter()
            excess_pct = alert.concentration_pct - alert.limit_pct
            await alerter.alert(
                event="POSITION_CONCENTRATION",
                severity="WARNING",
                agent="PositionConcentrationAlerter",
                message=(
                    f"⚠️ {alert.symbol} {alert.side} ocupa {alert.concentration_pct:.1f}% "
                    f"da equity (limite: {alert.limit_pct:.1f}%, excesso: +{excess_pct:.1f}%)"
                ),
                symbol=alert.symbol,
                payload={
                    "notional": f"${alert.position_notional_usd:,.0f}",
                    "equity": f"${alert.equity_usd:,.0f}",
                    "concentracao": f"{alert.concentration_pct:.1f}%",
                    "limite": f"{alert.limit_pct:.1f}%",
                    "lado": alert.side,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"PositionConcentrationAlerter._send_telegram error (suppressed): {exc}")

    @staticmethod
    def _get_default_alerter():
        from src.services.telegram_alerter import TelegramAlerter  # lazy import
        return TelegramAlerter()

"""
src/services/alert_throttle_manager.py
=========================================
AlertThrottleManager — Story 217 (Milestone 34: Monitoring & Alerting).

Gateway centralizado de dedup e throttle para alertas Telegram.
Previne fadiga de alertas garantindo cooldowns configuráveis por tipo de evento.

Design
------
- ``is_allowed(event_key, cooldown_seconds)`` → bool
  Retorna True se o evento pode ser enviado (primeira vez ou cooldown expirado).
- ``record_sent(event_key)``
  Registra que o evento foi enviado (atualiza timestamp).
- ``get_stats()`` → dict
  Métricas de diagnóstico: enviados, suprimidos, último envio por evento.
- ``reset()``
  Limpa todo o estado (novo dia UTC).
- Thread-safe via asyncio.Lock.
- Nunca lança exceção.

Integração típica (nos monitores)
-----------------------------------
    # Antes de enviar qualquer alerta:
    if not throttle_manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800):
        return  # suprimido — cooldown ativo
    await alerter.alert(...)
    throttle_manager.record_sent("DRAWDOWN_WARNING")

Cooldowns sugeridos por evento
--------------------------------
  DRAWDOWN_WARNING     : 1800s (30 min)
  DRAWDOWN_CRITICAL    : 900s  (15 min)
  DRAWDOWN_KILL        : 300s  (5 min)
  POSITION_CONCENTRATION: 3600s (1h)
  INTRADAY_PNL_*       : 1800s (30 min)
  FUNDING_*_WARN       : 7200s (2h)
  FUNDING_*_BLOCK      : 3600s (1h)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from loguru import logger


@dataclass
class _EventRecord:
    """Estado interno de um tipo de evento."""
    sent: int = 0
    suppressed: int = 0
    last_sent_ts: Optional[float] = None  # unix timestamp


class AlertThrottleManager:
    """
    Gateway centralizado de throttle e dedup para alertas Telegram.

    Cada instância mantém um registro em memória por event_key.
    ``is_allowed()`` verifica se o cooldown expirou; ``record_sent()``
    atualiza o timestamp após o envio bem-sucedido.

    Example::

        manager = AlertThrottleManager()
        if manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800):
            await alerter.alert(...)
            manager.record_sent("DRAWDOWN_WARNING")

    Nota: ``is_allowed()`` e ``record_sent()`` são separados para que o
    caller possa decidir se o envio foi bem-sucedido antes de registrar.
    """

    def __init__(self) -> None:
        self._records: Dict[str, _EventRecord] = {}
        self._lock = asyncio.Lock()
        self._log = logger.bind(service="AlertThrottleManager")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, event_key: str, cooldown_seconds: float) -> bool:
        """
        Verifica se o evento pode ser enviado agora.

        Retorna True se:
          1. O evento nunca foi enviado, OU
          2. O tempo desde o último envio ≥ cooldown_seconds.

        Incrementa o contador ``suppressed`` se retornar False.
        Nunca lança exceção.
        """
        try:
            record = self._records.setdefault(event_key, _EventRecord())
            now = time.monotonic()

            if record.last_sent_ts is None:
                return True  # Primeiro envio — sempre permitido

            elapsed = now - record.last_sent_ts
            if elapsed >= cooldown_seconds:
                return True

            # Cooldown ativo — incrementa suprimidos e nega
            record.suppressed += 1
            self._log.debug(
                f"Throttle: {event_key} suprimido "
                f"(elapsed={elapsed:.0f}s < cooldown={cooldown_seconds:.0f}s)"
            )
            return False
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"AlertThrottleManager.is_allowed() error (suppressed): {exc}")
            return True  # fail-open — na dúvida, permite

    def record_sent(self, event_key: str) -> None:
        """
        Registra que um alerta foi enviado com sucesso.

        Atualiza timestamp e incrementa contador ``sent``.
        Deve ser chamado imediatamente após envio bem-sucedido.
        Nunca lança exceção.
        """
        try:
            record = self._records.setdefault(event_key, _EventRecord())
            record.sent += 1
            record.last_sent_ts = time.monotonic()
            self._log.debug(f"Throttle: {event_key} registrado (total_enviados={record.sent})")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"AlertThrottleManager.record_sent() error (suppressed): {exc}")

    def get_stats(self) -> Dict[str, Dict]:
        """
        Retorna estatísticas de todos os eventos monitorados.

        Returns:
            Dict ``{event_key: {sent, suppressed, last_sent_ts}}``

        Example::

            {
                "DRAWDOWN_WARNING": {"sent": 2, "suppressed": 5, "last_sent_ts": 1716123456.7},
                "FUNDING_HIGH_LONG_WARN": {"sent": 1, "suppressed": 0, "last_sent_ts": ...},
            }
        """
        try:
            return {
                key: {
                    "sent": rec.sent,
                    "suppressed": rec.suppressed,
                    "last_sent_ts": rec.last_sent_ts,
                }
                for key, rec in self._records.items()
            }
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"AlertThrottleManager.get_stats() error (suppressed): {exc}")
            return {}

    def reset(self) -> None:
        """
        Limpa todo o estado (enviados, suprimidos, timestamps).

        Tipicamente chamado na virada do dia UTC ou ao reiniciar o sistema.
        """
        try:
            count = len(self._records)
            self._records.clear()
            self._log.info(f"AlertThrottleManager: estado resetado ({count} eventos limpos)")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"AlertThrottleManager.reset() error (suppressed): {exc}")

    @property
    def total_sent(self) -> int:
        """Total de alertas enviados nesta sessão."""
        return sum(r.sent for r in self._records.values())

    @property
    def total_suppressed(self) -> int:
        """Total de alertas suprimidos por throttle nesta sessão."""
        return sum(r.suppressed for r in self._records.values())

    def summary_line(self) -> str:
        """Uma linha de resumo para logs. Ex: 'Alertas: 12 enviados, 37 suprimidos (3 eventos)'"""
        return (
            f"Alertas: {self.total_sent} enviados, "
            f"{self.total_suppressed} suprimidos "
            f"({len(self._records)} tipos)"
        )

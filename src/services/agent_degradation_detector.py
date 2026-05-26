"""
src/services/agent_degradation_detector.py
============================================
Fase 2.3 do docs/AGENT-INTEGRATION-PLAN.md — Observabilidade de degradação
silenciosa de agentes.

PROBLEMA
--------
A introdução de timeouts no BaseAgent (Fase 2.1) faz com que agentes
travados disparem ``AgentTimeoutError`` em vez de bloquear o ciclo, e o
event bus passa a receber ``agent.error`` / ``agent.timeout`` sempre que
isso acontece. Mas hoje ninguém AGREGA esses sinais — um agente pode
estar falhando 5 vezes seguidas sem que o operador perceba até que o
breaker do NickFury engate (após 3-5 falhas, dependendo do agente).

SOLUÇÃO
-------
Subscribe nos eventos ``agent.error`` e ``agent.timeout`` e mantenha uma
janela rolante de 5 minutos por agente. Quando o mesmo agente acumular
``threshold`` falhas (default 3) na janela:

  1. Publica ``degradation.detected`` no event bus (para dashboards)
  2. Dispara alerta WARNING no Telegram (com cooldown anti-flood)
  3. Loga WARNING estruturado

A janela é resetada quando publica para evitar reflood imediato.

USO
---
    from src.services.agent_degradation_detector import (
        start_agent_degradation_detector,
    )

    # No bootstrap (NickFury.__init__ ou main.py):
    start_agent_degradation_detector()

Singleton — startar mais de uma vez é no-op.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Optional

from loguru import logger

# Janela rolante para classificar falhas como "degradação"
DEFAULT_WINDOW_SECONDS: float = 300.0  # 5 minutos
DEFAULT_THRESHOLD: int = 3             # 3 falhas no mesmo agente
DEFAULT_RESET_AFTER_ALERT: bool = True  # zera contador ao alertar
DEFAULT_ALERT_COOLDOWN_S: float = 600.0  # 10min entre alertas Telegram


class AgentDegradationDetector:
    """Detecta degradação silenciosa de agentes via event bus.

    Não é thread-safe — projetado para single-loop asyncio. Cada falha
    é registrada com timestamp; ao publicar/alertar, varre a janela e
    descarta eventos fora do horizonte.
    """

    def __init__(
        self,
        *,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        threshold: int = DEFAULT_THRESHOLD,
        reset_after_alert: bool = DEFAULT_RESET_AFTER_ALERT,
        alert_cooldown_s: float = DEFAULT_ALERT_COOLDOWN_S,
    ) -> None:
        self.window_seconds = window_seconds
        self.threshold = threshold
        self.reset_after_alert = reset_after_alert
        self.alert_cooldown_s = alert_cooldown_s

        # {codename -> deque[(ts, topic, reason)]}
        self._failures: dict[str, deque[tuple[float, str, str]]] = defaultdict(deque)
        # {codename -> last alert ts} — anti-flood
        self._last_alert_ts: dict[str, float] = {}
        self._started = False

    # ──────────────────────────────────────────────────────────────────
    # Wiring
    # ──────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Conecta os handlers no event bus. Idempotente."""
        if self._started:
            return
        try:
            from src.services.event_bus import get_event_bus  # noqa: WPS433
            bus = get_event_bus()
            bus.subscribe("agent.error", self._on_failure_event)
            bus.subscribe("agent.timeout", self._on_failure_event)
            self._started = True
            logger.info(
                f"[AgentDegradationDetector] started — "
                f"threshold={self.threshold} in {self.window_seconds:.0f}s window"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[AgentDegradationDetector] start failed: {exc}")

    def stop(self) -> None:
        """Desconecta do event bus. Útil em testes."""
        if not self._started:
            return
        try:
            from src.services.event_bus import get_event_bus  # noqa: WPS433
            bus = get_event_bus()
            bus.unsubscribe("agent.error", self._on_failure_event)
            bus.unsubscribe("agent.timeout", self._on_failure_event)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[AgentDegradationDetector] stop error: {exc}")
        self._started = False

    # ──────────────────────────────────────────────────────────────────
    # Event handler
    # ──────────────────────────────────────────────────────────────────

    async def _on_failure_event(self, event: dict) -> None:
        """Handler para agent.error e agent.timeout. Nunca lança."""
        try:
            codename = str(event.get("codename") or "").strip()
            if not codename:
                return
            topic = str(event.get("topic") or "agent.error")
            reason = str(event.get("reason") or event.get("timeout_s") or "")
            now = time.monotonic()

            failures = self._failures[codename]
            failures.append((now, topic, reason))

            # Drop eventos fora da janela
            cutoff = now - self.window_seconds
            while failures and failures[0][0] < cutoff:
                failures.popleft()

            if len(failures) >= self.threshold:
                await self._emit_degradation(codename, list(failures), now)
                if self.reset_after_alert:
                    failures.clear()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[AgentDegradationDetector] event handler error: {exc}")

    # ──────────────────────────────────────────────────────────────────
    # Emitter
    # ──────────────────────────────────────────────────────────────────

    async def _emit_degradation(
        self,
        codename: str,
        failures: list[tuple[float, str, str]],
        now: float,
    ) -> None:
        """Publica evento de degradação + dispara alerta Telegram (cooldown)."""
        count = len(failures)
        topics_breakdown: dict[str, int] = defaultdict(int)
        for _, topic, _ in failures:
            topics_breakdown[topic] += 1

        first_ts, _, _ = failures[0]
        elapsed_s = now - first_ts

        payload = {
            "codename": codename,
            "count": count,
            "window_s": round(elapsed_s, 1),
            "by_topic": dict(topics_breakdown),
        }

        # 1. Publica no event bus para dashboards
        try:
            from src.services.event_bus import get_event_bus  # noqa: WPS433
            get_event_bus().publish_sync("degradation.detected", payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[AgentDegradationDetector] publish failed: {exc}")

        # 2. Log estruturado
        logger.warning(
            f"[AgentDegradationDetector] DEGRADAÇÃO {codename}: "
            f"{count} falhas em {elapsed_s:.0f}s ({dict(topics_breakdown)})"
        )

        # 3. Telegram com cooldown
        last_alert = self._last_alert_ts.get(codename, 0.0)
        if now - last_alert < self.alert_cooldown_s:
            logger.debug(
                f"[AgentDegradationDetector] alerta Telegram em cooldown "
                f"({codename}, {now - last_alert:.0f}s desde último)"
            )
            return
        self._last_alert_ts[codename] = now

        try:
            from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
            breakdown_str = ", ".join(f"{t.split('.')[-1]}={c}" for t, c in topics_breakdown.items())
            await TelegramAlerter().send_message(
                f"⚠️ *Degradação detectada — `{codename}`*\n"
                f"{count} falhas nos últimos {elapsed_s:.0f}s ({breakdown_str}).\n"
                f"O sistema segue rodando — fallback ativo. "
                f"Verifique logs se persistir.",
                level="WARNING",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[AgentDegradationDetector] Telegram alert failed: {exc}")

    # ──────────────────────────────────────────────────────────────────
    # Introspecção (útil para testes e dashboards)
    # ──────────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, int]:
        """Retorna {codename: failures_in_window} para inspeção."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        out: dict[str, int] = {}
        for codename, failures in self._failures.items():
            count = sum(1 for ts, *_ in failures if ts >= cutoff)
            if count > 0:
                out[codename] = count
        return out


# ──────────────────────────────────────────────────────────────────────
# Singleton accessor
# ──────────────────────────────────────────────────────────────────────

_detector: Optional[AgentDegradationDetector] = None


def get_agent_degradation_detector() -> AgentDegradationDetector:
    """Retorna o singleton, criando se necessário."""
    global _detector
    if _detector is None:
        _detector = AgentDegradationDetector()
    return _detector


def start_agent_degradation_detector() -> AgentDegradationDetector:
    """Atalho: cria + inicia o singleton. Chame no bootstrap."""
    d = get_agent_degradation_detector()
    d.start()
    return d


def reset_agent_degradation_detector_for_testing() -> None:
    """Reset completo do singleton — apenas para testes."""
    global _detector
    if _detector is not None:
        _detector.stop()
    _detector = None

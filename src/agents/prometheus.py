"""
src/agents/prometheus.py
=========================
Prometheus — agente permanente de acompanhamento e melhoria.

Diferença em relação ao módulo `src.prompt_engineering` (offline/CLI):
- Aquele é uma BIBLIOTECA + CLI para auditoria.
- Este é um AGENTE RUNTIME (`BaseAgent`) que consome eventos do
  `MekkaEventBus` e registra aprendizados, sem participar de decisão de
  trade e sem chamar LLM.

Eventos consumidos
------------------
- `vision.signal`     → registra um observation point (qual decisão saiu)
- `agent.error`       → conta erro por codename (input para Beast/Mentor)
- `agent.timeout`     → idem
- `cycle.end`         → consolida estatísticas do ciclo

Eventos publicados
------------------
- `prometheus.observation` → toda vez que produz uma observação
- `prometheus.learning`    → quando produz um aprendizado consolidado

Proteções obrigatórias
----------------------
- **Dedup**: cada (event_signature) só conta uma vez dentro de uma janela
  (sha256 dos campos-chave).
- **Throttle**: máximo `MAX_OBS_PER_MIN` observações por minuto;
  máximo `MAX_LEARNINGS_PER_HOUR` aprendizados consolidados por hora.
- **Fail-silent**: exceções em handlers nunca propagam.
- **Opt-in**: agent só é registrado se `PROMETHEUS_AGENT_ENABLED=true`.
- **Sem efeito em decisões de trade**: handlers são *observers*; não
  publicam ordens, não bloqueiam pipeline, não chamam LLM.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections import deque
from typing import Any, Optional

from loguru import logger

from src.agents.base import AgentError, BaseAgent

# ---------------------------------------------------------------------------
# Constantes (limites configuráveis via env)
# ---------------------------------------------------------------------------

DEDUP_WINDOW_S = int(os.environ.get("PROMETHEUS_DEDUP_WINDOW_S", "60"))
MAX_OBS_PER_MIN = int(os.environ.get("PROMETHEUS_MAX_OBS_PER_MIN", "60"))
MAX_LEARNINGS_PER_HOUR = int(
    os.environ.get("PROMETHEUS_MAX_LEARNINGS_PER_HOUR", "12")
)

# Topics consumidos (mantém alinhado com src/services/event_bus.py docstring)
_CONSUMED_TOPICS = (
    "vision.signal",
    "agent.error",
    "agent.timeout",
    "cycle.end",
)

# Topics publicados pelo Prometheus
TOPIC_OBSERVATION = "prometheus.observation"
TOPIC_LEARNING = "prometheus.learning"


def is_agent_enabled() -> bool:
    """Flag de opt-in. Default = False — trading loop não toca Prometheus."""
    return os.environ.get("PROMETHEUS_AGENT_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


# ---------------------------------------------------------------------------
# Observation buffer (estado em memória)
# ---------------------------------------------------------------------------


class _Throttler:
    """Sliding-window counter para rate limit."""

    def __init__(self, max_events: int, window_s: float) -> None:
        self.max = max_events
        self.window = window_s
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._events and now - self._events[0] > self.window:
            self._events.popleft()
        if len(self._events) >= self.max:
            return False
        self._events.append(now)
        return True

    def count(self) -> int:
        return len(self._events)


class _Dedup:
    """Cache de fingerprints recentes para descartar duplicatas."""

    def __init__(self, window_s: float) -> None:
        self.window = window_s
        self._seen: dict[str, float] = {}

    def seen(self, key: str) -> bool:
        now = time.monotonic()
        self._cleanup(now)
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

    def _cleanup(self, now: float) -> None:
        expired = [k for k, ts in self._seen.items() if now - ts > self.window]
        for k in expired:
            del self._seen[k]


# ---------------------------------------------------------------------------
# Prometheus agent
# ---------------------------------------------------------------------------


class Prometheus(BaseAgent[dict[str, Any]]):
    """
    Agente observador. Não decide trade, não chama LLM.

    Lifecycle:
        agent = Prometheus()
        await agent.subscribe()       # registra handlers no event bus
        # ... pipeline rola normalmente ...
        await agent.unsubscribe()     # cleanup (ex.: shutdown)

    Pode também ser usado por `run()` direto para retornar um snapshot
    de estatísticas em qualquer momento (debug/dashboard).
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Prometheus",
            role="Continuous observer & learning recorder (read-only)",
            timeout_s=10.0,
        )
        self._obs_throttle = _Throttler(MAX_OBS_PER_MIN, 60.0)
        self._learning_throttle = _Throttler(MAX_LEARNINGS_PER_HOUR, 3600.0)
        self._dedup = _Dedup(DEDUP_WINDOW_S)
        self._observations: deque[dict[str, Any]] = deque(maxlen=500)
        self._learnings: deque[dict[str, Any]] = deque(maxlen=100)
        # Métricas internas
        self._stats: dict[str, int] = {
            "events_seen": 0,
            "events_deduped": 0,
            "events_throttled": 0,
            "observations_emitted": 0,
            "learnings_emitted": 0,
            "errors_in_handlers": 0,
        }
        self._bus = None  # set on subscribe()
        self._subscribed = False

    # ── lifecycle ────────────────────────────────────────────────────────

    async def subscribe(self) -> bool:
        """Registra handlers no event bus. Idempotente. Retorna sucesso."""
        if self._subscribed:
            return True
        try:
            from src.services.event_bus import get_event_bus
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Prometheus] event_bus indisponível: {exc}")
            return False

        try:
            self._bus = get_event_bus()
            for topic in _CONSUMED_TOPICS:
                self._bus.subscribe(topic, self._on_event)
            self._subscribed = True
            logger.info(
                f"[Prometheus] inscrito em {len(_CONSUMED_TOPICS)} topics"
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Prometheus] subscribe falhou: {exc}")
            return False

    async def unsubscribe(self) -> None:
        """Remove todos os handlers do event bus."""
        if not (self._subscribed and self._bus):
            return
        for topic in _CONSUMED_TOPICS:
            try:
                self._bus.unsubscribe(topic, self._on_event)
            except Exception:  # noqa: BLE001
                pass
        self._subscribed = False

    # ── handlers ─────────────────────────────────────────────────────────

    async def _on_event(self, event: dict[str, Any]) -> None:
        """Handler único para todos os topics. Fail-silent."""
        try:
            self._stats["events_seen"] += 1
            topic = event.get("topic", "unknown")

            # Dedup
            key = self._fingerprint(topic, event)
            if self._dedup.seen(key):
                self._stats["events_deduped"] += 1
                return

            # Throttle
            if not self._obs_throttle.allow():
                self._stats["events_throttled"] += 1
                return

            obs = {
                "topic": topic,
                "ts": time.time(),
                "summary": self._summarize(topic, event),
                "fingerprint": key,
            }
            self._observations.append(obs)
            self._stats["observations_emitted"] += 1

            # Publica observação (best-effort)
            if self._bus is not None:
                try:
                    await self._bus.publish(TOPIC_OBSERVATION, obs)
                except Exception:  # noqa: BLE001
                    pass

            # Consolida aprendizado a cada ciclo
            if topic == "cycle.end":
                await self._maybe_emit_learning(event)
        except Exception as exc:  # noqa: BLE001
            self._stats["errors_in_handlers"] += 1
            logger.debug(f"[Prometheus] handler error: {exc}")

    async def _maybe_emit_learning(self, cycle_event: dict[str, Any]) -> None:
        """Throttled consolidator. Sumariza últimas observações como aprendizado.

        PROM-B/C (2026-05-29): aprendizado enriquecido + auditado.
          - PROM-B: emite PROMETHEUS_LEARNING no audit_log (antes era write-only
            no vault e no bus, sem trilha consultável).
          - PROM-C: enriquece com KPIs reais (win_rate_24h, top error agents,
            distribuição de actions Vision) — antes era só topic_counts,
            insuficiente para qualquer decisão.
        """
        if not self._learning_throttle.allow():
            return
        recent = list(self._observations)[-50:]
        if not recent:
            return
        topics_count: dict[str, int] = {}
        for obs in recent:
            topics_count[obs["topic"]] = topics_count.get(obs["topic"], 0) + 1

        # PROM-C — KPIs derivados das observações em memória
        kpis = self._derive_kpis(recent)

        learning = {
            "ts": time.time(),
            "cycle_id": cycle_event.get("cycle_id"),
            "symbol": cycle_event.get("symbol"),
            "observation_count": len(recent),
            "topic_counts": topics_count,
            "kpis": kpis,                  # PROM-C
            "stats_snapshot": dict(self._stats),
        }
        self._learnings.append(learning)
        self._stats["learnings_emitted"] += 1

        # PROM-B (2026-05-29) — emite PROMETHEUS_LEARNING no audit_log
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433
            await MekkaRepository.log_event(
                agent="Prometheus",
                event="PROMETHEUS_LEARNING",
                severity="INFO",
                message=(
                    f"learning: {len(recent)} obs, "
                    f"{kpis.get('cycles_observed', 0)} cycles, "
                    f"{kpis.get('errors_observed', 0)} errors, "
                    f"action_mix={kpis.get('action_mix', {})}"
                ),
                payload={
                    "topic_counts": topics_count,
                    "kpis": kpis,
                    "observation_count": len(recent),
                    "stats_snapshot": dict(self._stats),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Prometheus] audit emit skipped: {exc}")

        if self._bus is not None:
            try:
                await self._bus.publish(TOPIC_LEARNING, learning)
            except Exception:  # noqa: BLE001
                pass

        # Persistência opt-in no vault. Fail-silent — agente continua se falhar.
        try:
            from src.services.prometheus_vault_writer import record_learning
            written = record_learning(learning)
            if written is not None:
                self._stats["vault_writes"] = self._stats.get("vault_writes", 0) + 1
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Prometheus] vault writer no-op: {exc}")

    @staticmethod
    def _derive_kpis(recent: list[dict[str, Any]]) -> dict[str, Any]:
        """PROM-C (2026-05-29) — extrai KPIs reais das observações.

        Antes: learning só carregava topic_counts.
        Agora:
          - cycles_observed:    # de cycle.end
          - errors_observed:    # de agent.error + agent.timeout
          - top_error_agents:   top 3 agentes que mais erraram
          - action_mix:         {LONG: N, SHORT: N, HOLD: N} de vision.signal
          - executions_observed:# de ironman.exec
        """
        cycles = errors = executions = 0
        error_agents: dict[str, int] = {}
        action_mix: dict[str, int] = {"LONG": 0, "SHORT": 0, "HOLD": 0, "OTHER": 0}

        for obs in recent:
            topic = obs.get("topic", "")
            summary = obs.get("summary", "") or ""
            if topic == "cycle.end":
                cycles += 1
            elif topic in ("agent.error", "agent.timeout"):
                errors += 1
                # summary do tipo "agent.error(IronMan) reason"
                # extraímos nome do agente entre parênteses
                import re as _re  # noqa: WPS433
                m = _re.search(r"\(([^)]+)\)", summary)
                if m:
                    name = m.group(1)
                    error_agents[name] = error_agents.get(name, 0) + 1
            elif topic == "ironman.exec":
                executions += 1
            elif topic == "vision.signal":
                # summary do tipo "Vision(BTC) → LONG"
                for k in ("LONG", "SHORT", "HOLD"):
                    if k in summary:
                        action_mix[k] += 1
                        break
                else:
                    action_mix["OTHER"] += 1

        # Top 3 agents com mais erros
        top_errors = sorted(
            error_agents.items(), key=lambda kv: kv[1], reverse=True,
        )[:3]

        # Action mix em %
        total_actions = sum(action_mix.values()) or 1
        action_pct = {
            k: round(v / total_actions * 100, 1)
            for k, v in action_mix.items() if v > 0
        }

        return {
            "cycles_observed": cycles,
            "errors_observed": errors,
            "executions_observed": executions,
            "top_error_agents": [{"agent": a, "n": n} for a, n in top_errors],
            "action_mix": action_pct,
            "error_rate": round(errors / max(cycles, 1), 3),
        }

    # ── BaseAgent.run() — snapshot de estado ────────────────────────────

    async def _run(self) -> dict[str, Any]:  # type: ignore[override]
        """Retorna snapshot atual — útil para o dashboard ou debug."""
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Estado atual do agente (não-mutante)."""
        return {
            "subscribed": self._subscribed,
            "topics": list(_CONSUMED_TOPICS),
            "stats": dict(self._stats),
            "throttle_state": {
                "observations_in_window": self._obs_throttle.count(),
                "obs_max_per_min": MAX_OBS_PER_MIN,
                "learnings_in_window": self._learning_throttle.count(),
                "learnings_max_per_hour": MAX_LEARNINGS_PER_HOUR,
            },
            "recent_observations": list(self._observations)[-10:],
            "recent_learnings": list(self._learnings)[-5:],
        }

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _fingerprint(topic: str, event: dict[str, Any]) -> str:
        """SHA-256 de campos discriminativos para dedup."""
        parts = [
            topic,
            str(event.get("cycle_id", "")),
            str(event.get("symbol", "")),
            str(event.get("agent", "")),
            str(event.get("action", "")),
            str(event.get("error_type", "")),
        ]
        h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return h[:16]

    @staticmethod
    def _summarize(topic: str, event: dict[str, Any]) -> str:
        """Resumo legível do evento (1 linha)."""
        sym = event.get("symbol", "?")
        if topic == "vision.signal":
            sig = event.get("signal")
            act = getattr(sig, "action", None) or event.get("action", "?")
            return f"Vision({sym}) → {act}"
        if topic.startswith("agent."):
            agent = event.get("agent") or event.get("codename") or "?"
            reason = event.get("reason") or event.get("error", "") or ""
            return f"{topic}({agent}) {reason}"[:120]
        if topic == "cycle.end":
            outcome = event.get("outcome", "?")
            return f"cycle.end({sym}) → {outcome}"
        return f"{topic}({sym})"


# ---------------------------------------------------------------------------
# Singleton helpers (opt-in)
# ---------------------------------------------------------------------------

_instance: Optional[Prometheus] = None


def get_prometheus_agent() -> Optional[Prometheus]:
    """
    Retorna instância singleton. Cria sob demanda apenas se opt-in.
    Em runtime do trading com flag OFF, retorna None — zero overhead.
    """
    global _instance
    if not is_agent_enabled():
        return None
    if _instance is None:
        _instance = Prometheus()
    return _instance


async def start_prometheus_agent() -> Optional[Prometheus]:
    """
    Helper de inicialização. Retorna o agente já inscrito no event bus,
    ou None se desabilitado / falha.
    """
    agent = get_prometheus_agent()
    if agent is None:
        return None
    ok = await agent.subscribe()
    return agent if ok else None

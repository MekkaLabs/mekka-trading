"""
src/agents/cable.py
====================
Cable (Nathan Summers) — Derivatives Intelligence Analyst.

Agente analítico **read-only**, **sem LLM**, **sem chamadas de trade**.
Complementa Deadpool (que olha SQLite local) lendo:
- Dados públicos de derivativos (funding, OI) via `derivatives_intel`
- Histórico pessoal importado via CSV ou (futuramente) API read-only

Não executa ordens. Não altera posições. Não usa credenciais de trade.
Não promete performance futura — apenas estatísticas descritivas.

Lifecycle igual a Prometheus:
- Opt-in via `CABLE_AGENT_ENABLED=true`
- Subscribe ao event_bus para `cycle.end` e produz `cable.report`
- Throttle: 1 report por hora (computar funding history é I/O bound)

Não duplica Deadpool: leem fontes distintas.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from typing import Any, Optional

from loguru import logger

from src.agents.base import BaseAgent

TOPIC_REPORT = "cable.report"
TOPIC_INSIGHT = "cable.insight"

# Limites configuráveis via env
MAX_REPORTS_PER_HOUR = int(os.environ.get("CABLE_MAX_REPORTS_PER_HOUR", "1"))
DEFAULT_SYMBOLS = os.environ.get("CABLE_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
TESTNET = os.environ.get("CABLE_TESTNET", "false").lower() in ("1", "true", "yes")


def is_agent_enabled() -> bool:
    """Opt-in. Default off — zero overhead se desabilitado."""
    return os.environ.get("CABLE_AGENT_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


class _Throttle:
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


class Cable(BaseAgent[dict[str, Any]]):
    """
    Derivatives Intelligence Analyst.

    NUNCA executa ordens. Apenas lê dados públicos e CSVs locais.
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Cable",
            role="Derivatives Intel Analyst (read-only, no LLM, no trade)",
            timeout_s=15.0,
        )
        self._throttle = _Throttle(MAX_REPORTS_PER_HOUR, 3600.0)
        self._reports: deque[dict[str, Any]] = deque(maxlen=20)
        self._stats: dict[str, int] = {
            "cycles_observed": 0,
            "reports_generated": 0,
            "reports_throttled": 0,
            "errors": 0,
        }
        self._bus = None
        self._subscribed = False

    # ── lifecycle ────────────────────────────────────────────────────────

    async def subscribe(self) -> bool:
        if self._subscribed:
            return True
        try:
            from src.services.event_bus import get_event_bus
            self._bus = get_event_bus()
            self._bus.subscribe("cycle.end", self._on_cycle_end)
            self._subscribed = True
            logger.info("[Cable] subscribed to cycle.end (derivatives intel)")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Cable] subscribe failed: {exc}")
            return False

    async def unsubscribe(self) -> None:
        if not (self._subscribed and self._bus):
            return
        try:
            self._bus.unsubscribe("cycle.end", self._on_cycle_end)
        except Exception:  # noqa: BLE001
            pass
        self._subscribed = False

    # ── handlers ────────────────────────────────────────────────────────

    async def _on_cycle_end(self, event: dict[str, Any]) -> None:
        """Fail-silent. Throttled. Read-only."""
        try:
            self._stats["cycles_observed"] += 1
            if not self._throttle.allow():
                self._stats["reports_throttled"] += 1
                return
            report = await self._build_report()
            self._reports.append(report)
            self._stats["reports_generated"] += 1
            if self._bus is not None:
                try:
                    await self._bus.publish(TOPIC_REPORT, report)
                except Exception:  # noqa: BLE001
                    pass
            # REV-4 (2026-05-29): persiste no vault canônico via cable_vault_writer
            # Opt-in via CABLE_VAULT_WRITER_ENABLED. Fail-silent.
            try:
                from src.services import cable_vault_writer as _cvw
                if _cvw.is_enabled():
                    _cvw.record_cable_report(report)
            except Exception as _cvw_exc:  # noqa: BLE001
                logger.debug(f"[Cable] vault writer no-op: {_cvw_exc}")
            # INV-2 (2026-05-29) — audit log: CABLE_REPORT event.
            # Antes: 0 eventos em 7d apesar do Cable rodando.
            try:
                from src.persistence.repository import MekkaRepository  # noqa: WPS433
                snap = report.get("snapshot", {}) or {}
                symbols = list((snap.get("data") or {}).keys())
                await MekkaRepository.log_event(
                    agent="Cable",
                    event="CABLE_REPORT",
                    severity="INFO",
                    message=f"funding/OI snapshot ({len(symbols)} symbols)",
                    payload={
                        "symbols": symbols,
                        "n_insights": len(report.get("insights", []) or []),
                    },
                )
            except Exception as _audit_exc:  # noqa: BLE001
                logger.debug(f"[Cable] audit emit no-op: {_audit_exc}")
        except Exception as exc:  # noqa: BLE001
            self._stats["errors"] += 1
            logger.debug(f"[Cable] handler error: {exc}")

    async def _build_report(self) -> dict[str, Any]:
        """
        Snapshot derivativos público + agregação. Não usa credenciais.
        """
        from src.services.derivatives_intel import collect_full_snapshot
        snapshot = await collect_full_snapshot(DEFAULT_SYMBOLS, testnet=TESTNET)
        # Computar insights determinísticos
        insights = self._derive_insights(snapshot)
        return {
            "ts": time.time(),
            "snapshot": snapshot,
            "insights": insights,
            "disclaimer": (
                "Métricas descritivas. Não constituem recomendação. "
                "Não garantem performance futura."
            ),
        }

    @staticmethod
    def _derive_insights(snap: dict[str, Any]) -> list[str]:
        """
        Heurísticas simples sobre o snapshot — totalmente determinísticas.
        Cada insight é uma string curta e específica.
        """
        out: list[str] = []
        data = snap.get("data", {})
        for sym, d in data.items():
            fund = (d.get("funding") or {})
            mean = fund.get("mean")
            last = fund.get("last")
            if mean is not None:
                if mean > 0.0005:
                    out.append(
                        f"{sym}: funding 8h MÉDIO POSITIVO ({mean*100:.3f}%) — "
                        "longs pagando shorts. Pode indicar excesso de bullish."
                    )
                elif mean < -0.0005:
                    out.append(
                        f"{sym}: funding 8h MÉDIO NEGATIVO ({mean*100:.3f}%) — "
                        "shorts pagando longs. Pode indicar bearish saturado."
                    )
            if last is not None and mean is not None:
                delta = (last - mean) * 100
                if abs(delta) > 0.02:
                    direction = "acima" if delta > 0 else "abaixo"
                    out.append(
                        f"{sym}: funding ATUAL {direction} da média "
                        f"({delta:+.3f}pp) — viés mudando."
                    )
            oi = (d.get("open_interest") or {}).get("value")
            if oi is not None:
                out.append(f"{sym}: OI corrente = {oi:,.0f} contratos.")
        if not out:
            out.append("Sem insights — dados indisponíveis ou ainda carregando.")
        return out

    # ── snapshot ────────────────────────────────────────────────────────

    async def _run(self) -> dict[str, Any]:  # type: ignore[override]
        """Snapshot atual — útil para dashboard ou debug."""
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "subscribed": self._subscribed,
            "stats": dict(self._stats),
            "throttle": {
                "reports_in_window": self._throttle.count(),
                "max_per_hour": MAX_REPORTS_PER_HOUR,
            },
            "symbols_watched": DEFAULT_SYMBOLS,
            "auth_available_personal_trades": bool(
                os.environ.get("CABLE_BINANCE_API_KEY")
                and os.environ.get("CABLE_BINANCE_API_SECRET")
            ),
            "recent_reports": list(self._reports)[-3:],
        }


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

_instance: Optional[Cable] = None


def get_cable_agent() -> Optional[Cable]:
    """Singleton opt-in. None se desabilitado."""
    global _instance
    if not is_agent_enabled():
        return None
    if _instance is None:
        _instance = Cable()
    return _instance


async def start_cable_agent() -> Optional[Cable]:
    """Helper de inicialização. Subscreve ao event_bus."""
    agent = get_cable_agent()
    if agent is None:
        return None
    ok = await agent.subscribe()
    return agent if ok else None

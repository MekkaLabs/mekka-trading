"""
src/dashboard/handlers/derivatives_intel.py
============================================
Handler do painel "Inteligência de Derivativos".

Consome:
- `Cable.snapshot()` quando o agente runtime está ativo
  (CABLE_AGENT_ENABLED=true)
- `derivatives_intel.collect_full_snapshot()` direto quando o agente
  ainda não rodou um report (cold start)

Read-only, fail-soft, cache 30s.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from src.dashboard.server import MekkaDashboardServer


_CACHE_TTL_S = 30.0
_cache: dict[str, Any] = {"ts": 0.0, "payload": None}


def _cable_snapshot() -> dict[str, Any]:
    """Snapshot do Cable agent. Vazio se desabilitado."""
    try:
        from src.agents.cable import get_cable_agent
        agent = get_cable_agent()
        if agent is None:
            return {"enabled": False, "subscribed": False, "stats": {}, "reports": []}
        snap = agent.snapshot()
        return {
            "enabled": True,
            "subscribed": snap.get("subscribed", False),
            "stats": snap.get("stats", {}),
            "symbols_watched": snap.get("symbols_watched", []),
            "auth_personal_trades": snap.get("auth_available_personal_trades", False),
            "throttle": snap.get("throttle", {}),
            "reports": snap.get("recent_reports", []),
        }
    except Exception:  # noqa: BLE001
        return {"enabled": False, "subscribed": False, "stats": {}, "reports": []}


async def _live_snapshot(symbols: list[str], testnet: bool) -> dict[str, Any]:
    """Snapshot DIRETO (sem agent) — usa quando Cable ainda não gerou report."""
    try:
        from src.services.derivatives_intel import collect_full_snapshot
        return await collect_full_snapshot(symbols, testnet=testnet)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "symbols": symbols}


async def handle_get(
    server: "MekkaDashboardServer",
    request: web.Request,
) -> web.Response:
    """
    GET /api/cable/snapshot[?symbols=BTCUSDT,ETHUSDT][&testnet=true]

    Sem cache cliente (no-store no front recomendado).
    """
    qs = request.rel_url.query
    symbols_raw = qs.get("symbols", "BTCUSDT,ETHUSDT")
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()][:10]
    testnet = qs.get("testnet", "false").lower() in ("1", "true", "yes")

    now = time.monotonic()
    cached = _cache.get("payload")
    if cached and (now - _cache["ts"]) < _CACHE_TTL_S:
        return web.json_response(cached)

    try:
        cable = _cable_snapshot()
        # Se agent já tem report recente, usa ele direto (não chama HTTP de novo)
        if cable.get("reports"):
            latest = cable["reports"][-1]
            payload = {
                "ts": time.time(),
                "source": "cable_agent",
                "cable_status": {k: v for k, v in cable.items() if k != "reports"},
                "latest_report": latest,
                "disclaimer": latest.get("disclaimer"),
            }
        else:
            # Cold path — chama direto
            live = await _live_snapshot(symbols, testnet=testnet)
            payload = {
                "ts": time.time(),
                "source": "live_fetch",
                "cable_status": cable,
                "snapshot": live,
                "disclaimer": (
                    "Métricas descritivas. Backtests/históricos NÃO garantem "
                    "performance futura. Read-only — sem ordens executadas."
                ),
            }
        _cache["ts"] = now
        _cache["payload"] = payload
        return web.json_response(payload)
    except Exception as exc:  # noqa: BLE001
        return web.json_response(
            {
                "ts": time.time(),
                "error": f"{type(exc).__name__}: {exc}",
                "cable_status": {"enabled": False},
                "disclaimer": "Erro de coleta — payload mínimo.",
            },
            status=200,  # 200 pra frontend renderizar estado de erro
        )

"""
src/dashboard/handlers/memory_hub.py
======================================
Handlers para o Memory Hub do dashboard.

Endpoints:
  GET /api/memory/snapshot       → agrega 6 camadas + bridge metadata
  GET /api/improvements/queued   → IMPs paradas + sugestões de match
  POST /api/improvements/reconcile-manual {rec_id, commit_sha, summary}
                                  → operador confirma match manual

Read-only por design exceto o POST de reconciliação (que muta apenas
o pr_tracker — não toca em IMP-*.md nem em git).

Cache de 10s no snapshot para evitar varredura agressiva.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from src.dashboard.server import MekkaDashboardServer


_SNAPSHOT_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_QUEUED_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_CACHE_TTL_S = 10.0


async def handle_memory_snapshot(
    server: "MekkaDashboardServer", request: web.Request,
) -> web.Response:
    """GET /api/memory/snapshot — métricas agregadas das 6 camadas."""
    now = time.monotonic()
    cached = _SNAPSHOT_CACHE.get("payload")
    if cached and (now - _SNAPSHOT_CACHE["ts"]) < _CACHE_TTL_S:
        return web.json_response(cached)
    try:
        from src.services.improvement_memory_bridge import memory_snapshot
        payload = memory_snapshot()
        _SNAPSHOT_CACHE["ts"] = now
        _SNAPSHOT_CACHE["payload"] = payload
        return web.json_response(payload)
    except Exception as exc:  # noqa: BLE001
        return web.json_response(
            {"error": f"{type(exc).__name__}: {exc}", "layers": {}}, status=200,
        )


async def handle_improvements_queued(
    server: "MekkaDashboardServer", request: web.Request,
) -> web.Response:
    """GET /api/improvements/queued — IMPs paradas + matches sugeridos."""
    try:
        days = int(request.rel_url.query.get("days", 30))
        if days < 1 or days > 365:
            days = 30
    except (ValueError, TypeError):
        days = 30

    now = time.monotonic()
    key = f"days={days}"
    cached = _QUEUED_CACHE.get("payload")
    if cached and (now - _QUEUED_CACHE["ts"]) < _CACHE_TTL_S and _QUEUED_CACHE.get("key") == key:
        return web.json_response(cached)
    try:
        from src.services.improvement_memory_bridge import auto_reconcile_dry_run
        payload = auto_reconcile_dry_run(days=days)
        _QUEUED_CACHE["ts"] = now
        _QUEUED_CACHE["key"] = key
        _QUEUED_CACHE["payload"] = payload
        return web.json_response(payload)
    except Exception as exc:  # noqa: BLE001
        return web.json_response(
            {"error": f"{type(exc).__name__}: {exc}", "candidates": {}, "no_match": []},
            status=200,
        )


async def handle_reconcile_manual(
    server: "MekkaDashboardServer", request: web.Request,
) -> web.Response:
    """POST /api/improvements/reconcile-manual {rec_id, commit_sha, summary}."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    rec_id = (body or {}).get("rec_id")
    commit_sha = (body or {}).get("commit_sha")
    summary = (body or {}).get("summary", "")
    if not rec_id or not commit_sha:
        return web.json_response(
            {"ok": False, "error": "rec_id e commit_sha são obrigatórios"}, status=400,
        )
    try:
        from src.services.improvement_memory_bridge import mark_resolved_manual
        result = mark_resolved_manual(rec_id=rec_id, commit_sha=commit_sha, summary=summary)
        # Invalida cache do queued
        _QUEUED_CACHE["ts"] = 0.0
        return web.json_response(result)
    except Exception as exc:  # noqa: BLE001
        return web.json_response(
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500,
        )

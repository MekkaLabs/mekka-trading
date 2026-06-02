"""
src/dashboard/handlers/system.py
=================================
Handlers do control plane do runtime — liga/desliga/reinicia/status do
loop principal de trading (RuntimeController).

Extraído de server.py em IMP-7cf025b8f64d [1/N]. Comportamento idêntico
ao original — apenas localização movida para reduzir 6951 linhas.

ROTAS COBERTAS
--------------
    GET  /api/system/status   → system_status
    POST /api/system/start    → system_start
    POST /api/system/stop     → system_stop   (body: {"confirm":"STOP"})
    POST /api/system/reboot   → system_reboot (body: {"confirm":"REBOOT"})

Comandos correspondentes no Telegram: /sistema, /ligar, /desligar, /reboot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from src.dashboard.server import MekkaDashboardServer


async def system_status(
    server: "MekkaDashboardServer",
    _request: web.Request,
) -> web.Response:
    """Estado atual do runtime. Read-only; sem controller acoplado o
    estado é 'unknown' (ex.: dashboard rodando sem run.py)."""
    if server._runtime is None:
        return web.json_response({"state": "unknown", "running": False})
    return web.json_response(server._runtime.status())


async def system_start(
    server: "MekkaDashboardServer",
    _request: web.Request,
) -> web.Response:
    """Liga o runtime. Idempotente (o controller trata o no-op)."""
    if server._runtime is None:
        return web.json_response({"error": "no runtime controller"}, status=503)
    result = await server._runtime.start()
    return web.json_response(result)


async def system_stop(
    server: "MekkaDashboardServer",
    request: web.Request,
) -> web.Response:
    """Desliga o runtime — cancela o loop e cessa todo token spend.
    Exige body {"confirm":"STOP"} para evitar parada acidental."""
    if server._runtime is None:
        return web.json_response({"error": "no runtime controller"}, status=503)
    body = await server._safe_json_body(request)
    if not isinstance(body, dict) or str(body.get("confirm") or "").upper() != "STOP":
        return web.json_response({"error": "confirm required"}, status=400)
    result = await server._runtime.stop()
    return web.json_response(result)


async def system_reboot(
    server: "MekkaDashboardServer",
    request: web.Request,
) -> web.Response:
    """Reinicia o runtime (stop seguido de start). Exige
    body {"confirm":"REBOOT"}."""
    if server._runtime is None:
        return web.json_response({"error": "no runtime controller"}, status=503)
    body = await server._safe_json_body(request)
    if not isinstance(body, dict) or str(body.get("confirm") or "").upper() != "REBOOT":
        return web.json_response({"error": "confirm required"}, status=400)
    result = await server._runtime.reboot()
    return web.json_response(result)

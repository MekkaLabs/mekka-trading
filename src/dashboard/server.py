from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from src.config.settings import settings
from src.persistence.repository import MekkaRepository


STATIC_DIR = Path(__file__).resolve().parent / "static"


class MekkaDashboardServer:
    def __init__(self) -> None:
        self._app = web.Application()
        self._sockets: set[web.WebSocketResponse] = set()
        self._broadcast_task: asyncio.Task[Any] | None = None
        self._configure_routes()
        self._app.on_startup.append(self._on_startup)
        self._app.on_shutdown.append(self._on_shutdown)

    @property
    def app(self) -> web.Application:
        return self._app

    def _configure_routes(self) -> None:
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/api/overview", self._handle_overview)
        self._app.router.add_get("/api/signals", self._handle_signals)
        self._app.router.add_get("/api/trades", self._handle_trades)
        self._app.router.add_get("/api/audit", self._handle_audit)
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_static("/static", path=STATIC_DIR)

    async def _on_startup(self, _: web.Application) -> None:
        await MekkaRepository.initialize()
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    async def _on_shutdown(self, _: web.Application) -> None:
        if self._broadcast_task is not None:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
        for ws in list(self._sockets):
            await ws.close(code=1001, message=b"server shutdown")

    async def _handle_index(self, _: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def _handle_overview(self, _: web.Request) -> web.Response:
        payload = await self._collect_payload(include_tables=False)
        return web.json_response(payload["overview"])

    async def _handle_signals(self, request: web.Request) -> web.Response:
        limit = _safe_limit(request.query.get("limit"), default=20, max_value=200)
        signals = await MekkaRepository.list_recent_signals(limit=limit)
        data = [
            {
                "id": s.id,
                "timestamp": s.timestamp.isoformat(),
                "symbol": s.symbol,
                "action": s.action,
                "confidence": s.confidence,
                "leverage": s.leverage,
                "risk_reward": s.risk_reward,
                "is_actionable": s.is_actionable,
                "reasoning": s.reasoning,
                "fallback": s.fallback,
            }
            for s in signals
        ]
        return web.json_response(data)

    async def _handle_trades(self, request: web.Request) -> web.Response:
        limit = _safe_limit(request.query.get("limit"), default=20, max_value=200)
        trades = await MekkaRepository.list_recent_trades(limit=limit)
        data = [
            {
                "id": t.id,
                "timestamp": t.timestamp.isoformat(),
                "symbol": t.symbol,
                "status": t.status,
                "is_paper": t.is_paper,
                "side": t.side,
                "quantity": t.quantity,
                "avg_price": t.avg_price,
                "notional_usd": t.notional_usd,
                "error": t.error,
            }
            for t in trades
        ]
        return web.json_response(data)

    async def _handle_audit(self, request: web.Request) -> web.Response:
        limit = _safe_limit(request.query.get("limit"), default=50, max_value=500)
        rows = await MekkaRepository.list_recent_audit(limit=limit)
        data = [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "agent": r.agent,
                "event": r.event,
                "symbol": r.symbol,
                "severity": r.severity,
                "message": r.message,
                "payload": r.payload or {},
            }
            for r in rows
        ]
        return web.json_response(data)

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)

        self._sockets.add(ws)
        await ws.send_str(json.dumps(await self._collect_payload(include_tables=True)))

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT and msg.data == "ping":
                    await ws.send_str("pong")
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._sockets.discard(ws)

        return ws

    async def _broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(2.0)
            if not self._sockets:
                continue
            payload = json.dumps(await self._collect_payload(include_tables=True))
            stale: list[web.WebSocketResponse] = []
            for ws in self._sockets:
                if ws.closed:
                    stale.append(ws)
                    continue
                try:
                    await ws.send_str(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self._sockets.discard(ws)

    async def _collect_payload(self, include_tables: bool) -> dict:
        overview = await MekkaRepository.get_overview()
        payload = {
            "overview": {
                **overview,
                "mode": settings.mode_label,
                "paper_trading": settings.paper_trading,
                "network": settings.hyperliquid_network,
                "assets": settings.trading_assets,
            }
        }
        if not include_tables:
            return payload

        signals = await MekkaRepository.list_recent_signals(limit=12)
        trades = await MekkaRepository.list_recent_trades(limit=12)
        audits = await MekkaRepository.list_recent_audit(limit=20)

        payload["signals"] = [
            {
                "timestamp": s.timestamp.isoformat(),
                "symbol": s.symbol,
                "action": s.action,
                "confidence": s.confidence,
                "is_actionable": s.is_actionable,
            }
            for s in signals
        ]
        payload["trades"] = [
            {
                "timestamp": t.timestamp.isoformat(),
                "symbol": t.symbol,
                "status": t.status,
                "side": t.side,
                "notional_usd": t.notional_usd,
                "is_paper": t.is_paper,
            }
            for t in trades
        ]
        payload["audit"] = [
            {
                "timestamp": r.timestamp.isoformat(),
                "agent": r.agent,
                "event": r.event,
                "severity": r.severity,
                "message": r.message,
            }
            for r in audits
        ]
        return payload


async def run_dashboard_server(host: str = "0.0.0.0", port: int = 8787) -> None:
    server = MekkaDashboardServer()
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


def _safe_limit(raw: str | None, default: int, max_value: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, min(value, max_value))

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
import csv
import io
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from src.config.settings import settings
from src.persistence.repository import MekkaRepository


STATIC_DIR = Path(__file__).resolve().parent / "static"
SNAPSHOT_DIR = Path("data/dashboard_snapshots")
HERO_LAYER = {
    "Superman": "L1",
    "DoctorStrange": "L1",
    "BlackPanther": "L1",
    "Thor": "L1",
    "Aquaman": "L1",
    "SpiderMan": "L1",
    "Vision": "L2",
    "ProfessorX": "L2",
    "Batman": "L3",
    "IronMan": "L3",
    "NickFury": "L4",
    "PortfolioManager": "L4",  # Story 028 — drift fix
    "DailyPnLWriter": "L4",  # Story 028 — service-layer audit events
}


class MekkaDashboardServer:
    def __init__(self) -> None:
        self._app = web.Application()
        self._sockets: set[web.WebSocketResponse] = set()
        self._broadcast_task: asyncio.Task[Any] | None = None
        self._last_snapshot_minute: str | None = None
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
        self._app.router.add_get("/api/replay", self._handle_replay)
        self._app.router.add_get("/api/replay/snapshots", self._handle_replay_snapshots)
        self._app.router.add_get("/api/replay/export", self._handle_replay_export)
        self._app.router.add_get("/api/replay/compare", self._handle_replay_compare)
        self._app.router.add_get("/api/replay/incident/latest", self._handle_incident_latest)
        self._app.router.add_get(
            "/api/replay/incident/latest/download", self._handle_incident_download
        )
        self._app.router.add_get("/api/replay/timeseries", self._handle_replay_timeseries)
        self._app.router.add_get("/api/incidents/queue", self._handle_incidents_queue)
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_static("/static", path=STATIC_DIR)

    async def _on_startup(self, _: web.Application) -> None:
        await MekkaRepository.initialize()
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
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

    async def _handle_replay_snapshots(self, _: web.Request) -> web.Response:
        files = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")],
            reverse=True,
        )
        return web.json_response({"snapshots": files})

    async def _handle_replay(self, request: web.Request) -> web.Response:
        snapshot_name = request.query.get("snapshot", "latest.json")
        if "/" in snapshot_name or ".." in snapshot_name:
            return web.json_response({"error": "invalid snapshot name"}, status=400)

        path = SNAPSHOT_DIR / snapshot_name
        if not path.exists():
            return web.json_response({"error": "snapshot not found"}, status=404)

        raw = await asyncio.to_thread(path.read_text, "utf-8")
        payload = json.loads(raw)
        return web.json_response(payload)

    async def _handle_replay_export(self, request: web.Request) -> web.Response:
        start = request.query.get("start")
        end = request.query.get("end")
        start_utc = request.query.get("start_utc")
        end_utc = request.query.get("end_utc")
        export_format = (request.query.get("format") or "json").lower()

        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")])
        if not files:
            return web.json_response({"error": "no snapshots"}, status=404)

        selected = _slice_snapshots(files, start, end)
        if not selected:
            return web.json_response({"error": "empty range"}, status=404)

        rows = []
        parsed_start = _parse_iso_utc(start_utc)
        parsed_end = _parse_iso_utc(end_utc)
        for name in selected:
            raw = await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
            payload = json.loads(raw)
            ov = payload.get("overview", {})
            ts = _parse_iso_utc(ov.get("timestamp"))
            if parsed_start and ts and ts < parsed_start:
                continue
            if parsed_end and ts and ts > parsed_end:
                continue
            rows.append(
                {
                    "snapshot": name,
                    "timestamp": ov.get("timestamp"),
                    "mode": ov.get("mode"),
                    "network": ov.get("network"),
                    "total_signals": ov.get("total_signals"),
                    "total_trades": ov.get("total_trades"),
                    "trades_today": ov.get("trades_today"),
                    "executions_today": ov.get("executions_today"),
                    "alerts_count": len(payload.get("global_alerts", [])),
                }
            )
        if not rows:
            return web.json_response({"error": "empty range after utc filter"}, status=404)

        if export_format == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            return web.Response(
                text=output.getvalue(),
                content_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=mekka-replay-export.csv"},
            )

        return web.json_response({"items": rows, "count": len(rows)})

    async def _handle_replay_compare(self, request: web.Request) -> web.Response:
        a = request.query.get("a")
        b = request.query.get("b")
        if not a or not b:
            return web.json_response({"error": "params a and b are required"}, status=400)
        if "/" in a or "/" in b or ".." in a or ".." in b:
            return web.json_response({"error": "invalid snapshot name"}, status=400)

        path_a = SNAPSHOT_DIR / a
        path_b = SNAPSHOT_DIR / b
        if not path_a.exists() or not path_b.exists():
            return web.json_response({"error": "snapshot not found"}, status=404)

        payload_a = json.loads(await asyncio.to_thread(path_a.read_text, "utf-8"))
        payload_b = json.loads(await asyncio.to_thread(path_b.read_text, "utf-8"))
        return web.json_response(_compare_snapshots(a, payload_a, b, payload_b))

    async def _handle_incident_latest(self, _: web.Request) -> web.Response:
        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True)
        if not files:
            return web.json_response({"error": "no snapshots"}, status=404)
        for name in files:
            payload = json.loads(await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8"))
            alerts = payload.get("global_alerts", [])
            has_kill = any("KILL_SWITCH" in str(a.get("code", "")) for a in alerts)
            if has_kill:
                prev = files[min(files.index(name) + 1, len(files) - 1)]
                payload_prev = json.loads(await asyncio.to_thread((SNAPSHOT_DIR / prev).read_text, "utf-8"))
                compare = _compare_snapshots(prev, payload_prev, name, payload)
                severity = _compute_severity(payload)
                return web.json_response(
                    {
                        "incident_snapshot": name,
                        "baseline_snapshot": prev,
                        "alerts": alerts,
                        "compare": compare,
                        "overview": payload.get("overview", {}),
                        "severity": severity,
                    }
                )
        return web.json_response({"error": "no kill switch incident found"}, status=404)

    async def _handle_incident_download(self, _: web.Request) -> web.Response:
        """Direct JSON download of the most recent incident bundle.

        Prefers persisted ``incident-bundle-*.json`` files (saved automatically
        when a kill switch is detected). If none exist, falls back to building
        an in-memory bundle from the latest snapshot containing a kill switch.
        """
        bundles = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("incident-bundle-*.json")],
            reverse=True,
        )
        if bundles:
            name = bundles[0]
            raw = await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
            return web.Response(
                text=raw,
                content_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{name}"'},
            )

        # Fallback: build from latest kill-switch snapshot.
        files = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True
        )
        for name in files:
            payload = json.loads(
                await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
            )
            alerts = payload.get("global_alerts", [])
            has_kill = any("KILL_SWITCH" in str(a.get("code", "")) for a in alerts)
            if has_kill:
                bundle = {
                    "captured_at": (payload.get("overview") or {}).get("timestamp"),
                    "source_snapshot": name,
                    "overview": payload.get("overview", {}),
                    "alerts": alerts,
                    "risk_heatmap": payload.get("risk_heatmap", []),
                    "hero_sla": payload.get("hero_sla", []),
                    "severity": _compute_severity(payload),
                }
                filename = f"incident-bundle-from-{name}"
                return web.Response(
                    text=json.dumps(bundle, ensure_ascii=True),
                    content_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )

        return web.json_response({"error": "no incident bundle available"}, status=404)

    async def _handle_replay_timeseries(self, request: web.Request) -> web.Response:
        """Aggregated time-series of signals/trades/alerts across snapshots.

        Used by the frontend to render Chart.js line charts in the replay panel.
        """
        limit = _safe_limit(request.query.get("limit"), default=120, max_value=720)
        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")])
        files = files[-limit:]
        if not files:
            return web.json_response({"items": [], "count": 0})

        items: list[dict[str, Any]] = []
        for name in files:
            try:
                payload = json.loads(
                    await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
                )
            except (OSError, json.JSONDecodeError):
                continue
            ov = payload.get("overview") or {}
            alerts = payload.get("global_alerts") or []
            severity = _compute_severity(payload)
            items.append(
                {
                    "snapshot": name,
                    "timestamp": ov.get("timestamp"),
                    "signals_total": int(ov.get("total_signals") or 0),
                    "trades_total": int(ov.get("total_trades") or 0),
                    "trades_today": int(ov.get("trades_today") or 0),
                    "executions_today": int(ov.get("executions_today") or 0),
                    "alerts_count": len(alerts),
                    "severity_score": severity["score"],
                    "severity_tier": severity["tier"],
                }
            )
        return web.json_response({"items": items, "count": len(items)})

    async def _handle_incidents_queue(self, request: web.Request) -> web.Response:
        """Investigation queue: snapshots ranked by incident severity score."""
        limit = _safe_limit(request.query.get("limit"), default=25, max_value=200)
        scan = _safe_limit(request.query.get("scan"), default=200, max_value=1000)

        files = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True
        )
        files = files[:scan]
        if not files:
            return web.json_response({"items": [], "count": 0})

        items: list[dict[str, Any]] = []
        for name in files:
            try:
                payload = json.loads(
                    await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
                )
            except (OSError, json.JSONDecodeError):
                continue
            severity = _compute_severity(payload)
            if severity["score"] <= 0:
                continue
            ov = payload.get("overview") or {}
            items.append(
                {
                    "snapshot": name,
                    "timestamp": ov.get("timestamp"),
                    "score": severity["score"],
                    "tier": severity["tier"],
                    "drivers": severity["drivers"],
                    "alerts": payload.get("global_alerts", []),
                    "kill_switch": severity["drivers"].get("kill_switch", 0) > 0,
                }
            )
        items.sort(key=lambda x: (x["score"], x["timestamp"] or ""), reverse=True)
        return web.json_response({"items": items[:limit], "count": len(items)})

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
            snapshot = await self._collect_payload(include_tables=True)
            await self._persist_snapshot(snapshot)
            payload = json.dumps(snapshot)
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
        audits = await MekkaRepository.list_recent_audit(limit=80)

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
                "symbol": r.symbol,
                "severity": r.severity,
                "message": r.message,
                "payload": r.payload or {},
            }
            for r in audits
        ]
        payload["layers"] = _build_layers_snapshot(audits)
        payload["timeline"] = _build_timeline(audits)
        payload["symbol_timeline"] = _build_symbol_timeline(audits)
        payload["risk_heatmap"] = _build_risk_heatmap(audits)
        payload["risk_drilldown"] = _build_risk_drilldown(audits)
        payload["anomalies"] = _build_spiderman_anomalies(audits)
        payload["global_alerts"] = _build_global_alerts(audits)
        payload["hero_sla"] = _build_hero_sla(audits)
        return payload

    async def _persist_snapshot(self, payload: dict) -> None:
        now = datetime.now(timezone.utc)
        data = json.dumps(payload, ensure_ascii=True)
        latest = SNAPSHOT_DIR / "latest.json"
        await asyncio.to_thread(latest.write_text, data, "utf-8")

        alerts = payload.get("global_alerts", [])
        has_kill = any("KILL_SWITCH" in str(a.get("code", "")) for a in alerts)
        if has_kill:
            bundle = SNAPSHOT_DIR / f"incident-bundle-{now.strftime('%Y%m%dT%H%M%S')}.json"
            await asyncio.to_thread(
                bundle.write_text,
                json.dumps(
                    {
                        "captured_at": now.isoformat(),
                        "overview": payload.get("overview", {}),
                        "alerts": alerts,
                        "risk_heatmap": payload.get("risk_heatmap", []),
                        "hero_sla": payload.get("hero_sla", []),
                        "severity": _compute_severity(payload),
                    },
                    ensure_ascii=True,
                ),
                "utf-8",
            )

        minute_key = now.strftime("%Y%m%dT%H%M")
        if minute_key != self._last_snapshot_minute:
            self._last_snapshot_minute = minute_key
            path = SNAPSHOT_DIR / f"snapshot-{minute_key}.json"
            await asyncio.to_thread(path.write_text, data, "utf-8")


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


def _build_layers_snapshot(audits: list[Any]) -> dict[str, Any]:
    hero_latest: dict[str, Any] = {}
    for row in audits:
        if row.agent not in HERO_LAYER:
            continue
        current = hero_latest.get(row.agent)
        if current is None or row.timestamp > current.timestamp:
            hero_latest[row.agent] = row

    layers: dict[str, dict[str, Any]] = {
        "L1": {"label": "Market Analysis", "heroes": []},
        "L2": {"label": "Strategy", "heroes": []},
        "L3": {"label": "Risk & Execution", "heroes": []},
        "L4": {"label": "Command & Control", "heroes": []},
    }

    now = max((r.timestamp for r in audits), default=None)
    for hero, layer in HERO_LAYER.items():
        row = hero_latest.get(hero)
        status = "idle"
        age_s = None
        event = "NO_EVENT"
        if row is not None:
            event = row.event
            if row.severity in ("ERROR", "CRITICAL"):
                status = "critical"
            elif row.severity == "WARNING":
                status = "warning"
            else:
                status = "active"
            if now is not None:
                age_s = int((now - row.timestamp).total_seconds())
        layers[layer]["heroes"].append(
            {
                "hero": hero,
                "status": status,
                "event": event,
                "age_seconds": age_s,
            }
        )

    cycle_window_seconds = None
    if len(audits) >= 2:
        cycle_window_seconds = int((audits[0].timestamp - audits[-1].timestamp).total_seconds())

    return {
        "cycle_window_seconds": cycle_window_seconds,
        "items": layers,
    }


def _build_timeline(audits: list[Any]) -> list[dict[str, Any]]:
    # Latest Nick Fury cycle markers for quick command timeline.
    rows = [r for r in audits if r.agent == "NickFury"]
    rows = sorted(rows, key=lambda r: r.timestamp, reverse=True)[:14]
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "event": r.event,
            "severity": r.severity,
            "message": r.message,
            "symbol": r.symbol,
        }
        for r in rows
    ]


def _build_risk_heatmap(audits: list[Any]) -> list[dict[str, Any]]:
    risk_rows = [r for r in audits if r.agent == "Batman"]
    per_symbol: dict[str, dict[str, Any]] = {}
    for row in risk_rows:
        symbol = row.symbol or "GLOBAL"
        item = per_symbol.setdefault(
            symbol,
            {
                "symbol": symbol,
                "approved": 0,
                "reduced": 0,
                "rejected": 0,
                "kill_switch": 0,
                "warning_count": 0,
                "critical_count": 0,
            },
        )
        event = row.event or ""
        if "APPROVED" in event:
            item["approved"] += 1
        elif "REDUCED" in event:
            item["reduced"] += 1
        elif "KILL_SWITCH" in event:
            item["kill_switch"] += 1
        else:
            item["rejected"] += 1
        if row.severity == "WARNING":
            item["warning_count"] += 1
        if row.severity in ("ERROR", "CRITICAL"):
            item["critical_count"] += 1
    return sorted(per_symbol.values(), key=lambda x: x["symbol"])


def _build_risk_drilldown(audits: list[Any]) -> dict[str, list[dict[str, Any]]]:
    rows = [r for r in audits if r.agent == "Batman"]
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        symbol = r.symbol or "GLOBAL"
        bucket = by_symbol.setdefault(symbol, [])
        payload = r.payload or {}
        bucket.append(
            {
                "timestamp": r.timestamp.isoformat(),
                "event": r.event,
                "severity": r.severity,
                "message": r.message,
                "reasons": payload.get("reasons", []),
                "breached_limits": payload.get("breached", []),
            }
        )
    return by_symbol


def _build_spiderman_anomalies(audits: list[Any]) -> list[dict[str, Any]]:
    rows = [r for r in audits if r.agent == "SpiderMan"]
    rows = sorted(rows, key=lambda r: r.timestamp, reverse=True)[:20]
    data: list[dict[str, Any]] = []
    for r in rows:
        payload = r.payload or {}
        severity = payload.get("severity") or payload.get("anomaly_severity") or r.severity
        should_pause = bool(payload.get("should_pause", False))
        data.append(
            {
                "timestamp": r.timestamp.isoformat(),
                "event": r.event,
                "symbol": r.symbol,
                "severity": str(severity),
                "should_pause": should_pause,
                "message": r.message,
            }
        )
    return data


def _build_symbol_timeline(audits: list[Any]) -> list[dict[str, Any]]:
    tracked_agents = {"ProfessorX", "Vision", "Batman", "IronMan"}
    by_symbol: dict[str, list[Any]] = {}
    for r in audits:
        if r.agent not in tracked_agents:
            continue
        symbol = r.symbol or "GLOBAL"
        by_symbol.setdefault(symbol, []).append(r)

    items: list[dict[str, Any]] = []
    for symbol, rows in by_symbol.items():
        rows_sorted = sorted(rows, key=lambda x: x.timestamp)
        first_ts = rows_sorted[0].timestamp
        last_ts = rows_sorted[-1].timestamp
        duration_s = int((last_ts - first_ts).total_seconds())
        steps = []
        seen = set()
        for r in reversed(rows_sorted):
            if r.agent in seen:
                continue
            seen.add(r.agent)
            steps.append({"agent": r.agent, "event": r.event, "severity": r.severity})
        items.append(
            {
                "symbol": symbol,
                "started_at": first_ts.isoformat(),
                "last_at": last_ts.isoformat(),
                "duration_seconds": duration_s,
                "steps": list(reversed(steps)),
            }
        )
    return sorted(items, key=lambda x: x["last_at"], reverse=True)[:20]


def _build_global_alerts(audits: list[Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    kill_file = Path("data/.kill_switch")
    if kill_file.exists():
        alerts.append(
            {
                "code": "KILL_SWITCH_FILE",
                "severity": "CRITICAL",
                "message": "Kill switch file ativo em data/.kill_switch",
            }
        )

    kill_rows = [
        r for r in audits
        if "KILL_SWITCH" in (r.event or "") or "CYCLE_SKIPPED" in (r.event or "")
    ]
    if kill_rows:
        row = sorted(kill_rows, key=lambda r: r.timestamp, reverse=True)[0]
        alerts.append(
            {
                "code": "KILL_SWITCH_EVENT",
                "severity": "CRITICAL",
                "message": f"{row.agent} reportou {row.event}",
                "timestamp": row.timestamp.isoformat(),
            }
        )

    pause_rows = [r for r in audits if r.agent == "SpiderMan" and bool((r.payload or {}).get("should_pause"))]
    if pause_rows:
        row = sorted(pause_rows, key=lambda r: r.timestamp, reverse=True)[0]
        alerts.append(
            {
                "code": "ANOMALY_PAUSE",
                "severity": "WARNING",
                "message": f"Spider-Man sinalizou pausa em {row.symbol or '-'}",
                "timestamp": row.timestamp.isoformat(),
            }
        )
    return alerts


def _build_hero_sla(audits: list[Any]) -> list[dict[str, Any]]:
    tracked_agents = {"ProfessorX", "Vision", "Batman", "IronMan"}
    by_symbol: dict[str, dict[str, Any]] = {}
    for r in audits:
        if r.agent not in tracked_agents:
            continue
        symbol = r.symbol or "GLOBAL"
        bucket = by_symbol.setdefault(symbol, {})
        if r.agent not in bucket or r.timestamp > bucket[r.agent].timestamp:
            bucket[r.agent] = r

    deltas: dict[str, list[int]] = {a: [] for a in tracked_agents}
    for symbol, points in by_symbol.items():
        _ = symbol
        px = points.get("ProfessorX")
        vi = points.get("Vision")
        ba = points.get("Batman")
        im = points.get("IronMan")

        if px and vi and vi.timestamp >= px.timestamp:
            deltas["Vision"].append(int((vi.timestamp - px.timestamp).total_seconds()))
        if vi and ba and ba.timestamp >= vi.timestamp:
            deltas["Batman"].append(int((ba.timestamp - vi.timestamp).total_seconds()))
        if ba and im and im.timestamp >= ba.timestamp:
            deltas["IronMan"].append(int((im.timestamp - ba.timestamp).total_seconds()))
        if px and im and im.timestamp >= px.timestamp:
            deltas["ProfessorX"].append(int((im.timestamp - px.timestamp).total_seconds()))

    result = []
    for hero in ["ProfessorX", "Vision", "Batman", "IronMan"]:
        values = deltas.get(hero, [])
        avg_s = round(sum(values) / len(values), 2) if values else None
        p95_s = sorted(values)[int((len(values) - 1) * 0.95)] if values else None
        result.append(
            {
                "hero": hero,
                "samples": len(values),
                "avg_seconds": avg_s,
                "p95_seconds": p95_s,
            }
        )
    return result


def _compute_severity(payload: dict) -> dict[str, Any]:
    """Score 0-100 and tier (NONE/LOW/MEDIUM/HIGH/CRITICAL) for a snapshot.

    Drivers considered:
    - kill_switch alerts (file or event)
    - critical / warning alert counts
    - SpiderMan anomalies with should_pause
    - breached_limits across Batman drilldown rows
    - degraded hero SLA (avg_seconds above threshold)
    """
    alerts = payload.get("global_alerts") or []
    anomalies = payload.get("anomalies") or []
    drilldown = payload.get("risk_drilldown") or {}
    hero_sla = payload.get("hero_sla") or []

    kill_switch = sum(1 for a in alerts if "KILL_SWITCH" in str(a.get("code", "")))
    critical_alerts = sum(
        1 for a in alerts if str(a.get("severity", "")).upper() == "CRITICAL"
    )
    warning_alerts = sum(
        1 for a in alerts if str(a.get("severity", "")).upper() == "WARNING"
    )
    anomaly_pause = sum(1 for a in anomalies if bool(a.get("should_pause")))

    breached_count = 0
    for rows in drilldown.values():
        for row in rows or []:
            breached = row.get("breached_limits") or []
            breached_count += len(breached)

    sla_degraded = 0
    for entry in hero_sla:
        avg = entry.get("avg_seconds")
        if isinstance(avg, (int, float)) and avg >= 30:
            sla_degraded += 1

    raw_score = (
        50 * critical_alerts
        + 35 * kill_switch
        + 25 * anomaly_pause
        + 15 * warning_alerts
        + 4 * breached_count
        + 5 * sla_degraded
    )
    score = max(0, min(100, raw_score))

    if score >= 80:
        tier = "CRITICAL"
    elif score >= 50:
        tier = "HIGH"
    elif score >= 20:
        tier = "MEDIUM"
    elif score > 0:
        tier = "LOW"
    else:
        tier = "NONE"

    return {
        "score": score,
        "tier": tier,
        "drivers": {
            "kill_switch": kill_switch,
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "anomaly_pause": anomaly_pause,
            "breached_limits": breached_count,
            "sla_degraded": sla_degraded,
        },
    }


def _slice_snapshots(files: list[str], start: str | None, end: str | None) -> list[str]:
    if start is None and end is None:
        return files
    start_idx = 0
    end_idx = len(files) - 1
    if start is not None and start in files:
        start_idx = files.index(start)
    if end is not None and end in files:
        end_idx = files.index(end)
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    return files[start_idx : end_idx + 1]


def _parse_iso_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except ValueError:
        return None


def _compare_snapshots(name_a: str, a: dict, name_b: str, b: dict) -> dict[str, Any]:
    ov_a = a.get("overview", {})
    ov_b = b.get("overview", {})
    overview_delta = {
        "total_signals": (ov_b.get("total_signals") or 0) - (ov_a.get("total_signals") or 0),
        "total_trades": (ov_b.get("total_trades") or 0) - (ov_a.get("total_trades") or 0),
        "trades_today": (ov_b.get("trades_today") or 0) - (ov_a.get("trades_today") or 0),
        "executions_today": (ov_b.get("executions_today") or 0) - (ov_a.get("executions_today") or 0),
    }

    risk_a = {r["symbol"]: r for r in a.get("risk_heatmap", [])}
    risk_b = {r["symbol"]: r for r in b.get("risk_heatmap", [])}
    all_symbols = sorted(set(risk_a) | set(risk_b))
    risk_delta = []
    for symbol in all_symbols:
        ra = risk_a.get(symbol, {})
        rb = risk_b.get(symbol, {})
        risk_delta.append(
            {
                "symbol": symbol,
                "approved": (rb.get("approved") or 0) - (ra.get("approved") or 0),
                "reduced": (rb.get("reduced") or 0) - (ra.get("reduced") or 0),
                "rejected": (rb.get("rejected") or 0) - (ra.get("rejected") or 0),
                "kill_switch": (rb.get("kill_switch") or 0) - (ra.get("kill_switch") or 0),
            }
        )

    alerts_a = {f'{x.get("code")}::{x.get("message")}' for x in a.get("global_alerts", [])}
    alerts_b = {f'{x.get("code")}::{x.get("message")}' for x in b.get("global_alerts", [])}
    alerts_added = sorted(list(alerts_b - alerts_a))
    alerts_removed = sorted(list(alerts_a - alerts_b))

    sla_a = {x["hero"]: x for x in a.get("hero_sla", [])}
    sla_b = {x["hero"]: x for x in b.get("hero_sla", [])}
    heroes = sorted(set(sla_a) | set(sla_b))
    sla_delta = []
    for hero in heroes:
        ha = sla_a.get(hero, {})
        hb = sla_b.get(hero, {})
        a_avg = ha.get("avg_seconds") or 0
        b_avg = hb.get("avg_seconds") or 0
        sla_delta.append(
            {
                "hero": hero,
                "avg_seconds_delta": round(b_avg - a_avg, 2),
                "samples_delta": (hb.get("samples") or 0) - (ha.get("samples") or 0),
            }
        )

    return {
        "snapshot_a": name_a,
        "snapshot_b": name_b,
        "overview_delta": overview_delta,
        "risk_delta": risk_delta,
        "alerts_added": alerts_added,
        "alerts_removed": alerts_removed,
        "sla_delta": sla_delta,
    }

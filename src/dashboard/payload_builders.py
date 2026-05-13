"""
src/dashboard/payload_builders.py
=================================
Pure functions that turn raw `AuditRecord` lists into the structured
payload sections the dashboard sends over `/ws` and REST.

These helpers do no I/O — they take audits in and return JSON-friendly
dicts/lists. Anything that needs the kill-switch file path or threshold
env vars (e.g. `_build_global_alerts`) stays in `server.py` so this
module remains free of side effects.
"""

from __future__ import annotations

from typing import Any


# Mapping of agent names to their layer in the L1–L4 command structure.
# Used by `build_layers_snapshot` and elsewhere; centralised here so the
# dashboard, tests and future tooling agree on the same source of truth.
HERO_LAYER: dict[str, str] = {
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


def build_layers_snapshot(audits: list[Any]) -> dict[str, Any]:
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
        cycle_window_seconds = int(
            (audits[0].timestamp - audits[-1].timestamp).total_seconds()
        )

    return {"cycle_window_seconds": cycle_window_seconds, "items": layers}


def build_timeline(audits: list[Any]) -> list[dict[str, Any]]:
    """Last 14 NickFury events for the command-timeline panel."""
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


def build_risk_heatmap(audits: list[Any]) -> list[dict[str, Any]]:
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


def build_risk_drilldown(audits: list[Any]) -> dict[str, list[dict[str, Any]]]:
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


def build_spiderman_anomalies(audits: list[Any]) -> list[dict[str, Any]]:
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


def build_symbol_timeline(audits: list[Any]) -> list[dict[str, Any]]:
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
        seen: set[str] = set()
        for r in reversed(rows_sorted):
            if r.agent in seen:
                continue
            seen.add(r.agent)
            steps.append(
                {"agent": r.agent, "event": r.event, "severity": r.severity}
            )
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


def build_hero_sla(
    audits: list[Any], percentile_fn
) -> list[dict[str, Any]]:
    """Latency stats per pipeline hop. ``percentile_fn`` is injected so this
    module doesn't import severity directly (avoids circular deps when the
    severity module wants to import builders later)."""
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

    result: list[dict[str, Any]] = []
    for hero in ["ProfessorX", "Vision", "Batman", "IronMan"]:
        values = deltas.get(hero, [])
        avg_s = round(sum(values) / len(values), 2) if values else None
        p95_s = percentile_fn([float(v) for v in values], 0.95)
        result.append(
            {
                "hero": hero,
                "samples": len(values),
                "avg_seconds": avg_s,
                "p95_seconds": p95_s,
            }
        )
    return result

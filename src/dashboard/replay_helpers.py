"""
src/dashboard/replay_helpers.py
===============================
Pure helpers for the replay/export/compare flow:

- ``slice_snapshots`` — slice a sorted file list by start/end names.
- ``parse_iso_utc``   — tolerant ISO-8601 parser that always returns a
                        timezone-aware datetime in UTC.
- ``compare_snapshots`` — diff two snapshots' overview, risk_heatmap,
                          alerts and hero_sla into a JSON-friendly delta.

No I/O, no imports from `aiohttp` or DB layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def slice_snapshots(
    files: list[str], start: str | None, end: str | None
) -> list[str]:
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


def parse_iso_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except ValueError:
        return None


def compare_snapshots(
    name_a: str, a: dict, name_b: str, b: dict
) -> dict[str, Any]:
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

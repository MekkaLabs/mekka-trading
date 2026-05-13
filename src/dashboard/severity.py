"""
src/dashboard/severity.py
=========================
Incident severity scoring + numeric helpers.

Pure functions, no aiohttp/SQLAlchemy imports — safe to call from tests,
notebooks, or batch jobs.
"""

from __future__ import annotations

import math
from typing import Any


def percentile(values: list[float], p: float) -> float | None:
    """Linearly-interpolated percentile. Returns None for empty input.

    Equivalent to numpy's default ``linear`` method. Used everywhere we
    surface latency metrics (hero SLA, market diagnostics).
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[int(rank)])
    low_v = ordered[low]
    high_v = ordered[high]
    return round(low_v + (high_v - low_v) * (rank - low), 2)


def compute_severity(payload: dict) -> dict[str, Any]:
    """Score 0-100 and tier (NONE/LOW/MEDIUM/HIGH/CRITICAL) for a snapshot.

    Drivers considered:
    - kill_switch alerts (file or event)
    - critical / warning alert counts
    - SpiderMan anomalies with should_pause
    - breached_limits across Batman drilldown rows
    - degraded hero SLA (avg_seconds above threshold)

    The score is intentionally additive: multiple co-occurring problems
    push the tier up rather than offsetting each other. The cap (100)
    ensures the queue ranking stays bounded under spam.
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

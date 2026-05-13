"""
src/dashboard/metrics.py
========================
Prometheus exposition for the dashboard's internal counters / gauges.

The server stores raw values in a plain dict + two latency buffers; this
module turns those into the canonical text format on demand. Keeping the
descriptors in one place makes it easy to extend the panel without
juggling duplicated strings across handlers.
"""

from __future__ import annotations

from typing import Iterable


# Static metric metadata. Anything not listed here gets a sensible default
# ("gauge" + the metric name as help-text) when serialised.
DESCRIPTORS: dict[str, tuple[str, str]] = {
    "broadcasts_total": ("counter", "Number of broadcast loop ticks completed"),
    "broadcasts_errors_total": ("counter", "Broadcast loop iterations that raised"),
    "ws_connections_total": ("counter", "WebSocket upgrades accepted"),
    "ws_connections_rejected_total": (
        "counter",
        "WebSocket upgrades rejected by Origin policy",
    ),
    "ws_messages_sent_total": ("counter", "WebSocket frames sent"),
    "ws_slow_consumers_dropped_total": (
        "counter",
        "Slow WS clients dropped on backpressure",
    ),
    "snapshot_writes_total": ("counter", "Per-minute snapshot files written"),
    "incident_bundle_writes_total": ("counter", "Incident-bundle files written"),
    "killswitch_engaged_total": ("counter", "Kill switches engaged via dashboard"),
    "killswitch_released_total": ("counter", "Kill switches released via dashboard"),
    "payload_cache_hits_total": ("counter", "Hits on the _collect_payload TTL cache"),
    "payload_cache_misses_total": ("counter", "Misses on the _collect_payload TTL cache"),
    "http_requests_total": ("counter", "HTTP requests served"),
    "started_at_unix_seconds": ("gauge", "Server start time (UTC seconds)"),
    "ws_active_connections": ("gauge", "WebSocket connections currently open"),
    "market_breakers_open": ("gauge", "Market provider URLs in open-circuit state"),
    "market_cache_size": ("gauge", "Cached market responses currently held"),
    "payload_collect_latency_ms_p50": ("gauge", "p50 latency of _collect_payload (ms)"),
    "payload_collect_latency_ms_p95": ("gauge", "p95 latency of _collect_payload (ms)"),
    "broadcast_loop_latency_ms_p50": ("gauge", "p50 latency of broadcast tick (ms)"),
    "broadcast_loop_latency_ms_p95": ("gauge", "p95 latency of broadcast tick (ms)"),
    "payload_collect_samples": ("gauge", "Latency samples currently held for payload"),
    "broadcast_loop_samples": ("gauge", "Latency samples currently held for broadcast"),
}


def render_prometheus(values: dict[str, float]) -> str:
    """Serialise a dict of {metric_name: value} into Prometheus text format.

    Every metric is prefixed with ``mekka_`` so consumers can grep cleanly
    even when scraping multiple services into the same Prometheus instance.
    """
    lines: list[str] = []
    for key, value in values.items():
        kind, helptext = DESCRIPTORS.get(key, ("gauge", key))
        lines.append(f"# HELP mekka_{key} {helptext}")
        lines.append(f"# TYPE mekka_{key} {kind}")
        lines.append(f"mekka_{key} {float(value):g}")
    return "\n".join(lines) + "\n"


def derive_runtime_metrics(
    base: dict[str, float],
    *,
    sockets_count: int,
    market_diag: dict,
    market_cache_size: int,
    payload_latencies_ms: list[float],
    broadcast_latencies_ms: list[float],
    percentile_fn,
) -> dict[str, float]:
    """Compose the live snapshot of runtime gauges on top of the durable
    counters dict the server maintains. ``percentile_fn`` is injected so this
    module doesn't depend on `severity.percentile` (avoids cycles)."""
    out = dict(base)
    out["ws_active_connections"] = float(sockets_count)
    out["market_breakers_open"] = float(
        sum(1 for v in market_diag.values() if bool(v.get("breaker_open")))
    )
    out["market_cache_size"] = float(market_cache_size)
    out["payload_collect_latency_ms_p50"] = float(
        percentile_fn(payload_latencies_ms, 0.5) or 0.0
    )
    out["payload_collect_latency_ms_p95"] = float(
        percentile_fn(payload_latencies_ms, 0.95) or 0.0
    )
    out["broadcast_loop_latency_ms_p50"] = float(
        percentile_fn(broadcast_latencies_ms, 0.5) or 0.0
    )
    out["broadcast_loop_latency_ms_p95"] = float(
        percentile_fn(broadcast_latencies_ms, 0.95) or 0.0
    )
    out["payload_collect_samples"] = float(len(payload_latencies_ms))
    out["broadcast_loop_samples"] = float(len(broadcast_latencies_ms))
    return out

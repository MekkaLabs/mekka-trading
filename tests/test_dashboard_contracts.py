from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

import src.dashboard.server as dashboard_server
from src.dashboard.server import MekkaDashboardServer, _diag_public_view


@pytest.fixture()
def snapshot_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(dashboard_server, "SNAPSHOT_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
async def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _noop_init() -> None:
        return None

    monkeypatch.setattr(
        dashboard_server.MekkaRepository,
        "initialize",
        staticmethod(_noop_init),
    )
    app = MekkaDashboardServer().app
    server = TestServer(app)
    c = TestClient(server)
    await c.start_server()
    try:
        yield c
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_health_contract(client: TestClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["service"] == "mekka-dashboard"
    assert "time_utc" in data
    assert "network" in data
    assert "mode" in data


@pytest.mark.asyncio
async def test_incidents_export_csv_header_when_empty(
    client: TestClient,
) -> None:
    resp = await client.get("/api/incidents/export?limit=20")
    assert resp.status == 200
    text = await resp.text()
    assert "snapshot,timestamp,tier,score" in text


@pytest.mark.asyncio
async def test_incidents_export_csv_with_tier_filter(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    payload = {
        "overview": {
            "timestamp": "2026-05-08T00:00:00+00:00",
            "total_signals": 5,
            "total_trades": 2,
            "trades_today": 1,
            "executions_today": 1,
        },
        "global_alerts": [
            {"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL", "message": "x"},
        ],
        "anomalies": [],
        "risk_drilldown": {},
        "hero_sla": [],
    }
    (snapshot_dir / "snapshot-20260508T0000.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    resp = await client.get("/api/incidents/export?tier=CRITICAL&limit=20")
    assert resp.status == 200
    text = await resp.text()
    assert "snapshot-20260508T0000.json" in text
    assert ",CRITICAL," in text


@pytest.mark.asyncio
async def test_market_diagnostics_contract(client: TestClient) -> None:
    resp = await client.get("/api/market/diagnostics")
    assert resp.status == 200
    data = await resp.json()
    assert "items" in data
    assert "cache_size" in data
    assert "time_utc" in data


@pytest.mark.asyncio
async def test_market_status_contract(client: TestClient) -> None:
    resp = await client.get("/api/market/status")
    assert resp.status == 200
    data = await resp.json()
    assert "state" in data
    assert data["state"] in {"unknown", "healthy", "warning", "degraded"}
    assert "breaker_open_keys" in data
    assert "calls" in data
    assert "errors" in data
    assert "stale_served" in data
    assert "time_utc" in data


@pytest.mark.asyncio
async def test_market_status_degraded_when_breaker_open() -> None:
    server = MekkaDashboardServer()
    now = asyncio.get_running_loop().time()
    server._market_diag["k1"] = {
        "calls": 5,
        "cache_hits": 2,
        "stale_served": 1,
        "errors": 4,
        "last_error": "RuntimeError: market provider error (500)",
        "last_latency_ms": 50,
        "avg_latency_ms": 45.0,
        "failure_streak": 4,
        "breaker_open": True,
        "breaker_open_until_s": 10.0,
        "latencies_ms": [40, 45, 50],
    }
    server._market_breaker_until["k1"] = now + 10.0
    resp = await server._handle_market_status(None)  # type: ignore[arg-type]
    data = json.loads(resp.text)
    assert data["state"] == "degraded"
    assert data["breaker_open_keys"] >= 1
    assert data["errors"] >= 1


@pytest.mark.asyncio
async def test_incidents_queue_supports_query_and_offset(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    p1 = {
        "overview": {"timestamp": "2026-05-08T00:00:00+00:00"},
        "global_alerts": [{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL", "message": "first"}],
        "anomalies": [],
        "risk_drilldown": {},
        "hero_sla": [],
    }
    p2 = {
        "overview": {"timestamp": "2026-05-08T00:01:00+00:00"},
        "global_alerts": [{"code": "SPIDERMAN_ANOMALY", "severity": "WARNING", "message": "second"}],
        "anomalies": [{"paused": True, "message": "pause"}],
        "risk_drilldown": {},
        "hero_sla": [],
    }
    (snapshot_dir / "snapshot-20260508T0000.json").write_text(json.dumps(p1), encoding="utf-8")
    (snapshot_dir / "snapshot-20260508T0001.json").write_text(json.dumps(p2), encoding="utf-8")

    r1 = await client.get("/api/incidents/queue?limit=1&offset=0")
    assert r1.status == 200
    d1 = await r1.json()
    assert d1["count"] >= 1
    assert len(d1["items"]) == 1

    r2 = await client.get("/api/incidents/queue?limit=5&q=spiderman")
    assert r2.status == 200
    d2 = await r2.json()
    assert d2["count"] >= 1
    assert any("SPIDERMAN" in str(a.get("code", "")) for a in d2["items"][0]["alerts"])


@pytest.mark.asyncio
async def test_incident_detail_contract(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    older = {
        "overview": {"timestamp": "2026-05-08T00:00:00+00:00", "total_signals": 1, "total_trades": 0},
        "global_alerts": [],
        "risk_heatmap": [],
        "hero_sla": [],
    }
    newer = {
        "overview": {"timestamp": "2026-05-08T00:01:00+00:00", "total_signals": 3, "total_trades": 1},
        "global_alerts": [{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL", "message": "stop"}],
        "risk_heatmap": [],
        "hero_sla": [],
    }
    (snapshot_dir / "snapshot-20260508T0000.json").write_text(json.dumps(older), encoding="utf-8")
    (snapshot_dir / "snapshot-20260508T0001.json").write_text(json.dumps(newer), encoding="utf-8")
    resp = await client.get("/api/incidents/detail?snapshot=snapshot-20260508T0001.json")
    assert resp.status == 200
    data = await resp.json()
    assert data["snapshot"] == "snapshot-20260508T0001.json"
    assert "baseline_snapshot" in data
    assert "severity" in data
    assert "overview" in data
    assert "alerts" in data
    assert "compare" in data


@pytest.mark.asyncio
async def test_market_breaker_uses_stale_cache_when_open() -> None:
    server = MekkaDashboardServer()
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": "1m", "limit": 2}
    key = f"{url}?{json.dumps(params, sort_keys=True)}"
    server._market_cache[key] = (0.0, [{"k": "stale"}])  # expired but still valid as stale fallback
    now = asyncio.get_running_loop().time()
    server._market_breaker_until[key] = now + 10.0
    data = await server._market_get_json(url, params, ttl_s=1.0)
    assert data == [{"k": "stale"}]
    diag = server._market_diag[key]
    assert diag["breaker_open"] is True
    assert diag["stale_served"] >= 1


@pytest.mark.asyncio
async def test_market_endpoints_with_mock_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_market_get_json(self, url, params, ttl_s, allow_error=False):
        if url.endswith("/klines"):
            return [
                [1715126400000, "62000", "62100", "61900", "62050", "123.4"],
                [1715130000000, "62050", "62200", "62000", "62120", "98.7"],
            ]
        if url.endswith("/ticker/24hr"):
            return {
                "lastPrice": "62120",
                "priceChangePercent": "1.25",
                "quoteVolume": "1234567.89",
                "highPrice": "62500",
                "lowPrice": "61000",
            }
        if url.endswith("/depth"):
            return {"bids": [["62100", "1.2"], ["62090", "0.8"]], "asks": [["62110", "1.1"], ["62120", "0.9"]]}
        if url.endswith("/aggTrades"):
            return [{"a": 1, "p": "62120", "q": "0.02", "T": 1715130000000, "m": False}]
        if allow_error:
            return None
        raise RuntimeError("unexpected mock endpoint")

    monkeypatch.setattr(MekkaDashboardServer, "_market_get_json", fake_market_get_json)

    r1 = await client.get("/api/market/candles?symbol=BTCUSDT&timeframe=1h&limit=2")
    assert r1.status == 200
    d1 = await r1.json()
    assert d1["symbol"] == "BTCUSDT"
    assert d1["count"] == 2
    assert d1["candles"][0]["open"] == 62000.0

    r2 = await client.get("/api/market/depth?symbol=BTCUSDT&limit=2")
    assert r2.status == 200
    d2 = await r2.json()
    assert d2["symbol"] == "BTCUSDT"
    assert len(d2["bids"]) == 2
    assert "summary" in d2

    r3 = await client.get("/api/market/trades?symbol=BTCUSDT&limit=1")
    assert r3.status == 200
    d3 = await r3.json()
    assert d3["symbol"] == "BTCUSDT"
    assert d3["count"] == 1
    assert d3["items"][0]["price"] == 62120.0


def test_market_diag_public_view_percentiles() -> None:
    view = _diag_public_view(
        {
            "calls": 10,
            "cache_hits": 4,
            "stale_served": 2,
            "errors": 1,
            "last_error": "RuntimeError: boom",
            "failure_streak": 1,
            "breaker_open": True,
            "breaker_open_until_s": 7.5,
            "last_latency_ms": 30,
            "avg_latency_ms": 25.5,
            "latencies_ms": [10, 20, 25, 30, 40, 100],
        }
    )
    assert view["calls"] == 10
    assert view["cache_hits"] == 4
    assert view["stale_served"] == 2
    assert view["errors"] == 1
    assert view["failure_streak"] == 1
    assert view["breaker_open"] is True
    assert view["breaker_open_until_s"] == 7.5
    assert view["sample_count"] == 6
    assert view["p50_latency_ms"] is not None
    assert view["p95_latency_ms"] is not None
    assert view["p95_latency_ms"] >= view["p50_latency_ms"]

"""
tests/test_dashboard_replay.py
==============================
Cobre os endpoints `/api/replay/*`, `/api/incidents/queue` e o helper
`_compute_severity` do dashboard Mekka.

Estratégia:
- Instanciar `MekkaDashboardServer` e remover hooks de startup/shutdown
  (que dependem de `MekkaRepository.initialize` e do loop de broadcast).
- Monkeypatch `SNAPSHOT_DIR` para um diretório temporário do `tmp_path`.
- Pré-popular snapshots fake (com e sem KILL_SWITCH) e validar respostas.

Run: pytest tests/test_dashboard_replay.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from src.dashboard import server as server_module
from src.dashboard.server import MekkaDashboardServer, _compute_severity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _snap_filename(stamp: str) -> str:
    return f"snapshot-{stamp}.json"


def _make_snapshot(
    *,
    timestamp: str,
    total_signals: int = 10,
    total_trades: int = 5,
    trades_today: int = 1,
    executions_today: int = 1,
    alerts: list[dict] | None = None,
    risk_heatmap: list[dict] | None = None,
    risk_drilldown: dict | None = None,
    anomalies: list[dict] | None = None,
    hero_sla: list[dict] | None = None,
) -> dict:
    return {
        "overview": {
            "timestamp": timestamp,
            "mode": "paper",
            "network": "testnet",
            "total_signals": total_signals,
            "total_trades": total_trades,
            "trades_today": trades_today,
            "executions_today": executions_today,
        },
        "global_alerts": alerts or [],
        "risk_heatmap": risk_heatmap or [],
        "risk_drilldown": risk_drilldown or {},
        "anomalies": anomalies or [],
        "hero_sla": hero_sla or [],
    }


def _write_snapshot(snapshot_dir: Path, name: str, payload: dict) -> Path:
    path = snapshot_dir / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
async def dashboard_client(monkeypatch, tmp_path):
    """Yield (TestClient, snapshot_dir) with startup/shutdown hooks disabled."""
    snapshot_dir = tmp_path / "dashboard_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)

    server = MekkaDashboardServer()
    # Skip DB init + broadcast loop. Tests only exercise stateless replay routes.
    server._app.on_startup.clear()
    server._app.on_shutdown.clear()

    test_server = TestServer(server._app)
    test_client = TestClient(test_server)
    await test_client.start_server()
    try:
        yield test_client, snapshot_dir
    finally:
        await test_client.close()


# ---------------------------------------------------------------------------
# Severity helper
# ---------------------------------------------------------------------------


class TestComputeSeverity:
    def test_empty_payload_is_none_tier(self):
        result = _compute_severity({})
        assert result["score"] == 0
        assert result["tier"] == "NONE"
        assert result["drivers"]["kill_switch"] == 0

    def test_kill_switch_alert_yields_high_or_critical(self):
        payload = {
            "global_alerts": [
                {"code": "KILL_SWITCH_FILE", "severity": "CRITICAL"},
            ]
        }
        result = _compute_severity(payload)
        # 50 (critical) + 35 (kill_switch) = 85 → CRITICAL
        assert result["drivers"]["kill_switch"] == 1
        assert result["drivers"]["critical_alerts"] == 1
        assert result["score"] >= 80
        assert result["tier"] == "CRITICAL"

    def test_warning_only_is_low_or_medium(self):
        payload = {
            "global_alerts": [{"code": "ANOMALY_PAUSE", "severity": "WARNING"}]
        }
        result = _compute_severity(payload)
        assert 0 < result["score"] < 50
        assert result["tier"] in {"LOW", "MEDIUM"}

    def test_drivers_aggregate_pause_and_breaches(self):
        payload = {
            "global_alerts": [{"code": "ANOMALY_PAUSE", "severity": "WARNING"}],
            "anomalies": [
                {"should_pause": True, "severity": "high"},
                {"should_pause": False},
            ],
            "risk_drilldown": {
                "BTC": [
                    {"breached_limits": ["max_drawdown", "max_leverage"]},
                    {"breached_limits": ["trades_today_cap"]},
                ]
            },
            "hero_sla": [
                {"hero": "Vision", "avg_seconds": 90.0},  # degraded
                {"hero": "Batman", "avg_seconds": 5.0},
            ],
        }
        result = _compute_severity(payload)
        assert result["drivers"]["anomaly_pause"] == 1
        assert result["drivers"]["breached_limits"] == 3
        assert result["drivers"]["sla_degraded"] == 1
        assert result["score"] > 0

    def test_score_is_capped_at_100(self):
        payload = {
            "global_alerts": [
                {"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL"},
                {"code": "KILL_SWITCH_FILE", "severity": "CRITICAL"},
                {"code": "EXTRA", "severity": "CRITICAL"},
            ],
            "anomalies": [{"should_pause": True}],
        }
        result = _compute_severity(payload)
        assert result["score"] == 100
        assert result["tier"] == "CRITICAL"


# ---------------------------------------------------------------------------
# /api/replay/snapshots
# ---------------------------------------------------------------------------


class TestReplaySnapshots:
    async def test_lists_snapshots_in_reverse_order(self, dashboard_client):
        client, snap_dir = dashboard_client
        for stamp in ("20260507T1000", "20260507T1100", "20260507T1200"):
            _write_snapshot(
                snap_dir,
                _snap_filename(stamp),
                _make_snapshot(timestamp=f"2026-05-07T{stamp[-4:-2]}:00:00+00:00"),
            )

        resp = await client.get("/api/replay/snapshots")
        assert resp.status == 200
        data = await resp.json()
        assert data["snapshots"][0] == "snapshot-20260507T1200.json"
        assert data["snapshots"][-1] == "snapshot-20260507T1000.json"

    async def test_empty_returns_empty_list(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay/snapshots")
        assert resp.status == 200
        assert (await resp.json())["snapshots"] == []


# ---------------------------------------------------------------------------
# /api/replay
# ---------------------------------------------------------------------------


class TestReplaySingle:
    async def test_returns_existing_snapshot(self, dashboard_client):
        client, snap_dir = dashboard_client
        name = _snap_filename("20260507T1200")
        _write_snapshot(
            snap_dir, name, _make_snapshot(timestamp="2026-05-07T12:00:00+00:00")
        )

        resp = await client.get(f"/api/replay?snapshot={name}")
        assert resp.status == 200
        body = await resp.json()
        assert body["overview"]["timestamp"] == "2026-05-07T12:00:00+00:00"

    async def test_unknown_returns_404(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay?snapshot=snapshot-nonexistent.json")
        assert resp.status == 404

    async def test_path_traversal_blocked(self, dashboard_client):
        client, _ = dashboard_client
        for bad in ("../etc/passwd", "snap/../etc"):
            resp = await client.get(f"/api/replay?snapshot={bad}")
            assert resp.status == 400


# ---------------------------------------------------------------------------
# /api/replay/export
# ---------------------------------------------------------------------------


class TestReplayExport:
    async def test_export_json(self, dashboard_client):
        client, snap_dir = dashboard_client
        for stamp, totals in (("20260507T1000", 10), ("20260507T1100", 12)):
            _write_snapshot(
                snap_dir,
                _snap_filename(stamp),
                _make_snapshot(
                    timestamp=f"2026-05-07T{stamp[-4:-2]}:00:00+00:00",
                    total_signals=totals,
                ),
            )

        resp = await client.get(
            "/api/replay/export"
            "?start=snapshot-20260507T1000.json"
            "&end=snapshot-20260507T1100.json&format=json"
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["count"] == 2
        assert {row["snapshot"] for row in body["items"]} == {
            "snapshot-20260507T1000.json",
            "snapshot-20260507T1100.json",
        }

    async def test_export_csv(self, dashboard_client):
        client, snap_dir = dashboard_client
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T1000"),
            _make_snapshot(timestamp="2026-05-07T10:00:00+00:00"),
        )

        resp = await client.get("/api/replay/export?format=csv")
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("text/csv")
        text = await resp.text()
        assert "snapshot,timestamp" in text.splitlines()[0]
        assert "snapshot-20260507T1000.json" in text

    async def test_export_no_snapshots_returns_404(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay/export")
        assert resp.status == 404

    async def test_utc_filter_excludes_out_of_range(self, dashboard_client):
        client, snap_dir = dashboard_client
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T1000"),
            _make_snapshot(timestamp="2026-05-07T10:00:00+00:00"),
        )
        _write_snapshot(
            snap_dir,
            _snap_filename("20260508T1000"),
            _make_snapshot(timestamp="2026-05-08T10:00:00+00:00"),
        )

        resp = await client.get(
            "/api/replay/export?start_utc=2026-05-08T00:00:00+00:00"
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["count"] == 1
        assert body["items"][0]["snapshot"] == "snapshot-20260508T1000.json"


# ---------------------------------------------------------------------------
# /api/replay/compare
# ---------------------------------------------------------------------------


class TestReplayCompare:
    async def test_compare_two_snapshots(self, dashboard_client):
        client, snap_dir = dashboard_client
        a_name = _snap_filename("20260507T1000")
        b_name = _snap_filename("20260507T1100")
        _write_snapshot(
            snap_dir,
            a_name,
            _make_snapshot(
                timestamp="2026-05-07T10:00:00+00:00",
                total_signals=10,
                total_trades=5,
            ),
        )
        _write_snapshot(
            snap_dir,
            b_name,
            _make_snapshot(
                timestamp="2026-05-07T11:00:00+00:00",
                total_signals=14,
                total_trades=9,
            ),
        )

        resp = await client.get(f"/api/replay/compare?a={a_name}&b={b_name}")
        assert resp.status == 200
        body = await resp.json()
        assert body["snapshot_a"] == a_name
        assert body["snapshot_b"] == b_name
        assert body["overview_delta"]["total_signals"] == 4
        assert body["overview_delta"]["total_trades"] == 4

    async def test_compare_missing_param_returns_400(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay/compare?a=foo.json")
        assert resp.status == 400

    async def test_compare_missing_snapshot_returns_404(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay/compare?a=x.json&b=y.json")
        assert resp.status == 404


# ---------------------------------------------------------------------------
# /api/replay/incident/latest + /download
# ---------------------------------------------------------------------------


class TestIncidentEndpoints:
    async def test_incident_latest_with_kill_switch(self, dashboard_client):
        client, snap_dir = dashboard_client
        prev = _snap_filename("20260507T0900")
        bad = _snap_filename("20260507T1000")
        _write_snapshot(
            snap_dir,
            prev,
            _make_snapshot(timestamp="2026-05-07T09:00:00+00:00"),
        )
        _write_snapshot(
            snap_dir,
            bad,
            _make_snapshot(
                timestamp="2026-05-07T10:00:00+00:00",
                alerts=[
                    {
                        "code": "KILL_SWITCH_EVENT",
                        "severity": "CRITICAL",
                        "message": "Batman kill switch tripped",
                    }
                ],
            ),
        )

        resp = await client.get("/api/replay/incident/latest")
        assert resp.status == 200
        body = await resp.json()
        assert body["incident_snapshot"] == bad
        assert body["baseline_snapshot"] == prev
        assert body["severity"]["tier"] in {"HIGH", "CRITICAL"}
        assert body["severity"]["score"] >= 50

    async def test_incident_latest_404_when_no_kill_switch(self, dashboard_client):
        client, snap_dir = dashboard_client
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T1000"),
            _make_snapshot(timestamp="2026-05-07T10:00:00+00:00"),
        )
        resp = await client.get("/api/replay/incident/latest")
        assert resp.status == 404

    async def test_incident_download_returns_existing_bundle(self, dashboard_client):
        client, snap_dir = dashboard_client
        bundle = snap_dir / "incident-bundle-20260507T100000.json"
        bundle_payload = {"captured_at": "2026-05-07T10:00:00+00:00", "alerts": []}
        bundle.write_text(json.dumps(bundle_payload), encoding="utf-8")

        resp = await client.get("/api/replay/incident/latest/download")
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("application/json")
        disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in disp
        assert "incident-bundle-20260507T100000.json" in disp
        body = await resp.json()
        assert body["captured_at"] == "2026-05-07T10:00:00+00:00"

    async def test_incident_download_falls_back_to_snapshot(self, dashboard_client):
        client, snap_dir = dashboard_client
        # No incident-bundle-*.json exists, but a kill-switch snapshot does.
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T1000"),
            _make_snapshot(
                timestamp="2026-05-07T10:00:00+00:00",
                alerts=[{"code": "KILL_SWITCH_FILE", "severity": "CRITICAL"}],
            ),
        )

        resp = await client.get("/api/replay/incident/latest/download")
        assert resp.status == 200
        body = await resp.json()
        assert body.get("source_snapshot") == "snapshot-20260507T1000.json"
        assert body["severity"]["tier"] == "CRITICAL"

    async def test_incident_download_404_when_empty(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay/incident/latest/download")
        assert resp.status == 404


# ---------------------------------------------------------------------------
# /api/replay/timeseries
# ---------------------------------------------------------------------------


class TestReplayTimeseries:
    async def test_returns_aggregated_series(self, dashboard_client):
        client, snap_dir = dashboard_client
        for i, stamp in enumerate(("20260507T1000", "20260507T1100", "20260507T1200")):
            _write_snapshot(
                snap_dir,
                _snap_filename(stamp),
                _make_snapshot(
                    timestamp=f"2026-05-07T{stamp[-4:-2]}:00:00+00:00",
                    total_signals=10 + i,
                    total_trades=5 + i,
                    alerts=(
                        [{"code": "ANOMALY_PAUSE", "severity": "WARNING"}] if i == 2 else []
                    ),
                ),
            )

        resp = await client.get("/api/replay/timeseries")
        assert resp.status == 200
        body = await resp.json()
        assert body["count"] == 3
        last = body["items"][-1]
        assert last["signals_total"] == 12
        assert last["alerts_count"] == 1
        assert "severity_score" in last and "severity_tier" in last

    async def test_empty_returns_zero_count(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay/timeseries")
        assert resp.status == 200
        body = await resp.json()
        assert body["count"] == 0
        assert body["items"] == []


# ---------------------------------------------------------------------------
# /api/incidents/queue
# ---------------------------------------------------------------------------


class TestIncidentsQueue:
    async def test_returns_only_incidents_with_score(self, dashboard_client):
        client, snap_dir = dashboard_client
        # Calm snapshot — should be filtered out (score == 0)
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T0900"),
            _make_snapshot(timestamp="2026-05-07T09:00:00+00:00"),
        )
        # Critical kill-switch snapshot
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T1000"),
            _make_snapshot(
                timestamp="2026-05-07T10:00:00+00:00",
                alerts=[{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL"}],
            ),
        )
        # Warning-only snapshot
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T1100"),
            _make_snapshot(
                timestamp="2026-05-07T11:00:00+00:00",
                alerts=[{"code": "ANOMALY_PAUSE", "severity": "WARNING"}],
            ),
        )

        resp = await client.get("/api/incidents/queue")
        assert resp.status == 200
        body = await resp.json()
        assert body["count"] == 2
        # Sorted by score descending — critical must come first
        first = body["items"][0]
        assert first["tier"] in {"HIGH", "CRITICAL"}
        assert first["kill_switch"] is True
        assert first["snapshot"] == "snapshot-20260507T1000.json"

    async def test_empty_returns_zero_count(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/incidents/queue")
        assert resp.status == 200
        body = await resp.json()
        assert body["count"] == 0
        assert body["items"] == []

    async def test_limit_param_is_respected(self, dashboard_client):
        client, snap_dir = dashboard_client
        for i in range(5):
            _write_snapshot(
                snap_dir,
                _snap_filename(f"2026050{i}T1000"),
                _make_snapshot(
                    timestamp=f"2026-05-0{i}T10:00:00+00:00",
                    alerts=[{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL"}],
                ),
            )

        resp = await client.get("/api/incidents/queue?limit=2")
        assert resp.status == 200
        body = await resp.json()
        assert len(body["items"]) == 2
        assert body["count"] >= 2

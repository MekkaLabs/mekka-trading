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
from src.dashboard import validators as validators_module
from src.dashboard.server import (
    MekkaDashboardServer,
    _build_global_alerts,
    _compute_severity,
    _is_origin_allowed,
    _is_valid_bundle_name,
    _is_valid_snapshot_name,
    _percentile,
)


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
        # Filename must clear `_is_valid_snapshot_name` (regex-strict since
        # the validator hardening) so we hit the "file not on disk" branch
        # at line ~382 of server.py instead of the 400-pre-disk branch.
        # Using a date that the test fixture never wrote keeps the assertion
        # pure: well-formed → no file → 404.
        resp = await client.get("/api/replay?snapshot=snapshot-20260101T0000.json")
        assert resp.status == 404

    async def test_path_traversal_blocked(self, dashboard_client):
        client, _ = dashboard_client
        # The validator is now strict: only `snapshot-YYYYMMDDTHHMM.json` and
        # `latest.json` are accepted, so traversal AND any unexpected
        # filename pattern returns 400 before touching the disk.
        bad_inputs = (
            "../etc/passwd",
            "snap/../etc",
            "evil.json",
            "snapshot-bad.json",
            "snapshot-20260507T1200.JSON",  # wrong case
            "",
        )
        for bad in bad_inputs:
            resp = await client.get(f"/api/replay?snapshot={bad}")
            assert resp.status == 400, f"expected 400 for {bad!r}, got {resp.status}"


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
            "/api/replay/export?start_utc=2026-05-08T00:00:00%2B00:00"
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
        resp = await client.get("/api/replay/compare?a=snapshot-20260507T1000.json")
        assert resp.status == 400

    async def test_compare_invalid_name_returns_400(self, dashboard_client):
        client, _ = dashboard_client
        # The strict regex blocks anything that isn't a real snapshot/latest
        # filename — caught BEFORE the existence check so we can never escape.
        resp = await client.get("/api/replay/compare?a=evil.json&b=snapshot-20260507T1000.json")
        assert resp.status == 400

    async def test_compare_missing_snapshot_returns_404(self, dashboard_client):
        client, _ = dashboard_client
        # Both names pass the regex but the files don't exist on disk.
        resp = await client.get(
            "/api/replay/compare"
            "?a=snapshot-20260507T1000.json"
            "&b=snapshot-20260507T1100.json"
        )
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


# ---------------------------------------------------------------------------
# Hardening regressions: validators, percentile helper, baseline=None.
# ---------------------------------------------------------------------------


class TestSnapshotNameValidator:
    @pytest.mark.parametrize(
        "good",
        [
            "snapshot-20260507T1200.json",
            "snapshot-20991231T2359.json",
            "latest.json",
        ],
    )
    def test_accepts_well_formed(self, good):
        assert _is_valid_snapshot_name(good) is True

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "../etc/passwd",
            "snap/../etc",
            "snapshot-bad.json",
            "snapshot-20260507T1200.JSON",
            "snapshot-2026057T1200.json",  # one digit short
            "snapshot-20260507T120.json",  # one digit short on time
            "incident-bundle-20260507T120000.json",
            "latest",  # missing extension
            "snapshot-20260507T1200.json\x00.txt",  # null-byte trick
        ],
    )
    def test_rejects_anything_else(self, bad):
        assert _is_valid_snapshot_name(bad) is False


class TestBundleNameValidator:
    def test_accepts_well_formed(self):
        assert _is_valid_bundle_name("incident-bundle-20260507T120000.json") is True

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "incident-bundle-bad.json",
            "incident-bundle-20260507T1200.json",  # missing seconds
            "incident-bundle-20260507T12000.json",  # one digit short on time
            "incident-bundle-20260507120000.json",  # missing T separator
            "snapshot-20260507T1200.json",
            "../incident-bundle-20260507T120000.json",
        ],
    )
    def test_rejects_anything_else(self, bad):
        assert _is_valid_bundle_name(bad) is False


class TestOriginAllowlist:
    @pytest.mark.parametrize(
        "ok",
        [
            "http://127.0.0.1:8787",
            "http://localhost:8787",
            "https://localhost",
            "https://127.0.0.1:9000",
        ],
    )
    def test_local_origins_allowed(self, ok):
        assert _is_origin_allowed(ok) is True

    @pytest.mark.parametrize(
        "bad",
        [
            None,
            "",
            "http://attacker.com",
            "https://evil.example/192.168",
            "file://",
            "javascript:alert(1)",
        ],
    )
    def test_other_origins_rejected(self, bad):
        assert _is_origin_allowed(bad) is False

    def test_extra_origins_env_extends(self, monkeypatch):
        # `EXTRA_WS_ORIGINS` lives in `src.dashboard.validators` since the
        # validator extraction refactor; `is_origin_allowed` reads the
        # binding from THAT module's globals, so patching the
        # `server_module` re-export is a no-op. Patch the source module
        # directly to extend the allowlist for this test only.
        monkeypatch.setattr(
            validators_module,
            "EXTRA_WS_ORIGINS",
            ("https://internal.corp",),
        )
        assert _is_origin_allowed("https://internal.corp") is True


class TestPercentileHelper:
    def test_empty_is_none(self):
        assert _percentile([], 0.95) is None

    def test_single_value(self):
        assert _percentile([5.0], 0.95) == 5.0

    def test_two_values_p95_is_close_to_max(self):
        # The previous inline calc returned the SMALLER value here; the
        # interpolated percentile must be near 9.0 for [1.0, 9.0].
        result = _percentile([1.0, 9.0], 0.95)
        assert result is not None and result > 8.0

    def test_known_p95(self):
        # Linearly-interpolated p95 of 1..10 should be near 9.55.
        result = _percentile([float(i) for i in range(1, 11)], 0.95)
        assert result is not None and 9.4 <= result <= 9.7


class TestIncidentLatestBaselineFallback:
    async def test_baseline_is_null_when_only_one_snapshot(self, dashboard_client):
        client, snap_dir = dashboard_client
        # Single snapshot AND it carries the kill switch — there is no
        # baseline to compare against, so baseline_snapshot must be null and
        # `compare` must be omitted/null rather than comparing the snapshot
        # against itself.
        _write_snapshot(
            snap_dir,
            _snap_filename("20260507T1000"),
            _make_snapshot(
                timestamp="2026-05-07T10:00:00+00:00",
                alerts=[{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL"}],
            ),
        )

        resp = await client.get("/api/replay/incident/latest")
        assert resp.status == 200
        body = await resp.json()
        assert body["incident_snapshot"] == "snapshot-20260507T1000.json"
        assert body["baseline_snapshot"] is None
        assert body["compare"] is None
        assert body["severity"]["tier"] in {"HIGH", "CRITICAL"}


class TestPersistSnapshotDedup:
    async def test_kill_switch_bundle_dedups_within_minute(self, monkeypatch, tmp_path):
        # Direct unit test on _persist_snapshot. We call it three times with
        # the same kill-switch payload and verify only ONE bundle is written
        # because all three calls land in the same wall-clock minute.
        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)
        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()

        kill_payload = _make_snapshot(
            timestamp="2026-05-07T10:00:00+00:00",
            alerts=[{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL"}],
        )
        for _ in range(3):
            await server._persist_snapshot(kill_payload)

        bundles = list(snapshot_dir.glob("incident-bundle-*.json"))
        assert len(bundles) == 1, (
            f"expected 1 bundle (front-edge), got {len(bundles)}: "
            f"{[b.name for b in bundles]}"
        )

    async def test_kill_clear_then_reactive_creates_new_bundle(self, monkeypatch, tmp_path):
        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)
        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()

        kill_payload = _make_snapshot(
            timestamp="2026-05-07T10:00:00+00:00",
            alerts=[{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL"}],
        )
        clear_payload = _make_snapshot(timestamp="2026-05-07T10:00:00+00:00")

        await server._persist_snapshot(kill_payload)
        await server._persist_snapshot(clear_payload)
        await server._persist_snapshot(kill_payload)

        bundles = sorted(snapshot_dir.glob("incident-bundle-*.json"))
        # First kill → bundle. Clear → state resets. Second kill → another bundle.
        assert len(bundles) == 2, [b.name for b in bundles]


class TestSnapshotPruning:
    async def test_prune_keeps_only_retention_window(self, monkeypatch, tmp_path):
        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)
        # Tighten retention so the test is fast and deterministic.
        monkeypatch.setattr(server_module, "SNAPSHOT_RETENTION_MINUTES", 3)
        monkeypatch.setattr(server_module, "INCIDENT_BUNDLE_RETENTION", 2)

        # Pre-create 6 snapshots and 4 bundles. Pruning keeps the newest
        # SNAPSHOT_RETENTION_MINUTES snapshots and INCIDENT_BUNDLE_RETENTION
        # bundles (sorted ascending, so the youngest survive).
        for i in range(6):
            (snapshot_dir / f"snapshot-2026050{i}T1000.json").write_text("{}", "utf-8")
        for i in range(4):
            (snapshot_dir / f"incident-bundle-2026050{i}T100000.json").write_text(
                "{}", "utf-8"
            )

        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()
        server._prune_snapshot_dir()

        snaps = sorted(p.name for p in snapshot_dir.glob("snapshot-*.json"))
        bundles = sorted(p.name for p in snapshot_dir.glob("incident-bundle-*.json"))
        assert snaps == [
            "snapshot-20260503T1000.json",
            "snapshot-20260504T1000.json",
            "snapshot-20260505T1000.json",
        ]
        assert bundles == [
            "incident-bundle-20260502T100000.json",
            "incident-bundle-20260503T100000.json",
        ]


class TestWebSocketOriginCheck:
    async def test_missing_origin_rejected(self, dashboard_client):
        client, _ = dashboard_client
        # No Origin header → the WS upgrade is rejected with HTTP 403 so a
        # tab on attacker.com cannot exfiltrate the live feed via CSWSH.
        resp = await client.get("/ws")
        assert resp.status == 403

    async def test_foreign_origin_rejected(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/ws", headers={"Origin": "https://attacker.com"})
        assert resp.status == 403


# ---------------------------------------------------------------------------
# /api/pnl/series + /api/pnl/summary
# ---------------------------------------------------------------------------


class _StubPnL:
    """Plain object that mimics the SQLAlchemy DailyPnLRecord shape used by
    the dashboard handlers. Avoids touching the DB during these unit tests."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _stub_pnl_row(**overrides):
    base = dict(
        id=1,
        date_utc="2026-05-01",
        is_paper=True,
        starting_equity=10_000.0,
        ending_equity=10_120.0,
        pnl_usd=120.0,
        pnl_pct=0.012,
        drawdown_pct=0.005,
        trades_count=4,
        wins=3,
        losses=1,
    )
    base.update(overrides)
    return _StubPnL(**base)


class TestPnLEndpoints:
    async def test_series_returns_oldest_first(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client
        rows = [
            _stub_pnl_row(date_utc="2026-04-29", ending_equity=9_900.0, pnl_usd=-100.0),
            _stub_pnl_row(date_utc="2026-04-30", ending_equity=10_000.0, pnl_usd=100.0),
            _stub_pnl_row(date_utc="2026-05-01", ending_equity=10_120.0, pnl_usd=120.0),
        ]

        async def fake_list_pnl(limit=90):
            return list(rows)

        monkeypatch.setattr(
            server_module.MekkaRepository, "list_recent_daily_pnl", fake_list_pnl
        )
        resp = await client.get("/api/pnl/series?days=30")
        assert resp.status == 200
        body = await resp.json()
        assert body["count"] == 3
        # Oldest-first so the chart can grow left → right.
        assert [it["date_utc"] for it in body["items"]] == [
            "2026-04-29",
            "2026-04-30",
            "2026-05-01",
        ]
        assert body["items"][-1]["ending_equity"] == 10_120.0

    async def test_summary_aggregates_window(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client

        async def fake_summary(window_days=30):
            return {
                "window_days": window_days,
                "window": {
                    "pnl_usd": 250.0,
                    "trades": 12,
                    "wins": 7,
                    "losses": 5,
                    "win_rate": 7 / 12,
                    "max_drawdown_pct": 0.04,
                    "latest_equity_usd": 10_500.0,
                    "days_with_data": 10,
                },
                "all_time": {
                    "pnl_usd": 1_500.0,
                    "trades": 60,
                    "wins": 35,
                    "losses": 25,
                    "win_rate": 35 / 60,
                    "max_drawdown_pct": 0.08,
                    "trading_days": 90,
                },
            }

        monkeypatch.setattr(
            server_module.MekkaRepository, "get_pnl_summary", fake_summary
        )
        resp = await client.get("/api/pnl/summary?days=30")
        assert resp.status == 200
        body = await resp.json()
        assert body["window_days"] == 30
        assert body["window"]["pnl_usd"] == 250.0
        assert body["all_time"]["trading_days"] == 90

    async def test_series_clamps_days_param(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client
        captured: dict = {}

        async def fake_list_pnl(limit=90):
            captured["limit"] = limit
            return []

        monkeypatch.setattr(
            server_module.MekkaRepository, "list_recent_daily_pnl", fake_list_pnl
        )
        # max_value=365 → out-of-range 9999 clamps to 365.
        resp = await client.get("/api/pnl/series?days=9999")
        assert resp.status == 200
        assert captured["limit"] == 365
        # Negative/garbage falls back to default 30.
        await client.get("/api/pnl/series?days=-1")
        assert captured["limit"] == 30
        await client.get("/api/pnl/series?days=abc")
        assert captured["limit"] == 30

    async def test_summary_timeout_returns_504(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client

        # Repository raises TimeoutError → handler must convert to 504.
        # We bypass wait_for entirely by raising directly; the handler's
        # `except asyncio.TimeoutError` still catches it and returns 504.
        import asyncio as _asyncio

        async def fake_summary(window_days=30):
            raise _asyncio.TimeoutError()

        monkeypatch.setattr(
            server_module.MekkaRepository, "get_pnl_summary", fake_summary
        )
        resp = await client.get("/api/pnl/summary?days=7")
        assert resp.status == 504


# ---------------------------------------------------------------------------
# Drawdown alerts (`_build_global_alerts`)
# ---------------------------------------------------------------------------


class TestDrawdownAlert:
    def test_zero_drawdown_emits_no_alert(self):
        alerts = _build_global_alerts([], drawdown_pct=0.0)
        codes = {a["code"] for a in alerts}
        assert "DRAWDOWN_WARNING" not in codes
        assert "DRAWDOWN_CRITICAL" not in codes

    def test_warn_threshold_emits_warning(self, monkeypatch):
        monkeypatch.setattr(server_module, "_DRAWDOWN_WARN", 0.05)
        monkeypatch.setattr(server_module, "_DRAWDOWN_CRIT", 0.10)
        alerts = _build_global_alerts([], drawdown_pct=0.06)
        codes = {a["code"] for a in alerts}
        assert "DRAWDOWN_WARNING" in codes
        assert "DRAWDOWN_CRITICAL" not in codes
        warn = next(a for a in alerts if a["code"] == "DRAWDOWN_WARNING")
        assert warn["severity"] == "WARNING"
        assert abs(warn["drawdown_pct"] - 0.06) < 1e-9

    def test_crit_threshold_emits_critical(self, monkeypatch):
        monkeypatch.setattr(server_module, "_DRAWDOWN_WARN", 0.05)
        monkeypatch.setattr(server_module, "_DRAWDOWN_CRIT", 0.10)
        alerts = _build_global_alerts([], drawdown_pct=0.12)
        codes = {a["code"] for a in alerts}
        # Only CRITICAL — no double-alert (the elif branch ensures this).
        assert "DRAWDOWN_CRITICAL" in codes
        assert "DRAWDOWN_WARNING" not in codes
        crit = next(a for a in alerts if a["code"] == "DRAWDOWN_CRITICAL")
        assert crit["severity"] == "CRITICAL"

    def test_drawdown_alert_lifts_severity_score(self):
        # Compose with _compute_severity so the queue ranking is consistent.
        alerts = _build_global_alerts([], drawdown_pct=0.15)
        sev = _compute_severity({"global_alerts": alerts})
        # 50 (critical) >= MEDIUM threshold → tier upgraded.
        assert sev["score"] >= 50
        assert sev["tier"] in {"HIGH", "CRITICAL"}


# ---------------------------------------------------------------------------
# Security headers + auth middleware
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    async def test_baseline_headers_present_on_get(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/replay/snapshots")
        assert resp.status == 200
        assert "Content-Security-Policy" in resp.headers
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in resp.headers
        # HSTS is HTTPS-only; the aiohttp test client uses plain HTTP.
        assert "Strict-Transport-Security" not in resp.headers

    async def test_csp_can_be_overridden_by_env(self, monkeypatch, tmp_path):
        # We exercise the override via monkeypatch on the module-level constant
        # (the env is read at import time, so changing os.environ won't help).
        custom = "default-src 'self'; img-src 'self' data:"
        monkeypatch.setattr(server_module, "_DASHBOARD_CSP", custom)
        snapshot_dir = tmp_path / "dashboard_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)
        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()
        async with TestClient(TestServer(server._app)) as client:
            resp = await client.get("/api/replay/snapshots")
            assert resp.headers["Content-Security-Policy"] == custom


class TestAuthMiddleware:
    async def test_get_endpoints_open_without_token(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client
        monkeypatch.setattr(server_module, "_DASHBOARD_TOKEN", "secret123")
        resp = await client.get("/api/replay/snapshots")
        assert resp.status == 200

    async def test_post_blocked_without_token(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client
        monkeypatch.setattr(server_module, "_DASHBOARD_TOKEN", "secret123")
        resp = await client.post("/api/killswitch/engage", json={"confirm": "ENGAGE"})
        assert resp.status == 401
        body = await resp.json()
        assert "X-Mekka-Token" in body["error"]

    async def test_post_allowed_with_correct_token(self, monkeypatch, tmp_path):
        # Fresh server with an isolated kill-switch path.
        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        ks_path = tmp_path / ".kill_switch"
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)
        monkeypatch.setattr(server_module, "KILL_SWITCH_FILE", ks_path)
        monkeypatch.setattr(server_module, "_DASHBOARD_TOKEN", "secret123")

        # MekkaRepository.log_event hits the DB; stub it out.
        async def fake_log(**kw):
            return 1
        monkeypatch.setattr(server_module.MekkaRepository, "log_event", fake_log)

        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()
        async with TestClient(TestServer(server._app)) as client:
            resp = await client.post(
                "/api/killswitch/engage",
                json={"confirm": "ENGAGE", "reason": "test"},
                headers={"X-Mekka-Token": "secret123"},
            )
            assert resp.status == 200
            assert ks_path.exists()
            assert "test" in ks_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Kill switch endpoints (status / engage / release)
# ---------------------------------------------------------------------------


class TestKillSwitchEndpoints:
    @pytest.fixture
    async def killswitch_client(self, monkeypatch, tmp_path):
        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        ks_path = tmp_path / ".kill_switch"
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)
        monkeypatch.setattr(server_module, "KILL_SWITCH_FILE", ks_path)
        # No token required for these tests — keeps assertions focused on the
        # endpoint contract rather than auth (covered separately above).
        monkeypatch.setattr(server_module, "_DASHBOARD_TOKEN", "")

        async def fake_log(**kw):
            return 1

        monkeypatch.setattr(server_module.MekkaRepository, "log_event", fake_log)
        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()
        async with TestClient(TestServer(server._app)) as client:
            yield client, ks_path

    async def test_status_when_clear(self, killswitch_client):
        client, ks_path = killswitch_client
        resp = await client.get("/api/killswitch/status")
        assert resp.status == 200
        body = await resp.json()
        assert body["active"] is False

    async def test_engage_then_status_then_release(self, killswitch_client):
        client, ks_path = killswitch_client
        # Engage requires confirm=ENGAGE.
        resp = await client.post("/api/killswitch/engage", json={"confirm": "wrong"})
        assert resp.status == 400
        resp = await client.post(
            "/api/killswitch/engage", json={"confirm": "ENGAGE", "reason": "drawdown"}
        )
        assert resp.status == 200
        assert ks_path.exists()
        resp = await client.get("/api/killswitch/status")
        body = await resp.json()
        assert body["active"] is True
        # Release requires confirm=RELEASE.
        resp = await client.post(
            "/api/killswitch/release", json={"confirm": "RELEASE", "operator": "ops"}
        )
        assert resp.status == 200
        assert not ks_path.exists()

    async def test_release_when_already_clear_is_idempotent(self, killswitch_client):
        client, ks_path = killswitch_client
        assert not ks_path.exists()
        resp = await client.post(
            "/api/killswitch/release", json={"confirm": "RELEASE"}
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["active"] is False
        assert body["had_file"] is False

    async def test_engage_invalid_json_returns_400(self, killswitch_client):
        client, _ = killswitch_client
        resp = await client.post(
            "/api/killswitch/engage",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400


# ---------------------------------------------------------------------------
# /metrics + /api/positions
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    async def test_metrics_format_is_prometheus_text(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/metrics")
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("text/plain")
        body = await resp.text()
        # HELP/TYPE/value triples for at least the headline counters.
        for needed in (
            "mekka_broadcasts_total",
            "mekka_ws_active_connections",
            "mekka_payload_collect_latency_ms_p50",
            "mekka_payload_collect_latency_ms_p95",
            "mekka_payload_cache_hits_total",
            "mekka_payload_cache_misses_total",
            "mekka_started_at_unix_seconds",
        ):
            assert f"# HELP {needed}" in body, f"missing HELP for {needed}"
            assert f"# TYPE {needed}" in body, f"missing TYPE for {needed}"

    async def test_metrics_increments_with_traffic(self, dashboard_client):
        client, _ = dashboard_client

        # Hit a few read endpoints; the counter middleware should bump
        # http_requests_total, and the payload cache miss counter rises on
        # the very first overview build.
        for _ in range(3):
            await client.get("/api/replay/snapshots")
        resp = await client.get("/metrics")
        body = await resp.text()
        # Parse "mekka_http_requests_total VALUE" line.
        for line in body.splitlines():
            if line.startswith("mekka_http_requests_total ") and "{" not in line:
                value = float(line.split()[-1])
                assert value >= 3.0
                return
        raise AssertionError("mekka_http_requests_total not present in /metrics")


class TestPositionsStub:
    async def test_returns_stable_contract(self, dashboard_client):
        client, _ = dashboard_client
        resp = await client.get("/api/positions")
        assert resp.status == 200
        body = await resp.json()
        # Stable contract — frontend renders unconditionally on these keys.
        # Paper trading is the default in tests, so we expect the stub.
        assert body["items"] == []
        assert body["count"] == 0
        assert body["source"] == "stub"
        assert body["supported"] is False
        assert "message" in body


# ---------------------------------------------------------------------------
# Hyperliquid positions provider — pure mapping + paper-trading short circuit
# ---------------------------------------------------------------------------


class TestPositionsProvider:
    def test_map_user_state_basic(self):
        from src.dashboard.positions_provider import map_user_state_to_positions
        user_state = {
            "assetPositions": [
                {
                    "type": "oneWay",
                    "position": {
                        "coin": "BTC",
                        "szi": "0.5",
                        "entryPx": "50000",
                        "markPx": "51000",
                        "unrealizedPnl": "500",
                        "leverage": {"value": 5, "type": "cross"},
                        "liquidationPx": "30000",
                    },
                },
                {
                    "type": "oneWay",
                    "position": {
                        "coin": "ETH",
                        "szi": "-2.0",
                        "entryPx": "3000",
                        "markPx": "2950",
                        "unrealizedPnl": "100",
                        "leverage": {"value": 3, "type": "cross"},
                    },
                },
                # Zero size → must be skipped.
                {"position": {"coin": "ZERO", "szi": "0"}},
            ]
        }
        out = map_user_state_to_positions(user_state)
        assert len(out) == 2
        # Sorted by |pnl| desc — BTC (500) before ETH (100).
        assert out[0]["symbol"] == "BTC"
        assert out[0]["side"] == "LONG"
        assert out[0]["size"] == 0.5
        assert out[0]["leverage"] == 5
        assert out[0]["liq_price"] == 30000.0
        assert out[1]["symbol"] == "ETH"
        assert out[1]["side"] == "SHORT"
        assert out[1]["size"] == 2.0
        assert out[1]["liq_price"] is None  # absent in input → None

    def test_map_user_state_empty(self):
        from src.dashboard.positions_provider import map_user_state_to_positions
        assert map_user_state_to_positions({}) == []
        assert map_user_state_to_positions({"assetPositions": []}) == []

    async def test_paper_trading_short_circuits(self, monkeypatch):
        # In paper mode the provider must NOT touch the SDK at all — it
        # returns the stub shape so the dashboard never imports hyperliquid.
        from src.dashboard import positions_provider as pp
        monkeypatch.setattr(pp.settings, "paper_trading", True, raising=False)
        data = await pp.fetch_positions()
        assert data["source"] == "stub"
        assert data["items"] == []
        assert data["supported"] is False
        assert "Paper trading" in data["message"]

    async def test_missing_address_returns_stub(self, monkeypatch):
        from src.dashboard import positions_provider as pp
        monkeypatch.setattr(pp.settings, "paper_trading", False, raising=False)
        monkeypatch.setattr(
            pp.settings, "hyperliquid_wallet_address", "", raising=False
        )
        data = await pp.fetch_positions()
        assert data["source"] == "stub"
        assert "WALLET_ADDRESS" in data["message"]


# ---------------------------------------------------------------------------
# Auth — token issue/verify + login/logout/me + middleware integration.
# ---------------------------------------------------------------------------


class TestAuthTokens:
    def test_issue_and_verify_roundtrip(self):
        from src.dashboard import auth as auth_mod
        bundle = auth_mod.issue_token(subject="ops", ttl_seconds=300)
        assert bundle["subject"] == "ops"
        payload = auth_mod.verify_token(bundle["token"])
        assert payload is not None
        assert payload["sub"] == "ops"
        assert payload["exp"] - payload["iat"] == 300

    def test_verify_rejects_garbage(self):
        from src.dashboard import auth as auth_mod
        for bad in (None, "", "no-dot", "abc.def", "x" * 200):
            assert auth_mod.verify_token(bad) is None

    def test_verify_rejects_expired(self, monkeypatch):
        from src.dashboard import auth as auth_mod
        bundle = auth_mod.issue_token(subject="ops", ttl_seconds=1)
        # Move time forward past expiry — auth uses time.time() directly.
        import time as _time
        real = _time.time
        monkeypatch.setattr(_time, "time", lambda: real() + 5)
        assert auth_mod.verify_token(bundle["token"]) is None

    def test_verify_rejects_tampered_signature(self):
        from src.dashboard import auth as auth_mod
        bundle = auth_mod.issue_token()
        body, sig = bundle["token"].rsplit(".", 1)
        # Flip a single char in the signature.
        bad = body + "." + ("A" if sig[0] != "A" else "B") + sig[1:]
        assert auth_mod.verify_token(bad) is None

    def test_check_password_disabled_when_unset(self, monkeypatch):
        from src.dashboard import auth as auth_mod
        monkeypatch.setattr(auth_mod, "PASSWORD", "")
        assert auth_mod.check_password("anything") is False
        assert auth_mod.is_login_enabled() is False

    def test_check_password_constant_time(self, monkeypatch):
        from src.dashboard import auth as auth_mod
        monkeypatch.setattr(auth_mod, "PASSWORD", "secret123")
        assert auth_mod.check_password("secret123") is True
        assert auth_mod.check_password("secret124") is False
        assert auth_mod.check_password("") is False
        assert auth_mod.check_password(None) is False
        assert auth_mod.is_login_enabled() is True


class TestAuthEndpoints:
    @pytest.fixture
    async def auth_client(self, monkeypatch, tmp_path):
        # Configure a password and reach into the auth module so login works.
        from src.dashboard import auth as auth_mod
        monkeypatch.setattr(auth_mod, "PASSWORD", "secret123")
        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)
        # Force middleware into "auth required" mode.
        monkeypatch.setattr(server_module, "_DASHBOARD_TOKEN", "")

        async def fake_log(**kw):
            return 1
        monkeypatch.setattr(server_module.MekkaRepository, "log_event", fake_log)

        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()
        async with TestClient(TestServer(server._app)) as client:
            yield client

    async def test_me_anon_then_authed(self, auth_client):
        client = auth_client
        resp = await client.get("/api/auth/me")
        assert resp.status == 200
        body = await resp.json()
        assert body["authenticated"] is False
        assert body["login_enabled"] is True

        resp = await client.post("/api/auth/login", json={"password": "secret123"})
        assert resp.status == 200
        login_body = await resp.json()
        assert login_body["authenticated"] is True
        assert "token" in login_body

        # Cookie was set by /login — TestClient persists it across requests.
        resp = await client.get("/api/auth/me")
        body = await resp.json()
        assert body["authenticated"] is True
        assert body["subject"] == "operator"

    async def test_login_wrong_password_returns_401(self, auth_client):
        resp = await auth_client.post("/api/auth/login", json={"password": "wrong"})
        assert resp.status == 401

    async def test_logout_clears_cookie(self, auth_client):
        await auth_client.post("/api/auth/login", json={"password": "secret123"})
        await auth_client.post("/api/auth/logout")
        resp = await auth_client.get("/api/auth/me")
        body = await resp.json()
        assert body["authenticated"] is False

    async def test_mutating_endpoint_blocked_then_allowed_after_login(self, auth_client):
        # Killswitch engage requires auth (POST). Anon → 401.
        resp = await auth_client.post(
            "/api/killswitch/engage", json={"confirm": "ENGAGE"}
        )
        assert resp.status == 401

        await auth_client.post("/api/auth/login", json={"password": "secret123"})
        resp = await auth_client.post(
            "/api/killswitch/engage", json={"confirm": "ENGAGE", "reason": "test"}
        )
        assert resp.status == 200

    async def test_legacy_shared_secret_still_accepted(self, monkeypatch, tmp_path):
        # Auth module disabled (no password) but legacy token configured.
        from src.dashboard import auth as auth_mod
        monkeypatch.setattr(auth_mod, "PASSWORD", "")
        monkeypatch.setattr(server_module, "_DASHBOARD_TOKEN", "legacy-token")
        snapshot_dir = tmp_path / "snap"
        snapshot_dir.mkdir()
        monkeypatch.setattr(server_module, "SNAPSHOT_DIR", snapshot_dir)

        async def fake_log(**kw):
            return 1
        monkeypatch.setattr(server_module.MekkaRepository, "log_event", fake_log)

        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()
        async with TestClient(TestServer(server._app)) as client:
            resp = await client.post("/api/killswitch/engage", json={"confirm": "ENGAGE"})
            assert resp.status == 401  # no header
            resp = await client.post(
                "/api/killswitch/engage",
                json={"confirm": "ENGAGE"},
                headers={"X-Mekka-Token": "legacy-token"},
            )
            assert resp.status == 200


# ---------------------------------------------------------------------------
# Alert dispatcher (dedup window, formatting, target detection)
# ---------------------------------------------------------------------------


class TestAlertDispatcher:
    async def test_dedup_window_skips_repeat(self, monkeypatch):
        from src.dashboard import alert_dispatcher as ad
        monkeypatch.setattr(ad, "SLACK_WEBHOOK", "https://example.invalid/slack")
        monkeypatch.setattr(ad, "DEDUP_WINDOW_S", 3600)
        d = ad.AlertDispatcher()

        async def fake_post(url, payload):
            return True

        monkeypatch.setattr(d, "_post_with_retry", fake_post)
        alerts = [{"code": "KILL_SWITCH_FILE", "severity": "CRITICAL", "message": "x"}]
        first = await d.dispatch(alerts, {"network": "testnet", "mode": "paper"})
        assert first["sent"] == 1
        # Second call inside the dedup window should be skipped — no extra send.
        second = await d.dispatch(alerts, {"network": "testnet", "mode": "paper"})
        assert second["sent"] == 0
        assert second["skipped"] == 1
        await d.close()

    async def test_no_targets_returns_zero(self, monkeypatch):
        from src.dashboard import alert_dispatcher as ad
        monkeypatch.setattr(ad, "SLACK_WEBHOOK", "")
        monkeypatch.setattr(ad, "TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setattr(ad, "TELEGRAM_CHAT_ID", "")
        d = ad.AlertDispatcher()
        report = await d.dispatch(
            [{"code": "KILL_SWITCH_FILE", "severity": "CRITICAL", "message": "x"}],
            {},
        )
        assert report["sent"] == 0
        assert "no targets" in (report.get("reason") or "")
        await d.close()

    async def test_only_dispatched_codes_fire(self, monkeypatch):
        from src.dashboard import alert_dispatcher as ad
        monkeypatch.setattr(ad, "SLACK_WEBHOOK", "https://example.invalid/slack")
        d = ad.AlertDispatcher()

        sends: list[str] = []

        async def fake_post(url, payload):
            sends.append(payload.get("text", ""))
            return True

        monkeypatch.setattr(d, "_post_with_retry", fake_post)
        alerts = [
            {"code": "DRAWDOWN_WARNING", "severity": "WARNING", "message": "skip me"},
            {"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL", "message": "fire me"},
        ]
        report = await d.dispatch(alerts, {})
        assert report["sent"] == 1
        assert any("KILL_SWITCH_EVENT" in s for s in sends)
        assert all("DRAWDOWN_WARNING" not in s for s in sends)
        await d.close()


# ---------------------------------------------------------------------------
# Trades execution timeline + benchmark endpoints
# ---------------------------------------------------------------------------


class TestTradesTimelineEndpoint:
    async def test_returns_hourly_buckets(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client
        from datetime import datetime as _dt, timedelta, timezone as _tz

        class FakeTrade:
            def __init__(self, ts, status):
                self.timestamp = ts
                self.status = status

        now = _dt.now(_tz.utc).replace(minute=0, second=0, microsecond=0)
        fakes = [
            FakeTrade(now - timedelta(hours=1), "FILLED"),
            FakeTrade(now - timedelta(minutes=30), "REJECTED"),  # 30 min ago → truncates to now-1h bucket
            FakeTrade(now, "PAPER"),
            FakeTrade(now, "ERROR"),
        ]

        async def fake_list(hours):
            return list(fakes)

        monkeypatch.setattr(
            server_module.MekkaRepository, "list_trades_within", fake_list
        )
        resp = await client.get("/api/trades/timeline?hours=2")
        assert resp.status == 200
        body = await resp.json()
        assert body["hours"] == 2
        # Two distinct hour buckets — one with filled+rejected, one with paper+error.
        assert body["count"] == 2
        totals = {it["hour_utc"]: it for it in body["items"]}
        h_prev = (now - timedelta(hours=1)).isoformat()
        h_now = now.isoformat()
        assert totals[h_prev]["filled"] == 1
        assert totals[h_prev]["rejected"] == 1
        assert totals[h_now]["paper"] == 1
        assert totals[h_now]["error"] == 1

    async def test_clamps_hours_param(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client
        captured: dict = {}

        async def fake_list(hours):
            captured["hours"] = hours
            return []

        monkeypatch.setattr(
            server_module.MekkaRepository, "list_trades_within", fake_list
        )
        await client.get("/api/trades/timeline?hours=9999")
        assert captured["hours"] == 168  # max_value


class TestBenchmarkEndpoint:
    async def test_returns_normalized_series(self, dashboard_client, monkeypatch):
        client, _ = dashboard_client

        async def fake_market_get_json(url, params, ttl_s, allow_error=False):
            # Binance kline-shape: [openTime, open, high, low, close, volume, ...]
            return [
                [1_700_000_000_000, "1", "1", "1", "100", "1"],
                [1_700_086_400_000, "1", "1", "1", "120", "1"],
                [1_700_172_800_000, "1", "1", "1", "110", "1"],
            ]

        # Force the handler down the deterministic path.
        monkeypatch.setattr(
            MekkaDashboardServer, "_market_get_json",
            lambda self, url, params, ttl_s, allow_error=False: fake_market_get_json(
                url, params, ttl_s, allow_error
            ),
        )
        resp = await client.get("/api/pnl/benchmark?days=3&symbols=BTC")
        assert resp.status == 200
        body = await resp.json()
        assert body["days"] == 3
        assert body["series"][0]["symbol"] == "BTCUSDT"
        ratios = [p["ratio"] for p in body["series"][0]["points"]]
        # First ratio must be exactly 1.0 (close[0]/close[0]).
        assert ratios[0] == 1.0
        assert ratios[1] == 1.2
        assert ratios[2] == 1.1

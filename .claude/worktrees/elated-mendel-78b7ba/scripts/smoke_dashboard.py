"""
scripts/smoke_dashboard.py
==========================
Smoke test do dashboard: sobe o servidor numa porta efêmera, popula uns
snapshots fake, bate em todas as rotas /api/replay/* + /api/incidents/*
e relata OK/FAIL por endpoint.

Uso (do diretório do projeto):
    .venv/bin/python scripts/smoke_dashboard.py

Não depende de pytest/pytest-aiohttp — usa apenas aiohttp e o servidor real
do dashboard (com on_startup/on_shutdown desabilitados para não exigir DB).
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from src.dashboard import server as server_module  # noqa: E402
from src.dashboard.server import MekkaDashboardServer  # noqa: E402


def _make_snapshot(timestamp: str, alerts=None) -> dict:
    return {
        "overview": {
            "timestamp": timestamp,
            "mode": "paper",
            "network": "testnet",
            "total_signals": 10,
            "total_trades": 5,
            "trades_today": 1,
            "executions_today": 1,
        },
        "global_alerts": alerts or [],
        "risk_heatmap": [],
        "risk_drilldown": {},
        "anomalies": [],
        "hero_sla": [],
    }


async def _run() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        snap_dir = Path(tmp) / "snapshots"
        snap_dir.mkdir()
        # Two snapshots; the latter trips a kill switch.
        (snap_dir / "snapshot-20260507T1000.json").write_text(
            json.dumps(_make_snapshot("2026-05-07T10:00:00+00:00")), "utf-8"
        )
        (snap_dir / "snapshot-20260507T1100.json").write_text(
            json.dumps(
                _make_snapshot(
                    "2026-05-07T11:00:00+00:00",
                    alerts=[{"code": "KILL_SWITCH_EVENT", "severity": "CRITICAL"}],
                )
            ),
            "utf-8",
        )

        server_module.SNAPSHOT_DIR = snap_dir
        server = MekkaDashboardServer()
        server._app.on_startup.clear()
        server._app.on_shutdown.clear()

        async with TestClient(TestServer(server._app)) as client:
            checks = [
                ("/api/replay/snapshots", 200),
                ("/api/replay?snapshot=snapshot-20260507T1000.json", 200),
                ("/api/replay?snapshot=../etc/passwd", 400),
                ("/api/replay/export?format=json", 200),
                ("/api/replay/export?format=csv", 200),
                (
                    "/api/replay/compare"
                    "?a=snapshot-20260507T1000.json"
                    "&b=snapshot-20260507T1100.json",
                    200,
                ),
                ("/api/replay/incident/latest", 200),
                ("/api/replay/incident/latest/download", 200),
                ("/api/replay/timeseries", 200),
                ("/api/incidents/queue", 200),
            ]
            for path, expected in checks:
                resp = await client.get(path)
                actual = resp.status
                tag = "OK" if actual == expected else "FAIL"
                print(f"  [{tag}] GET {path} -> {actual} (expected {expected})")
                if actual != expected:
                    failures.append(f"{path} got {actual}, expected {expected}")

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("\nAll dashboard endpoints responded with the expected status codes.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))

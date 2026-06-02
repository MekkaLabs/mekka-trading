"""
tests/test_batman_scalp_gates.py
==================================
Cobertura dos 2 novos scalp gates do Batman:
  - 3s: max_trades_per_hour
  - 3t: max_position_age (sentinel)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.agents.batman_scalp_gates import (
    GateResult,
    evaluate_all_scalp_gates,
    gate_max_position_age,
    gate_max_trades_per_hour,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Cria um SQLite temporário com schema mínimo de trades."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                symbol TEXT,
                status TEXT,
                side TEXT,
                quantity REAL,
                avg_price REAL,
                notional_usd REAL,
                pnl_usd REAL
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return db


def _insert_trade(db: Path, ts: datetime, status: str = "FILLED") -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO trades(timestamp, symbol, status, side, quantity, avg_price) "
            "VALUES (?,?,?,?,?,?)",
            (ts.isoformat(), "BTC", status, "long", 0.01, 100000.0),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gate 3s — max_trades_per_hour
# ---------------------------------------------------------------------------


class TestGateMaxTradesPerHour:
    def test_no_cap_returns_allow(self):
        result = gate_max_trades_per_hour({}, db_path=Path("/tmp/nonexistent.db"))
        assert result.gate_id == "3s"
        assert result.allowed is True
        assert "no scalp cap" in result.reason

    def test_cap_zero_returns_allow(self):
        result = gate_max_trades_per_hour({"max_trades_per_hour": 0}, db_path=Path("/tmp/nonexistent.db"))
        assert result.allowed is True

    def test_db_missing_returns_allow_failsilent(self, tmp_path):
        ghost = tmp_path / "no_such_db.db"
        result = gate_max_trades_per_hour({"max_trades_per_hour": 6}, db_path=ghost)
        assert result.allowed is True
        assert "db unavailable" in result.reason

    def test_under_cap_allows(self, temp_db):
        # 3 trades na última hora, cap = 6
        now = datetime.now(timezone.utc)
        for i in range(3):
            _insert_trade(temp_db, now - timedelta(minutes=i * 5))
        result = gate_max_trades_per_hour({"max_trades_per_hour": 6}, db_path=temp_db)
        assert result.allowed is True
        assert result.metadata["count_last_hour"] == 3
        assert result.metadata["cap"] == 6

    def test_at_cap_blocks(self, temp_db):
        now = datetime.now(timezone.utc)
        for i in range(6):
            _insert_trade(temp_db, now - timedelta(minutes=i * 5))
        result = gate_max_trades_per_hour({"max_trades_per_hour": 6}, db_path=temp_db)
        assert result.allowed is False
        assert "reached" in result.reason

    def test_over_cap_blocks(self, temp_db):
        now = datetime.now(timezone.utc)
        for i in range(10):
            _insert_trade(temp_db, now - timedelta(minutes=i * 3))
        result = gate_max_trades_per_hour({"max_trades_per_hour": 6}, db_path=temp_db)
        assert result.allowed is False

    def test_older_than_1h_not_counted(self, temp_db):
        now = datetime.now(timezone.utc)
        # 6 trades, todos >1h atrás
        for i in range(6):
            _insert_trade(temp_db, now - timedelta(hours=2 + i))
        result = gate_max_trades_per_hour({"max_trades_per_hour": 6}, db_path=temp_db)
        assert result.allowed is True
        assert result.metadata["count_last_hour"] == 0

    def test_error_status_excluded(self, temp_db):
        now = datetime.now(timezone.utc)
        # 5 FILLED + 3 ERROR — só FILLED contam
        for i in range(5):
            _insert_trade(temp_db, now - timedelta(minutes=i), status="FILLED")
        for i in range(3):
            _insert_trade(temp_db, now - timedelta(minutes=i), status="ERROR")
        result = gate_max_trades_per_hour({"max_trades_per_hour": 6}, db_path=temp_db)
        assert result.allowed is True
        assert result.metadata["count_last_hour"] == 5


# ---------------------------------------------------------------------------
# Gate 3t — max_position_age (sentinel)
# ---------------------------------------------------------------------------


class TestGateMaxPositionAge:
    def test_no_cap_allows(self):
        result = gate_max_position_age({}, [])
        assert result.allowed is True
        assert "no scalp age cap" in result.reason

    def test_no_positions_allows(self):
        result = gate_max_position_age({"max_position_age_minutes": 30}, [])
        assert result.allowed is True

    def test_fresh_positions_allow(self):
        now = datetime.now(timezone.utc)
        positions = [
            {"symbol": "BTC", "opened_at": (now - timedelta(minutes=5)).isoformat()},
            {"symbol": "ETH", "opened_at": (now - timedelta(minutes=10)).isoformat()},
        ]
        result = gate_max_position_age({"max_position_age_minutes": 30}, positions)
        assert result.allowed is True

    def test_stale_position_sentinel_warning(self):
        # P1-5 (2026-05-28): comportamento de duas camadas
        # - soft cap (30min): sentinel, allowed=True, reporta no metadata
        # - hard cap (cap × 1.5 = 45min): BLOQUEIA
        # 35min está entre soft e hard → sentinel
        now = datetime.now(timezone.utc)
        positions = [
            {"symbol": "BTC", "opened_at": (now - timedelta(minutes=35)).isoformat()},
        ]
        result = gate_max_position_age({"max_position_age_minutes": 30}, positions)
        assert result.allowed is True  # entre soft e hard — sentinel
        assert len(result.metadata["stale_positions"]) == 1
        assert result.metadata["stale_positions"][0]["symbol"] == "BTC"
        assert result.metadata["stale_positions"][0]["age_minutes"] >= 35

    def test_hard_cap_breach_blocks(self):
        # P1-5: posição com age >= cap × 1.5 BLOQUEIA novos trades
        now = datetime.now(timezone.utc)
        positions = [
            {"symbol": "BTC", "opened_at": (now - timedelta(minutes=50)).isoformat()},
        ]
        result = gate_max_position_age({"max_position_age_minutes": 30}, positions)
        assert result.allowed is False  # 50min > hard cap 45min
        assert "hard cap" in result.reason
        assert len(result.metadata["hard_breach_positions"]) == 1
        assert result.metadata["hard_breach_positions"][0]["age_minutes"] >= 50

    def test_hard_cap_multiplier_override(self):
        # Override do multiplicador via mode_params
        now = datetime.now(timezone.utc)
        positions = [
            {"symbol": "BTC", "opened_at": (now - timedelta(minutes=40)).isoformat()},
        ]
        # cap=30, multiplier=2.0 → hard cap = 60min. 40min ainda OK (sentinel)
        result = gate_max_position_age(
            {"max_position_age_minutes": 30, "max_position_age_hard_multiplier": 2.0},
            positions,
        )
        assert result.allowed is True  # 40min < hard cap 60min

    def test_invalid_timestamp_skipped(self):
        positions = [
            {"symbol": "BTC", "opened_at": "not-a-date"},
            {"symbol": "ETH"},  # sem timestamp
        ]
        result = gate_max_position_age({"max_position_age_minutes": 30}, positions)
        assert result.allowed is True
        assert "stale_positions" not in result.metadata or not result.metadata.get("stale_positions")


# ---------------------------------------------------------------------------
# evaluate_all_scalp_gates
# ---------------------------------------------------------------------------


class TestEvaluateAllScalpGates:
    def test_returns_both_gates(self, temp_db):
        results = evaluate_all_scalp_gates(
            {"max_trades_per_hour": 6, "max_position_age_minutes": 30},
            open_positions=[],
            db_path=temp_db,
        )
        assert len(results) == 2
        gate_ids = {r.gate_id for r in results}
        assert gate_ids == {"3s", "3t"}

    def test_all_allow_when_no_params(self):
        results = evaluate_all_scalp_gates({}, open_positions=[])
        assert all(r.allowed for r in results)

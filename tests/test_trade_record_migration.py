"""
tests/test_trade_record_migration.py
======================================
Smoke tests do script migrate_trade_quote_columns.py:
  - idempotência (rodar 2x não falha)
  - dry-run não modifica DB
  - apply adiciona colunas com defaults certos
  - backup criado em apply
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# Import the migration module
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import migrate_trade_quote_columns as mig  # type: ignore


def _make_trades_table(db_path: Path) -> None:
    """Cria um DB com schema trades MINIMAL (sem as colunas novas)."""
    conn = sqlite3.connect(str(db_path))
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
        conn.execute("INSERT INTO trades(symbol, status) VALUES ('BTC', 'FILLED')")
        conn.commit()
    finally:
        conn.close()


def _list_columns(db_path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]
    finally:
        conn.close()


class TestMigrationDryRun:
    def test_dry_run_no_changes(self, tmp_path):
        db = tmp_path / "test.db"
        _make_trades_table(db)
        cols_before = _list_columns(db, "trades")
        summary = mig.migrate(db, apply=False)
        cols_after = _list_columns(db, "trades")
        assert cols_before == cols_after
        assert "quote_currency" not in cols_after
        assert "pnl_quote" not in cols_after
        assert any("DRY-RUN" in a for a in summary["actions"])
        assert summary["backup_created"] is None

    def test_dry_run_db_missing(self, tmp_path):
        db = tmp_path / "nonexistent.db"
        summary = mig.migrate(db, apply=False)
        assert summary["db_exists"] is False
        assert any("SKIP" in a for a in summary["actions"])


class TestMigrationApply:
    def test_apply_adds_columns(self, tmp_path):
        db = tmp_path / "test.db"
        _make_trades_table(db)
        summary = mig.migrate(db, apply=True)
        cols = _list_columns(db, "trades")
        assert "quote_currency" in cols
        assert "pnl_quote" in cols
        assert summary["backup_created"] is not None
        assert Path(summary["backup_created"]).exists()

    def test_apply_default_quote_currency(self, tmp_path):
        db = tmp_path / "test.db"
        _make_trades_table(db)
        mig.migrate(db, apply=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.execute("SELECT quote_currency, pnl_quote FROM trades")
            row = cur.fetchone()
            assert row[0] == "USDT"
            assert row[1] is None
        finally:
            conn.close()

    def test_apply_idempotent(self, tmp_path):
        db = tmp_path / "test.db"
        _make_trades_table(db)
        # Roda 2x — segunda vez deve SKIP
        mig.migrate(db, apply=True)
        summary2 = mig.migrate(db, apply=True)
        assert any("SKIP: quote_currency already exists" in a for a in summary2["actions"])
        assert any("SKIP: pnl_quote already exists" in a for a in summary2["actions"])
        assert not summary2["errors"]

    def test_apply_preserves_existing_data(self, tmp_path):
        db = tmp_path / "test.db"
        _make_trades_table(db)
        mig.migrate(db, apply=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.execute("SELECT symbol, status FROM trades")
            row = cur.fetchone()
            assert row == ("BTC", "FILLED")
        finally:
            conn.close()


class TestMigrationTableMissing:
    def test_no_trades_table_skips_gracefully(self, tmp_path):
        # DB existe mas sem table 'trades'
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE other (id INTEGER)")
        conn.commit()
        conn.close()
        summary = mig.migrate(db, apply=True)
        assert summary["table_exists"] is False
        assert any("trades' table not yet created" in a for a in summary["actions"])

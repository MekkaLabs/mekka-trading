#!/usr/bin/env python3
"""
scripts/migrate_trade_quote_columns.py
========================================
Migration idempotente para adicionar colunas COIN-M Futures ao TradeRecord:
  - quote_currency: VARCHAR(8) NOT NULL DEFAULT 'USDT'
  - pnl_quote: REAL NULL

Comportamento:
  - **Idempotente**: usa PRAGMA table_info para detectar coluna; pula se já existe.
  - **Safe**: faz backup do DB ANTES de qualquer ALTER (cópia para
    data/mekka_trading.db.bak-YYYYMMDD-HHMMSS).
  - **Fail-safe**: se ALTER falhar, backup permite rollback manual.
  - **Verbose**: imprime cada step.

Uso:
    python3 scripts/migrate_trade_quote_columns.py            # dry-run
    python3 scripts/migrate_trade_quote_columns.py --apply    # aplica

Pode ser chamado pelo dashboard no startup (best-effort, fail-silent).
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_DB_PATH = _REPO / "data" / "mekka_trading.db"


def _backup_db(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_suffix(f".db.bak-{ts}")
    try:
        shutil.copy2(db_path, backup)
        return backup
    except OSError as exc:
        print(f"  ⚠️  backup failed: {exc}", file=sys.stderr)
        return None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def migrate(db_path: Path, apply: bool = False) -> dict:
    """Run migration. Returns summary dict."""
    summary: dict = {
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "table_exists": False,
        "quote_currency_exists": False,
        "pnl_quote_exists": False,
        "actions": [],
        "backup_created": None,
        "errors": [],
    }

    if not db_path.exists():
        summary["actions"].append("SKIP: DB does not exist (will be created with schema on next boot)")
        return summary

    if apply:
        bak = _backup_db(db_path)
        if bak:
            summary["backup_created"] = str(bak)
            print(f"  ✓ backup: {bak.name}")

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "trades"):
            summary["actions"].append("SKIP: 'trades' table not yet created")
            return summary
        summary["table_exists"] = True

        # Check + ALTER quote_currency
        if _column_exists(conn, "trades", "quote_currency"):
            summary["quote_currency_exists"] = True
            summary["actions"].append("SKIP: quote_currency already exists")
        else:
            sql = "ALTER TABLE trades ADD COLUMN quote_currency VARCHAR(8) NOT NULL DEFAULT 'USDT'"
            if apply:
                try:
                    conn.execute(sql)
                    conn.commit()
                    summary["actions"].append("ADDED: quote_currency (default 'USDT')")
                except sqlite3.Error as exc:
                    summary["errors"].append(f"quote_currency ALTER failed: {exc}")
            else:
                summary["actions"].append(f"DRY-RUN: would run `{sql}`")

        # Check + ALTER pnl_quote
        if _column_exists(conn, "trades", "pnl_quote"):
            summary["pnl_quote_exists"] = True
            summary["actions"].append("SKIP: pnl_quote already exists")
        else:
            sql = "ALTER TABLE trades ADD COLUMN pnl_quote REAL"
            if apply:
                try:
                    conn.execute(sql)
                    conn.commit()
                    summary["actions"].append("ADDED: pnl_quote (REAL NULL)")
                except sqlite3.Error as exc:
                    summary["errors"].append(f"pnl_quote ALTER failed: {exc}")
            else:
                summary["actions"].append(f"DRY-RUN: would run `{sql}`")
    finally:
        conn.close()

    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Migrate trades table — add COIN-M support (quote_currency, pnl_quote)"
    )
    ap.add_argument("--apply", action="store_true",
                    help="Apply changes (default: dry-run)")
    ap.add_argument("--db", type=Path, default=_DB_PATH,
                    help=f"Path to SQLite DB (default: {_DB_PATH})")
    args = ap.parse_args()

    print(f"=== Trade table COIN-M migration — {'APPLY' if args.apply else 'DRY-RUN'} ===")
    print(f"DB: {args.db}")
    print()

    summary = migrate(args.db, apply=args.apply)

    print("Actions:")
    for a in summary["actions"]:
        print(f"  • {a}")

    if summary["errors"]:
        print("\nErrors:")
        for e in summary["errors"]:
            print(f"  ✗ {e}")
        return 1

    if summary["backup_created"]:
        print(f"\nBackup: {summary['backup_created']}")

    if not args.apply and (
        not summary["quote_currency_exists"] or not summary["pnl_quote_exists"]
    ):
        print("\nRun with --apply to execute changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

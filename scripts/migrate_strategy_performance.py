#!/usr/bin/env python3
"""
scripts/migrate_strategy_performance.py
=========================================
Migration idempotente para criar a tabela ``strategy_performance`` que o
Be Water Framework usa para rastrear performance por
(strategy_name × regime × symbol).

Comportamento
-------------
- **Idempotente**: se a tabela já existir, faz NO-OP.
- **Safe**: backup do DB ANTES de qualquer DDL (cópia para
  data/mekka_trading.db.bak-YYYYMMDD-HHMMSS).
- **Verbose**: imprime cada step.
- **Dry-run por default**: nada é aplicado sem ``--apply``.

Schema criado
-------------
strategy_performance:
  id                  INTEGER PK AUTOINCREMENT
  strategy_name       VARCHAR(64) NOT NULL  (indexed)
  regime              VARCHAR(32) NOT NULL  (indexed)
  symbol              VARCHAR(16) NOT NULL  (indexed)
  timestamp           DATETIME    NOT NULL
  n_trades            INTEGER     DEFAULT 0
  n_wins              INTEGER     DEFAULT 0
  n_losses            INTEGER     DEFAULT 0
  total_pnl_usd       REAL        DEFAULT 0
  total_pnl_pct       REAL        DEFAULT 0
  sum_win_pnl_usd     REAL        DEFAULT 0
  sum_loss_pnl_usd    REAL        DEFAULT 0
  max_drawdown_pct    REAL        DEFAULT 0
  sharpe_ratio        REAL        NULL
  last_trade_at       DATETIME    NULL
  UNIQUE(strategy_name, regime, symbol)

Uso:
    python3 scripts/migrate_strategy_performance.py            # dry-run
    python3 scripts/migrate_strategy_performance.py --apply    # aplica
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


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS strategy_performance (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name    VARCHAR(64) NOT NULL,
    regime           VARCHAR(32) NOT NULL,
    symbol           VARCHAR(16) NOT NULL,
    timestamp        DATETIME    NOT NULL,
    n_trades         INTEGER     NOT NULL DEFAULT 0,
    n_wins           INTEGER     NOT NULL DEFAULT 0,
    n_losses         INTEGER     NOT NULL DEFAULT 0,
    total_pnl_usd    REAL        NOT NULL DEFAULT 0,
    total_pnl_pct    REAL        NOT NULL DEFAULT 0,
    sum_win_pnl_usd  REAL        NOT NULL DEFAULT 0,
    sum_loss_pnl_usd REAL        NOT NULL DEFAULT 0,
    max_drawdown_pct REAL        NOT NULL DEFAULT 0,
    sharpe_ratio     REAL,
    last_trade_at    DATETIME,
    CONSTRAINT uq_strategy_perf_triple UNIQUE (strategy_name, regime, symbol)
)
""".strip()

_INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS ix_strategy_performance_strategy_name "
    "ON strategy_performance (strategy_name)",
    "CREATE INDEX IF NOT EXISTS ix_strategy_performance_regime "
    "ON strategy_performance (regime)",
    "CREATE INDEX IF NOT EXISTS ix_strategy_performance_symbol "
    "ON strategy_performance (symbol)",
]


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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def migrate(db_path: Path, apply: bool = False) -> dict:
    summary: dict = {
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "table_existed": False,
        "actions": [],
        "backup_created": None,
        "errors": [],
    }

    if not db_path.exists():
        summary["actions"].append(
            "SKIP: DB does not exist yet — first app boot will create it via "
            "Base.metadata.create_all() (no migration needed)."
        )
        return summary

    if apply:
        bak = _backup_db(db_path)
        if bak:
            summary["backup_created"] = str(bak)
            print(f"  ✓ backup: {bak.name}")

    conn = sqlite3.connect(str(db_path))
    try:
        already = _table_exists(conn, "strategy_performance")
        summary["table_existed"] = already

        if already:
            summary["actions"].append("SKIP: strategy_performance already exists")
        else:
            if apply:
                try:
                    conn.execute(_CREATE_SQL)
                    for idx_sql in _INDEX_SQLS:
                        conn.execute(idx_sql)
                    conn.commit()
                    summary["actions"].append(
                        "CREATED: strategy_performance + 3 indexes"
                    )
                except sqlite3.Error as exc:
                    summary["errors"].append(f"CREATE TABLE failed: {exc}")
            else:
                summary["actions"].append(
                    "DRY-RUN: would CREATE TABLE strategy_performance + 3 indexes"
                )
    finally:
        conn.close()

    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create strategy_performance table for the Be Water Framework"
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default: dry-run)",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=_DB_PATH,
        help=f"Path to SQLite DB (default: {_DB_PATH})",
    )
    args = ap.parse_args()

    print(
        f"=== strategy_performance migration — "
        f"{'APPLY' if args.apply else 'DRY-RUN'} ==="
    )
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

    if not args.apply and not summary["table_existed"] and summary["db_exists"]:
        print("\nRun with --apply to execute changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

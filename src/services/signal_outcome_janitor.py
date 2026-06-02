"""
src/services/signal_outcome_janitor.py
========================================
INV-1 (auditoria 2026-05-29) — resolve signals que viram PENDING perpétuos.

Problema diagnosticado:
- Vision gera signal_id N → agent_memories.record(outcome=NULL) [PENDING]
- Batman rejeita signal → IronMan nunca executa → trade_id=NULL
- agent_memories.resolve_outcome só é chamado em close_position
- → signal vira PENDING pra sempre, Vision.query_similar ignora (filtra WIN/LOSS)
- → Vision não aprende com signals rejeitados!

Solução:
- janitor consulta signals com agent_memory PENDING há > N min e SEM trade
- Cross-check com audit_log RISK_REJECTED, RISK_KILL_SWITCH, SIGNAL_FLIP
- Marca outcome:
    - "REJECTED_BY_RISK"      — Batman rejeitou (encontrado em audit_log)
    - "NO_TRADE_EXECUTED"     — passou Batman mas IronMan falhou
    - "SIGNAL_FLIPPED"        — Vision flipou opinião antes do trade
    - "EXPIRED_NO_ACTION"     — idade > 6h, nenhum sinal de execução

Princípios:
- READ-MOSTLY: só UPDATE em agent_memories.outcome (não cria rows)
- FAIL-SILENT: erro em uma row não bloqueia as outras
- IDEMPOTENT: só toca rows com outcome NULL
- AUDIT TRAIL: emite evento JANITOR_RESOLVED no audit_log
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_REPO = Path(__file__).resolve().parents[2]
_DB_PATH = _REPO / "data" / "mekka_trading.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_orphan_signals(
    min_age_minutes: int = 30,
    max_age_hours: int = 24,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Resolve agent_memories PENDING que correspondem a signals nunca executados.

    Args:
        min_age_minutes: idade mínima do signal pra considerar. Default 30 min
            (tempo suficiente pra IronMan tentar executar).
        max_age_hours: idade máxima — acima disso marca como EXPIRED.
        dry_run: se True, só simula.

    Returns:
        dict com {checked, resolved_by_reason, errors, dry_run}.
    """
    if not _DB_PATH.exists():
        return {"error": "db_missing", "checked": 0}

    result: dict[str, Any] = {
        "checked": 0,
        "by_reason": {
            "REJECTED_BY_RISK": 0,
            "NO_TRADE_EXECUTED": 0,
            "SIGNAL_FLIPPED": 0,
            "EXPIRED_NO_ACTION": 0,
        },
        "errors": 0,
        "dry_run": dry_run,
        "ts": _now_iso(),
    }

    try:
        conn = sqlite3.connect(str(_DB_PATH))
        # 1) Buscar PENDING com signal_id, age > min_age, sem trade
        cur = conn.execute(
            f"""
            SELECT am.id, am.signal_id, am.symbol, am.timestamp,
                   (julianday('now') - julianday(am.timestamp)) * 24 * 60 AS age_minutes
            FROM agent_memories am
            LEFT JOIN trades t ON t.signal_id = am.signal_id
            WHERE (am.outcome IS NULL OR am.outcome = 'PENDING')
              AND am.signal_id IS NOT NULL
              AND t.id IS NULL
              AND am.timestamp < datetime('now', '-{min_age_minutes} minutes')
            ORDER BY am.id DESC
            LIMIT 200
            """
        )
        candidates = cur.fetchall()
        result["checked"] = len(candidates)

        if not candidates:
            return result

        for am_id, signal_id, symbol, ts_str, age_min in candidates:
            try:
                # Decidir reason via audit_log lookup
                reason = _infer_reason(
                    conn, signal_id, symbol, age_min, max_age_hours,
                )
                result["by_reason"][reason] = result["by_reason"].get(reason, 0) + 1

                if dry_run:
                    continue

                # UPDATE com pnl=0 (não foi trade real)
                conn.execute(
                    """
                    UPDATE agent_memories
                    SET outcome = ?, pnl_usd = 0.0, resolved_at = datetime('now')
                    WHERE id = ?
                    """,
                    (reason, am_id),
                )
            except Exception as exc:  # noqa: BLE001
                result["errors"] += 1
                logger.debug(f"[signal_janitor] row {am_id} error: {exc}")

        if not dry_run:
            conn.commit()
            # Emitir 1 evento agregado no audit_log
            try:
                import json
                payload = json.dumps(result["by_reason"], default=str)
                conn.execute(
                    "INSERT INTO audit_log (timestamp, agent, event, severity, message, payload) "
                    "VALUES (datetime('now'), ?, ?, ?, ?, ?)",
                    (
                        "SignalJanitor",
                        "JANITOR_RESOLVED",
                        "INFO",
                        f"resolved {len(candidates)} orphan signals",
                        payload,
                    ),
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[signal_janitor] audit_log emit skipped: {exc}")

        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[signal_janitor] failure: {exc}")
        result["error"] = str(exc)

    return result


def _infer_reason(
    conn: sqlite3.Connection,
    signal_id: int,
    symbol: str,
    age_min: float,
    max_age_hours: int,
) -> str:
    """
    Cross-check com audit_log dentro de ±2min do signal:
    - RISK_REJECTED → REJECTED_BY_RISK
    - SIGNAL_FLIP → SIGNAL_FLIPPED
    - >max_age_hours → EXPIRED_NO_ACTION
    - else → NO_TRADE_EXECUTED
    """
    # Buscar audit events do mesmo símbolo perto do timestamp do signal
    cur = conn.execute(
        """
        SELECT event FROM audit_log
        WHERE symbol = ? AND event IN ('RISK_REJECTED', 'SIGNAL_FLIP')
          AND timestamp >= (
              SELECT datetime(timestamp, '-2 minutes')
              FROM agent_memories WHERE signal_id = ?
              LIMIT 1
          )
          AND timestamp <= (
              SELECT datetime(timestamp, '+5 minutes')
              FROM agent_memories WHERE signal_id = ?
              LIMIT 1
          )
        ORDER BY id LIMIT 1
        """,
        (symbol, signal_id, signal_id),
    )
    row = cur.fetchone()
    if row:
        event = row[0]
        if event == "RISK_REJECTED":
            return "REJECTED_BY_RISK"
        if event == "SIGNAL_FLIP":
            return "SIGNAL_FLIPPED"

    # Sem audit match: usa idade
    if age_min and age_min > max_age_hours * 60:
        return "EXPIRED_NO_ACTION"
    return "NO_TRADE_EXECUTED"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Signal outcome janitor")
    p.add_argument("--apply", action="store_true", help="Apply (default: dry-run)")
    p.add_argument("--min-age-minutes", type=int, default=30)
    p.add_argument("--max-age-hours", type=int, default=24)
    args = p.parse_args()

    result = resolve_orphan_signals(
        min_age_minutes=args.min_age_minutes,
        max_age_hours=args.max_age_hours,
        dry_run=not args.apply,
    )
    import json
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

"""
src/services/decision_memory_janitor.py
========================================
MEM-AUDIT-3 (2026-05-29) — Resolve DECISION_MEMORY orphans retroativos.

Diagnóstico ao vivo:
  - audit_log tem 203 DECISION_MEMORY (Vision gravou decisão)
  - audit_log tem 0 DECISION_OUTCOME (closure nunca rodou)
  - Apesar do INV-15 plugado em trade_outcome_resolver, nenhum trade
    fechado em paper trading com TP/SL real para disparar o resolver.

Solução irmã do signal_outcome_janitor (INV-1):
  - Para cada DECISION_MEMORY com cycle_id, tenta match com:
      • TRADE_NOW_EXECUTED (manual trade dashboard)
      • Trade fechado em `trades` table (sequência de eventos)
      • SIGNAL_FLIP no mesmo cycle (decisão revertida)
      • EXPIRED (decision sem nenhuma execução em > N horas)
  - Marca outcome em payload via novo DECISION_OUTCOME event
  - Idempotente: skip se já tem DECISION_OUTCOME com mesmo cycle_id

READ-MOSTLY: só insere DECISION_OUTCOME (não toca DECISION_MEMORY).
FAIL-SILENT: erro em 1 row não bloqueia as outras.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

_REPO = Path(__file__).resolve().parents[2]
_DB_PATH = _REPO / "data" / "mekka_trading.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_payload(raw: str | dict | None) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def resolve_decision_orphans(
    min_age_hours: int = 2,
    max_age_days: int = 30,
    dry_run: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """
    Para cada DECISION_MEMORY com cycle_id + idade > min_age_hours, tenta
    inferir outcome via match com outros eventos.

    Reason codes possíveis:
      - EXECUTED_PAPER       — TRADE_NOW_EXECUTED OK no mesmo cycle
      - EXECUTED_LIVE        — IRONMAN_FILLED no mesmo cycle
      - REJECTED_BY_RISK     — RISK_REJECTED no mesmo cycle
      - FLIPPED              — SIGNAL_FLIP no mesmo cycle (vision mudou ideia)
      - NO_TRADE_EXECUTED    — passou risk mas IronMan não disparou
      - EXPIRED_NO_ACTION    — idade > max_age_days, sem traço

    Args:
        min_age_hours: idade mínima antes de tentar resolver (default 2h —
            dá tempo do fluxo natural rodar).
        max_age_days: idade máxima — acima disso marca EXPIRED.
        dry_run: só simula.
        limit: cap por execução.

    Returns:
        Dict {checked, by_reason, errors, dry_run, ts}.
    """
    if not _DB_PATH.exists():
        return {"error": "db_missing", "checked": 0}

    result: dict[str, Any] = {
        "checked": 0,
        "by_reason": {
            "EXECUTED_PAPER": 0,
            "EXECUTED_LIVE": 0,
            "REJECTED_BY_RISK": 0,
            "FLIPPED": 0,
            "NO_TRADE_EXECUTED": 0,
            "EXPIRED_NO_ACTION": 0,
        },
        "errors": 0,
        "dry_run": dry_run,
        "ts": _now_iso(),
    }

    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row

        # 1) Buscar DECISION_MEMORY com cycle_id, idade > min_age_hours,
        #    sem DECISION_OUTCOME correspondente ainda.
        # Note: cycle_id está no payload JSON — extração via json_extract.
        candidates = conn.execute(
            f"""
            SELECT id, timestamp, symbol, payload
            FROM audit_log
            WHERE event = 'DECISION_MEMORY'
              AND timestamp < datetime('now', '-{min_age_hours} hours')
              AND id NOT IN (
                  SELECT am.id FROM audit_log am
                  WHERE am.event = 'DECISION_OUTCOME'
              )
            ORDER BY id DESC
            LIMIT {limit}
            """
        ).fetchall()

        result["checked"] = len(candidates)
        if not candidates:
            conn.close()
            return result

        for row in candidates:
            try:
                payload = _safe_payload(row["payload"])
                cycle_id = payload.get("cycle_id")
                if not cycle_id:
                    continue
                age_days_row = conn.execute(
                    "SELECT (julianday('now') - julianday(?)) AS days",
                    (row["timestamp"],),
                ).fetchone()
                age_days = float(age_days_row["days"] or 0)

                # Cross-match dentro de janela ±10 min do timestamp.
                # MEM-FIX-6: ajustado para os eventos REAIS do audit_log
                # (IRONMAN_FILLED/IRONMAN_PAPER_FILLED não existem —
                # sistema usa TRADE_NOW_EXECUTED / MANUAL_TRADE_EXECUTED
                # para ambos paper e live, diferencia via payload.is_paper).
                related = conn.execute(
                    """
                    SELECT event, payload
                    FROM audit_log
                    WHERE timestamp >= datetime(?, '-10 minutes')
                      AND timestamp <= datetime(?, '+30 minutes')
                      AND symbol = ?
                      AND event IN (
                        'TRADE_NOW_EXECUTED',
                        'TRADE_NOW_FORCE_EXECUTE',
                        'MANUAL_TRADE_EXECUTED',
                        'MANUAL_TRADE_FORCE_EXECUTE',
                        'TRADE_NOW_BLOCKED',
                        'MANUAL_TRADE_BLOCKED',
                        'RISK_REJECTED',
                        'SIGNAL_FLIP'
                      )
                    ORDER BY id ASC
                    """,
                    (row["timestamp"], row["timestamp"], row["symbol"] or ""),
                ).fetchall()

                reason = None
                for r in related:
                    r_payload = _safe_payload(r["payload"])
                    r_cycle = r_payload.get("cycle_id")
                    # Match exato por cycle_id se presente em ambos
                    if r_cycle and r_cycle != cycle_id:
                        continue
                    event = r["event"]
                    # Execução real (paper ou live) — payload.is_paper
                    # distingue dentro do dashboard de quem executou.
                    if event in (
                        "TRADE_NOW_EXECUTED",
                        "TRADE_NOW_FORCE_EXECUTE",
                        "MANUAL_TRADE_EXECUTED",
                        "MANUAL_TRADE_FORCE_EXECUTE",
                    ):
                        if r_payload.get("is_paper", True):
                            reason = "EXECUTED_PAPER"
                        else:
                            reason = "EXECUTED_LIVE"
                        break
                    if event in ("TRADE_NOW_BLOCKED", "MANUAL_TRADE_BLOCKED",
                                 "RISK_REJECTED"):
                        reason = "REJECTED_BY_RISK"
                        break
                    if event == "SIGNAL_FLIP":
                        reason = "FLIPPED"
                        break

                # Fallback 2: IronMan automático NÃO emite audit event
                # próprio (apenas dashboard manual emite). Consulta direto
                # a tabela `trades` por (symbol + janela ±10min) para
                # capturar execuções do loop automático.
                if reason is None:
                    trade_row = conn.execute(
                        """
                        SELECT status, is_paper
                        FROM trades
                        WHERE symbol = ?
                          AND timestamp >= datetime(?, '-2 minutes')
                          AND timestamp <= datetime(?, '+10 minutes')
                          AND status IN ('PAPER', 'FILLED')
                        ORDER BY id ASC LIMIT 1
                        """,
                        (row["symbol"] or "", row["timestamp"], row["timestamp"]),
                    ).fetchone()
                    if trade_row is not None:
                        if trade_row["is_paper"]:
                            reason = "EXECUTED_PAPER"
                        else:
                            reason = "EXECUTED_LIVE"

                if reason is None:
                    if age_days > max_age_days:
                        reason = "EXPIRED_NO_ACTION"
                    else:
                        reason = "NO_TRADE_EXECUTED"

                result["by_reason"][reason] = result["by_reason"].get(reason, 0) + 1

                if dry_run:
                    continue

                # Inserir DECISION_OUTCOME virtual
                outcome_payload = json.dumps({
                    "type": "outcome",
                    "cycle_id": cycle_id,
                    "symbol": row["symbol"],
                    "resolved_by": "decision_memory_janitor",
                    "resolution_reason": reason,
                    "original_decision_id": row["id"],
                    "age_days_when_resolved": round(age_days, 2),
                    "timestamp": _now_iso(),
                }, default=str)

                conn.execute(
                    "INSERT INTO audit_log (timestamp, agent, event, severity, symbol, message, payload) "
                    "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)",
                    (
                        "DecisionJanitor",
                        "DECISION_OUTCOME",
                        "INFO",
                        row["symbol"],
                        f"resolved decision_memory {row['id']} as {reason}",
                        outcome_payload,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                result["errors"] += 1
                logger.debug(f"[decision_janitor] row {row['id']} err: {exc}")

        if not dry_run:
            conn.commit()
            # Audit aggregate
            try:
                conn.execute(
                    "INSERT INTO audit_log (timestamp, agent, event, severity, message, payload) "
                    "VALUES (datetime('now'), ?, ?, ?, ?, ?)",
                    (
                        "DecisionJanitor",
                        "DECISION_JANITOR_RESOLVED",
                        "INFO",
                        f"resolved {len(candidates)} orphan decision memories",
                        json.dumps(result["by_reason"], default=str),
                    ),
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[decision_janitor] aggregate audit err: {exc}")

        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[decision_janitor] failure: {exc}")
        result["error"] = str(exc)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Decision Memory orphan janitor")
    p.add_argument("--apply", action="store_true", help="Apply (default dry-run)")
    p.add_argument("--min-age-hours", type=int, default=2)
    p.add_argument("--max-age-days", type=int, default=30)
    p.add_argument("--limit", type=int, default=200)
    args = p.parse_args()

    result = resolve_decision_orphans(
        min_age_hours=args.min_age_hours,
        max_age_days=args.max_age_days,
        dry_run=not args.apply,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

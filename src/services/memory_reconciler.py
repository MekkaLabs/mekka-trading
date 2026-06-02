"""
src/services/memory_reconciler.py
====================================
Reconciler retroativo de AgentMemoryRecord órfãos.

Background (CIO Engineer audit, 2026-05-27):
  Antes do fix do `_emergency_flatten` (commit pendente desta sessão),
  104/105 rows em `agent_memories` ficaram PENDING (outcome=NULL,
  resolved_at=NULL). Mesmo agora com `resolve_trade_memories` chamado
  em todos os close-paths, os PENDING históricos não se resolvem
  sozinhos — ninguém ainda os encontra.

Este job idempotente varre PENDING com mais de N horas (default 4h)
e tenta cruzá-los com `trades` (mesmo símbolo, janela temporal próxima)
para atribuir outcome retroativamente. Quando não consegue, marca
como `ORPHAN_RECONCILED` (vs `WIN/LOSS/NEUTRAL`) — sinal de que foi
auto-resolvido sem trade match.

Hard rules:
  - Idempotente (re-rodar é seguro)
  - Fail-silent
  - Não modifica `trades`/`signal_records` (só `agent_memories`)
  - Default conservador: pnl=0.0 (NEUTRAL) quando há trade match mas
    pnl não está no DB; só inferimos WIN/LOSS quando trade.pnl é claro.

Uso (CLI/cron):
    python -m src.services.memory_reconciler --dry-run
    python -m src.services.memory_reconciler --apply
    python -m src.services.memory_reconciler --apply --min-age-h 1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import and_, func, select

from src.persistence.db import get_session
from src.persistence.models import AgentMemoryRecord, TradeRecord


async def find_orphan_pending(min_age_hours: float = 4.0) -> list[dict[str, Any]]:
    """Lista rows PENDING há mais de `min_age_hours`. Read-only."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    async with get_session() as s:
        stmt = (
            select(AgentMemoryRecord)
            .where(
                and_(
                    AgentMemoryRecord.outcome.in_((None, "PENDING")),
                    AgentMemoryRecord.timestamp < cutoff,
                )
            )
            .order_by(AgentMemoryRecord.timestamp.asc())
            .limit(500)
        )
        rows = (await s.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id, "symbol": r.symbol, "action": r.action,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "confidence": r.confidence,
        }
        for r in rows
    ]


async def _find_matching_trade(
    session, symbol: str, ts: datetime,
    window_hours: float = 24.0,
) -> Optional[TradeRecord]:
    """Procura trade do mesmo símbolo fechado dentro de uma janela ±window_hours."""
    lo = ts - timedelta(hours=window_hours)
    hi = ts + timedelta(hours=window_hours)
    stmt = (
        select(TradeRecord)
        .where(
            and_(
                TradeRecord.symbol == symbol,
                TradeRecord.timestamp >= lo,
                TradeRecord.timestamp <= hi,
            )
        )
        .order_by(TradeRecord.timestamp.asc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row


def _outcome_from_pnl(pnl: Optional[float]) -> str:
    if pnl is None:
        return "ORPHAN_RECONCILED"
    if pnl > 0.5:
        return "WIN"
    if pnl < -0.5:
        return "LOSS"
    return "NEUTRAL"


async def reconcile_orphans(
    min_age_hours: float = 4.0, apply: bool = False, limit: int = 200,
) -> dict[str, Any]:
    """
    Varre PENDING órfãos e tenta resolver.

    Returns dict com counts. Em apply=False, só sugere (dry-run).
    """
    report: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "min_age_hours": min_age_hours,
        "apply": apply,
        "found_pending": 0,
        "resolved_by_trade_match": 0,
        "resolved_orphan_no_match": 0,
        "errors": 0,
        "samples": [],
    }

    async with get_session() as s:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
        stmt = (
            select(AgentMemoryRecord)
            .where(
                and_(
                    AgentMemoryRecord.outcome.in_((None, "PENDING")),
                    AgentMemoryRecord.timestamp < cutoff,
                )
            )
            .order_by(AgentMemoryRecord.timestamp.asc())
            .limit(limit)
        )
        rows = (await s.execute(stmt)).scalars().all()
        report["found_pending"] = len(rows)

        for am in rows:
            try:
                trade = await _find_matching_trade(s, am.symbol, am.timestamp)
                pnl: Optional[float] = None
                if trade is not None:
                    # TradeRecord pode ter pnl_usd ou similar
                    pnl = getattr(trade, "pnl_usd", None) or getattr(trade, "realized_pnl", None)
                outcome = _outcome_from_pnl(pnl)
                if apply:
                    am.outcome = outcome
                    am.pnl_usd = float(pnl) if pnl is not None else 0.0
                    am.resolved_at = datetime.now(timezone.utc)
                if trade is not None:
                    report["resolved_by_trade_match"] += 1
                else:
                    report["resolved_orphan_no_match"] += 1
                if len(report["samples"]) < 8:
                    report["samples"].append({
                        "id": am.id, "symbol": am.symbol, "action": am.action,
                        "matched_trade_id": trade.id if trade else None,
                        "inferred_outcome": outcome,
                        "inferred_pnl": pnl,
                    })
            except Exception as exc:  # noqa: BLE001
                report["errors"] += 1
                logger.debug(f"[reconciler] row {am.id} error: {exc}")
        if apply:
            await s.commit()
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcilia AgentMemoryRecord órfãos PENDING")
    ap.add_argument("--dry-run", action="store_true", help="Padrão: só relatório")
    ap.add_argument("--apply", action="store_true", help="Aplica updates (cuidado!)")
    ap.add_argument("--min-age-h", type=float, default=4.0)
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    if args.apply and args.dry_run:
        print("erro: --apply e --dry-run são mutuamente exclusivos", file=sys.stderr)
        return 1

    report = asyncio.run(reconcile_orphans(
        min_age_hours=args.min_age_h, apply=args.apply, limit=args.limit,
    ))
    import json
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

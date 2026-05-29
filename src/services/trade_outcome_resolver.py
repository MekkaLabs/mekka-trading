"""Centralized resolver that closes the 4 'orphan-writer' memory gaps.

Background — see memory note `project-memory-orphan-writers` (2026-05-25).
Vision injects 3 prompt blocks (DecisionMemory 249, SignalOutcomeMemory 186,
RoleWorkingMemory 183) that historically had readers but no writers. Plus
AgentMemory.resolve_outcome (063) only ran on Cyclops auto-close, not on
manual dashboard closes.

This helper is called from every position-close path so the memories stay
in sync regardless of how a position was closed (SL/TP, manual, emergency).

Each underlying call is independently try/except — one failure never blocks
the others, and the close path itself is never broken by memory errors.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy import select

from src.persistence.db import get_session
from src.persistence.models import SignalRecord


async def resolve_trade_memories(
    *,
    symbol: str,
    pnl_usd: float,
    holding_hours: Optional[float] = None,
    cycle_id: Optional[str] = None,
    action: Optional[str] = None,
    regime: Optional[str] = None,
    confidence: Optional[float] = None,
    trade_id: Optional[str] = None,
    signal_id: Optional[int] = None,
) -> dict:
    """Resolve all memory stores for a closed position.

    Missing action/regime/confidence are best-effort recovered from the most
    recent actionable SignalRecord for the symbol.

    Returns a dict with per-store status (for observability/tests).
    """
    sym = symbol.upper()
    result = {
        "agent_memory": False,
        "role_working": False,
        "signal_outcome": False,
        "decision_memory": False,  # INV-15 (2026-05-29)
    }

    # ── Recover missing context from last actionable signal ─────────────
    if action is None or confidence is None or regime is None:
        try:
            async with get_session() as session:
                stmt = (
                    select(SignalRecord)
                    .where(
                        SignalRecord.symbol == sym,
                        SignalRecord.is_actionable.is_(True),
                        SignalRecord.action.in_(("LONG", "SHORT")),
                    )
                    .order_by(SignalRecord.timestamp.desc())
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                if action is None:
                    action = row.action
                if confidence is None:
                    confidence = float(row.confidence)
                if regime is None:
                    raw = row.raw or {}
                    md = raw.get("metadata") or {}
                    regime = (
                        md.get("market_regime")
                        or md.get("trend")
                        or "UNKNOWN"
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[OutcomeResolver] signal lookup skipped for {sym}: {exc}")

    action = (action or "UNKNOWN").upper()
    regime = (regime or "UNKNOWN").upper()
    confidence = float(confidence) if confidence is not None else 0.0

    # ── 1. AgentMemoryStore (Story 063 — SQLite agent_memories) ─────────
    try:
        from src.persistence.agent_memory import AgentMemoryStore as _AMS  # noqa: WPS433

        result["agent_memory"] = await _AMS.resolve_outcome(
            symbol=sym,
            pnl_usd=pnl_usd,
            holding_hours=holding_hours,
            signal_id=signal_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[OutcomeResolver] AgentMemory.resolve_outcome skipped: {exc}")

    # ── 2. RoleWorkingMemory (Story 183 — in-memory deque) ──────────────
    try:
        from src.services.role_working_memory import (  # noqa: WPS433
            get_role_working_memory as _grwm,
        )

        result["role_working"] = _grwm().resolve_outcome(
            symbol=sym,
            outcome_pnl=pnl_usd,
            cycle_id=cycle_id or "",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[OutcomeResolver] RoleWorkingMemory.resolve_outcome skipped: {exc}")

    # ── 3. SignalOutcomeMemory (Story 186 — in-memory similarity) ───────
    # Only record meaningful outcomes (action known and actionable).
    if action in ("LONG", "SHORT"):
        try:
            from src.services.signal_outcome_memory import (  # noqa: WPS433
                get_signal_outcome_memory as _gsom,
            )

            _gsom().record(
                symbol=sym,
                regime=regime,
                action=action,
                confidence=confidence,
                pnl_usd=pnl_usd,
                trade_id=trade_id or "",
            )
            result["signal_outcome"] = True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[OutcomeResolver] SignalOutcomeMemory.record skipped: {exc}")

    # ── 4. DecisionMemory (Story 249) — INV-15 (2026-05-29) ─────────────
    # Antes: snapshot mostrava 198 decisions, todas PENDING (with_outcome=0).
    # Vision gravava DECISION mas DECISION_OUTCOME nunca era emitido após
    # close — então decision_memory ficava órfão.
    # Agora: cada close resolve a decision do cycle_id correspondente
    # (ou da última decision do símbolo, fallback).
    try:
        from src.services.decision_memory import (  # noqa: WPS433
            DecisionMemoryStore as _DMS,
            DecisionOutcome as _DO,
        )

        # Resolve cycle_id: explícito → última decision do símbolo
        resolved_cycle = cycle_id
        if not resolved_cycle:
            try:
                # Buscar última DECISION_MEMORY do símbolo via audit_log
                from src.persistence.repository import MekkaRepository as _MR  # noqa: WPS433
                recent = await _MR.list_audit_events(
                    agent="Vision",
                    event="DECISION_MEMORY",
                    symbol=sym,
                    limit=1,
                )
                if recent:
                    payload = recent[0].get("payload") or {}
                    if isinstance(payload, str):
                        import json as _json  # noqa: WPS433
                        payload = _json.loads(payload)
                    resolved_cycle = payload.get("cycle_id")
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    f"[OutcomeResolver] cycle_id lookup skipped: {exc}"
                )

        if resolved_cycle:
            # Calcular pnl_pct estimado a partir de pnl_usd
            # (precisão limitada — sem valor de entry, usamos placeholder)
            pnl_pct_est = 0.0
            # Tentativa best-effort: pnl_pct = pnl_usd / equity baseline.
            # Mantemos 0.0 quando não temos baseline — o sinal mais importante
            # é "fechou" + exit_reason, não a magnitude exata.
            # DecisionOutcome só carrega o resultado; cycle_id/symbol vão na
            # chamada record_outcome().
            outcome = _DO(
                realized_pnl_pct=pnl_pct_est,
                hit_target=(pnl_usd > 0),
                duration_hours=holding_hours or 0.0,
                exit_reason="close",  # caller pode override via decisão futura
            )
            await _DMS().record_outcome(
                cycle_id=resolved_cycle,
                symbol=sym,
                outcome=outcome,
            )
            result["decision_memory"] = True
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            f"[OutcomeResolver] DecisionMemory.record_outcome skipped: {exc}"
        )

    return result

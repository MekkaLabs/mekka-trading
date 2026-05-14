"""
src/persistence/agent_memory.py
================================
Story 063 — Agent Episodic Memory

AgentMemoryStore is the single access point for recording and querying
the episodic memory of Vision and Batman.

Concept (inspired by MiroFish's agent-memory architecture)
----------------------------------------------------------
Every time Vision produces a non-HOLD signal, a *memory entry* is
created with the pattern fingerprint extracted from the MarketAnalysis:
RSI bucket, trend direction, volume elevation flag and signal confidence.
The outcome (WIN / LOSS / NEUTRAL) is filled later by Cyclops when the
position is closed via SL or TP.

At the start of each cycle Vision and Batman call
``query_similar()`` to receive a compact context snippet like:

    [Memory] Last 8 similar LONG BTC (RSI≈70, BULLISH, vol⬆):
    Win rate: 62.5% (5W / 3L) | Avg PnL: +1.84% | Avg hold: 13.2h
    Recent: WIN +2.3% (2d), LOSS -1.1% (4d), WIN +1.5% (7d)

This snippet is injected into Vision's user prompt and into Batman's
internal reasoning. Agents do not need to understand embeddings or
vector search — the fingerprint is a small set of categorical + bucketed
numeric features that map naturally to SQL equality / range queries.

Public API
----------
record_signal(symbol, action, rsi, trend, volume_elevated, confidence,
              signal_id) -> int
    Store a PENDING memory entry. Returns the new memory id.

resolve_outcome(symbol, pnl_usd, holding_hours) -> bool
    Find the most recent PENDING entry for symbol and mark it
    WIN / LOSS / NEUTRAL. Returns True if a row was updated.

query_similar(symbol, action, rsi_bucket, trend, limit) -> MemoryContext
    Retrieve the last ``limit`` resolved entries with a matching
    fingerprint and return a structured summary.

build_context_snippet(ctx) -> str
    Convert a MemoryContext into a compact plain-text block ready
    to be appended to a Vision or Batman prompt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger
from sqlalchemy import select, update

from src.persistence.db import get_session
from src.persistence.models import AgentMemoryRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rsi_bucket(rsi: Optional[float]) -> Optional[int]:
    """Round RSI to nearest 10 (e.g. 67 → 70, 32 → 30)."""
    if rsi is None:
        return None
    return int(round(rsi / 10.0) * 10)


def _outcome_label(pnl_usd: float, notional_usd: float = 1000.0) -> str:
    """
    Classify a trade outcome.
    WIN  : pnl_usd > +0.1% of notional
    LOSS : pnl_usd < -0.1% of notional
    NEUTRAL : |pnl_usd| ≤ 0.1% of notional (breakeven / fees)
    """
    threshold = notional_usd * 0.001  # 0.1%
    if pnl_usd > threshold:
        return "WIN"
    if pnl_usd < -threshold:
        return "LOSS"
    return "NEUTRAL"


def _hours_since(ts: Optional[datetime]) -> Optional[float]:
    """Hours elapsed since a UTC timestamp. None if timestamp is None."""
    if ts is None:
        return None
    now = datetime.now(timezone.utc)
    delta = now - ts
    return round(delta.total_seconds() / 3600, 1)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ResolvedMemory:
    """One resolved memory entry returned by query_similar."""
    outcome: str           # WIN / LOSS / NEUTRAL
    pnl_usd: float
    hours_ago: Optional[float]   # how many hours ago this trade was resolved


@dataclass
class MemoryContext:
    """Aggregated result from query_similar."""
    symbol: str
    action: str
    rsi_bucket: Optional[int]
    trend: str
    total: int             # number of resolved memories matched
    wins: int
    losses: int
    neutrals: int
    avg_pnl_usd: float
    avg_holding_hours: Optional[float]
    recent: List[ResolvedMemory] = field(default_factory=list)   # last 3–5

    @property
    def win_rate_pct(self) -> Optional[float]:
        decided = self.wins + self.losses
        if decided == 0:
            return None
        return round(100.0 * self.wins / decided, 1)

    @property
    def has_data(self) -> bool:
        return self.total > 0


# ---------------------------------------------------------------------------
# Main store
# ---------------------------------------------------------------------------

class AgentMemoryStore:
    """
    Async interface to the agent_memories table.
    All methods are static so callers do not need to instantiate the class.
    """

    # -----------------------------------------------------------------------
    # Write path
    # -----------------------------------------------------------------------

    @staticmethod
    async def record_signal(
        symbol: str,
        action: str,
        rsi: Optional[float],
        trend: str,
        volume_elevated: bool,
        confidence: float,
        signal_id: Optional[int] = None,
    ) -> int:
        """
        Create a PENDING memory entry for a new actionable signal.

        Parameters
        ----------
        symbol : e.g. "BTC"
        action : "LONG" or "SHORT"
        rsi    : raw RSI-14 value (will be bucketed internally)
        trend  : "BULLISH" / "BEARISH" / "NEUTRAL"
        volume_elevated : True if volume > 1.5× volume_ma
        confidence : Vision's confidence score (0–1)
        signal_id  : FK to signals table row (optional)

        Returns
        -------
        int — the new AgentMemoryRecord.id
        """
        bucket = _rsi_bucket(rsi)
        record = AgentMemoryRecord(
            symbol=symbol.upper(),
            action=action.upper(),
            rsi_bucket=bucket,
            trend=trend.upper(),
            volume_elevated=volume_elevated,
            confidence=round(confidence, 4),
            signal_id=signal_id,
            outcome="PENDING",
        )
        async with get_session() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
            logger.debug(
                f"[Memory] Recorded PENDING signal for {symbol} {action} "
                f"(RSI≈{bucket}, {trend}) memory_id={record.id}"
            )
            return record.id

    @staticmethod
    async def resolve_outcome(
        symbol: str,
        pnl_usd: float,
        holding_hours: Optional[float] = None,
        signal_id: Optional[int] = None,
    ) -> bool:
        """
        Resolve the most recent PENDING memory entry for ``symbol``.

        Called by Cyclops when SL/TP triggers or by NickFury when a
        position is manually closed.

        Parameters
        ----------
        symbol        : asset symbol (e.g. "BTC")
        pnl_usd       : realised P&L in USD (positive = win)
        holding_hours : how long the position was held
        signal_id     : if provided, prefer matching by signal_id over symbol

        Returns
        -------
        bool — True if a PENDING row was found and updated
        """
        outcome = _outcome_label(pnl_usd)
        now = datetime.now(timezone.utc)

        async with get_session() as session:
            # Prefer exact signal_id match, fall back to most-recent PENDING
            # row for the symbol.
            if signal_id is not None:
                stmt = (
                    select(AgentMemoryRecord)
                    .where(
                        AgentMemoryRecord.signal_id == signal_id,
                        AgentMemoryRecord.outcome == "PENDING",
                    )
                    .order_by(AgentMemoryRecord.timestamp.desc())
                    .limit(1)
                )
            else:
                stmt = (
                    select(AgentMemoryRecord)
                    .where(
                        AgentMemoryRecord.symbol == symbol.upper(),
                        AgentMemoryRecord.outcome == "PENDING",
                    )
                    .order_by(AgentMemoryRecord.timestamp.desc())
                    .limit(1)
                )

            result = await session.execute(stmt)
            row: Optional[AgentMemoryRecord] = result.scalar_one_or_none()

            if row is None:
                logger.debug(f"[Memory] No PENDING memory found for {symbol} — skipping resolve")
                return False

            row.outcome = outcome
            row.pnl_usd = round(pnl_usd, 4)
            row.holding_hours = round(holding_hours, 2) if holding_hours is not None else None
            row.resolved_at = now
            await session.commit()

            logger.info(
                f"[Memory] Resolved {symbol} → {outcome} "
                f"(pnl={pnl_usd:+.4f}, hold={holding_hours:.1f}h) memory_id={row.id}"
            )
            return True

    # -----------------------------------------------------------------------
    # Read path
    # -----------------------------------------------------------------------

    @staticmethod
    async def query_similar(
        symbol: str,
        action: str,
        rsi: Optional[float] = None,
        trend: Optional[str] = None,
        limit: int = 15,
    ) -> MemoryContext:
        """
        Query resolved memories with a matching fingerprint.

        Matching rules (in priority order — all ANDs):
          1. symbol  (exact)
          2. action  (exact: LONG / SHORT)
          3. trend   (exact if provided, else ignored)
          4. rsi_bucket ±10 (if rsi provided and bucket is not None)

        Returns a MemoryContext with aggregated stats + last 5 entries.
        The caller converts it to a prompt snippet via build_context_snippet().
        """
        bucket = _rsi_bucket(rsi) if rsi is not None else None

        async with get_session() as session:
            stmt = (
                select(AgentMemoryRecord)
                .where(
                    AgentMemoryRecord.symbol == symbol.upper(),
                    AgentMemoryRecord.action == action.upper(),
                    AgentMemoryRecord.outcome.in_(["WIN", "LOSS", "NEUTRAL"]),
                )
                .order_by(AgentMemoryRecord.timestamp.desc())
                .limit(limit * 3)   # over-fetch then filter in Python
            )

            if trend:
                stmt = stmt.where(AgentMemoryRecord.trend == trend.upper())

            result = await session.execute(stmt)
            rows: list[AgentMemoryRecord] = list(result.scalars().all())

        # Further filter by RSI bucket (±10) in Python — avoids complex SQL
        if bucket is not None:
            rows = [
                r for r in rows
                if r.rsi_bucket is None
                or abs((r.rsi_bucket or 50) - bucket) <= 10
            ]

        # Take the most recent `limit` after RSI filtering
        rows = rows[:limit]

        if not rows:
            return MemoryContext(
                symbol=symbol,
                action=action,
                rsi_bucket=bucket,
                trend=trend or "ANY",
                total=0,
                wins=0,
                losses=0,
                neutrals=0,
                avg_pnl_usd=0.0,
                avg_holding_hours=None,
            )

        wins = sum(1 for r in rows if r.outcome == "WIN")
        losses = sum(1 for r in rows if r.outcome == "LOSS")
        neutrals = sum(1 for r in rows if r.outcome == "NEUTRAL")
        pnls = [r.pnl_usd for r in rows if r.pnl_usd is not None]
        avg_pnl = round(sum(pnls) / len(pnls), 4) if pnls else 0.0

        holdings = [r.holding_hours for r in rows if r.holding_hours is not None]
        avg_hold = round(sum(holdings) / len(holdings), 1) if holdings else None

        # Recent: last 5 resolved entries for the "Recent:" line
        recent_rows = rows[:5]
        recent = [
            ResolvedMemory(
                outcome=r.outcome,
                pnl_usd=r.pnl_usd or 0.0,
                hours_ago=_hours_since(r.resolved_at),
            )
            for r in recent_rows
        ]

        return MemoryContext(
            symbol=symbol,
            action=action,
            rsi_bucket=bucket,
            trend=trend or "ANY",
            total=len(rows),
            wins=wins,
            losses=losses,
            neutrals=neutrals,
            avg_pnl_usd=avg_pnl,
            avg_holding_hours=avg_hold,
            recent=recent,
        )

    # -----------------------------------------------------------------------
    # Prompt formatting
    # -----------------------------------------------------------------------

    @staticmethod
    def build_context_snippet(ctx: MemoryContext) -> str:
        """
        Convert a MemoryContext into a compact text block for LLM injection.

        Example output:
            [EpisodicMemory] Last 8 similar LONG BTC (RSI≈70, BULLISH):
            Win rate: 62.5% (5W / 3L / 0N) | Avg PnL: +$1.84 | Avg hold: 13.2h
            Recent: WIN +$2.30 (2h ago), LOSS -$1.10 (48h ago), WIN +$1.50 (168h ago)
        """
        if not ctx.has_data:
            return (
                f"[EpisodicMemory] No historical data for {ctx.action} {ctx.symbol} "
                f"({ctx.trend}, RSI≈{ctx.rsi_bucket or '?'}) — first occurrences."
            )

        rsi_str = f"RSI≈{ctx.rsi_bucket}" if ctx.rsi_bucket else "RSI=?"
        header = (
            f"[EpisodicMemory] Last {ctx.total} similar "
            f"{ctx.action} {ctx.symbol} ({rsi_str}, {ctx.trend}):"
        )

        wr = ctx.win_rate_pct
        wr_str = f"{wr:.1f}%" if wr is not None else "N/A"
        hold_str = f"{ctx.avg_holding_hours:.1f}h" if ctx.avg_holding_hours else "N/A"
        pnl_sign = "+" if ctx.avg_pnl_usd >= 0 else ""
        stats = (
            f"Win rate: {wr_str} ({ctx.wins}W / {ctx.losses}L / {ctx.neutrals}N) | "
            f"Avg PnL: {pnl_sign}${ctx.avg_pnl_usd:.2f} | Avg hold: {hold_str}"
        )

        # Recent outcomes line
        recent_parts: list[str] = []
        for r in ctx.recent:
            sign = "+" if r.pnl_usd >= 0 else ""
            ago_str = f"{r.hours_ago:.0f}h ago" if r.hours_ago is not None else "?"
            recent_parts.append(f"{r.outcome} {sign}${r.pnl_usd:.2f} ({ago_str})")
        recent_line = "Recent: " + ", ".join(recent_parts) if recent_parts else ""

        parts = [header, stats]
        if recent_line:
            parts.append(recent_line)
        return "\n".join(parts)

"""
src/models/events.py
====================
Canonical audit-log event codes.

Every event written to `audit_log` (via
`MekkaRepository.log_event(event=...)`) should reference a member of
`AgentEvent`. Free-form strings are still accepted for backward
compatibility, but the enum is the canonical reference.

Adding a new event code:
  1. Add the member here.
  2. Reference it in the agent that emits it.
  3. Update `tests/test_phase5_contracts.py` if the test guard
     enumerates known codes.
"""

from __future__ import annotations

from enum import Enum


class AgentEvent(str, Enum):
    """Canonical audit-log event codes."""

    # ---- Lifecycle (Nick Fury) ----
    BOOT = "BOOT"
    SHUTDOWN = "SHUTDOWN"
    CYCLE_SKIPPED = "CYCLE_SKIPPED"
    CYCLE_ERROR = "CYCLE_ERROR"
    MONITOR_HEARTBEAT = "MONITOR_HEARTBEAT"

    # ---- Risk verdicts (Batman) ----
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REDUCED = "RISK_REDUCED"
    RISK_REJECTED = "RISK_REJECTED"
    RISK_KILL_SWITCH = "RISK_KILL_SWITCH"

    # ---- Execution status (Iron Man) ----
    EXEC_FILLED = "EXEC_FILLED"
    EXEC_PARTIAL = "EXEC_PARTIAL"
    EXEC_REJECTED = "EXEC_REJECTED"
    EXEC_PAPER = "EXEC_PAPER"
    EXEC_ERROR = "EXEC_ERROR"
    EXEC_SKIPPED = "EXEC_SKIPPED"

    # ---- Portfolio Manager ----
    SNAPSHOT_HYPERLIQUID = "SNAPSHOT_HYPERLIQUID"
    SNAPSHOT_PAPER_FALLBACK = "SNAPSHOT_PAPER_FALLBACK"
    SNAPSHOT_OVERRIDE = "SNAPSHOT_OVERRIDE"

    # ---- Daily PnL Writer ----
    DAILY_PNL_RECORDED = "DAILY_PNL_RECORDED"

    # ---- Generic error envelope (any agent) ----
    WRITE_ERROR = "WRITE_ERROR"
    AGENT_ERROR = "AGENT_ERROR"

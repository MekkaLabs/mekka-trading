"""Tests — trade_outcome_resolver (memory orphan-writer fix, 2026-05-25).

Cobre o helper central que resolve as 3 memórias após um close.
Background: ver memory/project-memory-orphan-writers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.trade_outcome_resolver import resolve_trade_memories


@pytest.mark.asyncio
async def test_resolver_calls_all_three_stores_when_action_provided():
    """When action/regime/confidence are passed, resolver hits all 3 stores."""
    fake_ams = MagicMock()
    fake_ams.resolve_outcome = AsyncMock(return_value=True)

    fake_rwm = MagicMock()
    fake_rwm.resolve_outcome = MagicMock(return_value=True)

    fake_som = MagicMock()
    fake_som.record = MagicMock()

    with patch(
        "src.persistence.agent_memory.AgentMemoryStore", fake_ams
    ), patch(
        "src.services.role_working_memory.get_role_working_memory",
        return_value=fake_rwm,
    ), patch(
        "src.services.signal_outcome_memory.get_signal_outcome_memory",
        return_value=fake_som,
    ):
        result = await resolve_trade_memories(
            symbol="BTC",
            pnl_usd=12.5,
            holding_hours=3.2,
            cycle_id="cycle-001",
            action="LONG",
            regime="BULL",
            confidence=0.82,
            trade_id="trade-xyz",
        )

    # INV-15 (2026-05-29) — adicionou decision_memory ao retorno.
    # Quando cycle_id é passado, o resolver tenta record_outcome — True
    # significa "tentamos chamar o writer" (alinhado com o contrato dos
    # outros 3 stores que retornam True na tentativa).
    assert result == {
        "agent_memory": True,
        "role_working": True,
        "signal_outcome": True,
        "decision_memory": True,
    }
    fake_ams.resolve_outcome.assert_awaited_once_with(
        symbol="BTC", pnl_usd=12.5, holding_hours=3.2, signal_id=None
    )
    fake_rwm.resolve_outcome.assert_called_once_with(
        symbol="BTC", outcome_pnl=12.5, cycle_id="cycle-001"
    )
    fake_som.record.assert_called_once_with(
        symbol="BTC",
        regime="BULL",
        action="LONG",
        confidence=0.82,
        pnl_usd=12.5,
        trade_id="trade-xyz",
    )


@pytest.mark.asyncio
async def test_resolver_recovers_action_from_signal_when_omitted():
    """If action is None, resolver looks up the most recent actionable signal."""
    # Simulated SignalRecord row
    row = MagicMock()
    row.action = "SHORT"
    row.confidence = 0.71
    row.raw = {"metadata": {"market_regime": "BEAR"}}

    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=row)
    fake_session.execute = AsyncMock(return_value=exec_result)

    fake_ams = MagicMock()
    fake_ams.resolve_outcome = AsyncMock(return_value=False)

    fake_rwm = MagicMock()
    fake_rwm.resolve_outcome = MagicMock(return_value=False)

    fake_som = MagicMock()
    fake_som.record = MagicMock()

    with patch(
        "src.services.trade_outcome_resolver.get_session", return_value=fake_session
    ), patch(
        "src.persistence.agent_memory.AgentMemoryStore", fake_ams
    ), patch(
        "src.services.role_working_memory.get_role_working_memory",
        return_value=fake_rwm,
    ), patch(
        "src.services.signal_outcome_memory.get_signal_outcome_memory",
        return_value=fake_som,
    ):
        result = await resolve_trade_memories(symbol="BTC", pnl_usd=-4.7)

    # Resolver should have queried signals table and used the recovered values
    fake_som.record.assert_called_once_with(
        symbol="BTC",
        regime="BEAR",
        action="SHORT",
        confidence=0.71,
        pnl_usd=-4.7,
        trade_id="",
    )
    assert result["signal_outcome"] is True


@pytest.mark.asyncio
async def test_resolver_skips_signal_outcome_when_action_unknown():
    """Without a known LONG/SHORT action, SignalOutcomeMemory.record is skipped."""
    fake_ams = MagicMock()
    fake_ams.resolve_outcome = AsyncMock(return_value=False)
    fake_rwm = MagicMock()
    fake_rwm.resolve_outcome = MagicMock(return_value=False)
    fake_som = MagicMock()
    fake_som.record = MagicMock()

    # Simulate signal lookup returning nothing
    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=None)
    fake_session.execute = AsyncMock(return_value=exec_result)

    with patch(
        "src.services.trade_outcome_resolver.get_session", return_value=fake_session
    ), patch(
        "src.persistence.agent_memory.AgentMemoryStore", fake_ams
    ), patch(
        "src.services.role_working_memory.get_role_working_memory",
        return_value=fake_rwm,
    ), patch(
        "src.services.signal_outcome_memory.get_signal_outcome_memory",
        return_value=fake_som,
    ):
        result = await resolve_trade_memories(symbol="BTC", pnl_usd=2.0)

    fake_som.record.assert_not_called()
    assert result["signal_outcome"] is False


@pytest.mark.asyncio
async def test_resolver_never_raises_when_individual_stores_fail():
    """Each store failure is independent — close path is never broken."""
    fake_ams = MagicMock()
    fake_ams.resolve_outcome = AsyncMock(side_effect=RuntimeError("db down"))

    fake_rwm = MagicMock()
    fake_rwm.resolve_outcome = MagicMock(side_effect=ValueError("oops"))

    fake_som = MagicMock()
    fake_som.record = MagicMock(side_effect=Exception("nope"))

    with patch(
        "src.persistence.agent_memory.AgentMemoryStore", fake_ams
    ), patch(
        "src.services.role_working_memory.get_role_working_memory",
        return_value=fake_rwm,
    ), patch(
        "src.services.signal_outcome_memory.get_signal_outcome_memory",
        return_value=fake_som,
    ):
        result = await resolve_trade_memories(
            symbol="BTC",
            pnl_usd=1.0,
            action="LONG",
            regime="BULL",
            confidence=0.5,
        )

    # All False but no exception leaked
    # INV-15 (2026-05-29) — decision_memory adicionado também é False aqui
    # (cycle_id ausente no fixture).
    assert result == {
        "agent_memory": False,
        "role_working": False,
        "signal_outcome": False,
        "decision_memory": False,
    }

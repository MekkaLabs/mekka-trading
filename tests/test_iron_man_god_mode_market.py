"""Tests — Modo Deus (force_execute) usa market em testnet (Bug fix 2026-05-26).

Background: operador clicou Modo Deus em Binance testnet, IronMan colocou
limit_ioc (porque settings.mainnet_dry_run=True força comportamento mainnet),
mas testnet tem book ralo e a IOC fill 0 units. Operador viu REJECTED e
achou que Modo Deus estava quebrado.

Fix: quando approval.metadata.force_execute=True E _is_testnet=True,
IronMan força market order (ignora binance_entry_order_type). Em mainnet
o comportamento não muda — slippage cap continua valendo (force_execute
em mainnet é bloqueado pelo server.py antes de chegar aqui).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal


def _build_signal(symbol: str = "BTC") -> TradingSignal:
    return TradingSignal(
        symbol=symbol,
        action=TradeAction.LONG,
        confidence=0.7,
        entry_price=77245.0,
        stop_loss=76000.0,
        take_profit=79000.0,
        size_pct=0.05,
        leverage=10,
        reasoning="test",
        agent_contributions={},
    )


def _build_approval(force_execute: bool = False) -> RiskApproval:
    return RiskApproval(
        symbol="BTC",
        verdict=RiskVerdict.APPROVED,
        reasons=["test"],
        adjusted_size_pct=0.05,
        adjusted_leverage=10,
        breached_limits=[],
        metadata={"force_execute": True} if force_execute else {},
    )


@pytest.mark.asyncio
async def test_iron_man_passes_force_market_when_force_execute_in_metadata():
    """approval.metadata.force_execute=True → _place_ccxt_order called with
    force_market_in_testnet=True."""
    from src.agents.iron_man import IronMan

    iron = IronMan()
    captured_kwargs = {}

    async def _fake_place_ccxt(**kw):
        captured_kwargs.update(kw)
        from src.models.execution import ExecutionResult, ExecutionStatus
        return ExecutionResult(
            symbol="BTC", status=ExecutionStatus.PAPER, is_paper=True,
            side="long", quantity=0.01, avg_price=77245.0, notional_usd=772.45,
        )

    with patch.object(iron, "_place_ccxt_order", side_effect=_fake_place_ccxt):
        with patch("src.agents.iron_man.settings") as mock_s:
            mock_s.active_exchange = "binance"
            mock_s.paper_trading = False
            mock_s.binance_testnet = True
            mock_s.execution_skew_max_ms = 5000
            await iron._run(
                signal=_build_signal(),
                approval=_build_approval(force_execute=True),
                equity_usd=5000.0,
            )

    assert captured_kwargs.get("force_market_in_testnet") is True


@pytest.mark.asyncio
async def test_iron_man_no_force_market_when_metadata_empty():
    """approval.metadata sem force_execute → force_market_in_testnet=False."""
    from src.agents.iron_man import IronMan

    iron = IronMan()
    captured_kwargs = {}

    async def _fake_place_ccxt(**kw):
        captured_kwargs.update(kw)
        from src.models.execution import ExecutionResult, ExecutionStatus
        return ExecutionResult(
            symbol="BTC", status=ExecutionStatus.PAPER, is_paper=True,
            side="long", quantity=0.01, avg_price=77245.0, notional_usd=772.45,
        )

    with patch.object(iron, "_place_ccxt_order", side_effect=_fake_place_ccxt):
        with patch("src.agents.iron_man.settings") as mock_s:
            mock_s.active_exchange = "binance"
            mock_s.paper_trading = False
            mock_s.binance_testnet = True
            mock_s.execution_skew_max_ms = 5000
            await iron._run(
                signal=_build_signal(),
                approval=_build_approval(force_execute=False),
                equity_usd=5000.0,
            )

    assert captured_kwargs.get("force_market_in_testnet") is False


def test_place_ccxt_order_signature_includes_force_market_param():
    """Smoke check: signature has force_market_in_testnet with default False
    so callers that don't pass it stay backward-compatible."""
    import inspect
    from src.agents.iron_man import IronMan

    sig = inspect.signature(IronMan._place_ccxt_order)
    params = sig.parameters
    assert "force_market_in_testnet" in params
    p = params["force_market_in_testnet"]
    assert p.default is False, "Default MUST be False to keep loop-driven path unchanged"

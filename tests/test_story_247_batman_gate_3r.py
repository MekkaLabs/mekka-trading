"""
tests/test_story_247_batman_gate_3r.py
=========================================
Story 247 — Batman Gate 3r: Flash Momentum Divergence

Tests that gate 3r correctly reduces size on Flash divergence and
leaves size unchanged when Flash confirms direction.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.signal import MomentumDirection


def _make_momentum(direction: MomentumDirection, is_strong: bool):
    return SimpleNamespace(direction=direction, is_strong=is_strong)


def _make_analysis(momentum):
    return SimpleNamespace(momentum=momentum)


class TestBatmanGate3r:
    """
    Unit tests for gate 3r — Flash divergence size reduction.

    We test the gate logic directly via the Batman._run() co-routine,
    mocking all heavy dependencies (exchange, SQLite, kill switch).
    """

    def _make_signal(self, action: str = "LONG", size_pct: float = 0.02):
        # NOTE: importava `SignalAction` que não existe — `TradeAction` é o nome correto.
        # O construtor aceita a string diretamente (Pydantic faz a coerção), então
        # nem é preciso importar o enum aqui.
        from src.models.signal import TradingSignal
        return TradingSignal(
            symbol="BTC",
            action=action,
            confidence=0.70,
            entry_price=65_000.0,
            stop_loss=63_000.0 if action == "LONG" else 67_000.0,
            take_profit=68_000.0 if action == "LONG" else 62_000.0,
            size_pct=size_pct,
            leverage=2,
            reasoning="Test signal",
            agent_contributions={"Superman": "trend"},
        )

    @pytest.mark.asyncio
    async def test_strong_flash_up_reduces_short_size(self):
        """Flash STRONG UP + SHORT signal → size reduced 30%."""
        from src.agents.batman import Batman

        signal = self._make_signal(action="SHORT", size_pct=0.02)
        momentum = _make_momentum(MomentumDirection.UP, is_strong=True)
        analysis = _make_analysis(momentum)

        batman = Batman()

        with (
            patch("src.agents.batman.is_kill_switch_active", return_value=False),
            patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
            patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
            patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
            # Neutraliza caches globais que poluem entre testes em batch:
            #   funding (gate 3i), MTF (gate 3h), ATR (gate 3q + section 5).
            patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
            patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
            patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
        ):
            approval = await batman.run(
                signal=signal,
                equity_usd=10_000.0,
                analysis=analysis,
            )

        # Should be approved (soft gate, not a veto)
        assert approval.is_executable
        # Size should be reduced by 30%
        assert approval.adjusted_size_pct is not None
        assert abs(approval.adjusted_size_pct - 0.02 * 0.70) < 0.001
        # Gate 3r reason should be recorded
        assert any("3r" in r for r in approval.reasons)

    @pytest.mark.asyncio
    async def test_strong_flash_down_reduces_long_size(self):
        """Flash STRONG DOWN + LONG signal → size reduced 30%."""
        from src.agents.batman import Batman

        signal = self._make_signal(action="LONG", size_pct=0.03)
        momentum = _make_momentum(MomentumDirection.DOWN, is_strong=True)
        analysis = _make_analysis(momentum)

        batman = Batman()

        with (
            patch("src.agents.batman.is_kill_switch_active", return_value=False),
            patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
            patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
            patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
            # Neutraliza caches globais que poluem entre testes em batch:
            #   funding (gate 3i), MTF (gate 3h), ATR (gate 3q + section 5).
            patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
            patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
            patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
        ):
            approval = await batman.run(
                signal=signal,
                equity_usd=10_000.0,
                analysis=analysis,
            )

        assert approval.is_executable
        assert approval.adjusted_size_pct is not None
        assert abs(approval.adjusted_size_pct - 0.03 * 0.70) < 0.001

    @pytest.mark.asyncio
    async def test_strong_flash_up_confirms_long(self):
        """Flash STRONG UP + LONG signal → no size reduction (confirmed)."""
        from src.agents.batman import Batman

        signal = self._make_signal(action="LONG", size_pct=0.02)
        momentum = _make_momentum(MomentumDirection.UP, is_strong=True)
        analysis = _make_analysis(momentum)

        batman = Batman()

        with (
            patch("src.agents.batman.is_kill_switch_active", return_value=False),
            patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
            patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
            patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
            # Neutraliza caches globais que poluem entre testes em batch:
            #   funding (gate 3i), MTF (gate 3h), ATR (gate 3q + section 5).
            patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
            patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
            patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
        ):
            approval = await batman.run(
                signal=signal,
                equity_usd=10_000.0,
                analysis=analysis,
            )

        # Should NOT have flash_divergence_reduction in breached list
        assert "flash_divergence_reduction" not in approval.breached_limits

    @pytest.mark.asyncio
    async def test_no_analysis_no_reduction(self):
        """Without analysis arg, gate 3r should not fire."""
        from src.agents.batman import Batman

        signal = self._make_signal(action="LONG", size_pct=0.02)

        batman = Batman()

        with (
            patch("src.agents.batman.is_kill_switch_active", return_value=False),
            patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
            patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
            patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
            # Neutraliza caches globais que poluem entre testes em batch:
            #   funding (gate 3i), MTF (gate 3h), ATR (gate 3q + section 5).
            patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
            patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
            patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
        ):
            approval = await batman.run(
                signal=signal,
                equity_usd=10_000.0,
                analysis=None,
            )

        assert "flash_divergence_reduction" not in approval.breached_limits

    @pytest.mark.asyncio
    async def test_weak_flash_does_not_trigger_reduction(self):
        """Flash weak (not STRONG) signal → no size reduction regardless of direction."""
        from src.agents.batman import Batman

        signal = self._make_signal(action="LONG", size_pct=0.02)
        momentum = _make_momentum(MomentumDirection.DOWN, is_strong=False)
        analysis = _make_analysis(momentum)

        batman = Batman()

        with (
            patch("src.agents.batman.is_kill_switch_active", return_value=False),
            patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
            patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
            patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
            # Neutraliza caches globais que poluem entre testes em batch:
            #   funding (gate 3i), MTF (gate 3h), ATR (gate 3q + section 5).
            patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
            patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
            patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
        ):
            approval = await batman.run(
                signal=signal,
                equity_usd=10_000.0,
                analysis=analysis,
            )

        assert "flash_divergence_reduction" not in approval.breached_limits

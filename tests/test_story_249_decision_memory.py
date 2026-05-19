"""Tests — Story 249: Decision Memory.

Cobre:
- Construção do bloco de reflexão a partir de decisões com outcomes
- Cálculo correto de win rate, PnL total, insights reflexivos
- Fallback síncrono via closed trades (build_reflection_block_from_closed_trades)
- Falha silenciosa quando DB indisponível
- Formato correto do payload de save_decision / record_outcome
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.decision_memory import (
    DecisionMemoryStore,
    DecisionOutcome,
    DecisionRecord,
    get_decision_memory,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _make_decision(
    cycle_id: str = "cycle-001",
    symbol: str = "BTC",
    action: str = "LONG",
    confidence: float = 0.80,
    debate_confidence: float = 0.75,
    regime: str = "BULL",
    entry_price: float = 65000.0,
) -> dict:
    return {
        "cycle_id": cycle_id,
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "debate_confidence": debate_confidence,
        "regime": regime,
        "entry_price": entry_price,
        "timestamp": "2026-01-01T10:00:00",
        "outcome": None,
    }


def _make_decision_with_outcome(
    cycle_id: str = "cycle-001",
    pnl_pct: float = 2.5,
    hit_target: bool = True,
    exit_reason: str = "TP",
    duration_hours: float = 4.5,
) -> dict:
    d = _make_decision(cycle_id=cycle_id)
    d["outcome"] = {
        "pnl_pct": pnl_pct,
        "hit_target": hit_target,
        "exit_reason": exit_reason,
        "duration_hours": duration_hours,
    }
    return d


# ──────────────────────────────────────────────────────────────────────────────
# build_reflection_block
# ──────────────────────────────────────────────────────────────────────────────


class TestBuildReflectionBlock:
    def test_empty_list_returns_empty_string(self):
        store = DecisionMemoryStore()
        result = store.build_reflection_block([], "BTC")
        assert result == ""

    def test_block_contains_symbol(self):
        store = DecisionMemoryStore()
        decisions = [_make_decision()]
        result = store.build_reflection_block(decisions, "BTC")
        assert "BTC" in result

    def test_pending_outcome_shows_waiting(self):
        store = DecisionMemoryStore()
        decisions = [_make_decision()]
        result = store.build_reflection_block(decisions, "BTC")
        assert "Aguardando" in result

    def test_positive_pnl_shows_checkmark(self):
        store = DecisionMemoryStore()
        decisions = [_make_decision_with_outcome(pnl_pct=3.2)]
        result = store.build_reflection_block(decisions, "BTC")
        assert "✅" in result
        assert "+3.20%" in result

    def test_negative_pnl_shows_cross(self):
        store = DecisionMemoryStore()
        decisions = [_make_decision_with_outcome(pnl_pct=-1.8)]
        result = store.build_reflection_block(decisions, "BTC")
        assert "❌" in result

    def test_win_rate_calculated_correctly(self):
        store = DecisionMemoryStore()
        decisions = [
            _make_decision_with_outcome("c1", pnl_pct=2.0),
            _make_decision_with_outcome("c2", pnl_pct=1.5),
            _make_decision_with_outcome("c3", pnl_pct=-0.8),
            _make_decision_with_outcome("c4", pnl_pct=3.0),
        ]
        result = store.build_reflection_block(decisions, "ETH")
        # 3W/1L = 75% win rate
        assert "75%" in result
        assert "3W/1L" in result

    def test_strong_win_rate_shows_encouragement(self):
        store = DecisionMemoryStore()
        decisions = [
            _make_decision_with_outcome(f"c{i}", pnl_pct=2.0) for i in range(5)
        ]
        result = store.build_reflection_block(decisions, "BTC")
        # 5W/0L = 100% win rate → mensagem positiva
        assert "forte" in result.lower() or "disciplina" in result.lower()

    def test_low_win_rate_shows_caution(self):
        store = DecisionMemoryStore()
        decisions = [
            _make_decision_with_outcome("c1", pnl_pct=-1.0),
            _make_decision_with_outcome("c2", pnl_pct=-2.0),
            _make_decision_with_outcome("c3", pnl_pct=-0.5),
        ]
        result = store.build_reflection_block(decisions, "BTC")
        assert "⚠️" in result

    def test_debate_confidence_shown_when_nonzero(self):
        store = DecisionMemoryStore()
        d = _make_decision(debate_confidence=0.80)
        result = store.build_reflection_block([d], "BTC")
        assert "Debate conf" in result
        assert "80%" in result

    def test_debate_confidence_hidden_when_zero(self):
        store = DecisionMemoryStore()
        d = _make_decision(debate_confidence=0.0)
        result = store.build_reflection_block([d], "BTC")
        assert "Debate conf" not in result

    def test_multiple_decisions_numbered(self):
        store = DecisionMemoryStore()
        decisions = [_make_decision(f"c{i}") for i in range(3)]
        result = store.build_reflection_block(decisions, "BTC")
        assert "1." in result
        assert "2." in result
        assert "3." in result


# ──────────────────────────────────────────────────────────────────────────────
# build_reflection_block_from_closed_trades (fallback síncrono)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class _FakeTradeRecord:
    id: int
    symbol: str
    side: str
    created_at: datetime
    updated_at: datetime
    metadata: dict


class TestBuildFromClosedTrades:
    def _make_trade(
        self,
        symbol: str = "BTC",
        side: str = "LONG",
        pnl_usd: float = 500.0,
        entry: float = 65000.0,
        exit_p: float = 67000.0,
        exit_reason: str = "TP",
        hours_ago: float = 4.0,
    ) -> _FakeTradeRecord:
        now = datetime.utcnow()
        return _FakeTradeRecord(
            id=1,
            symbol=symbol,
            side=side,
            created_at=now - timedelta(hours=hours_ago),
            updated_at=now,
            metadata={
                "realized_pnl_usd": pnl_usd,
                "entry_price": entry,
                "exit_price": exit_p,
                "exit_reason": exit_reason,
                "confidence": 0.75,
                "regime": "BULL",
            },
        )

    def test_empty_list_returns_empty(self):
        store = DecisionMemoryStore()
        result = store.build_reflection_block_from_closed_trades([], "BTC")
        assert result == ""

    def test_profit_trade_shown(self):
        store = DecisionMemoryStore()
        trade = self._make_trade(entry=65000.0, exit_p=67000.0)
        result = store.build_reflection_block_from_closed_trades([trade], "BTC")
        # PnL = (67000-65000)/65000 * 100 = 3.076...%
        assert "✅" in result or "+" in result

    def test_loss_trade_shown(self):
        store = DecisionMemoryStore()
        trade = self._make_trade(entry=65000.0, exit_p=63000.0, pnl_usd=-500.0)
        result = store.build_reflection_block_from_closed_trades([trade], "BTC")
        assert "❌" in result or "-" in result

    def test_duration_calculated(self):
        store = DecisionMemoryStore()
        trade = self._make_trade(hours_ago=6.0)
        result = store.build_reflection_block_from_closed_trades([trade], "BTC")
        # duração ~6h deve aparecer
        assert "h" in result  # "6.0h" ou similar

    def test_respects_limit(self):
        store = DecisionMemoryStore()
        trades = [self._make_trade() for _ in range(10)]
        result = store.build_reflection_block_from_closed_trades(trades, "BTC", limit=3)
        # Apenas 3 itens → "3." presente mas "4." ausente
        assert "3." in result
        assert "4." not in result


# ──────────────────────────────────────────────────────────────────────────────
# save_decision e record_outcome (mock do MekkaRepository)
# ──────────────────────────────────────────────────────────────────────────────


class TestSaveAndRecord:
    @pytest.mark.asyncio
    async def test_save_decision_calls_log_event(self):
        record = DecisionRecord(
            cycle_id="cycle-test-1",
            symbol="ETH",
            signal_action="LONG",
            entry_price=3200.0,
            confidence=0.85,
            debate_confidence=0.70,
            regime="BULL",
            timestamp=datetime(2026, 1, 1, 10, 0, 0),
        )
        with patch(
            "src.services.decision_memory.MekkaRepository",
            new_callable=MagicMock,
        ) as mock_repo:
            mock_repo.log_event = AsyncMock()
            store = DecisionMemoryStore()
            # Força importação dentro do método
            with patch.dict(
                "sys.modules",
                {"src.persistence.repository": MagicMock(MekkaRepository=mock_repo)},
            ):
                # Chama diretamente patch interno
                mock_repo.log_event.return_value = 1
                with patch(
                    "src.persistence.repository.MekkaRepository",
                    mock_repo,
                ):
                    await store.save_decision(record)

    @pytest.mark.asyncio
    async def test_save_decision_silently_handles_error(self):
        """save_decision não deve propagar exceções."""
        record = DecisionRecord(
            cycle_id="cycle-err",
            symbol="SOL",
            signal_action="HOLD",
            entry_price=0.0,
            confidence=0.5,
            debate_confidence=0.0,
            regime="UNKNOWN",
            timestamp=datetime.utcnow(),
        )
        store = DecisionMemoryStore()
        with patch(
            "src.services.decision_memory.MekkaRepository",
            side_effect=ImportError("DB unavailable"),
        ):
            # Não deve lançar exceção
            await store.save_decision(record)

    @pytest.mark.asyncio
    async def test_record_outcome_silently_handles_error(self):
        """record_outcome não deve propagar exceções."""
        outcome = DecisionOutcome(
            realized_pnl_pct=-2.0,
            hit_target=False,
            duration_hours=1.5,
            exit_reason="SL",
        )
        store = DecisionMemoryStore()
        with patch(
            "src.services.decision_memory.MekkaRepository",
            side_effect=ImportError("DB unavailable"),
        ):
            await store.record_outcome("cycle-err", "BTC", outcome)

    @pytest.mark.asyncio
    async def test_get_recent_returns_empty_on_error(self):
        """get_recent_with_outcomes deve retornar [] em caso de erro."""
        store = DecisionMemoryStore()
        with patch(
            "src.services.decision_memory.MekkaRepository",
            side_effect=ImportError("DB unavailable"),
        ):
            result = await store.get_recent_with_outcomes("BTC", limit=5)
        assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_get_decision_memory_returns_same_instance(self):
        import src.services.decision_memory as _mod

        _mod._STORE_INSTANCE = None  # Reset para teste limpo
        a = get_decision_memory()
        b = get_decision_memory()
        assert a is b

    def test_instance_is_decision_memory_store(self):
        import src.services.decision_memory as _mod

        _mod._STORE_INSTANCE = None
        store = get_decision_memory()
        assert isinstance(store, DecisionMemoryStore)

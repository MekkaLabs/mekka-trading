"""tests/test_story_220_backtest_outcome_simulator.py"""
from __future__ import annotations
from datetime import datetime, timezone
import pytest
from src.models.backtest import BacktestOutcome, BacktestTrade


def _trade(action="LONG", rr=2.0, conf=0.75, is_real=False, pnl=0.0, outcome=BacktestOutcome.UNKNOWN):
    return BacktestTrade(
        timestamp=datetime.now(timezone.utc), symbol="BTC", action=action,
        entry_price=50000.0, stop_loss=48000.0, take_profit=54000.0,
        size_pct=0.02, leverage=5, confidence=conf, risk_reward=rr,
        real_pnl_usd=pnl if is_real else None, pnl_usd=pnl,
        is_real=is_real, outcome=outcome,
    )


class TestStory220BacktestOutcomeSimulator:

    def test_import(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        assert BacktestOutcomeSimulator is not None

    def test_hold_becomes_expired(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator(seed=42)
        result = sim.simulate([_trade(action="HOLD")])
        assert result[0].outcome == BacktestOutcome.EXPIRED
        assert result[0].pnl_usd == 0.0

    def test_real_trade_preserved(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator(seed=42)
        t = _trade(is_real=True, pnl=200.0, outcome=BacktestOutcome.WIN)
        result = sim.simulate([t])
        assert result[0].is_real
        assert result[0].pnl_usd == pytest.approx(200.0)
        assert result[0].outcome == BacktestOutcome.WIN

    def test_unknown_gets_simulated_outcome(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator(seed=0)
        result = sim.simulate([_trade("LONG")])
        assert result[0].outcome in (BacktestOutcome.WIN, BacktestOutcome.LOSS)

    def test_pnl_positive_on_win(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        # seed que garante WIN para este trade com p_win alto
        sim = BacktestOutcomeSimulator(seed=42)
        # confidence=0.99, rr=3.0 → p_win alto
        t = _trade("LONG", conf=0.99, rr=3.0)
        results = [sim.simulate([t])[0] for _ in range(20)]
        wins = [r for r in results if r.outcome == BacktestOutcome.WIN]
        if wins:
            assert wins[0].pnl_usd > 0

    def test_pnl_negative_on_loss(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator(seed=99)
        results = []
        for seed in range(100):
            s = BacktestOutcomeSimulator(seed=seed)
            r = s.simulate([_trade("LONG")])[0]
            results.append(r)
        losses = [r for r in results if r.outcome == BacktestOutcome.LOSS]
        assert all(l.pnl_usd < 0 for l in losses)

    def test_reproducible_with_seed(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        trades = [_trade("LONG"), _trade("SHORT"), _trade("LONG")]
        r1 = BacktestOutcomeSimulator(seed=123).simulate(trades)
        r2 = BacktestOutcomeSimulator(seed=123).simulate(trades)
        assert [t.outcome for t in r1] == [t.outcome for t in r2]
        assert [t.pnl_usd for t in r1] == [t.pnl_usd for t in r2]

    def test_different_seeds_differ(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        trades = [_trade("LONG")] * 20
        r1 = BacktestOutcomeSimulator(seed=1).simulate(trades)
        r2 = BacktestOutcomeSimulator(seed=99).simulate(trades)
        outcomes1 = [t.outcome for t in r1]
        outcomes2 = [t.outcome for t in r2]
        assert outcomes1 != outcomes2  # extremamente improvável serem iguais

    def test_empty_list(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        assert BacktestOutcomeSimulator(seed=0).simulate([]) == []

    def test_p_win_range(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator
        # Alta conf + alto R:R → p_win ≤ 0.90
        p_high = sim._compute_p_win(_trade(conf=1.0, rr=5.0))
        assert p_high <= 0.90
        # Baixa conf + baixo R:R → p_win ≥ 0.10
        p_low = sim._compute_p_win(_trade(conf=0.0, rr=0.5))
        assert p_low >= 0.10

    # --- Regressão (2026-06-01): geometria de risco inválida não vira wipeout ---

    def test_invalid_stop_loss_not_simulated(self):
        """sl<=0 não pode virar perda de -100% da alocação (bug -$200 fantasma).

        Antes do guard, sl=0 fazia dist = |entry - 0| = entry → move_pct = 1.0
        → perda de toda a alocação. Agora vira UNKNOWN (não conta no PnL).
        """
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator(seed=42)
        t = _trade("LONG").model_copy(update={"stop_loss": 0.0})
        result = sim.simulate([t])[0]
        assert result.outcome == BacktestOutcome.UNKNOWN
        assert result.pnl_usd == 0.0

    def test_invalid_take_profit_not_simulated(self):
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator(seed=42)
        t = _trade("LONG").model_copy(update={"take_profit": 0.0})
        result = sim.simulate([t])[0]
        assert result.outcome == BacktestOutcome.UNKNOWN
        assert result.pnl_usd == 0.0

    def test_valid_geometry_still_simulated(self):
        """Geometria válida (sl/tp > 0) continua sendo simulada normalmente."""
        from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
        sim = BacktestOutcomeSimulator(seed=42)
        result = sim.simulate([_trade("LONG")])[0]
        assert result.outcome in (BacktestOutcome.WIN, BacktestOutcome.LOSS)

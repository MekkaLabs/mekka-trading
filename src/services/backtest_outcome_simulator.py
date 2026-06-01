"""
src/services/backtest_outcome_simulator.py
============================================
BacktestOutcomeSimulator — Story 220 (Milestone 35: Backtesting Engine).

Para cada BacktestTrade com outcome=UNKNOWN (sem trade real correspondente),
simula o resultado usando a geometria SL/TP e um modelo probabilístico
calibrado por R:R e confiança da Vision.

Resultados reais (is_real=True) são preservados intactos.

Modelo de simulação
-------------------
    p_win = clip(base_rate × rr_factor × confidence_factor, 0.10, 0.90)

    base_rate         = 0.45  (taxa base histórica de sistemas quant)
    rr_factor         = min(rr / 2.0, 1.5)      (R:R 2 = neutro, >2 = favor)
    confidence_factor = 0.70 + conf × 0.60      (Vision 75% conf → ×1.15)

PnL computado
-------------
    equity_allocated = equity_usd × size_pct
    WIN  → +equity_allocated × (tp_dist / entry) × leverage
    LOSS → -equity_allocated × (sl_dist / entry) × leverage
"""

from __future__ import annotations

import random
from typing import List, Optional

from loguru import logger

from src.models.backtest import BacktestOutcome, BacktestTrade

# Taxa base de win rate para um sistema de trading aleatório calibrado
_BASE_WIN_RATE = 0.45


class BacktestOutcomeSimulator:
    """
    Simula resultados de BacktestTrades sem outcome real.

    Args:
        seed: Semente para reprodutibilidade (None = aleatório).
        equity_usd: Equity inicial assumida para cálculo de PnL.
                    Pode ser sobrescrita por trade em `simulate()`.

    Example::

        sim = BacktestOutcomeSimulator(seed=42)
        trades = sim.simulate(trades=loaded_trades, equity_usd=10_000.0)
        # Cada trade agora tem outcome=WIN/LOSS/EXPIRED + pnl_usd preenchido
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        equity_usd: float = 10_000.0,
    ) -> None:
        self._rng = random.Random(seed)
        self._default_equity = equity_usd
        self._log = logger.bind(service="BacktestOutcomeSimulator")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def simulate(
        self,
        trades: List[BacktestTrade],
        equity_usd: Optional[float] = None,
    ) -> List[BacktestTrade]:
        """
        Processa a lista de BacktestTrades e preenche outcome + pnl_usd.

        - Trades com ``is_real=True`` são copiados sem modificação.
        - Trades com ``outcome=UNKNOWN`` recebem WIN/LOSS simulado.
        - Trades HOLD recebem ``outcome=EXPIRED, pnl_usd=0.0``.

        Returns:
            Nova lista de BacktestTrade com outcomes preenchidos.
        """
        eq = equity_usd if equity_usd is not None else self._default_equity
        result: List[BacktestTrade] = []

        for trade in trades:
            try:
                result.append(self._process_one(trade, eq))
            except Exception as exc:  # noqa: BLE001
                self._log.debug(f"BacktestOutcomeSimulator: erro em {trade.symbol} (suprimido): {exc}")
                result.append(trade)  # preserva original se falhar

        wins = sum(1 for t in result if t.outcome == BacktestOutcome.WIN)
        losses = sum(1 for t in result if t.outcome == BacktestOutcome.LOSS)
        self._log.info(
            f"BacktestOutcomeSimulator: {len(result)} trades → "
            f"{wins} WIN, {losses} LOSS, "
            f"{sum(1 for t in result if t.is_real)} reais"
        )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_one(self, trade: BacktestTrade, equity_usd: float) -> BacktestTrade:
        # Preservar resultados reais sem modificação
        if trade.is_real:
            # PnL já está preenchido pelo loader — calcular apenas pct
            if trade.pnl_usd != 0.0:
                allocated = equity_usd * trade.size_pct
                pnl_pct = (trade.pnl_usd / allocated * 100) if allocated > 0 else 0.0
                return trade.model_copy(update={"pnl_pct": round(pnl_pct, 4)})
            return trade

        # HOLD → EXPIRED, sem PnL
        if trade.action == "HOLD":
            return trade.model_copy(update={
                "outcome": BacktestOutcome.EXPIRED,
                "pnl_usd": 0.0,
                "pnl_pct": 0.0,
            })

        # Sinal LONG/SHORT sem resultado real → simular.
        # Guard de robustez (2026-06-01): geometria de risco inválida
        # (entry/sl/tp <= 0) não pode ser simulada. Sem isso, sl=0 fazia
        # dist = |entry - 0| = entry → move_pct = 1.0 → perda de 100% da
        # alocação (wipeout fantasma). Trades inválidos viram UNKNOWN e
        # não contaminam as métricas (não contam como WIN/LOSS).
        if trade.entry_price <= 0 or trade.stop_loss <= 0 or trade.take_profit <= 0:
            return trade.model_copy(update={"outcome": BacktestOutcome.UNKNOWN})

        p_win = self._compute_p_win(trade)
        is_win = self._rng.random() < p_win

        outcome = BacktestOutcome.WIN if is_win else BacktestOutcome.LOSS
        pnl_usd = self._compute_pnl(trade, equity_usd, is_win)
        allocated = equity_usd * trade.size_pct
        pnl_pct = (pnl_usd / allocated * 100) if allocated > 0 else 0.0

        return trade.model_copy(update={
            "outcome": outcome,
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 4),
        })

    @staticmethod
    def _compute_p_win(trade: BacktestTrade) -> float:
        """Probabilidade de WIN baseada em R:R e confiança da Vision."""
        rr = trade.risk_reward if trade.risk_reward > 0 else 1.0
        rr_factor = min(rr / 2.0, 1.5)

        conf = max(0.0, min(1.0, trade.confidence))
        confidence_factor = 0.70 + conf * 0.60

        p = _BASE_WIN_RATE * rr_factor * confidence_factor
        return max(0.10, min(0.90, p))

    @staticmethod
    def _compute_pnl(trade: BacktestTrade, equity_usd: float, is_win: bool) -> float:
        """Calcula PnL em USD para o trade simulado."""
        allocated = equity_usd * trade.size_pct
        if allocated <= 0 or trade.entry_price <= 0:
            return 0.0

        if is_win:
            dist = abs(trade.take_profit - trade.entry_price)
        else:
            dist = abs(trade.entry_price - trade.stop_loss)

        move_pct = dist / trade.entry_price
        pnl = allocated * move_pct * trade.leverage
        return pnl if is_win else -pnl

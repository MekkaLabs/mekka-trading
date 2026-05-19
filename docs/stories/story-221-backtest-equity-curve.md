# Story 221 — BacktestEquityCurve

**Milestone:** 35 — Backtesting Engine  
**Status:** Done  
**Tipo:** Analytics / Simulation  

---

## Contexto

Após a Story 220 simular os outcomes (WIN/LOSS/EXPIRED) de cada trade, precisamos
construir a curva de equity cronológica que rastreia a evolução do capital ao longo
do backtest. Esta curva é a base para calcular métricas de drawdown e visualizações.

---

## Goal

`BacktestEquityCurve`: dada uma lista ordenada de `BacktestTrade` com `pnl_usd`
preenchido, constrói a curva `List[EquityPoint]` com equity acumulada e drawdown
calculado ponto a ponto.

---

## Scope Delivered

- `src/services/backtest_equity_curve.py` — `BacktestEquityCurve`
  - `build(trades, initial_equity=10_000.0)` → `List[EquityPoint]`
  - Inclui ponto inicial `START` no índice 0 com equity = initial_equity, drawdown = 0
  - Apenas trades WIN/LOSS movem equity; EXPIRED/HOLD/UNKNOWN são ignorados
  - Equity sempre ≥ 0.0 (floor em zero para evitar negativos)
  - Rastreia `peak` para calcular `drawdown_pct = (peak - equity) / peak * 100`
  - Cada `EquityPoint` preserva `symbol`, `outcome` e `trade_pnl_usd` do trade
- `tests/test_story_221_backtest_equity_curve.py` — 11 testes

---

## Comportamento da Curva

```
Ponto 0 (START): equity = initial_equity, dd = 0, symbol = "START"
Ponto N:         equity += pnl_usd (se WIN/LOSS)
                 peak = max(peak, equity)
                 dd = (peak - equity) / peak * 100
```

Exemplo com initial_equity=10_000:
- Trade 1 WIN +500 → equity=10_500, peak=10_500, dd=0%
- Trade 2 LOSS -1000 → equity=9_500, peak=10_500, dd=9.52%
- Trade 3 EXPIRED → equity=9_500, peak=10_500, dd=9.52% (não muda)

---

## What's Next

- Story 222 — BacktestMetricsEngine

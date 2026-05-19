# Story 220 — BacktestOutcomeSimulator

**Milestone:** 35 — Backtesting Engine  
**Status:** Done  
**Tipo:** Analytics / Simulation  

---

## Contexto

A Story 219 carrega sinais com resultado real quando existe trade correspondente.
Mas a maioria dos sinais HOLD ou rejeitados pelo Batman não tem trade — ficam com
`outcome=UNKNOWN`. Para um backtest útil, precisamos simular o resultado desses
sinais: dado entry/SL/TP, o trade teria ganho ou perdido?

---

## Goal

`BacktestOutcomeSimulator`: para cada `BacktestTrade` com `outcome=UNKNOWN`,
simula o resultado usando a geometria SL/TP + um modelo probabilístico simples
calibrado pelo histórico de preços do próprio banco.

---

## Scope Delivered

- `src/services/backtest_outcome_simulator.py` — `BacktestOutcomeSimulator`
  - `simulate(trades, equity_usd)` → `list[BacktestTrade]` com outcome + pnl_usd
  - Preserva outcomes reais (`is_real=True`) sem modificação
  - Para sinais UNKNOWN: usa probabilidade baseada em R:R e confiança da Vision
  - Calcula `pnl_usd` e `pnl_pct` para cada trade
  - Modo deterministico opcional (seed fixo) para testes reproduzíveis
- `tests/test_story_220_backtest_outcome_simulator.py` — 9 testes

---

## Modelo de Simulação

Para sinais sem resultado real, a probabilidade de WIN é estimada por:

```
p_win = clip(base_rate × rr_factor × confidence_factor, 0.10, 0.90)

base_rate        = 0.45  (taxa base histórica de sistemas de trading)
rr_factor        = min(risk_reward / 2.0, 1.5)  (R:R > 2 é favorável)
confidence_factor = 0.7 + confidence × 0.6      (Vision 75% conf → +45%)
```

PnL simulado:
- WIN  → entry × size_pct × (tp_distance / entry) × leverage
- LOSS → -entry × size_pct × (sl_distance / entry) × leverage

---

## What's Next

- Story 221 — BacktestEquityCurve

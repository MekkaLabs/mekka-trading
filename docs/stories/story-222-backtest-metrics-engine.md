# Story 222 — BacktestMetricsEngine

**Milestone:** 35 — Backtesting Engine  
**Status:** Done  
**Tipo:** Analytics / Metrics  

---

## Contexto

Com os trades simulados (Story 220) e a curva de equity construída (Story 221),
precisamos computar as métricas financeiras padronizadas do backtest que permitem
avaliar a qualidade da estratégia de forma objetiva.

---

## Goal

`BacktestMetricsEngine`: recebe trades + curva de equity e calcula o conjunto
completo de métricas financeiras, retornando um `BacktestMetrics` populado.

---

## Scope Delivered

- `src/services/backtest_metrics_engine.py` — `BacktestMetricsEngine`
  - `compute(trades, equity_curve, initial_equity=10_000.0)` → `BacktestMetrics`
  - `_sharpe(returns, periods_per_year=252.0)` → float (anualizado, Rf=0)
  - `_sortino(returns, periods_per_year=252.0)` → float (downside deviation only)
- `tests/test_story_222_backtest_metrics_engine.py` — 12 testes

---

## Métricas Computadas

| Métrica | Fórmula |
|---------|---------|
| `win_rate` | wins / total × 100 |
| `profit_factor` | gross_profit / gross_loss |
| `expectancy_usd` | total_pnl / total_trades |
| `avg_win_usd` | gross_profit / wins |
| `avg_loss_usd` | gross_loss / losses |
| `max_drawdown_pct` | max(drawdown_pct) da equity_curve |
| `max_drawdown_usd` | max(peak - equity) em USD absoluto |
| `sharpe_ratio` | (mean/std) × √252 |
| `sortino_ratio` | (mean/downside_std) × √252; 999.0 se sem perdas |
| `avg_risk_reward` | média de risk_reward dos trades actionable |
| `avg_confidence` | média de confidence dos trades actionable |
| `days_covered` | (last_ts - first_ts).total_seconds / 86400 |

### Notas sobre Sharpe/Sortino

- Usa retornos em USD por trade (não % de equity)
- Sharpe com returns todos iguais → std=0 → retorna 0.0
- Sortino sem nenhuma perda → retorna 999.0 (cap de infinito)
- Trades EXPIRED/UNKNOWN são excluídos do cálculo de métricas

---

## What's Next

- Story 223 — BacktestRunner + CLI

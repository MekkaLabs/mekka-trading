# Story 219 — BacktestSignalLoader

**Milestone:** 35 — Backtesting Engine  
**Status:** Done  
**Tipo:** Analytics / Data Layer  

---

## Contexto

O sistema acumula sinais reais no SQLite (`signals` table) desde que começou a operar.
Esses dados são ouro para análise retrospectiva — mas não existe nenhum serviço que os
leia de forma estruturada para análise de qualidade de sinal.

---

## Goal

Criar `BacktestSignalLoader`: carrega sinais históricos do DB com filtros de
data/símbolo e retorna `BacktestTrade` — modelo Pydantic unificado que combina
dados do sinal com o resultado real do trade (quando existir na tabela `trades`).

---

## Scope Delivered

- `src/models/backtest.py` — `BacktestTrade`, `BacktestOutcome`, `BacktestSummary`
- `src/services/backtest_signal_loader.py` — `BacktestSignalLoader`
  - `load(symbol, start_date, end_date, actionable_only)` → `list[BacktestTrade]`
  - Join lazy com `trades` para puxar PnL real quando disponível
  - Suporta símbolo único (`"BTC"`) ou todos (`"*"`)
  - Funciona sem DB (retorna lista vazia — não lança exceção)
- `tests/test_story_219_backtest_signal_loader.py` — 8 testes

---

## Acceptance

```python
from src.services.backtest_signal_loader import BacktestSignalLoader

loader = BacktestSignalLoader()
trades = await loader.load(symbol="BTC", days=30)
# Retorna lista de BacktestTrade com campos: timestamp, symbol, action,
# entry_price, stop_loss, take_profit, size_pct, confidence,
# real_pnl_usd (None se sem trade correspondente)
```

---

## What's Next

- Story 220 — BacktestOutcomeSimulator

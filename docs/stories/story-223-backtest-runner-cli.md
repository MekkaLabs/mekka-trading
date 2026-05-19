# Story 223 — BacktestRunner + CLI

**Milestone:** 35 — Backtesting Engine  
**Status:** Done  
**Tipo:** Analytics / Orchestration / CLI  

---

## Contexto

Com todas as peças do pipeline prontas (Loader→Simulator→EquityCurve→Metrics),
precisamos de um orquestrador único e de uma interface CLI que permita ao time
rodar backtests diretamente do terminal sem precisar escrever código Python.

---

## Goal

`BacktestRunner`: orquestra o pipeline completo de backtesting em um único método
`run()` e renderiza um relatório Markdown pronto para uso.

`src.backtest` CLI: interface de linha de comando com subcomando `run`.

---

## Scope Delivered

### `src/services/backtest_runner.py` — `BacktestRunner`

- `__init__(initial_equity, seed, actionable_only)`
- `async run(symbol, days, start_date, end_date) → BacktestSummary`
  - Normaliza símbolo: `"BTCUSDT"` → `"BTC"`
  - Retorna `BacktestSummary` vazio se não há sinais (sem exception)
- `@staticmethod render_report(summary) → str`
  - Gera relatório Markdown com tabelas de: capital, trades, risco, PnL
  - Inclui mini-tabela com últimos 10 pontos da equity curve
- Pipeline interno: `SignalLoader → OutcomeSimulator → EquityCurve → MetricsEngine`

### `src/backtest/__init__.py` + `src/backtest/__main__.py`

- Subcomando `run` via `python -m src.backtest run`
- Opções: `--symbol`, `--days`, `--initial-equity`, `--seed`, `--output`, `--all-signals`, `--quiet`
- Salva relatório em arquivo `.md` se `--output` fornecido, senão imprime no stdout
- Exibe resumo final (WR, PF, Sharpe, MaxDD, Retorno) no stderr se não `--quiet`

### `tests/test_story_223_backtest_runner.py` — 8 testes

---

## Exemplos de Uso

```bash
# Backtest básico — últimos 30 dias
python -m src.backtest run --symbol BTC --days 30

# Com equity maior e semente fixa (reproduzível)
python -m src.backtest run --symbol ETH --days 90 --initial-equity 25000 --seed 42

# Salvando relatório em arquivo
python -m src.backtest run --symbol SOL --days 60 --output reports/sol_backtest.md

# Incluindo sinais HOLD (todos, não só LONG/SHORT)
python -m src.backtest run --symbol BTC --days 30 --all-signals

# Apenas relatório (sem logs)
python -m src.backtest run --symbol BTC --days 7 --quiet
```

---

## Exemplo de Saída (relatório Markdown)

```markdown
# Backtest Report — BTC

**Gerado em:** 2026-05-18 14:30 UTC
**Período:** 2026-04-18 → 2026-05-18 (30 dias)

## Capital
| | USD |
|---|---|
| Capital inicial | $10,000.00 |
| Capital final   | $12,340.00 |
| Retorno total   | +23.40% |

## Métricas de Trades
| Métrica | Valor |
|---|---|
| Total de trades | 48 |
| Win Rate        | 62.50% |
| Profit Factor   | 2.1234 |
...
```

---

## What's Next

- Milestone 36 — a definir

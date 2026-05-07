# Story 025 — Strategic Pipeline (Vision + Batman + Iron Man + Nick Fury)

## Context

Stories 001–024 entregaram a infra TypeScript (Megazord runtime, observability, ops alerting, audit, replay, DLQ) e a camada Python de **análise** (Superman, Doctor Strange, Black Panther, Thor, Aquaman, Spider-Man) — todos completos e testados.

O que faltava era o **pipeline estratégico end-to-end** em Python: o cérebro decisor (Vision), o gate de risco (Batman), o executor (Iron Man), o orquestrador paralelo (Professor X) e o comando central (Nick Fury). Sem isso o sistema produzia análise mas não decidia nem executava.

## Goal

Fechar o pipeline `Análise → Decisão → Risco → Execução → Persistência` em Python, paper-trading-first, com persistência SQLite e audit log.

## Scope Delivered

### Novos agentes (`src/agents/`)
- **`vision.py`** — Predictive Analyst. OpenAI GPT-4o, `response_format=json_object`, prompt engineering em `_SYSTEM_PROMPT`, fallback HOLD em qualquer falha (timeout, rate limit, JSON parse, schema violation). Coerção defensiva de `size_pct` (cap 10%), `leverage` (cap `settings.max_leverage`), `confidence` (clip 0–1). Geometria SL/TP delegada ao validator do `TradingSignal`.
- **`batman.py`** — Risk Guardian determinístico. Sem LLM. Enforce de seis camadas: kill switch, HOLD-bypass, daily drawdown, open positions, daily trade cap, confidence threshold, R:R mínimo, ajuste por Thor (volatility multiplier), penalidade por liquidez baixa (Aquaman), hard caps de tamanho e alavancagem. Verdict APPROVED / REDUCED / REJECTED / KILL_SWITCH. Kill switch dual: env `MEKKA_KILL_SWITCH=1` ou arquivo `data/.kill_switch`.
- **`iron_man.py`** — Hyperliquid Execution Engineer. Paper-trading-first (`settings.paper_trading=true` força simulação com order ids `PAPER-*`). Live mode usa `hyperliquid-python-sdk` + `eth-account`, com `update_leverage`, ordem entry IOC, e brackets SL/TP via `trigger.tpsl`. Tudo retentado via `tenacity` (3 tentativas, exponential backoff). Parsers defensivos para `oid`, `avgPx`, `totalSz`.
- **`professor_x.py`** — Swarm Coordinator. `asyncio.gather(..., return_exceptions=True)` para Layer-1, com Superman como dependência dura (sem chart, sem decisão). Coerce-and-skip nos demais.
- **`nick_fury.py`** — Mission Commander. `run_main_cycle()` itera todos os ativos rodando o pipeline completo, persistindo signal+trade+audit em cada passo. `run_monitor_cycle()` heartbeat (será expandido por Wolverine). `run_forever()` loop que respeita `main_loop_interval_seconds` (default 4h) e `monitor_interval_seconds` (default 5min).

### Novos models Pydantic (`src/models/`)
- **`risk.py`** — `RiskApproval` + `RiskVerdict` enum.
- **`execution.py`** — `ExecutionResult` + `ExecutionStatus` enum.

### Persistência SQLite (`src/persistence/`)
- **`models.py`** — SQLAlchemy 2.x ORM: `signals`, `trades`, `daily_pnl`, `audit_log`. Todos com timestamps UTC.
- **`db.py`** — async engine bootstrap via `aiosqlite`, table DDL automático na primeira inicialização, `get_session()` context manager.
- **`repository.py`** — `MekkaRepository` async com `save_signal`, `save_trade`, `log_event`, `upsert_daily_pnl`, `get_today_drawdown_pct`, `count_trades_today`, `list_recent_signals`.

### Entrypoint
- **`run.py`** — CLI Python com flags `--once` (single cycle) e `--equity`. Configura loguru com formato heroicamente colorido por agente.

### Dependências adicionadas
- `eth-account>=0.10.0` em `requirements.txt`.

## Hard Rules Mantidas

- `paper_trading=True` é o default — Iron Man retorna `ExecutionStatus.PAPER` sem tocar a SDK.
- Vision **sempre** retorna um `TradingSignal` válido. Falha → HOLD com `metadata.fallback=True`.
- Batman é **deterministic** — nunca envolve LLM em decisão de risco.
- Kill switch tem **prioridade absoluta** sobre qualquer outra regra.
- Spider-Man `should_pause=True` **bloqueia o pipeline antes do LLM** via `MarketAnalysis.is_safe_to_trade`.

## Pipeline End-to-End

```
NickFury.run_main_cycle(equity_usd)
    ↓ for each symbol in settings.trading_assets:
        ProfessorX.run(symbol)
            ↓ Superman.run(symbol) [REQUIRED]
            ↓ asyncio.gather(DoctorStrange, BlackPanther, Thor, Aquaman) [parallel]
            ↓ SpiderMan.run(symbol, chart, onchain)
            → MarketAnalysis bundle
        Vision.run(analysis) → TradingSignal
        MekkaRepository.save_signal(signal) → signal_id
        Batman.run(signal, volatility, liquidity, drawdown, open_positions, trades_today)
            → RiskApproval (APPROVED / REDUCED / REJECTED / KILL_SWITCH)
        if approval.is_executable:
            IronMan.run(signal, approval, equity_usd) → ExecutionResult (PAPER/FILLED/PARTIAL/ERROR)
            MekkaRepository.save_trade(execution, signal_id)
        MekkaRepository.log_event(...)
```

## Acceptance

- [x] `python run.py --once` completa sem crash em paper mode com `OPENAI_API_KEY` válida.
- [x] Vision retorna HOLD quando `MarketAnalysis.is_safe_to_trade=False` sem chamar OpenAI.
- [x] Vision retorna HOLD em qualquer exceção da OpenAI ou no parser JSON.
- [x] Batman bloqueia execução quando kill switch ativo.
- [x] Iron Man não toca a SDK quando `paper_trading=True`.
- [x] Tabelas SQLite criadas no primeiro boot em `data/mekka_trading.db`.
- [x] Audit log registra BOOT, CYCLE_SKIPPED, RISK_*, EXEC_*, MONITOR_HEARTBEAT, SHUTDOWN.

## What's Next (Story 026 candidates)

1. **Portfolio Manager** — substitui `_DEFAULT_EQUITY_USD` por leitura real do account state via Hyperliquid Info; popula `open_positions` em Batman.
2. **Wolverine (Recovery Agent)** — inflate `run_monitor_cycle` com posições reais, gestão dinâmica de SL/TP, recovery plan após drawdown.
3. **Flash (Momentum Scalper)** — sub-loop intra-candle.
4. **Telegram bot rico** — `/status /pnl /pause /resume` + push automático de cada decisão Vision e cada execução Iron Man.
5. **Deadpool (Chaos Simulator)** — backtest replay sobre `signals` + `trades` históricos.
6. **Pytest extension** — adicionar `test_phase2_pipeline.py` com mocks de OpenAI e Hyperliquid SDK.

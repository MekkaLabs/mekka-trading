# Mekka Trading — Hero Roster

## Mission

Establish an autonomous, modular, and observable trading operating system foundation with strict paper-trading safety controls. Every identity in this project is a super-hero — there are no other naming conventions.

## Roster (15 heroes across 4 layers)

### Layer 1 — Market Analysis (run in parallel)
- **Superman** — Chief Market Overseer. Multi-timeframe technical analysis (RSI, EMA-20/50, Bollinger, MACD, ATR) over Hyperliquid OHLCV via CCXT, with Binance/Bybit fallback. Classifies trend BULLISH / BEARISH / NEUTRAL with strength.
- **Doctor Strange** — Macro Probability Analyst. Aggregates CryptoPanic news + alternative.me Fear & Greed + CoinGecko BTC dominance into a -1.0 → +1.0 sentiment score.
- **Black Panther** — Onchain Intelligence. Hyperliquid `/info` for funding rate, open interest, and large-trade whale flow. Emits ACCUMULATION / DISTRIBUTION / NEUTRAL.
- **Thor** — Volatility Engine. ATR% regime classifier (LOW / MEDIUM / HIGH / EXTREME) with auto position-size multiplier (1.2x / 1.0x / 0.6x / 0.3x). Optional 7-day annualized realized vol.
- **Aquaman** — Liquidity Analyst. L2 order-book depth within 0.5% of mid, spread, $10k slippage estimate, composite liquidity score 0–1.
- **Spider-Man** — Anomaly Detector. Six checks: flash crash, volume spike, extreme funding, BB break, agent divergence, extreme RSI. Severity NONE/LOW/MEDIUM/HIGH; HIGH auto-sets `should_pause=True`.

### Layer 2 — Strategy
- **Vision** — Predictive Analyst. OpenAI GPT-4o with `response_format=json_object`. Receives consolidated `MarketAnalysis`, returns a structured `TradingSignal`. Falls back to a safe HOLD on any failure (timeout, rate limit, parse error, schema violation, anomaly halt).
- **Professor X** — Swarm Coordinator. Runs Layer-1 agents in parallel via `asyncio.gather`, isolates failures, assembles the `MarketAnalysis` bundle for Vision.

### Layer 3 — Risk & Execution
- **Batman** — Risk Guardian. Deterministic, no-LLM. Enforces kill switch, daily drawdown, open-position cap, daily trade cap, confidence threshold, R:R minimum, hard caps on size and leverage; aplica Thor multiplier e Aquaman liquidity penalty. Story 029a adicionou o **cap de capital agregado** (`max_total_capital_pct` + `max_total_notional_usd`) que rejeita novas entradas quando o notional combinado das posições abertas + a nova ordem ultrapassa o cap. Verdict APPROVED / REDUCED / REJECTED / KILL_SWITCH.
- **Iron Man** — Hyperliquid Execution Engineer. Paper-first; live mode uses `hyperliquid-python-sdk` + `eth-account`, IOC entry + reduce-only SL/TP brackets, retentado via tenacity (3 attempts, exponential backoff).

### Layer 4 — Command & Control
- **Nick Fury** — Mission Commander. Top-level orchestrator. `run_main_cycle()` (default 4h) executa Portfolio → Análise → Vision → Batman → Iron Man → SQLite por símbolo. Após cada símbolo alimenta dois `ConsecutiveBreaker` (Story 029a — exec_error e vision_fallback) que engatam o kill switch automaticamente quando ultrapassam o threshold. `run_monitor_cycle()` (default 5min) heartbeat. `run_forever()` agenda ambos.
- **Portfolio Manager** — Read-only equity & open-positions snapshot. Polla Hyperliquid `clearinghouseState` no início de cada cycle, retorna `EquitySnapshot` com fallback paper quando credenciais ausentes ou rede indisponível. Nunca envia ordens.

### Pending heroes (Story 029+)
- **Wolverine** — Recovery Agent. Position monitor expandido, gestão dinâmica de SL/TP, recovery plan pós-drawdown.
- **Flash** — Momentum Scalper. Sub-loop intra-candle para entradas táticas.
- **Deadpool** — Chaos Simulator. Backtest e stress test sobre histórico persistido.

## Squad Baseline

- `alpha-risk-command` — Batman + Nick Fury: governance de risco, kill-switch, validation gates.
- `hyperliquid-mock-ops` — Iron Man + exchange adapter mock (TS): execution rehearsal e paper-trading.
- `market-intel-lab` — Superman, Doctor Strange, Black Panther, Thor, Aquaman, Spider-Man, Vision: signal R&D.

## Hard Rules

- Never place real trades unless `paper_trading=False` and Batman approves with no breached limits — even then, Iron Man requires explicit operator awareness.
- Never bypass Batman.
- Never share state across projects.
- Always emit logs (loguru), audit_log rows (SQLite), and Pydantic-validated outputs.
- Kill switch (env `MEKKA_KILL_SWITCH=1` or file `data/.kill_switch`) is absolute.

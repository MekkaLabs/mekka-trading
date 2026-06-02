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
  - *Modalidade Vision Critic* (Story 031) — second-look opcional do mesmo herói. `vision_critic_enabled=False` por default. Quando ligado, revisa o signal e retorna ENDORSE/AMEND/REJECT. Critic só pode SUAVIZAR (size menor, leverage menor, SL mais apertado, TP mais perto). Não conta como herói novo no roster — é uma capacidade extra do Vision.
- **Professor X** — Swarm Coordinator. Runs Layer-1 agents in parallel via `asyncio.gather`, isolates failures, assembles the `MarketAnalysis` bundle for Vision.

### Layer 3 — Risk & Execution
- **Batman** — Risk Guardian. Deterministic, no-LLM. Enforces kill switch, daily drawdown, open-position cap, daily trade cap, confidence threshold, R:R minimum, hard caps on size and leverage; applies Thor multiplier and Aquaman liquidity penalty. Verdict APPROVED / REDUCED / REJECTED / KILL_SWITCH.
- **Iron Man** — Hyperliquid Execution Engineer. Paper-first; live mode uses `hyperliquid-python-sdk` + `eth-account`, IOC entry + reduce-only SL/TP brackets, retentado via tenacity (3 attempts, exponential backoff).

### Layer 4 — Command & Control
- **Nick Fury** — Mission Commander. Top-level orchestrator. `run_main_cycle()` (default 4h) executa Portfolio → Análise → Vision → Batman → Iron Man → SQLite por símbolo. `run_monitor_cycle()` (default 5min) executa Portfolio → Wolverine. `run_forever()` agenda ambos.
- **Portfolio Manager** — Read-only equity & open-positions snapshot. Polla Hyperliquid `clearinghouseState` no início de cada cycle, retorna `EquitySnapshot` com fallback paper quando credenciais ausentes ou rede indisponível. Nunca envia ordens.
- **Wolverine** — Recovery Agent. Read-only monitor sobre posições abertas: classifica por PnL (HOLD/TIGHTEN_STOP/TRAIL_STOP/SCALE_OUT/CLOSE/EMERGENCY_CLOSE), sugere novo SL, e funciona como backstop do kill switch quando intraday drawdown explode entre os ciclos principais. Emite `RecoveryPlan` para audit log; nunca toca a SDK.

### Layer 1.5 — Tactical Sub-Loop
- **Flash** (Story 033) — Momentum Scalper. Read-only e advisory. Detecta micro-momentum em janela curta usando net price move + volume multiplier. Emite `MomentumSignal` (UP/DOWN/SIDEWAYS + strength 0–1) com VOLUME-CONFIRMED tag. Em v1 nenhum agente downstream consome — está disponível para o operador e Story futura pode plugar como gate de entry timing.

### Layer 2 — Analytics (Python)
- **Deadpool** (Story 034) — Performance Analytics Agent. Determinístico, sem LLM. Lê o SQLite e computa `PerformanceReport` (win rate, PnL, Sharpe, drawdown, Wolverine endorsement rate, signal actionability, Batman approval). Emite `PerformanceVerdict` (READY / NOT_READY / INSUFFICIENT_DATA). Integrado ao preflight (gate H2 auto-check) e Telegram `/perf` + `/gates`.

## Squad Baseline

- `alpha-risk-command` — Batman + Nick Fury: governance de risco, kill-switch, validation gates.
- `hyperliquid-mock-ops` — Iron Man + exchange adapter mock (TS): execution rehearsal e paper-trading.
- `market-intel-lab` — Superman, Doctor Strange, Black Panther, Thor, Aquaman, Spider-Man, Vision: signal R&D.

## Services (não-agente)

- **DailyPnLWriter** (Story 027) — service que upserta `daily_pnl` no SQLite a cada cycle.
- **ConsecutiveBreaker** (Story 029) — counter passivo de hits booleanos para safety net (exec error / vision fallback).
- **UnifiedAuditReader** (Story 032) — leitura unificada SQLite + NDJSON.
- **TelegramAlerter** (Story 035) — push-only Telegram alerts em eventos críticos. Off por default.
- **TelegramInboundPoller** (Story 035b + 037) — long-polling de comandos do operador. Comandos: `/status /pnl /pause /resume /positions /perf /gates /help`. `/perf [N]` roda Deadpool (N dias). `/gates` mostra status H1–H6 em tempo real. Requer `TELEGRAM_INBOUND_ENABLED=true`.

## Dev / Quality Agents (NÃO participam do loop de trading)

- **Prometheus** — Prompt Engineering Operator. Determinístico, sem LLM, offline. Audita prompts de `src/agents/` segundo framework P.R.O.M.P.T. (scorecard /40), versiona via SHA-256, cataloga opcionalmente em `data/prompts/catalog.json`. Interface: `scripts/prometheus_cli.py`. Módulo: `src/prompt_engineering/`. **NUNCA importado pelo runtime de trade** — test de isolamento garante invariante.

## Hard Rules

- Never place real trades unless `paper_trading=False` and Batman approves with no breached limits — even then, Iron Man requires explicit operator awareness.
- Never bypass Batman.
- Never share state across projects.
- Always emit logs (loguru), audit_log rows (SQLite), and Pydantic-validated outputs.
- Kill switch (env `MEKKA_KILL_SWITCH=1` or file `data/.kill_switch`) is absolute.

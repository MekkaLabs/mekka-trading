# 🦸 Mekka Trading — Relatório Completo do Sistema
**Data:** 2026-05-18  
**Última story entregue:** 243 (Milestone 39 completo)  
**Auditor:** Claude Sonnet 4.6 via Cowork  
**Escopo:** Todos os agentes · Performance & Latência · Qualidade de Sinais · Dashboard & UX · Caminho para Mainnet

---

## 0. Resumo Executivo

O Mekka Trading é um sistema de trading multi-agente autônomo com **243 stories entregues** em **39 milestones**. A arquitetura está madura, bem documentada e segura para paper trading. O sistema tem 17 agentes ativos, 20+ gates de risco no Batman, pipeline LLM com fallback OpenAI→Claude, dashboard completo em porta 8787, backtesting integrado e sistema de debate multiagente.

**Status geral:** ✅ Operacional em paper trading | 🔴 Bloqueado para mainnet (H1–H6 pendentes)

### Saúde por camada

| Camada | Agentes | Status | Observação |
|--------|---------|--------|-----------|
| L1 — Market Analysis | Superman, Doctor Strange, Black Panther, Thor, Aquaman, Spider-Man | ✅ Saudável | Paralelo via asyncio.gather |
| L1.5 — Tático | Flash | ✅ Ativo | Advisory only — sem consumidores downstream ainda |
| L2 — Estratégia | Vision, VisionCritic, VisionMoA, ProfessorX | ✅ Saudável | 3 modos de inferência (single, critic, MoA) |
| L3 — Risco/Execução | Batman, IronMan | ✅ Saudável | 20+ gates determinísticos no Batman |
| L4 — Comando | NickFury, Wolverine, Cyclops, PortfolioManager | ✅ Saudável | Monitor cycle 5min + main cycle 4h |
| Analytics | Deadpool | ✅ Ativo | Gate H2 integrado ao preflight |
| Serviços | TelegramAlerter, TelegramInbound, DailyPnLWriter, DebateModerator | ✅ Implementados | Telegram configurado |

---

## 1. Auditoria Completa dos Agentes

### 1.1 Layer 1 — Análise de Mercado (paralelos)

#### 🦸 Superman — Chief Market Overseer
**Arquivo:** `src/agents/superman.py`  
**Output:** `MarketData` (RSI-14, EMA-20/50, BB, MACD, ATR-14, trend, recent_closes)

**Estado atual:**
- Compatível com Python 3.14 (indicadores manuais, sem pandas_ta/numba)
- Exchange fallback chain: Hyperliquid → Bybit → Binance via CCXT
- Dois timeframes: primário (4h) + confirmação (1h)
- Trend classification heurística: EMA relationship + RSI + MACD histogram

**Pontos fortes:**
- Fallback robusto entre exchanges
- Cálculos manuais garantem compatibilidade cross-version
- `recent_closes` exposto para Flash

**Gaps identificados:**
- Sem Volume Profile (VWAP intraday ausente)
- Sem detecção de suporte/resistência automática
- Fibonacci retracement não implementado
- Order flow imbalance ausente (diferente do L2 orderbook do Aquaman)
- MACD histogram normalizado poderia melhorar a sinalização

**Melhorias sugeridas:**
```
M-SUP-01: Adicionar VWAP rolling 24h ao MarketData — referência de preço justo
M-SUP-02: Suporte/Resistência automático via pivots (swing high/low nos últimos N candles)
M-SUP-03: Expor `volume_profile_poc` (Point of Control da sessão) — útil para Vision
M-SUP-04: Normalizar MACD histogram para range [-1, +1] para comparação entre ativos
```

---

#### 🧙 Doctor Strange — Macro Probability Analyst
**Arquivo:** `src/agents/doctor_strange.py`  
**Output:** `SentimentData` (score -1.0→+1.0, fear_greed, btc_dominance)

**Estado atual:**
- 3 fontes: CryptoPanic + Fear & Greed + CoinGecko BTC dominance
- Timeout 10s por fonte
- Score composto -1.0→+1.0
- Ativação condicional: `settings.sentiment_enabled` = `bool(cryptopanic_api_key)`

**Pontos fortes:**
- Arquitetura de 3 fontes reduz dependência única
- Agregação defensiva (falha de uma fonte não derruba o agente)

**Gaps identificados:**
- CryptoPanic gratuito tem rate limit baixo (~100/dia) e atraso de 15min
- Sem análise de sentimento em redes sociais (X/Twitter, Reddit)
- BTC dominance como proxy de risk appetite é muito grosseiro
- Sem distinção de sentimento por ativo (BTC vs ETH vs SOL podem divergir)
- Fear & Greed é diário — pouca granularidade para ciclos de 4h

**Melhorias sugeridas:**
```
M-DS-01: Adicionar Santiment ou LunarCrush como fonte alternativa ao CryptoPanic
M-DS-02: Sentiment por símbolo: filtrar news do CryptoPanic por ticker (já suportado pela API)
M-DS-03: Cache de 30min para Fear & Greed (dado é diário, chamada repetida é desperdício)
M-DS-04: Expor `news_count_last_4h` e `negative_ratio` no SentimentData (textura da notícia)
```

---

#### 🐾 Black Panther — Onchain Intelligence
**Arquivo:** `src/agents/black_panther.py`  
**Output:** `OnchainData` (funding_rate, open_interest, whale_flow, stance ACCUMULATION/DISTRIBUTION/NEUTRAL)

**Estado atual:**
- Consulta Hyperliquid `/info` para funding rate, OI e large trades
- Whale flow detectado por tamanho de trade (threshold configurável)

**Pontos fortes:**
- Dados onchain direto da exchange — sem intermediário
- Funding rate usado também pelo gate Batman 3i

**Gaps identificados:**
- Sem histórico de funding rate (somente spot atual)
- Whale flow usa threshold fixo — deveria ser dinâmico por ATR e liquidez
- Open Interest delta (variação vs ciclo anterior) não calculado
- Sem detecção de large liquidations (dado público na HL)
- Sem correlação BTC dominance × OI para detectar altseason

**Melhorias sugeridas:**
```
M-BP-01: Calcular OI delta % vs ciclo anterior — indica entrada/saída de capital
M-BP-02: Whale threshold dinâmico = max(50k, 0.1% do OI) em vez de valor fixo
M-BP-03: Monitorar liquidation cascade (liquidações > X no último candle) — Spider-Man deveria receber
M-BP-04: Expor `funding_rate_7d_avg` para contexto histórico (diferente do spot)
```

---

#### ⚡ Thor — Volatility Engine
**Arquivo:** `src/agents/thor.py`  
**Output:** `VolatilityData` (regime LOW/MEDIUM/HIGH/EXTREME, multiplier 1.2x/1.0x/0.6x/0.3x, ATR%)

**Estado atual:**
- Regime baseado em ATR% com 4 níveis
- Multiplier de posição aplicado pelo Batman no gate 5
- Opcional: vol realizada anualizada 7 dias

**Pontos fortes:**
- 4 níveis de regime bem calibrados
- Multiplier integrado diretamente ao Batman
- Parâmetros de leverage separados por regime (HIGH vs EXTREME)

**Gaps identificados:**
- Regime calculado sobre ATR instantâneo — susceptível a spike único
- Sem comparação com vol histórica (ativo pode ter ATR 3% que seja "baixo" para ele)
- Sem detecção de compressão de volatilidade (potencial breakout iminente)
- Vol cone (percentil histórico) não implementado

**Melhorias sugeridas:**
```
M-TH-01: Regime baseado em percentil ATR dos últimos 30 dias (ATR relativo ao histórico)
M-TH-02: Detectar squeeze de BB (banda < X% da média) — expor `volatility_squeeze=True`
M-TH-03: Expor `atr_percentile_30d` no VolatilityData — Vision usa para calibrar SL/TP
M-TH-04: Vol cone: calcular ATR percentual em 5 janelas (7/14/30/60/90d) para contexto
```

---

#### 🌊 Aquaman — Liquidity Analyst
**Arquivo:** `src/agents/aquaman.py`  
**Output:** `LiquidityData` (depth_bid/ask, spread, slippage_10k_usd, liquidity_score 0-1)

**Estado atual:**
- L2 orderbook via Hyperliquid `/info`
- Depth 0.5% do mid, spread, slippage estimado para $10k
- Score 0-1 composto

**Pontos fortes:**
- Slippage estimado em USD específico é muito útil para sizing
- Score 0-1 normalizável para Batman

**Gaps identificados:**
- Slippage estimado apenas para $10k — deveria escalar com a posição real planejada
- Sem detecção de book imbalance (bid/ask ratio)
- Spread relativo (spread/mid) não normalizado por histórico
- Sem detectar thin book (poucos níveis de preço no L2)

**Melhorias sugeridas:**
```
M-AQ-01: Calcular slippage para o tamanho real planejado (equity × size_pct × leverage)
M-AQ-02: Expor `book_imbalance_ratio` (bid_depth / ask_depth) — indica pressão direcional
M-AQ-03: Normalizar spread por médias históricas (spread_ratio = current/ma20)
M-AQ-04: Detectar `thin_book=True` quando níveis < 5 dentro de 0.5% do mid
```

---

#### 🕷️ Spider-Man — Anomaly Detector
**Arquivo:** `src/agents/spider_man.py`  
**Output:** `AnomalyReport` (checks: flash_crash, volume_spike, extreme_funding, BB_break, agent_divergence, extreme_RSI; severity NONE/LOW/MEDIUM/HIGH)

**Estado atual:**
- 6 checks independentes
- HIGH severity → `should_pause=True`
- Recebe chart + onchain como inputs

**Pontos fortes:**
- Checks puramente determinísticos — sem LLM
- `should_pause` direto ao Vision pre-flight

**Gaps identificados:**
- Agent divergence check heurístico (sem pesos por credibilidade)
- Sem detecção de regime change abrupto (mudança de trend intracandle)
- Flash crash usa threshold absoluto — deveria ser relativo ao ATR
- Sem memória de anomalias recentes (anomalia recorrente deveria ter severidade elevada)

**Melhorias sugeridas:**
```
M-SP-01: Flash crash threshold = 3× ATR do candle atual (relativo à volatilidade)
M-SP-02: Anomaly streak: se MEDIUM ocorreu nos últimos 2 ciclos, upgrade para HIGH
M-SP-03: Detectar regime change: trend mudou vs ciclo anterior? Expor `trend_changed=True`
M-SP-04: Expor `top_anomaly_reason` como string curta para Vision incluir no reasoning
```

---

### 1.2 Layer 1.5 — Tático

#### 🏃 Flash — Momentum Scalper
**Arquivo:** `src/agents/flash.py`  
**Output:** `MomentumSignal` (direction UP/DOWN/SIDEWAYS, strength 0-1, VOLUME-CONFIRMED tag)

**Estado atual:**
- Net price move + volume multiplier em janela curta
- Advisory only — nenhum agente downstream consome atualmente
- Disponível via ProfessorX no MarketAnalysis.momentum

**Gaps identificados:**
- **Maior gap do sistema**: MomentumSignal gerado mas não consumido por Vision
- Sem integração direta com timing de entrada
- Sem gate de filtro: Flash poderia evitar entradas contra momentum

**Melhorias sugeridas:**
```
M-FL-01 (ALTO IMPACTO): Injetar Flash.momentum no prompt do Vision como seção dedicada
M-FL-02: Gate de entry timing: se Flash=SIDEWAYS e Vision=LONG/SHORT, reduzir size 20%
M-FL-03: Flash pode servir como confirmation gate: Vision só entra se Flash confirma direção
M-FL-04: Expor Flash em endpoint GET /api/momentum/live para dashboard
```

---

### 1.3 Layer 2 — Estratégia

#### 👁️ Vision — Predictive Analyst
**Arquivo:** `src/agents/vision.py`  
**Output:** `TradingSignal` (action, confidence, entry/SL/TP, size_pct, leverage, reasoning)

**Estado atual:**
- GPT-4o principal, Claude Sonnet como fallback automático
- Pre-flight: `is_safe_to_trade` antes de chamar LLM
- HOLD seguro em qualquer falha
- Sistema prompt robusto com 7 princípios de decisão
- 5+ padrões de AI frameworks integrados: ArchitectEditor, AutoSignalLinter, VisionCritic, MoA, Pre-Reasoning, ReasoningBudget, PromptCache, SemanticMemory

**Pontos fortes:**
- Fallback chain robusto (OpenAI → Claude)
- Múltiplos layers de qualidade (Critic + MoA)
- Memória episódica semântica integrada
- PromptCache reduz latência em ciclos consecutivos
- DynamicReasoningBudget ajusta tokens por regime/cap_tier

**Gaps identificados:**
- Debate Verdict (Milestone 39) chega como texto no analysis — mas não tem campo dedicado no prompt Vision
- Flash.momentum não incluído no prompt
- `agent_contributions` no output raramente validado quantitativamente
- Vision não tem acesso ao histórico de Batman verdicts recentes
- Temperature 0.2 igual para todos os regimes (deveria ser mais baixo em EXTREME)

**Melhorias sugeridas:**
```
M-VI-01 (ALTO IMPACTO): Injetar debate_verdict como bloco estruturado no prompt Vision
M-VI-02 (ALTO IMPACTO): Injetar Flash momentum no prompt Vision
M-VI-03: Temperature dinâmico: EXTREME regime → 0.0, NORMAL → 0.2, LOW vol → 0.3
M-VI-04: Incluir Batman approval rate histórico por símbolo no prompt (ex: "BTC aprovado 70% das vezes")
M-VI-05: Validar `agent_contributions` — checar se pelo menos 4 dos 6 agentes aparecem
```

---

#### 🧠 Professor X — Swarm Coordinator
**Arquivo:** `src/agents/professor_x.py`  
**Output:** `MarketAnalysis` bundle

**Estado atual:**
- `asyncio.gather` com `return_exceptions=True` para isolamento
- Superman required, demais best-effort
- Debate integrado (Story 243) via `_maybe_run_debate`
- Routing adaptativo via `settings.layer1_routing_enabled`

**Pontos fortes:**
- Excelente isolamento de falhas
- Debate fire-and-forget (não bloqueia Vision)
- Flash integrado no gather

**Gaps identificados:**
- `_maybe_run_debate` usa heurísticas fixas para votos dos agentes
- Debate não consulta os agentes reais — usa estimativas baseadas em valores do MarketAnalysis
- Spider-Man ainda rodando serial após o gather (latência adicional)

**Melhorias sugeridas:**
```
M-PX-01 (MILESTONE 41): Substituir heurísticas do debate por chamadas reais aos L1 agents
M-PX-02: Paralelizar Spider-Man junto com os demais (remove dependência do onchain)
M-PX-03: Expor latência de cada agente no log estruturado (timing por agente no gather)
M-PX-04: Cache de análise por (symbol, candle_timestamp) — evitar re-análise no mesmo candle 4h
```

---

### 1.4 Layer 3 — Risco e Execução

#### 🦇 Batman — Risk Guardian
**Arquivo:** `src/agents/batman.py` (~1324 linhas)  
**Output:** `RiskApproval` (APPROVED/REDUCED/REJECTED/KILL_SWITCH)

**Estado atual — Gates implementados:**

| Gate | ID | Descrição | Status |
|------|----|-----------|--------|
| Kill Switch | 0 | File/env → halt absoluto | ✅ |
| HOLD bypass | 1 | Nada a executar | ✅ |
| Daily drawdown | 2 | ≥ max_daily_drawdown_pct | ✅ |
| Pyramid bypass | 3k | Scale-in em posição lucrativa | ✅ |
| Max open positions | 3 | ≥ max_open_positions | ✅ |
| Max trades/day | 3 | ≥ max_trades_per_day | ✅ |
| Total capital cap | 3b | Notional total vs equity | ✅ |
| Correlation gate | 3c | Posições correlacionadas mesma direção | ✅ |
| Episodic memory | 3d | Win rate histórico por padrão | ✅ |
| Portfolio exposure | 3e | Notional total aberto | ✅ |
| Re-entry cooldown | 3f | Cooling após SL Cyclops | ✅ |
| Symbol blacklist | 3g | 3 SLs consecutivos → blacklist 24h | ✅ |
| MTF confluence | 3h | Sinal vs tendência 4h | ✅ |
| Funding rate | 3i | Crowded positioning | ✅ |
| Trading hours | 3j | UTC window (desabilitado por default) | ✅ |
| Max trades/símbolo/dia | 3l | Por símbolo por dia | ✅ |
| Min notional | 3m | Micro-posição | ✅ |
| Max symbol drawdown/semana | 3n | Por símbolo na semana | ✅ |
| Max consecutive losses | 3o | N perdas consecutivas | ✅ |
| Directional bias | 3p | N trades na mesma direção | ✅ |
| Min ATR | 3q | Mercado parado | ✅ |
| Confidence gate | 4 | ≥ min_confidence_threshold | ✅ |
| R:R gate | 4 | ≥ min_risk_reward_ratio | ✅ |
| Thor multiplier | 5 | Ajuste por volatilidade | ✅ |
| ATR sizing | 5 | Sizing inversamente proporcional ao ATR | ✅ |
| Liquidity penalty | 5 | score < 0.4 → reduz size | ✅ |
| Runtime mode | 5 | Hot-reload de parâmetros | ✅ |
| Regime gate | 5b | BEAR/VOLATILE adjustments | ✅ |
| Asset classifier | 5c | SMALL/MID/LARGE_CAP leverage | ✅ |
| Signal Quality Score | 6 | Score 0-100 no approval metadata | ✅ |

**Pontos fortes:**
- Batman é o agente mais completo e seguro do sistema
- 20+ gates com fallback gracioso em todos
- Signal Quality Score (0-100) integrado no approval metadata

**Gaps identificados:**
- Gate de posição correlacionada usa runtime_mode params — acoplamento não documentado
- Sem gate de momentum divergence (Flash SIDEWAYS + sinal LONG deveria reduzir size)
- Sem gate de tempo-desde-último-trade (muito logo após outro trade = risky)
- Episodic memory gate importa dinamicamente (lento — deveria ser injetado)

**Melhorias sugeridas:**
```
M-BM-01: Gate 3r — Flash momentum divergence: se Flash ≠ direção do sinal → REDUCED 30%
M-BM-02: Gate 3s — Time since last trade: < 30min após trade no mesmo símbolo → REDUCED
M-BM-03: Injetar AgentMemoryStore como dependency injection no __init__ (não import dinâmico)
M-BM-04: Expor gate_id de cada rejeição no `breached_limits` com numeração formal (já existe parcialmente)
```

---

#### 🤖 Iron Man — Execution Engineer
**Arquivo:** `src/agents/iron_man.py`  
**Output:** `ExecutionResult` (FILLED/PARTIAL/PAPER/REJECTED/ERROR/SKIPPED)

**Estado atual:**
- Paper mode: fill simulado em `signal.entry_price`
- Live mode: Hyperliquid SDK com tenacity retry (3x, backoff exponencial)
- Mock Realism: latência aleatória + partial fills + slippage extra (Story 144)
- Multi-exchange: Hyperliquid, Bybit, Binance via CCXT
- Double gate: `paper_trading=False` E `live_trading_confirmed=True`

**Pontos fortes:**
- Retry robusto com exponential backoff
- Mock realism para stress test realista
- Double gate imperfeito ausente - é intencional e correto

**Gaps identificados:**
- Paper mode fill usa `signal.entry_price` (exato) — sem modelagem de slippage por liquidez
- Sem cálculo de custo de funding durante a posição (para planejamento de holding time)
- Bracket orders (SL/TP) em live mode: verificar se são reduce-only no HL testnet
- Sem logging do fill ratio esperado vs executado em modo paper

**Melhorias sugeridas:**
```
M-IM-01: Paper fill = entry_price ± slippage dinâmico baseado em Aquaman.slippage_pct
M-IM-02: Calcular funding cost estimate para o período de holding planejado (SL→TP range)
M-IM-03: Expor `fill_quality_score` = (expected_fill - actual_fill) / ATR para monitoramento
```

---

### 1.5 Layer 4 — Comando e Controle

#### 😤 Nick Fury — Mission Commander
**Arquivo:** `src/agents/nick_fury.py` (~34k tokens)  
**Output:** `list[CycleReport]`

**Estado atual:**
- Main cycle: 4h por símbolo (BTC, ETH, SOL por default)
- Monitor cycle: 5min (Wolverine + Cyclops)
- Múltiplos padrões AI integrados: LangGraph checkpoint, CycleStateGraph, CycleSOP, IncrementalCycleSkip, MetaGPT patterns, OpenHands patterns, SWE-agent patterns
- Monitors wired: DrawdownMonitor, PositionConcentrationAlerter, IntradayPnLTracker, FundingRateMonitor, AlertThrottleManager

**Pontos fortes:**
- Pipeline mais completo do sistema
- Increment skip evita LLM em ciclos estáveis
- Monitors de risco intraday bem integrados

**Gaps identificados:**
- `run_main_cycle` muito grande — difícil de testar individualmente
- Sem paralelização por símbolo (BTC, ETH, SOL rodam sequencialmente)
- CycleParallelBranch implementado (Story 211) mas pode não estar ativado no default

**Melhorias sugeridas:**
```
M-NF-01 (ALTO IMPACTO): Ativar CycleParallelBranch por default para multi-símbolo paralelo
M-NF-02: Expor cycle_duration_ms por símbolo no audit_log (telemetria de latência)
M-NF-03: Extração de _cycle_for_symbol para função pura testável independentemente
```

---

#### 🐺 Wolverine — Recovery Agent
**Arquivo:** `src/agents/wolverine.py`  
**Output:** `RecoveryPlan` (ações: HOLD/TIGHTEN_STOP/TRAIL_STOP/SCALE_OUT/CLOSE/EMERGENCY_CLOSE)

**Estado atual:**
- Read-only (não toca SDK)
- Kill switch se drawdown intraday explode entre ciclos
- Idempotente

**Gaps identificados:**
- Sugestões de Wolverine são advisory — NickFury executa via Cyclops mas o loop pode demorar 5min
- Sem priorização por urgência (EMERGENCY_CLOSE deveria ter caminho mais rápido)

---

#### 🚨 Cyclops — Order Manager
**Arquivo:** `src/agents/cyclops.py`  
**Output:** `ExecutionResult` (paper closes)

**Estado atual:**
- SL/TP automático em paper mode
- No-op em live (bracket orders no exchange)
- Partial SL (Story 105)
- TP Ladder (Story 083)

---

#### 📊 Deadpool — Performance Analytics
**Arquivo:** `src/agents/deadpool.py`  
**Output:** `PerformanceReport` + `PerformanceVerdict` (READY/NOT_READY/INSUFFICIENT_DATA)

**Estado atual:**
- Determinístico, sem LLM
- Métricas: win_rate, PnL, Sharpe, maxDD, Wolverine endorsement rate, signal actionability
- Gate H2 integrado ao preflight
- Comando Telegram `/perf [N]`

---

## 2. Eixo 1 — Performance & Latência

### 2.1 Estado atual do pipeline

```
Ciclo típico 4h (single symbol):
├── Superman OHLCV fetch + indicadores:     ~800ms (CCXT HTTP + cálculo)
├── Doctor Strange (3 HTTP calls paralelo): ~600ms (F&G + CryptoPanic + CoinGecko)
├── Black Panther (HL /info):               ~400ms
├── Thor (cálculo puro):                    ~20ms
├── Aquaman (HL L2):                        ~400ms
├── Flash (cálculo puro):                   ~10ms
├── Spider-Man (pós-gather):                ~30ms
├── ProfessorX gather overhead:             ~50ms
├── Vision LLM (GPT-4o):                   ~2.000–4.000ms
├── VisionCritic (+ 1 LLM call):           ~2.000ms (quando habilitado)
├── Batman (20+ gates, 3 DB queries):       ~200ms
├── IronMan paper fill:                     ~10ms
└── SQLite audit_log writes:               ~50ms

Tempo estimado total por símbolo: ~6–8s (paper, sem MoA)
Com MoA: +4–6s (3 LLMs paralelos)
Multi-símbolo (BTC+ETH+SOL): ~18–24s sequencial
```

### 2.2 Gargalos identificados

**Gargalo 1: Superman CCXT (~800ms)**
- CCXT usa REST polling — sem stream
- Fallback chain tenta exchanges adicionais em série

**Gargalo 2: Vision LLM (~2–4s)**
- Maior contribuidor de latência no pipeline
- Variância alta (picos de 8s em congestionamento da API)
- IncrementalCycleSkip mitiga quando preço estável

**Gargalo 3: Multi-símbolo sequencial**
- BTC → ETH → SOL em série = 3× o tempo
- CycleParallelBranch existe mas precisa ser ativado

**Gargalo 4: Batman com 3 DB queries (gates 3d, 3f, 3g, 3n, 3o, 3p)**
- Múltiplas queries SQLite a cada ciclo
- Connection overhead por query (sem pool)

### 2.3 Melhorias de performance propostas

**P-LAT-01 — Ativar CycleParallelBranch (impacto: -60% latência multi-símbolo)**
```python
# settings.py — adicionar:
cycle_parallel_enabled: bool = Field(default=True, ...)
```
BTC, ETH, SOL rodariam em paralelo → ciclo 3-símbolo = tempo de 1 símbolo.

**P-LAT-02 — Cache de sentimento Doctor Strange (impacto: -600ms por ciclo)**
```python
# F&G e BTC dominance mudam 1×/dia — cache de 6h
# CryptoPanic muda mais rápido — cache de 30min
```

**P-LAT-03 — Batman DB query batching (impacto: -150ms)**
```python
# Hoje: 6 queries independentes no _run()
# Proposta: MekkaRepository.get_batman_context(symbol) → 1 query com JOINs
```

**P-LAT-04 — Connection pool SQLite aiosqlite (impacto: -50ms)**
```python
# Criar pool de conexões em MekkaRepository.__init__
# aiosqlite suporta connection pool via asyncio.Queue
```

**P-LAT-05 — Vision LLM response streaming (impacto: UX improvement)**
```python
# Usar streaming=True no LLMClient para receber tokens incrementalmente
# Dashboard pode mostrar Vision "pensando" em tempo real
```

**P-LAT-06 — Superman OHLCV cache por candle (impacto: -400ms em re-análises)**
```python
# Cache keyed por (symbol, timeframe, candle_open_time)
# Válido até abertura do próximo candle
# AnalysisPromptCache já implementado — estender para OHLCV
```

### 2.4 Métricas de latência atuais vs target

| Estágio | Atual | Target P50 | Target P95 |
|---------|-------|------------|------------|
| Layer 1 (paralelo) | ~800ms | 600ms | 1000ms |
| Vision LLM | ~2500ms | 1500ms | 4000ms |
| Batman gates | ~200ms | 100ms | 300ms |
| **Ciclo total (1 símbolo)** | **~6s** | **3.5s** | **8s** |
| **Ciclo total (3 símbolos)** | **~18s** | **5s (paralelo)** | **10s** |

---

## 3. Eixo 2 — Qualidade dos Sinais

### 3.1 Análise do pipeline de decisão

O pipeline de sinal tem 5 camadas de qualidade:
1. **Análise de mercado** (6 agentes L1 → MarketAnalysis)
2. **Debate** (DebateModerator, quando habilitado)
3. **Inferência** (Vision LLM + ArchitectEditor + Pre-Reasoning)
4. **Revisão** (VisionCritic ou MoA)
5. **Gate de risco** (Batman com 20+ verificações)

### 3.2 Pontos cegos do sinal atual

**Ponto cego 1: Flash não é consumido por Vision**
Flash captura momentum intracandle mas este dado não chega ao prompt do Vision. Um setup bullish de 4h com Flash SIDEWAYS ou DOWN é menos confiável.

**Ponto cego 2: Debate verdict não estruturado no prompt Vision**
O `debate_verdict` é adicionado ao `MarketAnalysis` mas Vision recebe como texto livre — sem seção dedicada de alta visibilidade no prompt.

**Ponto cego 3: VisionCritic pode amenizar mas não tem acesso ao contexto de Batman**
O Critic não sabe quantas posições estão abertas, o drawdown atual, nem o Signal Quality Score do approval anterior.

**Ponto cego 4: SL/TP geometria é responsabilidade do Vision sem referência a suporte/resistência**
Vision calcula SL/TP baseado em raciocínio LLM, sem acesso a níveis técnicos objetivos (pivots, BB, VWAP).

**Ponto cego 5: Absence of market structure (order flow)**
O sistema não tem imbalance de order flow — grande blind spot para timing de entrada.

### 3.3 Melhorias de qualidade de sinal propostas

**Q-SIG-01 — Flash → Vision integration (impacto: +5-8% win rate estimado)**
```python
# Em vision.py prompt, adicionar seção:
## Flash Momentum (intra-candle):
direction={momentum.direction.value}, strength={momentum.strength:.2f}
{"[VOLUME-CONFIRMED]" if momentum.volume_confirmed else ""}
# Instrução: se Flash=SIDEWAYS, reduzir confiança em 0.05 automaticamente
```

**Q-SIG-02 — Debate Verdict no prompt Vision (impacto: melhora consistência)**
```python
# Adicionar seção estruturada ao prompt:
## Multiagent Debate Result (L1 consensus):
consensus_action={debate_verdict.consensus_action}
consensus_confidence={debate_verdict.consensus_confidence:.0%}
dissenters={debate_verdict.dissenters}
# Instrução: se debate_verdict contradiz sinal, reduzir confidence 0.10
```

**Q-SIG-03 — SL/TP ancorado em níveis técnicos (impacto: melhora geometria)**
```python
# Superman deve expor support_levels e resistance_levels
# Vision recebe e deve usar como referência para SL/TP
# "Preferred SL: below nearest support. Preferred TP: near next resistance."
```

**Q-SIG-04 — Batman Signal Quality Score → Vision feedback loop (impacto: melhora calibração)**
```python
# RoleWorkingMemory já injetado — adicionar campo:
# "Últimos 3 sinais para {symbol}: avg_quality_score={avg:.0f}/100, approvals={n}/3"
# Vision aprende a calibrar confidence para pass rate histórico
```

**Q-SIG-05 — Vision temperature adaptativo por regime (impacto: reduz ruído em EXTREME)**
```python
# Em vision.py:
_temp = {
    "EXTREME": 0.0,   # máxima determinismo em crise
    "HIGH": 0.1,
    "MEDIUM": 0.2,
    "LOW": 0.3,       # mais criatividade em mercado flat
}.get(regime_str, settings.openai_temperature)
```

**Q-SIG-06 — VisionMoA como default em mercados BULL (impacto: diversidade de perspectivas)**
```
Proposta: vision_moa_enabled ativado automaticamente quando market_regime=BULL
Em BULL, 3 LLMs em paralelo reduzem viés de modelo único nos grandes rallies
```

### 3.4 Análise do Batman como filtro de qualidade

Com 20+ gates, Batman filtra ativamente sinais ruins. Problemas identificados:

- Episodic memory gate (3d) usa import dinâmico dentro do `_run` — overhead em cada chamada
- Gates que falham silenciosamente (fall-open) não geram métrica de quantas vezes foram pulados
- Sem relatório de "gates mais acionados" no dashboard (útil para calibração)

**Proposta:**
```
Q-BAT-01: MekkaRepository.get_batman_context(symbol) — 1 query batch para gates 3d/3f/3g/3n/3o/3p
Q-BAT-02: Métricas de gate: EventBus publish gate_triggered/gate_skipped por ID
Q-BAT-03: Dashboard endpoint GET /api/risk/gate-stats — ranking de gates por acionamento
```

---

## 4. Eixo 3 — Dashboard & UX

### 4.1 Estado atual do dashboard

**URL:** http://localhost:8787  
**Arquivo:** `src/dashboard/server.py` (~2000 linhas) + `app.js` (~5500 linhas)  
**Tecnologia:** aiohttp + WebSocket + SSE + Chart.js

**Páginas implementadas:**

| Ícone | Página | Status | Completude |
|-------|--------|--------|-----------|
| 🏠 | Overview | ✅ Funcional | Widget "Resultado do Dia" corrigido (18 bugs) |
| 💼 | Wallet | ✅ Funcional | Posições + equity |
| ⚡ | Performance | ✅ Funcional | Rolling metrics + divergência |
| 🤖 | Agents | ✅ Funcional | Status dos agentes |
| 📋 | Trades | ✅ Funcional | Histórico |
| 🧠 | Memory | ✅ Funcional | Audit log |
| 🛡️ | Risk | ✅ Funcional | Batman timeline + heatmaps |
| 📜 | Logs | ✅ Funcional | Real-time |
| ⚙️ | Settings | ✅ Funcional | Configurações |
| 🏆 | Leaderboard | ✅ Funcional | Ranking |
| 📑 | Relatórios | ✅ Funcional | P&L + Histórico |
| 📊 | Backtest | ✅ Funcional | Interactive + Chart.js |
| 🔬 | Analytics | ✅ Funcional | Advanced |
| 📡 | Live | ✅ Funcional | Feed ao vivo + SSE |
| 🗣️ | Debate | ✅ Funcional | Run on-demand + histórico |

### 4.2 Gaps do dashboard

**Gap D-01: Página de Flash momentum ausente**
Flash não tem representação visual. Um painel de micro-momentum seria valioso para o operador.

**Gap D-02: Sem visualização de Signal Quality Score (0-100)**
Batman calcula o SQS mas não há widget dedicado no dashboard.

**Gap D-03: Sem mapa de correlação de ativos em tempo real**
O gate de correlação (3c) rejeita silenciosamente — o operador não vê quais pares estão correlacionados.

**Gap D-04: Sem timer visual do próximo ciclo**
O dashboard não mostra "próxima análise em X min" para o operador saber quando esperar.

**Gap D-05: Pixel Office não tem indicadores ao vivo**
A página `/office-v2/` é visual mas não exibe métricas reais sobre os heróis.

**Gap D-06: Sem modo mobile**
CSS atual não é responsivo — difícil monitorar pelo celular.

**Gap D-07: Sem alert badge visual para gates acionados**
Quando Batman rejeita por 3o (consecutive losses), não há destaque visual no dashboard.

### 4.3 Melhorias de UX propostas

**UX-01 — Signal Quality Score widget na página Risk (impacto: visibilidade operacional)**
```
Widget circular (gauge 0-100) mostrando o SQS do último sinal aprovado por símbolo
Verde > 70 | Amarelo 50-70 | Vermelho < 50
```

**UX-02 — Timer do próximo ciclo no topbar (impacto: reduz ansiedade do operador)**
```
"Próximo ciclo: 03:47:22" com countdown em tempo real
Alimentado pelo main_loop_interval_seconds e timestamp do último ciclo
```

**UX-03 — Gate de Batman dashboard (impacto: diagnóstico de rejeições)**
```
Endpoint: GET /api/risk/gate-stats?days=7
Exibe: ranking de gates mais acionados, % de rejeições por gate
Útil para calibrar parâmetros de settings
```

**UX-04 — Flash momentum live widget (impacto: timing de entrada)**
```
Endpoint: GET /api/momentum/live
Widget: seta direcional por símbolo + strength bar + VOLUME-CONFIRMED badge
```

**UX-05 — Correlation map (impacto: visibilidade do gate 3c)**
```
Matrix 3×3 (BTC/ETH/SOL) com correlação rolling 7 dias
Células vermelhas = alta correlação = gate 3c ativo
```

**UX-06 — Batman gate breakdown no card de sinal (impacto: debugging)**
```
Em cada sinal rejeitado: mostrar lista de gates que acionaram com motivo curto
Atualmente apenas aparece como texto no audit log
```

**UX-07 — Pixel Office com status dos heróis (impacto: visual)**
```
Cada herói no Office mostra: último resultado, latência, status (OK/ERROR/SKIP)
Click abre drawer com detalhes do último run
```

---

## 5. Eixo 4 — Caminho para Mainnet (Milestone 40)

### 5.1 Status dos Gates H1–H6

| Gate | Descrição | Status | Bloqueador |
|------|-----------|--------|-----------|
| **H1** | Histórico testnet ≥ 1 mês sem incidente crítico | 🔴 Pendente | Falta confirmação do período |
| **H2** | Wolverine ENDORSE rate ≥ 70% (últimos 30d) | 🔴 Pendente | Deadpool não tem dados suficientes |
| **H3** | Preflight script verde (`python3 scripts/preflight_mainnet.py`) | 🔴 Pendente | API keys reais ausentes |
| **H4** | Assinar `docs/MAINNET-AUTHORIZATION.md` | 🔴 Pendente | Checklist com `[ ]` ainda |
| **H5** | Carteira mainnet dedicada e funded | 🔴 Pendente | Placeholder keys no .env |
| **H6** | Telegram end-to-end testado | 🟡 Parcial | Bot configurado, testar comandos |

### 5.2 Bloqueadores críticos detalhados

**Bloqueador B1 — API Keys**
```bash
# Atual no .env:
HYPERLIQUID_PRIVATE_KEY=0x111...1  # PLACEHOLDER
HYPERLIQUID_WALLET_ADDRESS=0x111...1  # PLACEHOLDER

# Necessário:
1. Criar carteira EVM dedicada (MetaMask / hardware wallet)
2. NUNCA usar carteira pessoal
3. Depositar capital mínimo (sugestão: $100-500 para semana 1)
4. Exportar private key e substituir no .env
```

**Bloqueador B2 — LIVE_TRADING_CONFIRMED ausente**
```bash
# settings.py valida: se paper_trading=False e live_trading_confirmed=False → ValueError
# Necessário (só depois de H1-H5):
LIVE_TRADING_CONFIRMED=true
PAPER_TRADING=false
HYPERLIQUID_NETWORK=mainnet
```

**Bloqueador B3 — Parâmetros conservadores semana 1**
```bash
# Valores recomendados para semana 1 mainnet:
MAX_POSITION_SIZE_PCT=0.001    # 0.1% (vs default 2%)
MAX_LEVERAGE=2                  # (vs default 5)
MAX_DAILY_DRAWDOWN_PCT=0.05    # 5% (vs default 10%)
MAX_OPEN_POSITIONS=1            # Uma posição por vez
MAX_TRADES_PER_DAY=3           # (vs default 10)
TRADING_ASSETS=BTC              # Só BTC na semana 1
```

**Bloqueador B4 — Preflight script**
```bash
python3 scripts/preflight_mainnet.py
# Deve retornar: 🟢 ALL AUTOMATED CHECKS PASSED
# Checklist automático: API connectivity, DB integrity, kill switch, telegram
```

### 5.3 Roadmap Milestone 40 — Live Trading Gate (Stories 244-248)

**Story 244 — Preflight Automation + API Key Validator**
- Verificar conectividade real com HL testnet usando as keys configuradas
- Testar chamada read-only `/info` com a wallet real
- Verificar saldo mínimo na conta
- Output: relatório JSON + Telegram alert

**Story 245 — Gate H1 Formal: Testnet Activity Report**
- Deadpool computa relatório de 30 dias do testnet
- Verifica: trades executados ≥ 10, sem crashes críticos, uptime ≥ 90%
- Salva `docs/GATE_H1_REPORT.md` com timestamp

**Story 246 — Gate H2 Auto-check: Wolverine ENDORSE Rate**
- Deadpool calcula ENDORSE rate dos últimos 30 dias
- Verifica ≥ 70%
- Output: badge verde/vermelho no preflight

**Story 247 — Mainnet Authorization Flow**
- CLI interativo: `python3 scripts/mainnet_authorize.py`
- Exibe checklist H1-H6 com status atual
- Solicita texto `GO MAINNET` para confirmar
- Atualiza `docs/MAINNET-AUTHORIZATION.md` com timestamp e assinatura

**Story 248 — First Real Trade Pilot**
- Ativa mainnet com parâmetros ultra-conservadores (0.1% size, max 1 trade)
- Executa 1 ciclo completo com símbolos reais
- Salva relatório completo no Telegram
- Kill switch pronto na mão

### 5.4 Checklist do operador antes do Mainnet

```
PRÉ-MAINNET — CHECKLIST DO OPERADOR:

Configuração:
[ ] Carteira EVM dedicada criada (não é carteira pessoal)
[ ] Capital depositado na carteira (mínimo recomendado: $200)
[ ] HYPERLIQUID_PRIVATE_KEY substituído no .env
[ ] HYPERLIQUID_WALLET_ADDRESS substituído no .env
[ ] HYPERLIQUID_NETWORK=mainnet

Parâmetros conservadores semana 1:
[ ] MAX_POSITION_SIZE_PCT=0.001
[ ] MAX_LEVERAGE=2
[ ] MAX_DAILY_DRAWDOWN_PCT=0.05
[ ] TRADING_ASSETS=BTC (apenas 1 ativo na semana 1)
[ ] MAX_OPEN_POSITIONS=1

Validações:
[ ] python3 scripts/preflight_mainnet.py → 🟢 ALL CHECKS PASSED
[ ] python3 scripts/check_roster_consistency.py → [OK] 17 heroes
[ ] pytest -q → todos os testes passando
[ ] Dashboard acessível em http://localhost:8787
[ ] Telegram bot testado (/status retorna resposta)

Autorização:
[ ] docs/MAINNET-AUTHORIZATION.md revisado e assinado
[ ] Todos os [ ] → [x]
[ ] Linha "GO MAINNET" presente no documento

Monitoramento semana 1:
[ ] Dashboard aberto durante os primeiros ciclos
[ ] Telegram inbound ativado para comandos de pausa (/pause)
[ ] Kill switch script testado: ./scripts/kill.sh "teste"
[ ] rm data/.kill_switch para retomar
```

---

## 6. Roadmap de Melhorias — Priorizadas

### Tier 1 — Impacto Imediato (próximas 3 stories)

| ID | Melhoria | Impacto | Story sugerida |
|----|----------|---------|----------------|
| M-FL-01 | Flash momentum → Vision prompt | +5-8% win rate estimado | 244 (pode ser parte) |
| P-LAT-01 | CycleParallelBranch ativado | -60% latência multi-símbolo | 244 |
| Q-SIG-02 | Debate verdict estruturado no Vision | Consistência de sinais | 244 |
| UX-02 | Timer do próximo ciclo no topbar | UX operacional | 244 |

### Tier 2 — Qualidade (Milestone 41 — Debate Enhancement)

| ID | Melhoria | Impacto |
|----|----------|---------|
| M-PX-01 | Debate com chamadas reais aos L1 agents | Debate mais preciso |
| Q-SIG-03 | SL/TP ancorado em suporte/resistência | Geometria mais inteligente |
| Q-BAT-01 | Batman DB batch query | -150ms por ciclo |
| M-SUP-01 | VWAP no MarketData | Melhor referência de preço |
| M-TH-01 | Regime por percentil ATR histórico | Regime mais preciso |

### Tier 3 — Evolução (Milestone 42+)

| ID | Melhoria | Impacto |
|----|----------|---------|
| M-DS-01 | Santiment/LunarCrush | Sentimento mais rico |
| UX-03 | Batman gate-stats dashboard | Diagnóstico |
| UX-05 | Correlation map visual | Visibilidade operacional |
| M-VI-03 | Vision temperature adaptativo | Menos ruído |
| M-BP-01 | OI delta % por ciclo | Sinais onchain mais precisos |

### Tier 4 — Mainnet readiness (Milestone 40)

| ID | Story | Prioridade |
|----|-------|-----------|
| B1 | Story 244 — Preflight + API validator | CRÍTICO |
| B2 | Story 245 — Gate H1 testnet report | CRÍTICO |
| B3 | Story 246 — Gate H2 Wolverine check | CRÍTICO |
| B4 | Story 247 — Authorization flow CLI | CRÍTICO |
| B5 | Story 248 — First real trade pilot | CRÍTICO |

---

## 7. Análise de Risco do Sistema

### 7.1 Pontos de falha única identificados

| Componente | Risco | Mitigação atual | Gap |
|------------|-------|-----------------|-----|
| Vision LLM | OpenAI down → HOLDs infinitos | Fallback Claude | kill switch após N fallbacks ✅ |
| Superman CCXT | Exchange down → sem análise | Fallback chain HL→Bybit→Binance | ✅ |
| SQLite | Corrompido → sem persistência | Backups não automatizados | 🔴 Sem backup automático |
| Kill switch file | Deletado acidentalmente | env var alternativa | ✅ |
| Telegram bot | Token inválido → sem alertas | Graceful fail | ⚠️ Sem canal de fallback |

### 7.2 Recomendação crítica — Backup SQLite

```bash
# Adicionar ao crontab ou como scheduled task:
# Backup diário do banco de dados
0 1 * * * cp data/mekka_trading.db data/backups/mekka_trading_$(date +%Y%m%d).db

# Retention: manter 30 dias
find data/backups -name "*.db" -mtime +30 -delete
```

### 7.3 Chaos scenarios não testados

| Cenário | Status |
|---------|--------|
| CH-01: Vision timeout durante trade aberto | ✅ Testado (Story 150) |
| CH-02: Kill switch durante IronMan | ✅ Testado |
| CH-03: SQLite locked durante ciclo | 🔴 Não testado |
| CH-04: Telegram rate limit | 🔴 Não testado |
| CH-05: Clock skew (UTC drift) | 🔴 Não testado |
| CH-06: Hyperliquid maintenance (503) | ✅ Testado via fallback |
| CH-07: Memory leak após 100+ ciclos | 🔴 Não testado |

---

## 8. Métricas de Saúde do Sistema (Baseline)

Com base na arquitetura auditada, as métricas esperadas em paper trading saudável:

| Métrica | Target | Observação |
|---------|--------|-----------|
| Signal actionable rate | ≥ 50% | Sinais que passam do HOLD |
| Batman approval rate | ≥ 60% | Dos sinais actionable |
| Vision fallback rate | ≤ 10% | LLM sucesso > 90% |
| Cycle latency P95 | ≤ 10s | Por símbolo |
| Uptime sem incidente | ≥ 95% | Em janela de 30d |
| Wolverine ENDORSE rate | ≥ 70% | Gate H2 para mainnet |
| Win rate backtest | ≥ 45% | Deadpool READY verdict |
| Max drawdown (paper) | ≤ 15% | Deadpool threshold |
| Sharpe anualizado | ≥ 0.5 | Backtest simulado |

---

## 9. Resumo das Ações Recomendadas

### Ações imediatas (próxima sessão):

1. **Ativar CycleParallelBranch** — reduz latência de 18s para 6s em 3 símbolos
2. **Injetar Flash momentum no prompt Vision** — potencial impacto direto em qualidade de sinal
3. **Injetar debate_verdict estruturado no Vision** — aproveitar Milestone 39
4. **Timer visual no dashboard** — melhoria de UX simples
5. **Backup automatizado do SQLite** — risco de perda de dados

### Antes do Mainnet (obrigatório):

1. Criar carteira EVM dedicada e depositar capital mínimo
2. Substituir placeholders no .env
3. Executar `python3 scripts/preflight_mainnet.py` → verde
4. Assinar `docs/MAINNET-AUTHORIZATION.md`
5. Testar Telegram end-to-end
6. Confirmar parâmetros ultra-conservadores semana 1

### Milestone 40 completo antes de qualquer trade real:

```
Stories 244 → 245 → 246 → 247 → 248
Cada story = uma aula gravada = um gate verificado
Não pular etapas — cada gate existe por uma razão
```

---

## 10. Glossário dos Agentes

| Herói | Sigla | Layer | Responsabilidade resumida |
|-------|-------|-------|--------------------------|
| Superman | SM | L1 | OHLCV + indicadores técnicos |
| Doctor Strange | DS | L1 | Sentimento macro (news + F&G + BTC dom) |
| Black Panther | BP | L1 | Onchain: funding, OI, whale flow |
| Thor | TH | L1 | Volatilidade + regime + multiplier |
| Aquaman | AQ | L1 | Liquidez L2 + slippage |
| Spider-Man | SP | L1 | Anomalias e pausas |
| Flash | FL | L1.5 | Micro-momentum intracandle |
| Vision | VI | L2 | Decisão LLM (GPT-4o/Claude) |
| VisionCritic | VC | L2 | Second-look ENDORSE/AMEND/REJECT |
| VisionMoA | VM | L2 | Mixture-of-Agents (3 LLMs) |
| Professor X | PX | L2 | Swarm coordinator + debate |
| Batman | BM | L3 | Risk guardian determinístico |
| Iron Man | IM | L3 | Execução Hyperliquid |
| Wolverine | WL | L3 | Recovery monitor read-only |
| Nick Fury | NF | L4 | Mission commander |
| Deadpool | DP | Analytics | Performance analytics |
| Cyclops | CY | L4 | Kill-switch + SL/TP automático |

---

*Relatório gerado em 2026-05-18 · Claude Sonnet 4.6 via Cowork · Mekka Trading Story 243*  
*Próxima ação recomendada: Milestone 40 — Stories 244-248 (Live Trading Gate)*

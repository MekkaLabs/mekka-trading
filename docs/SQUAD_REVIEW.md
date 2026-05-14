# Mekka Trading — Squad Review Completo
**Data:** 2026-05-12  
**Revisor:** Squad Interno (NickFury Coordinator + Batman Risk Gate + Deadpool Analytics)  
**Versão:** Post-Story 044 · Pipeline: Foundation → Operator Control  

---

## Índice
1. [Visão Geral da Arquitetura](#1-visão-geral)
2. [Análise por Agente](#2-análise-por-agente)
3. [Falhas e Bugs Identificados](#3-falhas-e-bugs)
4. [Gaps Funcionais](#4-gaps-funcionais)
5. [Melhorias Recomendadas](#5-melhorias)
6. [Novos Agentes Sugeridos](#6-novos-agentes)
7. [Roadmap Prioritizado](#7-roadmap)

---

## 1. Visão Geral

O Mekka Trading é um sistema de trading algorítmico multi-agente com 3 camadas:

```
Layer 1 — Análise (ProfessorX coordena em paralelo)
  Superman       : OHLCV + indicadores técnicos (RSI, EMA, BB, MACD, ATR)
  DoctorStrange  : Sentimento (CryptoPanic, Fear&Greed, BTC Dominance)
  BlackPanther   : Onchain (funding rate, OI, whale signals via HL REST)
  Thor           : Volatilidade + regime (ATR-based, size multiplier)
  Aquaman        : Liquidez (L2 order book, slippage estimado)
  SpiderMan      : Detecção de anomalias (flash crashes, volume spikes)
  Flash          : Micro-momentum intra-candle (advisory, sem downstream)

Layer 2 — Decisão
  Vision         : LLM (GPT-4o) → TradingSignal
  VisionCritic   : LLM de segunda opinião (ENDORSE / AMEND / REJECT)

Layer 3 — Execução
  Batman         : Risk gate determinístico (sem LLM)
  IronMan        : Executor Hyperliquid (paper ou live)
  Wolverine      : Monitor de recuperação (read-only, 5min cycle)
  Deadpool       : Analytics de performance (determinístico, 30d window)
  PortfolioManager: Snapshot de equity e posições abertas
```

**Infraestrutura:**  
- Banco: SQLite via SQLAlchemy 2.x async (aiosqlite)  
- Servidor: aiohttp async na porta 8787  
- Notificações: Telegram (push + inbound commands)  
- Observabilidade: Audit log unificado + Prometheus text format  

---

## 2. Análise por Agente

### Superman ✅ Sólido
- OHLCV via CCXT com fallback para Binance/ByBit quando Hyperliquid indisponível  
- Indicadores corretos: RSI-14, EMA-20/50, BB, MACD, ATR-14  
- **Gap:** usa `candles_lookback=200` fixo; para timeframes curtos (1m/5m) isso é ~3h de dados — insuficiente para tendências de médio prazo

### Thor ✅ Sólido
- Regime de volatilidade bem calibrado (LOW/MEDIUM/HIGH/EXTREME → size multiplier)  
- **Gap:** thresholds hardcoded no arquivo (não em Settings) — dificulta ajuste sem deploy

### Aquaman ✅ Sólido
- L2 book da Hyperliquid com spread, profundidade e slippage estimado  
- `_DEPTH_BAND_PCT = 0.005` (0.5%) pode ser estreito demais em mercados thin

### DoctorStrange ⚠️ Frágil
- Depende de APIs externas gratuitas com SLA fraco (CryptoPanic free tier: 10 req/min)  
- `_TIMEOUT = 10s` por fonte; se todas as 3 derem timeout, o ciclo fica 30s parado  
- **Bug:** sem deduplicação de notícias — a mesma headline pode pontuar múltiplas vezes em ciclos próximos

### BlackPanther ⚠️ Parcialmente Implementado
- Funding rate e OI funcionam  
- `long/short_liquidations_24h` — a Hyperliquid não expõe liquidações diretamente; o campo é aproximado via clearinghouse state e pode ser zero sempre

### SpiderMan ✅ Sólido
- Detecção de anomalias via desvio-padrão de retornos  
- **Gap:** sem memória entre ciclos — um crash que dura > 4h não é "visto" como continuação

### Flash ⚠️ Advisory Dead-End
- Flash gera `MomentumSignal` que é passado ao Vision via prompt  
- **Bug de integração:** Flash recebe `recent_closes` do MarketData de Superman, mas se Superman retorna múltiplos timeframes, Flash usa apenas o primário — perde contexto de múltiplos TFs
- Vision recebe o sinal no prompt mas não há mecanismo de feedback sobre se Flash mudou alguma decisão

### Vision ⚠️ LLM Risk
- Fallback para HOLD em caso de falha — correto  
- **Risco:** `openai_temperature=0.2` é bom para determinismo, mas o prompt inclui `MarketAnalysis.build_prompt()` que pode ter >6000 tokens — risco de truncamento em modelos com context window reduzido
- `agents_consensus` na response baseia-se em `confidence >= threshold` mas o threshold vem de `runtime_settings.json` via `_confidence_threshold` — a VisionCritic não ciente disso e usa threshold fixo

### VisionCritic ✅ Bem Implementado
- Segunda opinião com `temperature=0.0` (mais conservador)  
- `vision_critic_min_disagreement=0.30` evita micro-overrides  
- **Gap:** VisionCritic não tem acesso ao MarketAnalysis completo — só vê o TradingSignal de Vision; perde contexto de liquidez e onchain

### Batman ✅ O Componente Mais Robusto
- Risk gate determinístico sem LLM  
- Kill switch por arquivo + env var  
- Múltiplos breakers: drawdown, max_open_positions, max_trades_per_day  
- **Gap:** não verifica correlação entre posições abertas (pode ter BTC LONG + ETH LONG = correlação altamente positiva, duplicando o risco real)

### IronMan ✅ Sólido em Paper / Não Testado em Live
- Paper: retorna PAPER status corretamente, persiste no DB  
- Live: retry com tenacity + exponential backoff  
- **Bug Crítico:** SL/TP bracket orders são marcados como `sl_order_id` e `tp_order_id` no banco, mas não há código que monitore se eles foram acionados — o sistema não sabe quando um trade foi fechado pela exchange

### Wolverine ⚠️ Parcialmente Funcional
- Produz `RecoveryPlan` com ações recomendadas (TIGHTEN_STOP, TRAIL_STOP, CLOSE, etc.)  
- **Bug Crítico:** As ações do RecoveryPlan são **APENAS LOG** — nunca são executadas. IronMan não consome o RecoveryPlan. O sistema monitora mas não age automaticamente
- Thresholds baseados em `equity used` (correto), mas equity_used = `notional / leverage` e o leverage vem do signal, não da posição atual real

### Deadpool ✅ Analítico Completo
- Sharpe, win-rate, drawdown, wolverine endorsement rate  
- `PerformanceVerdict` com thresholds READY/NOT_READY  
- **Gap:** janela de 30 dias fixos — em bootstrap (< 30 dias) é `INSUFFICIENT_DATA`, sem nenhum feedback útil

### PortfolioManager ⚠️ Leitura Inconsistente
- Em live: lê `clearinghouseState` da Hyperliquid  
- Em paper: retorna `paper_equity_usd` do settings (fixo, nunca atualizado com PnL real)  
- **Bug:** Após trades paper lucrativos/perdedores, a equity usada em cálculos de tamanho ainda é `paper_equity_usd=10000` original — não reflete o P&L acumulado

---

## 3. Falhas e Bugs

### 🔴 CRÍTICO

**[C1] Wolverine não executa — apenas loga**  
Arquivo: `src/agents/nick_fury.py` + `src/agents/wolverine.py`  
O `RecoveryPlan` com `EMERGENCY_CLOSE` ou `CLOSE` nunca chama IronMan.  
**Risco:** Posições em perda extrema não são fechadas automaticamente.  
**Fix:** Wiring Wolverine → IronMan no `run_monitor_cycle`.

**[C2] SL/TP bracket orders não são monitoradas**  
Arquivo: `src/agents/iron_man.py` + `src/persistence/models.py`  
`sl_order_id` e `tp_order_id` são salvos mas nunca verificados. Não há ciclo que detecte quando um SL/TP foi acionado na exchange e feche a posição no banco.  
**Risco:** DB sempre mostra posição aberta mesmo após SL disparar na exchange.

**[C3] Paper equity nunca atualiza com P&L acumulado**  
Arquivo: `src/agents/portfolio_manager.py`  
`paper_equity_usd=10000` é estático. Após 10 trades, o sistema ainda calcula size como 2% de $10,000 mesmo que a equity real (pelos trades) seja $8,000 ou $12,000.  
**Fix:** Calcular equity paper = `paper_equity_usd + sum(pnl_usd FROM trades WHERE is_paper=True)`.

### 🟡 ALTO

**[H1] DoctorStrange — deduplicação de notícias ausente**  
A mesma notícia pode ser processada em ciclos diferentes dentro de poucas horas, inflando artificialmente o score de sentimento.

**[H2] Flash → Vision — feedback loop ausente**  
`MomentumSignal.is_strong` não influencia se Vision aciona ou não o sinal. Flash é advisory mas não há métrica de quanto ele muda as decisões de Vision.

**[H3] VisionCritic sem contexto de mercado**  
Critic só vê o TradingSignal, não o MarketAnalysis. Um sinal de LONG em mercado de liquidez extremamente baixa (Aquaman score < 0.2) não seria criticado corretamente.

**[H4] `runtime_settings.json` super_aggressive bypass parcial**  
O threshold de confiança cai para 55% no analyze, mas VisionCritic ainda usa o threshold original de Settings. Um sinal com confiança 58% passaria o analyze mas poderia ser rejeitado pelo guardrail de consenso se VisionCritic disser 60%.

**[H5] ConsecutiveBreaker não persiste entre restarts**  
Arquivo: `src/services/breakers.py`  
O contador de erros consecutivos é in-memory. Se o servidor reiniciar após 2 erros, o breaker reseta. Com `max_consecutive_exec_errors=3`, um loop crash/restart pode acumular erros indefinidamente.

### 🟢 MÉDIO

**[M1] Flash usa só 1 timeframe**  
Usa `recent_closes` do timeframe primário (4h). Perda de contexto intra-candle real.

**[M2] SpiderMan sem memória entre ciclos**  
Anomalias de 4h+ não são rastreadas como continuação.

**[M3] BlackPanther liquidations proxy impreciso**  
Campo `long/short_liquidations_24h` raramente tem dados reais.

**[M4] `_market_cache` sem TTL cleanup**  
`self._market_cache` cresce indefinidamente. Com muitos símbolos e polling frequente, pode acumular centenas de MB em runs longos.

**[M5] `_rec_cache` max=20 pode causar expired rec_id**  
Se o operador espera >20 análises antes de executar, o rec_id expira silenciosamente.

---

## 4. Gaps Funcionais

| Gap | Impacto | Complexidade |
|-----|---------|-------------|
| Wolverine não executa RecoveryPlan | Alto | Médio |
| SL/TP monitor (bracket order tracker) | Alto | Alto |
| Paper equity dinâmica (P&L acumulado) | Alto | Baixo |
| Correlação entre posições abertas | Médio | Médio |
| Notificação Telegram de SL/TP acionado | Médio | Baixo |
| Deadpool sem feedback para Vision | Baixo | Alto |
| Flash multi-timeframe | Baixo | Médio |
| Backtesting framework real (Deadpool v2) | Alto | Alto |
| Liquidação automática em loss extremo | Alto | Alto |
| Order management (amend/cancel) | Alto | Alto |

---

## 5. Melhorias Recomendadas

### Imediatas (sem novo agente)

1. **Paper equity dinâmica**  
   Em `portfolio_manager.py`, calcular equity real = `paper_equity_usd + SUM(pnl_usd)` via query no banco.

2. **ConsecutiveBreaker persistente**  
   Salvar estado em `data/breaker_state.json` a cada incremento.

3. **Market cache cleanup**  
   Adicionar `asyncio.create_task(_market_cache_cleanup_loop())` que remove entradas com TTL vencido a cada 60s.

4. **Wolverine → IronMan wiring mínimo**  
   Quando `RecoveryAction.EMERGENCY_CLOSE`, criar um `ExecutionResult` sintético de fechamento e chamar `MekkaRepository.save_trade()`.

5. **VisionCritic recebe MarketAnalysis summary**  
   Adicionar ao prompt do Critic: liquidez (Aquaman score), volatilidade (Thor regime), onchain (BlackPanther whale signal).

6. **`_confidence_threshold` global via Settings**  
   Mover para Settings como `min_confidence_threshold` dinâmico; VisionCritic e analyze usam a mesma fonte.

### Médio Prazo

7. **SL/TP monitor background task**  
   Novo loop a cada 30s que checa os `sl_order_id`/`tp_order_id` pendentes via `Info.query_order_by_oid()` e fecha a posição no DB quando detectar fill.

8. **DoctorStrange deduplication**  
   Cache de headline hashes com TTL de 6h.

9. **Flash multi-timeframe momentum**  
   Passar também o timeframe de confirmação (1h) para Flash calcular concordância.

---

## 6. Novos Agentes Sugeridos

### 🆕 Cyclops — Order Manager & Position Tracker
**Prioridade: ALTA**

```
Papel    : Único agente responsável pelo lifecycle de ordens após execução
Camada   : Monitor (roda a cada 30s, entre os ciclos de Wolverine)
Input    : Lista de trades com sl_order_id / tp_order_id pendentes
Output   : OrderStatusUpdate (FILLED | CANCELLED | OPEN)
Ação     : Quando SL/TP filled → fecha posição no DB + loga + Telegram
Hard rules:
  - Read-only na exchange (apenas consulta, não cancela)
  - Se order_id inválido → marca como LOST + alerta
  - Nunca bloqueia outros ciclos (timeout 5s por ordem)
```

**Justificativa:** Sem Cyclops, o banco nunca sabe quando um SL foi acionado. É o gap mais crítico para o ciclo de vida completo de trades.

---

### 🆕 Gamora — Correlation Risk Monitor
**Prioridade: ALTA**

```
Papel    : Monitora correlação entre posições abertas e bloqueia concentração
Camada   : Pre-execution gate (roda antes de Batman)
Input    : Lista de posições abertas + novo sinal
Output   : CorrelationApproval (APPROVED | WARN | BLOCK)
Lógica   :
  - Calcula correlação de 30 dias entre ativos (retornos diários)
  - Se nova posição aumenta correlação média > 0.8 → WARN
  - Se todas as posições têm correlação > 0.85 → BLOCK (risco sistêmico)
  - BTC/ETH: correlação histórica ~0.85 (alta, mas tolerável isolada)
  - BTC + ETH + SOL + AVAX juntos: correlação média > 0.85 → BLOCK
Hard rules:
  - Usa dados históricos do banco (daily_pnl) ou CCXT
  - Nunca bloqueia quando há apenas 1 posição aberta
```

**Justificativa:** Com altcoins habilitadas, o sistema pode acumular múltiplas posições altamente correlacionadas, amplificando perdas em crashes sistêmicos.

---

### 🆕 Scarlet Witch — Macro Regime Detector
**Prioridade: MÉDIA**

```
Papel    : Classifica o regime macro de mercado e ajusta parâmetros globais
Camada   : Pre-analysis gate (roda 1x/dia ou quando BTC move > 5%)
Input    : Dados de 30 dias de preço BTC + DXY + SPY (opcional)
Output   : MacroRegime (BULL_RUN | BEAR_TRAP | SIDEWAYS | CAPITULATION | RECOVERY)
Ação     :
  BULL_RUN     → libera aggressive mode, aumenta max_leverage
  BEAR_TRAP    → força conservative mode, reduz max_position_size_pct
  CAPITULATION → engaja kill switch suave (sem novas entradas)
Hard rules:
  - Classificação determinística baseada em métricas (sem LLM)
  - Não pode override kill switch manual do operador
  - Log de toda mudança de regime com justificativa
```

**Justificativa:** Sem contexto macro, Vision pode operar agressivamente em bear markets. Scarlet Witch adiciona consciência do ciclo.

---

### 🆕 War Machine — Backup Executor
**Prioridade: MÉDIA**

```
Papel    : Fallback de execução quando IronMan falha repetidamente
Camada   : Execution layer (ativado automaticamente após N falhas de IronMan)
Input    : TradingSignal + RiskApproval (repassados por NickFury)
Output   : ExecutionResult (via caminho SDK alternativo)
Diferencial:
  - Usa ccxt.hyperliquid diretamente (IronMan usa SDK proprietário)
  - Timeout menor (3s vs 10s do IronMan) para situações de urgência
  - Apenas paper mode inicialmente
Hard rules:
  - Só ativa após ConsecutiveBreaker >= 2 falhas do IronMan
  - Não compete com IronMan — é mutex via asyncio.Lock
  - Sempre loga como WAR_MACHINE_EXEC no audit
```

**Justificativa:** Se o SDK Hyperliquid der problema, o sistema para completamente. War Machine garante continuidade via CCXT como path alternativo.

---

### 🆕 Captain Marvel — Signal Aggregator & Priority Queue
**Prioridade: BAIXA (médio prazo)**

```
Papel    : Agrega sinais de múltiplos símbolos e prioriza os melhores
Camada   : Entre ProfessorX e Vision
Input    : Lista de MarketAnalysis de todos os símbolos
Output   : Ranked list de oportunidades por score composto
Score    : f(confidence, liquidity, risk_reward, volatility_regime, momentum)
Hard rules:
  - Nunca gera sinais próprios — só ranqueia o que ProfessorX produziu
  - Se score do #1 < threshold mínimo → nenhum sinal passa (HOLD geral)
  - Respeita max_open_positions de Batman na priorização
```

**Justificativa:** Hoje Vision processa cada símbolo independentemente. Captain Marvel daria ao sistema consciência de "qual é a melhor oportunidade de todas as disponíveis agora".

---

### 🆕 Nick Fury Jr. — Mission Planner Tático (sub-ciclo 15min)
**Prioridade: BAIXA (longo prazo)**

```
Papel    : Versão mais rápida de NickFury para entradas táticas de curto prazo
Ciclo    : A cada 15min (vs 4h do NickFury principal)
Diferença:
  - Não chama VisionCritic (muito lento para 15min)
  - Usa apenas Superman (15m TF) + Flash + Batman
  - Batman tem threshold de confiança mais alto (0.80) para compensar menor análise
  - Só executa se NickFury principal sinalizou BULL
Hard rules:
  - Posição máxima: 50% do que Batman aprovaria no ciclo de 4h
  - Nunca abre posição oposta à posição aberta pelo ciclo de 4h
```

**Justificativa:** Aproveitar micro-oportunidades intra-candle sem a latência de uma análise completa de 4h.

---

## 7. Roadmap Prioritizado

### Sprint 1 — Bug Fixes Críticos (1-2 semanas)

| # | Item | Agente | Complexidade |
|---|------|--------|-------------|
| 1 | Paper equity dinâmica (soma P&L do banco) | PortfolioManager | Baixa |
| 2 | ConsecutiveBreaker persistente em JSON | Breakers | Baixa |
| 3 | Market cache cleanup loop | Server | Baixa |
| 4 | VisionCritic recebe contexto de Aquaman+Thor | VisionCritic | Média |
| 5 | `_confidence_threshold` unificado | Settings | Baixa |

### Sprint 2 — Novos Agentes Alta Prioridade (2-4 semanas)

| # | Agente | Impacto | Esforço |
|---|--------|---------|---------|
| 1 | Cyclops (Order Manager) | Crítico | Médio |
| 2 | Gamora (Correlation Monitor) | Alto | Médio |
| 3 | Wolverine → IronMan wiring | Alto | Médio |

### Sprint 3 — Regime e Resiliência (1-2 meses)

| # | Item | Impacto |
|---|------|---------|
| 1 | Scarlet Witch (Macro Regime) | Alto |
| 2 | War Machine (Backup Executor) | Médio |
| 3 | SL/TP monitor background task | Crítico |

### Sprint 4 — Evolução Estratégica (2-4 meses)

| # | Item | Impacto |
|---|------|---------|
| 1 | Captain Marvel (Signal Aggregator) | Alto |
| 2 | Nick Fury Jr. (15min sub-cycle) | Médio |
| 3 | Backtesting framework real (Deadpool v2) | Alto |
| 4 | Multi-exchange support (Bybit, OKX) | Médio |

---

## Sumário Executivo

O sistema está **arquiteturalmente sólido e bem estruturado**. A separação por agentes com responsabilidades claras, o audit log unificado e o double-gate para live trading mostram maturidade de design.

Os **3 bugs críticos** (Wolverine não executa, SL/TP sem monitor, equity paper estática) são os que mais limitam a confiabilidade em produção. Os 2 novos agentes de maior impacto são **Cyclops** (fechar o ciclo de vida de ordens) e **Gamora** (evitar concentração de risco em altcoins correlacionadas).

O painel de Live Trading com WebSocket da Hyperliquid e gráfico OHLC (Story 045) fecha o loop de observabilidade, permitindo acompanhar posições e o mercado em tempo real na interface do operador.

---

*Revisão conduzida pelo Squad interno via análise estática de código, revisão de models/contracts e simulação de fluxos de falha.*

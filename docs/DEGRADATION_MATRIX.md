# Matriz de Degradação por Dependência — Mekka Trading

> Story 139 — A4 do documento "Análise Crypto Squad".
> Cada linha desta matriz vira um teste de chaos engineering executável.
> Revisar quando nova dependência for adicionada ao pipeline.

---

## Dependências Críticas

### 1. OpenAI / LLM Provider

| Cenário | Comportamento do Sistema | Gate |
|---------|--------------------------|------|
| Latência alta (>5s) | Timeout agressivo, retorna HOLD | `LLMClient.timeout_s` |
| Falha isolada (<50% em janela) | Fallback Claude Sonnet (Story 125) | `vision_fallback_breaker` |
| Falha persistente (≥50% em janela) | DEGRADED_MODE: zero novas entradas | `llm_error_rate_breaker` |
| Indisponível >4h | DEGRADED_MODE + alerta Telegram CRITICAL | EventBus `agent.error` |
| Alucinação de formato | `_extract_json` fallback → HOLD | Vision parse handler |
| Rate limit 429 | Exponential backoff, HOLD neste ciclo | `LLMClient` retry |

**Ação em DEGRADED_MODE:** manter posições abertas com SL/TP existentes, Cyclops continua monitorando saídas, zero novas entradas. Recovery automático após `llm_recovery_cycles` ciclos sem erro.

---

### 2. Hyperliquid Exchange

| Cenário | Comportamento do Sistema | Gate |
|---------|--------------------------|------|
| Latência alta (200-2000ms) | Retry com backoff, warning log | `IronMan` timeout |
| Timeout de ordem | Ordem cancelada, HOLD posição atual | `IronMan` error handler |
| Conexão perdida temporariamente | Pause novas ordens, posições mantidas | `exec_error_breaker` |
| Circuit breaker da bolsa (halt) | Kill switch automático após N erros | `max_consecutive_exec_errors` |
| Feed WebSocket desconectado | Stale price detector dispara | `StalePriceDetector` |
| Liquidação inesperada | Wolverine detecta, alerta Telegram | `Wolverine.monitor_cycle` |

---

### 3. CryptoPanic / Sentiment Feed

| Cenário | Comportamento do Sistema | Gate |
|---------|--------------------------|------|
| Timeout / lento | DoctorStrange retorna `sentiment=None` | best-effort node |
| Indisponível | `sentiment=None`, analysis prossegue | best-effort node |
| Dados stale (cache velho) | Sentiment usado com peso reduzido | TTL no DoctorStrange |
| Indisponível longo | Alerta info, operação continua normal | log warning |

**Filosofia:** sentiment é best-effort. Indisponibilidade → `SentimentData=None` → Vision usa outros sinais.

---

### 4. Telegram Bot

| Cenário | Comportamento do Sistema | Gate |
|---------|--------------------------|------|
| HTTP timeout | Retry com jitter (DLQ) | `TelegramAlerter` DLQ |
| Token inválido / 401 | Log erro crítico, operação continua | `TelegramAlerter` error |
| Indisponível temporário | DLQ com retenção 24h | `DLQ` + retention |
| Indisponível longo (>24h) | Log crítico local, sistema opera sem alertas | log only |

**Impacto:** zero. Sistema opera normalmente sem Telegram. É canal de notificação, não gate de execução.

---

### 5. Feed de Preço / MarketData

| Cenário | Comportamento do Sistema | Gate |
|---------|--------------------------|------|
| Preço congelado (stale) | `StalePriceDetector` dispara, ciclo skipped | Story 138 |
| Preço outlier (flash crash) | Batman volume/volatility gates bloqueiam | Batman gate 3b/3c |
| OHLCV incompleto | Superman retorna chart parcial ou None | Superman error handler |
| Feed lento | Superman timeout → chart=None → CycleReport.error | Superman try/except |

---

### 6. OpenAI Embeddings (SemanticMemory)

| Cenário | Comportamento do Sistema | Gate |
|---------|--------------------------|------|
| API indisponível | `warm_up` retorna 0 entradas, `search` retorna [] | SemanticEpisodicStore fallback |
| Quota excedida | Fallback para AgentMemoryStore SQL | Story 128 fallback path |
| Embeddings corrompidos | Cosine similarity aleatória → resultados ruins | Silencioso (não crítico) |

**Impacto:** Vision usa SQL memory store como fallback. Decisões continuam sendo tomadas.

---

## Testes de Chaos Engineering

Execute manualmente antes de cada migração para capital real:

| ID | Dependência | Procedimento | Resultado esperado |
|----|-------------|--------------|-------------------|
| CH-01 | OpenAI | `export OPENAI_API_KEY=invalid && python run.py` | DEGRADED_MODE após `llm_error_rate_window` ciclos |
| CH-02 | Hyperliquid | Bloquear `api.hyperliquid.xyz` no `/etc/hosts` | `exec_error_breaker` trips → kill switch |
| CH-03 | Feed preço | Mockar Superman retornando mesmo preço N vezes | `StalePriceDetector` trips, ciclo skipped |
| CH-04 | Telegram | Revogar token Telegram | DLQ recebe mensagens, sistema opera normal |
| CH-05 | Restart | `kill -9 $(pgrep -f run.py)` durante ciclo ativo | Próximo boot recupera estado do LangGraph checkpoint |
| CH-06 | Drawdown | Simular -10% via `deadpool backtest --force-loss` | Trading para automaticamente |
| CH-07 | LLM rate limit | Mockar 429 em todas as calls | Backoff + HOLD, sem loop infinito |

---

## Limites Operacionais Configurados

```
max_daily_drawdown_pct:        10%   (Batman gate)
daily_profit_target_pct:       5%    (NickFury pause)
max_consecutive_losses:        3     (Batman gate 3a)
max_consecutive_exec_errors:   3     (kill switch)
max_consecutive_vision_fallbacks: 5  (kill switch)
llm_error_rate_threshold:      50%   (DEGRADED_MODE)
stale_price_window:            3     (skip cycle)
spread_max_multiplier:         3×    (skip trade)
```

---

*Documento criado em Story 139. Atualizar quando novas dependências forem adicionadas ou thresholds alterados.*

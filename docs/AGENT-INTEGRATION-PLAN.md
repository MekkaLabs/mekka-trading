# Plano de Melhoria de Integração entre Agentes

> **Status:** auditoria realizada em 2026-05-26 (sessão pós-batman refactor).
> Primeira camada de hardening (BaseAgent com timeout + telemetria) já implementada.

## Pontos fortes do estado atual

| # | O que já existe | Onde |
|---|----------------|------|
| 1 | Contratos Pydantic v2 em cada handoff | `src/models/*` |
| 2 | Layer 1 paralelo via `asyncio.gather` e fail-silent | `src/agents/professor_x.py` |
| 3 | `MarketAnalysis.is_safe_to_trade` curto-circuita antes de gastar LLM | `src/models/market_data.py` |
| 4 | Event bus pub/sub in-process desacoplado | `src/services/event_bus.py` |
| 5 | Episodic memory / win-rate por padrão | `src/persistence/agent_memory.py` |
| 6 | Circuit breakers (`_vision_fallback_breaker`, `_exec_error_breaker`, `_llm_error_breaker`) com sliding window | `src/agents/nick_fury.py` |
| 7 | BaseAgent mede `elapsed_ms` e loga | `src/agents/base.py` |

## Fragilidades identificadas

| Severidade | Fragilidade | Impacto |
|-----------|------------|---------|
| 🔴 Alta   | Sem timeouts por agente — chamada travada pode segurar ciclo inteiro | bloqueio |
| 🔴 Alta   | Sem retries automáticos — circuit breaker só BLOQUEIA, nunca retenta | falsos negativos |
| 🟠 Média  | VisionCritic falha silenciosamente — sinal original é mantido sem alerta | qualidade |
| 🟠 Média  | Erros silenciosos (Vision fallback, VisionCritic skipped) não chegam ao dashboard | observabilidade |
| 🟠 Média  | Layer 1 pode degradar até "só chart" sem rejeição — Vision toma decisão pobre | qualidade |
| 🟡 Baixa  | AgentMemoryStore escrita não-transacional — risco baixo em mono-loop | consistência |

## Fase 1 — JÁ IMPLEMENTADA nesta sessão

### 1.1 BaseAgent com timeout opcional + telemetria

`src/agents/base.py` agora aceita `timeout_s` no `__init__`. Quando setado:

- `run()` envolve `_run()` em `asyncio.wait_for`
- Timeout dispara `AgentTimeoutError` (subclass de `AgentError`)
- Todo `run()` publica evento no `MekkaEventBus`:
  - `agent.success` → `{codename, role, elapsed_ms}`
  - `agent.error`   → `{..., reason, error_type}`
  - `agent.timeout` → `{..., timeout_s}`
- Telemetria é fire-and-forget: nunca quebra o agente
- `_last_elapsed_ms` exposto para introspecção
- Retrocompatível — agentes existentes continuam funcionando sem mudança

## Fase 2 — A IMPLEMENTAR (próximas sessões)

### 2.1 Adotar timeouts nos agentes-chave (opt-in incremental)

Recomendação de orçamentos baseada nos perfis de I/O:

| Agente              | Layer | Timeout sugerido | Justificativa                       |
|---------------------|-------|------------------|-------------------------------------|
| Superman            | L1    | 30s              | Binance/Hyperliquid candles + TA    |
| Doctor Strange      | L1    | 30s              | Fear & Greed API + sentiment        |
| Black Panther       | L1    | 30s              | On-chain whales API                 |
| Thor / Aquaman      | L1    | 15s              | Cálculos locais + 1 chamada book    |
| Spider-Man          | L1    | 15s              | Computação local sobre candles      |
| Flash               | L1    | 10s              | Intra-candle, dados em cache        |
| Professor X         | L1.5  | 60s              | Coordena vários L1                  |
| Vision              | L2    | 45s              | LLM call (já tem fallback streak)   |
| VisionCritic        | L2    | 30s              | LLM call                            |
| Batman              | L3    | 15s              | Lógica local + DB queries           |
| IronMan             | L3    | 20s              | Order placement na exchange         |
| Cyclops             | L3    | 30s              | Position monitoring                 |

Aplicação: adicionar `timeout_s=N` em cada `super().__init__(...)`.

### 2.2 Retry com backoff em chamadas LLM

Adicionar wrapper em `LLMClient.chat()` com:
- Max 2 retries (3 tentativas no total)
- Backoff exponencial: 1s, 2s
- Apenas para erros retentáveis (timeout, 5xx, rate limit)
- Não retentar erros de schema/validação (são determinísticos)

### 2.3 Alerta de degradação silenciosa

Subscriber no event bus para `agent.error` e `agent.timeout`:
- Acumular contagem por agente em janela de 5min
- Se ≥ 3 erros do mesmo agente → publicar `degradation.detected`
- Dashboard renderiza banner âmbar com card do agente afetado
- Telegram alert nível WARNING

### 2.4 Validação de qualidade mínima de análise

No `ProfessorX._run`, após coletar Layer 1, validar:
- `chart` é obrigatório (já é hard-required pelo modelo)
- Pelo menos UMA fonte adicional disponível: `sentiment` OR `onchain` OR `volatility`
- Se só veio chart → marcar `analysis.metadata["degraded"] = True`
- Vision usa essa flag para ser mais conservador (size × 0.5, confidence cap 0.6)

### 2.5 VisionCritic com alerta de skip

Quando `vision_critic_enabled=True` mas o crítico falha:
- Publicar `agent.skipped` no event bus
- Anexar nota no `signal.metadata["critic_status"] = "skipped"`
- Dashboard mostra ícone de "sem revisão crítica" na recomendação

## Fase 3 — Estratégico (depende de capacidade)

### 3.1 Adaptive timeout tuning

Manter histórico de `_last_elapsed_ms` por agente. Calcular p95 nos últimos N runs.
Timeout efetivo = max(declared_timeout, p95 × 1.5). Salva ciclos em condições
degradadas sem sobre-rigor.

### 3.2 Transações na AgentMemoryStore

Envolver writes em `BEGIN TRANSACTION; ... COMMIT`. Risco baixo em mono-loop mas
necessário se Mekka rodar múltiplas réplicas no futuro.

### 3.3 Saga / compensação no fluxo execução

Hoje: Batman aprova → IronMan executa. Se IronMan falha após aprovar, o
estado de breakers fica "queimado" sem compensação. Padrão Saga: cada step
registra um "undo" — em rollback, IronMan dispara cancel + Cyclops marca
posição inexistente.

---

## Como medir sucesso

| Métrica                                       | Hoje    | Alvo Fase 2 |
|-----------------------------------------------|---------|-------------|
| Ciclos com agente travado > 60s               | ~3-5%   | < 0.5%      |
| Taxa de recuperação de erro LLM transitório   | 0%      | > 80%       |
| Visibilidade de degradação no dashboard       | parcial | completa    |
| Decisões Vision com análise incompleta        | aceita  | flagged     |

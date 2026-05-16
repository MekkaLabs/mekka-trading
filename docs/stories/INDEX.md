# Mekka Trading — Stories Index

Índice agrupado por milestone temático. Cada milestone fecha uma camada
arquitetural. Stories abaixo são lidas em ordem numérica dentro de cada
bloco.

Última story entregue: **172** (CycleEventLog SSE Dashboard Endpoint — streaming em tempo real do audit trail para o Live Trading Panel).
Stories 047–124 entregues e registradas no CHANGELOG.md (versões 0.2.0–0.8.0).

---

## Milestone 1 — Foundation
Estrutura inicial isolada do projeto, build TypeScript baseline, agentes
mock, mock connector Hyperliquid, observability mínima.

- [001 — Mekka Foundation](story-001-mekka-foundation.md)

## Milestone 2 — Megazord Runtime
Mission planner, squad router, runtime loop, expansão dos limites de
risco, position book, execution feedback loop.

- [002 — Megazord Runtime v1](story-002-megazord-runtime.md)

## Milestone 3 — Stress + Observability
Stress scenario packs, regime manager, observability completa com replay
de eventos e exchange capability validator.

- [003 — Stress Regime](story-003-stress-regime.md)
- [004 — Observability + Replay](story-004-observability-replay.md)
- [005 — Exchange Capability Validator](story-005-exchange-capability-validator.md)
- [006 — Mission Report Export](story-006-mission-report-export.md)
- [007 — Observability Integrity](story-007-observability-integrity.md)
- [008 — Integrity Verifier CLI](story-008-integrity-verifier-cli.md)
- [009 — Observability Health Check](story-009-observability-health-check.md)

## Milestone 4 — Alerting + DLQ
Dispatch de alertas, dedup, signed webhooks, retries com jitter, DLQ
replay e retention.

- [010 — Alert Dispatch Routing](story-010-alert-dispatch-routing.md)
- [011 — Alert Dedup Window](story-011-alert-dedup-window.md)
- [012 — Signed Webhook Retry](story-012-signed-webhook-retry.md)
- [013 — DLQ Jitter Retry](story-013-dlq-jitter-retry.md)
- [014 — DLQ Replay Retention](story-014-dlq-replay-retention.md)
- [015 — Health Retention + DLQ Backpressure](story-015-health-retention-and-dlq-backpressure.md)
- [016 — Replay Lock + Circuit Breaker](story-016-replay-lock-and-circuit-breaker.md)
- [017 — Operational Metrics Export](story-017-operational-metrics-export.md)

## Milestone 5 — Ops Governance
Trends, threshold alerting, suppression window, regime-aware severity,
Mission Commander routing, audit trail de delivery, KPIs e retention de
audit.

- [018 — Ops Trends + Lock Contention](story-018-ops-trends-and-lock-contention.md)
- [019 — Ops Threshold Alerting](story-019-ops-threshold-alerting.md)
- [020 — Ops Alert Suppression Window](story-020-ops-alert-suppression-window.md)
- [021 — Regime-Aware Ops Severity](story-021-regime-aware-ops-severity.md)
- [022 — Ops Mission Commander Routing](story-022-ops-mission-commander-routing.md)
- [023 — Ops Alert Delivery Audit Trail](story-023-ops-alert-delivery-audit-trail.md)
- [024 — Ops Alert Audit KPIs + Retention](story-024-ops-alert-audit-kpis-and-retention.md)

## Milestone 6 — Strategic Pipeline (Python)
Vision (cérebro GPT-4o), Batman (risk gate), Iron Man (Hyperliquid
execution paper-first), Professor X (swarm coordinator), Nick Fury
(Mission Commander), SQLite persistence.

- [025 — Strategic Pipeline](story-025-strategic-pipeline.md)

## Milestone 7 — Portfolio
Portfolio Manager — read-only equity & open-positions snapshot via
Hyperliquid clearinghouseState, com fallback paper.

- [026 — Portfolio Manager](story-026-portfolio-manager.md)

## Milestone 8 — Daily PnL + Hardening + Safety
Daily PnL writer fechando o ciclo de drawdown que Batman lê, contract
hardening uniforme, e a rede de segurança operacional (cap de capital
total + breakers consecutivos + kill switch script).

- [027 — Daily PnL Writer](story-027-daily-pnl-writer.md)
- [028 — Contract Hardening](story-028-contract-hardening.md)
- [029 — Safety Net](story-029-safety-net.md)

## Milestone 9 — Recovery + LLM Hardening
Wolverine como recovery agent + monitor cycle real, Vision Critic
opcional, audit log unificado TS↔Python.

- [030 — Wolverine Recovery Agent](story-030-wolverine.md)
- [031 — Vision Critic](story-031-vision-critic.md)
- [032 — Audit Single Source of Truth (Python reader)](story-032-audit-single-source.md)
- [032b — TS Audit Shim (SQLite Mirror)](story-032b-ts-audit-shim.md)

## Milestone 10 — Tactical + Simulation
Flash (sub-loop intra-candle), Deadpool (backtest replay), Telegram bot
rico.

- [033 — Flash](story-033-flash.md)
- [034 — Deadpool (Performance Analytics Agent)](story-034-deadpool.md)
- [035 — Telegram Alerter (push-only)](story-035-telegram-alerter.md)
- [035b — Telegram Inbound Commands](story-035b-telegram-inbound.md)

## Milestone 11 — Mainnet Readiness
Checklist formal, gate humano duplo (double-gate settings + preflight
script), template de autorização com assinatura humana obrigatória,
infra de gates H1–H6 com auto-check H2 via Deadpool e comandos Telegram.

- [036 — Mainnet Readiness](story-036-mainnet-readiness.md)
- [037 — Gate Infrastructure (H1–H6)](story-037-gate-infra.md)

## Milestone 12 — Dashboard + Analytics
Dashboard REST API completo, endpoint /api/performance, relatório diário
automático do Deadpool gravado no banco com audit trail.

- [038 — Dashboard /api/performance](story-038-dashboard-performance.md)
- [039 — DailyPerformanceWriter](story-039-daily-perf-writer.md)

## Milestone 13 — Operator UX

Dashboard v2 com navegação por páginas, topbar financeiro, blocos
personalizáveis e botão TradeNow com fluxo completo de análise de agentes,
confirmação e audit trail. Security fixes from squad reviews (Stories 040+).

- [040 — Dashboard v2: Pages, TopBar, Widgets, TradeNow](story-040-dashboard-v2.md)

---

## Como adicionar uma nova story

1. Criar `docs/stories/story-{NNN}-{slug-curto}.md` (ver story-026 como
   template).
2. Adicionar entrada nesse INDEX no milestone certo. Se a story
   inaugura uma camada nova, criar novo milestone.
3. Story deve ter: `Context · Goal · Scope Delivered · Hard Rules
   Mantidas · Pipeline End-to-End (se aplicável) · Acceptance ·
   What's Next · Files Changed`.
4. Não fechar a story sem `pytest -v` verde + `npm test` verde.

## Milestone 14 — Live Execution Pipeline

Fluxo TradeNow completo de ponta a ponta: cache de recomendações, Batman→IronMan
wired, paper e live mode funcionando. Prefs de widget persistidas no servidor.

- [041 — Broker Adapter: IronMan wired into TradeNow](story-041-broker-adapter.md)
- [042 — Widget Prefs: /api/prefs server-side](story-042-prefs-endpoint.md)
- [043 — Paper Trade Persistence & Positions Panel](story-043-paper-trade-persistence.md)

## Milestone 15 — Operator Control

Controle operacional manual: fechar posições individualmente, modos de risco
configuráveis (Super Agressivo / Altcoins) com toggles persistidos.

- [044 — Trading Modes, Close Position & Re-analyze](story-044-trading-modes-close-position.md)

## Milestone 16 — Exchange-Grade Monitoring

Painel Live Trading estilo exchange: gráfico candlestick (lightweight-charts) com preços
ao vivo via Hyperliquid WebSocket, posições abertas com PnL em tempo real, e revisão
arquitetural completa dos 15 agentes AIOS-Core com proposta de 6 novos agentes.

- [045 — Live Trading Panel + Squad Review](story-045-live-trading-panel.md)

## Milestone 17 — Bug Fixes Críticos + Multi-Exchange

Fecha os 3 bugs críticos do Squad Review: equity dinâmica [C3], Wolverine RecoveryPlan
execution [C1], e agente Cyclops SL/TP monitor [C2]. Adiciona Bybit/Binance como
exchanges alternativas via CCXT (configurável por env var).

- [046 — Equity Dinâmica, Wolverine Execution, Cyclops & Bybit Adapter](story-046-dynamic-equity-wolverine-cyclops-bybit.md)

---

## Milestone 18 — LLM Resilience + Python 3.14 + Operator UX (Stories 047–125)

Stories 047–124 cobertas no CHANGELOG.md versões 0.4.0–0.8.0:
operador UX (Telegram commands, gates avançados, leaderboard, heatmap),
memory episódica, risk gates 3d–3q, equity curve, Cyclops partial SL,
calendar heatmap, Pixel Office.

- [125 — LLM Fallback Claude, Superman Python 3.14, Telegram pt-BR, Pixel Office 2×2](story-125-llm-fallback-superman-py314.md)

## Milestone 19 — LangGraph Durable Execution (Stories 126–129)

LangGraph StateGraph envolvendo o ciclo NickFury com checkpoints SQLite,
interrupt/resume para aprovação Telegram durável, memória semântica episódica
e subgrafo paralelo Layer 1.

- [126 — LangGraph AsyncSqliteSaver: Durable Execution](story-126-langgraph-checkpointing.md)
- [127 — LangGraph Trade Approval: interrupt() + Command(resume=...)](story-127-lg-interrupt.md)
- [128 — Memória Episódica Semântica: SemanticEpisodicStore + text-embedding-3-small](story-128-semantic-memory.md)
- [129 — Layer 1 Parallel Subgraph: fan-out LangGraph com checkpoints por agente](story-129-layer1-subgraph.md)

## Milestone 20 — Decision Quality

Loop iterativo Vision↔VisionCritic (AutoGen Reflection) e Mixture of Agents com 3 LLMs
em paralelo sintetizados por um orchestrator (AutoGen MoA). Foco em diversidade de sinal
e redução de viés de modelo único.

- [130 — Iterative Vision Reflection: loop Vision↔VisionCritic até 3 rounds](story-130-vision-reflection.md)
- [131 — Mixture of Agents Vision: GPT-4o + Claude + GPT-4o-mini → orchestrator consenso](story-131-vision-moa.md)

## Milestone 21 — Memory Intelligence + Adaptive Routing + Observability

Composite scoring na memória episódica (semantic + recency + importance), dedup semântico,
pre-reasoning do Vision antes do sinal, routing adaptativo da Layer 1 por regime e
event bus in-process para observabilidade desacoplada.

Última story entregue: **136** (MekkaEventBus — pub/sub in-process).

- [132 — Memory Composite Scoring: semantic + recency_decay + importance](story-132-composite-scoring.md)
- [133 — Vision Pre-Reasoning: reflect antes de gerar TradingSignal (CrewAI Reasoning)](story-133-vision-pre-reasoning.md)
- [134 — Memory Consolidation: dedup semântico no add() e warm_up()](story-134-memory-consolidation.md)
- [135 — Adaptive Layer 1 Routing: skip agents por regime de mercado (Hierarchical Process)](story-135-adaptive-routing.md)
- [136 — MekkaEventBus: pub/sub in-process para observabilidade desacoplada](story-136-event-bus.md)

## Milestone 22 — Resilience II + Observability + Intelligence Gaps

DEGRADED_MODE formal (state machine NORMAL↔DEGRADED), snapshot fingerprinting,
custo de LLM via EventBus, prompt versioning, mock realism para testes de stress,
opportunity scanner e asset classifier com market regime detection.

Última story entregue: **146** (Asset Classifier + Market Regime Detection).

- [137 — Teste do Milhão: gate checklist completo antes de capital real](story-137-teste-do-milhao.md)
- [138 — Circuit Breaker Matrix Gaps: RateWindowBreaker + StalePriceDetector + SpreadBreaker](story-138-circuit-breakers.md)
- [139 — Degradation Matrix: doc de comportamento por dependência + chaos tests](story-139-degradation-matrix.md)
- [140 — DEGRADED_MODE Formal: state machine NORMAL↔DEGRADED + recovery automático](story-140-degraded-mode.md)
- [141 — MarketSnapshot snapshot_id: SHA-256 fingerprint no MarketAnalysis](story-141-snapshot-id.md)
- [142 — LLM Cost Metrics: evento llm.call.completed com tokens e custo](story-142-llm-cost-metrics.md)
- [143 — Prompt Versioning: SHA-256 hash de prompts no audit trail](story-143-prompt-versioning.md)
- [144 — Mock Realism IronMan: latência aleatória, partial fills, slippage extra](story-144-mock-realism.md)
- [145 — Opportunity Scanner: pré-scan de símbolos antes da análise profunda](story-145-opportunity-scanner.md)
- [146 — Asset Classifier + Market Regime: classificação cap tier + bull/bear/sideways/volatile](story-146-asset-classifier.md)

## Milestone 24 — Pipeline Integration: Connecting AI Framework Patterns into the Live Cycle

Conecta todos os serviços criados nas Stories 152–162 diretamente no _cycle_for_symbol do NickFury e no Vision,
fechando o ciclo entre construção e execução real.

Última story entregue: **167** (ContextWindowTracker NickFury Integration).

- [163 — Signal Metadata Pipeline: NickFury auto-inject market_regime + cap_tier antes do Batman](story-163-signal-metadata-pipeline.md)
- [164 — Vision MicroagentRegistry + RepoMap Injection: regime-aware prompt + compact agent map no Vision](story-164-vision-context-injection.md)
- [165 — CycleEventLog NickFury Integration: CYCLE_START/ANALYSIS_DONE/SIGNAL_EMITTED/RISK_VERDICT/EXECUTION_DONE/CYCLE_END](story-165-cycle-event-log-integration.md)
- [166 — AgentStepGuard NickFury Integration: stuck loop detection + graceful abort após Vision e Batman](story-166-step-guard-integration.md)
- [167 — SignalChangeLog + ContextWindowTracker NickFury Integration: diff audit trail + token tracking por ciclo](story-167-changelog-cwt-integration.md)

## Milestone 25 — Pipeline Integration Wave 2: Validation, Compression & Observability Live

Completa a integração dos serviços restantes de AI Framework Patterns no pipeline vivo:
SignalValidator bloqueia sinais inválidos antes do Batman, BoundedOutput e ChatHistoryCompressor
protegem o contexto do Vision contra overflow, ObservabilityPlugin expõe todo o telemetry via
MekkaKernel function calling, e o endpoint SSE entrega o CycleEventLog em tempo real para o
Live Trading Panel.

Última story entregue: **172** (CycleEventLog SSE Dashboard Endpoint).

- [168 — SignalValidator NickFury Integration: valida sinal antes do Batman, retorna CycleReport(error=...) se inválido](story-168-signal-validator-integration.md)
- [169 — BoundedOutput Vision Integration: truncate_str(12k) no prompt de análise + bound_prompt_section(3k) no bloco de memória](story-169-bounded-output-vision.md)
- [170 — ChatHistoryCompressor Vision Integration: compress antes do LLM call quando CWT reporta near-limit](story-170-chat-compressor-vision.md)
- [171 — ObservabilityPlugin MekkaKernel Integration: 5 @mekka_function expondo CycleEventLog/SignalChangeLog/CWT/StepGuard/Validator](story-171-observability-plugin.md)
- [172 — CycleEventLog SSE Dashboard Endpoint: GET /api/events/stream com Server-Sent Events para Live Trading Panel](story-172-sse-endpoint.md)

## Milestone 23 — Cost Intelligence + Regime-Aware Gates + Chaos Validation + AI Framework Patterns

LLM Cost Dashboard com agregações em memória e endpoint HTTP, integração do
MarketRegimeDetector e AssetClassifier no Batman (gates 5b e 5c), testes de
chaos engineering automatizados (CH-01–CH-07), benchmarks de latência
end-to-end com alertas de ciclos lentos, e padrões de dois frameworks líderes:

- **Microsoft Semantic Kernel**: filter chain (InvocationFilter) + plugin registry
  com decorator @mekka_function gerando OpenAI function calling schema
- **OpenHands (OpenDevin)**: append-only CycleEventLog (event sourcing), AgentStepGuard
  (MAX_ITERATIONS + stuck loop detection) e MicroagentRegistry (regime-aware Markdown prompts)
- **SWE-agent**: BoundedOutput (ACI output limiter — truncação explícita de strings/listas/dicts),
  SignalValidator (linter-on-edit pré-Batman — geometria SL/TP, R:R, leverage), ContextWindowTracker
  (token usage por estágio + alertas 80% + compress_history last_n_observations)
- **Aider (Aider-AI/aider)**: MekkaRepoMap (compact symbol index sem tree-sitter — scan regex,
  to_prompt_section() para Vision), ChatHistoryCompressor (compressão estrutural de prompt history
  quando >80% context window), SignalChangeLog (SEARCH/REPLACE diff entre signals + auto-commit message)

Última story entregue: **162** (SignalChangeLog — Aider auto-commit + SEARCH/REPLACE diff pattern).

- [147 — LLM Cost Dashboard: subscriber llm.call.completed + GET /api/cost](story-147-llm-cost-dashboard.md)
- [148 — MarketRegime Integration Batman: gate 5b BEAR/VOLATILE leverage+size adjustments](story-148-batman-market-regime.md)
- [149 — Asset Classifier Integration Batman: gate 5c SMALL/MID/LARGE_CAP leverage caps](story-149-batman-asset-classifier.md)
- [150 — Chaos Engineering Tests: CH-01 a CH-07 automatizados com mocks](story-150-chaos-engineering.md)
- [151 — Performance Benchmarks: latência p50/p95/p99 por estágio + GET /api/benchmarks](story-151-performance-benchmarks.md)
- [152 — Mekka Kernel Filter Chain: SK-style InvocationFilter + AuditLog/Retry/CircuitBreaker/EventPublish](story-152-invocation-filter.md)
- [153 — @mekka_function + MekkaPlugin Registry: decorator SK-inspired + MekkaKernel OpenAI tool calling](story-153-mekka-kernel.md)
- [154 — CycleEventLog: append-only event sourcing do ciclo (OpenHands EventLog pattern)](story-154-cycle-event-log.md)
- [155 — AgentStepGuard: MAX_ITERATIONS + stuck loop detection + graceful recovery (OpenHands PR #5500)](story-155-agent-step-guard.md)
- [156 — MicroagentRegistry: regime-aware prompts via Markdown microagents (OpenHands microagent system)](story-156-microagent-registry.md)
- [157 — BoundedOutput: ACI output limiter SWE-agent — truncate_str/list/dict/output, format_observation, last_n_observations](story-157-bounded-output.md)
- [158 — SignalValidator: linter-on-edit pré-Batman — geometria SL/TP/entry, R:R mínimo, leverage, confidence, reasoning](story-158-signal-validator.md)
- [159 — ContextWindowTracker: token usage por estágio pipeline + alertas 80% + compress_history (SWE-agent ContextWindowManager)](story-159-context-window-tracker.md)
- [160 — MekkaRepoMap: compact symbol index sem tree-sitter — scan regex, to_prompt_section() para Vision (Aider repomap.py)](story-160-repo-map.md)
- [161 — ChatHistoryCompressor: compressão estrutural de prompt history quando >80% context window (Aider history.py)](story-161-chat-history-compressor.md)
- [162 — SignalChangeLog: SEARCH/REPLACE diff entre TradingSignals consecutivos + auto-commit message (Aider editblock_coder + commands)](story-162-signal-changelog.md)

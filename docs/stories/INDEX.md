# Mekka Trading — Stories Index

Índice agrupado por milestone temático. Cada milestone fecha uma camada
arquitetural. Stories abaixo são lidas em ordem numérica dentro de cada
bloco.

Última story entregue: **251** (Cycle Checkpoint — persistência e retomada de `MarketAnalysis` (ProfessorX) + `TradingSignal` (Vision) por `cycle_id`, evitando recomputar etapas após crash/restart).
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

## Milestone 26 — Observability Live & Kernel Orchestration

Frontend conectado ao stream SSE, VisionPlugin integrado ao MekkaKernel com pre-invocation hook
disparando o filter chain antes de cada chamada Vision, endpoint widget `/api/obs/{tool_name}`
para dashboard sem acoplamento direto, alerta Telegram em sinais inválidos, e endpoint live
de uso de context window com ranking de ciclos críticos.

Última story entregue: **177** (ContextWindowTracker Dashboard Endpoint).

- [173 — Live Trading Panel SSE Integration: subscribeCycleEvents() via EventSource API + mock fallback](story-173-sse-frontend.md)
- [174 — MekkaKernel NickFury Orchestration: VisionPlugin com generate_signal/get_last_signal/get_vision_metrics + pre-invocation hook](story-174-vision-kernel.md)
- [175 — ObservabilityPlugin Dashboard Widget: GET /api/obs/{tool_name} despachando para obs/vision plugins](story-175-obs-widget.md)
- [176 — SignalValidator Telegram Alert: alerta Telegram quando sinal inválido com action/confidence/error_summary](story-176-validator-telegram.md)
- [177 — ContextWindowTracker Dashboard Endpoint: GET /api/context-window/live com summaries, usage_pct e is_near_limit](story-177-cwt-live.md)

## Milestone 28 — MetaGPT Patterns: Working Memory, Typed Messages, SOP, Long-Term Memory, Incremental Skip

Cinco padrões do framework FoundationAgents/MetaGPT mapeados para o pipeline Mekka Trading:
RoleWorkingMemory mantém janela deslizante de ciclos anteriores por símbolo e injeta no prompt
Vision (MetaGPT RoleContext.rc.memory), TypedCycleMessage envolve outputs de cada estágio com
metadados de roteamento explícitos (MetaGPT Message cause_by/send_to), CycleSOP declara o pipeline
formalmente com agentes e condições de skip (MetaGPT SOP), SignalOutcomeMemory armazena outcomes com
busca por similaridade regime+action (MetaGPT LongTermMemory), e IncrementalCycleSkip poupa a LLM call
do Vision quando preço/regime não mudaram materialmente (MetaGPT Incremental Development).

Última story entregue: **187** (IncrementalCycleSkip).

- [183 — RoleWorkingMemory Vision Integration: sliding window de ciclos + prompt block "recent trade history" (MetaGPT rc.memory)](story-183-role-working-memory.md)
- [184 — TypedCycleMessage NickFury: CycleMessage Pydantic com stage/sender/recipients/payload (MetaGPT Message routing)](story-184-typed-cycle-message.md)
- [185 — CycleSOP Dashboard: especificação declarativa de 9 estágios + GET /api/cycle-sop (MetaGPT SOP)](story-185-cycle-sop.md)
- [186 — SignalOutcomeMemory Vision Integration: similarity search regime+action + prompt block "past performance" (MetaGPT LongTermMemory)](story-186-signal-outcome-memory.md)
- [187 — IncrementalCycleSkip NickFury: skip Vision LLM call quando preço/regime estáveis + GET /api/incremental-guard (MetaGPT Incremental)](story-187-incremental-cycle-skip.md)

## Milestone 35 — Backtesting Engine: SignalLoader, OutcomeSimulator, EquityCurve, MetricsEngine, BacktestRunner + CLI

Pipeline completo de backtesting sobre sinais históricos do banco: BacktestSignalLoader lê sinais e trades
reais do SQLite via MekkaRepository e constrói BacktestTrade com outcome=WIN/LOSS já preenchido para trades
reais, BacktestOutcomeSimulator usa modelo probabilístico (`p_win = clip(0.45 × min(rr/2, 1.5) × (0.70 + conf×0.60), 0.10, 0.90)`)
para simular outcomes de sinais sem trade correspondente, BacktestEquityCurve constrói a curva de equity
cronológica com drawdown ponto a ponto, BacktestMetricsEngine computa o conjunto completo de métricas
(win_rate, profit_factor, expectancy, Sharpe/Sortino anualizado, max_drawdown, avg_rr, days_covered),
e BacktestRunner orquestra o pipeline inteiro retornando BacktestSummary com relatório Markdown via CLI.

Última story entregue: **243** (DebateModerator → integração Vision pipeline).

- [219 — BacktestTrade model + BacktestSignalLoader: Pydantic models (BacktestTrade, EquityPoint, BacktestMetrics, BacktestSummary) + loader assíncrono do DB](story-219-backtest-signal-loader.md)
- [220 — BacktestOutcomeSimulator: simula WIN/LOSS por geometria SL/TP + modelo probabilístico R:R × confiança, seed reproduzível](story-220-backtest-outcome-simulator.md)
- [221 — BacktestEquityCurve: curva de equity cronológica + drawdown_pct ponto a ponto, ponto inicial START, floor em 0](story-221-backtest-equity-curve.md)
- [222 — BacktestMetricsEngine: Sharpe/Sortino anualizado, profit_factor, win_rate, max_drawdown USD/%, expectancy, avg_rr, days_covered](story-222-backtest-metrics-engine.md)
- [223 — BacktestRunner + CLI: orquestra pipeline completo → BacktestSummary + relatório Markdown + `python -m src.backtest run --symbol BTC --days 30`](story-223-backtest-runner-cli.md)

## Milestone 36 — Backtesting Dashboard (Stories 224-228)

POST /api/backtest/run + GET /api/backtest/result + GET /api/backtest/history. BacktestBenchmark compara
estratégia vs BTC buy-hold. BacktestTelegramReport envia relatório Markdown após cada run. BacktestScheduler
executa daily às 00h UTC e mantém histórico de 30 runs em memória. Dashboard: página "Backtest" com 8 cards
de métricas, equity curve interativa (Chart.js), drawdown chart e benchmark comparison row.

- [224 — BacktestAPI: POST /api/backtest/run + GET /api/backtest/result + helper _backtest_summary_to_dict](story-224-backtest-api.md)
- [225 — BacktestPanel: página "backtest" no dashboard — 8 metric cards + equity curve + drawdown chart + benchmark row (Chart.js)](story-225-backtest-panel.md)
- [226 — BacktestBenchmark: buy-and-hold do símbolo no mesmo período; compara retorno vs estratégia e calcula alfa](story-226-backtest-benchmark.md)
- [227 — BacktestTelegramReport: relatório Markdown compacto (capital, WR, Sharpe, MaxDD, alfa vs benchmark) via TelegramAlerter](story-227-backtest-telegram-report.md)
- [228 — BacktestScheduler: background task diário às 00h UTC; histórico de 30 runs; GET /api/backtest/history](story-228-backtest-scheduler.md)

## Milestone 37 — Live Performance Tracking (Stories 229-233)

RollingMetricsService computa Sharpe/win_rate/expectancy/maxDD rolling. PerformanceTracker compara real vs
backtest. DivergenceAlerter categoriza divergências em LOW/MEDIUM/HIGH com recomendações acionáveis.
Dashboard: página "Analytics" com painel de métricas rolling + caixa de alertas de divergência.

- [229 — PerformanceTracker: snapshot comparativo real vs backtest (PerformanceSnapshot Pydantic)](story-229-performance-tracker.md)
- [230 — RollingMetricsService: Sharpe anualizado, win_rate, expectancy, maxDD rolling de trades do DB](story-230-rolling-metrics-service.md)
- [231 — DivergenceAlerter: LOW/MEDIUM/HIGH com recomendação por categoria (drawdown/win_rate/sharpe)](story-231-divergence-alerter.md)
- [232 — GET /api/performance/rolling: métricas rolling + Δ vs backtest em cache](story-232-perf-rolling-endpoint.md)
- [233 — GET /api/performance/divergence: relatório JSON de divergências real vs simulado](story-233-perf-divergence-endpoint.md)

## Milestone 38 — Risk Dashboard Avançado (Stories 234-238)

Três novos endpoints de risco: Batman verdicts timeline (APPROVED/REDUCED/REJECTED por dia, Chart.js stacked bar),
regime heatmap (ciclos por regime × hora UTC), concentration heatmap (% capital por símbolo, doughnut chart).
Dashboard: seções batman-timeline e concentration na página "Analytics".

- [234 — (reservada — equity curve interativa enhancements futuros)](story-234-equity-curve-interactive.md)
- [235 — GET /api/risk/batman-timeline: timeline de verdicts Batman — chart stacked + tabela últimos 20](story-235-batman-timeline.md)
- [236 — GET /api/risk/regime-heatmap: contagem ciclos por regime × hora UTC em janela configurável](story-236-regime-heatmap.md)
- [237 — (reservada — Deadpool analytics panel)](story-237-deadpool-analytics.md)
- [238 — GET /api/risk/concentration: % capital por símbolo + doughnut chart + trade count + PnL por símbolo](story-238-concentration-heatmap.md)

## Milestone 39 — Multiagent Debate (Stories 239-243)

DebateModerator (L1.5): coordena N rodadas de debate entre agentes L1 antes do Vision. ConsensusWeighter:
agrega votos ponderados por confiança × rodada (round_multiplier 1.0→1.2×). DebateVerdictLogger: persiste
no audit_log com vote_table. Integração no ProfessorX: settings.debate_enabled (default False),
MarketAnalysis.debate_verdict, fire-and-forget log. Dashboard: painel Debate com run on-demand + histórico.
POST /api/debate/run + GET /api/debate/history.

- [239 — DebateModerator: coordena debate L1.5 — max_rounds, consensus_threshold, heurísticas por especialidade de agente](story-239-debate-moderator.md)
- [240 — AgentDebateRound: protocolo de coleta de votos em paralelo com timeout por agente](story-240-agent-debate-round.md)
- [241 — ConsensusWeighter: agrega votos ponderados confiança × round_multiplier, detecta dissidentes](story-241-consensus-weighter.md)
- [242 — DebateVerdictLogger: persiste DebateVerdict no audit_log + fetch_recent para histórico](story-242-debate-verdict-logger.md)
- [243 — Integração ProfessorX: settings.debate_enabled + MarketAnalysis.debate_verdict + POST /api/debate/run + GET /api/debate/history](story-243-debate-integration.md)

## Milestone 40 — Agent Communication Upgrade (Stories 244-251)

Fechamento do loop “sinais auxiliares → comportamento do Vision → enforcement do Batman” e
upgrade de confiabilidade do pipeline (structured output + checkpoints), adicionando:

- Integração explícita Flash→Vision (guidance comportamental) e debate_verdict→Vision.
- Gate soft do Batman para divergência de momentum (redução automática de size).
- Novo agente **Beast** (read-only) para auditoria contínua e recomendações de melhoria.
- **DecisionMemory** e **CycleCheckpoint** persistindo artefatos de decisão no audit log.
- **Vision structured output** (Pydantic-first) com fallback seguro para o path clássico.

Última story entregue: **251** (Cycle Checkpoint).

- [244 — Flash → Vision Integration](story-244-flash-vision-integration.md)
- [245 — Debate Verdict → Vision Integration](story-245-debate-verdict-vision.md)
- [247 — Batman Gate 3r: Flash Momentum Divergence](story-247-batman-gate-3r-flash-divergence.md)
- [248 — Beast: Continuous System Improvement Agent](story-248-beast-agent.md)
- [249 — Decision Memory](story-249-decision-memory.md)
- [250 — Vision Structured Output](story-250-vision-structured-output.md)
- [251 — Cycle Checkpoint](story-251-cycle-checkpoint.md)

## Milestone 34 — Monitoring & Alerting: DrawdownMonitor, PositionConcentrationAlerter, IntradayPnLTracker, FundingRateMonitor, AlertThrottleManager

Cinco serviços de monitoramento e alertas Telegram ricos para o operador:
DrawdownMonitor dispara alertas escalonados em 3 níveis (WARNING/CRITICAL/KILL) conforme drawdown intraday
progride em relação ao limite diário configurado, PositionConcentrationAlerter monitora quando uma posição
individual excede o percentual máximo da equity após abertura, IntradayPnLTracker mantém snapshots horários
de P&L realizado e não-realizado e dispara alertas em marcos configuráveis (+3%/+5% ganho, -2%/-5% perda),
FundingRateMonitor monitora proativamente taxas de funding extremas independente de trades ativos e alerta
em níveis WARN e BLOCK reutilizando os thresholds do Batman, e AlertThrottleManager centraliza o dedup/throttle
de todos os alertas com cooldowns configuráveis por tipo de evento para prevenir fadiga do operador.

Última story entregue: **217** (AlertThrottleManager).

- [213 — DrawdownMonitor: alertas escalonados WARNING/CRITICAL/KILL em 50%/80%/100% do limite diário, dedup por nível](story-213-drawdown-monitor.md)
- [214 — PositionConcentrationAlerter: alerta quando posição individual excede max_concentration_pct da equity, dedup por símbolo](story-214-position-concentration-alerter.md)
- [215 — IntradayPnLTracker: snapshots horários de P&L realizado+não-realizado, alertas em marcos +3%/+5%/+10% e -2%/-5%](story-215-intraday-pnl-tracker.md)
- [216 — FundingRateMonitor: alertas proativos de funding extremo (WARN/BLOCK) reutilizando thresholds do Batman](story-216-funding-rate-monitor.md)
- [217 — AlertThrottleManager: gateway centralizado de dedup e throttle, cooldowns por evento, métricas de supressão](story-217-alert-throttle-manager.md)
- [218 — Monitor Wiring: integração dos 4 monitores + AlertThrottleManager ao NickFury.__init__ e run_main_cycle()](story-218-monitor-wiring-nick-fury.md)

## Milestone 33 — LangGraph Patterns: StateGraph, ConditionalRouter, Checkpointer, ParallelBranch, GraphInterrupt

Cinco padrões do framework LangGraph (LangChain AI) mapeados para o pipeline Mekka Trading:
CycleStateGraph + CycleCompiledGraph replicam o StateGraph/CompiledGraph do LangGraph com nós tipados,
arestas fixas e condicionais, e guard de max_steps (LangGraph StateGraph.compile()), CycleConditionalRouter
implementa roteamento por regras priorizadas com operadores EQ/NEQ/GT/LT/IN/CONTAINS/TRUTHY/FALSY e
avaliação de dotted-path no estado do ciclo (LangGraph conditional_edges), CycleGraphCheckpointer persiste
snapshots do estado após cada nó com FIFO eviction por thread e suporte a time-travel replay (LangGraph
MemorySaver/checkpointer), CycleParallelBranch executa análises multi-símbolo em paralelo via
ThreadPoolExecutor + asyncio.gather com fan-in por MAX_CONFIDENCE/MAJORITY_VOTE/ALL (LangGraph Send() API),
e CycleGraphInterrupt implementa pause/resume Human-in-the-Loop com estados PENDING/APPROVED/REJECTED/
TIMEOUT/SKIPPED e on_timeout configurável (LangGraph interrupt()/Command(resume=...)).

Última story entregue: **212** (CycleGraphInterrupt).

- [208 — CycleStateGraph + CycleCompiledGraph NickFury: typed state dict fluindo por nós com arestas fixas e condicionais, guard max_steps (LangGraph StateGraph)](story-208-cycle-state-graph.md)
- [209 — CycleConditionalRouter NickFury: roteamento por regras priorizadas com RouterCondition + RouterRule, dotted-path evaluation (LangGraph conditional_edges)](story-209-cycle-conditional-router.md)
- [210 — CycleGraphCheckpointer NickFury: snapshots de estado após cada nó, FIFO eviction, time-travel replay (LangGraph MemorySaver)](story-210-cycle-graph-checkpointer.md)
- [211 — CycleParallelBranch NickFury: fan-out/fan-in multi-símbolo com ThreadPoolExecutor + asyncio.gather, estratégias MAX_CONFIDENCE/MAJORITY_VOTE/ALL (LangGraph Send())](story-211-cycle-parallel-branch.md)
- [212 — CycleGraphInterrupt NickFury: pause/resume Human-in-the-Loop com timeout e on_timeout configurável, estados PENDING/APPROVED/REJECTED/TIMEOUT/SKIPPED (LangGraph interrupt)](story-212-cycle-graph-interrupt.md)

## Milestone 32 — AutoGen / CrewAI Patterns: GroupChat, ConversationSession, TaskDefinition, PipelineOrchestrator, AgentBackstory

Cinco padrões dos frameworks AutoGen (Microsoft) e CrewAI mapeados para o pipeline Mekka Trading:
CycleGroupChat + CycleGroupChatManager replicam o AutoGen GroupChat com seleção de speaker ROUND_ROBIN/
RANDOM/CUSTOM e consenso por maioria de votos LONG/SHORT/HOLD entre agentes participantes (AutoGen
GroupChat+GroupChatManager), MekkaConversationSession implementa o padrão AutoGen
ConversableAgent.initiate_chat() com max_turns, is_termination_msg callback, summary_method e carryover
para sessões estruturadas entre pares de agentes (AutoGen ConversableAgent.initiate_chat()),
CycleTaskDefinition define tarefas declarativas com expected_output, validator_fn e context chaining
entre stages (CrewAI Task+expected_output), CyclePipelineOrchestrator executa pipelines SEQUENTIAL e
HIERARCHICAL com skip automático do estágio IRONMAN quando action=HOLD no modo hierárquico (CrewAI
Process+Crew.kickoff()), e MekkaAgentBackstory registra role + goal + backstory + performance notes de
cada agente (NICKFURY/VISION/BATMAN/IRONMAN) e injeta um system prompt enriquecido no LLM call do Vision
com notas adaptativas de performance (CrewAI Agent.backstory).

Última story entregue: **207** (MekkaAgentBackstory).

- [203 — CycleGroupChat + CycleGroupChatManager NickFury: roundtable multi-agente com consenso LONG/SHORT/HOLD (AutoGen GroupChat)](story-203-cycle-group-chat.md)
- [204 — MekkaConversationSession NickFury: sessões estruturadas entre pares de agentes com termination callback e carryover (AutoGen initiate_chat)](story-204-mekka-conversation-session.md)
- [205 — CycleTaskDefinition NickFury: tarefas declarativas com expected_output, validator_fn e context chaining (CrewAI Task)](story-205-cycle-task-definition.md)
- [206 — CyclePipelineOrchestrator NickFury: pipeline SEQUENTIAL/HIERARCHICAL com skip IRONMAN em HOLD (CrewAI Process+Crew.kickoff)](story-206-cycle-pipeline-orchestrator.md)
- [207 — MekkaAgentBackstory Vision + NickFury: backstory adaptativo injetado no system prompt com performance notes (CrewAI Agent.backstory)](story-207-mekka-agent-backstory.md)

## Milestone 31 — OpenHands Patterns Wave 2: Conversation Memory, Condensation Engine, Artifact Store, Action Risk Analyzer, State Resetter

Cinco padrões novos do framework OpenHands/OpenHands (não cobertos pelo Milestone 30) mapeados
para o pipeline Mekka Trading: CycleConversationMemory centraliza o histórico de janela de
contexto por símbolo com build_messages() respeitando token budget (OpenHands ConversationMemory),
CycleCondensationEngine emite CondensationRecord quando o uso da context window excede o threshold
e aplica estratégia HALVE ou SUMMARIZE (OpenHands Condenser/CondensationAction), CycleArtifactStore
guarda artefatos de ciclo em memória com interface put/get/list/delete e path canônico symbol/cycle/type
(OpenHands InMemoryFileStore), CycleActionRiskAnalyzer classifica cada ação do pipeline em LOW/MEDIUM/HIGH
com escalada por notional, alavancagem e regime VOLATILE (OpenHands SecurityAnalyzer LLM risk), e
CycleStateResetter executa reset coordenado fail-silent de todos os singletons de estado efêmero
entre ciclos, preservando logs de auditoria (OpenHands AgentController.reset()).

Última story entregue: **202** (CycleStateResetter).

- [198 — CycleConversationMemory Vision + NickFury: histórico de janela de contexto por símbolo com token budget (OpenHands ConversationMemory)](story-198-cycle-conversation-memory.md)
- [199 — CycleCondensationEngine Vision: condensação de histórico por threshold + CondensationRecord (OpenHands Condenser)](story-199-cycle-condensation-engine.md)
- [200 — CycleArtifactStore NickFury: InMemoryFileStore para artefatos de ciclo com put/get/list (OpenHands FileStore)](story-200-cycle-artifact-store.md)
- [201 — CycleActionRiskAnalyzer NickFury: classificação LOW/MEDIUM/HIGH de ações antes da execução (OpenHands SecurityAnalyzer)](story-201-cycle-action-risk-analyzer.md)
- [202 — CycleStateResetter NickFury: reset coordenado de estado efêmero entre ciclos (OpenHands AgentController.reset)](story-202-cycle-state-resetter.md)

## Milestone 30 — OpenHands Patterns Wave 1: Sub-Agent Delegate, Retry Mixin, Agent State Machine, Event Source Tagger, Batched Exporter

Cinco padrões novos do framework OpenHands/OpenHands (não cobertos pelas Stories 154–156) mapeados
para o pipeline Mekka Trading: SubAgentDelegator permite que NickFury delegue tarefas isoladas para
sub-agentes Vision com DelegateObservation retornando outputs estruturados (OpenHands AgentDelegate),
VisionRetryMixin adiciona retry com backoff exponencial no _call_llm do Vision com tratamento especial
para respostas vazias via temperature jitter (OpenHands RetryMixin), CycleAgentStateMachine rastreia
o estado formal de cada símbolo (IDLE→SCANNING→ANALYZING→SIGNALING→RISK_CHECK→EXECUTING→FINISHED)
com transições validadas (OpenHands AgentState), CycleEventSourceTagger adiciona o campo `source`
a cada evento do pipeline para filtragem e auditoria por componente (OpenHands EventSource USER/AGENT/
ENVIRONMENT), e CycleBatchedExporter acumula eventos do ciclo e os exporta em lotes para um webhook
externo configurável com flush automático e fail-silent (OpenHands BatchedWebHook).

Última story entregue: **197** (CycleBatchedExporter).

- [193 — SubAgentDelegator NickFury: delegação isolada para sub-agentes Vision com DelegateObservation (OpenHands AgentDelegate)](story-193-sub-agent-delegator.md)
- [194 — VisionRetryMixin Vision: retry com backoff exponencial + temperature jitter em respostas vazias (OpenHands RetryMixin)](story-194-vision-retry-mixin.md)
- [195 — CycleAgentStateMachine NickFury: estado formal por símbolo com transições validadas (OpenHands AgentState)](story-195-cycle-agent-state.md)
- [196 — CycleEventSourceTagger NickFury: tagging de origem USER/AGENT/ENVIRONMENT por evento (OpenHands EventSource)](story-196-cycle-event-source.md)
- [197 — CycleBatchedExporter NickFury: export em lotes para webhook externo com flush automático (OpenHands BatchedWebHook)](story-197-cycle-batched-exporter.md)

## Milestone 29 — SWE-agent Patterns Wave 2: Trajectory, Budget Guard, Demonstrations, Observation Feedback, Environment Snapshot

Cinco padrões novos do framework SWE-agent (não cobertos pelas Stories 157–159) mapeados para
o pipeline Mekka Trading: CycleTrajectory mantém log append-only de steps por ciclo serializável
em JSONL para audit trail completo (SWE-agent Trajectory/StepOutput), CycleBudgetGuard rastreia
custo estimado de LLM por sessão e força HOLD quando o budget é excedido com graceful exit
(SWE-agent max_cost + done_status), SignalDemonstrationStore injeta exemplos WIN de ciclos
anteriores no prompt do Vision como few-shot demonstrations (SWE-agent Demonstrations YAML),
ObservationFeedbackLoop re-injeta as correções do AutoSignalLinter no próximo ciclo do Vision
para que o modelo corrija geometria nos seus próprios outputs (SWE-agent ACI guardrails +
linter observation), e MarketEnvironmentSnapshot captura o estado imutável do mercado entre
steps com diff material para contexto do Vision (SWE-agent Environment State Capture).

Última story entregue: **192** (MarketEnvironmentSnapshot).

- [188 — CycleTrajectory NickFury: StepRecord append-only por ciclo + JSONL audit trail (SWE-agent Trajectory)](story-188-cycle-trajectory.md)
- [189 — CycleBudgetGuard NickFury: custo LLM por sessão + HOLD quando budget excedido + graceful exit (SWE-agent max_cost)](story-189-cycle-budget-guard.md)
- [190 — SignalDemonstrationStore Vision: few-shot WIN examples no prompt + lazy load JSON (SWE-agent Demonstrations)](story-190-signal-demonstration-store.md)
- [191 — ObservationFeedbackLoop Vision + NickFury: lint corrections re-injetadas no próximo ciclo Vision (SWE-agent ACI guardrails)](story-191-observation-feedback-loop.md)
- [192 — MarketEnvironmentSnapshot NickFury: snapshot imutável do estado de mercado + diff material (SWE-agent EnvState)](story-192-market-environment-snapshot.md)

## Milestone 27 — Aider Patterns Wave 2: Architect/Editor, Auto-Linter, Watch Mode, Reasoning Budget, Prompt Caching

Cinco padrões do framework Aider-AI/aider mapeados para o pipeline Mekka Trading:
ArchitectEditorVision separa raciocínio livre de geração estruturada em dois LLM calls consecutivos,
AutoSignalLinter corrige geometria do sinal (clamp, swap, fallback) ao invés de bloquear,
TradeAnnotationWatcher monitora `data/trade_hints.json` com lazy reload por mtime para injetar
hints de analistas no prompt Vision, DynamicReasoningBudget ajusta max_tokens do Vision pelo
regime de mercado × cap tier, e AnalysisPromptCache armazena blocos de macro context com TTL
e warm paralelo para reduzir latência de ciclos consecutivos.

Última story entregue: **182** (AnalysisPromptCache).

- [178 — ArchitectEditorVision: dois LLM calls — thesis livre → JSON estruturado (Aider architect/editor mode)](story-178-architect-editor-vision.md)
- [179 — AutoSignalLinter NickFury Integration: lint pós-Vision com clamp/swap/fallback + LintFix SEARCH/REPLACE (Aider auto-lint)](story-179-auto-signal-linter.md)
- [180 — TradeAnnotationWatcher Vision Integration: lazy reload de trade_hints.json por mtime + prompt block (Aider watch mode / AI! comments)](story-180-trade-annotation-watcher.md)
- [181 — DynamicReasoningBudget Vision Integration: max_tokens por regime × cap_tier (Aider --thinking-tokens)](story-181-dynamic-reasoning-budget.md)
- [182 — AnalysisPromptCache Vision Integration: cache TTL de macro_context + get_or_build async + warm paralelo (Aider prompt caching)](story-182-analysis-prompt-cache.md)

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

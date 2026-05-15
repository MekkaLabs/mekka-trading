# Mekka Trading — Stories Index

Índice agrupado por milestone temático. Cada milestone fecha uma camada
arquitetural. Stories abaixo são lidas em ordem numérica dentro de cada
bloco.

Última story entregue: **029a** (Safety Net).
Próxima planejada: **029** (Wolverine — Recovery Agent).

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

## Milestone 8 — Recovery + Daily PnL
Daily PnL writer fechando o ciclo de drawdown que Batman lê, depois
contract hardening, depois Wolverine como recovery agent + monitor
cycle real.

- [027 — Daily PnL Writer](story-027-daily-pnl-writer.md)
- [028 — Contract Hardening](story-028-contract-hardening.md)
- [029a — Safety Net](story-029a-safety-net.md)
- 029 — Wolverine Recovery Agent (planejada)

## Milestone 9 — LLM Hardening (planned)
Vision Critic toggle, audit log harmonization TS↔Python.

- 030 — Vision Critic (planejada)
- 031 — Audit Single Source of Truth (planejada)

## Milestone 10 — Tactical + Simulation (planned)
Flash (sub-loop intra-candle), Deadpool (backtest replay), Telegram bot
rico.

- 032 — Flash (planejada)
- 033 — Deadpool (planejada)
- 034 — Telegram Bot (planejada)

## Milestone 11 — Mainnet Readiness (planned)
Checklist formal, gate humano, cobertura ≥ 80% em Vision/Batman/Iron
Man, observability harmonizada.

- 035 — Mainnet Readiness (planejada)

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

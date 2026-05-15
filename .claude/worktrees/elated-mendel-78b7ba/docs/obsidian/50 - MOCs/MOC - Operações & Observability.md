---
title: MOC — Operações & Observability
type: moc
tags: [moc, ops, observability]
created: 2026-05-07
---

# 🔭 MOC — Operações & Observability

> Mapa vivo de operações, logs, alertas, integridade e CLIs operacionais.

## Pipeline de Observabilidade

```
Evento → Store (jsonl) → Alerts → Reports → Audit Trail
```

## CLIs Operacionais Disponíveis

| CLI | Comando | Função |
|---|---|---|
| Runtime | `npm run run:runtime` | Loop principal do Megazord |
| Replay | `npm run run:replay` | Replay de eventos históricos |
| Export Report | `npm run run:export-report` | Exporta relatórios |
| Verify Integrity | `npm run run:verify-integrity` | Valida integridade do audit-trail |
| Health Check | `npm run run:health-check` | Saúde do sistema |
| Replay DLQ | `npm run run:replay-dlq` | Reprocessa Dead Letter Queue |
| Alerts Retention | `npm run run:alerts-retention` | Aplica política de retenção |
| Ops Status | `npm run run:ops-status` | Status operacional |
| Ops Alerts | `npm run run:ops-alerts` | Lista alertas |
| Ops Alert Audit | `npm run run:ops-alert-audit` | Auditoria de entrega de alertas |

## Stores

- `observability/store/` — eventos brutos (jsonl)
- `observability/alerts/` — alertas gerados
- `observability/reports/` — relatórios consolidados
- `memory/audit-log/` — trilha de auditoria
- `memory/alerts/` — alertas persistidos
- `memory/reports/` — relatórios de missão

> ⚠️ Todos esses diretórios são tratados como **dados runtime** — `.gitkeep` é versionado, conteúdo `.jsonl/.json` não.

## Stories de Observability

- story-002 — Megazord runtime
- story-004 — Observability replay
- story-006 — Mission report export
- story-007 — Observability integrity
- story-008 — Integrity verifier CLI
- story-009 — Observability health check
- story-010 — Alert dispatch routing
- story-011 — Alert dedup window
- story-012 — Signed webhook retry
- story-013 — DLQ jitter retry
- story-014 — DLQ replay retention
- story-015 — Health retention + DLQ backpressure
- story-016 — Replay lock + circuit breaker
- story-017 — Operational metrics export
- story-018 — Ops trends + lock contention
- story-023 — Ops alert delivery audit-trail
- story-024 — Ops alert audit KPIs + retention

## Runbooks

```dataview
LIST
FROM "30 - Resources/Runbooks"
SORT file.name ASC
```

## Próximos passos

- [ ] Criar runbook por CLI listada acima
- [ ] Documentar SLOs e SLIs
- [ ] Mapear matriz de alertas por severidade

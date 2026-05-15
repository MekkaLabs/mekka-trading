---
title: MOC — Arquitetura
type: moc
tags: [moc, arquitetura]
created: 2026-05-07
---

# 🏗️ MOC — Arquitetura

> Mapa vivo da arquitetura técnica do Mekka Trading.

## Visão Geral

Mekka Trading é um **Sistema Operacional de Trading Autônomo** com:
- **Mission Planner + Squad Router + Runtime Loop** (Megazord v1.1)
- **Risk-first execution** (paper-only)
- **Multi-agent orchestration** sobre AIOX Core
- **Observability completa**: logs, eventos, audit trail

## Contrato de Workflow

```
INPUT → ANALYSIS → DECOMPOSITION → ROUTING → EXECUTION → VALIDATION → REFLECTION → OUTPUT
```

## Módulos do Projeto

### Núcleo (TypeScript)
- `agents/` — definições de agentes individuais
- `squads/` — composições de squads (14 squads especializadas)
- `workflows/` — workflows orquestrados
- `cli/` — interface de linha de comando
- `prompts/` — prompts estruturados

### Domínio de Trading
- `exchanges/hyperliquid/` — adaptador mock para Hyperliquid
- `market-data/` — feeds de mercado
- `risk-engine/` — políticas de risco e kill switch
- `execution-engine/` — motor de execução (paper)
- `strategy-engine/` — sinais e estratégias
- `backtesting/` — replay e validação

### Infra
- `observability/` — store, alerts, reports
- `memory/` — audit-log, alerts, reports persistidos
- `aiox-core/` — framework AIOX Core (submódulo)

### Runtime Python (`src/`)
- `src/agents/` — implementações Python dos agentes super-heroes (Aquaman, Batman, Black Panther, Doctor Strange, Iron Man, Nick Fury, Professor X, Spider-Man, Superman, Thor, Vision)
- `src/dashboard/` — [[../20 - Areas/Arquitetura/Dashboard Web (Pixel 3D)|Dashboard Web (Pixel 3D)]] (FastAPI + WebSocket + pixel 3D Marvel/Wall Street)
- `src/persistence/` — SQLite (db, models, repository)
- `src/config/` — settings + .env loader
- `src/models/` — modelos compartilhados
- `run.py` — entrypoint Python (`--once`, `--dashboard`, `--dashboard-only`, `--equity`)

## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Runtime principal | Node.js 20+ / TypeScript 5.7 |
| Componentes auxiliares | Python 3.12 (pytest asyncio) |
| Exchange | Hyperliquid (mock-only) |
| Notificações | Telegram |
| Notícias | CryptoPanic |
| LLM | OpenAI |

## Decisões Arquiteturais (ADRs)

```dataview
TABLE without ID
  file.link AS "ADR",
  status AS "Status",
  date AS "Data"
FROM "30 - Resources/Decisoes Tecnicas"
SORT date DESC
```

## Notas relacionadas

```dataview
LIST
FROM #arquitetura
WHERE file.path != this.file.path
SORT file.mtime DESC
```

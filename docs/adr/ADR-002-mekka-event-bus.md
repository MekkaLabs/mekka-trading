# ADR-002 — MekkaEventBus (pub/sub in-process)

**Status:** ACCEPTED — entregue (Story 136)  
**Date:** 2026-05-15  
**Decision Drivers:** observability desacoplada, extensibilidade, baixo atrito, segurança paper-first

---

## Context

O pipeline do Mekka Trading tem múltiplos produtores de eventos relevantes
(Vision signal, Batman verdict, execução do IronMan, erros, timings), mas a
observabilidade intra-ciclo depende de logs e de instrumentação ad-hoc em cada
agente.

Isso cria fricção para:
- Dashboards e métricas (latência por etapa, contagem de fallbacks, custo de LLM).
- Alertas customizados (p.ex. pause automático por anomalias).
- Plugins/integrações sem tocar no core do pipeline.

Queremos um mecanismo leve e padronizado para publicar eventos sem acoplar
produtores e consumidores, e sem introduzir dependências externas (Kafka, Redis).

## Decision

Adotar um **pub/sub in-process** via `MekkaEventBus` (`src/services/event_bus.py`)
com as propriedades:
- Handlers **sync ou async**.
- `topic="*"` como wildcard.
- Execução paralela via `asyncio.gather`.
- **Fail-silent** (erros em handlers não derrubam o ciclo; apenas logam).
- Counters por topic para testes/telemetria.

O `NickFury._cycle_for_symbol()` publica eventos padrão do ciclo para criar um
contrato mínimo para consumidores.

## Considered Options

### Option A — Instrumentação por logs (status quo)

- **Pros:** zero código novo.
- **Cons:** não estruturado, difícil de compor/assinar, acopla parsing de log e
  não cria contrato para dashboards/alertas.

### Option B — Event bus in-process (decisão)

- **Pros:** baixo atrito, sem infraestrutura, extensível, contrato explícito.
- **Cons:** somente no processo (não atravessa múltiplas instâncias); precisa de
  cuidado para não virar “event storm”.

### Option C — Mensageria externa (Kafka/Redis/Rabbit)

- **Pros:** durável e distribuído.
- **Cons:** overhead operacional, mais moving parts, desnecessário para paper-first
  e para o ciclo atual.

## Consequences

### Positivas

- Consumidores podem ser adicionados sem editar agentes.
- Base para métricas de custo de LLM (Stories 142–143) e telemetria granular.
- Facilita chaos/observability hooks para `DEGRADED_MODE` (Story 140).

### Negativas / Riscos

- Pode mascarar bugs em handlers (fail-silent). Mitigação: counters + testes e
  alertas em logs.
- Não é distribuído. Se precisarmos multi-process, revisitar com mensageria.

## Follow-ups

- Definir contrato “canônico” de eventos (payload keys + versioning) antes de
  expor para dashboards externos.
- Usar EventBus para custo/tokens LLM e prompt versioning (Milestone 22).


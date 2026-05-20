---
title: ADR Index
type: index
tags: [adr, decisao, index]
created: 2026-05-20
updated: 2026-05-20
---

# ADR Index — Architecture Decision Records

> O projeto possui **duas localizações de ADRs** por razões históricas. Esta nota indexa ambas e explica o porquê.

## ADRs no Obsidian (formatação rica + cross-link)

Stack moderno de ADRs nascidos dentro do vault. Têm frontmatter completo, cross-links Obsidian, e seguem o template em `Template - ADR`.

- [[ADR-001 - Adoção de PARA + MOC para o segundo cérebro]] — Por que o vault existe e como ele é organizado.
- [[ADR-002 - Multi-Exchange via CCXT]] — Decisão de adotar CCXT como camada unificada para Bybit + Binance (Story 046).
- [[ADR-003 - Bybit Testnet Readiness]] — Sandbox routing + UX safety entregues em 2026-05-19 (Milestone 22).

## ADRs em `docs/adr/` (codex / Markdown puro)

ADRs criados pelo codex em formato Markdown técnico. Não estão no vault para evitar duplicação, mas são parte do registro arquitetural e devem ser consultados:

| Path | Tema | Status |
|---|---|---|
| `docs/adr/ADR-001-audit-single-source.md` | Audit log como single source of truth (Story 032/032b) | IN PROGRESS |
| `docs/adr/ADR-002-mekka-event-bus.md` | MekkaEventBus — pub/sub in-process (Story 136) | ACCEPTED |
| `docs/adr/ADR-003-llm-structured-output-first.md` | Vision saída JSON estruturada (Story 250) | ACCEPTED |

> **Importante**: a numeração colide deliberadamente. O contexto distingue:
> - "ADR-001" no obsidian = PARA adoption
> - "ADR-001" em docs/adr/ = audit single source
>
> Uma futura story pode unificar os dois sistemas. Por ora, o ADR Index aqui é a fonte de verdade sobre "qual ADR fala sobre o quê".

## Lacunas (ADRs que deveriam existir)

Decisões grandes do projeto sem ADR formal escrito:

- [ ] **LangGraph adoption** (Story 126) — por que LangGraph para durable execution
- [ ] **Mixture of Agents (MoA) Vision** (Story 131) — padrão AutoGen para reflexão
- [ ] **Adaptive Layer-1 Routing** (Story 135) — Strategy → Vision dispatch dinâmico
- [ ] **DecisionMemory** (Story 249) — armazenamento de decisões para replay
- [ ] **Beast Continuous Improvement Agent** (Story 248) — read-only auditor
- [ ] **Force Execute escape hatch** (M22.1, esta sessão) — bypass condicional do Batman
- [ ] **CycleCheckpoint** (Story 251) — checkpointing por ciclo do NickFury

## Workflow para novos ADRs

1. Use o template: `Template - ADR` (frontmatter `type: adr`, `status: proposta`).
2. Salve em `30 - Resources/Decisoes Tecnicas/` com nome `ADR-NNN - Título Curto.md`.
3. Atualize esta index.
4. Mencione o ADR na story relacionada via wikilink `[[ADR-NNN - ...]]`.
5. Para decisões muito técnicas/de baixo nível (incident response, format de payload), prefira `docs/adr/` mantendo nomeação ADR-NNN-titulo-kebab.md.

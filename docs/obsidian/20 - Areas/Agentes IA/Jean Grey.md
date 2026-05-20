---
title: "Agente — Jean Grey"
type: agente
tags: [agente]
codename: Jean Grey
role: Memory Master (Second Brain)
status: ativo
created: 2026-05-20
updated: 2026-05-20
---

# Agente — Jean Grey

> **Codinome**: Jean Grey
> **Papel**: Memory Master (keeper do segundo cérebro)
> **Squad principal**: market-intel-lab (knowledge/ops)

## Missão

Garantir a saúde do vault Obsidian (links, frontmatter, duplicações, drift) e sugerir atualizações do segundo cérebro com base no estado do repo.

## Responsabilidades

- **Vault health scan** — links quebrados (wikilinks sem nota correspondente),
  links de pasta (navegação, classificados à parte), notas órfãs (sem
  backlinks, exceto MOC/index/home/daily/templates) e duplicatas (similaridade
  textual via `difflib`).
- **`recall(query)`** — busca textual no vault + `DecisionMemory` (por símbolo);
  é a interface de memória de longo prazo que outros agentes consultam.
- **`draft_adr_from_beast(report)`** — converte propostas do [[Beast]] em
  rascunhos de ADR (`ADR-DRAFT-*.md`) em `30 - Resources/Decisoes Tecnicas`
  para o operador aprovar/rejeitar.
- Ajudar a manter **Home**, **Projeto**, **Stories**, **ADR Index** e
  índices/MOCs consistentes.

## Inputs (o que consome)

- Vault em `docs/obsidian/`
- `DecisionMemory` (decisões/outcomes do Vision, por símbolo)
- Propostas do [[Beast]] (para gerar ADR drafts)

## Outputs (o que produz)

- *Vault Health Report* (`VaultHealthReport`): `broken_links`, `folder_links`,
  `orphans`, `duplicates`
- `RecallHit[]` — trechos relevantes para outros agentes
- `ADR-DRAFT-*.md` — rascunhos de decisão a partir do Beast

## Detalhes técnicos

- **Normalização NFC**: nomes de arquivo no macOS vêm em NFD (decomposto) e
  wikilinks em NFC (composto) — Jean Grey normaliza ambos para NFC, evitando
  falsos positivos em notas acentuadas (MOCs, "Persistência SQLite", etc.).
- **Sem embeddings (MVP)**: análise puramente textual, zero dependência de
  API key. Dedup semântico via embeddings é follow-up de Fase 2.
- O scan roda em `asyncio.to_thread` para não bloquear o event loop do dashboard.

## Prompts / Instruções

- Implementação: `src/agents/jean_grey.py`
- Endpoint dashboard: `GET /api/jean/health-report`

## Métricas de qualidade

- Drift baixo (Home/Projeto/Stories Index/ADR Index coerentes com `docs/stories/INDEX.md` e estado do repo)
- Zero conflitos/artefatos (merge markers, duplicações, links quebrados) no vault

## Interações

- Com [[Beast]]: Beast pode propor melhorias; Jean Grey operacionaliza no vault
- Com [[Nick Fury]]: alimenta o ciclo com alertas de saúde do segundo cérebro (advisory)

## Histórico de mudanças

- 2026-05-20 — Criado

---
title: "Agente — Galactus"
type: agente
tags: [agente]
codename: Galactus
role: Premortem Specialist / Devourer of Ideas
status: ativo
created: 2026-05-20
updated: 2026-05-20
---

# Agente — Galactus

> **Codinome**: Galactus
> **Papel**: Especialista em premortem — o devorador de ideias
> **Squad principal**: market-intel-lab (improvement council)

## Missão

Comedor de planetas, aqui devorador de **ideias**. É o **contraponto** de
[[Beast]] e [[Jean Grey]]: enquanto eles constroem, Galactus destrói para
testar. Para cada proposta ele faz um **premortem** — "assuma que isso entrou
em produção e falhou catastroficamente: por quê?" — e só o que sobrevive à
fome dele chega consolidado ao [[Mekka]].

## Como decide

Para cada proposta produz um `PremortemVerdict`:
- **veredito**: `SURVIVES` | `NEEDS_HARDENING` | `DEVOURED`
- **hunger_score** (0–100): o quanto ele quer devorar = nível de risco
- **failure_modes**: modos de falha específicos por área + mitigação

Heurística (sem LLM no MVP): combina criticidade da área (risk/execution/
security = CRÍTICO), impacto declarado e força da evidência. Área crítica +
evidência fraca → **DEVOURED** na hora.

## Inputs / Outputs

- **Inputs**: lista de propostas (do [[Beast]] e do inbox, via [[Mekka]])
- **Outputs**: `PremortemReport` com os vereditos + mitigações
- Read-only, fail-silent, domain-agnostic (serve trading-ops E dev-squad)

## Interface

- Implementação: `src/agents/galactus.py`
- Consumido por [[Mekka]] em `GET /api/improvements`

## Interações

- Contraponto de [[Beast]] e [[Jean Grey]]
- Alimenta o [[Mekka]] com a crítica de premortem para consolidação

## Histórico de mudanças

- 2026-05-20 — Criado (premortem / devorador de ideias)

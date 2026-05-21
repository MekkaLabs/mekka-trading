---
title: Agente — Cypher
type: agente
tags: [agente, scanner, continuous-improvement, dev-squad, read-only, cypher]
codename: Cypher
real_name: Doug Ramsey
role: Code Auditor
status: ativo
layer: L4 (Analyst tier)
introduced: 2026-05-21
created: 2026-05-21
updated: 2026-05-21
---

# Agente — Cypher

> **Codinome**: Cypher (Doug Ramsey)
> **Papel**: CodeAuditor — scanner de dívida de código (dev-squad)
> **Layer**: L4 (Departamento de Melhoria Contínua)
> **Arquivo**: `src/agents/code_auditor.py`
> **Consolidado por**: [[Mekka]] (via `_code_auditor_proposals`)

## Missão

Auditar o **próprio repositório** e auto-detectar dívida técnica de dev — o que antes só entrava no conselho pelo inbox manual.

> _Por que Cypher?_ O poder do Doug Ramsey é compreender **qualquer linguagem**, incluindo código-fonte. Encaixe perfeito para o agente que lê o repo como linguagem.

## O que Cypher analisa

- Arquivos grandes (> 1500 linhas) → candidatos a refactor (detectou `server.py` 6710 linhas como HIGH).
- Marcadores `TODO/FIXME/HACK` em comentários.
- Módulos de agente sem teste correspondente em `tests/`.
- Findings do `ruff` (json, com timeout).

## Princípios

Read-only, fail-silent, evidence-based; nunca toca arquivos de segurança (`settings.py`, kill switch).

## Cross-references
- Comandante: [[Mekka]] · Premortem: [[Galactus]]
- Squad: [[Beast]], [[Domino]], [[Forge]], [[Ice Man]], [[Sage]], [[Jean Grey]]

## Status
- ✅ `src/agents/code_auditor.py` · integrado ao [[Mekka]] · roster + office (🔍 Cypher) · testes em `tests/test_improvement_scanners.py`.

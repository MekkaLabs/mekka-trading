---
title: Agente — Forge
type: agente
tags: [agente, scanner, continuous-improvement, infra, ops, read-only, forge]
codename: Forge
real_name: Forge (Cheyenne)
role: Ops Scanner
status: ativo
layer: L4 (Analyst tier)
introduced: 2026-05-21
created: 2026-05-21
updated: 2026-05-21
---

# Agente — Forge

> **Codinome**: Forge
> **Papel**: OpsScanner — scanner de saúde operacional (dev-squad/infra)
> **Layer**: L4 (Departamento de Melhoria Contínua)
> **Arquivo**: `src/agents/ops_scanner.py`
> **Consolidado por**: [[Mekka]] (via `_ops_scanner_proposals`)

## Missão

Monitorar a **saúde operacional** a partir do audit stream e do log de runtime, propondo correções de estabilidade.

> _Por que Forge?_ Forge é o mutante **engenheiro** dos X-Men — constrói, conserta e monitora sistemas/máquinas. Encaixe natural para o scanner de ops/infra.

## O que Forge analisa

- Erros recorrentes (ERROR/CRITICAL) agrupados por agente+evento no audit.
- `CYCLE_ERROR` por agente (falhas de ciclo).
- Exceções recorrentes no tail do log do dashboard.

## Princípios
Read-only, fail-silent; nunca reinicia serviços nem muta estado — só lê e propõe.

## Cross-references
- Comandante: [[Mekka]] · Premortem: [[Galactus]]
- Squad: [[Beast]], [[Cypher]], [[Domino]], [[Ice Man]], [[Sage]], [[Jean Grey]]

## Status
- ✅ `src/agents/ops_scanner.py` · integrado ao [[Mekka]] · roster + office (🛠️ Forge) · testes em `tests/test_improvement_scanners.py`.

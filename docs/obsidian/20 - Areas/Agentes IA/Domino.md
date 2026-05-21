---
title: Agente — Domino
type: agente
tags: [agente, scanner, continuous-improvement, trading-ops, risk, read-only, domino]
codename: Domino
real_name: Neena Thurman
role: Risk Scanner
status: ativo
layer: L4 (Analyst tier)
introduced: 2026-05-21
created: 2026-05-21
updated: 2026-05-21
---

# Agente — Domino

> **Codinome**: Domino (Neena Thurman)
> **Papel**: RiskScanner — scanner de postura de risco (trading-ops)
> **Layer**: L4 (Departamento de Melhoria Contínua)
> **Arquivo**: `src/agents/risk_scanner.py`
> **Consolidado por**: [[Mekka]] (via `_risk_scanner_proposals`)

## Missão

Ler a **postura de risco** ao longo do tempo e propor melhorias de segurança/estabilidade — sem nunca tocar o kill switch ou os gates (read-only).

> _Por que Domino?_ O poder da Neena é manipular **probabilidade/sorte** — exatamente o domínio do risco e das odds.

## O que Domino analisa

- Kill switch ativo agora, ou disparos repetidos (engates reais via `payload.kill_switch_engaged`).
- Drawdown diário aproximando-se do `max_daily_drawdown_pct`.
- Rejeições do [[Batman - Risk Guardian|Batman]] por motivo — **excluindo HOLD** (HOLD não é fricção, é o comportamento correto).

## Princípios
Read-only, fail-silent; nunca engata/libera o kill switch nem propõe tocar os safety gates.

## Cross-references
- Comandante: [[Mekka]] · Premortem: [[Galactus]]
- Squad: [[Beast]], [[Cypher]], [[Forge]], [[Ice Man]], [[Sage]], [[Jean Grey]]
- Risco: [[Batman - Risk Guardian]]

## Status
- ✅ `src/agents/risk_scanner.py` · integrado ao [[Mekka]] · roster + office (⚠️ Domino) · testes em `tests/test_improvement_scanners.py`.

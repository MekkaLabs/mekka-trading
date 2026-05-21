---
title: Agente — Sage
type: agente
tags: [agente, scanner, continuous-improvement, measurement, kpi, read-only, sage]
codename: Sage
real_name: Tessa (Sage)
role: Measurement Loop / KPI
status: ativo
layer: L4 (Analyst tier)
introduced: 2026-05-21
created: 2026-05-21
updated: 2026-05-21
---

# Agente — Sage

> **Codinome**: Sage (Tessa)
> **Papel**: Loop de medição — mede se o sistema está melhorando ou piorando
> **Layer**: L4 (Analyst — Departamento de Melhoria Contínua)
> **Arquivo**: `src/agents/sage.py`
> **Consolidado por**: [[Mekka]] (via `_sage_proposals`)

## Missão

Fechar o **ciclo** do departamento: em vez de só propor mudanças, Sage **mede o impacto** ao longo do tempo e devolve isso como evidência. É a memória estatística do squad.

> _Por que Sage?_ Tessa tem a mente que funciona como um computador, calculando estatísticas continuamente. Encaixe perfeito para o agente de medição/KPI.

## Como funciona (v1 — baseline de sistema)

1. A cada execução, tira um **snapshot** de métricas-chave em `data/sage_baselines.json`:
   win rate, profit factor, erros nas últimas 24h, nº de trades fechados.
2. Compara o snapshot atual com a **linha de base recente** (média das execuções anteriores).
3. Emite uma proposta quando uma métrica **regride** além do limiar:
   - win rate caiu ≥ 10 pontos percentuais → **HIGH**.
   - erros/24h ≥ 2× a base (e ≥ 5) → **MEDIUM**.
4. Expõe um **KPI do departamento** via `kpi()` (aceitas/reprovadas/taxa de aceitação, lido de `data/improvement_decisions.json`).

## Princípios

1. **Read-only no trading** — o único arquivo que escreve é o próprio histórico de baseline em `data/`.
2. **Fail-silent** — nunca lança exceção; primeira execução só estabelece baseline (sem propostas).
3. **Honesto** — v1 é medição **de sistema** (não atribui baseline a uma melhoria específica).

## Extensão futura (design §4)

- Atribuir baseline a uma **melhoria entregue específica** (antes/depois daquela mudança), e marcar cada melhoria como *efetiva / neutra / regressão* — alimentando a memória da [[Jean Grey]].

## Cross-references

- Comandante do squad: [[Mekka]]
- Pesquisa externa: [[Ice Man]]
- Memória/segundo cérebro: [[Jean Grey]]

## Status atual

- ✅ Implementado em `src/agents/sage.py`
- ✅ Integrado ao [[Mekka]] e ao filtro por fonte no dashboard (📐 Sage)
- ✅ Baseline persistido em `data/sage_baselines.json`
- ⏳ Medição por-melhoria (antes/depois atribuído) — futuro
- ⏳ Teste unitário dedicado — TODO

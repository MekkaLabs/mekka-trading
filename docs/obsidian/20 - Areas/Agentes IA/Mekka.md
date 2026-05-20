---
title: "Agente — Mekka"
type: agente
tags: [agente]
codename: Mekka
role: Continuous-Improvement Commander
status: ativo
created: 2026-05-20
updated: 2026-05-20
---

# Agente — Mekka

> **Codinome**: Mekka
> **Papel**: Comandante & consolidador da melhoria contínua
> **Squad principal**: market-intel-lab (improvement council)

## Missão

Super-herói do futuro com os maiores poderes de tecnologia e tomada de decisão
acertiva. Lidera o conselho de melhoria contínua: **não gera ideias cruas** —
consolida as propostas do time em recomendações ranqueadas e decisivas, para o
operador aprovar ou reprovar.

## Conselho que ele comanda

```
Beast      → propõe melhorias (data-driven, audit trail)
Jean Grey  → memória / contexto do vault
Galactus   → premortem (devora as ideias frágeis)
   ↓
Mekka      → consolida proposta + contexto + premortem em UMA recomendação
             ranqueada, com decisão clara, por domínio
   ↓
Operador   → aceita / reprova na Central de Melhorias
```

Atua em **dois domínios**:
- **trading-ops** (heróis): risk, execution, signal_quality, latency
- **dev-squad**: backend, frontend, dashboard, design, ux, security, data, infra

## Inputs / Outputs

- **Inputs**: propostas do [[Beast]] + inbox curado (`data/improvement_inbox.json`) + premortem do [[Galactus]]
- **Outputs**: `MekkaCouncilReport` com `CouncilRecommendation[]` (decision RECOMMEND / RECOMMEND_WITH_MITIGATION / REJECT / DEFER, priority P1–P3, domain)
- **Persistência**: decisões do operador em `data/improvement_decisions.json`

## Interface

- Implementação: `src/agents/mekka.py`
- Endpoints: `GET /api/improvements`, `POST /api/improvements/decision`
- Página: **Central de Melhorias** (`/Melhorias` no dashboard)

## Interações

- Com [[Beast]] e [[Galactus]]: consolida proposta + premortem
- Com [[Jean Grey]]: usa contexto/memória do vault
- Read-only quanto a trading — só escreve decisões de melhoria

## Histórico de mudanças

- 2026-05-20 — Criado (líder do conselho de melhoria contínua)

---
title: Agente — Beast
type: agente
tags: [agente, analista, l4, beast, continuous-improvement, read-only]
codename: Beast
real_name: Dr. Hank McCoy
role: Continuous Improvement Analyst
status: ativo
layer: L4 (Analyst tier)
story: 248
introduced: 2026-05-19
created: 2026-05-20
updated: 2026-05-20
---

# Agente — Beast

> **Codinome**: Beast (Dr. Hank McCoy)
> **Papel**: Read-only auditor + improvement proposal engine
> **Layer**: L4 (Analyst — junto com [[Wolverine]] e [[Portfolio Manager]])
> **Arquivo**: `src/agents/beast.py`
> **Story de origem**: [[Stories do Projeto|248 — Beast Agent]]

## Missão

Auditar continuamente o sistema, identificar padrões de degradação ou oportunidades de melhoria, e **propor** stories candidatas ao operador. Beast nunca executa, nunca trade, nunca modifica configuração — apenas observa, mede e recomenda.

> _Por que Beast?_ Hank McCoy é o cientista do time X-Men: o que melhora o time não fazendo combate, mas analisando, medindo e propondo. Equivalente perfeito para um agente de continuous improvement.

## Princípios

1. **Read-only por construção** — sem dependência de qualquer SDK de escrita.
2. **Evidence-based** — toda proposta vem com dados mensuráveis.
3. **Prioritizado** — propostas rotuladas HIGH/MEDIUM/LOW por impacto estimado.
4. **Non-disruptive** — roda out-of-band do ciclo principal de trading.
5. **Fail-silent** — qualquer erro → log + retorna lista vazia, nunca trava o sistema.

## O que Beast analisa

- **Trade outcomes** (últimos N dias): taxa de win, PnL, drawdown.
- **Gate statistics**: quais gates do [[Batman]] disparam mais, por quê, e se isso bloqueia oportunidades reais.
- **Signal quality vs execution quality**: gap entre o que [[Vision]] propõe e o que [[Iron Man]] executa.
- **Underperforming agents**: latência, taxa de fallback (Vision HOLD), warnings recorrentes no audit log.
- **Patterns cross-symbol**: drawdown concentrado em um ativo, perdas correlacionadas, etc.

## Como Beast se comunica

- **Telegram**: relatório semanal estruturado (ou on-demand via `/beast`).
- **Audit log**: cada execução grava `BEAST_PROPOSAL_BATCH` com a lista completa.
- **Dashboard**: futura tile dedicada (TODO) com as últimas propostas + status de adoção.

## Quando Beast NÃO age

- Durante kill switch ativo (não polui o canal com sugestões quando o sistema está em emergência).
- Quando o `INSUFFICIENT_DATA` predomina (precisa de pelo menos N=10 trades para análise estatística).
- Em paper mode com `equity_curve` curto (<3 dias) — espera maturidade dos dados.

## Cross-references

- Decisão técnica: [[ADR-002 - Multi-Exchange via CCXT]] (Beast lê estado multi-exchange uniformemente)
- Codex Milestone: M40 — Agent Communication Upgrade (entrega de Beast + 6 outras stories)
- Vizinhos no roster: [[Wolverine]], [[Portfolio Manager]], [[Cyclops]]

## Status atual

- ✅ Implementado em `src/agents/beast.py`
- ✅ Sprite adicionada em `office_v2/sprites.jsx` (cores cian-azul + visor escuro)
- ✅ Adicionado ao roster em `office-v2-src/roster.js` (L4, station na row 4)
- ⏳ Tile dashboard dedicada — TODO
- ⏳ Comando Telegram `/beast` — TODO

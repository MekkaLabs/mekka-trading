---
title: Agente — Ice Man
type: agente
tags: [agente, scanner, continuous-improvement, research, read-only, ice-man]
codename: Ice Man
real_name: Robert "Bobby" Drake
role: External Research Scanner
status: ativo
layer: L4 (Analyst tier)
introduced: 2026-05-21
created: 2026-05-21
updated: 2026-05-21
---

# Agente — Ice Man

> **Codinome**: Ice Man (Bobby Drake)
> **Papel**: Scanner de pesquisa externa (o "olhar para fora do sistema")
> **Layer**: L4 (Analyst — Departamento de Melhoria Contínua)
> **Arquivo**: `src/agents/ice_man.py`
> **Consolidado por**: [[Mekka]] (via `_ice_man_proposals`)

## Missão

Enquanto os outros scanners auditam o sistema **por dentro**, Ice Man pesquisa o **mundo lá fora** e traz o que deveria mudar aqui dentro. v1 foca no sinal de maior valor e menor risco para um bot que opera ao vivo: **frescor de dependências**.

> _Por que Ice Man?_ Bobby Drake é o X-Man que projeta gelo para fora de si — alcança o ambiente externo. Encaixe natural para o agente que estende o alcance do departamento para fora do repositório.

## O que Ice Man analisa (v1)

- **Dependências-chave instaladas vs. última no PyPI** — `ccxt`, `pydantic`, `aiohttp`, `pandas-ta`, `openai`, `anthropic`.
- **ccxt é crítico**: um ccxt desatualizado significa suporte velho às APIs das exchanges (Binance/Bybit) → risco real em mainnet → proposta **HIGH**.
- Demais deps desatualizadas → agrupadas em uma proposta **LOW** (menos ruído).

## Princípios (herdados do [[Beast]])

1. **Read-only** — Ice Man nunca instala nem altera nada; só propõe.
2. **Fail-silent + time-boxed** — chamadas HTTP ao PyPI com timeout curto; PyPI lento/bloqueado nunca trava o scan do conselho.
3. **Evidence-based** — cada proposta carrega versão instalada vs. latest.

## Extensões futuras (design §3)

- WebSearch/papers e MCPs financeiros (LSEG/bigdata) para sugerir features de sinal.
- GitHub releases/issues + CVEs de dependências.
- Nota: o processo do app **não** chama a ferramenta WebSearch do Claude Code — por isso v1 usa HTTP direto e auditável ao PyPI.

## Cross-references

- Comandante do squad: [[Mekka]]
- Premortem das propostas: [[Galactus]]
- Vizinhos no squad de melhoria: [[Beast]], [[Sage]], [[Jean Grey]]

## Status atual

- ✅ Implementado em `src/agents/ice_man.py`
- ✅ Integrado ao [[Mekka]] e ao filtro por fonte no dashboard (🧊 Ice Man)
- ⏳ Teste unitário dedicado — TODO
- ⏳ Pesquisa via GitHub/MCPs financeiros — futuro

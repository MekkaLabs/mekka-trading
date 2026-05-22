---
title: Histórico Testnet (gate H1)
type: operacional
tags: [operacional, testnet, mainnet, h1, evidencia, binance]
status: ativo
created: 2026-05-22
updated: 2026-05-22
---

# Histórico Testnet — evidência do gate H1

> **Gate H1** ([[Departamento de Melhoria Contínua|roadmap]] / `docs/MAINNET-AUTHORIZATION.md`):
> ≥ 1 mês de operação testnet **sem incidente crítico** antes de ir para mainnet.
> Esta nota é o log corrido dessa evidência.

## Resumo

| Item | Estado |
|---|---|
| Exchange | Binance Futures **Testnet** (`testnet.binancefuture.com`) |
| Modo | LIVE de testnet (`PAPER_TRADING=false`, ordens reais, dinheiro fictício) |
| Pipeline | Superman → Vision (LLM Anthropic) → Batman → IronMan → SQLite + SL na corretora |
| Início validado | 2026-05-21 |

## Log de marcos

### 2026-05-22 — ✅ 2 operações ganhas
- Operador relatou **2 operações vencedoras** no testnet.
- DB confirma execução real ponta a ponta: múltiplas ordens **FILLED** (`paper=False`).
  - Ex.: `#22`/`#23` BTC SHORT ~0,033 BTC, notional ~$2.550.
  - Trades menores anteriores (`#12`–`#15`) também FILLED.
- Validações de robustez ativas: SL fail-safe, guardião de SL (monitor + boot),
  reconciliação no boot, clock-skew hardening, min-notional, BinancePriceFeed.
- `pnl_usd` não é gravado na linha de abertura — vitória medida via uPnL/fechamento.

### A preencher (continuar o log)
- [ ] Período corrido de ≥ 1 mês sem incidente crítico (início: 2026-05-21).
- [ ] Registrar qualquer incidente em [[INCIDENT-PLAYBOOK|playbook de incidentes]].
- [ ] Win rate / nº de trades por semana (ver [[Sage]] / `/Melhorias` KPI).

## Próximo passo

Quando H1 (e H2–H6) estiverem satisfeitos, seguir o [[Runbook - Iniciar dashboard web|runbook]]
de virada: `docs/RUNBOOK-MAINNET-GOLIVE.md`.

## Cross-references
- [[Paper Trading vs Live]] · [[Kill Switch - Operação]] · [[Batman - Risk Guardian]]
- Medição: [[Sage]] · Comando do conselho: [[Mekka]]

---
title: Cable — Derivatives Intelligence Analyst
type: agent
layer: L4
status: ativo
tags: [agente, derivatives, analytics, read-only, cable, mekka-trading]
created: 2026-05-26
updated: 2026-05-26
---

# Cable

> **Categoria:** Agente analítico runtime — **NÃO executa ordens**
> **Arquivo:** `src/agents/cable.py`
> **Service:** `src/services/derivatives_intel.py`
> **Endpoint:** `GET /api/cable/snapshot`
> **Painel:** "📈 Inteligência de Derivativos" no dashboard

## Identidade

Cable (Nathan Summers) é o **analista de inteligência de derivativos** do
Mekka. Soldado cibernético do futuro — vê padrões. Read-only puro,
determinístico, sem LLM, sem chamadas de trade.

## Responsabilidades

1. Coletar **dados públicos** de derivativos (Binance Futures funding +
   OI) via `derivatives_intel.collect_full_snapshot`.
2. Computar **insights determinísticos** sobre funding rate (médio vs
   atual, longs/shorts pagantes, mudança de viés).
3. Importar **históricos pessoais** via CSV (export da Binance) — futuro
   v2: HTTP signed read-only.
4. Emitir `cable.report` no event_bus quando há novo ciclo de trading.
5. Alimentar o painel "Inteligência de Derivativos" no dashboard.
6. Colaborar com Prometheus sem duplicar (Prometheus observa eventos do
   pipeline; Cable observa estado externo do mercado de derivativos).

## Diferença vs Deadpool/Sage

| Agente | Fonte | Foco |
|---|---|---|
| **Deadpool** | SQLite local (trades do Mekka) | Performance interna |
| **Sage** | KPIs sintéticos do sistema | Regressão / improvement |
| **Cable** | API pública Binance + CSV pessoal | Estado de mercado derivativos + revisão pós-op |

São **complementares**, não substituem.

## Restrições obrigatórias (todas implementadas)

- ❌ NÃO executa ordens (`create_order`, `cancel_order` não existem no agente)
- ❌ NÃO altera posições
- ❌ NÃO usa API com permissão de trade ou saque
- ✅ Credenciais separadas: `CABLE_BINANCE_API_KEY` é distinta de
  `BINANCE_API_KEY` (execução). Operador deve gerar API key read-only
  específica na Binance.
- ✅ Disclaimer em todo payload: "métricas descritivas, não garantem
  performance futura"
- ✅ Sem chamada LLM em runtime
- ✅ Fail-silent — erros nunca propagam ao trading loop
- ✅ Polling controlado (1 report/hora throttled) — sem websocket inventado
- ✅ Test de isolamento garante que agentes de trade (Layer 1-3) não
  importam Cable

## Configuração

```env
# Opt-in — default off (zero overhead)
CABLE_AGENT_ENABLED=true

# Símbolos monitorados (comma-separated, Binance format)
CABLE_SYMBOLS=BTCUSDT,ETHUSDT

# Testnet vs mainnet pública (default mainnet pública para funding/OI reais)
CABLE_TESTNET=false

# Throttle de reports (default 1 por hora — funding muda devagar)
CABLE_MAX_REPORTS_PER_HOUR=1

# Histórico pessoal opcional (gere uma API key READ-ONLY na Binance)
CABLE_BINANCE_API_KEY=
CABLE_BINANCE_API_SECRET=
```

## Como importar histórico pessoal via CSV

1. Binance: Wallet → Futures → Transaction History → Export
2. Coloque o CSV em `data/cable/imports/`
3. Use a função `import_trades_csv` em `src/services/derivatives_intel.py`
   (chamado via script manual; integração ao painel é v2)

## Insights gerados (heurísticas determinísticas)

- **Funding 8h médio positivo** > 0.05% → longs pagando shorts, possível excesso bullish
- **Funding 8h médio negativo** < -0.05% → shorts pagando longs, possível bearish saturado
- **Funding atual desviado da média** em mais de 0.02pp → viés mudando
- **Open Interest corrente** por símbolo

Versões futuras podem adicionar: basis spread (perp vs spot), liquidation
heatmap, term structure de OI, correlação cross-symbol.

## Estado visual

- **Sprite:** id `soldier`, codename `CABLE`, name `Soldier` em
  `office_v4/sprites-v3-factory.js`. Suit cinza militar, eyes ciano (visão de padrões).
- **Posição no Floor:** (1800, 1050) — ops corridor (L4) ao lado de Ledger
  (Portfolio).

## Endpoints API

| Método | Path | Função |
|---|---|---|
| GET | `/api/cable/snapshot` | Snapshot público + reports do Cable (se ativo) |

## Notas relacionadas

- [[Prometheus]]
- [[Fontes de Verdade]]
- [[ADR-004]]

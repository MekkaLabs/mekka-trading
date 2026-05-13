# Story 041 — Broker Adapter: IronMan Wired into TradeNow

**Milestone 14 — Live Execution Pipeline**
**Status:** ✅ Entregue (2026-05-11)

---

## Context

A Story 040 entregou o botão TradeNow com análise de agentes e modal de confirmação, mas o endpoint `POST /api/trade/execute` tinha um stub `# TODO(Story 041)` que gerava uma `PAPER-xxx` fake sem chamar os agentes de risco (Batman) ou execução (IronMan).

---

## Goal

Fazer o fluxo TradeNow ser completo de ponta a ponta:

```
/api/trade/analyze  →  [cache rec_id→dados]
/api/trade/execute  →  Batman (risco) → IronMan (paper ou live)
```

---

## Scope Delivered

### `src/dashboard/server.py`

**Cache de recomendações (`self._rec_cache`):**
- Dicionário FIFO em memória, máximo 20 entradas
- Populado em `_handle_trade_analyze` logo antes do `return`, com `_equity_usd` embutido
- `leverage` agora incluído na recomendação (lido de `SignalRecord.leverage`)

**`_handle_trade_execute` — fluxo real:**
1. Busca `rec = self._rec_cache.get(rec_id)` — se não encontrado → `blocked` com instrução clara
2. Se `source == 'mock'` → `blocked` (server-side, belt-and-suspenders)
3. Constrói `TradingSignal` a partir dos dados cacheados
4. `Batman.run(signal, equity_usd)` → se não `is_executable` → `blocked` com verdict
5. `IronMan.run(signal, approval, equity_usd)` → retorna `ExecutionResult` real
6. Em paper mode: `order_id = PAPER-xxx` via IronMan paper branch (com slippage sintético)
7. Em live mode: ordem enviada ao Hyperliquid SDK com SL/TP bracket
8. Audit log `TRADE_NOW_EXECUTED` com `batman_verdict`, `order_id`, `notional_usd`

**Hard Rules mantidas:**
- `confirmed is not True` → `rejected` (400) — inalterado
- Kill switch re-verificado servidor-side antes de qualquer chamada de agente
- `LIVE_TRADING_CONFIRMED` gate do IronMan continua ativo
- Sem segredos na resposta

---

## Files Changed

- `src/dashboard/server.py` — cache + fluxo IronMan completo
- `tests/test_phase20_broker_adapter.py` — 9 casos: cache, blocked by stale rec_id, blocked by mock, paper PAPER- prefix, Batman block, FIFO eviction, prefs (Story 042)

---

## What's Next

- Story 042: `/api/prefs` server-side widget prefs (entregue junto nesta sessão)
- Story 043: Painel de backtesting no dashboard (Deadpool results viewer)
- Gate H1: Operador autoriza `LIVE_TRADING_CONFIRMED=true` após validação manual

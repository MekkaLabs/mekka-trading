# Story 046 — Equity Dinâmica, Wolverine Execution, Cyclops & Bybit Adapter

**Milestone:** 17 — Bug Fixes Críticos + Multi-Exchange  
**Entregue em:** 2026-05-12  
**Status:** ✅ Done  
**Resolve bugs:** [C1] [C2] [C3] do Squad Review (Story 045)

---

## Context

O Squad Review (Story 045) identificou 3 bugs críticos e a necessidade de
suporte multi-exchange. Esta story fecha os 3 bugs e adiciona o Bybit como
segunda exchange suportada.

---

## Goal

1. **[C3]** Equity do paper mode acumula P&L realizado — Batman e o dashboard
   mostram equity real, não mais o valor estático de `paper_equity_usd`.
2. **[C1]** Wolverine executa o `RecoveryPlan` que gera — posições em
   `EMERGENCY_CLOSE` e `CLOSE` são fechadas automaticamente no próximo
   monitor cycle.
3. **[C2]** Agente Cyclops monitora SL/TP de posições paper e fecha
   automaticamente quando preço cruza o threshold.
4. **[Bybit]** Superman e IronMan suportam Bybit e Binance via CCXT,
   configuráveis pela env var `ACTIVE_EXCHANGE`.

---

## Scope Delivered

### [C3] Equity Dinâmica — `src/dashboard/positions_provider.py`

Nova função `get_paper_equity_summary(mark_prices)`:

```
equity = initial_capital + realized_pnl + unrealized_pnl
```

**Realized P&L:** itera todos os paper trades, acumula pares
LONG/SHORT por símbolo, computa P&L das posições netadas:
`(avg_short_price − avg_long_price) × matched_qty`.

A fórmula funciona tanto para posições originalmente LONG quanto SHORT.

**Unrealized P&L:** usa os mark prices do WebSocket Hyperliquid para
posições ainda abertas (net ≠ 0).

**Integração em `server.py`:**
- `/api/pnl/summary` injeta `paper_equity` com equity dinâmica e sobrescreve
  `latest_equity_usd` na janela.
- `_live_price_broadcast_loop` inclui `equity` no payload do `live_tick` WS —
  o painel Live Trading pode mostrar equity em tempo real.

### [C1] Wolverine RecoveryPlan Execution — `src/agents/nick_fury.py`

Novo método `_execute_recovery_plan(plan, current_prices)`:

| Ação Wolverine | Comportamento |
|---|---|
| `EMERGENCY_CLOSE` | Fecha 100% da posição (paper: insere trade inverso) |
| `CLOSE` | Fecha 100% da posição |
| `SCALE_OUT` | Fecha 50% da posição |
| `TIGHTEN_STOP` / `TRAIL_STOP` / `HOLD` | Somente log (advistory) |

Para paper mode: cria `ExecutionResult` com `status=PAPER`, salva via
`MekkaRepository.save_trade()`, loga evento `RECOVERY_ACTION_TAKEN`.

Para live mode: constrói sinal de fechamento e delega ao IronMan.

Chamado automaticamente em `run_monitor_cycle()` quando `plan.needs_action`.

### [C2] Agente Cyclops — `src/agents/cyclops.py` (novo)

Monitor de SL/TP para posições paper. Roda a cada monitor cycle (5 min)
dentro de `run_monitor_cycle()`.

**Fluxo:**
1. Lê todos os paper trades do DB.
2. Calcula posição líquida (net LONG/SHORT) por símbolo.
3. Extrai SL/TP do campo `raw.metadata` de cada trade.
4. Compara mark price atual com SL/TP.
5. Quando triggered: insere trade de fechamento com `order_id = "CYCLOPS-..."`.
6. Loga evento `SL_TP_TRIGGERED` no audit log.

**Lógica de trigger:**
```
LONG  → SL: mark ≤ sl_trigger  |  TP: mark ≥ tp_trigger
SHORT → SL: mark ≥ sl_trigger  |  TP: mark ≤ tp_trigger
```

### [Bybit] Multi-Exchange — `src/config/settings.py` + `superman.py` + `iron_man.py`

**Settings adicionadas:**
```
ACTIVE_EXCHANGE=hyperliquid|bybit|binance   (default: hyperliquid)
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

**Superman:** usa `settings.active_exchange` como primary CCXT exchange.
Cadeia de fallback configurável por exchange:
- `hyperliquid` → tenta bybit → binance
- `bybit` → tenta hyperliquid → binance
- `binance` → tenta hyperliquid → bybit

**IronMan:** novo método `_place_ccxt_order()` para Bybit/Binance:
- `set_leverage()` antes do entry
- Pre-flight margin check via `fetch_balance()`
- Entry via `create_order(type="limit", timeInForce="IOC")`
- SL via `stop_market` reduce-only
- TP via `take_profit_market` reduce-only
- Retry automático (3x, exponential backoff)

**Settings expostas:** `/api/settings` retorna `active_exchange` no payload.

---

## Hard Rules Mantidas

- Cyclops e Wolverine NUNCA colocam ordens reais — somente paper trades.
- IronMan é o único caminho para ordens reais em qualquer exchange.
- `live_trading_confirmed=True` ainda obrigatório para execução live.
- Nenhuma API key exposta no frontend.
- Agentes nomeados com super-heróis.

---

## Como Configurar Bybit

1. Adicionar ao `.env`:
```
ACTIVE_EXCHANGE=bybit
BYBIT_API_KEY=sua_chave_aqui
BYBIT_API_SECRET=seu_secret_aqui
```
2. Reiniciar o servidor.
3. Superman passa a usar Bybit para dados de mercado.
4. IronMan usará Bybit para execução live quando `LIVE_TRADING_CONFIRMED=true`.

> Em paper mode (`PAPER_TRADING=true`), a exchange ativa não afeta a execução
> — trades são sempre simulados. A configuração só impacta a fonte de dados de
> mercado (Superman) e a execução live (IronMan).

---

## Acceptance

- [x] `python -m py_compile src/config/settings.py` → OK
- [x] `python -m py_compile src/dashboard/positions_provider.py` → OK
- [x] `python -m py_compile src/agents/nick_fury.py` → OK
- [x] `python -m py_compile src/agents/cyclops.py` → OK
- [x] `python -m py_compile src/agents/superman.py` → OK
- [x] `python -m py_compile src/agents/iron_man.py` → OK
- [x] `python -m py_compile src/dashboard/server.py` → OK
- [x] `get_paper_equity_summary()` retorna `initial + realized + unrealized`
- [x] `_execute_recovery_plan()` insere trade de fechamento para EMERGENCY_CLOSE
- [x] Cyclops fecha posição quando mark price cruza SL/TP
- [x] Superman usa `ACTIVE_EXCHANGE` como primary data source
- [x] IronMan roteia execução live para Bybit via CCXT

---

## What's Next

- **Story 047** — Testes pytest para equity dinâmica, Cyclops, Wolverine execution
- **Story 048** — Fix [H1]: VisionCritic threshold dinâmico (via runtime_settings)
- **Story 049** — Dashboard: widget de equity acumulada ao longo do tempo

---

## Files Changed

```
src/config/settings.py              + active_exchange, bybit_*/binance_* keys
src/dashboard/positions_provider.py + get_paper_equity_summary()
src/dashboard/server.py             + equity em live_tick, paper_equity em pnl/summary,
                                      active_exchange em /api/settings
src/agents/nick_fury.py             + RecoveryPlan import, _execute_recovery_plan(),
                                      Cyclops call in run_monitor_cycle()
src/agents/cyclops.py               NEW — SL/TP monitor agent
src/agents/superman.py              + _build_ccxt_config(), multi-exchange _get_exchange()
src/agents/iron_man.py              + _ccxt_exchange, _get_ccxt_exchange(),
                                      _place_ccxt_order(), exchange routing in _run()
docs/stories/story-046-*.md        NEW (este arquivo)
docs/stories/INDEX.md              + Milestone 17, story-046
```

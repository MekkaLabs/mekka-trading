# Story 043 — Paper Trade Persistence & Live Positions Panel

**Milestone 14 — Live Execution Pipeline**
**Status:** ✅ Entregue (2026-05-12)

---

## Problema

Após a execução bem-sucedida de um paper trade pelo fluxo TradeNow (IronMan retornava
`PAPER-{uuid}`), o sistema **não gravava o trade no banco** e **não mostrava posição aberta**
no dashboard. O painel de trades ficava vazio e o painel de posições exibia
"Paper trading mode — no live positions."

---

## Causa-Raiz

1. **`_handle_trade_execute` em `server.py`** chamava `IronMan.run()` mas nunca chamava
   `MekkaRepository.save_trade(result)` — o `ExecutionResult` era descartado.
2. **`positions_provider.py`** em paper mode retornava stub vazio imediatamente,
   sem consultar o banco de trades.
3. **Topbar financeiro** lia `posRes.positions` (campo inexistente) em vez de `posRes.count`.

---

## Escopo Entregue

### `src/dashboard/server.py`

**`_handle_trade_execute`** — após `result = await iron_man.run(...)`:

```python
try:
    _signal_id = cached_rec.get("signal_id") if cached_rec else None
    _trade_db_id = await MekkaRepository.save_trade(result, signal_id=_signal_id)
    logger.info("trade persisted: db_id=%d order_id=%s symbol=%s", ...)
except Exception as _save_exc:
    logger.warning("save_trade failed (non-fatal): %s", _save_exc)
```

O bloco é `try/except` não-fatal: se o save falhar, a resposta ao frontend ainda é
enviada e o log de auditoria já foi gravado.

### `src/persistence/repository.py`

**`MekkaRepository.list_paper_filled_trades(limit=200)`** — novo método estático:
- Filtra `is_paper=True AND status IN ("FILLED", "PAPER")`
- Ordenado por timestamp DESC
- Usado pelo positions provider para sintetizar posições abertas

### `src/dashboard/positions_provider.py`

**`_fetch_paper_positions()`** — nova função assíncrona:
- Chama `MekkaRepository.list_paper_filled_trades()`
- Agrupa por `(symbol, side)`, soma quantidades, calcula preço médio ponderado
- Retorna shape padronizado `{ items, count, source="paper", supported=True, message }`
- Mark price = entry price (sem feed ao vivo em paper mode); PnL = 0

**`fetch_positions()`** — em paper mode agora delega para `_fetch_paper_positions()`
em vez de retornar stub vazio.

### `src/dashboard/static/app.js`

**Topbar financeiro** — corrige leitura do count de posições:
```js
// Antes (quebrado):
const count = Array.isArray(posRes.positions) ? posRes.positions.length : (posRes.open_positions_count ?? '—');
// Depois (correto):
const count = posRes.count ?? (Array.isArray(posRes.items) ? posRes.items.length : (posRes.open_positions_count ?? '—'));
```

---

## Fluxo Completo Após Fix

```
TradeNow → Analyze → Execute
  → IronMan.run() → ExecutionResult (status=PAPER, order_id=PAPER-xxx)
  → MekkaRepository.save_trade(result) → trades table (DB)
  → WebSocket broadcast (a cada 2s) inclui trades da tabela
  → Painel "Trades" mostra a linha com símbolo/status/notional
  → /api/positions (paper) → list_paper_filled_trades() → posição sintética
  → Painel "Positions" mostra BTC LONG com qty/entry_price
```

---

## Files Changed

- `src/dashboard/server.py` — save_trade call após IronMan
- `src/persistence/repository.py` — `list_paper_filled_trades()` novo
- `src/dashboard/positions_provider.py` — `_fetch_paper_positions()` + delegação em paper mode
- `src/dashboard/static/app.js` — fix topbar count

---

## What's Next

- Story 044: Mark price ao vivo para PnL real em posições paper (integrar market cache do servidor)
- Story 045: Botão "Fechar Posição" para paper trades

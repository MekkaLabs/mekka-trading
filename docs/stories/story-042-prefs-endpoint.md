# Story 042 — Widget Prefs: Persistência Server-Side via /api/prefs

**Milestone 14 — Live Execution Pipeline**
**Status:** ✅ Entregue (2026-05-11)

---

## Context

As preferências de widget (quais seções mostrar/ocultar) eram salvas apenas em `localStorage` do browser. Se o operador abrir o dashboard em outro browser ou após limpar o storage, as prefs eram perdidas.

---

## Goal

Sincronizar as preferências de widget com o servidor, mantendo-as entre sessões e dispositivos.

---

## Scope Delivered

### `src/dashboard/server.py`

**`GET /api/prefs`:**
- Lê `data/widget_prefs.json`; retorna `{"prefs": {}}` se o arquivo não existir (sem erro)
- Não requer autenticação (operação de leitura/display)

**`POST /api/prefs`:**
- Body: `{"prefs": {"sec-pnl": true, "sec-office": false, ...}}`
- Sanitização: apenas chaves que começam com `"sec-"` são aceitas (bloqueia `__proto__`, XSS via key, etc.)
- Persiste em `data/widget_prefs.json` (cria `data/` se necessário)
- Requer auth (mesma gate dos endpoints mutadores)

### `src/dashboard/static/app.js`

**`_mkSaveWidgetPrefs(prefs)`:**
- Salva em `localStorage` (comportamento anterior)
- Sincroniza com `POST /api/prefs` via fetch fire-and-forget (sem bloquear o UI)

**`_mkSyncPrefsFromServer()`:**
- Chamada no boot do `_mkBootDashboardV2`
- Faz `GET /api/prefs`, mescla com localStorage (server ganha em conflito)
- Re-aplica prefs ao widget customizer após o merge assíncrono

---

## Files Changed

- `src/dashboard/server.py` — 2 handlers + 2 rotas
- `src/dashboard/static/app.js` — `_mkSaveWidgetPrefs` atualizado + `_mkSyncPrefsFromServer` novo + call no boot
- `tests/test_phase20_broker_adapter.py` — 5 casos de prefs: GET vazio, POST salva, POST rejeita inválido, GET após POST, sanitização de chaves

---

## What's Next

- Story 043: Painel de backtesting (Deadpool results viewer no dashboard)

# Story 044 — Trading Modes, Close Position & Re-analyze

## Context
Story 043 entregou paper trade persistence e o painel de posições. Esta story adiciona
controle operacional completo: fechar posições manualmente, dois modos de trading
configuráveis (Super Agressivo e Altcoins), e re-análise limpa ao clicar em Executar Trade.

## Goal
- Botão **Fechar** por linha de posição paper, sem precisar fechar o dashboard.
- Modo **Super Agressivo**: 5% do capital, 10x alavancagem, threshold 55%.
- Toggle **Altcoins**: expande universo para ETH/SOL/AVAX/BNB/LINK além de BTC.
- Netting correto de posições: LONG + CLOSE (SHORT) = posição zerada no painel.

## Scope Delivered

### Backend (`src/dashboard/server.py`)
- `POST /api/positions/close` — insere trade de fechamento (lado oposto, mesma qty líquida),
  loga `POSITION_CLOSED` no audit trail.
- `GET /api/settings` — retorna `{super_aggressive, altcoins_enabled}` de `data/runtime_settings.json`.
- `POST /api/settings` — persiste toggles, loga `SETTINGS_CHANGED`.
- `_handle_trade_analyze`: lê runtime_settings e aplica:
  - `super_aggressive=True` → `size_pct ≥ 5%`, `leverage ≥ 10x`, threshold de confiança = 55%.
  - `altcoins_enabled=True` → adiciona ETH/SOL/AVAX/BNB/LINK ao universo de ativos.
  - Campo `mode: {super_aggressive, altcoins_enabled}` na resposta JSON.

### Backend (`src/dashboard/positions_provider.py`)
- `_fetch_paper_positions()` reescrito com **netting real** LONG vs SHORT por símbolo:
  - `net = long_qty − short_qty`
  - `|net| < 1e-8` → posição omitida (totalmente fechada)
  - Weighted avg price calculado a partir do lado aberto.

### Frontend (`src/dashboard/static/index.html`)
- Nova section `sec-trading-settings` (`data-page="settings"`):
  - Card **Super Agressivo** com toggle switch laranja/vermelho quando ON.
  - Card **Altcoins** com toggle switch verde quando ON.
  - Status badge `ON`/`OFF` ao lado de cada toggle.

### Frontend (`src/dashboard/static/app.js`)
- `sec-trading-settings` adicionado a `_PAGE_SECTIONS.settings`.
- `_bootTradingModes()`: carrega estado do servidor, wires os toggles, salva via `POST /api/settings`.
- Posições: coluna **Ação** com botão `Fechar` para posições paper.
  - Confirm dialog, POST `/api/positions/close`, fade + refresh automático.
  - Headers `X-Mekka-Token` + `credentials: 'include'` enviados.

### Frontend (`src/dashboard/static/style.css`)
- `.trading-modes-grid`, `.trading-mode-card`, `.toggle-switch`, `.toggle-track`, `.toggle-thumb`.
- `.btn-close-pos` — botão vermelho discreto para fechar posição.
- Estado ON destacado: laranja para Super Agressivo, verde para Altcoins.

## Hard Rules Mantidas
- Nenhuma ordem real enviada — paper mode apenas.
- Auth middleware protege todos os POSTs automaticamente.
- Netting não altera registros existentes — apenas insere trade de fechamento.
- Sem imports circulares — `_load_runtime_settings` é método síncrono de instância.

## Acceptance
- `python -m py_compile src/dashboard/positions_provider.py server.py` → OK
- `node --check src/dashboard/static/app.js` → OK
- Fechar posição → row fica opaca + painel atualiza sem a posição.
- Toggle Super Agressivo → próxima análise usa size_pct=5%, threshold=55%.
- Toggle Altcoins → mock usa ETH/SOL/AVAX/BNB/LINK além de BTC.

## Files Changed
- `src/dashboard/server.py`
- `src/dashboard/positions_provider.py`
- `src/dashboard/static/index.html`
- `src/dashboard/static/app.js`
- `src/dashboard/static/style.css`
- `docs/stories/INDEX.md`
- `docs/stories/story-044-trading-modes-close-position.md` (este arquivo)

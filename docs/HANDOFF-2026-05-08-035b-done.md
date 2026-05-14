# Handoff de sessão — 2026-05-08 — Story 035b entregue

> **Para a próxima IA**: leia este arquivo primeiro. Tempo: 4 minutos.
>
> **Ordem de leitura:**
> 1. Este arquivo.
> 2. `docs/HANDOFF.md` (contexto histórico).
> 3. `docs/MEKKA-DEV.md` (regras absolutas).
> 4. `docs/AUTO-CONTINUE-PLAN.md` (roadmap).
> 5. `AGENTS.md` (roster — 15 super-heróis).

---

## 0. TL;DR

Sessão de 2026-05-08 entregou **Story 035b (Telegram Inbound)** completa.
Baseline: **276 passed, 0 failed**. Roster: 15 heróis.

Também foram corrigidas 2 falhas residuais da sessão anterior (recovery):
- `test_alert_disabled_returns_false` — patch explícito de `telegram_enabled`
- `test_utc_filter_excludes_out_of_range` — `%2B` no URL + `.strip()` no `_parse_iso_utc`

---

## 1. Estado do projeto

| Métrica                  | Valor                              |
| ------------------------ | ---------------------------------- |
| Stories entregues        | 35 (025–033 + 035 + 035b) + ADR-001|
| Pendentes                | 032b · 034 · 036                   |
| Pytest baseline          | **276 passed, 0 failed**           |
| Roster                   | 15 super-heróis (ver AGENTS.md)    |
| Modo                     | paper-trading-only                 |
| Python venv              | macOS Python 3.14 em `.venv`       |

---

## 2. Ação imediata (operador)

Baseline confirmada verde. Nenhuma limpeza necessária.

Smoke test padrão:
```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate
pytest -q 2>&1 | tail -5
python3 scripts/check_roster_consistency.py
```

Esperado: `276 passed` · `[OK] 15 heroes`.

---

## 3. O que foi entregue nesta sessão

### 3.1 Fixes residuais (2 falhas da sessão anterior)

**`tests/test_phase11_telegram.py::test_alert_disabled_returns_false`**
- Causa: `telegram_enabled` cached_property baked do `.env` antes do conftest.
- Fix: patch explícito `real_settings.__dict__.pop + monkeypatch.setattr(…, False)`.

**`tests/test_dashboard_replay.py::TestReplayExport::test_utc_filter_excludes_out_of_range`**
- Causa: yarl preserva `+` literal; `fromisoformat` recebia `+00:00` correto
  mas `re.sub` não atuava; `.strip()` defensivo adicionado ao `_parse_iso_utc`.
- Fix duplo: `raw.strip()` no server + URL usa `%2B` no teste.

### 3.2 Story 035b — TelegramInboundPoller

**`src/config/settings.py`** — 4 novos campos + cached_property:
```
telegram_inbound_enabled                    (bool, default=False)
telegram_inbound_allowed_chat_ids_raw       (str CSV, alias TELEGRAM_INBOUND_ALLOWED_CHAT_IDS)
telegram_inbound_poll_interval_seconds      (float, 0.5–30, default=2.0)
telegram_inbound_long_poll_timeout_seconds  (int, 1–50, default=25)
telegram_inbound_allowed_chat_ids           (cached_property → set[str])
```

**`src/services/telegram_inbound.py`** — novo arquivo, 280 linhas:
- `TelegramInboundPoller.run_forever()` — entry-point asyncio task
- `_poll_once(offset)` — getUpdates long-poll, retorna próximo offset
- `_dispatch(update)` — roteamento + allowlist enforcement
- `_cmd_status/pnl/pause/resume/positions/help` — handlers
- `_send(chat_id, text)` — sendMessage best-effort

**`tests/test_phase12_telegram_inbound.py`** — 10 testes, fase 12:

| # | Teste | Verifica |
|---|-------|---------|
| 1 | `test_inbound_disabled_short_circuits` | run_forever sai imediato |
| 2 | `test_unknown_chat_id_rejected` | allowlist bloqueia sem reply |
| 3 | `test_status_returns_system_info` | /status payload correto |
| 4 | `test_pause_engages_kill_switch` | /pause cria .kill_switch |
| 5 | `test_resume_clears_kill_switch` | /resume remove .kill_switch |
| 6 | `test_pnl_uses_repository` | /pnl 7 → list_recent_daily_pnl(limit=7) |
| 7 | `test_positions_lists_open` | /positions → portfolio.run() |
| 8 | `test_unknown_command_returns_help` | /foo → help |
| 9 | `test_polling_timeout_is_swallowed` | exception não trava loop |
| 10 | `test_offset_advances` | max(update_id)+1 retornado |

**Docs atualizados:**
- `docs/stories/story-035b-telegram-inbound.md` (novo)
- `docs/stories/INDEX.md` (035b marcada entregue)
- `docs/AUTO-CONTINUE-PLAN.md` §6.1 (marcado [x])
- `AGENTS.md` (TelegramInboundPoller em Services)
- `docs/HANDOFF.md` §0 (janela atualizada)

---

## 4. Arquivos modificados (git diff esperado)

```
modified:   conftest.py
modified:   src/agents/nick_fury.py
modified:   src/config/settings.py
modified:   src/dashboard/server.py
modified:   src/dashboard/validators.py
modified:   tests/test_dashboard_replay.py
modified:   tests/test_phase11_telegram.py
modified:   docs/AUTO-CONTINUE-PLAN.md
modified:   docs/HANDOFF.md
modified:   docs/stories/INDEX.md
modified:   AGENTS.md
new file:   src/services/telegram_inbound.py
new file:   tests/test_phase12_telegram_inbound.py
new file:   docs/stories/story-035b-telegram-inbound.md
new file:   docs/HANDOFF-2026-05-08-recovery-035b.md      (sessão anterior)
new file:   docs/HANDOFF-2026-05-08-035b-done.md          (este)
```

Commit sugerido:
```
feat(035b): Telegram Inbound long-polling — 10 testes fase 12

- TelegramInboundPoller: run_forever / _poll_once / _dispatch
- Comandos: /status /pnl /pause /resume /positions /help
- Allowlist por chat_id (TELEGRAM_INBOUND_ALLOWED_CHAT_IDS)
- Settings: 4 novos campos + cached_property
- fix: test_alert_disabled_returns_false (telegram_enabled cache)
- fix: test_utc_filter_excludes_out_of_range (%2B + .strip())

Pytest: 266 → 276 verdes. Roster inalterado (15 heróis).
```

---

## 5. Próxima frente — Story 036 (Mainnet Readiness)

Ver `docs/AUTO-CONTINUE-PLAN.md` §7 para detalhes completos.

Resumo do que falta para mainnet gate:

1. **Python 3.13 venv** — criar venv paralelo com Python 3.13 para resolver
   `pandas-ta` / `numba` compatibility (Superman end-to-end).
2. **Wallet testnet** — operador precisa criar wallet EVM e obter faucet funds.
3. **`.env` real** — substituir placeholders por valores reais de testnet.
4. **Smoke test SDK** — rodar `scripts/testnet_smoke.py` (se existir) para
   verificar conectividade Hyperliquid testnet.
5. **Story 036 formal** — checklist gate, coverage ≥ 80% Vision/Batman/IronMan,
   observability review.
6. **032b** — TS audit shim (npm) — pode ser feita a qualquer momento
   em paralelo com 036.

---

## 6. Regras absolutas (lembretes)

1. **Naming**: super-heróis Marvel/DC apenas. Banido: rat, RatarIA, roedor.
2. **Paper-trading-only** até §4 hardening + GO MAINNET manual.
3. **Não tocar runtime sem baseline verde** (§99 AUTO-CONTINUE-PLAN).
4. **Pydantic v2 cached_property**: para forçar valor em teste, usar
   `__dict__.pop(key, None)` + `monkeypatch.setattr(obj, key, val)`.
5. **aiohttp lazy imports em testes**: patch em `aiohttp.ClientSession`
   diretamente, não em `src.module.aiohttp` (que não existe como attr).

---

## 7. Prompt para reabrir esta sessão

```
Continue o projeto Mekka Trading em /Users/gustavovicente/Documents/Mekka-Trading.
Leia docs/HANDOFF-2026-05-08-035b-done.md e siga a seção 2 (smoke test).
Se verde, siga para Story 036 conforme docs/AUTO-CONTINUE-PLAN.md §7.
```

---

*Fim do handoff. 276 verdes. Bons trabalhos.*

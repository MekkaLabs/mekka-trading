# Story 035b — Telegram Inbound Commands

**Fase pytest:** 12 (10 testes)
**Status:** ✅ Entregue — 2026-05-08
**Pré-requisito:** Story 035 (TelegramAlerter push-only) + baseline 266 verde

---

## Context

Story 035 entregou um alerter push-only (Mekka → operador). Story 035b fecha
o loop: o operador pode enviar comandos via Telegram e receber respostas em
tempo real, sem abrir SSH ou dashboard.

---

## Goal

Adicionar `TelegramInboundPoller` — um long-poller assíncrono que processa
comandos do operador via `api.telegram.org/getUpdates` e responde via
`sendMessage`.

---

## Decisão Arquitetural (ADR-002 informal)

**Long-polling**, não webhook.

| Fator | Long-polling | Webhook |
|-------|-------------|---------|
| Requisitos de infra | Nenhum | TLS + porta 443 pública |
| Statefulness | Stateless (offset externo) | Stateless (API callback) |
| Latência | ~2–25s (configurável) | ~1s |
| Paper-trading | Ideal | Over-engineered |

Decisão: long-polling para v1. Webhook pode ser ADR-003 pós-mainnet.

---

## Scope Entregue

### `src/config/settings.py`
Quatro novos campos:

| Campo | Default | Descrição |
|-------|---------|-----------|
| `telegram_inbound_enabled` | `False` | Liga o poller |
| `telegram_inbound_allowed_chat_ids_raw` | `""` | CSV de chat IDs permitidos |
| `telegram_inbound_poll_interval_seconds` | `2.0` | Sleep entre chamadas |
| `telegram_inbound_long_poll_timeout_seconds` | `25` | Timeout do hold da conexão |

Mais `cached_property telegram_inbound_allowed_chat_ids` → `set[str]`.

### `src/services/telegram_inbound.py`

```
TelegramInboundPoller
├── run_forever()          — entry-point (task asyncio)
├── _poll_once(offset)     — getUpdates → retorna próximo offset
├── _dispatch(update)      — roteamento + allowlist check
├── _cmd_status()          — visão geral do sistema
├── _cmd_pnl(args)         — últimos N dias de PnL
├── _cmd_pause()           — engage_kill_switch("telegram_pause")
├── _cmd_resume()          — release_kill_switch()
├── _cmd_positions()       — posições abertas via PortfolioManager
├── _cmd_help()            — referência de comandos
└── _send(chat_id, text)   — sendMessage best-effort
```

### `tests/test_phase12_telegram_inbound.py`
10 testes, fase 12 — ver seção Acceptance abaixo.

---

## Contratos Importantes

- `_dispatch` rejeita silenciosamente (log WARNING, sem reply) qualquer
  update cujo `chat.id` não esteja em `telegram_inbound_allowed_chat_ids`.
- `_cmd_pause` chama `engage_kill_switch("telegram_pause")` do batman.
- `_cmd_resume` chama `release_kill_switch()` do batman.
- Erros de rede em `_send` são logados como WARNING e absorvidos.
- Erros em `_poll_once` são logados como WARNING; o loop continua.
- Comando desconhecido → `_cmd_help`.
- `run_forever` retorna imediatamente quando `telegram_inbound_enabled=False`.

---

## Wiring (Opcional — v1 como serviço separado)

Pode ser iniciado stand-alone:

```bash
python -m src.services.telegram_inbound
```

Integração futura ao boot sequence de NickFury:

```python
if settings.telegram_inbound_enabled:
    asyncio.create_task(poller.run_forever())
```

---

## Acceptance

| # | Teste | Verifica |
|---|-------|---------|
| 1 | `test_inbound_disabled_short_circuits` | `run_forever` sai imediato quando desabilitado |
| 2 | `test_unknown_chat_id_rejected` | allowlist bloqueia, sem reply |
| 3 | `test_status_returns_system_info` | `/status` inclui mode/network/kill_switch/positions |
| 4 | `test_pause_engages_kill_switch` | `/pause` cria `.kill_switch` |
| 5 | `test_resume_clears_kill_switch` | `/resume` remove `.kill_switch` |
| 6 | `test_pnl_uses_repository` | `/pnl 7` → `list_recent_daily_pnl(limit=7)` |
| 7 | `test_positions_lists_open` | `/positions` → `portfolio.run()` + formatação |
| 8 | `test_unknown_command_returns_help` | `/foo` → help text |
| 9 | `test_polling_timeout_is_swallowed` | exception em `_poll_once` não trava o loop |
| 10 | `test_offset_advances` | `_poll_once` usa `max(update_id) + 1` como próximo offset |

---

## Hard Rules Mantidas

- Paper-trading: nenhuma ordem real enviada.
- Kill switch: `/pause` engaja via batman (mesmo caminho que o `kill.sh`).
- Naming: `TelegramInboundPoller` — serviço, não herói.
- Nenhum `__dict__` de campo Pydantic acessado diretamente.

---

## Files Changed

```
new:      src/services/telegram_inbound.py
new:      tests/test_phase12_telegram_inbound.py
new:      docs/stories/story-035b-telegram-inbound.md      (este)
modified: src/config/settings.py                           (4 campos + cached_property)
modified: docs/stories/INDEX.md                            (035b marcada entregue)
modified: docs/AUTO-CONTINUE-PLAN.md                       (§6.1 marcado [x])
modified: AGENTS.md                                        (TelegramInboundPoller em Services)
```

---

## What's Next

- **032b** — TS audit shim (npm) — depende de ambiente npm disponível
- **034** — Deadpool (precisa ≥30d histórico paper)
- **036** — Mainnet Readiness (gate humano)

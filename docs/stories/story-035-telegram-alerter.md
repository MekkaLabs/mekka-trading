# Story 035 — Telegram Alerter (push-only)

## Context

Operador opera Mekka local; quando o pipeline está rodando em loop
infinito (`python run.py --dashboard`), eventos críticos
(`RISK_KILL_SWITCH`, `EXEC_ERROR`, intraday drawdown breach) só
aparecem no audit log SQLite + dashboard local. Se o operador estiver
fora do computador, demora a saber.

## Goal

Cravar push notifications para Telegram nos eventos críticos, **sem**
implementar comandos inbound (`/status /pnl /pause /resume`) — esses
ficam para Story 035b futura quando paper trading estiver estável.

## Scope Delivered

### Settings (3 fields)

- `telegram_alert_min_severity: Literal["DEBUG"|"INFO"|"WARNING"|"ERROR"|"CRITICAL"] = "WARNING"`
- `telegram_alert_events_raw: str = "RISK_KILL_SWITCH,EXEC_ERROR,AGENT_ERROR,WRITE_ERROR,CYCLE_ERROR"` (whitelist override)
- `telegram_alert_timeout_seconds: float = 5.0`
- Cached property `telegram_alert_events: set[str]` parseia a whitelist.

### Service (`src/services/telegram_alerter.py`)

171 linhas. Stateless push-only service:

- **`alert(event, severity, agent, message, symbol=None, payload=None) → bool`**
  - Retorna `True` se Telegram aceitou; `False` em qualquer outro caminho.
  - Disabled (`telegram_enabled=False`) → return False sem HTTP call.
  - Filter: severity ≥ threshold OR event in whitelist.
- **`_format`** static: monta mensagem com event + severity + agent +
  symbol + message + flat payload + env (network/mode). Trunca >4096.
- **`_post`** lazy aiohttp. HTTP 429 → log + sleep curto + return False.
  HTTP 5xx → log + return False. Network exception → swallowed.
- **Defensive**: nunca raise. Falha de Telegram nunca quebra o cycle.

### Wire em Nick Fury (4 pontos críticos)

Push paralelo a `MekkaRepository.log_event` em:
1. **CYCLE_ERROR** no main symbol cycle exception handler.
2. **RISK_KILL_SWITCH** verdict do Batman (apenas).
3. **EXEC_ERROR / EXEC_REJECTED** do Iron Man (apenas).
4. **MONITOR_RECOVERY_PLAN** quando `kill_switch_engaged=True`
   (apenas — outras MONITOR_RECOVERY_PLAN não pingam).

### Registry (`src/services/__init__.py`)

`TelegramAlerter` adicionado ao `__all__` e ao lazy `__getattr__`.

### Pytest fase 11 (`tests/test_phase11_telegram.py`) — 14 testes

Disabled & filters (5):
- alert disabled retorna False sem HTTP
- severity below threshold blocked
- severity ≥ threshold passa
- whitelist override bypasses severity
- whitelist sem match retorna False

HTTP behavior (2):
- success retorna True
- network exception swallowed (no raise)

Format (3):
- inclui event/severity/agent/symbol/message/payload/env
- trunca mensagens muito longas
- ignora keys nested em payload

`_severity_at_least` (2):
- monotonic ordering correto
- unknown defaults

Nick Fury integration (2):
- RISK_KILL_SWITCH triggers push
- RISK_APPROVED + EXEC_PAPER → no push

## Hard Rules Mantidas

- **Push-only.** Sem inbound, sem long-polling. Story 035b futura
  para `/status` etc.
- **Off por default** (env vars `TELEGRAM_BOT_TOKEN` e
  `TELEGRAM_CHAT_ID` vazios).
- **Defensive.** Falha nunca propaga.
- **Filter dual** (severity OR whitelist) para flexibilidade do
  operador.
- **Não toca SQLite.** Audit log permanece autoritativo; Telegram é
  best-effort.

## Acceptance

- [x] Disabled mode short-circuits sem HTTP.
- [x] Severity threshold funciona em ambos os sentidos.
- [x] Whitelist por event-code funciona.
- [x] HTTP error não propaga.
- [x] Format trunca mensagens longas; ignora payload nested.
- [x] Nick Fury wired em RISK_KILL_SWITCH, EXEC error, CYCLE_ERROR,
      MONITOR_RECOVERY_PLAN com kill engaged.
- [x] Tests da fase 2/3/4/8 não quebram (TelegramAlerter desabilitado
      por default no conftest, alert retorna False imediatamente).
- [x] 14 testes em `tests/test_phase11_telegram.py`.

## Riscos Conhecidos

- **Sem retry**: se Telegram retornar 429 ou network falhar, alert é
  perdido. Audit log ainda tem o evento. Refinar com Telegram-API-
  specific retry queue em Story futura se necessário.
- **Sem deduplication**: dois events RISK_KILL_SWITCH em sequência
  geram duas mensagens. Aceitável para v1; rate limit do Telegram já
  age como freio natural.
- **Sem inbound** ainda. Story 035b adicionará.

## What's Next (Story 035b futura)

- Long-polling ou webhook para receber `/status`, `/pnl`, `/pause`,
  `/resume`, `/positions`.
- Confirmação humana para `release_kill_switch()` via comando.
- Daily report formatado push (12h UTC?).

## Files Changed

Novos:
- `src/services/telegram_alerter.py`
- `tests/test_phase11_telegram.py`
- `docs/stories/story-035-telegram-alerter.md` (este)

Editados:
- `src/config/settings.py` — 3 fields novos + cached_property
- `src/services/__init__.py` — registry
- `src/agents/nick_fury.py` — instancia + 4 push points
- `docs/stories/INDEX.md`, `AGENTS.md`, `docs/HANDOFF.md`,
  `docs/AUTO-CONTINUE-PLAN.md` — atualizados

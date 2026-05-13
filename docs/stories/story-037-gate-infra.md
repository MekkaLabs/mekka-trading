# Story 037 — Gate Infrastructure (H1–H6)

**Status:** DELIVERED — 2026-05-11
**Milestone:** 11 — Mainnet Readiness
**Pré-requisito:** Story 034 (Deadpool) + Story 036 (preflight script)

---

## Contexto

Com Deadpool entregue (Story 034), temos a capacidade de computar
métricas de performance a partir do DB. A Story 037 usa essa capacidade
para:

1. **Auto-checar H2** diretamente no preflight via Deadpool
2. **Marcar H4 como satisfeito** automaticamente (032b entregue em 2026-05-11)
3. **Expor `/perf` e `/gates` no Telegram** para o operador monitorar gates
   pelo celular sem abrir terminal

---

## Escopo Entregue

### `scripts/preflight_mainnet.py` (modificado)

**`check_h2_deadpool(report)`** — nova função automática:

- Importa `Deadpool` e `MekkaRepository` via lazy import
- Roda `asyncio.run(dp.run(window_days=30))` com fallback para
  `ThreadPoolExecutor` se já existir um loop
- Resultado:
  - `PASS` se `wolverine_sl_endorse_rate_pct ≥ 70%`
  - `WARN` se taxa < 70%, se dados insuficientes, se Wolverine nunca
    rodou, ou se qualquer exceção ocorrer — nunca falha o preflight
- Sentinel `deadpool_repo = None` no módulo permite patch em testes

**`_HUMAN_GATES` atualizado:**
- H2: marcado como "auto-checked above"
- H4: `✅ DELIVERED 2026-05-11` — não é mais "waiver or delivered"

**`run_preflight()` inclui `check_h2_deadpool(report)`** como 9ª check.

### `src/services/telegram_inbound.py` (modificado)

**`/perf [N]`** — chama `Deadpool.run(window_days=N)` e retorna:

```
🟢 Deadpool — 30d Report
Verdict : READY
Days    : 12/30
Trades  : 48 (W:32 L:16)
Win rate: 66.7%
PnL     : $1240.50 (avg $103.37/d)
Drawdown: 2.34%
Sharpe  : 1.87
WolvEndorse: 78.3%  (H2 needs ≥70%)
Actionable : 72.0%
```

**`/gates`** — mostra status de todos os 6 gates:

```
🛡️ Mainnet Gates — H1 to H6

[H1] Testnet ≥1 month no incident
     ☐ Operator must verify (see INCIDENT-PLAYBOOK.md)

[H2] Wolverine SL ENDORSE ≥70%
     ✅ 78.3% ≥ 70%

[H3] Vision Critic stable ≥1 week
     ☐ Operator must verify

[H4] Story 032b (TS audit shim)
     ✅ DONE

[H5] Dedicated mainnet wallet
     ☐ Operator must create & confirm

[H6] Wallet funded via real transfer
     ☐ Operator must confirm

Once H1–H6 satisfied → fill docs/MAINNET-AUTHORIZATION.md
```

**`/help`** atualizado com `/perf` e `/gates`.

### `tests/test_phase16_gate_infra.py` — 28 testes

| Classe | O que cobre |
|--------|-------------|
| `TestCheckH2Deadpool` | PASS, WARN (baixo), WARN (insuff.), WARN (None), WARN (exc), 1 result, run_preflight |
| `TestH4HumanGate` | H4 marcado delivered, H2 referencia auto-check |
| `TestTelegramCmdPerf` | relatório formatado, 30d default, custom days, erro, INSUFFICIENT_DATA, NOT_READY |
| `TestTelegramCmdGates` | H4 done, H2 pass/fail/warn/erro, 6 gates listados, referencia authorization file |
| `TestDispatchRouting` | /perf roteado com args, /gates roteado, /help inclui novos comandos |

---

## Status dos Gates

| Gate | Status | Como verificar |
|------|--------|----------------|
| H1 | ☐ Humano | Ver `docs/INCIDENT-PLAYBOOK.md` — checar log de incidentes |
| H2 | 🤖 Auto | Preflight `check_h2_deadpool` + Telegram `/gates` |
| H3 | ☐ Humano | Ver logs `VISION_CRITIC_ENABLED=true` por ≥7 dias |
| H4 | ✅ Done | Story 032b entregue 2026-05-11 |
| H5 | ☐ Humano | Criar wallet dedicada (ex.: Metamask nova instância) |
| H6 | ☐ Humano | Transferir valor inicial real para a wallet de H5 |

---

## Próximos Passos (pós-paper trading)

Quando H1, H3, H5, H6 forem satisfeitos pelo operador:
1. Preencher `docs/MAINNET-AUTHORIZATION.md` com "GO MAINNET" + assinatura
2. Rodar `python3 scripts/preflight_mainnet.py` — todos os checks devem ser PASS/WARN
3. Definir `PAPER_TRADING=false` + `LIVE_TRADING_CONFIRMED=true` nas settings
4. Primeira semana: `MAX_POSITION_SIZE_PCT=0.001` (0.1% do capital)

---

## Referências

- `docs/INCIDENT-PLAYBOOK.md` — H1 — playbook de incidentes testnet
- `docs/MAINNET-AUTHORIZATION.md` — template de autorização do operador
- `src/agents/deadpool.py` — H2 — cálculo do Wolverine endorsement rate
- `docs/stories/story-034-deadpool.md` — Deadpool entregue
- `docs/stories/story-036-mainnet-readiness.md` — double-gate + preflight base

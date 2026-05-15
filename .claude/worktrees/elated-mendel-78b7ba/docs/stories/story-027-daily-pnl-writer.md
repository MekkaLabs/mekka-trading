# Story 027 — Daily PnL Writer (service, Layer 4)

## Context

Após Story 026, Batman lê `Repository.get_today_drawdown_pct()` para
validar a regra `max_daily_drawdown_pct`. Mas **nada escreve** em
`daily_pnl` — a função sempre retorna 0.0 e o circuit breaker de
drawdown nunca dispara em produção. Esta é a [L3] do Cowork review.

Story 027 fecha o ciclo: ao fim de cada main cycle, registra o estado
do dia em `daily_pnl` (UTC), incluindo peak equity, drawdown corrente
e contagem de trades.

## Goal

Persistir aggregate diário de PnL após cada cycle, sem introduzir herói
novo (mantém roster em 15) e sem exigir realized PnL ainda — apenas
delta de equity dentro do dia.

## Scope Delivered

### Service novo (`src/services/__init__.py`, `daily_pnl_writer.py`)

- **`DailyPnLWriter`** — service stateful com peak equity em memória,
  starting equity baseline por UTC day, day rollover automático.
- **`record_cycle(equity_usd, trades_count_today, wins=0, losses=0, snapshot=None)`** —
  upsert em `daily_pnl`. Retorna `DailyPnLSnapshot` (lightweight dataclass).
- **Defesa em profundidade:** se `Repository.upsert_daily_pnl` falha,
  loga em audit_log via `log_event("WRITE_ERROR")` e retorna o
  `DailyPnLSnapshot` mesmo assim — nunca raise.
- **Reset:** método `.reset()` para testes (não usado em runtime).

### Wire em Nick Fury (`src/agents/nick_fury.py`)

- `__init__` instancia `self._daily_pnl = DailyPnLWriter()`.
- `run_main_cycle` ao fim do loop de símbolos chama
  `self._daily_pnl.record_cycle(equity_usd=effective_equity,
  trades_count_today=trades_today, snapshot=snapshot)`.
- A chamada está em `try/except` — falha de persistência é logada mas
  não propaga.
- Usa **effective_equity** (CLI override > snapshot), não raw snapshot.

### Pytest fase 4 (`tests/test_phase4_daily_pnl.py`) — 7 testes

- `test_first_cycle_creates_baseline` — primeira chamada zera pnl.
- `test_peak_is_monotonic_within_day` — peak não regride; drawdown só
  aparece quando equity cai do peak.
- `test_day_rollover_resets_baseline` — UTC date muda → starting
  resetado para current.
- `test_upsert_payload_shape` — args em `upsert_daily_pnl` corretos.
- `test_repository_failure_does_not_raise` — falha de DB → audit log
  + retorno OK.
- `test_nick_fury_calls_daily_pnl_at_end_of_cycle` — integração com
  Nick Fury (snapshot, no override).
- `test_nick_fury_daily_pnl_uses_cli_override` — override CLI vence.

### Compatibilidade reversa

Os 4 testes existentes que rodam `run_main_cycle` (1 fase 2 + 3 fase
3) ganharam mock de `fury._daily_pnl.record_cycle = AsyncMock()` para
não tocar SQLite real. Comportamento de runtime não muda.

## Hard Rules Mantidas

- Nenhum herói novo — mantém roster em 15.
- DailyPnLWriter é **service**, não agent. Vive em `src/services/`,
  não em `src/agents/`.
- Não escreve em `signals` nem em `trades`. Só em `daily_pnl` (e em
  `audit_log` em caso de erro).
- Não modifica Batman nem nenhum gate de risco.
- Não modifica schema do `daily_pnl` — usa o que Story 009 já criou.
- Day rollover é determinístico por UTC date (`%Y-%m-%d`), não por
  timezone local.

## Pipeline Atualizado

```
NickFury.run_main_cycle(...)
    PortfolioManager.run() → snapshot
    log SNAPSHOT_*
    effective_equity = override or snapshot.equity_usd
    for symbol in trading_assets:
        ProfessorX → Vision → Batman → IronMan
    ↓
    DailyPnLWriter.record_cycle(            ← NOVO
        equity_usd=effective_equity,
        trades_count_today,
        snapshot,
    )
    ↓ Repository.upsert_daily_pnl(date_utc, ending_equity, pnl_usd,
                                   pnl_pct, drawdown_pct, ...)
    ↓ on next cycle: Batman.get_today_drawdown_pct() reads non-zero
```

## Acceptance

- [x] `record_cycle` cria row na primeira chamada do dia.
- [x] Chamadas subsequentes do mesmo dia atualizam (não duplicam).
- [x] Peak preservado em memória; drawdown computado contra peak.
- [x] Day rollover detectado por UTC date — starting reset para current.
- [x] Falha de `upsert_daily_pnl` não propaga; vira audit event.
- [x] CLI override `--equity` é o que entra em `daily_pnl`, não snapshot.
- [x] Os 4 testes legados que tocavam `run_main_cycle` continuam verdes
      após mockar `record_cycle`.
- [x] 7 testes novos em `test_phase4_daily_pnl.py`.

## What's Next (Story 028)

Wolverine — Recovery Agent:

1. Substitui `run_monitor_cycle` heartbeat por monitor real.
2. Lê `EquitySnapshot.positions[]` (do PortfolioManager) e calcula PnL
   unrealized + realized fechamentos de SL/TP.
3. Preenche `wins`/`losses` em `record_cycle` quando positions fecham.
4. Aciona kill switch se intraday drawdown explode (combinando
   `daily_pnl.drawdown_pct` com `settings.max_daily_drawdown_pct`).

Sem Story 027, Wolverine teria que escrever sua própria persistência —
agora já tem `daily_pnl` confiável para empilhar wins/losses em cima.

## Files Changed

- `src/services/__init__.py` (novo)
- `src/services/daily_pnl_writer.py` (novo)
- `src/agents/nick_fury.py` (import + instância + chamada no fim do cycle)
- `tests/test_phase4_daily_pnl.py` (novo, 7 testes)
- `tests/test_phase2_pipeline.py` (1 mock adicional)
- `tests/test_phase3_portfolio.py` (3 mocks adicionais)
- `docs/stories/story-027-daily-pnl-writer.md` (este arquivo)
- `docs/stories/INDEX.md` (Milestone 8 atualizado)

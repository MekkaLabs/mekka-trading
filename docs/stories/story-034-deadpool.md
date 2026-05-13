# Story 034 — Deadpool (Performance Analytics Agent)

**Status:** DELIVERED — 2026-05-11
**Milestone:** 10 — Tactical + Simulation
**Pré-requisito:** ≥ 7 dias de dados de trading em `daily_pnl` (MIN_DAYS_REQUIRED)

---

## Contexto

Com o sistema em paper trading, precisamos de uma camada analítica que responda à
pergunta: **"o squad está funcionando bem o suficiente para mainnet?"**

Deadpool é o agente quantitativo determinístico que responde essa pergunta lendo
o banco de dados SQLite e computando um `PerformanceReport` consolidado. Sem LLM,
sem chamadas externas — puramente dados + aritmética.

A Story 034 estava marcada como pendente porque exigia ≥ 30 dias de histórico para
o contexto original. Revisamos o limiar mínimo para 7 dias (MIN_DAYS_REQUIRED),
o suficiente para detectar tendências confiáveis de curto prazo durante o paper run.

---

## Escopo Entregue

### `src/models/performance.py`

Três modelos Pydantic:

| Classe | Propósito |
|--------|-----------|
| `PerformanceVerdict` | Enum: `READY`, `NOT_READY`, `INSUFFICIENT_DATA` |
| `SymbolStats` | Stats por símbolo: trades, wins, losses, win_rate_pct, total_pnl_usd |
| `PerformanceReport` | Relatório completo com todos os campos + `to_audit_payload()` |

**Campos do PerformanceReport:**

```
window_days, days_with_data
total_trades, wins, losses, win_rate_pct
total_pnl_usd, avg_daily_pnl_usd
max_drawdown_pct, sharpe_estimate
wolverine_sl_endorse_rate_pct   ← proxy H2
signal_actionable_rate_pct      ← proxy H3
batman_approval_rate_pct
top_symbols, bottom_symbols     ← top 3 e bottom 3 por PnL
verdict, notes, generated_at
```

### `src/agents/deadpool.py`

Agente `Deadpool` (não herda BaseAgent — puramente async, sem LLM):

- `run(window_days=30)` → `PerformanceReport`
- Internamente chama `_compute(...)` (síncrono, testável sem mock de IO)
- Faz 4 queries via repo:
  - `list_recent_daily_pnl(limit=window_days)` — agregados por dia
  - `list_recent_trades(limit=5000)` — breakdown por símbolo
  - `list_recent_signals(limit=5000)` — taxas Vision/Batman
  - `list_audit_by_event("MONITOR_RECOVERY_PLAN", limit=2000)` — taxa Wolverine

**Thresholds de verdito:**

| Métrica | Limiar | Efeito |
|---------|--------|--------|
| `days_with_data` | < 7 | `INSUFFICIENT_DATA` |
| `win_rate_pct` | < 45% | `NOT_READY` |
| `max_drawdown_pct` | > 15% | `NOT_READY` |
| `signal_actionable_rate_pct` | < 50% (se dados disponíveis) | `NOT_READY` |
| Tudo OK + dados suficientes | — | `READY` |

**Wolverine SL endorsement rate:**
- Lê payloads `MONITOR_RECOVERY_PLAN` do audit_log
- Para cada ciclo: se todos os `positions[].action == "HOLD"` → ciclo endossado
- Taxa = `endorsed_cycles / total_cycles × 100`
- `None` se sem dados (Wolverine não rodou ainda)
- Falha de parse é silenciosa — rows inválidos são saltados

**Sharpe estimate:**
- Requer ≥ 5 dias para calcular
- `(mean_daily_pnl / std_daily_pnl) × √252`
- `None` se std = 0 (retornos constantes) ou < 5 dias

### `src/persistence/repository.py` (adição)

Novo método estático:

```python
@staticmethod
async def list_audit_by_event(event: str, limit: int = 500) -> list[AuditRecord]:
```

Filtra `audit_log` por `event` code, retorna oldest-first. Deadpool usa com
`event="MONITOR_RECOVERY_PLAN"`.

### `tests/test_phase15_deadpool.py` — 38 testes

| Classe | O que cobre |
|--------|-------------|
| `TestPerformanceReportModel` | Defaults, to_audit_payload, SymbolStats.decided |
| `TestInsufficientData` | zero days, below MIN, exactly MIN transitions |
| `TestNotReady` | low win rate, high drawdown, low actionable rate |
| `TestReady` | all thresholds met, no signals → None skips threshold |
| `TestWinRateAndPnL` | None sem decided, cálculo correto, total_pnl, avg_daily, zero |
| `TestSharpeEstimate` | None com < 5 dias, None com std=0, valor correto com variância |
| `TestSignalRates` | actionable_rate, batman_approval_rate, None sem signals |
| `TestWolverineEndorseRate` | None, 100%, parcial, empty positions, bad payload, null payload |
| `TestSymbolBreakdown` | ordenação por PnL, bottom symbols, ≤3 símbolos, win_rate por símbolo |
| `TestRepositoryListAuditByEvent` | método existe e é callable |
| `TestDeadpoolRun` | run() retorna PerformanceReport, READY verdict, INSUFFICIENT_DATA |

---

## Não Entregue

- Integração de Deadpool ao ciclo principal (Nick Fury fan-out) — planejada para
  Story 037 ou configurável via Telegram `/perf` command
- Integração com dashboard web — PerformanceReport pode alimentar um endpoint REST
  futuro

---

## Referências

- `src/models/recovery.py` — RecoveryAction enum (HOLD usado na taxa Wolverine)
- `src/persistence/models.py` — AuditRecord.payload é JSON string
- `docs/stories/story-030-wolverine.md` — MONITOR_RECOVERY_PLAN audit event
- `docs/stories/story-036-mainnet-readiness.md` — gates H1–H6 que Deadpool proxia

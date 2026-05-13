# Story 029 — Safety Net

## Context

A revisão Cowork após Story 028 listou três safety gaps que iriam morder
o operador na primeira semana de testnet:

1. Vision pode pedir 5 LONGs em sequência a 2% size cada — Batman valida
   cada um isoladamente e o sistema chega a 10% deployed sem ninguém
   reclamar. Não havia **cap absoluto sobre soma de notional**.
2. N execuções `EXEC_ERROR` consecutivas (Hyperliquid SDK, rede, edge
   case) deixavam o sistema continuar tentando — sem **exec error
   breaker**.
3. Vision retornar HOLD-fallback (`metadata.fallback=True`) por OpenAI
   timeout, anomaly halt, etc., não tinha **detecção de streak**.

Story 029 fecha os 3 com edits aditivos. Cumprida em duas fases: code
adiantado pelo operador/linter; tests + docs nesta entrega.

## Goal

Cravar redes de segurança operacionais antes de qualquer execução
testnet real, sem mexer em comportamento de pipeline existente.

## Scope Delivered

### Service novo (`src/services/breakers.py`)

- **`ConsecutiveBreaker`** — counter passivo, stateful, com
  `observe(hit: bool) -> bool`. Retorna `True` **apenas no momento
  exato** em que o streak cruza o threshold. Hits subsequentes
  mantêm o streak crescendo mas não re-trippam.
- `reset()` para uso em testes / pós-release de kill switch.
- `is_armed` quando streak > 0.
- `summary()` para logs.
- **74 linhas, sem dependências de agente.** Orquestrador decide o
  que fazer no trip; o breaker só conta.

### Settings novos (`src/config/settings.py`)

- `max_total_capital_pct: float = 0.10` — fração de equity que pode
  estar em notional aberto simultaneamente (default 10%).
- `max_total_notional_usd: Optional[float] = None` — cap absoluto em
  USD. Quando preenchido, **toma precedência** sobre o cap percentual.
- `max_consecutive_exec_errors: int = 3` — threshold do exec breaker.
- `max_consecutive_vision_fallbacks: int = 5` — threshold do vision
  fallback breaker.

### Batman (`src/agents/batman.py`)

- Assinatura ganhou `equity_usd: float = 0.0` e
  `running_notional_usd: float = 0.0` (defaults preservam back-compat
  com chamadas antigas).
- Nova **seção 3b. Total capital cap**:
  - Calcula `new_notional = equity × signal.size_pct × signal.leverage`.
  - `projected_total = running_notional_usd + new_notional`.
  - Se `max_total_notional_usd` está setado e `projected > absolute`
    → `REJECTED` com `breached_limits=["max_total_notional_usd"]`.
  - Senão, se `projected > equity × max_total_capital_pct` →
    `REJECTED` com `breached_limits=["max_total_capital_pct"]`.
  - **Avaliado contra a INTENÇÃO do Vision (pré-Thor)**, não contra
    o size pós-multiplier. Razão: se a intenção já blowa o cap, é
    sinal de problema upstream, não algo a "consertar" multiplicando.

### Nick Fury (`src/agents/nick_fury.py`)

- Importa `ConsecutiveBreaker`.
- `__init__` instancia 2 breakers:
  - `self._exec_error_breaker` (threshold de
    `settings.max_consecutive_exec_errors`)
  - `self._vision_fallback_breaker` (threshold de
    `settings.max_consecutive_vision_fallbacks`)
- `run_main_cycle` calcula `running_notional_usd` no início somando
  `position.size × position.entry_price` do `EquitySnapshot.positions`.
  Incrementa a cada paper/live execução do cycle.
- `_cycle_for_symbol` repassa `equity_usd` e `running_notional_usd`
  para Batman.
- Novo método **`_check_breakers(report: CycleReport)`** chamado por
  símbolo após o cycle:
  - Observa `report.execution.status == ExecutionStatus.ERROR` no
    exec breaker. Trip → `engage_kill_switch(reason)` + audit log
    `RISK_KILL_SWITCH` com `payload.breaker = "exec_error"`.
  - Observa `report.signal.action == HOLD AND
    metadata.fallback=True` no vision breaker. Trip → mesma chain
    com `payload.breaker = "vision_fallback"`.

### Operator script (`scripts/kill.sh`)

- Toca `data/.kill_switch` com payload `[timestamp UTC] reason`.
- Imprime instruções de release (`rm data/.kill_switch`).
- Executável (`chmod +x`).
- Smoke-tested em `/tmp` antes de commit.

### Pytest fase 6 (`tests/test_phase6_safety_net.py`) — 16 testes

ConsecutiveBreaker (6):
- `test_breaker_invalid_threshold_raises`
- `test_breaker_threshold_one_trips_on_first_hit`
- `test_breaker_trips_only_when_streak_crosses_threshold`
- `test_breaker_reset_on_non_hit`
- `test_breaker_manual_reset`
- `test_breaker_summary_format`

Batman cap (5):
- `test_batman_skips_cap_when_equity_zero` — back-compat para
  callers que ainda não passam equity.
- `test_batman_cap_pct_blocks_when_running_plus_new_exceeds`
- `test_batman_cap_pct_allows_when_within_limit`
- `test_batman_absolute_cap_takes_precedence`
- `test_batman_cap_evaluated_against_pre_thor_intent`

Nick Fury (5):
- `test_nick_fury_exec_error_breaker_trips_on_threshold`
- `test_nick_fury_exec_breaker_resets_on_non_error`
- `test_nick_fury_vision_fallback_breaker`
- `test_nick_fury_no_breaker_trip_on_clean_cycle`
- `test_nick_fury_running_notional_starts_from_snapshot_positions`

## Hard Rules Mantidas

- **Pure additivo.** Defaults dos novos params Batman são `0.0`,
  preservando back-compat com testes da fase 2/3/4.
- Quando `equity_usd=0`, o cap de capital é **pulado** (caller legado
  funciona). Cap só engata em chamadas pós-Story 029.
- Breakers ficam em `src/services/`, não em `src/agents/`. Sem
  persona, sem inflar roster (continua 15 heróis).
- `engage_kill_switch` continua usando `data/.kill_switch` —
  mecanismo já existente.
- Nenhum runtime de Vision, Iron Man, Portfolio Manager,
  DailyPnLWriter foi modificado.

## Pipeline Atualizado

```
NickFury.run_main_cycle(...)
  → PortfolioManager.run() → EquitySnapshot
  → running_notional_usd  = Σ size × entry_price (das positions abertas)
  → for symbol in trading_assets:
        ProfessorX → Vision → Batman(equity, running_notional) → IronMan
        if executed: running_notional_usd += execution.notional_usd
        ↓
        _check_breakers(report)        ← NOVO
            ↓ exec_error_breaker.observe(status==ERROR)
            ↓ vision_fallback_breaker.observe(action==HOLD AND fallback)
            ↓ se trip → engage_kill_switch + audit RISK_KILL_SWITCH
  → DailyPnLWriter.record_cycle(...)
```

## Acceptance

- [x] Settings novos default-conservadores (10% cap, 3 errors, 5 fallbacks).
- [x] Batman aceita `equity_usd=0` (legacy callers) sem quebrar.
- [x] Cap absoluto vence o percentual quando ambos disparam.
- [x] Cap é pre-Thor (avalia intenção do Vision).
- [x] Exec breaker reseta em qualquer non-ERROR (PAPER, FILLED, PARTIAL).
- [x] Vision fallback breaker só conta `metadata.fallback=True` em HOLD.
- [x] `_check_breakers` engaja kill switch + audit `RISK_KILL_SWITCH`.
- [x] Audit payload carries `breaker` field para identificar qual.
- [x] `scripts/kill.sh` cria flag com motivo + UTC timestamp.
- [x] 16 testes novos em `tests/test_phase6_safety_net.py`.
- [x] Tests da fase 1–5 não foram tocados.

## Riscos Conhecidos (registrados, não bloqueantes)

- **Vision fallback breaker não distingue causa.** Anomaly halt
  (Spider-Man HIGH) e OpenAI timeout trippam o mesmo contador.
  Para v1 isso é aceitável — ambos os casos exigem atenção humana.
  Refinar quando tiver casos reais para discriminar.
- **Cap roda antes do Thor multiplier.** Documentado como decisão
  intencional. Próxima IA não deve "consertar" sem justificativa.
- **Exec breaker não distingue tipo de erro.** Network timeout e
  schema parse error trippam igual. Refinar com `AgentErrorReport`
  taxonomy em story futura.

## What's Next (Story 030 — Wolverine, agora desbloqueada)

Wolverine entra com:
- `ConsecutiveBreaker` para reaproveitar (e.g. consecutive position
  drawdowns).
- `running_notional` já alimentando Batman.
- Kill switch automático em pé via `_check_breakers`.
- `wins`/`losses` pendentes em `DailyPnLWriter` que Wolverine vai
  preencher quando posições fecharem por SL/TP.

## Files Changed

Novos:
- `src/services/breakers.py`
- `tests/test_phase6_safety_net.py`
- `scripts/kill.sh`
- `docs/stories/story-029-safety-net.md` (este arquivo)

Editados (aditivos, todos por usuário/linter antes desta entrega):
- `src/services/__init__.py` (registry)
- `src/config/settings.py` (4 settings novos)
- `src/agents/batman.py` (params + seção 3b)
- `src/agents/nick_fury.py` (breakers + running_notional + _check_breakers)

Editados nesta entrega:
- `docs/stories/INDEX.md` (Story 029 → entregue, Wolverine 030)
- `AGENTS.md` (Pending → Story 030+)
- `docs/HANDOFF.md` (Story 029 fechada, próxima 030)

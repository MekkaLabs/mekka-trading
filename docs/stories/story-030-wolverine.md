# Story 030 — Wolverine (Recovery Agent)

## Context

Após Story 029 (Safety Net) o monitor cycle ainda era um heartbeat
vazio. Posições abertas ficavam sem supervisão entre os 4h dos
ciclos principais. Se o mercado decidisse correr 5% em 30 minutos
contra a posição, ninguém avisaria — Daily PnL Writer só roda no fim
do main cycle.

Story 030 entrega Wolverine, o **recovery agent** que sobe esse
heartbeat para um monitor real read-only.

## Goal

Monitorar posições abertas a cada 5 min (intervalo padrão), gerar
um plano de recuperação por posição, e atuar como **backstop** do
kill switch quando intraday drawdown explode entre os ciclos
principais.

## Scope Delivered

### Models novos (`src/models/recovery.py`)

- **`RecoveryAction`** enum — `HOLD / TIGHTEN_STOP / TRAIL_STOP /
  SCALE_OUT / CLOSE / EMERGENCY_CLOSE`.
- **`PositionUpdate`** — uma por posição aberta no cycle. Carrega
  symbol, side, size, entry_price, current_price, unrealized_pnl_usd,
  action, new_stop_loss, new_take_profit, reason.
- **`RecoveryPlan`** — output do Wolverine.run. Contém lista de
  PositionUpdate, intraday_drawdown_pct agregado, kill_switch_engaged
  flag, notes. Properties `total_unrealized_pnl_usd` e `needs_action`.
  `to_audit_payload()` para persistência.

### Wolverine agent (`src/agents/wolverine.py`)

Read-only recovery agent (135 linhas). Nada de chamadas de
escrita ao exchange. Iron Man continua único caminho da SDK.

- **Classificador determinístico** `_classify_position` baseado em
  PnL como % do notional:
  - `≤ -5%` → `EMERGENCY_CLOSE`
  - `≤ -1.5%` → `TIGHTEN_STOP`
  - `≥ +5%` → `SCALE_OUT`
  - `≥ +2%` → `TRAIL_STOP`
  - resto → `HOLD`
- **Cálculo de PnL** longo `(price - entry) × size`, curto
  `(entry - price) × size`. Fallback para `position.unrealized_pnl_usd`
  do snapshot quando `current_price` não foi passado.
- **Sugestão de novo SL** apenas para `TIGHTEN_STOP`/`TRAIL_STOP`.
  Buffer simples de 0.5% do current price (long: SL abaixo,
  short: SL acima). ATR-based vai entrar em story futura.
- **Backstop kill switch**: se aggregate intraday drawdown
  (`-total_upnl / equity`) ≥ `settings.max_daily_drawdown_pct`,
  Wolverine engaja kill switch e força `EMERGENCY_CLOSE` em
  todas as posições do plano.
- **Defesa em profundidade**: snapshot vazio → empty plan,
  `engage_kill_switch` falha → plan ainda retornado, classificador
  exception → propagado para Nick Fury que captura e audita.
- **Idempotente**: mesma snapshot → mesmo plan. Sem state interno.

### Wire em Nick Fury (`src/agents/nick_fury.py`)

- `__init__` instancia `self._wolverine = Wolverine()` (lazy import).
- `run_monitor_cycle` deixou de ser heartbeat:
  - Short-circuit se kill switch já ativo.
  - `_portfolio.run()` para snapshot atualizado.
  - `_wolverine.run(snapshot)` para o plano.
  - `MekkaRepository.log_event(event="MONITOR_RECOVERY_PLAN", ...)`
    com payload completo do plan.
  - Retorna dict com status / positions_monitored /
    intraday_drawdown_pct / kill_switch_engaged.
  - try/except em ambos `portfolio.run` e `wolverine.run` — falha
    nunca propaga, vira audit `CYCLE_ERROR`.

### Registry (`src/agents/__init__.py`)

- `Wolverine` adicionado ao `__all__` e ao `__getattr__` lazy-load.
- Layer 4 ganha terceira entry no docstring header.

### Pytest fase 7 (`tests/test_phase7_wolverine.py`) — 15 testes

Wolverine puro (10):
- empty snapshot → empty plan
- long PnL math, short PnL math
- fallback para snapshot PnL quando current_price omitido
- emergency loss → EMERGENCY_CLOSE
- tighten loss → TIGHTEN_STOP com SL recalculado
- trail profit → TRAIL_STOP com SL recalculado
- scale-out profit → SCALE_OUT
- HOLD na banda neutra
- intraday drawdown breach → kill switch + força EMERGENCY_CLOSE
- engage_kill_switch raise → plan ainda retorna sem propagar

Nick Fury wired (3):
- monitor_cycle chama wolverine + audita plan
- monitor_cycle short-circuit quando kill switch já ativo
- monitor_cycle captura wolverine raise e retorna error sem propagar

Sem positions edge case (2):
- aggregate drawdown 0 → kill switch off
- snapshot sem positions → audit ainda emitido

## Hard Rules Mantidas

- **Wolverine nunca escreve no exchange.** RecoveryPlan é advisory
  em v1. Iron Man segue único caminho de execução.
- **Backstop, não substituto.** Batman ainda é o gate per-signal
  para drawdown. Wolverine só age quando o drawdown explode entre
  os ciclos principais (gap entre Daily PnL writes).
- **Read-only no portfolio.** Wolverine não modifica `EquitySnapshot`,
  só lê.
- **Sem novos settings.** Thresholds são constantes locais
  (`_TRAIL_PROFIT_PCT`, `_TIGHTEN_LOSS_PCT`, `_SCALE_OUT_PROFIT_PCT`,
  `_EMERGENCY_LOSS_PCT`). Refinar em story futura quando
  comportamento for validado em paper.

## Pipeline Atualizado

Monitor cycle (a cada 5 min entre os 4h):
```
NickFury.run_monitor_cycle()
  → kill_switch_active? → halt
  → PortfolioManager.run() → EquitySnapshot
  → Wolverine.run(snapshot)
        ↓ for each position:
              compute upnl
              classify action
              suggest new SL/TP if applicable
        ↓ aggregate intraday_drawdown_pct
        ↓ if breach: engage_kill_switch + force EMERGENCY_CLOSE all
  → log_event(MONITOR_RECOVERY_PLAN)
  → return {status, positions_monitored, intraday_dd, kill_engaged}
```

## Acceptance

- [x] Wolverine instancia sem dependência opcional.
- [x] Empty snapshot → empty plan, no kill switch.
- [x] Long e short PnL math corretos.
- [x] Fallback para snapshot.unrealized_pnl_usd quando current_price omitido.
- [x] 5 ações de classifier acionadas conforme thresholds.
- [x] Intraday drawdown breach → kill switch + force EMERGENCY_CLOSE.
- [x] Persistência failure no kill switch → plan retorna sem propagar.
- [x] Nick Fury monitor cycle calls wolverine + audits.
- [x] Monitor cycle short-circuit em kill switch já ativo.
- [x] Wolverine raise → audit CYCLE_ERROR, sem propagação.
- [x] 15 testes novos em `tests/test_phase7_wolverine.py`.

## Riscos Conhecidos

- **SL buffer fixo 0.5%.** ATR-based sizing é melhor mas exige
  injetar Thor no Wolverine. Story futura.
- **Sem cálculo de TP recalculado.** TIGHTEN_STOP só mexe em SL,
  TP fica intocado. Aceitável para v1.
- **Vision não é informado do plan.** Próximo cycle main não sabe
  que Wolverine recomendou EMERGENCY_CLOSE. Refinar com
  pre-cycle handoff quando Vision Critic entrar (Story 031).
- **`current_prices` precisa vir de fora.** Hoje Nick Fury não
  passa — Wolverine cai no fallback do snapshot. Wire de feed real
  é responsabilidade de Story futura (Superman.run no monitor cycle
  é overkill, mas um lookup leve de `marketDataFeed` resolveria).

## What's Next (Story 031 — Vision Critic)

Wolverine entrega o último componente grande de runtime antes de
testnet. Próxima Story: Vision Critic — toggle off por default que
adiciona um second-look LLM para reduzir alucinação de decisões em
produção.

## Files Changed

Novos:
- `src/models/recovery.py` (110 linhas)
- `src/agents/wolverine.py` (167 linhas)
- `tests/test_phase7_wolverine.py` (305 linhas)
- `docs/stories/story-030-wolverine.md` (este)

Editados (aditivos):
- `src/agents/__init__.py` — Wolverine registrado em Layer 4
- `src/agents/nick_fury.py` — instancia Wolverine + reescreve `run_monitor_cycle`
- `docs/stories/INDEX.md` — Story 030 entregue, próxima 031
- `AGENTS.md` — Wolverine sai de "Pending"
- `docs/HANDOFF.md` — Story 030 fechada, próxima 031

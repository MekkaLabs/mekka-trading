# Story 028 — Contract Hardening

> Wolverine bumped to Story 029. This story is a **hardening pass**
> intentionally placed before introducing the next agent so that
> Wolverine inherits clean contracts.

## Context

A Cowork review (após Story 027) identificou 9 inconsistências de
contrato e comunicação entre agentes. Os 4 mais relevantes:

- **R1** `CycleReport` era classe Python pura; `DailyPnLSnapshot` era
  `@dataclass`. Os outros 11 contratos de output são Pydantic.
- **R2** `audit_log.event` é string livre, sem enum — typos passam
  silenciosos.
- **R3** Codename de herói tinha 3 grafias coexistindo (`"IronMan"`,
  `"Iron Man"`, `"IronMan"` no dashboard) sem fonte de verdade.
- **R5** Sem `schema_version` em nenhum model — a primeira migração
  vai morder.
- **R6** `datetime.now(timezone.utc)` reimplementado em 8+ lugares.
- **R7** Padrão de erro de agente não uniforme.
- **R8** PortfolioManager fora do `HERO_LAYER` do dashboard.

Story 028 endereça todos esses pontos com edits **aditivos**. Nenhum
comportamento de runtime muda; nenhuma assinatura existente quebra.

## Goal

Cravar fundações de contrato — Pydantic uniforme, enums canônicas,
schema versioning, error envelope padrão — antes de adicionar
Wolverine, Flash ou Deadpool.

## Scope Delivered

### Foundation utilities (5 arquivos novos)

- **`src/utils/__init__.py`** + **`src/utils/time.py`** — `utc_now()`
  e `utc_today_iso()` como única referência de relógio. Substituirá
  progressivamente `datetime.now(timezone.utc)` espalhados.
- **`src/models/heroes.py`** — `HeroName` enum com 15 membros.
  Single source of truth para codenames; `.normalize(s)` tolera
  espaços e hyphens.
- **`src/models/events.py`** — `AgentEvent` enum com todos os event
  codes hoje em uso (lifecycle, risk, exec, snapshot, errors).
- **`src/models/errors.py`** — `AgentErrorReport` Pydantic. Envelope
  padronizado para `audit_log.payload` em paths defensivos.
- **`src/models/protocols.py`** — `Promptable`, `AuditPayloadable`
  Protocols. Formaliza o contrato tácito de `to_prompt_section()` e
  `to_audit_payload()`.

### Pydantic migration (2 contratos promovidos)

- **`src/models/orchestration.py`** (novo) — `CycleReport` agora é
  `BaseModel`. `nick_fury.py` re-exporta para preservar
  `from src.agents.nick_fury import CycleReport`.
- **`src/services/daily_pnl_writer.py`** — `DailyPnLSnapshot` agora
  é `BaseModel`. Todos os tests existentes seguem funcionando porque
  acessavam apenas atributos / método `.summary()`.

### `schema_version: int = 1` adicionado

A 7 models críticos: `TradingSignal`, `RiskApproval`,
`ExecutionResult`, `EquitySnapshot`, `MarketAnalysis`, `CycleReport`,
`AgentErrorReport`. Todos com default 1, retro-compatíveis.

### Dashboard drift fixed

`HERO_LAYER` em `src/dashboard/server.py` ganhou `PortfolioManager` e
`DailyPnLWriter` na Layer 4 — eventos desses agentes agora aparecem
mapeados na timeline em vez de "unmapped".

### Pytest fase 5 — 14 meta-tests novos

Em `tests/test_phase5_contracts.py`:
- `utc_now` é tz-aware; `utc_today_iso` formato YYYY-MM-DD
- `HeroName` tem 15 membros e bate com `agents/registry.ts`
- `HeroName.normalize` tolera variantes conhecidas
- `AgentEvent` cobre todos os event codes em uso
- `CycleReport` é `BaseModel`, round-trip JSON funciona
- `nick_fury.CycleReport` re-export aponta para o mesmo objeto
- `DailyPnLSnapshot` é `BaseModel`, round-trip funciona
- 7 models críticos têm `schema_version` (parametrize)
- `Promptable` Protocol valida `MarketData`
- `AuditPayloadable` valida `CycleReport` e `AgentErrorReport`
- `AgentErrorReport` round-trip + `summary()` correto
- Dashboard `HERO_LAYER` inclui PortfolioManager
- Keys de `HERO_LAYER` são PascalCase sem espaços

## Hard Rules Mantidas

- **Nenhum runtime quebra.** Todas as edits são aditivas: novos
  campos com default, novas constantes, novos arquivos. Nenhuma
  assinatura de função/método mudou.
- **`MekkaRepository.log_event(event=str)` continua aceitando string.**
  Adoção do `AgentEvent` enum pode ser progressiva (cada agente
  migra na sua própria story).
- **`BaseAgent(codename=str)` continua aceitando string.** Adoção
  do `HeroName` enum também é progressiva.
- **Não migramos os 8 usos de `datetime.now(timezone.utc)`.**
  Substituição é trivial mas pode ser feita em qualquer story
  futura sem quebrar nada.
- **Não criamos hierarquia de herança nova.** `Promptable` e
  `AuditPayloadable` são Protocols PEP-544 (duck typing).
- **Não tocamos Vision, Batman, Iron Man, risk-engine, hyperliquid
  mock, kill switch, ou geometria SL/TP.**

## Pipeline Atualizado

Sem mudança operacional. O pipeline canônico permanece:

```
NickFury.run_main_cycle(...)
  → PortfolioManager.run() → EquitySnapshot
  → for symbol in trading_assets:
        ProfessorX → Vision → Batman → IronMan
  → DailyPnLWriter.record_cycle(...)
  → list[CycleReport]   ← agora Pydantic, com schema_version=1
```

A diferença é que **toda saída do pipeline agora serializa
uniformemente** via `.model_dump(mode="json")`.

## Story Renumbering

Wolverine sai de **028** e vira **029**. Atualizado em `INDEX.md`,
`HANDOFF.md`, e `AGENTS.md` (Story 029+).

## Acceptance

- [x] `python3 -m py_compile` em todos os arquivos novos/editados.
- [x] `scripts/check_roster_consistency.py` retorna `[OK] Roster
      consistent — 15 heroes`.
- [x] Tests existentes (47 da fase 1–4) continuam compatíveis sem
      mudança (CycleReport e DailyPnLSnapshot mantêm interface).
- [x] 14 tests novos em `tests/test_phase5_contracts.py`.
- [x] `from src.agents.nick_fury import CycleReport` segue funcionando.
- [x] `HERO_LAYER` do dashboard cobre 13 entries (15 heróis menos
      Flash/Wolverine/Deadpool ainda pendentes, mais
      DailyPnLWriter como service).

## Files Changed

Novos:
- `src/utils/__init__.py`, `src/utils/time.py`
- `src/models/heroes.py`, `events.py`, `errors.py`, `protocols.py`,
  `orchestration.py`
- `tests/test_phase5_contracts.py`
- `docs/stories/story-028-contract-hardening.md` (este arquivo)

Editados (aditivos):
- `src/models/signal.py` (`schema_version`)
- `src/models/risk.py` (`schema_version`)
- `src/models/execution.py` (`schema_version`)
- `src/models/portfolio.py` (`schema_version`)
- `src/models/market_data.py` (`schema_version` em `MarketAnalysis`)
- `src/services/daily_pnl_writer.py` (`DailyPnLSnapshot` → BaseModel,
  usa `utc_today_iso`)
- `src/agents/nick_fury.py` (importa `CycleReport` de orchestration,
  remove definição inline, re-exporta)
- `src/dashboard/server.py` (`HERO_LAYER` + PortfolioManager + DailyPnLWriter)

## What's Next (Story 029 — Wolverine, agora)

Wolverine entra num solo limpo:
- `HeroName.WOLVERINE` já existe.
- `AgentEvent` ganhará `MONITOR_*` codes na própria Story 029.
- Erros vão como `AgentErrorReport`.
- Posições fechadas geram `wins`/`losses` que `DailyPnLWriter`
  já aceita como param.
- Output de Wolverine (RecoveryPlan?) será Pydantic com
  `schema_version=1` desde o dia zero.

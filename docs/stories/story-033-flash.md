# Story 033 — Flash (Momentum Scalper)

## Context

Após Wolverine (Story 030) o monitor cycle ficou ativo, mas só
classifica posições abertas. Não há detecção de **micro-momentum**
intra-candle — bursts ou reversões dentro de uma janela curta que
sinalizem timing de entrada.

Story 033 adiciona Flash como agente **read-only e advisory** que
emite `MomentumSignal`. Em v1 nada consome esse signal — fica no
audit log para o operador (e Deadpool/dashboard futuros) verem.
Story futura pode usar `MomentumSignal.is_strong` como gate de
entry timing dentro do main cycle.

## Goal

Cravar detecção determinística de momentum sem mudar o pipeline
principal e sem depender de LLM, mantendo o roster e o pacing
pedagógico.

## Scope Delivered

### Agent novo (`src/agents/flash.py`)

148 linhas. Stateless por chamada — caller passa histórico relevante:

- **Inputs**: `symbol`, `recent_prices` (lista chronológica),
  `recent_volumes` (opcional alinhado), `window_seconds`.
- **Defesa**: histórico < 6 pontos → `SIDEWAYS` strength 0.0,
  notes explica.
- **Direction classification**:
  - net move ≥ +0.5% → `UP`
  - net move ≤ -0.5% → `DOWN`
  - resto → `SIDEWAYS`
- **Strength scoring**: combo `move_component * 0.7 +
  vol_component * 0.3`, saturado em 1.0.
- **Volume multiplier**: current vs. mean da janela.
  Misalignment ou erros silenciados → fallback 1.0.
- **VOLUME-CONFIRMED tag** quando vol_mult ≥ 1.5 E direction !=
  SIDEWAYS — destaque para o operador.
- Sem chamadas externas. Pure cálculo. Determinístico.

### Registry (`src/agents/__init__.py`)

Flash adicionado ao `__all__`, ao `__getattr__` lazy-load, e à
docstring (nova "Layer 1.5 — Tactical Sub-Loop" para diferenciar
de Layer 1 que é análise de longo prazo).

### Pytest fase 10 (`tests/test_phase10_flash.py`) — 16 testes

Direction (5):
- empty / short / None history → SIDEWAYS
- up burst → UP
- down burst → DOWN
- small move → SIDEWAYS

Strength (3):
- bigger magnitude → bigger strength
- strength saturates at 1.0
- volume amplifies strength

VOLUME-CONFIRMED tag (2):
- spike + direction → tag
- spike + SIDEWAYS → no tag

is_strong gate (1):
- strength≥0.70 AND vol_mult≥1.5 → True

Misc (5):
- entry_window_seconds propagated
- is_expired when window=0
- misaligned volumes don't raise
- zero first price doesn't divide-by-zero
- MomentumSignal model usable as plain Pydantic

## Hard Rules Mantidas

- **Read-only**, não toca exchange.
- **Stateless**: cada `run()` é independente; caller passa input.
- **Determinístico**, sem LLM.
- **Não modifica pipeline principal.** Em v1 nenhum agente downstream
  consome o `MomentumSignal`. Story futura pode integrar com Vision
  via `analysis.momentum`.
- **Defensivo**: dados ruins / curtos / misaligned não fazem raise.

## Posicionamento no Roster

Flash é **Layer 1.5 — Tactical**: rápido demais para Layer 1
(análise multi-timeframe de Superman), tático demais para Layer 4
(comando estratégico). Documentado como categoria separada no
`agents/__init__.py` docstring.

`HeroName.FLASH` já existia em `src/models/heroes.py` desde Story 028
(Contract Hardening) — agora tem implementação pareada. `agents/registry.ts`
também já tinha a entry. Nenhum drift de roster.

## Pipeline Atualizado

Em v1, Flash NÃO está cabido em nenhum cycle automaticamente. É
invocável manualmente:

```python
from src.agents.flash import Flash
sig = await Flash().run(
    symbol="BTC",
    recent_prices=[...],
    recent_volumes=[...],
)
if sig.is_strong:
    # operator decides what to do
    ...
```

Story futura ("034" ou "035"): plugar Flash dentro de
`NickFury._run_monitor_cycle` paralelo com Wolverine, alimentar
`MomentumSignal` no audit_log e expor no dashboard.

## Acceptance

- [x] Agent compila sem dependência opcional.
- [x] 5 paths de direction classification funcionando.
- [x] Strength saturate em 1.0.
- [x] Volume multiplier amplifica.
- [x] VOLUME-CONFIRMED tag firing apenas quando direção + spike.
- [x] is_strong property funcionando.
- [x] Defensive paths (None, short, misaligned, zero) não raise.
- [x] 16 testes em `tests/test_phase10_flash.py`.
- [x] Roster consistency mantida (Flash já estava em registry.ts).

## What's Next (Story 034 — Deadpool)

Backtest + chaos simulator sobre histórico SQLite (`signals` +
`trades`). Pré-requisito: ≥ 30 dias de histórico paper-trading
acumulado.

Antes da Story 034 (que precisa de dados reais), o ideal é o
operador executar o `RUNBOOK-TESTNET.md` para começar a gerar
histórico real.

## Files Changed

Novos:
- `src/agents/flash.py` (148 linhas)
- `tests/test_phase10_flash.py` (210 linhas)
- `docs/stories/story-033-flash.md` (este arquivo)

Editados:
- `src/agents/__init__.py` — Flash registrado em Layer 1.5
- `docs/stories/INDEX.md` — Story 033 entregue
- `AGENTS.md` — Flash sai de "Pending"
- `docs/HANDOFF.md` — 33 stories, ~185 testes
- `docs/AUTO-CONTINUE-PLAN.md` — § 5.1 marcada concluída

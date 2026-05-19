# Story 251 — Cycle Checkpoint

## Objetivo

Permitir que NickFury retome um ciclo de trading interrompido **de onde parou**, sem
re-executar agentes já concluídos — eliminando latência duplicada e chamadas LLM
desnecessárias após um crash ou reinício do processo.

## Motivação

Antes desta story, um crash entre ProfessorX e Vision forçava NickFury a re-executar
todos os L1 agents (Superman, DoctorStrange, BlackPanther, Thor, Aquaman, SpiderMan)
e o ProfessorX antes de chegar à Vision. Com ciclos podendo durar 15–30 segundos por
símbolo, essa redundância aumentava o tempo de recuperação e consumia tokens LLM
desnecessariamente.

## Implementação

### `src/services/cycle_checkpoint.py`

| Componente | Descrição |
|---|---|
| `CycleCheckpointStore` | Salva e restaura estados intermediários de ciclo via AuditRecord |
| `get_cycle_checkpoint_store()` | Singleton factory |

**Chave de lookup:** `(cycle_id, symbol, stage)` — única por ciclo.

**Stages suportados:**

| Stage | Agente | Payload |
|---|---|---|
| `ANALYSIS` | ProfessorX | `MarketAnalysis.model_dump()` |
| `SIGNAL` | Vision | `TradingSignal.model_dump()` |

**Padrão de persistência:**

Reutiliza `MekkaRepository.log_event()` + `list_audit_events()` (mesmo padrão da
Story 249 — Decision Memory), sem dependência de LangGraph.

Cada checkpoint é um `AuditRecord` com:
```
agent   = "NICKFURY"
event   = "CYCLE_CHECKPOINT"
symbol  = <symbol>
payload = {"cycle_id": str, "stage": str, "data": dict}
```

**API:**

```python
store = get_cycle_checkpoint_store()

# Salva resultado de ProfessorX
await store.save(cycle_id, symbol, "ANALYSIS", analysis.model_dump())

# Verifica se já existe antes de chamar Vision
if await store.exists(cycle_id, symbol, "SIGNAL"):
    data = await store.load(cycle_id, symbol, "SIGNAL")
    signal = TradingSignal(**data)

# Remove checkpoints expirados (default: >60 min)
deleted = await store.clear_expired(max_age_minutes=60)
```

**Métodos:**

| Método | Retorno | Descrição |
|---|---|---|
| `save(cycle_id, symbol, stage, payload)` | `None` | Persiste via log_event |
| `load(cycle_id, symbol, stage)` | `dict \| None` | Busca por (cycle_id, symbol, stage) |
| `exists(cycle_id, symbol, stage)` | `bool` | Atalho para `load(...) is not None` |
| `clear_expired(max_age_minutes=60)` | `int` | DELETE direto via SQLAlchemy |

### `src/agents/nick_fury.py` — `_cycle_for_symbol()`

Três blocos inseridos na pipeline de `_cycle_for_symbol()`:

#### Bloco 1 — Init do store (antes de ProfessorX)

```python
_cp251 = None
try:
    from src.services.cycle_checkpoint import get_cycle_checkpoint_store
    _cp251 = get_cycle_checkpoint_store()
except Exception as _cp251_init_exc:
    logger.debug(f"[NickFury:251] CycleCheckpointStore init skipped: {_cp251_init_exc}")
```

#### Bloco 2 — Check/restore ANALYSIS antes de ProfessorX

```python
_analysis251_restored = False
if _cp251 is not None:
    try:
        _cp251_analysis_data = await _cp251.load(str(_cycle_id), symbol, "ANALYSIS")
        if _cp251_analysis_data:
            analysis = MarketAnalysis(**_cp251_analysis_data)
            _analysis251_restored = True
    except Exception as _cp251_load_exc:
        logger.debug(...)

if not _analysis251_restored:
    # ... chama ProfessorX normalmente ...
    # Após conclusão:
    await _cp251.save(str(_cycle_id), symbol, "ANALYSIS", analysis.model_dump())
```

#### Bloco 3 — Check/restore SIGNAL antes de Vision + save após Vision

```python
# Antes do try Vision:
_signal251_restored = False
_signal251_cached = None
if _cp251 is not None:
    data = await _cp251.load(str(_cycle_id), symbol, "SIGNAL")
    if data:
        signal = TradingSignal(**data)
        _signal251_restored = True

# Dentro do try Vision:
if _signal251_restored and _signal251_cached is not None:
    signal = _signal251_cached  # Vision não é chamada
elif _budget_skipped:
    # ... path existente ...
else:
    signal = await self._vision.run(analysis=analysis)

# Após o finally de Vision:
if _cp251 and not _signal251_restored and not _budget_skipped and not _vision_error:
    await _cp251.save(str(_cycle_id), symbol, "SIGNAL", signal.model_dump())
```

## Diagrama de Fluxo

```
_cycle_for_symbol()
  │
  ├─ Init CycleCheckpointStore (_cp251)
  │
  ├─ ANALYSIS checkpoint?
  │    ├─ YES → MarketAnalysis(**data) ─────────────────────────────┐
  │    └─ NO  → ProfessorX.run() → save ANALYSIS checkpoint         │
  │                                                                  │
  ├─ SIGNAL checkpoint?   ◄────────────────────────────────────────┘
  │    ├─ YES → TradingSignal(**data) ──────────────────────────────┐
  │    └─ NO  → Vision.run(analysis) → save SIGNAL checkpoint       │
  │                                                                  │
  └─ Continua pipeline... ◄────────────────────────────────────────┘
```

## Estratégia de Rollback Zero

- `_cp251` permanece `None` se o serviço falhar ao inicializar.
- Todos os checkpoint operations são `try/except` com `logger.debug()` — nunca quebram o ciclo.
- O pipeline existente continua idêntico quando `_cp251 is None`.
- Save de ANALYSIS e SIGNAL são condicionais — só acontecem quando ProfessorX/Vision
  realmente rodaram (não em casos de skip, budget guard, incremental, ou erro).

## Expiração Automática

Checkpoints têm TTL de 60 minutos por padrão. `clear_expired()` é chamado via
`CycleScheduler` ou manualmente. Checkpoints expirados são removidos por DELETE
direto via SQLAlchemy no `AuditRecord`.

## Testes

`tests/test_story_251_cycle_checkpoint.py` — 5 classes de teste cobrindo:

| Classe | O que testa |
|---|---|
| `TestCycleCheckpointSave` | log_event args, falha silenciosa, conversão de int→str |
| `TestCycleCheckpointLoad` | found/not found, filtro por stage, payload JSON string, silencia exceções |
| `TestCycleCheckpointExists` | True quando loaded, False quando None |
| `TestCycleCheckpointClearExpired` | rowcount retornado, zero em falha |
| `TestGetCycleCheckpointStore` | singleton, instância correta |
| `TestNickFuryCycleCheckpointIntegration` | restore analysis, restore signal, save→load round-trip, símbolo errado |

## Aceitação

- [x] `CycleCheckpointStore.save()` persiste via `MekkaRepository.log_event(agent="NICKFURY", event="CYCLE_CHECKPOINT")`
- [x] `CycleCheckpointStore.load()` recupera dados corretos por `(cycle_id, symbol, stage)`
- [x] `CycleCheckpointStore.load()` faz `json.loads()` quando payload é string
- [x] `CycleCheckpointStore.exists()` retorna `True`/`False` corretamente
- [x] `CycleCheckpointStore.clear_expired()` executa DELETE com cutoff por timestamp
- [x] Toda falha é silenciosa (`logger.debug`) — o ciclo nunca quebra por causa do checkpoint
- [x] `get_cycle_checkpoint_store()` retorna singleton
- [x] NickFury restaura ANALYSIS do checkpoint antes de chamar ProfessorX
- [x] NickFury salva ANALYSIS após ProfessorX concluir com sucesso
- [x] NickFury restaura SIGNAL do checkpoint antes de chamar Vision
- [x] NickFury salva SIGNAL após Vision concluir com sucesso (não salva em budget_skipped, incremental_skipped, ou vision_error)
- [x] `pytest tests/test_story_251_cycle_checkpoint.py` ✓

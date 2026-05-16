# Story 134 — Memory Consolidation

## Context

Story 128 introduziu o `SemanticEpisodicStore` com add() irrestrito e warm_up()
que carrega até 500 registros do SQLite. Com o tempo, o índice in-memory acumula
entradas semanticamente redundantes — trades com setups quase idênticos mas
resultados diferentes. Isso aumenta ruído na busca e dilui o sinal dos trades
mais informativos.

Implementado junto com Story 132 (Composite Scoring) no mesmo arquivo,
pois ambos modificam `semantic_memory.py` e complementam o pipeline de busca.

## Goal

Prevenir duplicatas semânticas no índice: dois mecanismos de dedup baseados em
similaridade cossenoidal com threshold configurável.

## Scope Delivered

### `src/langgraph/semantic_memory.py`

**`_max_cosine_similarity(emb) → float`** — helper que retorna a maior
similaridade cossenoidal de `emb` contra todas as entradas do índice.
Usado pelo `add()` antes de inserir.

**`_consolidate_entries() → int`** — sweep O(N²) pós-warm_up:
iterar entradas em ordem de chegada, descartar qualquer posterior cuja
similaridade com uma entrada já aceita seja `>= _consolidation_threshold`.
Retorna número de entradas removidas. Logga o resultado.

**`add()` — dedup on-write:**
```python
if _consolidation_enabled and _entries:
    if _max_cosine_similarity(emb) >= _consolidation_threshold:
        logger.debug("skipped dup")
        return
```

**`warm_up_from_db()` — consolidação pós-carregamento:**
```python
if _consolidation_enabled and len(_entries) > 1:
    await _consolidate_entries()
```

**`__init__()` — lê configuração do settings:**
```python
_consolidation_enabled = settings.semantic_memory_consolidation_enabled
_consolidation_threshold = settings.semantic_memory_consolidation_threshold
```

### `src/config/settings.py`

| Campo | Default | Descrição |
|-------|---------|-----------|
| `semantic_memory_consolidation_enabled` | `True` | Liga/desliga dedup |
| `semantic_memory_consolidation_threshold` | `0.92` | Threshold cossenoidal |

## Hard Rules Mantidas

- Consolidação é opcional (toggle via settings)
- `add()` fail-silent — qualquer erro retorna sem adicionar, sem propagar
- warm_up() continua normalmente mesmo se consolidação falhar
- Threshold padrão 0.92 preserva variantes com ≥8% diferença semântica

## Acceptance

- Testes cobertos em `tests/test_story_132_composite_scoring.py`
  (seção `TestMemoryConsolidation`, 6 testes)
- `_consolidate_entries()` com 3 embeddings idênticos + 1 diferente → remove 2
- `add()` com embedding idêntico ao existente → não adiciona (len permanece 1)
- `consolidation_enabled=False` → duplicata é adicionada normalmente

## Files Changed

*(Implementado em conjunto com Story 132)*

- `src/langgraph/semantic_memory.py`
- `src/config/settings.py`
- `tests/test_story_132_composite_scoring.py`
- `docs/stories/story-134-memory-consolidation.md` — este documento

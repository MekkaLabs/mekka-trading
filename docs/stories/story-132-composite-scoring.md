# Story 132 — Memory Composite Scoring

## Context

Story 128 introduziu o `SemanticEpisodicStore` com busca por similaridade cossenoidal pura.
A busca era 100% semântica — não levava em conta quando o trade ocorreu nem quão lucrativo foi.
Isso significa que um trade de 3 meses atrás com setup idêntico mas mercado diferente competia
igualmente com trades recentes e relevantes.

A partir do CrewAI Memory architecture e boas práticas de RAG com temporal awareness,
identificamos que busca de memórias episódicas deve combinar **relevância semântica**,
**recência** e **importância** para máxima utilidade como contexto para o Vision.

Story 134 (Memory Consolidation / dedup semântico) é implementada no mesmo arquivo
e entregue junto com Story 132.

## Goal

1. Substituir similaridade cossenoidal pura por **composite score** ponderado:
   ```
   composite = sem_w × similarity + rec_w × recency_decay + imp_w × importance
   ```
2. Calcular `recency_decay = 0.5^(age_days / half_life_days)` — memórias recentes pontuam mais.
3. Calcular `importance = |pnl_usd| / max_pnl` — trades de maior impacto financeiro pontuam mais.
4. Prevenir duplicatas semânticas no índice: dedup no `add()` e consolidação pós `warm_up()`.

## Scope Delivered

### `src/langgraph/semantic_memory.py`

- **`_compute_importance(pnl_usd, max_pnl=200.0) → float`**  
  Normaliza `|pnl_usd|` para [0, 1]. PnL nulo → 0.5 (neutro).

- **`_compute_recency_decay(recorded_at, half_life_days=30.0) → float`**  
  Decay exponencial `0.5^(age_days / half_life_days)`. Hoje → 1.0; 30 dias atrás → 0.5.

- **`_Entry` dataclass**  
  Dois campos novos: `recorded_at: Optional[datetime]` e `importance: float`.

- **`SemanticEpisodicStore.__init__()`**  
  Carrega `_consolidation_enabled` e `_consolidation_threshold` do settings.

- **`warm_up_from_db()`**  
  Extrai `timestamp` e `pnl_usd` de cada row; popula `recorded_at` e `importance`.  
  Executa `_consolidate_entries()` após indexação quando consolidação habilitada.

- **`add()`**  
  Computa `importance` pelo PnL; seta `recorded_at = now`.  
  Chama `_max_cosine_similarity()` antes de inserir — skip se dup ≥ threshold.

- **`search()`**  
  Calcula `composite_scores` por entrada; ordena e retorna com `{score, semantic_score, ...}`.  
  Lê pesos e half_life do settings via `getattr(settings, field, default)`.

- **`_cosine_similarities(q_emb)`**  
  Helper extraído: numpy batched ou fallback Python puro.

- **`_max_cosine_similarity(emb)`**  
  Story 134 — max similarity para dedup check em `add()`.

- **`_consolidate_entries()`**  
  Story 134 — O(N²) sweep: mantém entradas únicas pelo threshold cossenoidal.  
  Logga entradas removidas.

- **`build_context_snippet()`**  
  Label atualizado: `"Composite score range"` (era `"Semantic score range"`).

### `src/config/settings.py`

Seis campos novos na seção "Semantic Memory Composite Scoring":

| Campo | Default | Descrição |
|-------|---------|-----------|
| `semantic_memory_semantic_weight` | 0.5 | Peso da similaridade semântica |
| `semantic_memory_recency_weight` | 0.3 | Peso do decaimento por recência |
| `semantic_memory_importance_weight` | 0.2 | Peso da importância por PnL |
| `semantic_memory_recency_half_life_days` | 30.0 | Meia-vida em dias |
| `semantic_memory_consolidation_enabled` | True | Liga/desliga dedup |
| `semantic_memory_consolidation_threshold` | 0.92 | Threshold cossenoidal para dedup |

## Hard Rules Mantidas

- Fallback silencioso: qualquer falha no embedding → comportamento idêntico ao anterior
- Sem imports circulares: settings carregado lazy dentro dos métodos
- Sem dependências novas: numpy opcional (fallback Python puro)
- Threads de asyncio single event loop — sem locks

## Acceptance

- `pytest tests/test_story_132_composite_scoring.py -v` → verde (≥ 95% dos testes)
- `build_context_snippet()` retorna "Composite score range" no snippet
- `warm_up_from_db()` chama `_consolidate_entries()` quando `_consolidation_enabled=True`
- `add()` skipa entradas com similaridade ≥ 0.92 com `_consolidation_enabled=True`
- Pesos somam ~1.0 nos defaults (0.5 + 0.3 + 0.2)

## What's Next

- Story 133 — Vision Pre-Reasoning: reflect antes de gerar sinal (CrewAI Reasoning)
- Story 134 — docs apenas, código entregue aqui
- Story 135 — Adaptive Layer 1 Routing (Hierarchical Process)
- Story 136 — MekkaEventBus

## Files Changed

- `src/langgraph/semantic_memory.py` — composite scoring + consolidation
- `src/config/settings.py` — 6 novos campos
- `tests/test_story_132_composite_scoring.py` — 18 testes
- `docs/stories/story-132-composite-scoring.md` — este documento

# Story 128 — Memória Episódica Semântica (SemanticEpisodicStore)

**Versão:** 0.10.0-dev  
**Data:** 2026-05-15  
**Dependência:** Story 126 (LangGraph StateGraph + AsyncSqliteSaver), Story 063 (AgentMemoryStore SQL)

---

## Context

A Story 063 implementou memória episódica para o Vision via `AgentMemoryStore`:
o Vision consulta registros anteriores de trades com critérios de igualdade/range
(símbolo, action, RSI ±10, trend exato) antes de chamar o LLM, enriquecendo o
prompt com estatísticas de win-rate de padrões semelhantes.

Essa abordagem tem limitações estruturais:
1. **Matching rígido**: RSI 71 não casa com RSI 69 se o bucket for 70 — mesmo que o
   contexto de mercado seja praticamente idêntico.
2. **Sem semântica**: dois cenários semanticamente similares (ex: "BULLISH forte com
   volume alto") mas com RSI ligeiramente diferente são tratados como não-relacionados.
3. **Cobertura estreita**: poucos registros passam pelos filtros de igualdade, deixando
   a janela de memória subutilizada.

Com embeddings OpenAI `text-embedding-3-small`, cada registro de trade é convertido
em um vetor semântico. A busca por similaridade cossenoidal retorna os padrões
_mais relevantes semanticamente_, independente de thresholds numéricos.

---

## Goal

Implementar `SemanticEpisodicStore` — um índice in-memory de embeddings que substitui
a busca SQL bucket-matching do Vision no modo `--langgraph`. A memória é aquecida do
SQLite na inicialização do ciclo e atualizada em tempo real à medida que trades são
resolvidos pelo Cyclops.

**Não substitui** o `AgentMemoryStore` SQL — esse continua como fallback quando
`SemanticEpisodicStore` não estiver disponível (sem chave OpenAI, sem LangGraph).

---

## Architecture

```
make_checkpointed_graph()
        │
        ├── SemanticEpisodicStore(model="text-embedding-3-small")
        │         │
        │         └── warm_up_from_db(limit=500)
        │               └── AgentMemoryRecord (WIN/LOSS/NEUTRAL) → embed_batch()
        │
        └── fury._vision._semantic_store = store
                  │
                  └── Vision._build_memory_block(analysis, semantic_store=store)
                            │
                            ├── build_query_text() → embed_single() → cosine sim
                            └── build_context_snippet() → "[SemanticMemory] ..."
                                        injected into Vision LLM prompt
```

### Formato de texto para embedding

```
Memory: "LONG BTC | RSI=70 | trend=BULLISH | vol=HIGH | conf=0.82 | outcome=WIN | pnl=+$45.20 | hold=8.5h"
Query:  "LONG BTC | RSI=72 | trend=BULLISH | vol=HIGH | conf=0.85"
```

Incluir símbolo e action no texto garante que o modelo de embedding dê peso maior
a padrões do mesmo ativo e direção — sem precisar de filtros separados.

---

## Files Changed

### New

| Arquivo | Descrição |
|---------|-----------|
| `src/langgraph/semantic_memory.py` | `SemanticEpisodicStore` + helpers `build_memory_text()` / `build_query_text()` |
| `tests/test_story_128_semantic_memory.py` | 11 testes cobrindo text helpers, store CRUD, busca semântica mockada e routing do Vision |
| `docs/stories/story-128-semantic-memory.md` | Este documento |

### Modified

| Arquivo | Mudança |
|---------|---------|
| `src/agents/vision.py` | `self._semantic_store = None`; `_build_memory_block()` aceita `semantic_store` param; routing semântico vs SQL |
| `src/langgraph/cycle_graph.py` | `make_checkpointed_graph()` cria e aquece o store, injeta em `fury._vision._semantic_store` |
| `docs/stories/INDEX.md` | Story 128 adicionada ao Milestone 19 |

---

## Implementation Details

### SemanticEpisodicStore

```python
class SemanticEpisodicStore:
    _EMBED_BATCH_SIZE = 100  # max textos por chamada OpenAI

    async def warm_up_from_db(self, limit: int = 500) -> int: ...
    async def add(self, symbol, action, rsi, trend, ...) -> None: ...
    async def search(self, query: str, limit: int = 8, filter_fn=None) -> list[dict]: ...
    async def build_context_snippet(self, symbol, action, rsi, ...) -> str: ...
    async def _embed_single(self, text: str) -> list[float]: ...
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

**Similaridade cossenoidal** via numpy (fallback pure Python se numpy indisponível):
```
score = (query_emb · entry_emb) / (||query_emb|| * ||entry_emb||)
```

### Vision routing

```python
# _build_memory_block() — Story 128 path
if semantic_store is not None:
    for action in ("LONG", "SHORT"):
        snippet = await semantic_store.build_context_snippet(...)
    return "=== Historical Pattern Memory (Semantic Search) ===\n..."

# Story 063 fallback path (unchanged)
long_ctx = await AgentMemoryStore.query_similar(...)
```

### Injeção pelo LangGraph

```python
# make_checkpointed_graph() — cycle_graph.py
try:
    _sem_store = SemanticEpisodicStore(model="text-embedding-3-small")
    n_loaded = await _sem_store.warm_up_from_db(limit=500)
    fury._vision._semantic_store = _sem_store
    logger.info(f"[LG:graph] SemanticEpisodicStore pronto — {n_loaded} memórias")
except Exception as _exc:
    logger.warning(f"[LG:graph] SemanticEpisodicStore indisponível: {_exc}")
    # Vision usa fallback SQL automaticamente
```

---

## Fail-Silent Design

| Cenário | Comportamento |
|---------|---------------|
| `OPENAI_API_KEY` não configurada | `_embed_batch()` lança `ValueError` → capturado → store vazio, Vision usa SQL |
| OpenAI timeout / 429 | Exceção capturada em `build_context_snippet()` → retorna `""` → Vision usa SQL |
| Store vazio (zero trades resolvidos) | `search()` retorna `[]` → `build_context_snippet()` retorna `""` |
| `warm_up_from_db()` falha | `is_ready = True`, store vazio, zero impacto no ciclo |
| Exceção em `_build_memory_block()` | Capturada no `_run()` do Vision, `debug` log, LLM chamado sem memória |

---

## Tests

```
tests/test_story_128_semantic_memory.py
├── TestBuildTexts (4 testes)
│   ├── test_build_memory_text_win
│   ├── test_build_memory_text_loss
│   ├── test_build_memory_text_no_rsi
│   └── test_build_query_text
├── TestSemanticEpisodicStore (5 testes) — _embed_single mockado via AsyncMock
│   ├── test_empty_store_returns_no_results
│   ├── test_add_and_search
│   ├── test_filter_fn_applied
│   ├── test_build_context_snippet_non_empty
│   ├── test_build_context_snippet_empty_store
│   └── test_warm_up_empty_db
└── TestVisionMemoryRouting (3 testes)
    ├── test_uses_semantic_store_when_available
    ├── test_falls_back_to_sql_when_no_semantic_store
    └── test_semantic_store_exception_returns_empty
```

Todos os testes de embedding usam `patch.object(store, "_embed_single", new_callable=AsyncMock)`
para evitar chamadas reais à API OpenAI.

---

## Upgrade Path

1. **Sem flags adicionais** — `--langgraph` já ativa o SemanticEpisodicStore automaticamente.
2. **Modo clássico** (`--no-langgraph`) — `Vision._semantic_store` permanece `None`, SQL path inalterado.
3. **Novas memórias** — quando Cyclops resolve um trade, `store.add()` pode ser chamado para
   atualização em tempo real (Story 129+ pode implementar o wire-up no Cyclops).

---

## Definition of Done

- [x] `SemanticEpisodicStore` implementado com warm_up, add, search, build_context_snippet
- [x] `build_memory_text()` e `build_query_text()` helpers
- [x] `Vision._build_memory_block()` roteia para semântico quando store disponível
- [x] `make_checkpointed_graph()` cria e aquece o store, injeta no Vision
- [x] 11 testes passando sem chamadas reais à OpenAI
- [x] Fail-silent em todos os pontos de falha possíveis
- [x] Story doc criado
- [x] INDEX.md atualizado

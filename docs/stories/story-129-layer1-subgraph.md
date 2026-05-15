# Story 129 — Layer 1 Parallel Subgraph

**Versão:** 0.10.0-dev  
**Data:** 2026-05-15  
**Dependência:** Story 126 (LangGraph StateGraph + AsyncSqliteSaver), Story 129

---

## Context

O `ProfessorX` usa `asyncio.gather()` para executar os 6 agentes da Layer 1 em
paralelo. Isso funciona bem, mas tem uma limitação: não há checkpoint por agente.
Se o processo morrer enquanto Thor está buscando dados de volatilidade, na próxima
execução todos os 6 agentes rodam do zero — incluindo Superman, que já tinha
concluído com sucesso.

Com LangGraph, cada nó é um ponto de checkpoint independente. Se Thor crasha no
super-step 2, o LangGraph retoma exatamente dali — sem re-executar Superman,
DoctorStrange, BlackPanther, Aquaman ou Flash, que já tinham completado.

---

## Goal

Implementar o fan-out da Layer 1 como um LangGraph `StateGraph` compilado,
substituindo o `asyncio.gather()` do ProfessorX no modo `--langgraph`. O subgrafo
usa o mesmo `AsyncSqliteSaver` do ciclo principal, com thread IDs no namespace
`"{cycle_id}:{symbol}:l1"` para evitar conflitos.

**Não substitui** o `ProfessorX.run()` no modo clássico — esse continua sendo
usado como fallback quando `layer1_graph` não está disponível.

---

## Architecture

```
START → superman_node
             ├── sentiment_node (DoctorStrange)  ─┐
             ├── onchain_node   (BlackPanther)     │
             ├── thor_node      (Thor)             ├── spiderman_node → assemble_node → END
             ├── aquaman_node   (Aquaman)          │
             └── flash_node     (Flash)           ─┘
```

### Checkpointing por super-step

| Super-step | Nós executados        | Checkpointado após |
|------------|-----------------------|-------------------|
| 1          | superman              | chart + conf_chart |
| 2          | sentiment, onchain, thor, aquaman, flash (paralelo) | todos 5 outputs |
| 3          | spiderman             | anomaly |
| 4          | assemble              | analysis (MarketAnalysis final) |

Se o processo crashar no super-step 2 (ex: Thor timeout), na próxima invocação
do grafo com o mesmo thread_id, o LangGraph pula os nós já concluídos no
super-step 2 e re-executa apenas Thor.

### Serialização

Os nós escrevem `Pydantic.model_dump(mode="json")` no estado.
O `assemble_node` reconstrói `MarketAnalysis` via `model_validate()`.
Todos os campos do `Layer1State` são JSON-serializáveis.

### Thread ID

```
cycle_id: "550e8400-e29b-41d4-a716-446655440000"
symbol:   "BTC"
→ layer1 thread_id: "550e8400-e29b-41d4-a716-446655440000:BTC:l1"
```

---

## Files Changed

### New

| Arquivo | Descrição |
|---------|-----------|
| `src/langgraph/layer1_graph.py` | `Layer1State`, `build_layer1_graph()`, `run_layer1_subgraph()` |
| `tests/test_story_129_layer1_subgraph.py` | 8 testes cobrindo estrutura, routing e integração |
| `docs/stories/story-129-layer1-subgraph.md` | Este documento |

### Modified

| Arquivo | Mudança |
|---------|---------|
| `src/langgraph/cycle_graph.py` | `make_checkpointed_graph()` compila layer1 graph; `process_symbol_node` passa `layer1_graph` |
| `src/agents/nick_fury.py` | `self._layer1_graph = None`; `_cycle_for_symbol()` aceita `layer1_graph` e usa `run_layer1_subgraph()` quando disponível |
| `docs/stories/INDEX.md` | Story 129 adicionada ao Milestone 19 |

---

## Implementation Details

### Layer1State

```python
class Layer1State(TypedDict):
    symbol: str
    chart: Optional[dict]              # MarketData.model_dump(mode="json")
    confirmation_chart: Optional[dict]
    sentiment: Optional[dict]
    onchain: Optional[dict]
    volatility: Optional[dict]
    liquidity: Optional[dict]
    momentum: Optional[dict]
    anomaly: Optional[dict]
    errors: Annotated[list[str], operator.add]  # reducer: acumula
    analysis: Optional[dict]           # MarketAnalysis final
```

### Injeção pelo LangGraph

```python
# make_checkpointed_graph() — cycle_graph.py
try:
    from src.langgraph.layer1_graph import build_layer1_graph
    _layer1_graph = build_layer1_graph(fury._professor).compile(checkpointer=saver)
    fury._layer1_graph = _layer1_graph
    logger.info("[LG:graph] Layer 1 subgraph compilado")
except Exception as _l1_exc:
    fury._layer1_graph = None
    logger.warning(f"[LG:graph] Layer 1 subgraph indisponível: {_l1_exc}")
```

### Routing em _cycle_for_symbol()

```python
if layer1_graph is not None and lg_thread_id is not None:
    # Story 129 — LangGraph fan-out com checkpoints por agente
    analysis = await run_layer1_subgraph(
        graph=layer1_graph,
        symbol=symbol,
        cycle_id=lg_thread_id,
    )
else:
    # Fallback — asyncio.gather via ProfessorX (modo clássico)
    analysis = await self._professor.run(symbol=symbol)
```

---

## Fail-Silent Design

| Cenário | Comportamento |
|---------|---------------|
| `build_layer1_graph()` falha | `fury._layer1_graph = None` → `_cycle_for_symbol()` usa ProfessorX |
| Superman node crasha | `chart=None`, `analysis=None` → `run_layer1_subgraph()` levanta `AgentError` → `CycleReport(error=...)` |
| Qualquer outro agente crasha | Campo fica `None`, `errors` acumula, ciclo continua com MarketAnalysis parcial |
| `run_layer1_subgraph()` levanta exceção inesperada | Capturado como `AgentError` no `_cycle_for_symbol()` → `CycleReport(error=...)` |

---

## Tests

```
tests/test_story_129_layer1_subgraph.py
├── TestLayer1GraphStructure (4 testes)
│   ├── test_layer1_state_has_required_fields
│   ├── test_build_layer1_graph_returns_state_graph
│   ├── test_graph_has_expected_nodes
│   └── test_graph_compiles_without_error
├── TestRunLayer1Subgraph (3 testes)
│   ├── test_success_returns_market_analysis
│   ├── test_superman_failure_raises_agent_error
│   └── test_thread_id_format
├── TestNickFuryCycleRouting (2 testes)
│   ├── test_uses_layer1_graph_when_provided
│   └── test_fallback_to_professor_when_no_layer1_graph
└── TestNickFuryLayerGraphAttribute (1 teste)
    └── test_nick_fury_has_layer1_graph_attribute
```

---

## Definition of Done

- [x] `Layer1State` TypedDict com 11 campos JSON-serializáveis
- [x] `build_layer1_graph()` retorna StateGraph com 8 nós + fan-out/fan-in correto
- [x] `run_layer1_subgraph()` helper que invoca o grafo e devolve `MarketAnalysis`
- [x] `make_checkpointed_graph()` compila layer1 graph com o mesmo saver
- [x] `_cycle_for_symbol()` roteia para layer1 quando `layer1_graph` disponível
- [x] Fallback para `ProfessorX.run()` quando layer1_graph=None
- [x] 10 testes passando sem chamadas reais à exchange
- [x] Fail-silent em todos os pontos críticos
- [x] Story doc criado
- [x] INDEX.md atualizado

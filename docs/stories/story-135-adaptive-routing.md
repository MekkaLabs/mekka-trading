# Story 135 — Adaptive Layer 1 Routing

## Context

O subgrafo Layer 1 (Story 129) sempre executa todos os 5 agentes paralelos
(DoctorStrange, BlackPanther, Thor, Aquaman, Flash), independente do regime de
mercado. Em volatilidade extrema, macro sentiment e momentum intra-candle têm
baixa relevância — e executar todos os agentes consome tempo e tokens
desnecessariamente.

Inspirado no padrão **CrewAI Hierarchical Process** — onde um manager agent
delega para sub-agentes com base em contexto — a Story 135 introduz um
`routing_node` que inspeciona o regime de volatilidade do chart (ATR%) e decide
quais agentes pular neste ciclo.

## Goal

Após Superman gerar o chart, um `routing_node` serializado (antes do fan-out)
classifica o regime de mercado e escreve um `skip_set` no estado. Cada agente
secundário (sentiment, onchain, thor, aquaman, flash) verifica se está no
`skip_set` e retorna `None` imediatamente se sim — sem chamar APIs externas.

## Scope Delivered

### `src/langgraph/layer1_graph.py`

**Funções novas (module-level):**

- **`_classify_regime(chart_dict) → str`**  
  Deriva `EXTREME / HIGH / LOW / NORMAL` a partir de `atr_pct`:  
  `> 5%` → EXTREME, `> 2%` → HIGH, `< 0.5%` → LOW, else NORMAL.  
  Fallback: campo `regime` no dict, ou NORMAL se ausente.

- **`_decide_skip_set(chart_dict) → list[str]`**  
  Retorna `[]` se `layer1_routing_enabled=False`.  
  Carrega override CSV do settings (`layer1_routing_{regime}_skip`).  
  Defaults embutidos:  
  - NORMAL → `[]`  
  - HIGH → `["flash"]`  
  - EXTREME → `["sentiment", "flash"]`  
  - LOW → `["onchain", "flash"]`

**`Layer1State` — campo novo:**
```python
skip_set: Optional[list[str]]  # nós a pular neste ciclo (None = rodar tudo)
```

**`routing_node` (novo nó):**  
Executa após `superman`, antes do fan-out.  
Chama `_decide_skip_set(chart_dict)` → escreve `skip_set` no estado.

**Nós atualizados (cada um verifica skip_set):**  
`sentiment_node`, `onchain_node`, `thor_node`, `aquaman_node`, `flash_node`  
→ cada um: `if "<nome>" in (state.get("skip_set") or []): return {field: None, ...}`

**Topologia atualizada:**
```
START → superman → routing → [sentiment, onchain, thor, aquaman, flash]
                                                     ↓
                                               spiderman → assemble → END
```

### `src/config/settings.py`

| Campo | Default | Descrição |
|-------|---------|-----------|
| `layer1_routing_enabled` | `False` | Liga/desliga routing adaptativo |
| `layer1_routing_normal_skip` | `""` | Skip CSV para NORMAL |
| `layer1_routing_high_skip` | `"flash"` | Skip CSV para HIGH |
| `layer1_routing_extreme_skip` | `"sentiment,flash"` | Skip CSV para EXTREME |
| `layer1_routing_low_skip` | `"onchain,flash"` | Skip CSV para LOW |

Ativação: `LAYER1_ROUTING_ENABLED=true`

## Hard Rules Mantidas

- `layer1_routing_enabled=False` (default) → comportamento 100% idêntico à Story 129
- Falha no `routing_node` → `skip_set=[]`, todos os agentes rodam normalmente
- Superman failure → `chart=None` → `_classify_regime(None)=NORMAL` → skip set vazio
- Nenhuma dependência nova; topologia LangGraph estendida (nó extra, não substituição)

## Acceptance

- `pytest tests/test_story_135_adaptive_routing.py -v` → verde
- `_classify_regime({"atr_pct": 6.0}) == "EXTREME"`
- `_decide_skip_set` com routing disabled → `[]`
- `_decide_skip_set` com EXTREME → `["sentiment", "flash"]`
- Layer1State tem campo `skip_set`
- Settings defaults: `layer1_routing_enabled=False`

## What's Next

- Story 136 — MekkaEventBus (lightweight pub/sub in-process)

## Files Changed

- `src/langgraph/layer1_graph.py` — `_classify_regime`, `_decide_skip_set`, `routing_node`, skip checks nos 5 nós, `Layer1State.skip_set`
- `src/config/settings.py` — 5 novos campos de routing
- `tests/test_story_135_adaptive_routing.py` — 22 testes
- `docs/stories/story-135-adaptive-routing.md` — este documento

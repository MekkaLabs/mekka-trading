# Story 126 — LangGraph AsyncSqliteSaver: Durable Execution no NickFury

**Versão:** 0.10.0-dev  
**Data:** 2026-05-15  
**Dependência externa:** `langgraph>=0.2.0`, `langgraph-checkpoint-sqlite>=2.0.0`

---

## Context

O ciclo principal de 4h do NickFury processa múltiplos símbolos em sequência.
Se o processo morrer após processar BTC mas antes de processar ETH, o ciclo
inteiro se perde — no próximo restart, BTC seria analisado novamente (chamada
de API duplicada, sinal potencialmente repetido).

LangGraph oferece `AsyncSqliteSaver` que grava o estado do grafo entre
"super-steps" (nós). Com checkpointing por símbolo, um crash durante ETH
permite retomar de ETH — não de BTC.

---

## Goal

Envolver o ciclo NickFury em um `StateGraph` LangGraph com `AsyncSqliteSaver`,
adicionando durable execution sem quebrar o pipeline existente. O pipeline
original (`run_main_cycle`) permanece intacto — o modo LangGraph é opt-in via
`--langgraph`.

---

## Scope Delivered

### Novos arquivos

- **`src/langgraph/__init__.py`** — módulo LangGraph do projeto
- **`src/langgraph/state.py`** — `MekkaCycleState` TypedDict serializável
- **`src/langgraph/cycle_graph.py`** — `build_cycle_graph()`, `make_checkpointed_graph()`, `make_initial_state()`
- **`tests/test_story_126_langgraph_checkpointing.py`** — testes com `pytest.importorskip`

### Arquivos modificados

- **`src/agents/nick_fury.py`** — novo método `run_with_checkpointing()`
- **`run.py`** — flag `--langgraph` no argparse, `_run_once` aceita `langgraph=bool`
- **`requirements.txt`** — `langgraph>=0.2.0`, `langgraph-checkpoint-sqlite>=2.0.0`

### Arquitetura do grafo

```
START → preflight ──(skip_reason?)──→ finalize → END
                └──(normal)────────→ process_symbol ──┐
                                          ↑             │ self-loop
                                          └─────────────┘ (symbols_remaining > 0)
                                          │ (empty)
                                          └──→ finalize → END
```

### MekkaCycleState (campos JSON-serializáveis)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `cycle_id` | str | UUID único por ciclo |
| `equity_usd` | float | Equity efetivo |
| `symbols_remaining` | list[str] | Fila de símbolos a processar |
| `symbols_completed` | list[str] | Símbolos já processados |
| `reports` | Annotated[list[dict], add] | Reports acumulados (reducer) |
| `skip_reason` | str \| None | Se preenchido, ciclo foi abortado |
| `open_positions` | int | Contador atualizado por símbolo |
| `trades_today` | int | Contador atualizado por símbolo |
| `drawdown_pct` | float | Drawdown lido no preflight |
| `running_notional_usd` | float | Notional acumulado |

### Como usar

```bash
# Instalar (única vez)
pip3 install langgraph langgraph-checkpoint-sqlite --break-system-packages

# Rodar com checkpointing
python3 run.py --once --langgraph

# Pipeline original (sem mudança)
python3 run.py --once
```

### Checkpointer

`AsyncSqliteSaver` grava em `data/mekka_trading.db` (mesmo arquivo do
MekkaRepository). Cria tabelas próprias: `checkpoints`, `checkpoint_blobs`,
`checkpoint_writes`. Sem conflito com as tabelas existentes.

---

## Hard Rules Mantidas

- `paper_trading=True` — Iron Man nunca tocou a SDK em modo live.
- Batman continua gate intransponível — chamado dentro de `_cycle_for_symbol`.
- Pipeline original (`run_main_cycle`) intocado — modo LangGraph é opt-in.
- Nenhuma API key real em código.

---

## Acceptance

- [x] `src/langgraph/` criado com sintaxe válida (verificado com `ast.parse`)
- [x] `run.py` aceita `--langgraph` sem erro de importação
- [x] Testes têm `pytest.importorskip("langgraph")` — passam mesmo sem LangGraph instalado
- [x] `run_main_cycle()` intocado — backward compatible
- [x] `requirements.txt` atualizado

---

## What's Next

- **Story 127**: Migrar Telegram Trade Approval (Story 074) para `interrupt()` + `Command(resume=...)` dentro do `process_symbol_node`. Operador aprova via Telegram; bot chama `graph.invoke(Command(resume=True))`.
- **Story 128**: `InMemoryStore` + embeddings OpenAI para memória semântica do Vision.
- **Story 129**: Layer 1 (ProfessorX + 6 agentes) como subgrafo paralelo com checkpoints por agente.

---

## Files Changed

| Arquivo | Tipo |
|---------|------|
| `src/langgraph/__init__.py` | NEW |
| `src/langgraph/state.py` | NEW |
| `src/langgraph/cycle_graph.py` | NEW |
| `src/agents/nick_fury.py` | MODIFIED (+`run_with_checkpointing`) |
| `run.py` | MODIFIED (+`--langgraph`) |
| `requirements.txt` | MODIFIED |
| `tests/test_story_126_langgraph_checkpointing.py` | NEW |

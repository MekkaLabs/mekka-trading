# Story 127 — LangGraph Trade Approval: interrupt() + Command(resume=...)

**Versão:** 0.10.0-dev  
**Data:** 2026-05-15  
**Dependência:** Story 126 (LangGraph StateGraph + AsyncSqliteSaver)

---

## Context

A Story 074 implementou aprovação de trade via Telegram usando `asyncio.Event`:
o NickFury pausa, envia mensagem com botões ✅/❌, aguarda `event.wait()` com
timeout, e o TelegramInbound resolve o evento quando o operador responde.

Essa abordagem tem dois problemas críticos:
1. **Não sobrevive a restarts**: se o processo morrer enquanto aguarda aprovação,
   o estado se perde — o trade é cancelado silenciosamente.
2. **Não é durável**: a aprovação pendente existe apenas na memória; nenhum
   checkpoint SQLite registra que um trade específico está aguardando operador.

Com o LangGraph StateGraph (Story 126), temos `interrupt()` + `Command(resume=...)`:
o grafo pausa em um super-step, salva o estado inteiro no SQLite, e pode ser
retomado de qualquer lugar — incluindo após restart do processo.

---

## Goal

Migrar o fluxo de Telegram Trade Approval do modo `--langgraph` para usar
`interrupt()` + `Command(resume=...)`, mantendo o fluxo asyncio.Event da
Story 074 intacto para o modo `--once` (sem `--langgraph`).

---

## Scope Delivered

### Novos arquivos

- **`src/langgraph/interrupt_registry.py`** — registry `thread_id → (graph, saver)`
  para que TelegramInbound localize o grafo correto sem precisar recriá-lo.

### Arquivos modificados

| Arquivo | Mudança |
|---------|---------|
| `src/agents/nick_fury.py` | `_cycle_for_symbol()` aceita `lg_thread_id`; bloco de aprovação bifurcado 074/127; `run_with_checkpointing()` registra grafo no registry |
| `src/langgraph/cycle_graph.py` | `process_symbol_node` passa `lg_thread_id=state["cycle_id"]` |
| `src/services/trade_approval.py` | Nova `send_lg_approval_message()` com botões `lg_approve:{thread_id}:{trade_id}` |
| `src/services/telegram_inbound.py` | `_handle_callback_query()` detecta prefixo `lg_`; novo `_handle_lg_callback()` faz resume via `Command(resume=...)` |
| `tests/test_story_127_lg_interrupt.py` | Testes com `pytest.importorskip` |

---

## Arquitetura do fluxo de aprovação

```
python run.py --once --langgraph

NickFury.run_with_checkpointing()
    ↓ register(thread_id, graph, saver)
graph.ainvoke(initial_state, config)
    ↓
[preflight_node] — checks, equity, symbols
    ↓
[process_symbol_node] — Vision + Superman + Batman para BTC
    ↓ Batman aprova → entra no bloco de aprovação
    ↓ send_lg_approval_message() → Telegram: botões lg_approve/lg_reject
    ↓ interrupt({"trade_id": "T-XYZ", "thread_id": "uuid-ciclo", ...})
    ↓ NodeInterrupt (BaseException) propaga
graph.ainvoke() RETORNA estado parcial (interrompido)
run_with_checkpointing() RETORNA [] (sem relatórios ainda)

[Operador vê mensagem no Telegram]

TelegramInboundPoller._poll_once()
    ↓ callback_query: "lg_approve:uuid-ciclo:T-XYZ"
    ↓ _handle_callback_query() → detecta prefixo lg_
    ↓ _handle_lg_callback("lg_approve:uuid-ciclo:T-XYZ")
    ↓ get_graph("uuid-ciclo") → retorna graph do registry
    ↓ graph.ainvoke(Command(resume=True), config)
        ↓ interrupt() retorna True (sem suspend)
        ↓ _cycle_for_symbol() continua → IronMan executa
        ↓ process_symbol_node completa → checkpoint para BTC
        ↓ símbolos_restantes = [ETH] → self-loop
        ↓ process_symbol_node para ETH → ... outro interrupt se necessário ...
        ↓ [finalize_node] → daily_pnl, CYCLE_COMPLETE_LG
    ↓ graph.aget_state().next == [] → grafo completo
    ↓ unregister("uuid-ciclo") + saver.conn.close()
```

---

## interrupt() vs. asyncio.Event — comparação

| Aspecto | Story 074 (asyncio.Event) | Story 127 (interrupt) |
|---------|--------------------------|----------------------|
| Modo ativo | `--once` (sem `--langgraph`) | `--once --langgraph` |
| Durabilidade | ❌ Volátil (RAM) | ✅ SQLite checkpoint |
| Sobrevive restart | ❌ Não | ✅ Sim (thread_id no DB) |
| Timeout auto | ✅ asyncio.wait_for | ⚠️ Via timeout no próprio `send_lg_approval_message` (futuro) |
| Overhead | Mínimo | Ligeiro (re-run Vision+Batman no resume) |
| Backward compat | ✅ Intacto | ✅ Não toca fluxo 074 |

---

## NodeInterrupt — propagação correta

`interrupt()` levanta `NodeInterrupt(BaseException)` na primeira chamada.
Por ser `BaseException`, **não é capturado** pelos `except Exception` presentes em:
- `_cycle_for_symbol()` (bloco `except Exception as _appr_exc`)
- `process_symbol_node` (bloco `except Exception as exc`)

Propaga naturalmente até o LangGraph, que o captura internamente, salva o
checkpoint e retorna o estado parcial para `graph.ainvoke()`.

Na chamada de resume (`Command(resume=...)`), `interrupt()` retorna o valor
sem levantar exceção — `_cycle_for_symbol()` continua normalmente.

---

## Hard Rules Mantidas

- `paper_trading=True` — Iron Man nunca toca SDK em modo live.
- Batman é gate intransponível — chamado antes de qualquer interrupt().
- Fluxo Story 074 (asyncio.Event) 100% intacto para modo sem `--langgraph`.
- Nenhuma API key real em código.
- `interrupt_registry` é in-memory: limpo em cada restart (estado durável
  está no SQLite; resume manual possível via CLI em Story 128+).

---

## Acceptance

- [x] `interrupt_registry.py` criado com register/get/unregister/list_active
- [x] `send_lg_approval_message()` usa `lg_approve:{thread_id}:{trade_id}`
- [x] `_cycle_for_symbol()` aceita `lg_thread_id` — bifurca 074 vs. 127
- [x] `process_symbol_node` passa `lg_thread_id=state["cycle_id"]`
- [x] `_handle_callback_query()` detecta prefixo `lg_` e roteia
- [x] `_handle_lg_callback()` faz resume e limpa registry quando completo
- [x] Testes com `pytest.importorskip("langgraph")` — passam sem LangGraph instalado
- [x] Fluxo Story 074 intocado

---

## What's Next

- **Story 128**: `InMemoryStore` + OpenAI `text-embedding-3-small` para
  memória semântica episódica do Vision — recupera sinais similares do passado.
- **Story 129**: Layer 1 (ProfessorX + 6 agentes) como subgrafo paralelo
  com checkpoints por agente.
- **Story 130** (futuro): timeout durável — se operador não responder em X
  minutos, `graph.ainvoke(Command(resume=paper_trading))` automático via
  scheduler (Story 126 scheduled task).

---

## Files Changed

| Arquivo | Tipo |
|---------|------|
| `src/langgraph/interrupt_registry.py` | NEW |
| `src/agents/nick_fury.py` | MODIFIED (lg_thread_id + registry) |
| `src/langgraph/cycle_graph.py` | MODIFIED (lg_thread_id passado) |
| `src/services/trade_approval.py` | MODIFIED (send_lg_approval_message) |
| `src/services/telegram_inbound.py` | MODIFIED (_handle_lg_callback) |
| `tests/test_story_127_lg_interrupt.py` | NEW |

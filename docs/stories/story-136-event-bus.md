# Story 136 — MekkaEventBus

## Context

O pipeline Mekka Trading tem vários agentes produzindo eventos relevantes
(sinal do Vision, aprovação do Batman, execução do IronMan, erros) mas nenhum
canal estruturado de observabilidade intra-ciclo. Logs existem, mas não há uma
forma de plug-ins externos (dashboards, alertas customizados, métricas) receberem
esses eventos sem modificar o código de cada agente.

Inspirado no padrão **CrewAI Event Listeners** — que expõe hooks para cada fase
do ciclo de um agent/crew — a Story 136 introduz o `MekkaEventBus`: um pub/sub
in-process leve que permite desacoplar produtores de eventos dos consumidores.

## Goal

Criar `src/services/event_bus.py` com um pub/sub asyncio in-process. Integrar
no `NickFury._cycle_for_symbol()` para publicar 5 eventos padrão por ciclo.
Subscritores (sync ou async) se registram via `subscribe()` sem alterar o pipeline.

## Scope Delivered

### `src/services/event_bus.py` (novo)

**`MekkaEventBus`** — classe principal:

- **`subscribe(topic, handler)`** — registra handler para topic. `topic="*"` = wildcard.
- **`unsubscribe(topic, handler)`** — remove handler. No-op se não registrado.
- **`publish(topic, payload) → int`** — publica evento. Injeta `"topic"` no payload.
  Chama todos handlers (paralelo via `asyncio.gather`). Fail-silent: erros logados.
  Retorna número de handlers com sucesso.
- **`publish_sync(topic, payload)`** — wrapper síncrono via `create_task` / `asyncio.run`.
- **`subscriber_count(topic) → int`** — para testes e monitoramento.
- **`event_count(topic) → int`** — contador de publicações por topic.
- **`topics() → list[str]`** — topics com ≥1 publicação.
- **`reset_counters()`** / **`clear()`** — para testes.

**`get_event_bus() → MekkaEventBus`** — singleton global.  
**`reset_event_bus()`** — reseta singleton (para testes).

Handlers podem ser sync ou async — `_call_handler()` detecta com `inspect.iscoroutinefunction`.

### `src/agents/nick_fury.py`

`_cycle_for_symbol()` publica 5 eventos padrão via helper `_emit()` fail-silent:

| Evento | Momento | Payload key fields |
|--------|---------|-------------------|
| `cycle.start` | Início do ciclo | `cycle_id, symbol, timestamp` |
| `vision.signal` | Após salvar sinal | `cycle_id, symbol, action, confidence, signal_id` |
| `batman.gate` | Após Batman risk gate | `cycle_id, symbol, verdict, approved, reasons` |
| `ironman.exec` | Após IronMan executa | `cycle_id, symbol, status, is_paper, order_id` |
| `cycle.end` | Antes do return final | `cycle_id, symbol, timestamp, outcome` |

### Eventos padrão documentados no módulo

```
cycle.start    cycle.end    vision.signal
batman.gate    ironman.exec    agent.error
layer1.routing
```

## Hard Rules Mantidas

- Fail-silent: erros em qualquer handler não interrompem o pipeline
- Import lazy: `get_event_bus()` importado dentro do `_emit()` helper — sem import circular
- Default = zero subscribers → comportamento 100% idêntico ao anterior
- Nenhuma dependência nova; asyncio puro
- Singleton thread-safe para asyncio single event loop

## Acceptance

- `pytest tests/test_story_136_event_bus.py -v` → verde
- Pub/sub funciona: handler recebe evento com `topic` injetado
- Wildcard `"*"` recebe todos os tópicos
- Handler que lança exceção → fail-silent, outros handlers continuam
- Singleton: `get_event_bus()` retorna mesma instância
- `nick_fury._cycle_for_symbol()` publica `cycle.start` e `vision.signal`

## What's Next

- Milestone 21 sugerido: OpenTelemetry Tracing formal (Story 137)
  — span por agente, `trace_id` ligando o pipeline completo
- Ou: Adaptive Memory Decay (Story 138)
  — `SemanticEpisodicStore` com janela deslizante automática

## Files Changed

- `src/services/event_bus.py` — novo (MekkaEventBus + singleton)
- `src/agents/nick_fury.py` — 5 eventos publicados em `_cycle_for_symbol()`
- `tests/test_story_136_event_bus.py` — 24 testes
- `docs/stories/story-136-event-bus.md` — este documento

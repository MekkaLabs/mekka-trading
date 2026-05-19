# Story 250 — Vision Structured Output

## Objetivo

Substituir o `json.loads()` manual na Vision por **OpenAI Structured Output** via Pydantic,
eliminando respostas malformadas e simplificando o parse da saída do LLM.

## Motivação

A Vision confiava em `json.loads(raw)` sobre texto gerado livremente, o que causava
falhas intermitentes quando o modelo emitia markdown, comentários ou JSON truncado.
O padrão OpenAI Structured Output garante que o modelo produza JSON válido e
compatível com o schema Pydantic, eliminando a necessidade de limpeza manual.

## Implementação

### `src/models/vision_output.py`

| Componente | Descrição |
|---|---|
| `TradingSignalOutput` | Modelo Pydantic que espelha exatamente o schema JSON que a Vision emite |

**Campos:**

| Campo | Tipo | Default | Restrição |
|---|---|---|---|
| `action` | `str` | `"HOLD"` | — |
| `confidence` | `float` | `0.5` | `[0.0, 1.0]` |
| `entry_price` | `float` | `0.0` | `≥ 0` |
| `stop_loss` | `float` | `0.0` | `≥ 0` |
| `take_profit` | `float` | `0.0` | `≥ 0` |
| `size_pct` | `float` | `0.02` | `[0.0, 1.0]` |
| `leverage` | `int` | `1` | `[1, 50]` |
| `reasoning` | `str` | `""` | — |
| `agent_contributions` | `Dict[str, Any]` | `{}` | — |

> Tipos primitivos (`str`/`float`/`int`) em vez de Enum garantem compatibilidade máxima
> com o schema JSON simplificado exigido pelo OpenAI Structured Output.

### `src/agents/llm_client.py`

Três novos métodos adicionados à classe `LLMClient`:

#### `chat_structured(system_prompt, user_prompt, response_model, agent_id="")`

API pública para structured output. Retorna uma instância Pydantic validada ou `None`.

- **OpenAI**: usa `client.beta.chat.completions.parse(response_format=Model)` — schema garantido.
- **Anthropic**: fallback JSON mode via `_call_anthropic()` + limpeza de code fences + `model_validate()`.
- **Falha silenciosa**: qualquer exceção retorna `None`; o chamador deve usar o path raw JSON.
- **Observabilidade**: publica `llm.call.completed` com `"structured": True` para distinguir os paths.

#### `_call_openai_structured(system_prompt, user_prompt, response_model)`

Interno. Chama `client.beta.chat.completions.parse()` e retorna `(parsed_model, tokens_in, tokens_out)`.

#### `_call_anthropic_structured(system_prompt, user_prompt, response_model)`

Interno. Chama `_call_anthropic()`, limpa code fences, faz `json.loads()` + `model_validate()`.
Retorna `(parsed_model, tokens_in, tokens_out)`.

### `src/agents/vision.py`

Dois pontos de mudança:

#### `_call_llm_structured(user_prompt) → TradingSignalOutput | None`

Novo método após `_call_llm()`. Reutiliza a lógica de AgentBackstory (Story 207) para
enriquecer o system prompt antes de chamar `self._llm.chat_structured()`.
Retorna `None` em qualquer erro (falha silenciosa).

#### `_run()` — substituição do bloco de chamada LLM

```
1. Tenta _call_llm_structured(prompt) → structured output
2. Se obteve modelo Pydantic → _build_signal(payload.model_dump()) → retorna signal ✓
3. Se retornou None OU _build_signal falhou → cai no path clássico
4. Path clássico: _call_llm(prompt) → _extract_json() → _build_signal()
5. Qualquer falha no path clássico → _fallback_hold()
```

## Diagrama de Fluxo

```
_run()
  └─ _call_llm_structured(prompt)
       ├─ _llm.chat_structured(sys, user, TradingSignalOutput)
       │    ├─ OpenAI: beta.chat.completions.parse()  → parsed model ✓
       │    └─ Anthropic: _call_anthropic() + model_validate() → parsed model ✓
       │
       ├─ structured is not None ─→ _build_signal(payload.model_dump()) ─→ RETURN signal ✓
       │
       └─ structured is None / error
            └─ [FALLBACK] _call_llm(prompt) → _extract_json() → _build_signal() → RETURN signal
                                                                 └─ error → _fallback_hold() → RETURN HOLD
```

## Estratégia de Rollback Zero

- O path clássico (`_call_llm` + `_extract_json`) permanece **inalterado**.
- Qualquer falha no path estruturado é silenciosa (log `DEBUG`) e passa controle ao path clássico.
- Zero risco de regressão: se structured output não estiver disponível ou falhar, o sistema
  continua exatamente como antes.

## Testes

`tests/test_story_250_structured_output.py` — 6 classes de teste cobrindo:

| Classe | O que testa |
|---|---|
| `TestTradingSignalOutput` | Validação Pydantic, defaults, bounds (confidence, leverage, size_pct, entry_price), round-trip |
| `TestCallOpenAIStructured` | Mock do `beta.chat.completions.parse`, verificação de `response_format` arg |
| `TestCallAnthropicStructured` | Parse JSON, limpeza de code fences |
| `TestChatStructured` | Sem provider → None, path OpenAI, fallback OpenAI→Anthropic, falha total → None, path só-Anthropic |
| `TestVisionCallLlmStructured` | Retorna modelo, retorna None em erro, retorna None quando `chat_structured` retorna None |
| `TestVisionRunStructuredPath` | Path structured usado quando disponível, fallback ao raw JSON quando structured retorna None |

## Aceitação

- [x] `TradingSignalOutput` Pydantic valida todos os campos com bounds corretos
- [x] `chat_structured()` retorna instância validada via OpenAI Structured Output
- [x] `chat_structured()` faz fallback para Anthropic JSON mode quando OpenAI falha
- [x] `chat_structured()` retorna `None` em caso de falha total
- [x] `_call_anthropic_structured()` limpa code fences antes de fazer `json.loads()`
- [x] Vision usa structured output como path primário em `_run()`
- [x] Vision faz fallback silencioso para raw JSON quando structured retorna `None`
- [x] AgentBackstory (Story 207) aplicado em `_call_llm_structured()`
- [x] `chat_structured()` publica `llm.call.completed` com `"structured": True`
- [x] `pytest tests/test_story_250_structured_output.py` ✓

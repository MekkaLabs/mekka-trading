# Story 140 — DEGRADED_MODE Formal

**Milestone:** 22 — Resilience & Observability II  
**Status:** Done  
**Tipo:** Resiliência / Safety Net  

---

## Contexto

Quando dependências críticas (LLM / exchange) ficam instáveis, o sistema precisa de
um estado formal de degradação — não apenas um circuit breaker pontual, mas uma
**máquina de estados** que garante zero novas entradas enquanto o problema persiste
e recovery automático assim que a situação se normaliza.

Stories 137–139 documentaram os cenários de falha. A Story 140 implementa o mecanismo.

---

## Arquitetura

```
NORMAL ──── trigger(reason) ──────────► DEGRADED
              (LLM error rate ≥ 50%)    │
                                         │  observe_success() × N
              ◄── recovery_cycles ───────┘
              (padrão: 5 ciclos limpos)
```

### `DegradedModeManager` (`src/services/degraded_mode.py`)

| Método | Descrição |
|--------|-----------|
| `trigger(reason)` | Entra em DEGRADED. Retorna `True` se foi transição nova (NORMAL→DEGRADED). |
| `observe_success()` | Ciclo limpo. Retorna `True` se completou recovery (DEGRADED→NORMAL). |
| `observe_failure(reason)` | Reseta contador de recovery. |
| `is_degraded` | Property booleana. |
| `reason` | Motivo atual (string vazia se NORMAL). |
| `recovery_progress` | `"2/5"` ou `"N/A"`. |
| `trigger_count` | Total de ativações nesta sessão. |
| `summary()` | String de status legível para logs. |

Singleton via `get_degraded_mode_manager()` / `reset_degraded_mode_manager()`.

---

## Integração no NickFury

### 1. Inicialização (`__init__`)

```python
from src.services.degraded_mode import get_degraded_mode_manager
self._degraded_mode = get_degraded_mode_manager(
    recovery_cycles=settings.degraded_mode_recovery_cycles
)
```

### 2. Check no início de cada ciclo (`_cycle_for_symbol`)

```python
if self._degraded_mode.is_degraded:
    return CycleReport(symbol=symbol, error=f"DEGRADED_MODE: {self._degraded_mode.reason}")
```

### 3. try/except/finally no bloco Vision

O bloco Vision foi refatorado para usar `finally`, garantindo que o breaker e o
DEGRADED_MODE são atualizados MESMO quando Vision lança exceção:

```python
try:
    signal = await self._vision.run(analysis=analysis)
except Exception:
    _vision_error = True
    raise
finally:
    self._llm_error_breaker.observe(_vision_error)
    if _vision_error and self._llm_error_breaker.is_tripped:
        was_new = self._degraded_mode.trigger(...)
        if was_new:
            await _emit("system.degraded", {...})
    elif not _vision_error and self._degraded_mode.is_degraded:
        recovered = self._degraded_mode.observe_success()
        if recovered:
            await _emit("system.recovered", {...})
```

### 4. Reset com kill switch (`reset_breakers`)

Quando o operador usa `/resume`, o DEGRADED_MODE é também resetado — o sistema
volta ao estado NORMAL imediatamente, sem esperar os `recovery_cycles`.

---

## Eventos EventBus publicados

| Tópico | Quando |
|--------|--------|
| `system.degraded` | Primeira transição NORMAL → DEGRADED. |
| `system.recovered` | Transição DEGRADED → NORMAL (após `recovery_cycles` sucessos). |

---

## Configuração

| Setting | Padrão | Descrição |
|---------|--------|-----------|
| `degraded_mode_recovery_cycles` | `5` | Ciclos consecutivos limpos para recovery. |
| `llm_error_rate_threshold` | `0.5` | Taxa de erros LLM que aciona o trigger. |
| `llm_error_rate_window` | `10` | Janela deslizante para calcular taxa. |

---

## Comportamento em DEGRADED_MODE

- **Zero novas entradas** — `_cycle_for_symbol` retorna erro imediatamente.
- **Posições existentes** — Cyclops/Wolverine continuam no monitor cycle (não afetados).
- **Recovery automático** — após `recovery_cycles` Vision calls bem-sucedidos.
- **Recovery manual** — operador usa `/resume` via Telegram → `reset_breakers()` limpa tudo.

---

## Fix Story 138 (bônus)

A Story 138 tinha um bug silencioso: quando Vision lançava exceção, `_llm_error_breaker.observe(True)` 
nunca era chamado (o `raise` impedia a linha de observação). O `finally` block desta story corrige isso:
agora toda chamada Vision — sucesso OU falha — é observada pelo breaker.

---

## Testes

`tests/test_story_140_degraded_mode.py` — 28 testes cobrindo:
- Estado inicial (NORMAL)
- `trigger()`: transições, trigger_count, reset de recovery counter
- `observe_success()`: progresso, threshold, recovery completo
- `observe_failure()`: reset do contador, preservação de reason
- Properties: `recovery_progress`, `summary()`, `reason`
- Singleton: mesma instância, reset, `recovery_cycles` na primeira criação

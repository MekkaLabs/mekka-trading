# Story 249 — Decision Memory

## Objetivo

Persistir cada decisão da Vision com o resultado posterior e injetar um bloco de reflexão no início do próximo ciclo. Padrão inspirado no TradingAgents (TauricResearch): *decision log with outcome feedback*.

## Motivação

A Vision tomava decisões sem memória de performance recente. Um trader humano revisaria seus últimos 5 trades antes de entrar numa nova posição — a Vision precisa do mesmo contexto para calibrar confiança e evitar repetir erros.

## Implementação

### `src/services/decision_memory.py`

| Componente | Descrição |
|---|---|
| `DecisionRecord` | Snapshot da decisão: `cycle_id`, `symbol`, `signal_action`, `confidence`, `debate_confidence`, `regime`, `entry_price`, `timestamp` |
| `DecisionOutcome` | Resultado após trade fechar: `realized_pnl_pct`, `hit_target`, `duration_hours`, `exit_reason` |
| `DecisionMemoryStore` | Salva/recupera decisões; constrói bloco de reflexão |
| `get_decision_memory()` | Singleton global |

### Persistência

Reutiliza `AuditRecord` via `MekkaRepository.log_event()` com:
- `event="DECISION_MEMORY"` → snapshot da decisão
- `event="DECISION_OUTCOME"` → resultado do trade

Evita novo modelo de DB; cross-join em memória por `cycle_id`.

### `src/persistence/repository.py`

Adicionado método `list_audit_events(agent, event, symbol, limit)` para busca filtrada de AuditRecords.

### `src/agents/vision.py`

Injeção do bloco após Story 186 (SignalOutcomeMemory), antes de Story 180 (TradeAnnotationWatcher):

```python
# Story 249 — Decision Memory
_dm249 = get_decision_memory()
_decisions249 = await _dm249.get_recent_with_outcomes(_sym249, limit=5)
_refl_block249 = _dm249.build_reflection_block(_decisions249, _sym249)
prompt = prompt + "\n\n" + _refl_block249
```

Fallback automático via `list_recent_closed_trades()` quando não há decisões registradas ainda. Falha silenciosa em caso de erro.

## Formato do Bloco de Reflexão

```
## 🧠 Decision Memory — Histórico Recente (BTC)

Suas últimas decisões para este símbolo e seus resultados:

1. [2026-01-01] **LONG** | Regime: BULL | Confiança: 82% | Debate conf: 75%
   → ✅ PnL: +2.50% | Saída: TP | Duração: 4.5h | Target atingido: Sim

2. [2025-12-31] **SHORT** | Regime: BEAR | Confiança: 70%
   → ❌ PnL: -1.20% | Saída: SL | Duração: 2.0h | Target atingido: Não

**Resumo:** 3W/1L | Win rate: 75% | PnL total: +4.30%
💡 *Seu histórico recente neste símbolo é forte. Mantenha disciplina...*
```

## Insights Reflexivos Automáticos

| Condição | Mensagem |
|---|---|
| Win rate ≥ 70% | Encorajamento + manter disciplina |
| Win rate ≤ 30% | Aviso + aumentar limiar ou reduzir tamanho |
| PnL total < -5% | Aviso + ser mais seletivo |

## Testes

`tests/test_story_249_decision_memory.py` — 18 testes cobrindo:
- Bloco de reflexão (wins, losses, win rate, insights)
- Fallback via closed trades
- Falha silenciosa (save, record, get)
- Singleton

## Aceitação

- [x] `DecisionMemoryStore` salva decisão via `log_event(event="DECISION_MEMORY")`
- [x] `DecisionMemoryStore` registra outcome via `log_event(event="DECISION_OUTCOME")`
- [x] `build_reflection_block()` formata histórico legível para o LLM
- [x] Bloco injetado em `vision.py` após Story 186
- [x] Fallback síncrono via closed trades quando sem histórico
- [x] Falha silenciosa (Vision nunca quebra por erro de memória)
- [x] `pytest tests/test_story_249_decision_memory.py` ✓

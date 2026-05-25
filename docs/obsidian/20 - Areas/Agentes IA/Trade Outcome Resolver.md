---
title: Serviço — Trade Outcome Resolver
type: servico
tags: [servico, memory, learning, write-path, trade-outcome-resolver]
codename: Trade Outcome Resolver
real_name: Helper central
role: Sincroniza 3 memórias após close (fecha 4 gaps de writer órfão)
status: ativo
layer: L3 (Execution-adjacent helper)
introduced: 2026-05-25
created: 2026-05-25
updated: 2026-05-25
---

# Serviço — Trade Outcome Resolver

> **Não é um agente**: é um helper centralizado chamado por todos os
> caminhos de close. Mas é a peça que **finalmente** alimenta as
> memórias que Vision sempre leu mas que historicamente estavam vazias.

> **Arquivo**: `src/services/trade_outcome_resolver.py`
> **Função pública**: `resolve_trade_memories(symbol, pnl_usd, ...) -> dict`
> **Cabeado em 3 sites**:
> - `Cyclops` auto-close (`cyclops.py:701`)
> - `Dashboard` LIVE manual close (`server.py:2620`)
> - `Dashboard` PAPER manual close (`server.py:2700`)

## Missão

Fechar os **4 gaps de writer órfão** descobertos em 2026-05-25:

| Memória | Gap antes | Agora |
|---|---|---|
| `AgentMemoryStore` (Story 063) | Resolve só em auto-close | ✅ Resolve em todos os 3 paths |
| `RoleWorkingMemory` (Story 183) | `.record()` órfão | ✅ Helper chama na close |
| `SignalOutcomeMemory` (Story 186) | `.record()` órfão | ✅ Helper chama na close |
| `DecisionMemory` (Story 249) | `save_decision()` órfão | ✅ Chamada em NickFury no signal emit |

Detalhes do diagnóstico:
`~/.claude/projects/-Users-gustavovicente-Documents-Mekka-Trading/memory/project-memory-orphan-writers.md`

## Como funciona

```python
async def resolve_trade_memories(
    *,
    symbol: str,
    pnl_usd: float,
    holding_hours: Optional[float] = None,
    cycle_id: Optional[str] = None,
    action: Optional[str] = None,     # LONG/SHORT — recuperado se omitido
    regime: Optional[str] = None,     # BULL/BEAR/... — idem
    confidence: Optional[float] = None,
    trade_id: Optional[str] = None,
    signal_id: Optional[int] = None,
) -> dict:
    # Recovery: se action/regime/confidence ausentes, lê o último
    # SignalRecord actionable do symbol (raw.metadata)
    # Chama 3 stores em try/except independente:
    #   - AgentMemoryStore.resolve_outcome
    #   - RoleWorkingMemory.resolve_outcome
    #   - SignalOutcomeMemory.record
    return {"agent_memory": bool, "role_working": bool, "signal_outcome": bool}
```

## Princípios

1. **Idempotente**: chamar 2× não cria duplicatas.
2. **Isolated failures**: cada store dentro de try/except próprio. Falha
   em um nunca bloqueia os outros nem o close path.
3. **Best-effort recovery**: se action/regime/confidence faltam, busca
   no `signals` table do DB (último actionable do mesmo symbol).
4. **Paper-safe**: funciona em paper e live; só Hyperliquid não é
   tratado (bookkeeping diferente).

## Cross-references

- Produtor de outcomes para: [[Mentor]] (parameter suggestions)
- Consumidor jusante: [[Vision]] (prompt blocks)
- Fonte de signal data: `signals` table do SQLite
- Cabeado em: [[Cyclops]] auto-close + dashboard manual close (live + paper)
- Sister memory writer: NickFury (escreve no signal emit, lá em cima)

## Status atual

- ✅ Implementado em `src/services/trade_outcome_resolver.py` (commit `57bdc96`)
- ✅ 4 testes em `tests/test_trade_outcome_resolver.py` (4/4 PASS)
- ✅ Cabeado em 3 close paths
- ✅ Habilita [[Mentor]] (que só funciona quando há outcomes resolved)
- ⏳ **Aguardando**: 1ª resolução real para validar end-to-end no live testnet

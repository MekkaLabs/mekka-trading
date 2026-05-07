# Story 026 — Portfolio Manager (Layer 4)

## Context

A Story 025 fechou o pipeline estratégico end-to-end (Vision + Batman +
Iron Man + Nick Fury), mas dois pontos do diagnóstico do reviewer sênior
seguiam abertos:

1. **`_DEFAULT_EQUITY_USD = 10_000.0` hardcoded** em Nick Fury — Iron Man
   sizing assumia uma realidade fictícia.
2. **`open_positions=0` hardcoded** ao chamar Batman — o cap
   `max_open_positions` nunca disparava em paper mode porque a
   realidade era falsa por construção.

Story 026 corrige ambos com um único agente novo, sem mudar
comportamento de trading.

## Goal

Introduzir Portfolio Manager (Layer 4) — agente read-only que poll do
Hyperliquid `clearinghouseState` no início de cada cycle, retorna um
`EquitySnapshot` Pydantic, e alimenta Nick Fury com equity real e
contagem de posições abertas reais para Batman validar.

## Scope Delivered

### Modelos novos (`src/models/portfolio.py`)

- **`PositionSummary`** — uma posição aberta (symbol, side, size,
  entry_price, unrealized_pnl_usd, leverage opcional).
- **`EquitySnapshot`** — saída do Portfolio Manager. Campos:
  `timestamp`, `source` (HYPERLIQUID/PAPER_FALLBACK/OVERRIDE),
  `is_paper`, `equity_usd`, `available_balance_usd`,
  `margin_used_usd`, `open_positions_count`, `positions: list`,
  `error: str | None`. Property `is_degraded`. Method `summary()`.
- **`EquitySource`** enum.

### Agente novo (`src/agents/portfolio_manager.py`)

- **Read-only**: nunca envia ordens, só consome `/info` com
  `type=clearinghouseState`.
- **Lazy import** de `aiohttp` dentro do `_fetch_clearinghouse_state`
  (mesmo padrão de Iron Man / Vision).
- **Defensive degradation** em três camadas:
  1. Wallet placeholder `0x0000...` → `PAPER_FALLBACK` instantâneo,
     sem tocar a rede.
  2. Exception na rede (timeout, HTTP non-200) → `PAPER_FALLBACK` com
     `error` populado.
  3. Parse exception → `PAPER_FALLBACK` com `error` populado.
- Em qualquer fallback: `equity_usd = settings.paper_equity_usd`.
- Parser tolerante a campos faltantes (`marginSummary`, `withdrawable`,
  `assetPositions`); posições com `szi=0` são ignoradas.

### Settings (`src/config/settings.py`)

- Novo campo `paper_equity_usd: float = 10_000.0` com env var
  `PAPER_EQUITY_USD`. Validador `gt=0.0`.

### `.env.example`

- Bloco "Portfolio Manager" com `PAPER_EQUITY_USD=10000.0`.

### Wire-up em Nick Fury (`src/agents/nick_fury.py`)

- `__init__` instancia `self._portfolio = PortfolioManager()`.
- `run_main_cycle(equity_usd: Optional[float] = None)`:
  - Chama `self._portfolio.run()` uma vez por cycle.
  - Loga snapshot via `MekkaRepository.log_event(event="SNAPSHOT_<source>")`.
  - **Override hierarchy**: se `equity_usd` foi passado (CLI `--equity`
    ou teste), ele vence. Senão usa `snapshot.equity_usd`.
  - `open_positions = snapshot.open_positions_count` é forwarded para
    Batman em cada `_cycle_for_symbol`.
  - **Rolling counter**: quando uma execução paper/live abre uma
    posição nova, `open_positions += 1` para o próximo símbolo do
    mesmo cycle ver o total atualizado.
- `_cycle_for_symbol` ganha parâmetro `open_positions: int = 0`,
  removendo o `open_positions=0` hardcoded antes de chamar Batman.
- `run_forever(equity_usd: Optional[float] = None)` — semântica
  preservada (override CLI ainda funciona).

### Registry (`src/agents/__init__.py`)

- `PortfolioManager` adicionado ao `__all__` e ao `__getattr__`.

### Pytest fase 3 (`tests/test_phase3_portfolio.py`)

6 testes novos:

- `test_portfolio_paper_fallback_on_placeholder_wallet`
- `test_portfolio_paper_fallback_on_network_error`
- `test_portfolio_parses_clearinghouse_state`
- `test_nick_fury_uses_portfolio_manager_equity` — verifica que
  notional usa equity de Portfolio Manager (25k, não 10k legacy).
- `test_nick_fury_equity_override_wins` — verifica que CLI override
  bate Portfolio Manager.
- `test_nick_fury_open_positions_increment_during_cycle` — verifica que
  o contador rolling é repassado entre símbolos (`[0, 1]` para 2 ativos).

## Hard Rules Mantidas

- Nenhuma chamada de escrita à Hyperliquid. `clearinghouseState` é
  endpoint read-only.
- Comportamento default permanece **paper-trading**. Settings sem
  wallet real → fallback automático.
- Batman segue determinístico — só recebe `open_positions` como
  parâmetro de entrada, não consome o agente diretamente.
- Iron Man inalterado.
- Nenhuma mudança de schema em `signals` / `trades` / `audit_log`.
- Os 20 testes da fase 2 continuam passando: o
  `test_nick_fury_full_paper_cycle` passava `equity_usd=10_000.0`
  como override explícito, então o Portfolio Manager roda mas seu
  retorno é descartado em favor do override.

## Pipeline Atualizado

```
NickFury.run_main_cycle(equity_usd=None | float)
    ↓
    PortfolioManager.run()                          ← NOVO
        ↓ wallet placeholder?
        SIM → PAPER_FALLBACK snapshot
        NÃO → POST /info type=clearinghouseState
              parse marginSummary + assetPositions
              → HYPERLIQUID snapshot (or fallback on error)
    ↓
    log_event("SNAPSHOT_<source>")
    ↓
    effective_equity = equity_usd OR snapshot.equity_usd
    open_positions   = snapshot.open_positions_count
    ↓
    for symbol in trading_assets:
        ProfessorX → Vision → Batman(open_positions) → IronMan(effective_equity)
        if executed: open_positions += 1
```

## Acceptance

- [x] `PortfolioManager()` instancia sem dependência opcional.
- [x] Fallback path nunca raise, sempre retorna `EquitySnapshot`.
- [x] `EquitySnapshot.is_degraded` é True para `PAPER_FALLBACK`.
- [x] Nick Fury loga `SNAPSHOT_HYPERLIQUID` ou `SNAPSHOT_PAPER_FALLBACK`
      no audit_log.
- [x] CLI `--equity X` continua sobrescrevendo Portfolio Manager.
- [x] Pytest fase 2 (20 testes) e fase 3 (6 testes) compilam todos.
- [x] `python run.py --once` em paper-trading com wallet placeholder
      executa fallback path sem tocar rede.
- [x] Nenhuma mudança em `risk-engine/` (TS) ou em `kill_switch`.

## What's Next (Story 027 candidates)

1. **Wolverine (Recovery Agent)** — usa `EquitySnapshot.positions[]`
   para recalcular SL/TP dinâmicos por ATR atual; aciona kill switch
   se intraday drawdown explodir.
2. **Daily PnL writer** — escreve `daily_pnl` no SQLite usando
   `snapshot.equity_usd` no início e fim do dia para fechar o ciclo
   de drawdown que Batman já lê.
3. **Vision Critic** — second-look LLM (toggle off por default).
4. **Single-source audit** — harmonizar audit log TS↔Python.
5. **Telegram bot rico** — `/status` mostra `EquitySnapshot.summary()`.

## Files Changed

- `src/models/portfolio.py` (novo)
- `src/agents/portfolio_manager.py` (novo)
- `src/agents/nick_fury.py` (wire-up + assinatura `equity_usd: Optional`)
- `src/agents/__init__.py` (registry)
- `src/config/settings.py` (`paper_equity_usd`)
- `.env.example` (bloco Portfolio Manager)
- `tests/test_phase3_portfolio.py` (novo)
- `docs/stories/story-026-portfolio-manager.md` (este arquivo)
- `AGENTS.md` (Portfolio Manager sai de "pendente")
- `docs/ARCHITECTURE.md` (Layer 4 + I/O table)

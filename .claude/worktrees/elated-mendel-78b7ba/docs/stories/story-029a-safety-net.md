# Story 029a — Safety Net

> Mini-story de hardening posicionada **entre** a 028 (Contract Hardening)
> e a 029 (Wolverine — Recovery Agent). Objetivo: trancar três barreiras
> defensivas extras antes de qualquer agente ainda começar a tocar
> posições reais ou simular monitor cycle ativo.

## Context

Após Story 028 os contratos estão limpos, mas o pipeline ainda tinha três
janelas onde uma falha sustentada poderia escalar sem ninguém ver:

- **Total notional sem cap.** Batman valida cada trade individualmente
  (size_pct ≤ 2%, leverage ≤ 5x), mas três trades simultâneos podem
  somar 30% de notional sem nenhum gate ver o agregado.
- **Iron Man devolvendo `ExecutionStatus.ERROR` em loop.** Cada erro
  é logado, mas o ciclo seguinte tenta de novo. Sem desistência
  automática, um glitch da SDK Hyperliquid pode virar um pagedown
  silencioso de 2 dias.
- **Vision em fallback HOLD permanente.** Quando OpenAI cai ou retorna
  JSON inválido, Vision emite HOLD com `metadata.fallback=True`. Hoje
  isso fica vivo até alguém olhar a timeline. Em testnet tudo bem; em
  mainnet é uma cegueira garantida.

Story 029a fecha as três janelas com edits **aditivos**, sem mexer em
agentes existentes (Vision, Iron Man) e sem mover a Story 029
(Wolverine) na fila — ela continua sendo a próxima.

## Goal

Adicionar três salvaguardas mínimas, sem refactor:

1. **Cap de capital total** lido por Batman a cada novo trade.
2. **Circuit breakers de eventos consecutivos** (Iron Man ERROR,
   Vision fallback) que engatam o kill switch automaticamente.
3. **Helper de operador** `scripts/kill.sh` para engatar/soltar o
   kill switch persistente sem editar o arquivo na mão.

## Scope Delivered

### Service novo

- **`src/services/breakers.py`** — `ConsecutiveBreaker` dataclass.
  Contador passivo de hits consecutivos; `observe(hit)` retorna
  `True` exatamente uma vez quando o streak cruza o threshold,
  retorna `False` em hits subsequentes (não re-trip) e zera o streak
  em qualquer não-hit. Sem dependência de agente — só conta.

### Settings — 4 campos novos

Em `src/config/settings.py`:

- `max_total_capital_pct: float = 0.10` — fração de equity acima da
  qual Batman bloqueia novas entradas (cap agregado).
- `max_total_notional_usd: Optional[float] = None` — cap absoluto
  em USD. Quando setado, **toma precedência** sobre o pct cap
  (belt-and-suspenders das primeiras semanas em testnet).
- `max_consecutive_exec_errors: int = 3` — engata kill switch após
  N `ExecutionStatus.ERROR` em sequência.
- `max_consecutive_vision_fallbacks: int = 5` — engata kill switch
  após N fallback HOLDs em sequência.

Espelhados em `.env.example` com defaults conservadores.

### Batman — capital cap (aditivo)

`src/agents/batman.py:_run` ganha dois parâmetros novos com default
seguro (não quebra callers antigos):

- `running_notional_usd: float = 0.0`
- `equity_usd: float = 0.0`

Após os gates de drawdown / open_positions / trades_today e antes do
gate de confidence/RR, Batman calcula:

```
new_notional      = equity_usd * signal.size_pct * signal.leverage
projected_total   = running_notional_usd + new_notional
cap_usd           = max_total_notional_usd if set else equity_usd * max_total_capital_pct
```

Se `projected_total > cap`, **REJECTED** com `breached_limits`
contendo `max_total_notional_usd` ou `max_total_capital_pct`.
Quando `equity_usd <= 0` o cap é pulado (snapshot quebrado não pode
bloquear trade — outros gates seguem ativos).

### Nick Fury — wiring + auto-kill

`src/agents/nick_fury.py` ganhou:

- Dois `ConsecutiveBreaker` no `__init__` (instâncias por NickFury,
  não singletons globais — cada execução de teste começa limpa).
- `running_notional_usd` calculado a partir do snapshot da Portfolio
  Manager no início do ciclo, e incrementado a cada execução
  bem-sucedida dentro do mesmo ciclo (`+= execution.notional_usd`).
- Propagação de `equity_usd` e `running_notional_usd` para Batman.
- Método novo `_check_breakers(report)` chamado depois de cada
  `_cycle_for_symbol`. Ele alimenta os dois breakers e, se algum
  trip, chama `engage_kill_switch(reason)` + emite audit event
  `RISK_KILL_SWITCH` com `payload.breaker` identificando qual.

### Operator helper

- **`scripts/kill.sh`** — wrapper sobre `data/.kill_switch` em sync
  com `batman._KILL_SWITCH_FILE`. Subcomandos `on [reason]`, `off`,
  `status`. Emite cores + reason. Não toca env var
  `MEKKA_KILL_SWITCH` (essa é transiente ao processo).

### Pytest fase 5 — 13 tests novos

Em `tests/test_phase5_safety_net.py`:

- `ConsecutiveBreaker` — 5 tests (rejeita threshold inválido, dispara
  no crossing, não re-dispara sem reset, hit-False zera streak,
  reset manual mantém lifetime count).
- Batman cap — 4 tests (bloqueia quando excede pct cap, passa quando
  abaixo, cap absoluto tem precedência, equity zero pula o cap).
- Nick Fury wiring — 4 tests (3 exec errors → kill switch + audit,
  paper fill zera streak, 2 vision fallbacks (threshold reduzido
  para 2 no test) → kill switch, hold normal zera streak).

Todos os tests Nick Fury usam `release_kill_switch()` em `try/finally`
para garantir que o flag de arquivo não vaze entre testes.

## Hard Rules Mantidas

- **Iron Man, Vision, Professor X, Portfolio Manager, Daily PnL
  Writer não foram tocados.** Nenhuma assinatura mudou.
- **Batman.run() continua aceitando os mesmos kwargs.** Os dois
  novos têm default zero — código antigo segue compilando e o
  comportamento é idêntico ao da Story 028 quando o caller não
  passa equity/running_notional.
- **Kill switch continua sendo o único halt absoluto.** Os breakers
  não criam um "halt suave" novo — eles puxam o gatilho que já
  existe.
- **Não migramos eventos para `AgentEvent` enum aqui.** O event
  `RISK_KILL_SWITCH` que Nick Fury emite continua como string;
  a migração progressiva fica como prevista na Story 028.
- **Sem refactor de naming, sem reorganização de imports, sem
  toque em risk-engine TS.**

## Pipeline End-to-End

```
NickFury.run_main_cycle(equity_usd?)
  ↓ PortfolioManager.run() → EquitySnapshot
  ↓ running_notional_usd = sum(p.size * p.entry_price for p in snapshot.positions)
  ↓ for symbol in trading_assets:
        ProfessorX → Vision → Batman(running_notional_usd, equity_usd) → IronMan
        if execution succeeds:
            running_notional_usd += execution.notional_usd
        await _check_breakers(report)
            ├── exec_error_breaker.observe(execution.status == ERROR)
            └── vision_fallback_breaker.observe(signal.metadata.fallback == True)
                if either trips → engage_kill_switch + audit RISK_KILL_SWITCH
  ↓ DailyPnLWriter.record_cycle(...)
  ↓ list[CycleReport]
```

## Acceptance

- [x] `python3 -m py_compile` em `src/services/breakers.py`,
      `src/agents/nick_fury.py`, `src/agents/batman.py`,
      `src/config/settings.py`, `tests/test_phase5_safety_net.py`,
      `scripts/check_roster_consistency.py`.
- [x] `python3 scripts/check_roster_consistency.py` →
      `[OK] Roster consistent — 15 heroes`.
- [x] `pytest tests/test_phase5_safety_net.py -v` → 13/13 verdes.
- [x] Suite Python completa: 108 passed, 2 falhas pré-existentes
      em arquivos NÃO tocados pela 029a (drift de arredondamento em
      `test_phase4_daily_pnl.py::test_peak_is_monotonic_within_day`
      e drift de filtragem UTC em
      `test_dashboard_replay.py::test_utc_filter_excludes_out_of_range`).
      Documentadas como debt para uma story de housekeeping
      separada — não bloqueiam Wolverine.
- [x] `scripts/kill.sh on/off/status` smoke-tested com saída correta
      e cria/remove `data/.kill_switch` no caminho que `batman.py`
      lê.
- [x] Backward compat: chamar `Batman().run(signal=...)` sem os
      novos kwargs continua retornando o mesmo verdict que retornava
      antes (equity_usd default 0 ⇒ cap pulado).

## What's Next

A próxima entrega volta para a fila original:

- **Story 029 — Wolverine (Recovery Agent).** Monitor cycle real
  (não mais heartbeat); Wolverine consome posições abertas via
  Portfolio Manager, calcula PnL não-realizado, decide saídas
  defensivas (trailing stop, time-stop). `HeroName.WOLVERINE` já
  existe; o output do Wolverine (`RecoveryPlan`?) já nasce Pydantic
  com `schema_version=1`.

Bloqueio anterior à 029, ainda em aberto:
- **Smoke test manual da SDK Hyperliquid testnet** com credenciais
  reais de testnet, paper_trading=True, kill switch on by default.
  Confirmar que `IronMan._connect()` chega e fecha sem efeito
  colateral. Sem isso, Wolverine vai assumir uma SDK que ninguém
  rodou de verdade desde a Story 026.

## Files Changed

Novos:
- `src/services/breakers.py`
- `tests/test_phase5_safety_net.py`
- `scripts/kill.sh`
- `docs/stories/story-029a-safety-net.md` (este arquivo)

Editados (commit `69e584f` da sessão anterior — todos aditivos):
- `src/config/settings.py` (4 campos novos do Safety Net)
- `.env.example` (espelhamento dos 4 campos)
- `src/agents/batman.py` (parâmetros `running_notional_usd` e
  `equity_usd` + bloco de cap antes do gate de confidence)
- `src/agents/nick_fury.py` (instanciação dos 2 breakers,
  propagação do running_notional, método `_check_breakers`,
  chamada após cada `_cycle_for_symbol`)

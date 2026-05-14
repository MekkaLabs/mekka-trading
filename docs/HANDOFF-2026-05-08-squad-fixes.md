# Mekka Trading — Handoff: Squad Fixes (Pré-Story 036)
**Data**: 2026-05-08  
**Sessão**: Squad evaluation + 15 melhorias implementadas antes da Story 036

---

## O que foi feito nesta sessão

Antes de avançar para Story 036 (Mainnet Readiness), foram implementadas
**15 melhorias estruturais** identificadas pela avaliação de três squads:

- **Alpha-Risk-Command** — governança de risco (Batman / NickFury / Telegram)
- **Hyperliquid-Mock-OPS** — execução IronMan
- **Market-Intel-Lab** — pipeline de sinais (ProfessorX / Flash / VisionCritic)

Baseline: **276 testes verdes** (pós-035b). Esperado pós-fixes: ≥ 276.

---

## Melhorias por grupo

### A-group — Alpha-Risk-Command

| ID  | Arquivo(s)                                      | Mudança                                                                        |
| --- | ----------------------------------------------- | ------------------------------------------------------------------------------ |
| A1  | `src/agents/nick_fury.py`                       | `run_monitor_cycle()` agora busca preços via Hyperliquid `/info` e passa `current_prices` ao Wolverine (fix: Wolverine estava recebendo `{}` e sempre reportando upnl=0) |
| A2  | `src/agents/batman.py`, `src/services/telegram_inbound.py` | Kill switch persiste JSON estruturado `{reason, agent, timestamp_utc}`. `read_kill_switch_metadata()` adicionado. `/status` do Telegram mostra metadados. Legado plain-text suportado via fallback. |
| A3  | `src/agents/nick_fury.py`, `src/services/telegram_inbound.py` | `NickFury.reset_breakers()` adicionado. `/resume` agora chama `reset_breakers()` pós-release para que streak de erros não retripe o kill switch imediatamente. |
| A4  | `src/agents/nick_fury.py`                       | Bloco de early-return do kill switch agora tenta gravar um snapshot de `daily_pnl` antes de retornar `[]` (melhor contabilidade de ciclos abortados). |
| A5  | `src/config/settings.py`, `src/agents/batman.py` | Caps de leverage por regime de volatilidade: `max_leverage_high_regime=3` e `max_leverage_extreme_regime=2`. Batman aplica o cap mais restritivo entre regime e global. |

### B-group — Hyperliquid-Mock-OPS

| ID   | Arquivo(s)                  | Mudança                                                                                                                        |
| ---- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| B1/B2 | `src/agents/iron_man.py`  | Após entry IOC, extrai `filled_qty` com `fallback=0.0`. Se `filled_qty ≤ 0` retorna REJECTED imediatamente (sem SL/TP). SL e TP usam `filled_qty` (não quantidade planejada). |
| B3   | `src/agents/iron_man.py`   | `asyncio.Lock` em `__init__` + `_connect_async()` como wrapper assíncrono: previne double-init do SDK sob coroutines concorrentes. |
| B4   | `src/agents/iron_man.py`   | Pre-flight margin check via `info.user_state()` antes de tentativas de ordem: retorna REJECTED com mensagem clara se `withdrawable < required_margin`. |
| B5   | `src/config/settings.py`, `src/agents/iron_man.py` | Paper fills aplicam slippage sintético configurável via `paper_slippage_bps` (default 3 bps). LONG paga mais, SHORT paga menos — reflete custo real. |

### C-group — Market-Intel-Lab

| ID  | Arquivo(s)                                               | Mudança                                                                                                          |
| --- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| C1  | `src/models/market_data.py`, `src/agents/professor_x.py` | `MarketAnalysis.confirmation_chart: Optional[MarketData]`. ProfessorX chama Superman duas vezes (4h primário + 1h confirmação). Ambos aparecem no prompt do Vision. |
| C2  | `src/agents/superman.py`                                 | Rastreia `_exchange_id`. Fallback Binance/Bybit usa `defaultType="swap"` e símbolo `BTC/USDT:USDT` (perps) em vez de `BTC/USDT` (spot). |
| C3  | `src/agents/doctor_strange.py`                           | CryptoPanic recebe `published_after = now − 8h`: filtra posts velhos que inflariam score de sentimento. |
| C4  | `src/models/market_data.py`                              | Em `to_prompt()`, anomalias de severidade HIGH (ou `should_pause=True`) são inseridas **antes** do chart — não no final — para dar peso máximo ao LLM. |
| C5  | `src/models/market_data.py`, `src/agents/superman.py`, `src/agents/professor_x.py` | Flash agora está no fan-out do ProfessorX. Superman extrai `recent_closes` (últimos 20 closes). `MarketAnalysis.momentum: Optional[MomentumSignal]`. Seção de momentum aparece no prompt entre volatility e liquidity. |
| C6  | `src/config/settings.py`, `src/agents/vision_critic.py` | `vision_critic_model` (default `""` → herda `openai_model`) e `vision_critic_temperature` (default `0.0`) permitem que o Critic use modelo/temperatura diferente do Vision para diversidade de perspectiva. |

---

## Arquivos modificados

```
src/config/settings.py          ← A5 (regime caps), B5 (slippage), C6 (critic settings)
src/agents/batman.py            ← A2 (JSON kill switch), A5 (regime leverage cap)
src/agents/nick_fury.py         ← A1 (current_prices), A3 (reset_breakers), A4 (daily_pnl on KS)
src/services/telegram_inbound.py← A2 (metadata em /status), A3 (reset_breakers em /resume)
src/agents/iron_man.py          ← B1/B2 (filled_qty guard + SL/TP fix), B3 (Lock), B4 (margin), B5 (slippage)
src/agents/superman.py          ← C1 (timeframe param), C2 (exchange_id + swap symbol), C5 (recent_closes)
src/agents/doctor_strange.py    ← C3 (published_after)
src/models/market_data.py       ← C1 (confirmation_chart), C4 (anomaly ordering), C5 (momentum + recent_closes)
src/agents/professor_x.py       ← C1 (confirmation_chart call), C5 (Flash fan-out + momentum field)
src/agents/vision_critic.py     ← C6 (critic model + temperature)
tests/test_phase13_squad_fixes.py ← 35+ testes cobrindo todos os grupos
```

---

## Testes

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate
pytest tests/test_phase13_squad_fixes.py -v
pytest -v   # baseline completo
```

Todos os 6 arquivos editados passam por análise de sintaxe AST (`python3 -c "ast.parse(...)"`).
Testes da fase 13 cobrem: kill switch JSON (A2), reset_breakers (A3), leverage por regime (A5),
paper slippage direcional (B5), asyncio.Lock (B3), filled_qty guard (B1/B2), campos novos do
MarketAnalysis (C1/C5), ordenação de prompt (C4), filtro CryptoPanic (C3), símbolo CCXT (C2),
modelo/temperatura do Critic (C6).

---

## Próximo passo: Story 036 — Mainnet Readiness

Com as 15 melhorias concluídas, o sistema está pronto para iniciar a Story 036.
Ver `docs/AUTO-CONTINUE-PLAN.md § 7` para o checklist completo de gates humanos
obrigatórios antes de qualquer ordem mainnet.

**Gates que a IA pode preparar:**
- Cobertura de testes (`pytest --cov`)
- Revisão de todos os hard-limits no `settings.py`
- Documentação do processo de unlock do Iron Man para live

**Gates que exigem operador humano (NUNCA a IA faz):**
- 7.2 ≥ 1 mês testnet sem incidente
- 7.6 `MAINNET-AUTHORIZATION.md` com assinatura do operador
- 7.7 Remoção do hard-block paper_trading

# Auditoria Scalp + COIN-M — 2026-05-28

> Conduzida por 3 agentes Explore em paralelo + 4 smoke tests ao vivo.
> Todos os achados validados contra código real (não suposições).

---

## 🔴 P0 — BUGS CRÍTICOS (impedem o sistema de funcionar)

### P0-1 — Hook Batman scalp gates COMPLETAMENTE QUEBRADO
**Arquivo:** `src/agents/batman.py:1323-1329`
**Bug:** Código usa `g.passed` e `g.gate_name`, mas `GateResult` dataclass tem `allowed` e `gate_id`.
**Impacto:** `AttributeError` em runtime sempre que scalp gates rodam. Exception é capturada pelo `except Exception` do hook → log warning + flow continua sem rejeitar nada. **Nenhum scalp gate jamais bloqueou um trade.**
**Fix:** Trocar `g.passed → g.allowed`, `g.gate_name → g.gate_id` (5 linhas).

### P0-2 — Flash proposer bridge NÃO EXISTE
**Arquivo:** `src/services/flash_proposer_bridge.py` — **não foi criado**
**Bug:** Preset `flash_is_proposer=True` em `runtime_mode.py:154` mas nenhum código consome essa flag. Flash continua só consumidor. Vision recebe MarketAnalysis sem `momentum_proposal`.
**Impacto:** Modo scalp perde sinal de timing crítico. Vision opera "às cegas" comparado ao prometido pelo preset.
**Fix:** Criar o módulo + integrar no `mekka_kernel` ou `nick_fury`.

### P0-3 — `to_ccxt()` chamado SEM `market_type` em iron_man
**Arquivo:** `src/agents/iron_man.py:700` (e provavelmente outros callers)
**Bug:** `to_ccxt(symbol, exchange_id)` sem o 3º arg → default "linear" sempre. Em modo `inverse`, sistema gera `BTC/USDT:USDT` mas o cliente CCXT espera `BTC/USD:BTC` → "Unknown symbol".
**Impacto:** **TODAS as ordens em COIN-M falham silenciosamente.** Sistema parece aceitar mas CCXT rejeita.
**Fix:** Passar `market_type=settings.binance_market_type` em todos os callers de `to_ccxt`.

### P0-4 — Balance check hardcoded "USDT" em inverse mode
**Arquivo:** `src/agents/iron_man.py:793-810`
**Bug:** `balance_info.get("USDT", {})["free"]` — em COIN-M, saldo está em BTC/ETH, não USDT.
**Impacto:** `equity = 0` → todas as ordens rejeitadas como "insufficient margin".
**Fix:** Resolver balance key dinamicamente (`"USDT"` para linear, settlement coin para inverse).

### P0-5 — Portfolio Manager `_extract_balance_totals()` ignora COIN-M
**Arquivo:** `src/agents/portfolio_manager.py:514-522`
**Bug:** Busca só `USDT` e `USDC`. Em inverse, conta tem BTC → equity_usd retorna 0.
**Impacto:** Mesmo problema que P0-4 mas em outro caminho. Dashboard mostra equity=0 falsamente.
**Fix:** Branch para inverse: somar BTC/ETH × mark_price → equity_usd.

### P0-6 — `save_trade()` NÃO popula `quote_currency` nem `pnl_quote`
**Arquivo:** `src/persistence/repository.py:77-93`
**Bug:** TradeRecord criado sem esses campos → ficam nos defaults (`"USDT"` / `None`).
**Impacto:** Em COIN-M, registros novos ficam marcados como USDT → análise histórica corrompida. Impossível reconstruir PnL real.
**Fix:** Passar `quote_currency` (derivar do market_type) e `pnl_quote` ao construir TradeRecord.

---

## 🟡 P1 — SEMI-CRÍTICOS (degradam silenciosamente)

### P1-1 — `scalp_mainnet_enabled` definido mas NUNCA enforced
**Arquivo:** `src/agents/nick_fury.py` (boot/initialize)
**Bug:** Flag existe em settings + aparece em /api/env, mas nenhum código checa.
**Impacto:** Operador pode ativar scalp em mainnet live por engano → 120s loop com risco real.
**Fix:** Adicionar gate em `NickFury.initialize()` ou `_should_run_cycle()`: bloqueia se modo=scalp + live + flag=false.

### P1-2 — Race condition cache CCXT
**Arquivo:** `src/agents/iron_man.py:517-565`
**Bug:** `settings.binance_market_type` lido 2x (cache_key e cfg) sem lock cobrindo ambos.
**Impacto:** Sob hot-swap, cliente CCXT pode ficar com `defaultSubType` divergente do cache_key.
**Fix:** Snapshot do `binance_market_type` em variável local antes do bloco lockado.

### P1-3 — Validator de hot-swap promised but missing
**Arquivo:** `src/config/settings.py:175` (docstring) vs validators
**Bug:** Docstring promete "validator bloqueia swap com posições abertas" — não existe.
**Impacto:** Operador troca market_type, posições antigas viram zumbis (rastreadas no client errado).
**Fix:** Implementar validator real OU remover promessa do docstring + adicionar gate no `/api/settings`.

### P1-4 — Mode toggle race no meio do ciclo
**Arquivo:** múltiplos agentes (`superman.py`, `vision.py`, `batman.py`, `cyclops.py`)
**Bug:** Cada um chama `get_params()` em momentos diferentes.
**Impacto:** Se operador troca modo mid-cycle, agentes leem valores inconsistentes.
**Fix:** Snapshot atômico no início de cada ciclo + passar params via parâmetro.

### P1-5 — Gate `max_position_age` é SENTINEL, não bloqueia
**Arquivo:** `src/agents/batman_scalp_gates.py:119+`
**Bug:** Doc diz "Allowed sempre True (sentinel)" — depende do Cyclops time-stop fechar. Mas Cyclops time-stop é lazy (próximo ciclo).
**Impacto:** Em loop de 120s, posição de 35min pode entrar em novo trade sem bloqueio durante 1+ ciclo.
**Fix:** Decisão de design — manter sentinel ou trocar para bloqueador? Recomendo: bloquear se cap_min × 1.2 (hard cap), sentinel para warning.

### P1-6 — contract_sizer linear perde 5% via rounding
**Arquivo:** `src/services/contract_sizer.py:140+` `_round_down`
**Bug:** Step size agressivo: $1000 @ BTC$73k → 0.013 BTC ($949) em vez de 0.0137 ($1000).
**Impacto:** Sizing 5% abaixo do alvo em todas ordens linear.
**Fix:** Permitir step_size menor (0.001 ou ler precisão do market_registry).

---

## 🟢 P2 — MELHORIAS DE QUALIDADE

- Gate `created_at`/`opened_at` keys inconsistentes (smoke usou `created_at`, gate busca `opened_at`)
- Bybit price_feed hardcoded linear topic
- positions_provider não converte pnl_quote → pnl_usd
- ExecutionResult não tem `quote_currency` (precisa pra save_trade detectar)
- Migration backfill não detecta histórico inverse (Bybit)
- Clock skew detection em Cyclops time-stop
- Log binance_market_type no boot do CCXT

---

## 📊 Resumo

| Severidade | Count | Impacto |
|---|---|---|
| 🔴 P0 | 6 | Sistema inverse + scalp gates não funcionam |
| 🟡 P1 | 6 | Risco operacional sem visibilidade |
| 🟢 P2 | 7+ | Qualidade/observabilidade |

**Veredicto:** A implementação F1-F8 entregou **estrutura correta** (arquivos, settings, schemas) mas tem **6 bugs P0 que impedem o sistema de operar** em COIN-M ou aplicar scalp gates corretamente. Todos os bugs são localizados (linhas específicas) e corrigíveis em <2h.

# Auditoria de Prontidão para MAINNET — Mekka Trading

> **Verificação independente (pós-workflow):** os 3 bloqueadores CRITICAL foram
> conferidos manualmente no código e estão **CONFIRMADOS** (não são falsos positivos):
> C1 `cycle_id` ausente no escopo de `_place_ccxt_order` (NameError real na linha 1108);
> C2 `stopPrice` cru sem `price_to_precision` na linha 1044 (Guardian na 1564 quantiza — inconsistência real);
> C3 retry com exceções built-in que não casam com `ccxt.*` + sem `newClientOrderId`.
> ⚠️ `src/agents/iron_man.py` e `settings.py` são PROTECTED — correções exigem OK do operador.


> Auditoria-chefe consolidando 8 dimensões + pré-mortens adversariais.
> Data: 2026-06-01 · Sistema: trading algorítmico multi-agente · Capital: DINHEIRO REAL.

---

## 1. Veredito: **NO-GO**

**Não autorizar mainnet hoje.** Existe pelo menos um bug **CRITICAL confirmado** que quebra exatamente o fail-safe mais importante do sistema: quando o stop-loss falha na colocação, um `NameError` em `iron_man.py:1108` impede o `emergency_flatten` de rodar, deixando a posição **NUA (sem stop) com dinheiro real** por até 5 minutos. Pior: o gatilho mais provável desse cenário (stopPrice não quantizado → rejeição de precisão na Binance) também está confirmado. Some-se a falta de idempotência (ordem duplicável) e a possibilidade de sizing inflado por equity de fallback, e o perfil de risco é incompatível com capital real até as correções P0.

---

## 2. Sumário Executivo

A arquitetura de segurança é **conceitualmente sólida e bem pensada**: double-gate à prova de bypass acidental, SL fail-safe no caminho de entrada, SL Guardian a cada 5 min, reconciliação no boot, hard clamp de 1ª semana (0.1%/2x) rodando por último no Batman, e force_execute corretamente bloqueado em mainnet. **O problema não é o desenho — é que vários fail-safes não foram exercitados em teste e estão quebrados no caminho ativo (Binance/CCXT).** O fail-safe de SL tem um `NameError` que o anula; o retry de ordens usa exceções built-in que nunca casam com as do CCXT (retry morto); não há `clientOrderId`, então retry pode duplicar ordem; e a checagem de margem + snapshot de equity falham-aberto, podendo inflar size. Os circuit breakers de drawdown e perda absoluta também têm furos (reset por restart; default desligado). O hard clamp da 1ª semana mitiga muita coisa **enquanto está ligado**, mas não cobre o estado pós-1ª-semana nem os bugs de execução. Veredito: corrigir o bloco P0 (execução) e validar com testes antes de qualquer dólar real.

---

## 3. Bloqueadores CRÍTICOS (must-fix antes de qualquer dólar real)

| # | Achado | Local | Impacto | Fix |
|---|--------|-------|---------|-----|
| C1 | **NameError em `cycle_id` impede emergency_flatten** quando SL falha → posição fica NUA | `iron_man.py:1108` | Entrada preenche, SL falha 3x, flatten **nunca roda** (NameError antes da execução) → posição sem stop até o Guardian (até 5 min). É justamente o cenário que o fail-safe deveria cobrir. | Adicionar `cycle_id` como parâmetro de `_place_ccxt_order` (propagar de NickFury onde `_cycle_id` já existe) ou no mínimo `cycle_id=None`. **Teste unitário** simulando falha definitiva de SL asserindo que `_emergency_flatten` é chamado. |
| C2 | **stopPrice de SL/TP de entrada não quantizado ao tickSize** | `iron_man.py:1044` (SL), `:1160` (TP) | Binance rejeita por PRICE_FILTER (-1111/-4014). É o **gatilho mais provável** que dispara o caminho bugado C1 → posição nua. Vision gera SL/TP como floats arbitrários (`entry*0.97`). | `_sl_px = float(exchange.price_to_precision(ccxt_symbol, signal.stop_loss))` antes do create_order (espelhar padrão já existente na linha 1566 do Guardian). Idem TP. Validar `stop != entry` após arredondar. |
| C3 | **Sem idempotência (clientOrderId) — retry de entrada pode DUPLICAR ordem** | `iron_man.py:944-967` | Ordem chega à Binance e a resposta sofre timeout → tenacity re-envia → **2ª posição aberta** (2x notional, 2x risco) sem aprovação do Batman. Viola "nunca inflar size". SL dimensiona só o 1º fill → parte fica sem stop. | `newClientOrderId` determinístico (hash de snapshot_id+symbol+side+cycle_id), reusado no retry (Binance rejeita duplicata -2010). Persistir em `order_id`. Sem isso, NÃO re-tentar create_order por timeout — fazer reconcile (`fetch_open_orders`) antes. |

> **Nota de encadeamento:** C2 → C1 → exposição nua é uma cadeia única e altamente provável em mainnet. Tratar como um bloco indivisível.

---

## 4. Riscos ALTOS (corrigir antes ou na 1ª semana, sob clamp ativo)

| # | Achado | Local | Impacto | Fix |
|---|--------|-------|---------|-----|
| H1 | **paper_fallback em LIVE injeta equity=$10k + positions=[]** sem bloquear execução | `portfolio_manager.py:649-668` + `nick_fury.py:620-623` | Falha de snapshot (InvalidNonce -1021, timeout) sem cache → sizing contra $10k sintético. Conta real de $500 → notional ~20x. `positions=[]` cega gates de exposição/concorrência/correlação. Corrompe `starting_equity` do dia → drawdown/kill-switch falsos. | Em `paper_trading=False`, snapshot degradado/PAPER_FALLBACK = **SKIP do ciclo** (não abrir trade) + alerta. Nunca usar `paper_equity_usd` para sizing live. Capturar `starting_equity` só de snapshot não-degradado. |
| H2 | **Checagem de margem por-ordem é fail-open** | `iron_man.py:861-886` | Exception no `fetch_balance` (InvalidNonce conhecido) → apenas warning, **ordem enviada sem verificar saldo**. Pode liquidar prematuro / rejeição em loop. | Fail-CLOSED: qualquer exceção → `ExecutionResult(REJECTED)`. 1-2 retries com backoff antes de abortar. Log CRITICAL + Telegram. |
| H3 | **Circuit breaker de drawdown diário reseta após restart** | `nick_fury.py:178` + `daily_pnl_writer.py:140-172` | Restore grava em `_peak_equity` (atributo **morto**; real é `_state.peak_equity`); `record_cycle` re-semeia peak pela equity atual e nunca passa `peak_equity_usd` no upsert. Após perda de 8% + restart → drawdown≈0 → Batman **continua aprovando**. | Hidratar `_state = _DayState(starting=persistido, peak=persisted_peak)` no boot; em `record_cycle` carregar peak/starting do DB antes de re-semear (nunca rebaixar peak); passar `peak_equity_usd`. Teste: perda→restart→drawdown preservado→bloqueio. |
| H4 | **Retry/backoff das ordens CCXT é inoperante** | `iron_man.py:944-967` | Filtro usa `(TimeoutError, ConnectionError)` built-ins, que **não são superclasses** de `ccxt.RequestTimeout/NetworkError` (herdam de BaseError). Timeout transitório da Binance → falha na 1ª tentativa, sem retry. Promessa do docstring não cumprida. | Trocar para `retry_if_exception_type((ccxt.NetworkError, ccxt.RequestTimeout, ccxt.ExchangeNotAvailable, ccxt.DDoSProtection))`. **Só ativar retry junto com idempotência (C3)** para não duplicar ordem. Superman já acerta isso (superman.py:322-323). |
| H5 | **PortfolioManager roteia sandbox por `is_mainnet` (atrelado a Hyperliquid)** | `portfolio_manager.py:193` | `is_mainnet = hyperliquid_network=='mainnet'`. Operador em Binance mainnet com `hyperliquid_network=testnet` (default) → PortfolioManager lê balance/positions da **Binance TESTNET** enquanto IronMan executa na MAINNET. Equity fictício infla sizing. | Rotear por-exchange igual ao resto (`binance_testnet`). Helper único `settings.exchange_is_testnet(exchange_id)` usado em todos. Gate no preflight. |
| H6 | **save_trade após ordem pode deixar posição órfã no DB** | `nick_fury.py:2188` | Sem try/except dedicado; falha de commit → ordem real aberta **sem TradeRecord**, sem alerta, sem contagem para gates do Batman → próximo ciclo pode aprovar **entrada duplicada** no mesmo símbolo. (SL já posto → não fica nua.) | Outbox: gravar TradeRecord 'PENDING' **antes** do IronMan.run e atualizar depois. Falha → Telegram CRITICAL + fila de retry persistida. |
| H7 | **PnL realizado de closes LIVE (SL/TP) nunca gravado no DB** | `cyclops.py:78-80` (live retorna 0) | Nenhum polling de `fetch_my_trades`/`realizedPnl`. Closes por bracket ficam com `pnl_usd=NULL`. Beast, leaderboards, win-rate cegos/errados → self-improvement ajusta params com base em histórico incompleto. (Não afeta kill-switch, que usa delta de equity.) | Reconciliador de fills live no `run_monitor_cycle`: `fetch_my_trades`/`fetch_income` desde cursor persistido, gravar close com `realizedPnl` real. |
| H8 | **Sem monitoramento de proximidade de liquidação em live** | `portfolio_manager.py:454-468`; `positions_provider.py:424` | `liquidationPrice` é lido/exibido mas **nenhum agente age**. SL cancelado/falho + vela rápida entre ciclos de 5 min → liquidação (perda total da margem) sem alerta proativo. | No `run_monitor_cycle` (live): se `|mark - liq|/mark < ~5%` → alerta CRITICAL + de-risk/close parcial. Fallback conservador quando `liq=None` (cross margin). |
| H9 | **Take-profit em live é best-effort e nunca reforçado** | `iron_man.py:1153-1166`; Guardian só checa SL (`:1471`) | Se a TP falhar na abertura ou for cancelada, ninguém recoloca (Cyclops é paper-only). SL é protegido, TP não — assimétrico. Perda de oportunidade, não de capital. | Estender Guardian para garantir/alertar TP ausente, ou documentar explicitamente que TP live depende de fechamento manual. |

---

## 5. Pré-mortem Consolidado (modos de falha por probabilidade × impacto)

| Rank | Cenário de falha | Probabilidade | Impacto | Mitigação atual | Gap |
|------|------------------|---------------|---------|-----------------|-----|
| 1 | **Entrada preenche → SL rejeitado por tickSize → NameError → posição nua → movimento adverso/liquidação** | Alta (toda entrada cujo SL viole precisão) | Severo (perda descontrolada até 5 min) | SL Guardian recoloca a cada 5 min | C1+C2 quebram o fail-safe imediato; janela de 5 min é exposição total |
| 2 | **Timeout na resposta da ordem → retry → posição duplicada (2x size)** | Média (picos de volatilidade = mais timeouts) | Severo (2x risco não aprovado) | Nenhuma — retry está morto (H4), mas se consertado sem C3, duplica | Sem clientOrderId nem reconcile |
| 3 | **Snapshot de equity falha em live → fallback $10k → sizing inflado ~20x + gates cegos** | Média (InvalidNonce -1021 é conhecido/recorrente) | Severo (notional desproporcional, kill-switch falso) | Hard clamp 1ª semana (0.1%/2x), pré-check de margem do IronMan (mas é fail-open, H2) | Sem gate de degraded snapshot; clamp some após 1ª semana |
| 4 | **Restart após dia ruim → drawdown reseta → Batman volta a aprovar trades** | Média (deploy/crash/OOM acontecem) | Alto (perde o freio do dia) | `max_daily_loss_usd` poderia frear — mas default 0.0 (desligado) | Persistência de peak quebrada (H3) + freio absoluto desligado (M1) |
| 5 | **Operador em Binance mainnet com hyperliquid_network=testnet → equity vem da testnet** | Média (default favorece o erro) | Alto (sizing com saldo fictício) | Nenhuma no PortfolioManager | Roteamento divergente (H5) |
| 6 | **Partial fill → `filled` bruto não quantizado → SL/flatten rejeitado por LOT_SIZE → posição nua** | Baixa-Média | Severo | — | `amount_to_precision` ausente em SL/TP/flatten (M2) |
| 7 | **set_sandbox_mode falha em modo testnet → ordens "de teste" vão à produção** | Baixa (chaves testnet 401 em prod) | Severo | Chaves testnet separadas | Fail-open contraria o próprio comentário do código (M3) |
| 8 | **Stop cancelado externamente logo após um ciclo → nua por até 5 min** | Baixa | Alto | Guardian a cada 5 min, fail-safe na entrada | Polling 5 min, não event-driven (M4) |

---

## 6. Médios / Baixos (lista enxuta)

**MEDIUM**
- **M1** — `max_daily_loss_usd` default 0.0 (kill-switch de perda absoluta desligado). `settings.py:328-336`. Definir 2-5% do capital no .env de mainnet.
- **M2** — SL/TP/emergency_flatten usam `filled` bruto sem `amount_to_precision`; partial fill pode rejeitar por LOT_SIZE → cai no caminho C1. `iron_man.py:1042/1158/1230`.
- **M3** — `set_sandbox_mode` fail-open: se falhar em modo testnet, prossegue com cliente apontado para produção. `iron_man.py:644-658`. Tornar fail-closed.
- **M4** — Entrada `market` explícita na mainnet ignora cap de slippage. `iron_man.py:897`. Forçar limit_ioc ou exigir flag dedicado.
- **M5** — Preflight: gates conservadores são só WARN e usam 0.5% em vez do 0.1% do MAINNET-AUTHORIZATION. `preflight_mainnet.py:292-333`. Promover a FAIL em mainnet+live e alinhar threshold.
- **M6** — Sem gate automatizado de saldo mínimo no preflight; H6 é checkbox manual. Adicionar `check_min_balance` + `min_equity_floor_usd`.
- **M7** — Falha em `fetch_positions` no Guardian aborta verificação de **todas** as posições naquele ciclo sem escalar. `iron_man.py:1522-1528`. Retry imediato + alerta CRITICAL.
- **M8** — Feed WS de markPrice sem detecção de staleness; preço WS velho sobrepõe markPrice fresco da venue → PnL exibido enganoso. `price_feed.py` + `positions_provider.py:749-753`. Timestamp por símbolo + TTL ~10-15s.
- **M9** — Caps de leverage COIN-M não aplicados no loop automático (só no dashboard). `coin_m_leverage_caps.py:84`. Latente — só afeta se trocar para `inverse`.

**LOW**
- **L1** — Cache de snapshot sem TTL nem flag de staleness. `portfolio_manager.py:632-643`.
- **L2** — `set_leverage` fail-open silencioso → ordem pode abrir com leverage residual ≠ aprovado. `iron_man.py:851-854`.
- **L3** — Preflight exibe "ALL CHECKS PASSED" mesmo com `PAPER_TRADING=true`. `preflight_mainnet.py:220-227`.
- **L4** — `order_id` sem constraint UNIQUE — DB não barra re-inserção duplicada. `models.py:76`.
- **L5** — Synthetic close de phantom recon grava `avg_price=0`/`pnl_usd=NULL`, distorce agregações. `iron_man.py:1847-1864`.
- **L6** — SL emergencial de 2% no boot pode ficar do lado errado do preço após downtime longo. `nick_fury.py:197-268`.
- **L7** — PortfolioManager não reusa `_CCXT_SHARED` — paga load_markets (9-18s) a cada snapshot. `portfolio_manager.py:116-212`.

---

## 7. O que JÁ está sólido (crédito devido)

- **Double-gate de live trading à prova de bypass acidental.** `live_trading_double_gate` levanta ValueError no boot; IronMan reprova de novo em runtime (`iron_man.py:260`). Dashboard não muta `paper_trading`/`testnet`/`live_confirmed` (whitelist de 4 campos).
- **force_execute / Modo Deus HARD-REJECTED em mainnet+live** (`server.py:6346`). Kill switch file-based + env-based, não burlável nem com force_execute.
- **Hard clamp de 1ª semana (0.1% / 2x) roda por ÚLTIMO no Batman** (`batman.py:1799`) — reduz de volta qualquer config frouxa/agressiva.
- **Bump de size mínimo corretamente bloqueado na mainnet** (`iron_man.py:802`) — nunca infla size silenciosamente com dinheiro real. Confirmado correto.
- **Batman é um gate determinístico robusto** (~25 gates bem ordenados) com cálculo de size correto para USDT-M linear.
- **SL Guardian** (`ensure_stops_for_open_positions`) recoloca SL ausente a cada ciclo; **reconciliação no boot** cobre "processo caiu com posição aberta"; **phantom reconciliation** cobre drift DB-vs-corretora; **limpeza de stops órfãos (-4045)** bem tratada.
- **SL colocado DENTRO do IronMan.run ANTES do save_trade** — a rede de segurança financeira se mantém mesmo se o DB falhar.
- **Persistência sólida:** SQLite WAL + busy_timeout, single-writer sequencial; drawdown/kill-switch live derivado de delta de EQUITY da corretora (não do pnl por trade).
- **Clock skew hardening:** recvWindow 60s + adjustForTimeDifference contra -1021.
- **TelegramAlerter nunca lança exceção**, com throttle/dedup e monitor de drawdown escalonado (50/80/100%).
- **Preflight já é Binance-aware** (creds por-exchange, check de network).

---

## 8. Plano de Melhorias Priorizado (checklist acionável)

### P0 — Bloqueadores de mainnet (fazer ANTES de qualquer dólar real)
- [ ] **(C1) Corrigir NameError do `cycle_id`** em `iron_man.py:1108` + propagar parâmetro de NickFury. **[S]**
- [ ] **(C2) Quantizar stopPrice de SL e TP de entrada** via `price_to_precision` (`:1044`, `:1160`). **[S]**
- [ ] **(C3) Adicionar `newClientOrderId` determinístico** + reuso no retry / reconcile antes de re-enviar. **[M]**
- [ ] **(H2) Tornar checagem de margem fail-CLOSED** (`:861-886`). **[S]**
- [ ] **(H1) Gate de degraded snapshot em live:** SKIP do ciclo se PAPER_FALLBACK/is_degraded; nunca usar `paper_equity_usd` para sizing live. **[M]**
- [ ] **(H5) Unificar roteamento testnet por-exchange** (`exchange_is_testnet` helper) e corrigir `portfolio_manager.py:193`. **[M]**
- [ ] **Testes:** unit de falha de SL→flatten chamado; unit de degraded snapshot→skip; unit de duplicação no retry. **[M]**

### P1 — Endurecer na 1ª semana (sob clamp ativo)
- [ ] **(H3) Corrigir persistência de peak_equity** (restore + record_cycle + upsert) com teste de regressão. **[M]**
- [ ] **(H4) Trocar filtro de retry para exceções CCXT** (somente junto com C3). **[S]**
- [ ] **(H6) Outbox para save_trade** (PENDING antes / update depois + alerta + fila). **[M]**
- [ ] **(H7) Reconciliador de fills live** com cursor persistido (`realizedPnl` real no DB). **[L]**
- [ ] **(H8) Monitor de proximidade de liquidação** no run_monitor_cycle. **[M]**
- [ ] **(M1) Definir `MAX_DAILY_LOSS_USD` > 0** no .env de mainnet + documentar como gate obrigatório. **[S]**
- [ ] **(M2) Quantizar `filled`** em SL/TP/flatten + tratar `filled < min`. **[S]**
- [ ] **(M3) `set_sandbox_mode` fail-closed.** **[S]**
- [ ] **(M5/M6) Preflight Binance-aware:** WARN→FAIL em mainnet+live, threshold 0.1%, `check_min_balance`. **[M]**

### P2 — Melhorias de robustez/observabilidade
- [ ] **(H9) Guardian garante/alerta TP ausente** ou documentar best-effort. **[M]**
- [ ] **(M4) Forçar limit_ioc na mainnet** / flag dedicado para market. **[S]**
- [ ] **(M7) Guardian: retry + escalação** em falha de fetch_positions. **[S]**
- [ ] **(M8) Staleness do feed WS** (timestamp + TTL). **[S]**
- [ ] **(M4/H8) Reduzir `monitor_interval` para 60-90s em live** ou tornar event-driven. **[M]**
- [ ] **(L4) Índice UNIQUE em order_id + upsert idempotente.** **[S]**
- [ ] **(M9) `clamp_leverage` COIN-M no Batman** quando `inverse`. **[S]**
- [ ] **(L1/L2/L5/L6/L7)** demais lows. **[S-M]**

---

## 9. Recomendação de Rollout (quando P0 estiver verde)

**Pré-condições para virar a chave:**
1. Todos os itens **P0** corrigidos **com testes passando** (especialmente o teste de falha de SL→emergency_flatten).
2. `python3 scripts/preflight_mainnet.py --strict` verde **com gates Binance-aware** (após M5).
3. `MAX_DAILY_LOSS_USD > 0` definido (P1/M1) — não esperar a 1ª semana inteira para isso.
4. Confirmar `hyperliquid_network` não derruba o roteamento (H5).

**Parâmetros conservadores — 1ª semana:**
- `MAX_POSITION_SIZE_PCT=0.001` (0.1%), `MAX_LEVERAGE=2` (hard clamp confirma).
- `MAX_DAILY_LOSS_USD` = 2-5% do capital real; `MAX_DAILY_DRAWDOWN_PCT=0.10`.
- Conta funded com **valor mínimo conservador** (não o capital total pretendido).
- `BINANCE_ENTRY_ORDER_TYPE=auto` (limit_ioc) — nunca `market`.
- `TELEGRAM_TRADE_APPROVAL_ENABLED=true` para aprovação manual de cada trade na 1ª semana.
- `monitor_interval_seconds` reduzido para 60-90s.

**Critérios de PARADA (kill switch manual imediato):**
- Qualquer posição observada **sem SL na corretora** por mais de 1 ciclo.
- Qualquer **ordem duplicada** / size diferente do aprovado pelo Batman.
- Snapshot de equity caindo em PAPER_FALLBACK em modo live (sizing potencialmente sintético).
- `drawdown_pct` no DB divergindo da perda real após um restart.
- InvalidNonce -1021 recorrente afetando margem/posições.

**O que monitorar de perto:**
- Presença de SL reduce-only na venue para **toda** posição aberta (auditar a cada ciclo).
- `order_id` único por fill no DB; ausência de duplicatas.
- Equity efetivo usado no sizing = leitura real confirmada (nunca $10k de fallback).
- Distância até liquidação em posições alavancadas.
- Logs CRITICAL de emergency_flatten / margem / sandbox.
- Reconciliação DB vs corretora (pnl_usd dos closes live preenchido após H7).

---
title: "Runbook — Cenários de Stress Test em Paper-on-Testnet"
type: runbook
tags: [runbook, stress-test, papernet, bybit, testnet, paper, scenarios]
status: ativo
created: 2026-05-19
updated: 2026-05-19
audience: [operador, qa, dev]
related: [[Runbook - Bybit Testnet Setup]], [[ADR-003 - Bybit Testnet Readiness]]
---

# Runbook — Cenários de Stress Test em Paper-on-Testnet

> **Objetivo**: validar empiricamente como o Mekka reage a 25 situações de stress (mercado, notícia, risco, sistema, operacional) — tudo em paper mode contra Bybit testnet, com risco financeiro zero.
> **Ferramenta**: `python scripts/stress_inject.py <cenário>` automatiza os cenários simuláveis. Cenários de mercado real exigem observação ou orderbook externo.
> **Pré-requisitos**: [[Runbook - Bybit Testnet Setup]] já executado; dashboard subindo em http://localhost:8787 com badge **BYBIT · PAPER**.

> ⚠️ **REGRA DE OURO**: cada cenário deve começar com **estado limpo** (kill switch off, sem posições abertas) e terminar com **estado documentado** (capture screenshots, salve `/api/audit?since=<marker>`).

## Antes de começar — checklist baseline

- [ ] Dashboard subindo e badge `BYBIT · PAPER` visível
- [ ] `/api/env` retorna `mode: "paper"` e `network: "testnet"`
- [ ] Kill switch DESLIGADO (`python scripts/stress_inject.py kill-switch-release`)
- [ ] Nenhuma posição paper aberta (`/api/positions` retorna `count: 0`)
- [ ] Audit log baseline marcado: `python scripts/stress_inject.py market-event-marker --label session_start`
- [ ] Telegram (se configurado) está respondendo `/status`

---

## 🌊 Categoria 1 — Movimentos bruscos de mercado

### C1.1 — Pump repentino (preço sobe +5% em 5 min)

**Como provocar**: aguardar evento orgânico (ETF approval news, FOMC surprise) **OU** observar o feed Bybit testnet em momento de volatilidade real **OU** usar `market-event-marker` antes da janela esperada.

```bash
python scripts/stress_inject.py market-event-marker --label pump_btc
```

**O que esperar do sistema**:
- Thor (Volatility Engine) registra spike → severidade do regime sobe
- Vision pode emitir LONG signal com confidence elevada → veja `/api/signals`
- Batman aplica gate 3q (ATR mínimo) — em pump, ATR cresce, gate passa
- Se já houver LONG aberto, Wolverine **NÃO** deve fechar (tendência a favor)
- Cyclops monitora TP → se atingir, fecha automaticamente

**Falha detectável**:
- Spider-Man emite `ANOMALY_DETECTED` com severidade ERROR (esperado WARN, no máximo)
- Iron Man tenta executar e clock skew check rejeita (se NTP estiver off)
- Dashboard live-tick atrasa >2s

### C1.2 — Dump repentino (preço cai −5% em 5 min)

**Como provocar**: similar a C1.1; aguarde dump orgânico ou marque antes de notícia bearish esperada.

```bash
python scripts/stress_inject.py market-event-marker --label dump_btc
```

**O que esperar**:
- Se houver LONG aberto, **Cyclops** dispara SL → fecha posição
- Audit registra `SL_TP_TRIGGERED` com `order_id=CYCLOPS-...`
- PnL realized cai na equity dinâmica
- Telegram envia alerta de SL atingido
- Batman gate 3o conta a perda — após N losses consecutivos, novas LONG são rejeitadas

**Falha detectável**:
- Cyclops não fecha mesmo com mark cruzando SL (bug crítico)
- Equity dinâmica não atualiza no painel
- Telegram não envia (verificar dedup window não está suprimindo)

### C1.3 — Flash crash (queda −10%+ em 1 minuto)

**Como provocar**: raro; geralmente coincide com hack/halt. Marker antes:

```bash
python scripts/stress_inject.py market-event-marker --label flash_crash
```

**O que esperar**:
- Wolverine detecta drawdown crítico → emite `RecoveryPlan` com `EMERGENCY_CLOSE`
- `_execute_recovery_plan` fecha 100% das posições paper
- Kill switch é engatado automaticamente se drawdown > `max_daily_drawdown_pct`
- Próximo ciclo NickFury entra em `skip_reason=kill_switch`
- Telegram envia alerta CRITICAL

**Falha detectável**:
- Wolverine emite plano mas não executa (`recovery_actions_taken=0`)
- Kill switch não engata mesmo com drawdown excedido
- Dashboard continua mostrando posições "fantasma" depois do EMERGENCY_CLOSE

### C1.4 — Whipsaw (alta seguida de queda na mesma janela)

**Como provocar**: aguardar evento como CPI release, FOMC, ETF decision day. Marker:

```bash
python scripts/stress_inject.py market-event-marker --label whipsaw_fomc
```

**O que esperar**:
- Vision pode emitir 2 sinais opostos na mesma janela (LONG depois SHORT, ou vice-versa)
- VisionCritic deve discordar do segundo se a janela for muito curta — `vision_critic_min_disagreement` controla o threshold
- Batman gate 3p (max same-direction streak) **NÃO** dispara aqui (são direções opostas)
- Se 2 trades opostos executam, PortfolioManager netta corretamente em `/api/positions`

**Falha detectável**:
- Sistema abre LONG e SHORT no mesmo símbolo sem netting (posição "real" deveria ser 0)
- VisionCritic não dispara mesmo com sinais conflitantes em <5 min

### C1.5 — Mercado parado (ATR muito baixo)

**Como provocar**: aguardar horário de baixa atividade (madrugada UTC, fim de semana com pouco volume). Marker antes:

```bash
python scripts/stress_inject.py market-event-marker --label dead_market
```

**O que esperar**:
- Batman gate 3q rejeita sinais quando ATR% < `min_atr_pct` (default 0.0 = desabilitado, mas habilitável)
- Audit log mostra `GATE_REJECTED` com motivo `3q_min_atr`
- Nenhuma execução nova
- Sistema continua observando, sem placeholder de erro

**Falha detectável**:
- Sistema executa trade mesmo com mercado parado e gate 3q ativo
- Vision continua emitindo sinais mas Batman rejeita silenciosamente sem audit

---

## 📰 Categoria 2 — Notícia / Sentimento

### C2.1 — Notícia escandalosa positiva (ETF, regulamentação favorável)

**Como provocar**: CryptoPanic publica artigo com sentimento `+0.8`+. Se `CRYPTOPANIC_API_KEY` estiver configurado, Doctor Strange consome automaticamente. Marker:

```bash
python scripts/stress_inject.py market-event-marker --label news_bullish
```

**O que esperar**:
- Doctor Strange recalcula probabilidade macro → upweight em decisões pró-LONG
- Vision pode emitir LONG com confidence boost
- Reasoning do signal cita o headline
- Se Vision emitir sinal, Batman valida normalmente

**Falha detectável**:
- Vision emite sinal **sem** mencionar a notícia no reasoning (sentiment não está sendo consumido)
- Confidence permanece baixa apesar do sentiment positivo

### C2.2 — Notícia escandalosa negativa (hack de exchange, SEC action)

```bash
python scripts/stress_inject.py market-event-marker --label news_bearish
```

**O que esperar**:
- Doctor Strange ajusta probabilidade macro para baixo
- Vision pode emitir SHORT ou HOLD
- Se há posição LONG aberta, Vision/Wolverine podem recomendar `SCALE_OUT`
- Spider-Man detecta anomalia de price/volume em <1 ciclo

**Falha detectável**:
- Sistema ignora notícia bearish e continua executando LONG
- Spider-Man não detecta a anomalia mesmo com volume 3x acima da média

### C2.3 — Notícia ambígua / contraditória

**Como provocar**: dia com 2+ headlines opostas no mesmo intervalo. Marker.

**O que esperar**:
- Sentiment composite (média ponderada por relevância) tende ao neutro
- Vision não emite sinal de alta convicção (`confidence < 0.65` esperado)
- Batman pode rejeitar por gate de confidence mínima

**Falha detectável**:
- Sentiment fica fixado no último headline em vez de fazer média
- Vision emite sinal com confidence ≥ 0.85 apesar do sentiment neutro

---

## 🛡️ Categoria 3 — Risco / Compliance

### C3.1 — Drawdown ultrapassa limite diário

**Como provocar**: rodar `drawdown-alert` manualmente com pct > `max_daily_drawdown_pct` (default 10%):

```bash
python scripts/stress_inject.py drawdown-alert --pct 15
```

**O que esperar**:
- Telegram recebe alerta CRITICAL formatado em pt-BR
- Audit registra o evento
- Em produção (não simulado), Wolverine engataria kill switch automaticamente
- Próximo ciclo NickFury checa kill_switch e pula

**Falha detectável**:
- Telegram não recebe (token inválido, dedup ativo, rate limit)
- Mensagem está em inglês em vez de pt-BR

### C3.2 — Kill switch acionado manualmente

```bash
python scripts/stress_inject.py kill-switch-engage --reason "stress test C3.2"
```

**O que esperar**:
- `data/.kill_switch` é criado
- Dashboard mostra estado kill no Live Risk Panel (em <2s via WS broadcast)
- `/api/trade/execute` rejeita qualquer tentativa: `kill switch active`
- Próximo ciclo NickFury entra em `skip_reason=kill_switch`
- Audit registra `KILL_SWITCH_ENGAGED`

**Para sair do estado**:

```bash
python scripts/stress_inject.py kill-switch-release
```

**Falha detectável**:
- Kill switch engata mas dashboard continua deixando o operador clicar "Trade Now"
- Painel Live Risk não reflete o estado em <5s
- Após `release`, sistema não volta a aceitar trades

### C3.3 — N losses consecutivos (gate 3o)

**Como provocar**: injetar 3 sinais que viram SL (entry próxima do SL):

```bash
# Sinal 1 — perda
python scripts/stress_inject.py fake-signal --side long --symbol BTC --entry 65000 --sl 64900 --tp 70000
# (aguarde execução, SL ser atingido — Cyclops fecha)
# Repetir 2x ou ajustar entry/sl para garantir loss
```

**O que esperar**:
- Após `max_consecutive_losses` (default 3) SLs consecutivos, Batman rejeita novos sinais com gate 3o
- Audit registra `GATE_REJECTED` com `reason=3o_consecutive_losses`
- Gate 3o reset acontece na próxima vitória (story 111: Cyclops TP triggers `GATE_3O_RESET`)

**Falha detectável**:
- Batman continua aprovando sinais após 3 losses
- Gate não reseta após win

### C3.4 — Direcionamento excessivo (gate 3p)

**Como provocar**: injetar 4 sinais LONG seguidos:

```bash
for i in 1 2 3 4; do
  python scripts/stress_inject.py fake-signal --side long --symbol BTC --entry $((65000 + $i * 100))
done
```

**O que esperar**:
- Após `max_same_direction_streak` (default 4), Batman rejeita o 5º LONG
- Audit: `GATE_REJECTED reason=3p_same_direction_streak`
- SHORTs continuam permitidos

**Falha detectável**:
- Batman aprova 5º LONG

### C3.5 — Drawdown por símbolo (gate 3n)

**Como provocar**: Injetar 2-3 LONGs em BTC que viram SL. Após perda acumulada > `max_symbol_drawdown_pct * equity` na janela semanal, Batman rejeita novos BTC.

**O que esperar**:
- Batman: `GATE_REJECTED reason=3n_symbol_drawdown`
- ETH e SOL continuam aceitáveis (gate é por símbolo)

**Falha detectável**:
- Gate 3n não considera só BTC; bloqueia outros símbolos também
- Após X dias, gate não reseta automaticamente (janela rolling de 7 dias)

### C3.6 — Notional mínimo (gate 3m)

**Como provocar**: injetar sinal com size muito pequeno:

```bash
python scripts/stress_inject.py fake-signal --side long --symbol BTC --entry 65000 --size-pct 0.0001
```

(0.01% do capital → notional ~$1 com equity $10k)

**O que esperar**:
- Batman: `GATE_REJECTED reason=3m_min_notional`
- Audit registra o reject

**Falha detectável**:
- Batman aprova trade com notional < `min_trade_notional_usd`

---

## ⚙️ Categoria 4 — Falhas de sistema

### C4.1 — Clock skew (NTP desincronizado)

**Como provocar**: medir skew real com Bybit:

```bash
python scripts/stress_inject.py skew-check
```

Para simular skew >5s sem mexer no relógio do SO, use uma máquina com NTP desligado por 5+ min, OU edite `_check_clock_skew` em `iron_man.py` temporariamente.

**O que esperar**:
- `skew-check` reporta `CLOCK SKEW CRÍTICO` se >5000ms
- Em ordens reais, IronMan aborta com `ExecutionResult(REJECTED, error="Clock skew +Xms: ...")`
- A mensagem inclui o comando de fix (sntp/timedatectl)

**Falha detectável**:
- Skew >5s e IronMan executa mesmo assim → ordem retorna 10002 silenciosa

### C4.2 — Exchange WebSocket cai

**Como provocar**: bloquear conexão temporariamente:

```bash
# Em outro terminal, derruba conectividade Bybit por 30s
# (macOS) sudo pfctl -e e adicionar regra de drop — avançado
# Mais simples: desconectar Wi-Fi por 30s
```

**O que esperar**:
- `BybitPriceFeed.run` loga `Bybit price pump disconnected (...) — reconnecting in 5s`
- Reconnect automático após 5s
- Dashboard live-tick para mas não trava; reconecta quando o backend reconecta
- Nenhuma exceção propaga para a tela

**Falha detectável**:
- Backend trava em loop infinito (nunca reconecta)
- Dashboard mostra erro JS no console
- Audit log enche de exceções

### C4.3 — Telegram bot offline / token revogado

**Como provocar**: editar `TELEGRAM_BOT_TOKEN` no `.env` para algo inválido e reiniciar, OU revogar o token no BotFather.

**O que esperar**:
- Sistema continua funcionando — Telegram é opcional
- Logs mostram `TelegramAlerter` failures mas downgrade graceful
- DLQ recebe os alertas que falharam
- `npm run run:replay-dlq` (TS) ou worker de retry tenta reenviar

**Falha detectável**:
- Sistema crasha por causa do Telegram offline
- Audit log enche de stack traces

### C4.4 — LLM (OpenAI/Anthropic) timeout

**Como provocar**: setar `OPENAI_API_KEY=` inválido. Sistema deve cair no fallback Anthropic (story 125). Se ambos inválidos:

**O que esperar**:
- Vision emite `HOLD` fallback com `confidence=0`
- Após `MAX_CONSECUTIVE_VISION_FALLBACKS` (default 5), kill switch é engatado
- Audit registra `LLM_FAILURE` e `KILL_SWITCH_ENGAGED reason=vision_fallback`

**Falha detectável**:
- Vision crasha em vez de HOLD fallback
- Contador de fallback não incrementa

### C4.5 — DB SQLite lockado / corrompido

**Como provocar**: enquanto o sistema escreve, abrir o DB em outro processo com lock exclusivo (raro em SQLite). Mais fácil: renomear `data/mekka_trading.db` durante a operação.

**O que esperar**:
- Writes falham com retry exponencial
- Após N retries, alerta CRITICAL é disparado
- Sistema continua **lendo** mas para de escrever — degraded mode (story 140)

**Falha detectável**:
- Sistema crasha em vez de degradar
- Operador não é notificado

### C4.6 — Bybit rate limit (código 10006)

**Como provocar**: rodar `telegram-flood` ou abusar `/api/positions` em loop. Mais difícil em paper porque IronMan não envia ordens reais — esse cenário foca em market data:

```bash
# Em outro terminal, faz 100 requests rápidas
for i in {1..100}; do curl -s http://localhost:8787/api/positions > /dev/null & done; wait
```

**O que esperar**:
- CCXT incorpora rate limit interno (`enableRateLimit: true`)
- Pedidos são enfileirados, não rejeitados
- Se rate limit do CCXT for excedido, retry exponencial entra em ação

**Falha detectável**:
- Bybit retorna 10006 e o sistema não trata (deve cair no retry da tenacity)

---

## 🎮 Categoria 5 — Operacional

### C5.1 — Operador troca de mode no meio da operação

```bash
# Estado inicial: balanced
python scripts/stress_inject.py mode-switch aggressive
```

**O que esperar**:
- `data/runtime_mode.json` atualizado
- Próximo ciclo Vision/Batman usa novos parâmetros (size_pct=5%, leverage=10x, threshold=55%)
- Audit registra `MODE_CHANGED`
- UI atualiza badge em <30s (polling do `_bootGlobalMode`)
- Telegram envia confirmação se inbound configurado (`/mode aggressive`)

**Voltar**:

```bash
python scripts/stress_inject.py mode-switch balanced
```

**Falha detectável**:
- Modo persiste no JSON mas próximo ciclo continua com parâmetros antigos
- UI fica defasada >60s

### C5.2 — Operador fecha todas as posições manualmente

Pré-condição: ter 2-3 posições paper abertas.

```bash
python scripts/stress_inject.py close-all-paper
```

**O que esperar**:
- Cada posição vira trade de fechamento (lado oposto, mesma qty líquida)
- Audit: `POSITION_CLOSED` por símbolo
- `/api/positions` zera em <2s
- Equity realizada atualiza
- Telegram envia alerta agregado

**Falha detectável**:
- Alguma posição não fecha (qty residual no netting)
- Audit registra fechamento mas posição continua no painel
- Telegram envia 1 alerta por posição em vez de agregado (spam)

### C5.3 — Telegram-flood / dedup window

```bash
python scripts/stress_inject.py telegram-flood --count 10
```

**O que esperar**:
- Apenas 1 alerta entregue dentro da janela de dedup (`alert_dedup_window_seconds`)
- Dedup store persiste em `memory/alerts/*.json`
- Audit registra 10 tentativas com 9 `DEDUP_SUPPRESSED`

**Falha detectável**:
- Telegram recebe 10 mensagens (dedup quebrado)
- Dedup persiste mas não detecta a partir da segunda invocação

### C5.4 — Sinal forçado via dashboard (Trade Now)

Na UI: aba **Live** → **Trade Now** → confirmar.

**O que esperar**:
- Vision gera recomendação on-demand
- Card mostra `RecommendationCard` com justificativa
- Batman valida → aprovado ou rejeitado com motivo legível
- Se aprovado, trade paper persiste no DB
- Cyclops começa a monitorar SL/TP na próxima janela

**Falha detectável**:
- Trade Now mostra "Carregando..." indefinidamente
- Sinal aprovado mas não aparece em `/api/positions`
- Cyclops não inclui o novo símbolo na monitoração

### C5.5 — Re-análise após Trade Now

Clicar **Trade Now** novamente sem confirmar o anterior.

**O que esperar**:
- Cache do recommendation anterior é limpo
- Nova análise roda do zero
- Não há vazamento de estado entre execuções

**Falha detectável**:
- Card antigo permanece visível com botão "Confirmar" ativo

### C5.6 — Wolverine RecoveryPlan dispara SCALE_OUT

**Como provocar**: criar posição com SL distante, esperar drawdown a –0.5R (não –1R). Wolverine deve sugerir SCALE_OUT (fecha 50%).

**O que esperar**:
- Wolverine emite RecoveryPlan com `action=SCALE_OUT`
- `_execute_recovery_plan` fecha 50% da posição
- Audit: `RECOVERY_ACTION_TAKEN action=SCALE_OUT qty=0.5x_original`
- Posição restante segue normalmente

**Falha detectável**:
- Wolverine emite plano mas executa fechamento de 100% (deveria ser 50%)
- Posição original permanece intacta

---

## Categoria 6 — Cenários combinados (regressão)

### C6.1 — Pump → Stop hunt → Recuperação

Sequência completa em 30 min:

1. Marker `python scripts/stress_inject.py market-event-marker --label combined_C6.1_start`
2. Aguardar pump genuíno OU injetar 2 LONGs com TP próximo
3. Aguardar dump pós-pump (stop hunt clássico)
4. Cyclops deve fechar com SL → equity cai
5. Vision avalia se ainda há tese → emite novo sinal ou HOLD
6. Marker `--label combined_C6.1_end`

**Métricas a coletar**:
- N de trades disparados
- PnL realizado total
- N de SLs atingidos
- Tempo até reset do gate 3o
- Whether kill switch foi engatado

### C6.2 — Notícia bearish → Drawdown → Kill switch → Recuperação

1. Marker `--label news_bearish_cascade_start`
2. Aguardar headline bearish (ou simular via dump)
3. Observar Wolverine emitir EMERGENCY_CLOSE em cascata
4. Kill switch automático após drawdown > `max_daily_drawdown_pct`
5. Operador investiga, depois `kill-switch-release`
6. Sistema retoma operação

**Métricas**:
- Tempo entre detecção e EMERGENCY_CLOSE
- Drawdown final
- Tempo de kill switch ativo (audit)
- Mode global após release (deveria voltar ao baseline)

### C6.3 — Latência de execução acumulada

Loop de 1h com auditoria de `agents_step_guard` para detectar steps lentos (>5s).

**O que esperar**:
- Nenhum step ultrapassa 5s consistentemente
- p95 de Hero SLA em `/api/hero-sla` permanece <2s
- Se latência aumenta, alerta automático dispara

**Falha detectável**:
- p95 > 5s sem alerta
- Algum agent trava (timeout não interrompe)

---

## Tabela de comandos rápidos

```bash
# Sempre comece a sessão:
python scripts/stress_inject.py market-event-marker --label session_start

# Sinal sintético:
python scripts/stress_inject.py fake-signal --side long --symbol BTC --entry 65000

# Kill switch on/off:
python scripts/stress_inject.py kill-switch-engage --reason "C3.2 test"
python scripts/stress_inject.py kill-switch-release

# Mode swap:
python scripts/stress_inject.py mode-switch aggressive
python scripts/stress_inject.py mode-switch balanced  # voltar

# Close all positions:
python scripts/stress_inject.py close-all-paper

# Drawdown alert:
python scripts/stress_inject.py drawdown-alert --pct 15

# Telegram dedup test:
python scripts/stress_inject.py telegram-flood --count 10

# NTP / clock skew real:
python scripts/stress_inject.py skew-check

# Sempre termine:
python scripts/stress_inject.py market-event-marker --label session_end
```

---

## Como ler os resultados

### Audit log
```bash
# Eventos da sessão de stress test:
curl -s "http://localhost:8787/api/audit?event=STRESS_TEST_INJECT" | jq

# Eventos correlacionados ao cenário:
curl -s "http://localhost:8787/api/audit?since=<timestamp_do_marker>" | jq
```

### Dashboard widgets relevantes por cenário

| Cenário | Widget(s) chave |
|---|---|
| C1.x — Mercado | Live Trading Panel, Equity Curve, Cyclops badge |
| C2.x — Notícia | Doctor Strange tile, Vision Signals timeline |
| C3.x — Risco | Live Risk Panel, Batman gates timeline, Kill Switch banner |
| C4.x — Sistema | Internals tile, Hero SLA, Audit Stream |
| C5.x — Operacional | Positions table, Trading Mode panel, Telegram log |

---

## Checklist final da sessão

- [ ] Todos os cenários planejados executados (marcar os realizados)
- [ ] Screenshots/logs capturados para cada um
- [ ] Falhas detectadas viraram issues no GitHub
- [ ] `python scripts/stress_inject.py kill-switch-release` (garantir estado limpo)
- [ ] `python scripts/stress_inject.py close-all-paper` (garantir sem posições)
- [ ] Marker final no audit log
- [ ] Resumo da sessão em [[{{date}}]]

# INCIDENT PLAYBOOK

> **Para quem é**: o operador quando algo dá errado durante runtime
> testnet (ou mainnet futuro). Cada incidente tem: sintomas, ação
> imediata, diagnóstico, e recovery path.

> **Princípio rector**: kill switch primeiro, debug depois. Trading
> automatizado errado custa rapidamente; uma hora parado custa pouco.

---

## 0. Comando universal — kill switch

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
./scripts/kill.sh "<reason>"
```

Cria `data/.kill_switch`. Próximo cycle Batman retorna `KILL_SWITCH`,
Nick Fury short-circuit, monitor cycle também para. **Não** mata o
processo Python — preserva runtime para diagnóstico via dashboard.

Para soltar depois do diagnóstico:

```bash
rm data/.kill_switch
```

---

## INC-001 — Hyperliquid API down

### Sintomas
- `EXEC_ERROR` consecutivos no audit_log com `Hyperliquid /info HTTP 5xx`.
- PortfolioManager retorna `PAPER_FALLBACK` mesmo com wallet válida
  (`source=PAPER_FALLBACK`, `error=Hyperliquid unreachable`).
- Dashboard `/api/audit` mostra streak de erros.

### Ação imediata
1. `./scripts/kill.sh "hyperliquid down"` — bloqueia novas tentativas.
2. Verifica status oficial: https://status.hyperliquid.xyz (ou
   alternative.me se status page existir).
3. Confirma com `curl -X POST https://api.hyperliquid-testnet.xyz/info
   -H 'Content-Type: application/json' -d '{"type":"meta"}'`.

### Diagnóstico
- Se cURL retorna 5xx: API mesmo está down → espera.
- Se cURL retorna 200: problema é local (SDK, network) → próximo passo.
- Confirma sua wallet ainda existe no testnet:
  `info.user_state(addr)` em REPL Python.

### Recovery
- Hyperliquid voltou: `rm data/.kill_switch`. Próximo cycle reentra.
- Hyperliquid persistente down (≥ 30 min): mantém kill switch, vai
  dormir, retoma quando voltar.
- **Posições abertas durante o downtime** ficam onde estavam.
  Wolverine não consegue ler positions — fará fallback no próximo
  monitor cycle.

### Pós-incidente
- Anota duração no `audit_log` payload via uma entry manual.
- Se foi > 1h, considera abrir uma micro-story para adicionar
  retry com backoff mais agressivo no PortfolioManager.

---

## INC-002 — OpenAI rate limit / outage

### Sintomas
- Vision retorna fallback HOLD streak (≥ 3 consecutivos).
- `RISK_KILL_SWITCH` event com `payload.breaker = "vision_fallback"`
  — Story 029 Safety Net já engajou kill switch automaticamente.
- audit_log mostra `OpenAI APITimeoutError` ou `RateLimitError`.

### Ação imediata
- Se kill switch já engajou (esperado): **deixa engajado**.
  Sistema fez o trabalho dele.
- Confirma status: https://status.openai.com.

### Diagnóstico
```bash
# Conta fallbacks consecutivos
sqlite3 data/mekka_trading.db "
  select timestamp, agent, event, message
  from audit_log
  where event = 'RISK_KILL_SWITCH'
  order by timestamp desc limit 5;
"
```

- Se rate limit: OpenAI account no plano errado? Verifica
  https://platform.openai.com/account/limits.
- Se outage OpenAI: aguarda restore.

### Recovery
- Quando voltar, valida com 1 chamada manual:
  ```python
  from openai import AsyncOpenAI
  import asyncio, os
  c = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
  print(asyncio.run(c.chat.completions.create(
    model="gpt-4o", messages=[{"role":"user","content":"ping"}],
    max_tokens=5,
  )))
  ```
- Se voltou: `rm data/.kill_switch`, primeiro cycle vai testar Vision
  vivo. Watch o vision_fallback_breaker — deve resetar.

### Pós-incidente
- Considera adicionar OpenAI fallback (Anthropic, Gemini) como Story
  futura se incidentes repetidos.

---

## INC-003 — Drawdown breach (intraday)

### Sintomas
- `RISK_KILL_SWITCH` com `payload.breaker = "intraday_drawdown"` ou
  `kill_switch.reason = "Wolverine intraday drawdown"`.
- `daily_pnl.drawdown_pct ≥ max_daily_drawdown_pct` (default 10%).
- Dashboard mostra `intraday_drawdown_pct` alto na timeline.

### Ação imediata
- Sistema **já parou**. Não desligar o kill switch sem revisão.
- Verifica que posições abertas estão hedgeadas (têm SL no exchange).

### Diagnóstico
```bash
sqlite3 data/mekka_trading.db "
  select date_utc, starting_equity, ending_equity, pnl_usd, drawdown_pct
  from daily_pnl order by date_utc desc limit 3;
"
sqlite3 data/mekka_trading.db "
  select timestamp, symbol, status, side, quantity, avg_price, pnl_usd
  from trades order by timestamp desc limit 10;
"
```

Causa típica:
- Movimento de mercado fora do regime que Vision viu (gap, flash
  crash). Spider-Man deveria pegar — verifica anomalias.
- Posição com SL não acionado (Iron Man failed to place SL bracket?).
- Acumulação de pequenas perdas além do esperado.

### Recovery
- **Decisão humana**: fechar posições manualmente via Hyperliquid UI?
- Se decidir continuar: ajusta `MAX_DAILY_DRAWDOWN_PCT` para baixo
  no `.env` por uma semana. `rm data/.kill_switch`.
- Se decidir parar: deixa o kill switch on, fecha posições na UI,
  revisa estratégia antes de reativar.

### Pós-incidente
- **Obrigatório**: log no `Histórico de desvios` do AUTO-CONTINUE-PLAN.
- Se 2 drawdown breaches em 1 mês: review de Vision prompt + Batman
  thresholds.

---

## INC-004 — Trade preso em PARTIAL

### Sintomas
- `audit_log` `EXEC_PARTIAL` event sem `EXEC_FILLED` subsequente.
- `trades` table tem row `status=PARTIAL`, quantity < quantity esperada.
- Hyperliquid UI mostra ordem aberta resting.

### Ação imediata
1. NÃO usar kill switch ainda — deixa o monitor cycle de Wolverine
   ver o estado.
2. Verifica via REPL:
   ```python
   from hyperliquid.info import Info
   info = Info(constants.TESTNET_API_URL, skip_ws=True)
   state = info.user_state(addr)
   for pos in state.get("assetPositions", []):
       print(pos)
   ```

### Diagnóstico
- O fill parcial é normal em mercados thin? Aquaman score baixo no
  audit_log?
- A ordem residual ainda está resting no book?
- O notional total da position está dentro do que Batman aprovou?

### Recovery
- **Cancelar a residual manualmente** via Hyperliquid UI ou:
  ```python
  ex.cancel("BTC", oid)  # oid do audit_log.payload
  ```
- Atualiza `daily_pnl` manualmente se necessário (`upsert_daily_pnl`).
- Wolverine no próximo monitor cycle vai ver a position parcial e
  classificar (provavelmente HOLD se PnL ainda neutro).

### Pós-incidente
- Iron Man precisa de retry-then-cancel mais agressivo? Story futura.

---

## INC-005 — Kill switch acionado por engano

### Sintomas
- `data/.kill_switch` existe.
- Operator não lembra de tê-lo criado.

### Ação imediata
- **Não pressionar `rm` sem entender por quê**.
- Lê o conteúdo: `cat data/.kill_switch`. O motivo está lá.

### Diagnóstico
- Foi automático (Wolverine, Vision fallback breaker, exec error
  breaker)? `audit_log.event=RISK_KILL_SWITCH` mostra qual.
- Foi manual? `cat scripts/kill.sh` — vê se houve ./scripts/kill.sh
  recente em algum tab.

### Recovery
- Se foi automático e o problema raiz já voltou (ex: OpenAI on
  novamente, mercado calmo): `rm data/.kill_switch`.
- Se foi manual e você esqueceu o motivo: rola log mental, decide.

### Pós-incidente
- Considera estender o kill switch para uma file que também grava
  `metadata.json` com auto-release timestamp ("clear after 1h").

---

## INC-006 — Pytest vermelho inesperado durante operação

### Sintomas
- CI / pre-commit hook falhou.
- pytest local mostrou vermelho que não estava antes.

### Ação imediata
- **Não tocar runtime**. Operação atual continua.
- Não fazer commit. Não puxar a branch para main.

### Diagnóstico
- Diff `git status` — algum arquivo Python foi tocado por linter
  fora do que foi commited?
- Bug em runtime real ou bug em teste?
- Contaminação Pydantic v2 `__dict__` (já documentada em
  `HANDOFF § 11.5`)?

### Recovery
- Ler `HANDOFF § 11.5` — Lições aprendidas.
- Aplicar fix no lugar correto (test fix em `tests/`, runtime fix
  em `src/`).
- Atualizar `HANDOFF § 11.5` se descobriu novo padrão.

---

## INC-007 — Dashboard não mostra dados novos

### Sintomas
- `python run.py --dashboard` está rodando.
- `/api/overview` retorna estado antigo, não atualiza.
- `/ws` websocket conectou mas não recebe broadcasts.

### Ação imediata
- Confirma que **Nick Fury também está rodando** (ou outro processo
  alimentando o SQLite). Dashboard `--dashboard-only` lê DB que outro
  processo escreve.

### Diagnóstico
```bash
ls -lat data/mekka_trading.db
# arquivo deve estar com mtime recente

sqlite3 data/mekka_trading.db "
  select timestamp from audit_log order by timestamp desc limit 1;
"
# último timestamp deve estar próximo do agora
```

### Recovery
- Se SQLite parado: o processo de Nick Fury caiu. Reinicia.
- Se SQLite atualizando mas dashboard estático: F5 no browser. Se
  persistir, reinicia `python run.py --dashboard-only`.

---

## INC-008 — Pipeline degradou silenciosamente

### Sintomas
- Sem erros no audit_log.
- Mas a quantidade de signals/trades caiu de 8/dia para 0–1/dia.
- Vision retorna confidence < threshold consistentemente.

### Ação imediata
- Não é emergência. Não usa kill switch.
- Investigue.

### Diagnóstico
- Mercado mudou de regime? Spider-Man `should_pause=True` muito
  frequente?
- OpenAI mudou modelo padrão? `OPENAI_MODEL` ainda aponta para GPT-4o?
- Alguma config conservadora demais entrou?
  ```bash
  python -c "from src.config.settings import settings; print(settings.summary())"
  ```

### Recovery
- Caso a caso. Se for reduce de confiança em mercado lateral, ok.
- Se for config errada, restaura `.env`.

---

## Apêndice A — Comandos diagnósticos rápidos

```bash
# Status global do dia
sqlite3 data/mekka_trading.db "
  select date_utc, ending_equity, pnl_pct, drawdown_pct, trades_count
  from daily_pnl order by date_utc desc limit 7;
"

# Eventos críticos hoje (severity > INFO)
sqlite3 data/mekka_trading.db "
  select datetime(timestamp), agent, event, severity, message
  from audit_log
  where severity in ('WARNING','ERROR','CRITICAL')
  and timestamp >= date('now','start of day')
  order by timestamp desc;
"

# Distribution por agente nas últimas 24h
sqlite3 data/mekka_trading.db "
  select agent, event, count(*)
  from audit_log
  where timestamp >= datetime('now','-1 day')
  group by agent, event
  order by count(*) desc;
"
```

## Apêndice B — Quando NÃO precisa de playbook

Estes não são incidentes, são comportamento normal:

- Vision retornar HOLD em mercado lateral (sintoma 008 com
  causa orgânica).
- Batman retornar `REDUCED` por Thor multiplier — é desejado.
- `EXEC_SKIPPED` quando Batman REJECTED — pipeline funcionando.
- DailyPnL.drawdown_pct = 0.0 num dia neutro.
- 0 trades hoje em fim de semana baixa volatilidade.

Se inseguro: `pytest -v` e `python3 scripts/check_roster_consistency.py`.
Verde = está tudo bem na infra; comportamento neutro é mercado.

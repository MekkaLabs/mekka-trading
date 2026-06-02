# Revisão Profunda de Agentes — Mekka Trading (2026-06-01)

> 4 revisores adversariais independentes cobriram ~30 agentes (Batman/IronMan/
> NickFury/PortfolioManager já auditados antes nesta sessão). Foco: bugs reais +
> melhorias com `file:line`. Os 4 achados de maior valor já foram CORRIGIDOS
> (commit `fix(agents)`); o resto está priorizado abaixo para próximas rodadas.

---

## ✅ JÁ CORRIGIDOS (commit fix(agents) 2026-06-01)

| # | Achado | Local | Fix |
|---|--------|-------|-----|
| 1 | **Spider-Man FAIL-OPEN** — falha do detector de anomalia → `anomaly=None` → `is_safe_to_trade=True` | `professor_x.py:131` | sintetiza `AnomalyReport(should_pause=True)` na falha (fail-safe) |
| 2 | **VisionCritic rebaixa REJECT** a ENDORSE por delta pequeno (+ NameError silencioso) | `vision_critic.py:216,228` | só AMEND sujeito ao floor; REJECT preservado; sem re-chamar `_get_mode_params` |
| 3 | **Thor: ATR ausente → MEDIUM/1.0×** | `thor.py:106` | default HIGH/0.6× (conservador) |
| 4 | **Implementer run-once: rota+handler DUPLICADOS, default `dry_run=False`** | `server.py:575/590, 7264/7541` | consolidado em 1, default `dry_run=True` |

---

## ✅ RESOLVIDOS — rodadas 2 e 3 (2026-06-01)

| Achado | Fix |
|--------|-----|
| Aquaman lança em vez de degradar; book vazio→0.1; slippage só ask | degrada (_no_liquidity); score 0.0; slippage 2 lados (pior) |
| Spider-Man "flash crash" = desvio EMA-20 | queda close-a-close (recent_closes) |
| Cyclops avg_entry poluído por closes | filtra trades CYCLOPS-*/cyclops_* |
| Sem floor/teto de distância de stop-loss | gate Batman 4d (0.1%–20%) |
| MoA _vote_fallback pode lançar (quebra never-raises) | envolto → HOLD |
| MoA pula clamps do Vision (degraded + flash scalp) | aplicados no caminho MoA |
| Funding unit mismatch (BP horário vs Cable 8h) | Cable converte 8h→horário (÷8) |
| base.py CancelledError | except explícito (propaga limpo) |
| Mentor loop dead-end (s.rationale/evidence_n) | atributos certos + contrato applier |
| vault_auditor falsos órfãos (Cypher/Domino/Forge) | aliases codename↔arquivo |

## 🔴 ALTA PRIORIDADE — pendentes (próxima rodada)

### Layer 1 (dados → Vision)
- **Funding rate com unidade inconsistente** — Black Panther emite funding **horário**; o Cable adapter injeta funding **8h** no MESMO campo `onchain.funding_rate`. Spider-Man compara contra threshold horário. Erro de ~8× na interpretação. `black_panther.py:141` + `professor_x.py:191` + `spider_man.py:149`.
- **"Flash crash" do Spider-Man mede desvio da EMA-20, não crash** — falso positivo paralisa trading em downtrend; falso negativo deixa passar crash real. É o único check que gera HIGH/should_pause. `spider_man.py:111`. Usar `recent_closes` para variação candle-a-candle.
- **Defaults que mascaram falha como "tudo bem"** — DoctorStrange score 0.0, Black Panther NEUTRAL, Aquaman score 0.1/spread 1%, Thor (corrigido) — "não sei" vira "neutro/líquido/normal". Aquaman ainda **lança** em vez de degradar (`aquaman.py:141`) e estima slippage **só do lado ask** (errado p/ vendas, `:180`).
- **Indicadores manuais do Superman divergem de pandas_ta** — RSI (SMA vs Wilder), ATR (EWM vs Wilder), EMA (sem seed). ATR alimenta Thor (sizing). Mesmo candle → sinais diferentes conforme pandas_ta instalado. `superman.py:442-470`. Candle parcial tratado como fechado (`:478`).

### Layer 2 (LLM)
- **Sem floor/teto de distância de stop-loss** — LLM pode emitir SL a 0.01% do entry → R:R inflado (3000) passa no Batman, mas stop é estopado pelo primeiro tick; ou SL a 40% → perda real >> size sugerido. Nenhum gate de `min/max_stop_loss_pct`. Estrutural, vale corrigir independente de MoA.
- **MoA `_vote_fallback` pode lançar `ValidationError`** (fora de try/except) → quebra "never raises" → derruba o ciclo. `vision_moa.py:264,442`. (opt-in `VISION_MOA_ENABLED`)
- **MoA pula `_apply_degraded_quality_clamp` + flash scalp hard-block** do Vision — contorna proteções determinísticas. `vision_moa.py:258`.
- **MoA pondera por confiança auto-reportada** → amplifica outlier (modelo barato alucinando 0.95 domina). `vision_moa.py:421`.

### Monitoramento
- **Cyclops `avg_entry` poluído por trades de fechamento** em reentradas no mesmo símbolo → SL/TP/PnL sobre entrada errada. `cyclops.py:137`. (paper accounting; base do PnL)
- **Cyclops time-stop nunca roda em posição sem SL/TP** (skip antes do bloco de idade). `cyclops.py:161` vs `627`.
- **Debate (ProfessorX) fabrica consenso direcional de heurística não-direcional** (Aquaman/Thor votam LONG por liquidez/vol) e o prompt manda Vision "weight heavily" → viés long sistemático. `debate_moderator.py:281,290`. (opt-in `DEBATE_MODE_ENABLED`)

---

## 🟠 MÉDIA — pendentes

- **Mentor: loop de override é DEAD-END** — `mentor_overrides.json` não tem leitor (`get_override` sem consumidores) + `_enqueue_in_inbox` lança AttributeError engolido (`s.rationale`/`s.evidence_n` inexistentes) + dict do inbox omite campos que o applier exige. O loop "aprende" mas nada chega ao trade. `mentor.py:436,485` + `mentor_applier.py:132`. (NOTA: isso torna o auto-apply inócuo = fail-safe por acidente; religar exige reforçar `tighten`-only no consumo).
- **Wolverine não é "read-only"**: aciona `engage_kill_switch` sozinho (defensivo, ok) mas o trigger usa PnL **agregado** (posição A +500 / B −600 mascara sangria). `wolverine.py:263,275`.
- **base.py**: adicionar `except asyncio.CancelledError: raise` explícito (defensivo); `to_thread`+`timeout_s` = thread órfã (latente). `base.py:110,144`.
- **Jean Grey `recall()` relê o vault síncrono no event loop** sem `to_thread`/cache → bloqueia o loop se chamado por trade. `jean_grey.py:536`.
- **LLM**: retry empilhado (Vision × interno × fallback) → custo descontrolado em surto 429; sem `seed` (decisão não reproduzível); Anthropic status None retentado. `vision.py:967` + `llm_client.py:364,448`.
- **Prompt injection** via `headlines`/`macro_notes` scraped injetados verbatim no prompt do Vision (limitado pelos clamps, mas enviesa direção/confidence). `market_data.py:294`.
- **Escritas JSON sem fsync/lock** em mentor_applier/worker/_enqueue_in_inbox (race com auto-learning loop). Usar `atomic_write_json`.

---

## 🟡 BAIXA — pendentes
- ProfessorX `_degraded <= 2 fontes` permissivo demais (só dispara se todos os 6 Layer-1 caírem).
- ProfessorX task fire-and-forget sem retenção (`asyncio.create_task` GC). `:263`.
- Jean Grey dedup O(n²) (ok p/ 170 notas, não escala) + falso positivo por prefixo 700-char.
- Flash: dados de candle 4h rotulados como momentum intra-candle 5min + cache 60s (em scalp, stale). `flash.py:119`.
- `_last_elapsed_ms` atributo de classe (anti-pattern). `base.py:84`.

---

## 🧭 Tema central da revisão

O sistema é **robusto contra crash** (ninguém derruba o ciclo — `gather(return_exceptions=True)` + `_coerce`) mas **frágil contra silêncio**: quase todo agente Layer 1 degrada para um default que diz "tudo bem / neutro / líquido / volatilidade normal" em vez de "não sei". **Num sistema com dinheiro real, ausência de dado deveria empurrar para conservador/pausa, não para operar.** Os 4 fixes desta rodada começaram a inverter isso (Spider-Man e Thor agora fail-safe); o resto dos defaults perigosos (Aquaman, DoctorStrange, Black Panther, funding unit) é o próximo bloco.

Os safety gates de mainnet permanecem intactos (double-gate, Cyclops no-op em live, agentes de melhoria read-only/não-tocam-PROTECTED). Nenhum achado expõe perda direta determinística — concentram-se em **decisão enviesada** e **contabilidade paper distorcida**.

---

🤖 Gerado 2026-06-01 — 4 revisores adversariais (Claude Opus 4.8)

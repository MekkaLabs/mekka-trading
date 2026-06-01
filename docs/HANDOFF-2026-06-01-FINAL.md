# Handoff FINAL — Sessão 2026-06-01 (consolidado)

> Para a próxima janela. Sessão massiva: **auditoria de prontidão mainnet +
> revisão profunda de TODOS os agentes + revisão dos modos de trade + memória/
> Obsidian**. Branch `fix/mainnet-p0-audit`: **26 commits, 61 arquivos,
> +4628/-274, ~19 arquivos de teste novos.** Tudo SEM push (merge é do @devops).

---

## 🎯 TL;DR (5 linhas)

1. **Auditoria mainnet (13 agentes, workflow):** NO-GO → **GO-com-condições**. 28 findings + 2 follow-ups (H6/H7) corrigidos. Bloqueadores de execução/risco todos fechados.
2. **Revisão profunda de agentes (4 revisores adversariais, ~30 agentes):** ~26 fixes em 4 rodadas. Tema "fail-open → fail-safe" e "no-data ≠ neutro".
3. **Revisão dos 4 modos de trade:** 5 bugs (presets de risco ignorados + scalp gates mortos por import quebrado). Corrigidos.
4. **Memória/Obsidian:** loop de aprendizado do Mentor estava MORTO (bug de atributo) — religado ponta-a-ponta com clamp tighten-only. Vault 92/100, sync ok, falsos órfãos corrigidos.
5. **Backtest:** o "edge -4.58" era bug de `export_signals`, não estratégia.

---

## 🚦 AÇÃO DO OPERADOR antes do GO em mainnet

`.env` é PROTECTED (não posso editar). Para liberar mainnet:

```env
# OBRIGATÓRIO — o código agora EXIGE (preflight FALHA sem):
MAX_DAILY_LOSS_USD=...        # 2–5% do capital (kill-switch absoluto)
# Recomendado (M6):
MIN_EQUITY_FLOOR_USD=...      # piso de saldo (preflight FALHA se equity < piso)
# Params conservadores 1ª semana:
MAX_POSITION_SIZE_PCT=0.001   # 0.1%
MAX_LEVERAGE=2
BINANCE_ENTRY_ORDER_TYPE=auto # limit_ioc em mainnet
TELEGRAM_TRADE_APPROVAL_ENABLED=true
```
Depois: `python scripts/preflight_mainnet.py --strict` → tudo verde. Não escalar size na 1ª semana.

---

## 📦 OS 26 COMMITS (por tema)

**Auditoria mainnet (16 commits):** `7f66fd8` backtest-bug · `47c60e9` P0(C1/C2/H2/H1/H5) · `636eb06` C3+H4 · `036bf6e` H3+M1 · `35850d2` MEDIUM(M3/M4/M5/M7+H6) · `4e99d6c` H7/H8/H9 · `7b4ce30` M6/M8/M9 · `5007f90` L1+L7 · `b2f9120` L2-L6 · `90c79ab` H6-outbox+H7-atribuição · `fa26611` code-review-fixes · + 5 docs/handoff.

**CI squad (2):** `16b1768` testes scanners · `41f53df` KPI tile + Sage v2.

**Modos de trade (1):** `d86d345` presets de risco realmente aplicam + scalp gates religados.

**Revisão de agentes (6):** `54d833d` Spider-Man/Thor/VisionCritic/implementer · `ae93f43` Aquaman/Spider/Cyclops/stop-distance · `192a29b` MoA/funding/base · `daf80b3` no-data/time-stop/MoA/prompt-injection · `a33314a` Superman-Wilder/LLM-seed/debate/Mentor-reader · `f6e2b3c`+`9c7683f` docs.

**Memória/Obsidian (1):** `d37281d` Mentor loop religado + vault_auditor falsos órfãos.

---

## 🗂️ MAPA DE FIXES POR ÁREA

### Auditoria mainnet (30 findings — 100% fechado)
C1 NameError fail-safe · C2/M2 quantização SL/TP · C3/H4 idempotência+retry · H1 snapshot degradado · H2 margem fail-closed · H3 drawdown sobrevive restart · H5 roteamento testnet por-exchange · H6 outbox PENDING/finalize/reaper · H7 reconciliador+atribuição PnL live · H8 monitor liquidação · H9 TP guardian · M1 kill-switch absoluto exigido · M3 set_sandbox fail-closed · M4 market→limit_ioc · M5 preflight FAIL · M6 saldo mínimo · M7 guardian escala · M8 staleness feed · M9 clamp COIN-M · L1 TTL cache · L2 set_leverage fail-closed · L3 banner paper · L4 dedup order_id · L5 synthetic price · L6 SL no mark · L7 reuso CCXT.

### Modos de trade (5 fixes — `batman.py`)
P0 scalp gates 3s/3t religados (`get_active_mode`→`get_mode`) · P1 `max_daily_drawdown_pct`+`min_risk_reward_ratio` leem o preset · P2 `max_trades_per_day` lê preset · P3 `min_atr_pct_for_entry` aplicado (gate 3q). **Antes: trocar de modo NÃO ajustava drawdown/R:R/trades-dia.** Altcoins (override) e hard-clamp 1ª semana já ok.

### Revisão de agentes (~26 fixes)
- **Fail-open → fail-safe:** Spider-Man (falha → pausa) · VisionCritic (REJECT não rebaixa) · Thor (ATR ausente → HIGH conservador) · margem/sandbox fail-closed.
- **No-data ≠ neutro:** campo `data_available` em OnchainData/SentimentData/LiquidityData; Black Panther/DoctorStrange/Aquaman setam False; ProfessorX conta qualidade.
- **Execução/contabilidade:** Aquaman degrada+slippage-2-lados · Spider-Man flash-crash close-a-close · Cyclops avg_entry filtra closes + time-stop sem-SL/TP · Wolverine trigger por-posição · stop-distance gate (Batman 4d 0.1%-20%).
- **LLM/decisão:** MoA crash-wrap+clamps+confidence-clamp · prompt-injection sanitização · Superman RSI/ATR Wilder · LLM seed · debate Thor/Aquaman abstêm.
- **Robustez:** base.py CancelledError + `_last_elapsed_ms` instância · ProfessorX task retention · Jean Grey recall→to_thread.

### 🔑 Loop de aprendizado do Mentor — RELIGADO e SEGURO
`Mentor sugere → _enqueue_in_inbox (bug s.rationale/evidence_n corrigido) → mentor_applier (loosen-BLOCKED, opt-in) → mentor_overrides.json → Batman lê min_confidence com clamp tighten-only (max(override,default))`. Mesmo arquivo editado à mão NÃO afrouxa o gate.

---

## 🧪 TESTES (~19 arquivos novos, ~120 testes)

`test_iron_man_sl_failsafe_c1` · `test_iron_man_idempotency_c3_h4` · `test_h3_drawdown_restart` · `test_m1_daily_loss_cap_preflight` · `test_medium_mainnet_fixes` · `test_high_h7_h8_h9` · `test_residual_m6_m8_m9` · `test_low_l1_l7` · `test_low_l2_l6` · `test_followup_h6_h7` · `test_trading_modes` · `test_improvement_scanners` · `test_agents_review_fixes` · `test_agents_backlog_fixes` · `test_agents_backlog_round3` · `test_followups_final` · `test_followups_round2` · `test_memory_obsidian_fixes` · `test_story_220_backtest_outcome_simulator`.

**⚠️ Falhas de suíte que NÃO são regressão (NÃO confundir):**
- `test_nick_fury_calls_daily_pnl_at_end_of_cycle` (phase4), `phase6_safety_net`, `phase8_vision_critic`, `story_130`, `story_150_chaos` (13), `story_247` (2).
- São **pré-existentes** (provado: passam em ISOLAMENTO, falham só no run amplo por poluição de estado entre testes) ou **ambientais** (OpenAI/Anthropic 401 — sem API key no shell do Claude Code).
- **SEMPRE comparar com baseline via `git stash` em FOREGROUND** antes de atribuir uma falha às mudanças. `git stash` em background deixa o tree no estado baseline entre push/pop.

```bash
# Rodar só os testes da sessão (rápido, sem LLM/DB):
pytest tests/test_followups_round2.py tests/test_followups_final.py \
  tests/test_agents_backlog_round3.py tests/test_agents_backlog_fixes.py \
  tests/test_agents_review_fixes.py tests/test_memory_obsidian_fixes.py \
  tests/test_trading_modes.py tests/test_improvement_scanners.py -q   # 68 passam
```

---

## ⏳ PENDÊNCIAS (nenhuma bloqueia mainnet)

- **Operador:** setar `.env` (acima) + preflight verde.
- **@devops:** revisar/mergear/push da branch `fix/mainnet-p0-audit` (26 commits).
- **Vault:** 8 daily-note gaps (operator-manual).
- **Opcional:** o Mentor reader hoje só consome `min_confidence_threshold` no Batman; outros params (size/leverage) poderiam ser consumidos com o mesmo clamp tighten-only se desejado.
- **Candle parcial do Superman** (deixado de fora: tradeoff freshness vs precisão — decisão de design).

---

## 🗺️ ARQUIVOS-CHAVE TOCADOS

`src/agents/`: iron_man, nick_fury, batman, cyclops, wolverine, vision_moa, professor_x, spider_man, aquaman, black_panther, doctor_strange, thor, vision_critic, superman, mentor, base, jean_grey, llm_client.
`src/services/`: repository, daily_pnl_writer, price_feed, cable_regime_adapter, mentor_applier, vault_auditor, debate_moderator, backtest_*.
`src/models/`: market_data (data_available + _sanitize_untrusted), execution (PENDING/ORPHAN).
`src/config/`: settings, runtime_mode. `scripts/`: preflight_mainnet. `src/dashboard/`: positions_provider, server (KPI tile).

## 📄 RELATÓRIOS
`docs/audit/MAINNET-READINESS-AUDIT-2026-06-01.md` · `docs/audit/AGENTS-DEEP-REVIEW-2026-06-01.md`.

## 🧠 MEMÓRIAS ATUALIZADAS
project-mainnet-readiness-audit · project-trading-modes-review · project-agents-deep-review · project-memory-obsidian-review · project-backtest-edge-bug · project-memory-orphan-writers (resolvido).

---

## 🔄 PARA A PRÓXIMA SESSÃO

1. Abrir este handoff + os 2 relatórios em `docs/audit/`.
2. `git log --oneline main..fix/mainnet-p0-audit` (26 commits).
3. Caminho recomendado: (a) @devops revisa/mergeia; (b) operador seta `.env` + preflight; (c) 1ª semana em mainnet com params conservadores + Telegram approval.

**Estado mental:** sistema substancialmente endurecido — fail-safe onde era fail-open, conservador onde mascarava silêncio, aprendizado funcionando com segurança, vault saudável. **GO-com-condições.** Não escalar size até acumular trades reais e validar o edge empiricamente (as métricas de backtest são SIMULADAS).

---

🤖 Generated 2026-06-01 by Claude Opus 4.8 — handoff consolidado da sessão completa

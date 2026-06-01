# Handoff — Sessão 2026-06-01 (Auditoria de prontidão MAINNET)

> Para a próxima janela. Estado completo da branch `fix/mainnet-p0-audit`.
> Auditoria multi-agente do Mekka → veredito **NO-GO → GO-com-condições** após
> endurecer todos os bloqueadores. 11 commits, ~48 testes novos.

---

## 🎯 TL;DR

1. Rodou auditoria de **13 agentes** (8 dimensões + 4 pré-mortems) → relatório em
   `docs/audit/MAINNET-READINESS-AUDIT-2026-06-01.md`. Veredito inicial: **NO-GO**.
2. **28 findings corrigidos** (CRITICAL/HIGH/MEDIUM/LOW) em 11 commits na branch
   `fix/mainnet-p0-audit`. Só restam 2 follow-ups maiores (H6 outbox, H7 por-trade).
3. Também: corrigido o **edge "negativo" do backtest** (era bug de `export_signals`,
   não estratégia — Sharpe -4.58 → +6.64, mas métricas são simuladas, n pequeno).
4. **Sem push** — push/merge é exclusivo do @devops (Gage).

---

## 🚦 AÇÃO DO OPERADOR antes do GO real

`.env` é PROTECTED (não posso editar). Para liberar mainnet:

```env
# Obrigatório — o código agora EXIGE (preflight FALHA sem):
MAX_DAILY_LOSS_USD=...      # 2–5% do capital (kill-switch absoluto)

# Opcional mas recomendado (M6):
MIN_EQUITY_FLOOR_USD=...    # piso de saldo — preflight FALHA se equity < piso

# Params conservadores 1ª semana:
MAX_POSITION_SIZE_PCT=0.001   # 0.1%
MAX_LEVERAGE=2
BINANCE_ENTRY_ORDER_TYPE=auto # limit_ioc em mainnet
TELEGRAM_TRADE_APPROVAL_ENABLED=true
```

Depois: `python scripts/preflight_mainnet.py --strict` → tudo verde.

---

## 📦 BRANCH `fix/mainnet-p0-audit` — 11 commits

| Commit | Escopo |
|--------|--------|
| `7f66fd8` | fix(backtest) — edge "-4.58" era bug de `export_signals` (raw vazio → sl=0 → wipeout -$200) |
| `47c60e9` | P0 — C1 NameError fail-safe / C2 quantização SL/TP / H2 margem fail-closed / H1 snapshot degradado / H5 roteamento testnet |
| `636eb06` | C3+H4 — idempotência (clientOrderId) + retry CCXT correto |
| `036bf6e` | H3 drawdown sobrevive restart + M1 kill-switch absoluto exigido |
| `35850d2` | MEDIUM — M3 set_sandbox fail-closed / M4 market→limit_ioc mainnet / M5 preflight FAIL / M7 guardian escala / H6 anti-órfão |
| `4e99d6c` | H7 reconciliador PnL live / H8 monitor liquidação / H9 TP guardian |
| `7b4ce30` | M6 saldo mínimo / M8 staleness feed / M9 clamp COIN-M |
| `61c83d3` | docs: handoff |
| `5007f90` | L1 TTL cache snapshot / L7 reuso CCXT compartilhado |
| `b2f9120` | L2-L6 (set_leverage fail-closed, banner paper, dedup order_id, synthetic price, SL ancorado no mark) |

---

## 🗂️ FINDINGS RESOLVIDOS (28) — mapa rápido

| # | Problema | Arquivo |
|---|----------|---------|
| C1 | `cycle_id` ausente → NameError matava emergency_flatten (posição nua) | `iron_man.py` |
| C2/M2 | stopPrice/qty SL/TP não quantizados → rejeição PRICE_FILTER | `iron_man.py` |
| C3/H4 | sem idempotência + retry morto → duplicação de ordem | `iron_man.py` |
| H1 | snapshot PAPER_FALLBACK em live → equity sintético $10k | `nick_fury.py` |
| H2 | margem fail-open | `iron_man.py` |
| H3 | drawdown resetava no restart (atributo morto `_peak_equity`) | `nick_fury.py` + `daily_pnl_writer.py` + `repository.py` |
| H5 | `is_mainnet` só olhava Hyperliquid → lia saldo testnet | `settings.py` (`exchange_is_testnet`) + `portfolio_manager.py` |
| H6 | save_trade sem guard → posição órfã no DB | `nick_fury.py` |
| H7 | PnL de closes live nunca gravado | `nick_fury.py` (`_reconcile_live_close_pnl`) |
| H8 | sem monitor de proximidade de liquidação | `nick_fury.py` (`_check_liquidation_proximity`) |
| H9 | TP best-effort, guardian só cuidava do SL | `iron_man.py` (`_has_take_profit`) |
| M1 | kill-switch absoluto desligado (default 0.0) | `preflight_mainnet.py` + `nick_fury.py` |
| M3 | set_sandbox fail-open | `iron_man.py` |
| M4 | market em mainnet sem cap de slippage | `iron_man.py` |
| M5 | preflight só WARN, threshold 0.5% | `preflight_mainnet.py` |
| M6 | saldo mínimo só checkbox manual | `settings.py` + `preflight_mainnet.py` |
| M7 | guardian silencioso ao não ler posições | `iron_man.py` |
| M8 | feed WS markPrice sem staleness | `price_feed.py` + `positions_provider.py` |
| M9 | clamp leverage COIN-M só no dashboard | `batman.py` (gate 5d) |

---

## ✅ LOW L1–L7 — TODOS RESOLVIDOS (commits 5007f90 + b2f9120)

| # | Fix |
|---|-----|
| L1 | TTL no cache de snapshot (15min) + flag de staleness — `portfolio_manager.py` |
| L2 | set_leverage fail-closed em live (-4046 = sucesso; senão retry → REJECTED) — `iron_man.py` |
| L3 | banner "MODO PAPER" no preflight quando paper_trading=true — `preflight_mainnet.py` |
| L4 | save_trade dedup por order_id (idempotência no write) — `repository.py` |
| L5 | synthetic close usa avg entry ponderado (não 0) — `iron_man.py` |
| L6 | SL emergencial ancorado no MARK atual (não entry) — `iron_man.py` |
| L7 | PortfolioManager reusa `_CCXT_SHARED` do IronMan (não fecha) — `portfolio_manager.py` |

## ⚠️ PENDÊNCIAS (apenas 2 follow-ups maiores — não bloqueiam mainnet)

- **Follow-up H6**: outbox completo (gravar TradeRecord PENDING *antes* da ordem +
  update depois + fila de retry). Hoje há retry + alerta anti-órfão.
- **Follow-up H7**: atribuição por-trade do realizedPnl (hoje só audit agregado
  `LIVE_PNL_RECONCILED`).

---

## 🧪 TESTES (novos nesta sessão, ~48)

`test_iron_man_sl_failsafe_c1.py` · `test_iron_man_idempotency_c3_h4.py` ·
`test_h3_drawdown_restart.py` · `test_m1_daily_loss_cap_preflight.py` ·
`test_medium_mainnet_fixes.py` · `test_high_h7_h8_h9.py` ·
`test_residual_m6_m8_m9.py` + atualização de `test_phase14` (TestCheckRiskLimits).

**⚠️ Falhas de suite que NÃO são regressão:** `phase6_safety_net`,
`phase8_vision_critic`, `story_130`, `story_150_chaos` (13), `story_247` (2) —
pré-existentes (provado: phase6 falha **com e sem** a mudança) ou **ambientais**
(LLM 401 — sem API key no shell do Claude Code). **Sempre** comparar com baseline
via `git stash` antes de atribuir uma falha às mudanças.
**Cuidado:** `git stash` em **background** pode deixar o working tree no estado
baseline entre push/pop — rodar stash em **FOREGROUND**.

---

## 🛠️ COMANDOS ÚTEIS

```bash
# Preflight (agora Binance-aware + gates M1/M5/M6)
python scripts/preflight_mainnet.py --strict

# Rodar só os testes da auditoria (rápido, sem LLM)
pytest tests/test_residual_m6_m8_m9.py tests/test_high_h7_h8_h9.py \
  tests/test_medium_mainnet_fixes.py tests/test_h3_drawdown_restart.py \
  tests/test_m1_daily_loss_cap_preflight.py tests/test_iron_man_sl_failsafe_c1.py \
  tests/test_iron_man_idempotency_c3_h4.py -q

# Backtest (métricas simuladas — não é prova de edge real)
python -m src.backtest run --symbol BTC --days 7 --seed 42

# Relatório completo da auditoria
cat docs/audit/MAINNET-READINESS-AUDIT-2026-06-01.md
```

---

## 🔄 CONTINUIDADE

Próxima sessão:
1. Abrir este handoff + `docs/audit/MAINNET-READINESS-AUDIT-2026-06-01.md`.
2. `git log --oneline main..fix/mainnet-p0-audit` (11 commits).
3. Decidir: (a) @devops revisa/mergeia a branch; (b) operador seta `.env` +
   preflight verde; (c) opcional: follow-ups H6/H7 (outbox completo, atribuição por-trade).

**Estado mental:** todos os bloqueadores de execução e risco fechados e testados.
O sistema está **operável em mainnet sob condições** (config do operador + preflight
verde + params conservadores). Não escalar size na 1ª semana.

---

🤖 Generated 2026-06-01 by Claude Opus 4.8

# Story 036 — Mainnet Readiness Pre-Flight

**Milestone**: 11 — Mainnet Readiness  
**Status**: ✅ Entregue 2026-05-08  
**Fase pytest**: 14 (36 testes)

---

## Context

Mekka Trading foi construído paper-trading-first. O pipeline Python
completo (Stories 025–035b + Squad Fixes A1–C6) está funcionando em
testnet com paper_trading=True. Antes de qualquer ordem real, é
necessário um mecanismo formal de autorização duplo-gate que:

1. Impeça ordens acidentais quando alguém muda apenas `PAPER_TRADING=false`.
2. Forneça um checklist automatizado de pré-voo auditável.
3. Exija assinatura humana explícita antes de qualquer capital real.

---

## Goal

Implementar a infraestrutura de "duplo gate" (double-gate) para live
trading, um script de pré-voo com 8 verificações automáticas e 6
lembretes humanos, e um template de autorização formal.

---

## Scope Delivered

### 1. `src/config/settings.py` — campo `live_trading_confirmed` + validator

```python
live_trading_confirmed: bool = Field(
    default=False,
    description=(
        "Explicit second opt-in for live execution. "
        "Must be True together with paper_trading=False. ..."
    ),
)

@model_validator(mode="after")
def live_trading_double_gate(self) -> "Settings":
    if not self.paper_trading and not self.live_trading_confirmed:
        raise ValueError(
            "LIVE_TRADING_CONFIRMED must be set to 'true' when PAPER_TRADING=false. ..."
        )
    return self

@property
def is_live(self) -> bool:
    return not self.paper_trading and self.live_trading_confirmed
```

**Combinações válidas:**

| `paper_trading` | `live_trading_confirmed` | Resultado           |
| --------------- | ------------------------ | ------------------- |
| True            | False                    | PAPER (padrão)      |
| True            | True                     | PAPER (confirmado ignorado) |
| False           | True                     | LIVE (duplo opt-in) |
| False           | False                    | ❌ ValueError no startup |

`mode_label` foi atualizado para retornar `"LIVE"` apenas no terceiro
caso, nunca o quarto (bloqueado no validator Pydantic).

### 2. `src/agents/iron_man.py` — guard runtime (belt-and-suspenders)

Antes de qualquer branch live, IronMan re-verifica `live_trading_confirmed`
em tempo de execução. Isso protege contra mutations de settings pós-init:

```python
if not settings.paper_trading and not settings.live_trading_confirmed:
    self._log.error("[IronMan] BLOCKED: ...")
    return ExecutionResult(
        symbol=symbol,
        status=ExecutionStatus.REJECTED,
        is_paper=False,
        side=side,
        error="Live execution blocked: LIVE_TRADING_CONFIRMED not set. "
              "See docs/MAINNET-AUTHORIZATION.md.",
    )
```

### 3. `scripts/preflight_mainnet.py` — checklist de pré-voo

Script standalone com dois modelos de dado:

- `CheckResult(name, passed, level, detail, fix)` — resultado de uma verificação.
- `PreflightReport` — coleção com helpers `ok/fail/warn/skip` + `all_pass/fail_count/warn_count`.

**Verificações automáticas (8):**

| # | Verificação | Falha quando |
|---|-------------|--------------|
| 1 | `env_vars_required` | `OPENAI_API_KEY`, `HYPERLIQUID_PRIVATE_KEY` ou `HYPERLIQUID_WALLET_ADDRESS` ausentes |
| 2 | `settings_loads` | Settings.live_trading_double_gate levanta `ValueError` |
| 3 | `kill_switch` | `is_kill_switch_active()` retorna True |
| 4 | `network` | `HYPERLIQUID_NETWORK != "mainnet"` |
| 5 | `risk_limits` | position_size > 0.5%, leverage > 2x, trades/day > 5, open_pos > 2 |
| 6 | `telegram` | `telegram_enabled=False` |
| 7 | `sdk_eth_account` / `sdk_hyperliquid` | imports falham |
| 8 | `authorization_file` | arquivo ausente ou sem "GO MAINNET" |

**Gates humanos (6 lembretes — H1–H6):**

- H1: ≥ 1 mês testnet sem incidente crítico
- H2: Wolverine SL ENDORSE rate ≥ 70% nos últimos 30 dias
- H3: Vision Critic ON por ≥ 1 semana sem regressão de sinal
- H4: Story 032b (TS audit shim) entregue ou waiver documentado
- H5: Wallet mainnet dedicada criada (não pessoal)
- H6: Wallet funded via transferência real (não faucet testnet)

**Flags:**
```bash
python3 scripts/preflight_mainnet.py            # texto legível
python3 scripts/preflight_mainnet.py --json     # machine-readable para CI
python3 scripts/preflight_mainnet.py --strict   # exit 1 em qualquer WARN
```

### 4. `docs/MAINNET-AUTHORIZATION.md` — template de autorização

Template com seções obrigatórias: declaração GO MAINNET, identificação
do operador, checklist de gates humanos, parâmetros de capital inicial,
e assinatura. O preflight verifica a presença de "GO MAINNET" e a
ausência de placeholders `____`/`YOUR_NAME`.

### 5. `tests/test_phase14_mainnet_readiness.py` — 36 testes

Cobertura completa do duplo gate e do script de pré-voo:

- Settings double-gate (4 combinações válidas/inválidas)
- `is_live` property (3 testes)
- `mode_label` (3 testes)
- IronMan runtime guard — REJECTED quando gate não aberto (2 testes)
- `PreflightReport` helpers (6 testes)
- `check_env_vars` (4 testes)
- `check_kill_switch` (2 testes)
- `check_risk_limits` (4 testes)
- `check_authorization_file` (4 testes)
- `_HUMAN_GATES` integridade (5 testes)
- `run_preflight` integração/smoke (2 testes)

---

## Hard Rules Mantidas

- `paper_trading=True` permanece o default. Nenhuma ordem real enviada.
- IronMan é o único agente autorizado a tocar o SDK Hyperliquid.
- A dupla chave (`PAPER_TRADING=false` + `LIVE_TRADING_CONFIRMED=true`)
  não existe em nenhum `.env` de desenvolvimento — apenas no momento
  de autorização formal.
- O validator Pydantic rejeita `paper_trading=False + live_trading_confirmed=False`
  **no startup**, antes de qualquer outro código rodar.

---

## Acceptance

- [x] `Settings(paper_trading=False, live_trading_confirmed=False)` levanta `ValidationError`
- [x] `Settings(paper_trading=False, live_trading_confirmed=True)` inicializa sem erro
- [x] `settings.is_live` retorna `True` apenas quando ambos os gates estão abertos
- [x] `IronMan._run()` retorna `ExecutionStatus.REJECTED` quando `live_trading_confirmed=False` em runtime
- [x] `scripts/preflight_mainnet.py --json` produz saída JSON válida com `all_pass`, `fail_count`, `warn_count`
- [x] `check_authorization_file` detecta: ausente, sem sign-off, com placeholders, assinado
- [x] `run_preflight()` chama todas as 8 verificações automáticas
- [x] 36 testes fase 14 passam sem erros

---

## What's Next

- **§ 4** do AUTO-CONTINUE-PLAN — pré-requisitos operacionais:
  - Recriar venv em Python 3.13
  - Smoke test manual Iron Man SDK na testnet
  - Validar `MAX_POSITION_SIZE_PCT=0.005`, `MAX_LEVERAGE=2` no `.env`
  - Criar wallet mainnet dedicada
- **Story 034 — Deadpool** (requer ≥ 30 dias de histórico paper)
- **Story 032b** — TS audit shim (requer npm + better-sqlite3)
- **Autorização formal** — operador preenche `docs/MAINNET-AUTHORIZATION.md`
  quando todos os gates humanos H1–H6 forem satisfeitos.

---

## Files Changed

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `src/config/settings.py` | modificado | `live_trading_confirmed` field + `live_trading_double_gate` validator + `is_live` property + `mode_label` + `summary()` |
| `src/agents/iron_man.py` | modificado | Belt-and-suspenders runtime double-gate antes do branch live |
| `scripts/preflight_mainnet.py` | novo | Script de pré-voo com 8 verificações automáticas, 6 lembretes humanos, flags `--json`/`--strict` |
| `docs/MAINNET-AUTHORIZATION.md` | novo | Template de autorização formal (preenchido pelo operador antes do GO MAINNET) |
| `tests/test_phase14_mainnet_readiness.py` | novo | 36 testes cobrindo double-gate, preflight checks e autorização |
| `docs/stories/story-036-mainnet-readiness.md` | novo | Este documento |

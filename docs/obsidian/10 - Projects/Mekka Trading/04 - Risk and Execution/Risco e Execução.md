---
title: Risco e Execução
type: risk
created: 2026-05-15
updated: 2026-05-15
---

# Risco e Execução

## Hard Rules

- Nunca bypassar Batman.
- Kill switch (`MEKKA_KILL_SWITCH=1` ou `data/.kill_switch`) é absoluto.
- Live trade exige `paper_trading=False` e aprovação sem violações.
- Sempre registrar logs + audit_log + outputs validados.

## Batman — Gates de Risco

| Gate | ID | Regra |
| ---- | -- | ----- |
| Kill switch | — | Para tudo imediatamente |
| Drawdown diário | 1 | `daily_drawdown > max_daily_drawdown_pct` |
| Tamanho de posição | 2 | Cap em `max_position_size_pct` |
| Alavancagem | 3 | Cap em `max_leverage` |
| Confiança mínima | 4 | `confidence < min_confidence_threshold` |
| Risk/Reward | 5 | `rr < min_risk_reward_ratio` |
| Exposure cap | 6 | Total de posições abertas |
| Correlação | 3d | Rejeita símbolos correlacionados |
| Flash crash | 3e | Volatilidade extrema detectada |
| Re-entry cooldown | 3f | Cooldown após SL |
| ATR dinâmico | 3g | Posição dimensionada por ATR |
| Blacklist | 3h | Símbolo na blacklist automática |
| Funding rate | 3i | Funding adverso ao side |
| Trading hours | 3j | Fora da janela de operação |
| Pyramid | 3k | Scale-in apenas em posições lucrativas |
| Max trades/símbolo/dia | 3l | Limita frequência por ativo |
| Notional mínimo | 3m | Rejeita micro-posições |
| Drawdown semanal/símbolo | 3n | Limita perda por ativo na semana |
| Perdas consecutivas | 3o | Para após N SLs seguidos |
| Directional bias | 3p | Evita sequência do mesmo lado |
| ATR mínimo | 3q | Rejeita mercado parado |

Veredictos possíveis: `APPROVED` · `REDUCED` · `REJECTED` · `KILL_SWITCH`

## Cyclops — Monitor de Posições

Monitora posições abertas e age sobre SL/TP:

- **TP completo** → fecha posição + reset gate 3o
- **TP Ladder** → saídas graduais (1/3R, 2/3R, full)
- **Partial SL** → fecha 50% ao cruzar −0.75R (`partial_sl_enabled`)
- **Half-R warning** → alerta Telegram ao cruzar −0.5R
- **Scale-out** → Cyclops fecha parcialmente; Wolverine move SL

## Wolverine — Recovery Agent

- Move SL para breakeven ao atingir +1R
- Move SL para +1R ao atingir +2R (lock-in profit)
- `TIGHTEN_STOP` e `TRAIL_STOP` funcionam em modo live

## Iron Man — Execução

- Paper-first (SDK mock quando `paper_trading=True`)
- Live com SDK Hyperliquid (testnet → mainnet sob condições formais)
- Retry com tenacity (3 tentativas)
- Suporte a Bybit via CCXT (`exchange_adapter` configurável)

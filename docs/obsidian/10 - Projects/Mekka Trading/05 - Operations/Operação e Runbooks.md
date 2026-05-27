---
title: Operação e Runbooks
type: operations
created: 2026-05-15
updated: 2026-05-15
---

# Operação e Runbooks

## Entrypoints Python

> ⚠️ Usar sempre `python3` (não `python`) — sistema roda em Python 3.14 (Homebrew).

| Comando | O que faz |
| ------- | --------- |
| `python3 run.py --once` | Roda um ciclo completo e encerra |
| `python3 run.py --dashboard` | Sobe pipeline + dashboard em `localhost:8787` |
| `python3 run.py --dashboard-only` | Só o dashboard, sem pipeline |
| `python3 run.py --equity` | Mostra equity snapshot e encerra |

Dashboard → `http://localhost:8787`  
Pixel Office → `http://localhost:8787/office-v2/`

## Reinstalar dependências (Python 3.14)

```bash
pip3 install -r requirements.txt --break-system-packages
pip3 install pydantic-settings tenacity greenlet --break-system-packages
# pandas_ta sem numba (incompatível com Py3.14):
pip3 install pandas-ta --no-deps --break-system-packages
```

## CLIs TypeScript operacionais

- `npm run run:runtime`
- `npm run run:replay`
- `npm run run:export-report`
- `npm run run:verify-integrity`
- `npm run run:health-check`
- `npm run run:replay-dlq`
- `npm run run:alerts-retention`
- `npm run run:ops-status`
- `npm run run:ops-alerts`
- `npm run run:ops-alert-audit`

## Kill switch

```bash
# Parada imediata por env var:
MEKKA_KILL_SWITCH=1 python3 run.py --once

# Parada por arquivo:
touch data/.kill_switch
```

## Rotina de segurança

1. Verificar kill switch.
2. Validar modo paper antes da execução (`PAPER_TRADING=true`).
3. Rodar monitoramento (`run_monitor_cycle`) em janelas curtas.
4. Conferir audit trail ao final do ciclo.

## Telegram — comandos disponíveis

| Comando | Função |
| ------- | ------ |
| `/status` | Status geral do sistema |
| `/equity` | Breakdown de equity |
| `/balance` | Saldo live do Hyperliquid |
| `/positions` | Posições abertas |
| `/stats` | Estatísticas gerais |
| `/leaderboard` | Ranking de símbolos |
| `/risk` | Configurações de risco |
| `/weekly` | Relatório semanal |
| `/report` | Relatório diário |
| `/dryrun on\|off` | Ativa/desativa dry-run |
| `/unblacklist SYMBOL` | Remove símbolo da blacklist |

---
title: Runbook — Incident Playbook
type: runbook
tags: [runbook, incidente, mainnet, operacional, h1, kill-switch]
status: ativo
created: 2026-05-25
updated: 2026-05-25
---

# Runbook — Incident Playbook

> Procedimento para classificar, conter e documentar incidentes no Mekka Trading. Referenciado por [[Histórico Testnet (H1)]] como destino de cada incidente registrado durante o gate H1 (≥ 1 mês testnet sem incidente crítico).

## O que conta como incidente

| Severidade | Critério (exemplos) |
|---|---|
| **CRITICAL** | Kill switch engaged sem operador • Posição sem SL detectada • PnL diário ≤ −5% • Order rejected por -1021 (clock skew) recorrente • Drift DB↔exchange detectado mas não reconciliado • Wolverine EMERGENCY_CLOSE • Telegram alerta `SL_GUARDIAN_FAILED` |
| **HIGH** | Cycle_error recorrente em ≥3 ciclos consecutivos • Vision/Batman timeout • Reconciliação no boot encontrou erros • Phantom position detectado (DB acha aberto, exchange não) |
| **MEDIUM** | Single CYCLE_SKIPPED • Order rejeitado por -4045 (max stop orders) • Anomaly HIGH detectado por Spider-Man |
| **LOW** | Single retry de connection • Single -4164 (notional too small) |

## Fluxo de resposta (resumo: triagem → contenção → análise → registro)

### 1. Triagem (≤ 5 min)

- [ ] Confirmar nível via `curl -s http://localhost:8787/api/system/status`
- [ ] Confirmar posições atuais: `curl -s http://localhost:8787/api/positions`
- [ ] Confirmar mainnet readiness: `curl -s http://localhost:8787/api/mainnet-readiness`
- [ ] Verificar kill switch: `cat data/.kill_switch 2>/dev/null && echo ENGAGED || echo OFF`
- [ ] Verificar últimos audits: `sqlite3 data/mekka_trading.db "SELECT datetime(timestamp), agent, event, message FROM audit_log ORDER BY id DESC LIMIT 20"`

### 2. Contenção

Se CRITICAL:
- [ ] Engajar kill switch manualmente: dashboard → painel Kill Switch → Engage → motivo
- [ ] Telegram alerta para operador (deve disparar automaticamente se há `SL_GUARDIAN_FAILED` ou `BOOT_RECONCILE_ERRORS`)
- [ ] Considerar parar dashboard: `pkill -f "run.py --dashboard"`

Se HIGH:
- [ ] Inspecionar `logs/dashboard_runtime.log` últimas 200 linhas
- [ ] Confirmar SL guardian rodou no último monitor cycle
- [ ] Se há posição: confirmar que tem SL na exchange (`ensure_stops_for_open_positions`)

### 3. Análise (root cause)

- [ ] Reconstruir cronologia via audit_log
- [ ] Identificar caminho de código envolvido
- [ ] Verificar se há proteção/gate que deveria ter disparado
- [ ] Documentar contramedida aplicada

### 4. Registro

- [ ] Adicionar entrada em [[Histórico Testnet (H1)]] (formato: data + severidade + causa + ação)
- [ ] Se mudança de código necessária: criar ImprovementProposal via [[Mekka]] → operator accept → implementar
- [ ] Atualizar este playbook se a categoria do incidente é nova

## Contramedidas conhecidas

### Kill switch disparou (-5% PnL diário)
- Wolverine auto-engages quando `intraday_dd ≥ max_daily_drawdown_pct` (default 10%). Backstop defensivo correto.
- Investigar **por que** chegou a 10%: liquidez ruim, regime mudou, anomaly não detectada.
- Antes de liberar kill switch, garantir que [[Spider-Man]] não está sinalizando `should_pause`.
- Liberar via dashboard: painel Kill Switch → Release → motivo.

### Posição sem SL detectada
- [[Iron Man]] `ensure_stops_for_open_positions()` recoloca automaticamente no próximo monitor cycle (5min). Alerta `SL_GUARDIAN_REPLACED` (WARNING) ou `SL_GUARDIAN_FAILED` (CRITICAL).
- Se FAILED: revisar manualmente via terminal CCXT. Posição **NÃO** pode ficar nua em mainnet.

### Phantom position (DB tem, exchange não)
- `IronMan.reconcile_phantom_positions()` insere synthetic close automático. Alerta `PHANTOM_RECONCILED` (WARNING).
- Se phantom persiste: investigar audit_log para entender quando posição foi fechada fora-do-bot.

### Order rejeitado -4045 (max stop orders, Binance)
- SL guardian já trata: cancela órfãos + retry. Se persistir, é quota dessincronizada da testnet.
- Workaround: aguardar reset testnet ou usar nova conta.

### Order rejeitado -1021 (clock skew)
- `recvWindow=60_000` já configurado em todos clientes CCXT.
- Se ocorre: verificar NTP do host (`sntp -sS pool.ntp.org`).

### Drift DB↔exchange detectado
- [[Trade Outcome Resolver]] não cobre — é caminho diferente.
- Phantom reconciliation (boot + monitor) corrige o lado "DB tem".
- Lado oposto (exchange tem, DB não tem) — SL guardian já coloca SL emergencial.

## Cross-references

- [[Histórico Testnet (H1)]] — registro de incidentes
- [[Kill Switch - Operação]] — operação do kill switch
- [[Iron Man]] — owner do SL guardian e phantom reconciliation
- [[Batman]] — gates de risco antes do trade
- [[Wolverine]] — recovery e auto-engage kill switch
- [[Trade Outcome Resolver]] — sincroniza memórias no close

## Status

- ✅ Criado em 2026-05-25 (fix do único link quebrado do vault)
- ⏳ Adicionar diagrama de fluxo (CRITICAL path) na próxima iteração
- ⏳ Linkar para Mekka `/Melhorias` quando incident vira proposta

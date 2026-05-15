---
title: "Runbook — Iniciar runtime do Megazord"
type: runbook
tags: [runbook, ops]
created: 2026-05-07
severity: low
---

# Runbook — Iniciar runtime do Megazord

> **Quando usar**: para inicializar o loop principal de operação (paper trading)
> **Severidade**: baixa
> **Tempo médio**: 1-2 min

## Pré-requisitos

- Node.js 20+ instalado
- `.env` configurado a partir do `.env.example`
- `PAPER_TRADING=true` (default — não alterar sem revisão de risco)
- Dependências instaladas: `npm install`

## Passos

1. **Build do projeto**
   ```bash
   npm run build
   ```

2. **Quality gates**
   ```bash
   npm run lint
   npm run typecheck
   npm test
   ```

3. **Inicializar runtime**
   ```bash
   npm run run:runtime
   ```
   Equivalente a `node dist/cli/main.js`.

4. **Em outro terminal, monitorar status operacional**
   ```bash
   npm run run:ops-status
   ```

## Validação

- Logs aparecem em `observability/store/`
- Audit-log incrementando em `memory/audit-log/`
- `npm run run:health-check` retorna OK
- Nenhum alerta crítico em `npm run run:ops-alerts`

## Rollback

- `Ctrl+C` para parar o runtime
- Validar integridade: `npm run run:verify-integrity`

## Referências

- [[../../50 - MOCs/MOC - Operações & Observability]]
- README — seção "Start"

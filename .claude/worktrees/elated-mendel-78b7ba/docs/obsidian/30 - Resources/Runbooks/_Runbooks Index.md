---
title: Runbooks — Index
type: index
tags: [runbook]
created: 2026-05-07
---

# Runbooks

> Procedimentos passo-a-passo para operação. Use `Template - Runbook`.

## Runbooks a criar (sugeridos)

- [ ] Iniciar runtime do Megazord
- [ ] Replay de eventos históricos
- [ ] Reprocessar Dead Letter Queue (DLQ)
- [ ] Ativar/desativar kill switch
- [ ] Verificar integridade do audit-log
- [ ] Exportar relatório de missão
- [ ] Investigar alerta crítico
- [ ] Rotacionar credenciais (.env)
- [ ] Restaurar de backup

## Runbooks documentados

```dataview
TABLE without ID
  file.link AS "Runbook",
  severity AS "Severidade"
FROM "30 - Resources/Runbooks"
WHERE type = "runbook"
SORT file.name ASC
```

---
title: Inbox
type: index
tags: [inbox]
---

# 📥 Inbox

> Toda nota nova nasce aqui. Reserve 5 min/dia para processar:
> - O que é projeto com prazo? → mover para `10 - Projects`
> - O que é responsabilidade contínua? → mover para `20 - Areas`
> - O que é referência/runbook/decisão? → mover para `30 - Resources`
> - O que está concluído? → mover para `40 - Archive`
> - O que é só rascunho efêmero? → deletar sem culpa

## Notas a processar

```dataview
LIST
FROM "00 - Inbox"
WHERE file.path != this.file.path
SORT file.ctime DESC
```

---
title: Operacional — Index
type: area
tags: [area, ops]
created: 2026-05-07
---

# Área — Operacional

> Runbooks, alertas, métricas, incidentes.

Ver também: [[../../50 - MOCs/MOC - Operações & Observability]]

## Notas

```dataview
LIST
FROM "20 - Areas/Operacional"
WHERE file.path != this.file.path
SORT file.mtime DESC
```

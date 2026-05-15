---
title: Daily Notes
type: index
tags: [daily]
---

# 📅 Daily Notes

> Log diário. Use `Cmd/Ctrl + P` → "Daily notes: Open today's daily note".
> Template em `[[../70 - Templates/Daily Note]]`.

## Última semana

```dataview
LIST
FROM "60 - Daily"
WHERE file.path != this.file.path AND date(file.cday) >= date(today) - dur(7 days)
SORT file.cday DESC
```

## Todas as daily notes

```dataview
LIST
FROM "60 - Daily"
WHERE file.path != this.file.path
SORT file.cday DESC
LIMIT 30
```

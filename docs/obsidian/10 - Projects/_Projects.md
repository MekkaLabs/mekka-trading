---
title: Projects
type: index
tags: [projects]
---

# 🎯 Projects

> Iniciativas com **entregável claro** e **prazo definido**. Quando termina, vai para `40 - Archive`.

## Frontmatter recomendado para cada projeto

```yaml
---
title: "Projeto — <nome>"
type: project
status: ativo | pausado | done | archived
due: YYYY-MM-DD
owner: 
tags: [project]
---
```

## Projetos ativos

```dataview
TABLE without ID
  file.link AS "Projeto",
  status AS "Status",
  due AS "Prazo",
  owner AS "Owner"
FROM "10 - Projects"
WHERE status = "ativo"
SORT due ASC
```

## Pausados

```dataview
LIST
FROM "10 - Projects"
WHERE status = "pausado"
```

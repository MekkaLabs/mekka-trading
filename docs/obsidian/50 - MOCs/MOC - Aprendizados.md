---
title: MOC — Aprendizados
type: moc
tags: [moc, aprendizado]
created: 2026-05-07
---

# 📚 MOC — Aprendizados

> Lições aprendidas, padrões observados, anti-padrões evitados.

## Por que isto existe

Um segundo cérebro só vale a pena se os erros não se repetirem. Toda vez que algo sair errado (ou inesperadamente certo), capture aqui — vira capital intelectual do projeto.

## Categorias

- `#aprendizado/tecnico` — descobertas técnicas (libs, padrões, gotchas)
- `#aprendizado/produto` — sobre o domínio de trading
- `#aprendizado/processo` — como você trabalha melhor
- `#aprendizado/erro` — bugs e como foram resolvidos

## Aprendizados recentes

```dataview
TABLE without ID
  file.link AS "Aprendizado",
  category AS "Categoria",
  date AS "Data"
FROM #aprendizado
SORT date DESC
LIMIT 20
```

## Antipadrões a evitar

```dataview
LIST
FROM #antipadrao
SORT file.mtime DESC
```

## Como capturar

1. Aconteceu algo digno de nota? Crie nota no `00 - Inbox`
2. Use o template `[[../70 - Templates/Template - Aprendizado]]`
3. Tag com `#aprendizado/<categoria>`
4. Nas suas daily notes, vincule ao aprendizado quando relevante

---
title: Paper Trading vs Live
type: ops
tags: [ops, execução, risco]
created: 2026-05-07
updated: 2026-05-07
---

# Paper Trading vs Live

## Padrão

- Operação padrão é paper (`paper_trading=True`)

## Live (somente com consciência explícita)

Condições mínimas simultâneas:

1. `paper_trading=False`
2. Batman aprovado sem limites violados
3. Operador ciente do risco e janela de execução

## Garantias

- Iron Man permanece com retry controlado (tenacity)
- Logs + SQLite audit são obrigatórios em qualquer modo

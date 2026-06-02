---
rec_id: "cb9240865227"
type: implementation-recipe
area: research
impact: MEDIUM
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-cb9240865227 — ccxt: releases novas com breaking/segurança (4.5.55)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `research`
- **Impacto:** `MEDIUM`

## Descrição

Há releases de `ccxt` mais novas que a instalada (4.5.52) cujas notas mencionam breaking changes/segurança/deprecação. Revisar o changelog antes de atualizar e validar em testnet.

## Por que importa

_(sem rationale)_

## Evidência

github.com/ccxt/ccxt/releases — versões 4.5.55 > instalada 4.5.52.

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-cb9240865227.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-cb9240865227`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-cb9240865227] ccxt: releases novas com breaking/segurança (4.5.55)"
   ```
7. Atualizar `dev_state` para `pr_open` via dashboard ou rodar
   `python3 scripts/sync_imp_commits.py`.
8. Bridge automaticamente:
   - tira snapshot Sage DEPOIS
   - cria nota de review em `30 - Resources/Reviews/` no vault canônico

## Checklist de validação

- [ ] Mudança implementada conforme descrição
- [ ] Mitigações do Galactus endereçadas (ver brief)
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam
- [ ] Validado em paper/testnet antes de qualquer impacto em produção
- [ ] Commit subject contém `[IMP-cb9240865227]`

## Notas relacionadas

- Brief original: [[IMP-cb9240865227]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

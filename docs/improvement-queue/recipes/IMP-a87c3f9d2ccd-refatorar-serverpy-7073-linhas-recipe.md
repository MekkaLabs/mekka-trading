---
rec_id: "a87c3f9d2ccd"
type: implementation-recipe
area: backend
impact: HIGH
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-a87c3f9d2ccd — Refatorar server.py (7073 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `HIGH`

## Descrição

`src/dashboard/server.py` tem 7073 linhas — acima do limite de 1500. Arquivos grandes concentram risco, dificultam revisão e testes. Quebrar em módulos coesos por responsabilidade.

## Por que importa

_(sem rationale)_

## Evidência

src/dashboard/server.py: 7073 linhas (limite 1500, enorme ≥4000).

## Arquivos prováveis afetados

- `src/dashboard/server.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-a87c3f9d2ccd.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-a87c3f9d2ccd`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-a87c3f9d2ccd] Refatorar server.py (7073 linhas)"
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
- [ ] Commit subject contém `[IMP-a87c3f9d2ccd]`

## Notas relacionadas

- Brief original: [[IMP-a87c3f9d2ccd]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

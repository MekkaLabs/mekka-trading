---
rec_id: "ec93e1bea26e"
type: implementation-recipe
area: frontend
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-ec93e1bea26e — Frontend: refatorar style.css (4827 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `frontend`
- **Impacto:** `LOW`

## Descrição

`src/dashboard/static/style.css` tem 4827 linhas de CSS. Considere modularizar por componente ou usar BEM/utility classes.

## Por que importa

_(sem rationale)_

## Evidência

src/dashboard/static/style.css: 4827 linhas

## Arquivos prováveis afetados

- `src/dashboard/static/style.css`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-ec93e1bea26e.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-ec93e1bea26e`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-ec93e1bea26e] Frontend: refatorar style.css (4827 linhas)"
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
- [ ] Commit subject contém `[IMP-ec93e1bea26e]`

## Notas relacionadas

- Brief original: [[IMP-ec93e1bea26e]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

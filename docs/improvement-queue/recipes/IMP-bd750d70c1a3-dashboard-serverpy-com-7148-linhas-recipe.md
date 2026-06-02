---
rec_id: "bd750d70c1a3"
type: implementation-recipe
area: dashboard
impact: HIGH
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-bd750d70c1a3 — Dashboard: server.py com 7148 linhas

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `dashboard`
- **Impacto:** `HIGH`

## Descrição

`src/dashboard/server.py` tem **7148 linhas** — extrair handlers para módulos por domínio. Já existe parte feita em `src/dashboard/routers/` (improvements). Continuar a extração.

## Por que importa

_(sem rationale)_

## Evidência

src/dashboard/server.py: 7148 linhas

## Arquivos prováveis afetados

- `src/dashboard/server.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-bd750d70c1a3.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-bd750d70c1a3`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-bd750d70c1a3] Dashboard: server.py com 7148 linhas"
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
- [ ] Commit subject contém `[IMP-bd750d70c1a3]`

## Notas relacionadas

- Brief original: [[IMP-bd750d70c1a3]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

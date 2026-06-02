---
rec_id: "af335f1706af"
type: implementation-recipe
area: backend
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-af335f1706af — Refatorar src/services/mekka_kernel.py (875 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `LOW`

## Descrição

`src/services/mekka_kernel.py` tem 875 linhas. Monitorar crescimento.

## Por que importa

_(sem rationale)_

## Evidência

src/services/mekka_kernel.py: 875 linhas (limite 600)

## Arquivos prováveis afetados

- `src/services/mekka_kernel.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-af335f1706af.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-af335f1706af`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-af335f1706af] Refatorar src/services/mekka_kernel.py (875 linhas)"
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
- [ ] Commit subject contém `[IMP-af335f1706af]`

## Notas relacionadas

- Brief original: [[IMP-af335f1706af]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

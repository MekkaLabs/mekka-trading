---
rec_id: "c6fe17ff9544"
type: implementation-recipe
area: agents
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-c6fe17ff9544 — Refatorar batman.py (1798 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `agents`
- **Impacto:** `LOW`

## Descrição

`src/agents/batman.py` tem 1798 linhas (acima do warn 1500). Monitorar crescimento.

## Por que importa

_(sem rationale)_

## Evidência

src/agents/batman.py: 1798 linhas (limite 1500, enorme ≥4000).

## Arquivos prováveis afetados

- `src/agents/batman.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-c6fe17ff9544.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-c6fe17ff9544`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-c6fe17ff9544] Refatorar batman.py (1798 linhas)"
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
- [ ] Commit subject contém `[IMP-c6fe17ff9544]`

## Notas relacionadas

- Brief original: [[IMP-c6fe17ff9544]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

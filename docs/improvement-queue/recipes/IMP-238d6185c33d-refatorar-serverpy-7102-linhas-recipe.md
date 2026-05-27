---
rec_id: "238d6185c33d"
type: implementation-recipe
area: backend
impact: HIGH
generated_at: 2026-05-27T18:41:06
auto_generated: true
---

# Recipe IMP-238d6185c33d — Refatorar server.py (7102 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `HIGH`

## Descrição

`src/dashboard/server.py` tem 7102 linhas — acima do limite de 1500. Arquivos grandes concentram risco, dificultam revisão e testes. Quebrar em módulos coesos por responsabilidade.

## Por que importa

_(sem rationale)_

## Evidência

src/dashboard/server.py: 7102 linhas (limite 1500, enorme ≥4000).

## Arquivos prováveis afetados

- `src/dashboard/server.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-238d6185c33d.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-238d6185c33d`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-238d6185c33d] Refatorar server.py (7102 linhas)"
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
- [ ] Commit subject contém `[IMP-238d6185c33d]`

## Notas relacionadas

- Brief original: [[IMP-238d6185c33d]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

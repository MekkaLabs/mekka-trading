---
rec_id: "8b6bf57f5bc3"
type: implementation-recipe
area: backend
impact: HIGH
generated_at: 2026-05-27T19:04:11
auto_generated: true
---

# Recipe IMP-8b6bf57f5bc3 — Função longa: run() em cyclops.py (700 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `HIGH`

## Descrição

`run` em `src/agents/cyclops.py` tem 700 linhas (limite 120). Funções longas escondem complexidade e dificultam teste — extrair em helpers.

## Por que importa

_(sem rationale)_

## Evidência

src/agents/cyclops.py: run() = 700 linhas (limite 120).

## Arquivos prováveis afetados

- `src/agents/cyclops.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-8b6bf57f5bc3.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-8b6bf57f5bc3`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-8b6bf57f5bc3] Função longa: run() em cyclops.py (700 linhas)"
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
- [ ] Commit subject contém `[IMP-8b6bf57f5bc3]`

## Notas relacionadas

- Brief original: [[IMP-8b6bf57f5bc3]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

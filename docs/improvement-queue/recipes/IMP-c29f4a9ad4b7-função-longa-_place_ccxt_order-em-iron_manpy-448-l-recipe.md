---
rec_id: "c29f4a9ad4b7"
type: implementation-recipe
area: backend
impact: HIGH
generated_at: 2026-05-27T18:41:06
auto_generated: true
---

# Recipe IMP-c29f4a9ad4b7 — Função longa: _place_ccxt_order() em iron_man.py (448 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `HIGH`

## Descrição

`_place_ccxt_order` em `src/agents/iron_man.py` tem 448 linhas (limite 120). Funções longas escondem complexidade e dificultam teste — extrair em helpers.

## Por que importa

_(sem rationale)_

## Evidência

src/agents/iron_man.py: _place_ccxt_order() = 448 linhas (limite 120).

## Arquivos prováveis afetados

- `src/agents/iron_man.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-c29f4a9ad4b7.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-c29f4a9ad4b7`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-c29f4a9ad4b7] Função longa: _place_ccxt_order() em iron_man.py (448 linhas)"
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
- [ ] Commit subject contém `[IMP-c29f4a9ad4b7]`

## Notas relacionadas

- Brief original: [[IMP-c29f4a9ad4b7]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

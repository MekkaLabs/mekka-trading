---
rec_id: "23fcc9e5e472"
type: implementation-recipe
area: backend
impact: MEDIUM
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-23fcc9e5e472 — Refatorar src/services/telegram_inbound.py (1320 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `MEDIUM`

## Descrição

`src/services/telegram_inbound.py` tem 1320 linhas. Considere extrair responsabilidades em módulos coesos.

## Por que importa

_(sem rationale)_

## Evidência

src/services/telegram_inbound.py: 1320 linhas (limite 600)

## Arquivos prováveis afetados

- `src/services/telegram_inbound.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-23fcc9e5e472.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-23fcc9e5e472`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-23fcc9e5e472] Refatorar src/services/telegram_inbound.py (1320 linhas)"
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
- [ ] Commit subject contém `[IMP-23fcc9e5e472]`

## Notas relacionadas

- Brief original: [[IMP-23fcc9e5e472]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

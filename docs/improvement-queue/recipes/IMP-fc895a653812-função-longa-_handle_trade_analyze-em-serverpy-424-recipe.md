---
rec_id: "fc895a653812"
type: implementation-recipe
area: backend
impact: HIGH
generated_at: 2026-05-27T18:41:06
auto_generated: true
---

# Recipe IMP-fc895a653812 — Função longa: _handle_trade_analyze() em server.py (424 linhas)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `HIGH`

## Descrição

`_handle_trade_analyze` em `src/dashboard/server.py` tem 424 linhas (limite 120). Funções longas escondem complexidade e dificultam teste — extrair em helpers.

## Por que importa

_(sem rationale)_

## Evidência

src/dashboard/server.py: _handle_trade_analyze() = 424 linhas (limite 120).

## Arquivos prováveis afetados

- `src/dashboard/server.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-fc895a653812.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-fc895a653812`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-fc895a653812] Função longa: _handle_trade_analyze() em server.py (424 linhas)"
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
- [ ] Commit subject contém `[IMP-fc895a653812]`

## Notas relacionadas

- Brief original: [[IMP-fc895a653812]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

---
rec_id: "3b4064687ecc"
type: implementation-recipe
area: frontend
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-3b4064687ecc — Frontend: 3 HTMLs com scripts sem cache-bust

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `frontend`
- **Impacto:** `LOW`

## Descrição

Scripts locais sem `?v=...` ficam grudados no cache do browser após mudanças no servidor (Babel-standalone é especialmente agressivo). Top: src/dashboard/static/index.html: 7 scripts; src/dashboard/static/office_v4/index.html: 7 scripts; src/dashboard/static/office-v2/cloud/Mekka Pixel Office.html: 7 scripts.

## Por que importa

_(sem rationale)_

## Evidência

3 HTMLs com scripts sem cache-bust

## Arquivos prováveis afetados

- `src/dashboard/static/index.html`
- `src/dashboard/static/office_v4/index.html`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-3b4064687ecc.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-3b4064687ecc`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-3b4064687ecc] Frontend: 3 HTMLs com scripts sem cache-bust"
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
- [ ] Commit subject contém `[IMP-3b4064687ecc]`

## Notas relacionadas

- Brief original: [[IMP-3b4064687ecc]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

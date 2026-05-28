---
rec_id: "26f583cd5112"
type: implementation-recipe
area: frontend
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-26f583cd5112 — Frontend: ~38 classes CSS potencialmente órfãs

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `frontend`
- **Impacto:** `LOW`

## Descrição

Heurística detectou 38 classes definidas em CSS que não aparecem em nenhum HTML/JS. Sujeito a falsos positivos (classes geradas dinamicamente, BEM siblings) — revisar antes de remover.

## Por que importa

_(sem rationale)_

## Evidência

~38 classes definidas e aparentemente não-usadas

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-26f583cd5112.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-26f583cd5112`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-26f583cd5112] Frontend: ~38 classes CSS potencialmente órfãs"
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
- [ ] Commit subject contém `[IMP-26f583cd5112]`

## Notas relacionadas

- Brief original: [[IMP-26f583cd5112]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

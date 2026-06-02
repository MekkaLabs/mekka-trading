---
rec_id: "3b7949351e8f"
type: implementation-recipe
area: memory
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-3b7949351e8f — Vault: 477 par(es) de notas duplicadas

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `memory`
- **Impacto:** `LOW`

## Descrição

Notas quase idênticas fragmentam o conhecimento e confundem a recuperação. Consolidar/mesclar as duplicatas.

## Por que importa

_(sem rationale)_

## Evidência

477 pares candidatos. Ex.: 30 - Resources/Reviews/Review Semanal.md≈20 - Areas/Operacional/Review Semanal.md (100%); 10 - Projects/Mekka Trading/06 - Stories and Roadmap/Stories/Story 032b.md≈10 - Projects/Mekka Trading/06 - Stories and Roadmap/Stories/Story 032.md (95%); 10 - Projects/Mekka Trading/06 - Stories and Roadmap/Stories/Story 035.md≈10 - Projects/Mekka Trading/06 - Stories and Roadmap/Stories/Story 035b.md (95%)

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-3b7949351e8f.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-3b7949351e8f`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-3b7949351e8f] Vault: 477 par(es) de notas duplicadas"
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
- [ ] Commit subject contém `[IMP-3b7949351e8f]`

## Notas relacionadas

- Brief original: [[IMP-3b7949351e8f]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

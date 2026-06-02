---
rec_id: "ea44c364dd65"
type: implementation-recipe
area: memory
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-ea44c364dd65 — Vault: 7 link(s) quebrado(s) no segundo cérebro

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `memory`
- **Impacto:** `LOW`

## Descrição

Wikilinks apontando para notas inexistentes degradam a navegação e a recuperação de memória dos agentes. Corrigir os alvos ou criar as notas.

## Por que importa

_(sem rationale)_

## Evidência

7 links quebrados. Ex.: 20 - Areas/Agentes IA/Cable.md→[[adr-004]]; 20 - Areas/Agentes IA/Prometheus.md→[[prompt_engineering]]; 20 - Areas/Agentes IA/Prometheus.md→[[vision critic]]; 60 - Daily/2026-05-27-improvements-accepted.md→[[imp-1daa6c90a1b5]]

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-ea44c364dd65.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-ea44c364dd65`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-ea44c364dd65] Vault: 7 link(s) quebrado(s) no segundo cérebro"
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
- [ ] Commit subject contém `[IMP-ea44c364dd65]`

## Notas relacionadas

- Brief original: [[IMP-ea44c364dd65]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

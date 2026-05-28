---
rec_id: "c289312c383d"
type: implementation-recipe
area: dashboard
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-c289312c383d — Dashboard: 29/134 handlers sem docstring

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `dashboard`
- **Impacto:** `LOW`

## Descrição

Endpoints sem docstring no def dificultam onboarding e observabilidade. Top: `server._handle_index`, `server._handle_health`, `server._handle_overview`, `server._handle_signals`, `server._handle_trades`.

## Por que importa

_(sem rationale)_

## Evidência

29 de 134 handlers sem docstring

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-c289312c383d.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-c289312c383d`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-c289312c383d] Dashboard: 29/134 handlers sem docstring"
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
- [ ] Commit subject contém `[IMP-c289312c383d]`

## Notas relacionadas

- Brief original: [[IMP-c289312c383d]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

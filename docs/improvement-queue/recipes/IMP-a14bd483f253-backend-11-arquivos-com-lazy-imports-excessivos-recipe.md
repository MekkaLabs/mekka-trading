---
rec_id: "a14bd483f253"
type: implementation-recipe
area: backend
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-a14bd483f253 — Backend: 11 arquivos com lazy imports excessivos

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `LOW`

## Descrição

Lazy imports dentro de funções (`from src... import` indentado) geralmente indicam ciclo de import não-resolvido. Top offenders: `src/services/telegram_inbound.py` (26), `src/services/mekka_kernel.py` (15), `src/services/improvement_memory_bridge.py` (8), `src/services/cycle_state_resetter.py` (6), `src/services/signal_validator.py` (6). Vale revisar dependências.

## Por que importa

_(sem rationale)_

## Evidência

11 arquivos com >=4 lazy imports

## Arquivos prováveis afetados

- `src/services/telegram_inbound.py`
- `src/services/mekka_kernel.py`
- `src/services/improvement_memory_bridge.py`
- `src/services/cycle_state_resetter.py`
- `src/services/signal_validator.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-a14bd483f253.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-a14bd483f253`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-a14bd483f253] Backend: 11 arquivos com lazy imports excessivos"
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
- [ ] Commit subject contém `[IMP-a14bd483f253]`

## Notas relacionadas

- Brief original: [[IMP-a14bd483f253]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

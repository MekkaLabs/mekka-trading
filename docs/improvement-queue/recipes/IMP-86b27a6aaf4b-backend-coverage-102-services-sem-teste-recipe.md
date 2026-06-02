---
rec_id: "86b27a6aaf4b"
type: implementation-recipe
area: backend
impact: MEDIUM
generated_at: 2026-06-01T20:54:27
auto_generated: true
---

# Recipe IMP-86b27a6aaf4b — Backend coverage: 102 services sem teste

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `backend`
- **Impacto:** `MEDIUM`

## Descrição

102 services em `src/services/` não têm teste correspondente em `tests/`. Faltam: `agent_degradation_detector`, `agent_step_guard`, `alert_throttle_manager`, `analysis_prompt_cache`, `asset_classifier`, `auto_learning_scheduler`, `auto_signal_linter`, `backtest_benchmark`, … (+94).

## Por que importa

_(sem rationale)_

## Evidência

102 services sem tests/test_*.py

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-86b27a6aaf4b.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-86b27a6aaf4b`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-86b27a6aaf4b] Backend coverage: 102 services sem teste"
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
- [ ] Commit subject contém `[IMP-86b27a6aaf4b]`

## Notas relacionadas

- Brief original: [[IMP-86b27a6aaf4b]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

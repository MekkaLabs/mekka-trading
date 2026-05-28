---
rec_id: "f9fb870b0857"
type: implementation-recipe
area: risk_gates
impact: MEDIUM
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-f9fb870b0857 — Batman rejeita majoritariamente por 'max_trades_per_day'

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `risk_gates`
- **Impacto:** `MEDIUM`

## Descrição

De 8 rejeições no período, 'max_trades_per_day' domina (8×). Se for fricção de execução (não risco real), recalibrar o gate; se for risco real, ajustar a geração de sinal a montante.

## Por que importa

_(sem rationale)_

## Evidência

8 RISK_REJECTED; top motivo 'max_trades_per_day' = 8×.

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-f9fb870b0857.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-f9fb870b0857`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-f9fb870b0857] Batman rejeita majoritariamente por 'max_trades_per_day'"
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
- [ ] Commit subject contém `[IMP-f9fb870b0857]`

## Notas relacionadas

- Brief original: [[IMP-f9fb870b0857]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

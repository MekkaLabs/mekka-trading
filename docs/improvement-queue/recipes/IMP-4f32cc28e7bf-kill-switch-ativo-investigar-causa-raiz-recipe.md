---
rec_id: "4f32cc28e7bf"
type: implementation-recipe
area: risk
impact: HIGH
generated_at: 2026-05-27T19:04:11
auto_generated: true
---

# Recipe IMP-4f32cc28e7bf — Kill switch ATIVO — investigar causa raiz

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `risk`
- **Impacto:** `HIGH`

## Descrição

O kill switch está engatado agora. Trading está halted. Investigar o gatilho (drawdown/erro) antes de liberar.

## Por que importa

_(sem rationale)_

## Evidência

is_kill_switch_active()=True; 4 eventos de kill no período.

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-4f32cc28e7bf.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-4f32cc28e7bf`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-4f32cc28e7bf] Kill switch ATIVO — investigar causa raiz"
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
- [ ] Commit subject contém `[IMP-4f32cc28e7bf]`

## Notas relacionadas

- Brief original: [[IMP-4f32cc28e7bf]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

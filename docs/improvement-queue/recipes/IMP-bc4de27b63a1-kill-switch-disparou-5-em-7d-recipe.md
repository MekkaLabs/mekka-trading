---
rec_id: "bc4de27b63a1"
type: implementation-recipe
area: risk
impact: MEDIUM
generated_at: 2026-05-27T18:41:06
auto_generated: true
---

# Recipe IMP-bc4de27b63a1 — Kill switch disparou 5× em 7d

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `risk`
- **Impacto:** `MEDIUM`

## Descrição

Disparos repetidos do kill switch indicam fragilidade de risco ou thresholds mal calibrados. Revisar gatilhos e limites.

## Por que importa

_(sem rationale)_

## Evidência

5 eventos de kill switch no período.

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-bc4de27b63a1.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-bc4de27b63a1`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-bc4de27b63a1] Kill switch disparou 5× em 7d"
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
- [ ] Commit subject contém `[IMP-bc4de27b63a1]`

## Notas relacionadas

- Brief original: [[IMP-bc4de27b63a1]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

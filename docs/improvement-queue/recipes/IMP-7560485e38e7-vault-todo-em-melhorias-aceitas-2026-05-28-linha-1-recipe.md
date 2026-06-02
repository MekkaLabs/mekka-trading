---
rec_id: "7560485e38e7"
type: implementation-recipe
area: vault
impact: MEDIUM
generated_at: 2026-05-28T12:41:33
auto_generated: true
---

# Recipe IMP-7560485e38e7 — Vault: TODO em 'Melhorias Aceitas — 2026-05-28' (linha 154)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `vault`
- **Impacto:** `MEDIUM`

## Descrição

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: s os trades executados (pelo `side`). A nova query `list_recent_closed_trades()` foi adicionada ao repositório para suportar ambos".".

Origem: `60 - Daily/2026-05-28-improvements-accepted.md:154`. Considere transformar em story (ou marcar como resolvido).

## Por que importa

_(sem rationale)_

## Evidência

60 - Daily/2026-05-28-improvements-accepted.md:154 — TODO: s os trades executados (pelo `side`). A nova query `list_recent_closed_trades()` foi adicionada ao repositório par

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-7560485e38e7.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-7560485e38e7`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-7560485e38e7] Vault: TODO em 'Melhorias Aceitas — 2026-05-28' (linha 154)"
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
- [ ] Commit subject contém `[IMP-7560485e38e7]`

## Notas relacionadas

- Brief original: [[IMP-7560485e38e7]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

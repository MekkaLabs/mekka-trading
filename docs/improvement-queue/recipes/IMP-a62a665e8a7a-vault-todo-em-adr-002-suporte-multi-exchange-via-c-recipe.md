---
rec_id: "a62a665e8a7a"
type: implementation-recipe
area: architecture
impact: MEDIUM
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-a62a665e8a7a — Vault: TODO em 'ADR-002 — Suporte Multi-Exchange via CCXT' (linha 59)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `architecture`
- **Impacto:** `MEDIUM`

## Descrição

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: s os exchanges); algumas features avançadas (HL position close-on-trigger nativo) não mapeiam 1:1 na interface unificada — por isso HL continua usando SDK nativo.".

Origem: `30 - Resources/Decisoes Tecnicas/ADR-002 - Multi-Exchange via CCXT.md:59`. Considere transformar em story (ou marcar como resolvido).

## Por que importa

_(sem rationale)_

## Evidência

30 - Resources/Decisoes Tecnicas/ADR-002 - Multi-Exchange via CCXT.md:59 — TODO: s os exchanges); algumas features avançadas (HL position close-on-trigger nativo) não mapeiam 1:1 na interface uni

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-a62a665e8a7a.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-a62a665e8a7a`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-a62a665e8a7a] Vault: TODO em 'ADR-002 — Suporte Multi-Exchange via CCXT' (linha 59)"
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
- [ ] Commit subject contém `[IMP-a62a665e8a7a]`

## Notas relacionadas

- Brief original: [[IMP-a62a665e8a7a]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

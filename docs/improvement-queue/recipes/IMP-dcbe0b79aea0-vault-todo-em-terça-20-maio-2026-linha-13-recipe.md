---
rec_id: "dcbe0b79aea0"
type: implementation-recipe
area: vault
impact: MEDIUM
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-dcbe0b79aea0 — Vault: TODO em 'Terça, 20 Maio 2026' (linha 13)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `vault`
- **Impacto:** `MEDIUM`

## Descrição

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: o trabalho paralelo (codex M40 + nossa M22) na branch `main`, ligar Vision via Anthropic (que estava silenciado por bug ambiental), adicionar **Force Execute** como escape ha".

Origem: `60 - Daily/2026-05-20.md:13`. Considere transformar em story (ou marcar como resolvido).

## Por que importa

_(sem rationale)_

## Evidência

60 - Daily/2026-05-20.md:13 — TODO: o trabalho paralelo (codex M40 + nossa M22) na branch `main`, ligar Vision via Anthropic (que estava silenciado po

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-dcbe0b79aea0.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-dcbe0b79aea0`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-dcbe0b79aea0] Vault: TODO em 'Terça, 20 Maio 2026' (linha 13)"
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
- [ ] Commit subject contém `[IMP-dcbe0b79aea0]`

## Notas relacionadas

- Brief original: [[IMP-dcbe0b79aea0]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

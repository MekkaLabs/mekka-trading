---
rec_id: "7cceef332f5c"
type: implementation-recipe
area: vault
impact: MEDIUM
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-7cceef332f5c — Vault: TODO em 'Fluxo Automático e Versionamento' (linha 114)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `vault`
- **Impacto:** `MEDIUM`

## Descrição

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: `src/`, `tests/`, `docs/` (incluindo `docs/obsidian/`, exceto exclusões abaixo)".

Origem: `30 - Resources/Fluxo Automático e Versionamento.md:114`. Considere transformar em story (ou marcar como resolvido).

## Por que importa

_(sem rationale)_

## Evidência

30 - Resources/Fluxo Automático e Versionamento.md:114 — TODO: `src/`, `tests/`, `docs/` (incluindo `docs/obsidian/`, exceto exclusões abaixo)

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-7cceef332f5c.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-7cceef332f5c`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-7cceef332f5c] Vault: TODO em 'Fluxo Automático e Versionamento' (linha 114)"
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
- [ ] Commit subject contém `[IMP-7cceef332f5c]`

## Notas relacionadas

- Brief original: [[IMP-7cceef332f5c]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

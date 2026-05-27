---
rec_id: "d56f21960c2f"
type: implementation-recipe
area: research
impact: LOW
generated_at: 2026-05-27T19:04:11
auto_generated: true
---

# Recipe IMP-d56f21960c2f — Dependências desatualizadas (1)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `research`
- **Impacto:** `LOW`

## Descrição

Bibliotecas do stack atrás da última versão do PyPI. Atualizar em lote (com teste) reduz dívida e captura correções de segurança/bugs.

## Por que importa

_(sem rationale)_

## Evidência

openai 2.36.0→2.38.0

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-d56f21960c2f.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-d56f21960c2f`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-d56f21960c2f] Dependências desatualizadas (1)"
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
- [ ] Commit subject contém `[IMP-d56f21960c2f]`

## Notas relacionadas

- Brief original: [[IMP-d56f21960c2f]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

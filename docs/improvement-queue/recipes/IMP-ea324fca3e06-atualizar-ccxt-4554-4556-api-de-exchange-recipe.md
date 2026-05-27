---
rec_id: "ea324fca3e06"
type: implementation-recipe
area: research
impact: MEDIUM
generated_at: 2026-05-27T18:41:06
auto_generated: true
---

# Recipe IMP-ea324fca3e06 — Atualizar ccxt 4.5.54 → 4.5.56 (API de exchange)

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `research`
- **Impacto:** `MEDIUM`

## Descrição

`ccxt` está em 4.5.54; a última no PyPI é 4.5.56. Para um bot que opera ao vivo, um ccxt desatualizado pode ter suporte velho a endpoints/símbolos das exchanges (Binance/Bybit). Revisar changelog por breaking changes e atualizar com teste em testnet.

## Por que importa

_(sem rationale)_

## Evidência

PyPI: ccxt instalado 4.5.54, latest 4.5.56.

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-ea324fca3e06.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-ea324fca3e06`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-ea324fca3e06] Atualizar ccxt 4.5.54 → 4.5.56 (API de exchange)"
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
- [ ] Commit subject contém `[IMP-ea324fca3e06]`

## Notas relacionadas

- Brief original: [[IMP-ea324fca3e06]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

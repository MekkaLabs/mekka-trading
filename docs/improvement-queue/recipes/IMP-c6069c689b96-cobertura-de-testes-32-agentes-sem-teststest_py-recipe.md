---
rec_id: "c6069c689b96"
type: implementation-recipe
area: agents
impact: MEDIUM
generated_at: 2026-05-27T19:00:55
auto_generated: true
---

# Recipe IMP-c6069c689b96 — Cobertura de testes: 32 agentes sem `tests/test_*.py`

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `agents`
- **Impacto:** `MEDIUM`

## Descrição

32 agentes não têm arquivo de teste correspondente. Faltam: `agents_scanner.py`, `aquaman.py`, `backend_scanner.py`, `batman.py`, `beast.py`, `black_panther.py`, `code_auditor.py`, `cyclops.py`, … (+24 outros). Cada agente sem teste é risco silencioso — regressão só aparece em produção.

## Por que importa

_(sem rationale)_

## Evidência

32 agentes em src/agents/ sem teste em tests/

## Arquivos prováveis afetados

- _(nenhum detectado)_

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-c6069c689b96.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-c6069c689b96`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-c6069c689b96] Cobertura de testes: 32 agentes sem `tests/test_*.py`"
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
- [ ] Commit subject contém `[IMP-c6069c689b96]`

## Notas relacionadas

- Brief original: [[IMP-c6069c689b96]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

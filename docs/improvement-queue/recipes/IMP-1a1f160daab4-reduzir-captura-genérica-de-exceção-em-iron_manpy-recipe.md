---
rec_id: "1a1f160daab4"
type: implementation-recipe
area: agents
impact: LOW
generated_at: 2026-05-28T12:39:52
auto_generated: true
---

# Recipe IMP-1a1f160daab4 — Reduzir captura genérica de exceção em iron_man.py

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `agents`
- **Impacto:** `LOW`

## Descrição

`src/agents/iron_man.py` tem **6 `except Exception`** (sendo 0 truly-bare). Captura genérica dificulta diagnóstico — substituir por tipos específicos onde possível, marcar `# noqa: BLE001` onde o try-broad é intencional.

## Por que importa

_(sem rationale)_

## Evidência

src/agents/iron_man.py: 0 bare + 6 broad except = 6

## Arquivos prováveis afetados

- `src/agents/iron_man.py`

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-1a1f160daab4.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-1a1f160daab4`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-1a1f160daab4] Reduzir captura genérica de exceção em iron_man.py"
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
- [ ] Commit subject contém `[IMP-1a1f160daab4]`

## Notas relacionadas

- Brief original: [[IMP-1a1f160daab4]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]

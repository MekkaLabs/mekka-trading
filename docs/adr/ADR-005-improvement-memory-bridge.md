# ADR-005 — Bridge Improvement ↔ Memory + Memory Hub + UX Melhorias

**Status:** Aceito (2026-05-27)
**Autor:** sessão Claude Code

## Contexto

Investigação revelou 3 problemas concorrentes no loop de melhoria contínua:

1. **25 IMPs aprovadas paradas em `queued`** — `sync_imp_commits.py` existe
   mas depende de tag `[IMP-xxxxxxxx]` nos commits. Operador + Claude Code
   não usaram a tag. Apenas 9 commits do histórico têm a tag, contra 51
   IMPs registradas.
2. **Sem visibilidade unificada das 6 camadas de memória** — operator não
   tem como saber se Agent Memory está sendo populada, quantas Decision
   Records existem, etc.
3. **Página /Melhorias poluída** — múltiplos filtros + tabs + Mentor + KPI
   Sage + Mainnet + Histórico tudo aberto ao mesmo tempo. Difícil decidir
   o que olhar primeiro.

## Decisão

### 1. Service (não agente) `improvement_memory_bridge.py`

NÃO criei novo agente. Bridge é operacional, sem agência decisória — quem
decide é o operator via UI/CLI.

Funções principais:
- `on_improvement_accepted(rec_id)` → snapshot Sage BEFORE
- `on_improvement_pr_merged(rec_id)` → snapshot Sage AFTER
- `find_match_candidates(rec_id)` → heurística git log + IMP brief
- `auto_reconcile_dry_run()` → relatório das paradas
- `mark_resolved_manual(rec_id, commit_sha)` → operator confirma match
- `memory_snapshot()` → agrega 6 camadas

Persistência: `data/improvement_memory_bridge.json` (gitignored runtime).

### 2. Endpoints novos

- `GET /api/memory/snapshot` — métricas das 6 camadas
- `GET /api/improvements/queued` — IMPs paradas + matches sugeridos
- `POST /api/improvements/reconcile-manual` — operator aplica match

### 3. UI

- **Memory Hub** (`memory_hub.js`) — card no design ciano abaixo do
  Atividade do Segundo Cérebro. Mostra 6 layers, badges ON/OFF, métricas.
- **Improvements v2** (`improvements_v2.js`) — sobrecamada ao app.js
  existente. Adiciona:
  - Stats bar (6 contadores grandes)
  - Tab nova "Paradas" que lista IMPs queued + matches sugeridos +
    botão "Aplicar" (chama reconcile-manual)
  - Filtros secundários colapsados (`<details>`)
  - Mentor/KPI/Mainnet colapsados em "Sinais do sistema"
- CSS adicional dentro do `<section>` (escopado por `.improvements-v2`)

### 4. CLI `scripts/imp_reconcile.py`

3 subcomandos:
- `dry-run` — relatório das paradas com matches
- `show <rec_id>` — top candidatos pra uma IMP
- `apply <rec_id> <commit_sha>` — aplica match no pr_tracker

### 5. Pre-push hook

Novo: `scripts/git-hooks/pre-push-imp-sync` → roda `sync_imp_commits.py`
silent antes de cada push. Bypass: `SKIP_IMP_SYNC=1 git push`.
Instala via `scripts/install-git-hooks.sh` (atualizado).

## Consequências

### Positivas
- Loop fechado: ACCEPT → snapshot Sage → DEV → MERGE → snapshot Sage →
  attribution real do impacto da melhoria.
- 25 IMPs paradas têm caminho UI/CLI para reconciliação.
- Operator vê estado real das 6 camadas de memória.
- Página /Melhorias respira: stats no topo, filtros somem por default.

### Riscos
- Heurística de match (palavras-chave + paths) tem falsos positivos —
  por isso "aplicar" é manual com confirm() do operator.
- `memory_snapshot` agrega 6 camadas a cada 10s (cache TTL); pode
  causar I/O em cenários extremos — mitigação: cache.
- Pre-push hook depende de `python3` no PATH; fail-silent se não
  encontrar.

### Validação futura
- Próximo push de @devops deve disparar pre-push hook → IMPs com
  `[IMP-xxxxxxxx]` se reconciliarem automaticamente.
- Após 7d com IMP merged, snapshot AFTER deve aparecer no
  `improvement_memory_bridge.json`.

## Convenção operacional (importante)

Daqui pra frente, **todo commit que resolve uma IMP** deve incluir
`[IMP-xxxxxxxx]` no subject (12 hex chars). Exemplo:

```
git commit -m "feat(ui): redesign Central de Melhorias [IMP-d56f21960c2f]"
```

Sem o tag, a melhoria fica órfã no tracker até reconciliação manual.

## Referências
- `src/services/improvement_memory_bridge.py` (esta sessão)
- `src/services/pr_tracker.py` (preexistente)
- `src/agents/sage.py` (preexistente, fornece snapshot)
- `scripts/sync_imp_commits.py` (preexistente, reconcilia via tag)
- `scripts/imp_reconcile.py` (esta sessão, reconcilia sem tag)
- ADR-004 — Second Brain Architecture

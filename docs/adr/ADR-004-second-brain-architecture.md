# ADR-004 — Arquitetura do Segundo Cérebro: vault, AIOX Core, squads, Prometheus

**Status:** Aceito (2026-05-26)
**Autor:** sessão Claude Code (consolidação)
**Contexto:** Investigação revelou que muito do sistema "Segundo Cérebro" já existe
mas estava sub-documentado.

## Contexto

A missão de evoluir o segundo cérebro do projeto exigiu validar 4 premissas:

1. O vault `mekka-trading-obsidian` é a fonte de dados oficial do Segundo Cérebro?
2. AIOX Core está integrado ao projeto?
3. Squads (anexados no `squads.zip` ou já presentes) trazem capacidades novas?
4. Prometheus deve ser um agente permanente do sistema?

## Decisão

### 1. Vault como fonte do Segundo Cérebro: **CONFIRMADO**

**Evidências:**
- Vault existe: `~/Documents/mekka-trading-obsidian` (168 .md)
- `src/agents/jean_grey.py:300` define `build_graph()` que indexa o vault
- `src/dashboard/server.py:6756` expõe `GET /api/jean/graph` (link graph)
- `src/dashboard/static/index.html:466` renderiza `#sec-neural-graph` via ForceGraph
- `src/dashboard/static/app.js:610` consome o endpoint
- Smoke test (2026-05-26): 103 nodes, 270 links — funcional sem regressão
- `src/services/vault_context.py` (Story #72) leitura read-only, opt-in
- `src/dashboard/handlers/second_brain_activity.py` (criado nesta sessão)
  expõe atividade real (arquivos modificados + estado do Prometheus)

**Diretórios incluídos:** todo `*.md` exceto `.obsidian/` e `.trash/`.
**Excluídos por segurança:** `.env*`, qualquer `.json` do `.obsidian/`,
binários, logs.

### 2. AIOX Core: **JÁ INSTALADO**

Localização: `aiox-core/` (~30 pastas: `bin`, `docs`, `packages`, `squads`,
`tests`, `.aiox-core/` interno com `cli`, `core`, `monitor`, `hooks`, etc.).

`package.json` raiz declara: `"description": "AI-Orchestrated Autonomous
Trading Operating System powered by AIOX Core and Hyperliquid"`.

**Decisão operacional:** **não reinstalar, não migrar, não atualizar
versão.** O framework está integrado conceitualmente; nenhuma chamada CLI
direta foi feita nesta sessão. Para evoluções futuras que precisem usar
ferramentas AIOX, usar `aiox-core/bin/` ou `npm run` do `aiox-core/package.json`.

### 3. Squads: **13 já presentes, anexo IDÊNTICO**

`squads/` contém 13 squads do framework AIOX: `_example`, `advisory-board`,
`brand-squad`, `c-level-squad`, `claude-code-mastery`, `copy-squad`,
`cybersecurity`, `data-squad`, `design-squad`, `hormozi-squad`, `movement`,
`storytelling`, `traffic-masters`.

Cada squad tem `squad.yaml` (declaração AIOX v4.0), `agents/*.md`,
`tasks/*.md`, `workflows/*.yaml`, `data/*.yaml`, `checklists/*.md`.

Adicionalmente, `squads/squads.ts` define 3 squads do **runtime Mekka**:
`alpha-risk-command`, `hyperliquid-mock-ops`, `market-intel-lab` (mapeando
para os super-heróis Python).

**Comparação com `/Users/gustavovicente/Downloads/squads.zip`:**
o conteúdo é **idêntico** (diff = só `squads.ts` que falta no zip).
**Decisão: não importar o zip** — não traz nada novo.

### 4. Prometheus: **AGENTE PERMANENTE**

Implementado em duas camadas:
- **Offline / dev tool** (`src/prompt_engineering/`): extractor, auditor
  P.R.O.M.P.T., catálogo, cross-provider adapter, CLI.
- **Runtime agent** (`src/agents/prometheus.py`): `BaseAgent` observer
  que consome `MekkaEventBus`, dedup SHA-256, throttle sliding window,
  fail-silent, opt-in via `PROMETHEUS_AGENT_ENABLED=true`.

**Nova capacidade desta sessão:** `src/services/prometheus_vault_writer.py`
persiste aprendizados em `~/Documents/mekka-trading-obsidian/60 - Daily/{date}-prometheus-learnings.md`
com:
- Opt-in via `PROMETHEUS_VAULT_WRITER_ENABLED=true`
- Throttle 6 escritas/hora (configurável)
- Atomic write (`os.replace`)
- Sanitização anti-secret (whitelist de chaves)
- Fail-silent

## Consequências

### Positivas
- Documentação canônica do que existe versus o que foi acrescentado.
- Fim da confusão `/aios` vs `.aios-core` vs `aiox-core/`.
- Política de squads.zip explícita (não importar — duplicaria).
- Prometheus tem caminho rastreável de aprendizado → vault.

### Riscos
- Pre-existência mascara que `aiox-core/` não é invocado pelo runtime
  Python — só serve como referência arquitetural. Operador deve decidir
  se ativá-lo (via npm scripts).
- `PROMETHEUS_VAULT_WRITER_ENABLED` em produção criará 1 arquivo `.md`
  por dia em `60 - Daily/`. Cresce ~365 arquivos/ano. Aceitável.

### Validação futura
- Quando Prometheus rodar em produção com vault writer ON, conferir que
  o arquivo do dia recebe blocos de learning a cada `cycle.end`.
- Conferir que o conteúdo passa pela sanitização (sem chaves vazadas).

## Referências
- ADR-001 a ADR-003 (vault history em `docs/obsidian/30 - Resources/Decisoes Tecnicas/`)
- `src/prompt_engineering/` (sessões anteriores)
- `src/agents/prometheus.py` (sessões anteriores)
- `src/services/prometheus_vault_writer.py` (esta sessão)
- `docs/obsidian/30 - Resources/Fontes de Verdade.md`
- `docs/obsidian/30 - Resources/Fluxo Automático e Versionamento.md`

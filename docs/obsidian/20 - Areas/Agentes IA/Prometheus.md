---
title: Prometheus — Prompt Engineering Operator
type: agent
layer: dev-ops
status: ativo
tags: [agente, prompt-engineering, prometheus, qa, mekka-trading]
created: 2026-05-26
updated: 2026-05-26
---

# Prometheus

> **Categoria:** Agente de dev/qualidade — **NÃO participa do loop de trading**
> **Módulo:** [[src/prompt_engineering]] (não em `src/agents/` por design)
> **Interface humana:** `scripts/prometheus_cli.py`
> **Persistência:** opt-in em `data/prompts/catalog.json`

## Identidade

Prometheus é o **arquiteto/auditor de prompts** do Mekka. Opera 100% offline,
de forma determinística (sem chamadas LLM), e nunca executa decisão de trade.
Inspirado no agente de mesmo nome em `prompt-architect-pro-global.md`.

## Responsabilidades

1. **Extrair** prompts hardcoded de `src/agents/*.py` via AST.
2. **Auditar** segundo framework **P.R.O.M.P.T.** (Purpose, Role, Output,
   Method, Pitfalls, Test).
3. **Versionar** com fingerprint SHA-256 (mesmo formato do `prompt_registry`
   existente).
4. **Catalogar** opcionalmente em `data/prompts/catalog.json` (opt-in via
   `PROMETHEUS_CATALOG_ENABLED=true`).
5. **Reportar** scorecards `/40` legíveis (CLI texto) ou JSON (para CI).

## Scorecard (4 dimensões × 10)

| Dimensão | O que mede |
|---|---|
| **CLARITY** | Role + Purpose + Output declarados |
| **HALLUCINATION_RISK** | 10 = sem risco, 0 = alto; penaliza linguagem vaga, premia pitfalls + schema strict |
| **TESTABILITY** | Existe exemplo, critério de aceite, bloco de código? |
| **PROMPT_COVERAGE** | Presença dos 6 componentes P.R.O.M.P.T. |

**Etiquetas de health:**
- 32-40: EXCELLENT
- 24-31: GOOD
- 16-23: NEEDS_WORK
- 0-15: CRITICAL

## Comandos CLI

```bash
# Auditar um arquivo
python scripts/prometheus_cli.py audit src/agents/vision.py

# Listar todos os prompts em src/agents/
python scripts/prometheus_cli.py scan-agents

# Auditar texto via stdin
echo "Você é..." | python scripts/prometheus_cli.py audit-text

# Registrar (catálogo opt-in)
PROMETHEUS_CATALOG_ENABLED=true python scripts/prometheus_cli.py register src/agents/vision.py

# Listar catálogo
PROMETHEUS_CATALOG_ENABLED=true python scripts/prometheus_cli.py list

# JSON output para qualquer comando
python scripts/prometheus_cli.py audit src/agents/vision.py --json
```

## Baseline auditado (2026-05-26)

| Prompt | File:Line | Score |
|---|---|---|
| `vision_system_prompt` | vision.py:44 | **33/40 EXCELLENT** |
| `vision_pre_reasoning_system` | vision.py:106 | **26/40 GOOD** |
| `vision_critic_system_prompt` | vision_critic.py:40 | (rodar para medir) |
| `vision_moa_orchestrator` | vision_moa.py:52 | (rodar para medir) |
| `nick_fury_msg` | nick_fury.py:324 | (rodar para medir) |
| `mekka_rationale_*` (3) | mekka.py:364,370,376 | (rodar para medir) |

## Integração com sistema existente

| Componente Mekka | Como Prometheus se conecta |
|---|---|
| `src/services/prompt_registry.py` | Função aditiva `register_prompt_for_audit()` — **não altera** `prompt_version()` existente; bridge opt-in via env var |
| `src/agents/vision.py` (e demais) | **Não importa Prometheus.** Test de isolamento garante invariante |
| `src/services/analysis_prompt_cache.py` | Não acoplado — Prometheus opera sobre o source code, não o runtime |
| `llm_client.py` | Lista de modelos compatíveis é puxada para `DEFAULT_COMPATIBLE_MODELS` |
| CI (`.github/workflows/`) | Futuro: workflow rodando `prometheus_cli audit` em PRs que tocam `src/agents/` |

## Garantias de segurança

1. **Determinístico.** Auditor é Python puro; mesma entrada → mesma saída.
2. **Sem chamadas LLM.** Zero custo, zero latência, zero risco de leak.
3. **Sem efeito no trading.** Trading loop não importa o módulo; teste
   `TestIsolation` confirma e bloqueia regressão.
4. **Opt-in para escrita.** Catálogo só é tocado com env var explícita.
5. **Graceful degradation.** Se módulo `prompt_engineering` falhar ao
   importar, `register_prompt_for_audit()` retorna o fingerprint normal.

## Testes

`tests/test_prompt_engineering.py` — 27 testes em 6 classes:
- TestExtractor (7): AST, role detection, edge cases
- TestAuditor (5): scorecard determinístico, thresholds
- TestCatalog (5): persistence, upsert, corruption resilience
- TestPrometheus (4): orchestration, opt-in
- TestPromptRegistryBridge (4): API preservada + fallback
- TestIsolation (2): invariante de não-acoplamento com `src/agents/`

## Limitações conhecidas

- AST não captura prompts construídos via concatenação ou f-string
  complexa — apenas string literals em assignments diretos.
- Heurísticas de role são gramaticais — `_SETTINGS_PROMPT` viraria
  `system` (substring match).
- Score é informativo. Score baixo NÃO bloqueia commit ou deploy.

## Roadmap

1. **Cross-provider adapter.** Gerar variantes de um prompt otimizadas
   para Anthropic vs OpenAI, registrar em catálogo com modelo compatível.
2. **CI integration.** Workflow `.github/workflows/prometheus-audit.yml`
   que comenta scorecard em PRs tocando `src/agents/`.
3. **Critic loop generalizado.** Padrão Vision Critic aplicado a outros
   agentes via prompts gerados pelo Prometheus.

## Notas relacionadas

- [[Vision]]
- [[Vision Critic]]
- [[Fontes de Verdade]]
- [[Fluxo Automático e Versionamento]]

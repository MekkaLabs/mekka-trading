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

## Modo runtime (agente permanente — opt-in)

Além da CLI offline, Prometheus existe como **`BaseAgent` runtime**
em `src/agents/prometheus.py`. Quando habilitado via
`PROMETHEUS_AGENT_ENABLED=true`, ele:

- Subscreve aos topics `vision.signal`, `agent.error`, `agent.timeout`,
  `cycle.end` do [[event_bus]] (Story 136 — MekkaEventBus).
- Mantém buffers `recent_observations` e `recent_learnings` em memória
  (deque com cap 500 e 100 respectivamente).
- Publica `prometheus.observation` e `prometheus.learning` no bus.

**Proteções obrigatórias (todas testadas):**
- **Dedup** por SHA-256 dos campos discriminativos em janela
  `PROMETHEUS_DEDUP_WINDOW_S` (default 60s).
- **Throttle**: `PROMETHEUS_MAX_OBS_PER_MIN` (default 60) e
  `PROMETHEUS_MAX_LEARNINGS_PER_HOUR` (default 12).
- **Fail-silent**: exceções em handlers nunca propagam (logs DEBUG).
- **Opt-in**: sem env var, `get_prometheus_agent()` retorna `None` —
  zero overhead.
- **Observer-only**: teste de isolamento garante que nenhum agente
  Layer 1-3 importe `src/agents/prometheus.py`.

### Lifecycle típico

```python
from src.agents.prometheus import start_prometheus_agent

# Em startup (run.py / main.py):
agent = await start_prometheus_agent()  # None se desabilitado

# ... pipeline rola ...

# Em shutdown:
if agent:
    await agent.unsubscribe()
```

### Dashboard

O endpoint `GET /api/second-brain/activity` consome
`Prometheus.snapshot()` e expõe no novo módulo
"Atividade do Segundo Cérebro" (Frontend: `second_brain_activity.js`).
Polling controlado de 30s; sem WebSocket inventado.

## CI workflow

`.github/workflows/prometheus-audit.yml` roda em PRs/push para main que
tocam `src/agents/`. Comenta scorecard /40 por prompt no PR (informativo,
não bloqueia merge).

## Cross-provider adapter

`src/prompt_engineering/adapter.py` traduz prompts entre OpenAI e
Anthropic:
- `adapt_to_anthropic(text)` — converte cabeçalhos em tags XML
  semânticas (`<role>`, `<output_format>`, `<method>`, etc.)
- `adapt_to_openai(text)` — remove tags XML e reforça
  "Return ONLY a single JSON object" quando há schema inline.

100% determinístico, sem chamada LLM.

## Roadmap

1. **Critic loop generalizado.** Aplicar padrão Vision Critic a outros
   agentes via prompts gerados pelo Prometheus.
2. **Persistência de aprendizados no vault.** Hook do Prometheus que
   escreve `60 - Daily/{date}-prometheus-learnings.md` quando
   `learnings_emitted >= N`.
3. **Catálogo cross-provider versionado.** Cada `PromptRecord` ter
   variants[] com fingerprints separados por provider.

## Notas relacionadas

- [[Vision]]
- [[Vision Critic]]
- [[Fontes de Verdade]]
- [[Fluxo Automático e Versionamento]]

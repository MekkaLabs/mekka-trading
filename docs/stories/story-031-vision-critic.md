# Story 031 — Vision Critic

## Context

Vision (Story 025) é um único call LLM por símbolo. Em produção real,
um único LLM ocasionalmente alucina ou racionaliza decisões caras
(ex: aceitar trade contra anomaly). Story 031 adiciona um
**second-look** opcional — Vision Critic — que revisa cada
TradingSignal contra a mesma MarketAnalysis e pode endossar, emendar
(reduzindo risco), ou rejeitar (downgrade para HOLD).

Toggle off por default. Custo: ~1 chamada extra de OpenAI por
símbolo por cycle quando ligado.

## Goal

Cravar safety net LLM-based opcional que reduz alucinações de
decisão sem inflar latência ou custo até o operador estar pronto
para o trade-off.

## Scope Delivered

### Settings (2 fields novos)

- `vision_critic_enabled: bool = False` — master toggle.
- `vision_critic_min_disagreement: float = 0.30` — confidence delta
  threshold abaixo do qual AMEND/REJECT degradam para ENDORSE.

### Models novos (`src/models/critique.py`)

- **`CritiqueAction`** enum — `ENDORSE / AMEND / REJECT`.
- **`VisionCritique`** Pydantic — schema_version, timestamp, symbol,
  action, confidence_delta (0–1), 4 amended_* opcionais (size_pct,
  leverage, stop_loss, take_profit), reasoning, fallback flag.
- `is_actionable()` property + `summary()` + `to_audit_payload()`.

### Vision Critic agent (`src/agents/vision_critic.py`)

312 linhas. Padrão alinhado a Vision (try/except ModuleNotFoundError
para openai, fallback path defensivo).

- **Bypass de HOLD**: signals HOLD não passam pelo LLM; ENDORSE
  imediato (nada a override).
- **Prompt engineering** dedicado em `_SYSTEM_PROMPT` — princípios
  conservadores: ENDORSE quando análise sustenta, AMEND **só com
  smaller/lower/tighter/closer**, REJECT em anomalias / liquidez
  pobre / sinais conflitantes.
- **Disagreement floor**: critique com `confidence_delta <
  vision_critic_min_disagreement` é rebaixada para ENDORSE — pequenos
  desacordos não valem o overhead de override.
- **Safer-only filter**: `_coerce_amended_*` rejeita qualquer
  override que aumente risco:
  - `amended_size_pct > original` → descartado
  - `amended_leverage > original` → descartado
  - SL mais largo (mais distante de entry) → descartado
  - TP mais distante de entry → descartado
- **Fallback ENDORSE** em qualquer falha (timeout, rate limit, parse,
  schema, openai não instalada). `fallback=True` no audit.

### `apply_critique(signal, critique) -> TradingSignal`

Função pura no mesmo módulo:
- ENDORSE → retorna signal original sem mudança
- REJECT → retorna HOLD com `metadata.critic_rejected=True` e
  `critic_reason`. Geometria SL/TP fabricada para passar validator.
- AMEND → retorna nova TradingSignal com fields safer-only aplicados,
  `metadata.critic_amended=True`.

### Wire em Nick Fury (`_cycle_for_symbol`)

Inserido entre Vision e Batman (passo 2b):
1. Se `settings.vision_critic_enabled` → roda Critic.
2. Loga `CRITIQUE_<ACTION>` no audit_log com payload completo.
3. Se `critique.is_actionable()` → aplica via `apply_critique`.
4. Salva o signal **pós-critique** em `signals` table (Batman vê o
   signal possivelmente modificado).
5. try/except envolvendo o critic step — falha do critic NUNCA
   quebra o cycle.

### Registry (`src/agents/__init__.py`)

`VisionCritic` adicionado em Layer 2 — Strategy.

### Pytest fase 8 — 15 testes (`tests/test_phase8_vision_critic.py`)

VisionCritic puro (10):
- HOLD bypass (no LLM call)
- LLM ENDORSE preserved
- LLM REJECT honored above threshold
- LLM AMEND honored above threshold (size/leverage/SL/TP applied)
- small delta downgrades to ENDORSE
- fallback on LLM error
- fallback on invalid JSON
- safer-only filter rejects bigger size
- safer-only filter rejects bigger leverage
- safer-only filter rejects wider SL

apply_critique (3):
- ENDORSE returns identical signal (object identity)
- REJECT returns HOLD with critic_rejected metadata
- AMEND applies size/leverage/SL/TP with critic_amended metadata

Nick Fury wired (2):
- enabled=False → critic.run never called
- enabled=True → critic.run called, REJECT downgrades signal,
  CRITIQUE_REJECT event audited, signal saved is HOLD

## Hard Rules Mantidas

- **Off por default.** `vision_critic_enabled=False` em settings.
  Operador deve ligar explicitamente após 2 semanas de paper estável.
- **Critic nunca aumenta risco.** Safer-only filter aplica em
  amended_size_pct, amended_leverage, amended_stop_loss,
  amended_take_profit.
- **Critic nunca quebra o cycle.** Try/except envolvendo o step;
  fallback ENDORSE preserva o signal original.
- **Critic não chama exchange.** Read-only sobre análise + signal.
- **Sem mudança em Vision/Batman/Iron Man.**

## Pipeline Atualizado

```
NickFury._cycle_for_symbol
  → ProfessorX.run(symbol) → MarketAnalysis
  → Vision.run(analysis) → TradingSignal v1
  → if settings.vision_critic_enabled:        ← NOVO
        VisionCritic.run(analysis, v1) → VisionCritique
        log_event(CRITIQUE_<ACTION>)
        if critique.is_actionable():
            v2 = apply_critique(v1, critique)
            signal = v2
  → save_signal(signal)
  → Batman.run(signal, ...) → RiskApproval
  → IronMan.run(...) → ExecutionResult
  → DailyPnLWriter.record_cycle(...)
```

## Acceptance

- [x] Settings novos default-conservadores (off, threshold 0.30).
- [x] VisionCritic instancia sem dependência opcional (lazy openai).
- [x] HOLD bypass — nenhum LLM call.
- [x] Fallback ENDORSE em todos os caminhos defensivos.
- [x] Safer-only filter para todos os 4 amended_* fields.
- [x] Disagreement floor rebaixa AMEND/REJECT para ENDORSE.
- [x] apply_critique pura (sem side effects).
- [x] Nick Fury bypassa critic quando disabled.
- [x] Nick Fury aplica critique e audita quando enabled.
- [x] 15 testes em `tests/test_phase8_vision_critic.py`.
- [x] Tests legados das fases 2/3/4 não tocados (critic só roda
      quando enabled, default off).

## Riscos Conhecidos

- **Dobra custo OpenAI** quando ligado. Mitigação: ligar só após
  paper-trading estável, monitorar custo por dia via OpenAI dashboard.
- **Latency penalty ~1-2s** por símbolo por cycle. Não afeta o ciclo
  4h main, mas pode ser sensível em ciclos curtos futuros (Flash).
- **Critic e Vision usam mesmo modelo** — `settings.openai_model`.
  Em produção real, vale considerar modelo mais barato (gpt-4o-mini)
  para o critic. Story futura.
- **Sem bypass para sinais já HOLD via fallback de Vision.** Hoje
  HOLD bypass cobre signal.action=HOLD; mas se Vision retornar HOLD
  por fallback (`metadata.fallback=True`), ainda passa pelo critic
  flow (que retorna ENDORSE imediato). Aceitável.

## What's Next (Story 032 — Audit Single Source of Truth)

Conforme `AUTO-CONTINUE-PLAN.md § 3`:
- 3.1 — Decisão arquitetural humana: SQLite ganha como fonte única.
- 3.2 — Shim TS → SQLite via better-sqlite3.
- 3.3 — Marcar `memory/*.ndjson` como deprecated.
- 3.4 — Tests cross-runtime confirmando paridade.

## Files Changed

Novos:
- `src/models/critique.py` (94 linhas)
- `src/agents/vision_critic.py` (312 linhas)
- `tests/test_phase8_vision_critic.py` (392 linhas)
- `docs/stories/story-031-vision-critic.md` (este)

Editados (aditivos):
- `src/config/settings.py` — 2 fields novos
- `src/agents/nick_fury.py` — instancia critic + step 2b no cycle
- `src/agents/__init__.py` — registry + Layer 2 docstring
- `docs/stories/INDEX.md` — Story 031 entregue
- `AGENTS.md` — VisionCritic em Layer 2
- `docs/HANDOFF.md` — Story 031 fechada, próxima 032
- `docs/AUTO-CONTINUE-PLAN.md` — § 2 marcada concluída

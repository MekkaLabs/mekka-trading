# ADR-003 — Vision Structured Output First (Pydantic-first)

**Status:** ACCEPTED — entregue (Story 250)  
**Date:** 2026-05-19  
**Decision Drivers:** confiabilidade de parse, segurança paper-first, redução de falhas por JSON inválido, fallback seguro

---

## Context

O Vision é o único componente LLM central do pipeline: ele transforma `MarketAnalysis` em um
`TradingSignal`. Historicamente, esse passo dependia de:

- geração de JSON “na marra” via prompt;
- extração do JSON via regex/heurísticas (`_extract_json`);
- validação/normalização posterior (`_build_signal`).

Mesmo com guardrails, esse fluxo falha em casos comuns (code fences, vírgulas a mais, campos
faltando, tipos incorretos). Como o sistema é paper-first e risk-first, qualquer falha deve
resultar em **HOLD** sem quebrar o ciclo — mas ainda assim isso gera:

- latência adicional (retries),
- ruído de logs,
- maior incidência de fallbacks.

## Decision

Adotar **structured output first** no Vision:

- Definir um schema Pydantic explícito para o payload do Vision (`TradingSignalOutput`).
- Tentar obter resposta estruturada do provider (quando suportado) e validar via Pydantic.
- Se structured output falhar/indisponível, cair para o **path clássico** (raw JSON) **sem regressão**.
- Se ambos falharem, retornar `HOLD` via fallback seguro.

## Considered Options

### Option A — Apenas prompt + JSON manual (status quo)

- **Pros:** compatível com qualquer provider.
- **Cons:** maior taxa de falha de parse; exige heurísticas; mais fallbacks.

### Option B — Structured output first + fallback clássico (decisão)

- **Pros:** reduz falhas; validação forte; mantém compatibilidade; rollback zero.
- **Cons:** depende de suporte do provider; precisa manter dois caminhos.

### Option C — Tool/function calling obrigatório

- **Pros:** também estruturado.
- **Cons:** muda a arquitetura do call; exige contrato e tool schema mais rígidos; risco de regressão maior.

## Consequences

### Positivas

- Menos falhas de parse e menos HOLD por ruído de JSON.
- Saída mais previsível para Batman (risk gate determinístico).
- Base para métricas: structured success rate vs fallback rate.

### Negativas / Riscos

- Manter “dois caminhos” exige disciplina de testes.
- Providers sem structured output continuam dependendo do path clássico.

## Follow-ups

- Logar counters (structured_success / structured_fallback / hard_fallback_hold) no audit trail.
- Expor no dashboard e no `/gates`/`/status` (se/when aplicável).


# ADR-001 — Audit Log Single Source of Truth

**Status:** IN PROGRESS — Option C entregue (Story 032), Option A shim entregue (Story 032b). Option A ativável com `npm install better-sqlite3`.
**Date:** 2026-05-08
**Decision Drivers:** observability, dashboard correctness, mainnet readiness

---

## Context

Hoje convivem dois caminhos de auditoria:

| Caminho | Localização | Quem escreve | Quem lê |
| ------- | ----------- | ------------ | ------- |
| TS Megazord | `memory/*.events.ndjson` + `memory/*.audits.ndjson` | TS runtime, ops alerting (Stories 002–024) | TS replay CLIs |
| Python pipeline | `data/mekka_trading.db` table `audit_log` | Nick Fury, Wolverine, Vision Critic, Daily PnL Writer (Stories 025–031) | Dashboard, Batman drawdown read |

Resultado: ao depurar um incidente, o operador (ou Deadpool no futuro)
precisa cruzar dois formatos com timestamps separados, IDs separados,
schemas diferentes. **Nenhum lado é fonte única**, e ambos divergem
silenciosamente.

Isso bloqueia:
- Forensics confiável durante o paper trading.
- Replay end-to-end em uma timeline única.
- Dashboard mostrando o pipeline TS+Python como um sistema só.
- Mainnet readiness — incident playbook precisa de UM lugar para olhar.

## Decision Drivers

1. **Reversibilidade** — qualquer mudança deve ser desfazível por
   ≥ 1 milestone (não quebrar TS legado).
2. **Pacing pedagógico** — Stories 002–024 já entregaram NDJSON
   como contrato. Removê-lo agora violaria a regra de "não acelerar
   além da etapa atual".
3. **Defesa em profundidade** — kill switch e audit não podem
   depender de um único arquivo desavortável.
4. **Custo cognitivo da próxima IA** — qualquer agente futuro deve
   ter UM endpoint óbvio para ler.

## Considered Options

### Option A — SQLite ganha, TS escreve via shim, NDJSON deprecated

- TS continua escrevendo NDJSON, mas tambem chama um shim
  `observability/sqlite-mirror.ts` que duplica em SQLite via
  `better-sqlite3`.
- Dashboard e qualquer leitor novo lê de SQLite.
- NDJSON marcado deprecated após 1 milestone; remoção dos writes
  TS é uma story posterior.
- **Pros:** SQL queries para filtragem, índices baratos, dashboard
  já usa SQLite, persistence layer Python já existe.
- **Cons:** TS precisa de dep nova (`better-sqlite3`), shim adiciona
  ~100 linhas TS, possíveis race conditions entre dois writers no
  mesmo arquivo SQLite.

### Option B — NDJSON unificado, SQLite vira mirror Python→NDJSON

- Inverter: NDJSON é fonte única, Python escreve cópia em
  `memory/python.audit.ndjson` (ou stream para o mesmo arquivo).
- Dashboard lê NDJSON.
- **Pros:** zero dep nova, append-only é seguro contra corrupção,
  preserva o trabalho das Stories 002–024.
- **Cons:** queries em NDJSON exigem scan linear, dashboard tem
  que reescrever leitor, perdemos `Repository.get_today_drawdown_pct`
  + `count_trades_today` que dependem de SQL. Drawdown leitura
  vira O(N).

### Option C — Reader unificado lê de ambos, writes ficam como estão

- Não muda comportamento de escrita.
- Cria uma camada de leitura (`UnifiedAuditReader`) que combina
  events de SQLite + NDJSON, deduplica por (timestamp, agent, event,
  message), ordena cronologicamente.
- Dashboard e novos consumers lêem por essa camada.
- **Pros:** zero risco para TS legado, totalmente reversível,
  pode ser implementado 100% em Python sem tocar TS, marca o
  caminho para Option A no futuro.
- **Cons:** não resolve drift de schema de longo prazo, mantém os
  dois lados, é solução transitória.

## Decision

**Adotar Option C (reader unificado) AGORA, com migração para
Option A planejada como Story TS futura quando o operador estiver
em ambiente com `npm install` testado.**

Razão: Option A é a melhor solução final, mas exige tocar TS
runtime. O ambiente atual de IA não tem garantias de rodar `npm
test` confiavelmente para validar o shim. Forçar Option A agora
violaria "Não quebrar funcionalidades existentes" da MEKKA-DEV §2.

Option C é o **stepping stone seguro**: entrega o valor imediato
de "uma timeline para o operador", deixa o caminho aberto para A,
e não cria dívida técnica nova.

Option B é descartada porque sacrifica capacidades já entregues
(SQL queries do Repository) sem upside proporcional.

## Decision Outcome

### Story 032 (esta) — Python reader

- `src/observability/unified_audit_reader.py` — lê SQLite + NDJSON,
  retorna `list[AuditEvent]` ordenado.
- `tests/test_phase9_unified_audit.py` — cobertura de cada caminho
  (SQLite-only, NDJSON-only, both, ordering, dedup).
- Dashboard pode opt-in usando o reader em vez de Repository
  direto (não obrigatório nesta story).

### Story 032b (futura) — TS shim

- `observability/sqlite-mirror.ts` com `better-sqlite3`.
- TS event-pipeline ganha hook para emitir cópia em SQLite.
- NDJSON marcado deprecated em ARCHITECTURE.md.
- Pré-requisito: operador rodar `npm install better-sqlite3` em
  ambiente de teste e confirmar `npm test` verde.

### Story 032c (futura, longo prazo) — NDJSON sunset

- Após 1 milestone com 032b verde, remover writes em NDJSON.
- Manter readers de fallback no `UnifiedAuditReader` para arquivos
  legados.

## Reversibility

- **Option C (esta entrega)**: 100% aditiva, zero impacto em writes.
  Para reverter: deletar `src/observability/unified_audit_reader.py`
  e o teste; nenhum runtime depende dele até dashboard ou Deadpool
  optar.
- **Option A (futura)**: o TS shim é um listener no event-pipeline.
  Para reverter: remover o listener; NDJSON segue sendo escrito.

## Riscos Conhecidos

- **Schema mismatch** — eventos SQLite têm `payload: dict`, NDJSON
  tem estrutura própria do Megazord runtime. O reader normaliza
  para um envelope comum (`AuditEvent`), perda de campos
  específicos é registrada em `payload.raw`.
- **Dedup heurístico** — chave de dedup `(timestamp_minute, agent,
  event)` pode colidir em dois eventos legítimos no mesmo minuto.
  Aceitável para v1; refinar com correlation_id em Story futura.
- **Performance em datasets grandes** — leitura linear de NDJSON +
  query SQL. Para v1 com paper trading, sub-segundo. Mainnet com
  meses de histórico vai exigir paginação — fica como follow-up.

## References

- `docs/MEKKA-DEV.md` § 7 — TS vs Python ownership table.
- `docs/ARCHITECTURE.md` § 7 — descreve a coexistência hoje.
- `docs/HANDOFF.md` § 7 — lista "Decisões em aberto".
- `docs/AUTO-CONTINUE-PLAN.md` § 3.1 — definiu este como gate humano.

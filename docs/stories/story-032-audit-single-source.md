# Story 032 — Audit Single Source of Truth (Python reader)

> **Esta story entrega APENAS o lado Python.** O shim TS que escreve
> em SQLite ficou planejado como Story 032b (futura), com pré-requisito
> de o operador rodar `npm install better-sqlite3` em ambiente
> testado. Ver `docs/adr/ADR-001-audit-single-source.md`.

## Context

Dois caminhos de auditoria coexistiam:
- TS Megazord escrevia em `memory/audit-log/*.ndjson`.
- Pipeline Python escrevia em SQLite `audit_log`.

Resultado: forensics + replay exigiam cruzar dois formatos. A
decisão arquitetural foi documentada em `ADR-001`.

## Goal

Entregar **uma timeline unificada** de eventos de auditoria a partir
dos dois stores, sem tocar TS. Pavimenta o caminho para a migração
final (Option A do ADR) em Story 032b.

## Scope Delivered

### ADR

`docs/adr/ADR-001-audit-single-source.md` — análise das 3 opções
(SQLite-wins, NDJSON-wins, Reader-unificado), decisão Option C
(reader unificado primeiro, shim TS depois).

### Modelos

`src/observability/__init__.py` + `src/observability/unified_audit_reader.py`:

- **`AuditSource`** enum (`SQLITE` | `NDJSON`).
- **`AuditEvent`** Pydantic — envelope comum: `schema_version`,
  `timestamp` (UTC-aware), `source`, `agent`, `event`, `severity`,
  `symbol`, `message`, `payload`, `record_id`.
- **`AuditEvent.dedup_key()`** — `(timestamp_minute, agent, event)`
  para colapso heurístico de cross-source duplicates.

### Reader

`UnifiedAuditReader`:

- `read_recent(limit, since)` async, retorna `list[AuditEvent]`
  cronologicamente ascendente.
- Lê SQLite via `MekkaRepository.list_recent_audit` — **defensive**:
  se SQLite falha, NDJSON ainda funciona.
- Lê NDJSON varrendo `memory/audit-log/*.ndjson`. Cada linha
  malformada é silenciosamente skipped — nunca quebra o reader.
- `_ndjson_to_audit` parseia o shape Megazord
  (`{schemaVersion, stream, missionId, record:{kind, actor, data,
  timestamp}, hash}`).
- `_merge_and_dedup` prefere SQLite sobre NDJSON na colisão
  (SQLite tem campos mais ricos).
- `since` filter aplicado em ambos os stores e novamente pós-merge
  (defensa em profundidade).

### Pytest fase 9 — 19 testes

Helpers estáticos (5):
- `_parse_iso` aceita Z-suffix / offset / naive; rejeita junk.
- `_ensure_aware` promove naive para UTC.

NDJSON parsing (2):
- Shape Megazord parseado corretamente.
- Garbage rejeitado (não-dict, sem record, timestamp inválido).

Dedup (3):
- `dedup_key` agrupa por minuto independente do segundo.
- Merge prefere SQLite sobre NDJSON quando ambos colidem.
- Eventos em minutos diferentes não são deduplicados.

NDJSON dir-level (4):
- Empty dir → `[]`.
- Lê múltiplas linhas de um arquivo.
- Skip de linha corrupta + continua.
- Filtro `since` exclui events anteriores.

`read_recent` integração (5):
- SQLite-only (NDJSON dir vazio).
- NDJSON-only (SQLite retorna `[]`).
- Both sources, dedup aplicado, ordem cronológica.
- `since` filter end-to-end.
- SQLite raise não propaga, reader cai gracioso para NDJSON-only.

## Hard Rules Mantidas

- **Read-only.** Reader nunca escreve em SQLite nem NDJSON.
- **Defensivo.** Falha em qualquer source é absorvida — outro
  source continua funcionando.
- **Lossy mas auditável.** Campos NDJSON específicos do Megazord
  são preservados em `payload.raw`.
- **Sem dependência nova.** Tudo Python puro. NDJSON via `pathlib`
  + `json` stdlib, SQLite via `MekkaRepository` existente.
- **Sem mudança em writes.** TS continua escrevendo NDJSON,
  Python continua escrevendo SQLite. Story 032b futura mudará isso.
- **Não toca TS.** Zero linhas em TypeScript.

## Pipeline Atualizado

```
Forensics / Dashboard / Deadpool (futuro)
    ↓
UnifiedAuditReader.read_recent(limit, since)
    ├── _read_sqlite() → MekkaRepository.list_recent_audit()
    └── _read_ndjson() → memory/audit-log/*.ndjson scan
        ↓
    _merge_and_dedup() prefere SQLite na colisão
        ↓
    sort by timestamp ascendente
        ↓
    list[AuditEvent]
```

## Acceptance

- [x] ADR-001 documenta as 3 opções e a decisão.
- [x] `AuditEvent` Pydantic v2 com `schema_version=1`.
- [x] `UnifiedAuditReader` instancia sem deps opcionais.
- [x] `read_recent` retorna eventos chronologicamente ascendentes.
- [x] Dedup via `(minute, agent, event)`.
- [x] SQLite preferido sobre NDJSON na colisão.
- [x] Falha em SQLite NÃO propaga (reader cai para NDJSON).
- [x] Linha NDJSON corrupta não interrompe leitura.
- [x] `since` filter funciona em ambas as fontes.
- [x] 19 testes em `tests/test_phase9_unified_audit.py`.
- [x] Compatibilidade com Stories 002–031 — zero alteração em writes.

## Riscos Conhecidos

- **Dedup heurístico por minuto** — pode colidir em dois eventos
  legítimos no mesmo minuto. Mitigação futura: adicionar
  correlation_id em `audit_log.payload`.
- **Performance linear em NDJSON** — sub-segundo em paper trading,
  exige paginação para meses de histórico. Aceitável v1.
- **Schema lossy** — NDJSON Megazord guarda `prevHash` / `hash` /
  `missionId`. UnifiedAuditReader preserva em `payload.raw` mas
  não expõe como first-class fields. Refinar quando Deadpool
  precisar.

## What's Next

Conforme `AUTO-CONTINUE-PLAN.md`:

- **§ 4** — Pre-testnet hardening (Python 3.13, RUNBOOK, etc.).
  É operacional / humano, não de código.
- **Story 032b futura** — TS shim para escrever em SQLite,
  marcar NDJSON deprecated. Pré-requisito: `npm install
  better-sqlite3` testado.
- **Story 033 — Flash** (Momentum Scalper). Sub-loop intra-candle.

## Files Changed

Novos:
- `docs/adr/ADR-001-audit-single-source.md` (171 linhas)
- `src/observability/__init__.py` (28 linhas)
- `src/observability/unified_audit_reader.py` (213 linhas)
- `tests/test_phase9_unified_audit.py` (310 linhas)
- `docs/stories/story-032-audit-single-source.md` (este arquivo)

Editados (aditivos):
- `docs/stories/INDEX.md` — Story 032 entregue, próxima 033
- `AGENTS.md` — sem alteração (UnifiedAuditReader não é herói)
- `docs/HANDOFF.md` — Story 032 fechada
- `docs/AUTO-CONTINUE-PLAN.md` — § 3 marcada como entregue (Python
  parte), Story 032b agendada como sub-tarefa

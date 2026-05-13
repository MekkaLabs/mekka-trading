# Story 032b — TS Audit Shim (SQLite Mirror)

**Status:** DELIVERED — 2026-05-11
**Milestone:** 9 — Recovery + LLM Hardening
**Pré-requisito:** Story 032 (Python reader) entregue

---

## Contexto

Story 032 entregou o `UnifiedAuditReader` Python que lê eventos de dois stores:
SQLite (pipeline Python) e NDJSON (runtime TS Megazord). O problema é que
eventos TS chegam ao Python apenas via NDJSON — schema diferente, scan linear,
sem índices.

Story 032b fecha o loop: o TS Megazord agora espelha cada evento publicado no
SQLite compartilhado, tornando a timeline TS+Python consultável por SQL.

Isso pavimenta o caminho para a **Option A** do ADR-001 (SQLite como fonte
única de verdade).

---

## Escopo Entregue

### `observability/sqlite-mirror.ts`

**SqliteMirror** — a shim propriamente dita:

- Interface `SqliteWriter` (dependency-injected) — permite testes sem
  `better-sqlite3` instalado.
- `mirrorEvent(DomainEvent)` — escreve uma linha em `audit_log` compatível com
  o modelo SQLAlchemy Python (`AuditRecord`). Evento code → `event`, fonte →
  `agent`, payload serializado como JSON string.
- `mirrorAudit(AuditRecord)` — idem para registros de `AuditTrail`.
  Kind (`trade` | `execution`) vira `AUDIT_TRADE` / `AUDIT_EXECUTION`.
- Resiliência total: qualquer erro do writer é contabilizado em `droppedCount`
  e nunca relançado — o runtime TS não pode parar por falha de auditoria.
- `createSqliteMirror(dbPath)` — factory que carrega `better-sqlite3`
  dinamicamente via `require()`. Se o pacote não está instalado, retorna um
  mirror no-op e imprime aviso em stderr. Zero breaking change.

### Schema SQLite (compatível com Python)

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT    NOT NULL,   -- ISO 8601 UTC
  agent     TEXT    NOT NULL,
  event     TEXT    NOT NULL,
  symbol    TEXT,               -- nullable; TS events raramente trazem símbolo
  severity  TEXT    NOT NULL DEFAULT 'INFO',
  message   TEXT    NOT NULL DEFAULT '',
  payload   TEXT              -- JSON string, nullable
);
```

### `observability/event-pipeline.ts` (atualizado)

`EventPipeline` aceita agora um segundo parâmetro opcional `mirror?: SqliteMirror`.
`publish()` chama `mirror?.mirrorEvent(event)` após escrever no NDJSON store.
Retrocompatível — construtores existentes sem `mirror` continuam funcionando.

### `observability/audit-trail.ts` (atualizado)

`AuditTrail` aceita `mirror?: SqliteMirror`.
`add()` chama `mirror?.mirrorAudit(record)` após escrever no NDJSON store.

### `tests/sqlite-mirror.test.ts` — 12 testes TS

Cobertura com `FakeWriter` (sem `better-sqlite3`):

| # | Cenário |
|---|---------|
| 1 | No-op sem writer — sem throws |
| 2 | `mirrorEvent` → MirroredRow correto (timestamp, agent, event, payload) |
| 3 | `mirrorEvent` sem missionId — message sem prefixo |
| 4 | `mirrorAudit` → AUDIT_TRADE com actor, data, missionId |
| 5 | `mirrorAudit` kind=execution → AUDIT_EXECUTION |
| 6 | Erro do writer → droppedCount++ sem propagação |
| 7 | `EventPipeline.publish` chama `mirrorEvent` |
| 8 | `EventPipeline` sem mirror — sem throws |
| 9 | `AuditTrail.add` chama `mirrorAudit` |
| 10 | `AuditTrail` sem mirror — sem throws |
| 11 | `createSqliteMirror` sem `better-sqlite3` → retorna SqliteMirror |
| 12 | `close()` delega ao writer / no-op sem writer |

---

## Instruções de Ativação

Para habilitar escrita real em SQLite:

```bash
npm install better-sqlite3
# opcional: npm install --save-dev @types/better-sqlite3
```

No runtime (ex.: `workflows/megazord-runtime.ts`):

```typescript
import { createSqliteMirror } from '../observability/sqlite-mirror';

const mirror = createSqliteMirror('data/mekka_trading.db');
const pipeline = new EventPipeline(store, mirror);
const trail   = new AuditTrail(store, mirror);

// Ao encerrar:
mirror.close();
```

Se `better-sqlite3` não estiver instalado, o mirror é silenciosamente desativado
e o comportamento existente (apenas NDJSON) é preservado.

---

## Não Entregue (Story 032c — futura)

- Deprecar writes NDJSON no TS runtime.
- Remover `_ndjson_to_audit` do `UnifiedAuditReader` após 1 milestone com
  032b verde em produção.

---

## Referências

- `docs/adr/ADR-001-audit-single-source.md` — decisão arquitetural
- `src/observability/unified_audit_reader.py` — leitor Python (Story 032)
- `src/persistence/models.py` — `AuditRecord` SQLAlchemy (schema de referência)
- `docs/stories/story-032-audit-single-source.md` — story predecessor

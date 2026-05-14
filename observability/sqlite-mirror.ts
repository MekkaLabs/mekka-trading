/**
 * observability/sqlite-mirror.ts
 * ================================
 * Story 032b — TypeScript → SQLite audit shim.
 *
 * Hooks into EventPipeline and AuditTrail to mirror events into the shared
 * SQLite `audit_log` table that the Python pipeline already uses.  This makes
 * TS Megazord events visible to:
 *   - Python's UnifiedAuditReader (Story 032)
 *   - The live dashboard replay API
 *   - Deadpool's performance forensics (Story 034)
 *
 * Design
 * ------
 * Uses a dependency-injected `SqliteWriter` interface so the class is fully
 * testable without requiring `better-sqlite3` to be installed.  The
 * `createSqliteMirror()` factory lazily loads `better-sqlite3` at runtime and
 * falls back to a silent no-op if the package is not available.
 *
 * Schema
 * ------
 * Writes into the same `audit_log` table that the Python SQLAlchemy model uses:
 *
 *   id        INTEGER PRIMARY KEY AUTOINCREMENT
 *   timestamp TEXT    NOT NULL   -- ISO 8601 UTC
 *   agent     TEXT    NOT NULL
 *   event     TEXT    NOT NULL
 *   symbol    TEXT               -- nullable
 *   severity  TEXT    NOT NULL   DEFAULT 'INFO'
 *   message   TEXT    NOT NULL   DEFAULT ''
 *   payload   TEXT               -- JSON string, nullable
 *
 * See docs/adr/ADR-001-audit-single-source.md
 */

import type { DomainEvent } from './event-pipeline';
import type { AuditRecord } from './audit-trail';

// ---------------------------------------------------------------------------
// Mirrored row (matches Python SQLAlchemy AuditRecord columns)
// ---------------------------------------------------------------------------

export interface MirroredRow {
  timestamp: string;   // ISO 8601 UTC
  agent: string;
  event: string;
  symbol?: string;     // optional — TS events rarely carry a symbol
  severity: string;
  message: string;
  payload?: string;    // JSON string
}

// ---------------------------------------------------------------------------
// Dependency-injection boundary — allows tests to inject a fake writer
// ---------------------------------------------------------------------------

export interface SqliteWriter {
  insert(row: MirroredRow): void;
  close(): void;
}

// ---------------------------------------------------------------------------
// SqliteMirror — the shim itself
// ---------------------------------------------------------------------------

export class SqliteMirror {
  private _dropped = 0;

  /** Pass a SqliteWriter to enable writes; omit for a silent no-op mirror. */
  constructor(private readonly writer?: SqliteWriter) {}

  /**
   * Mirror a DomainEvent published by EventPipeline.
   * Silently swallows any SqliteWriter errors — the TS runtime must never
   * halt because the audit mirror failed.
   */
  mirrorEvent(event: DomainEvent): void {
    if (!this.writer) return;
    try {
      this.writer.insert({
        timestamp: event.createdAt,
        agent: event.source,
        event: event.type,
        severity: 'INFO',
        message: event.missionId
          ? `[mission:${event.missionId}] ${event.type}`
          : event.type,
        payload: JSON.stringify(event.payload),
      });
    } catch {
      this._dropped += 1;
    }
  }

  /**
   * Mirror an AuditRecord added by AuditTrail.
   * Same resilience guarantee — errors are counted but not re-thrown.
   */
  mirrorAudit(record: AuditRecord): void {
    if (!this.writer) return;
    try {
      this.writer.insert({
        timestamp: record.timestamp,
        agent: record.actor,
        event: `AUDIT_${record.kind.toUpperCase()}`,
        severity: 'INFO',
        message: record.missionId
          ? `[mission:${record.missionId}] ${record.kind}`
          : record.kind,
        payload: JSON.stringify(record.data),
      });
    } catch {
      this._dropped += 1;
    }
  }

  /** Number of rows that could not be written due to SqliteWriter errors. */
  get droppedCount(): number {
    return this._dropped;
  }

  /** Release the underlying database connection. */
  close(): void {
    this.writer?.close();
  }
}

// ---------------------------------------------------------------------------
// BetterSqlite3Writer — production adapter (wraps better-sqlite3)
// ---------------------------------------------------------------------------

const _CREATE_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    agent     TEXT    NOT NULL,
    event     TEXT    NOT NULL,
    symbol    TEXT,
    severity  TEXT    NOT NULL DEFAULT 'INFO',
    message   TEXT    NOT NULL DEFAULT '',
    payload   TEXT
  )
`;

const _INSERT_SQL = `
  INSERT INTO audit_log (timestamp, agent, event, symbol, severity, message, payload)
  VALUES (@timestamp, @agent, @event, @symbol, @severity, @message, @payload)
`;

// Minimal structural type for a better-sqlite3 Database instance
interface BetterSqliteDb {
  exec(sql: string): void;
  prepare(sql: string): { run(params: Record<string, unknown>): unknown };
  close(): void;
}

class BetterSqlite3Writer implements SqliteWriter {
  private readonly stmt: ReturnType<BetterSqliteDb['prepare']>;

  constructor(private readonly db: BetterSqliteDb) {
    db.exec(_CREATE_TABLE_SQL);
    this.stmt = db.prepare(_INSERT_SQL);
  }

  insert(row: MirroredRow): void {
    this.stmt.run({
      timestamp: row.timestamp,
      agent: row.agent,
      event: row.event,
      symbol: row.symbol ?? null,
      severity: row.severity,
      message: row.message,
      payload: row.payload ?? null,
    });
  }

  close(): void {
    this.db.close();
  }
}

// ---------------------------------------------------------------------------
// Factory — optional better-sqlite3, silent no-op fallback
// ---------------------------------------------------------------------------

/**
 * Create a SqliteMirror backed by better-sqlite3.
 *
 * If better-sqlite3 is not installed the factory logs a one-time warning to
 * stderr and returns a no-op mirror that silently discards all events.
 *
 * Installation:
 *   npm install better-sqlite3
 *   npm install --save-dev @types/better-sqlite3  (optional, for type hints)
 */
export function createSqliteMirror(dbPath: string): SqliteMirror {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Database = require('better-sqlite3') as new (path: string) => BetterSqliteDb;
    const db = new Database(dbPath);
    return new SqliteMirror(new BetterSqlite3Writer(db));
  } catch {
    process.stderr.write(
      '[SqliteMirror] better-sqlite3 not available — SQLite mirroring disabled.\n' +
      '  Run: npm install better-sqlite3\n',
    );
    return new SqliteMirror(); // silent no-op
  }
}

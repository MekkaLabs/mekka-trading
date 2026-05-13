/**
 * tests/sqlite-mirror.test.ts
 * ============================
 * Story 032b — Unit tests for SqliteMirror.
 *
 * Uses a fake SqliteWriter so better-sqlite3 does NOT need to be installed.
 * Tests cover:
 *   1. No-op behaviour when no writer is provided
 *   2. DomainEvent → MirroredRow mapping (mirrorEvent)
 *   3. AuditRecord → MirroredRow mapping (mirrorAudit)
 *   4. Dropped-count increments on writer errors
 *   5. SqliteMirror does not propagate writer errors
 *   6. EventPipeline calls mirror.mirrorEvent on publish
 *   7. AuditTrail calls mirror.mirrorAudit on add
 *   8. createSqliteMirror returns a no-op when better-sqlite3 is absent
 *
 * Run (after npm run build):
 *   node --test dist/tests/sqlite-mirror.test.js
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { SqliteMirror, createSqliteMirror } from '../observability/sqlite-mirror';
import type { MirroredRow, SqliteWriter } from '../observability/sqlite-mirror';
import { EventPipeline } from '../observability/event-pipeline';
import { AuditTrail } from '../observability/audit-trail';

// ---------------------------------------------------------------------------
// Fake writer — collects rows + supports configurable failure
// ---------------------------------------------------------------------------

class FakeWriter implements SqliteWriter {
  readonly rows: MirroredRow[] = [];
  closed = false;
  failOnNext = false;

  insert(row: MirroredRow): void {
    if (this.failOnNext) {
      this.failOnNext = false;
      throw new Error('simulated sqlite error');
    }
    this.rows.push({ ...row });
  }

  close(): void {
    this.closed = true;
  }
}

// ---------------------------------------------------------------------------
// 1. No-op when no writer
// ---------------------------------------------------------------------------

test('SqliteMirror — no-op when no writer is provided', () => {
  const mirror = new SqliteMirror();
  // Should not throw
  mirror.mirrorEvent({
    type: 'TEST_EVENT',
    source: 'NickFury',
    payload: {},
    createdAt: new Date().toISOString(),
  });
  mirror.mirrorAudit({
    kind: 'trade',
    actor: 'IronMan',
    data: { symbol: 'BTC' },
    timestamp: new Date().toISOString(),
  });
  assert.equal(mirror.droppedCount, 0);
});

// ---------------------------------------------------------------------------
// 2. mirrorEvent — correct MirroredRow mapping
// ---------------------------------------------------------------------------

test('SqliteMirror — mirrorEvent maps DomainEvent to MirroredRow', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);
  const ts = '2026-05-11T12:00:00.000Z';

  mirror.mirrorEvent({
    type: 'CYCLE_START',
    source: 'NickFury',
    payload: { assets: ['BTC', 'ETH'] },
    missionId: 'mission-abc',
    createdAt: ts,
  });

  assert.equal(writer.rows.length, 1);
  const row = writer.rows[0]!;
  assert.equal(row.timestamp, ts);
  assert.equal(row.agent, 'NickFury');
  assert.equal(row.event, 'CYCLE_START');
  assert.equal(row.severity, 'INFO');
  assert.ok(row.message.includes('mission-abc'));
  assert.ok(row.message.includes('CYCLE_START'));
  const payload = JSON.parse(row.payload ?? '{}');
  assert.deepEqual(payload.assets, ['BTC', 'ETH']);
});

test('SqliteMirror — mirrorEvent without missionId omits mission prefix', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);

  mirror.mirrorEvent({
    type: 'HEARTBEAT',
    source: 'Batman',
    payload: {},
    createdAt: new Date().toISOString(),
  });

  const row = writer.rows[0]!;
  assert.equal(row.message, 'HEARTBEAT');
});

// ---------------------------------------------------------------------------
// 3. mirrorAudit — correct MirroredRow mapping
// ---------------------------------------------------------------------------

test('SqliteMirror — mirrorAudit maps AuditRecord to MirroredRow', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);
  const ts = '2026-05-11T12:05:00.000Z';

  mirror.mirrorAudit({
    kind: 'trade',
    actor: 'IronMan',
    data: { symbol: 'BTC', notional: 1500 },
    missionId: 'mission-xyz',
    timestamp: ts,
  });

  assert.equal(writer.rows.length, 1);
  const row = writer.rows[0]!;
  assert.equal(row.timestamp, ts);
  assert.equal(row.agent, 'IronMan');
  assert.equal(row.event, 'AUDIT_TRADE');
  assert.equal(row.severity, 'INFO');
  assert.ok(row.message.includes('mission-xyz'));
  assert.ok(row.message.includes('trade'));
  const payload = JSON.parse(row.payload ?? '{}');
  assert.equal(payload.notional, 1500);
});

test('SqliteMirror — mirrorAudit execution kind maps to AUDIT_EXECUTION', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);

  mirror.mirrorAudit({
    kind: 'execution',
    actor: 'IronMan',
    data: {},
    timestamp: new Date().toISOString(),
  });

  assert.equal(writer.rows[0]?.event, 'AUDIT_EXECUTION');
});

// ---------------------------------------------------------------------------
// 4. droppedCount increments on writer errors
// ---------------------------------------------------------------------------

test('SqliteMirror — droppedCount increments when writer throws', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);

  writer.failOnNext = true;
  mirror.mirrorEvent({
    type: 'BAD_EVENT',
    source: 'Test',
    payload: {},
    createdAt: new Date().toISOString(),
  });

  assert.equal(mirror.droppedCount, 1);
  assert.equal(writer.rows.length, 0);
});

// ---------------------------------------------------------------------------
// 5. Mirror does not propagate writer errors
// ---------------------------------------------------------------------------

test('SqliteMirror — writer errors never throw to the caller', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);

  writer.failOnNext = true;
  // Should not throw
  assert.doesNotThrow(() => {
    mirror.mirrorEvent({
      type: 'X',
      source: 'Y',
      payload: {},
      createdAt: new Date().toISOString(),
    });
  });
});

// ---------------------------------------------------------------------------
// 6. EventPipeline calls mirror.mirrorEvent
// ---------------------------------------------------------------------------

test('EventPipeline — publish calls mirror.mirrorEvent', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);
  const pipeline = new EventPipeline(undefined, mirror);

  pipeline.publish('SIGNAL_GENERATED', 'Vision', { confidence: 0.8 }, 'mission-1');

  assert.equal(writer.rows.length, 1);
  assert.equal(writer.rows[0]?.event, 'SIGNAL_GENERATED');
  assert.equal(writer.rows[0]?.agent, 'Vision');
});

test('EventPipeline — publish without mirror does not throw', () => {
  const pipeline = new EventPipeline();
  assert.doesNotThrow(() => {
    pipeline.publish('RISK_APPROVED', 'Batman', {});
  });
});

// ---------------------------------------------------------------------------
// 7. AuditTrail calls mirror.mirrorAudit
// ---------------------------------------------------------------------------

test('AuditTrail — add calls mirror.mirrorAudit', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);
  const trail = new AuditTrail(undefined, mirror);

  trail.add('execution', 'IronMan', { filled: true }, 'mission-2');

  assert.equal(writer.rows.length, 1);
  assert.equal(writer.rows[0]?.event, 'AUDIT_EXECUTION');
  assert.equal(writer.rows[0]?.agent, 'IronMan');
});

test('AuditTrail — add without mirror does not throw', () => {
  const trail = new AuditTrail();
  assert.doesNotThrow(() => {
    trail.add('trade', 'IronMan', { symbol: 'ETH' });
  });
});

// ---------------------------------------------------------------------------
// 8. createSqliteMirror — no-op when better-sqlite3 is absent
// ---------------------------------------------------------------------------

test('createSqliteMirror — returns no-op mirror when better-sqlite3 is not installed', () => {
  // better-sqlite3 is likely not installed in the test env.
  // If it IS installed, the factory returns a real mirror — we just verify
  // it returns a SqliteMirror without throwing either way.
  let mirror: SqliteMirror | undefined;
  assert.doesNotThrow(() => {
    mirror = createSqliteMirror('/tmp/test-audit-mirror.db');
  });
  assert.ok(mirror instanceof SqliteMirror);
  // Clean up in case better-sqlite3 actually was available
  mirror?.close();
});

// ---------------------------------------------------------------------------
// 9. close() releases the writer
// ---------------------------------------------------------------------------

test('SqliteMirror.close — delegates to writer.close', () => {
  const writer = new FakeWriter();
  const mirror = new SqliteMirror(writer);
  mirror.close();
  assert.equal(writer.closed, true);
});

test('SqliteMirror.close — no-op when no writer', () => {
  const mirror = new SqliteMirror();
  assert.doesNotThrow(() => mirror.close());
});

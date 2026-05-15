import test from 'node:test';
import assert from 'node:assert/strict';
import { OpsAlertRouter } from '../observability/alerts/ops-alert-router';
import { AlertDispatcher } from '../observability/alerts/dispatchers';
import { OpsStatusReport } from '../observability/ops-status';
import { OpsAlertAuditTrail } from '../observability/alerts/ops-alert-audit-trail';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

class CaptureDispatcher implements AlertDispatcher {
  sent = 0;
  constructor(public readonly name: string) {}
  async dispatch(): Promise<void> {
    this.sent += 1;
  }
}

class FailingDispatcher implements AlertDispatcher {
  constructor(public readonly name: string) {}
  async dispatch(): Promise<void> {
    throw new Error('downstream-failure');
  }
}

test('ops alert router dispatches by channel', async () => {
  const webhook = new CaptureDispatcher('webhook');
  const email = new CaptureDispatcher('email');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-ops-audit-'));
  const audit = new OpsAlertAuditTrail(path.join(tmp, 'ops-alert-delivery.ndjson'));
  const router = new OpsAlertRouter(webhook, email, audit);

  const report: OpsStatusReport = {
    generatedAt: new Date().toISOString(),
    dlq: {
      entries: 0,
      lockActive: false,
      lockPath: '/tmp/x.lock',
      lockContention: { recentWindow: 5, occurrences: 0, recurring: false },
    },
    trend: { window: 5, samples: 1, avgDlqEntries: 0, avgReplayFailureRate: 0 },
    alerts: [
      {
        code: 'OPS_LOCK_CONTENTION_RECURRING',
        severity: 'warn',
        message: 'warn route',
        channel: 'email',
        audience: 'ops-watch',
      },
      {
        code: 'OPS_REPLAY_FAILURE_RATE_HIGH',
        severity: 'critical',
        message: 'critical route',
        channel: 'webhook',
        audience: 'mission-commander',
      },
    ],
    alertsMeta: {
      rawCount: 2,
      emittedCount: 2,
      suppressedCount: 0,
      suppressionWindowMinutes: 30,
    },
  };

  const result = await router.dispatch(report);
  assert.equal(result.attempted, 2);
  assert.equal(result.dispatched, 2);
  assert.equal(result.failed, 0);
  assert.equal(webhook.sent, 1);
  assert.equal(email.sent, 1);
  assert.equal(audit.list().length, 2);
  assert.equal(audit.list().every((r) => r.outcome === 'delivered'), true);
});

test('ops alert router audits failed deliveries', async () => {
  const webhook = new FailingDispatcher('webhook');
  const email = new CaptureDispatcher('email');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-ops-audit-'));
  const audit = new OpsAlertAuditTrail(path.join(tmp, 'ops-alert-delivery.ndjson'));
  const router = new OpsAlertRouter(webhook, email, audit);

  const report: OpsStatusReport = {
    generatedAt: new Date().toISOString(),
    dlq: {
      entries: 0,
      lockActive: false,
      lockPath: '/tmp/x.lock',
      lockContention: { recentWindow: 5, occurrences: 0, recurring: false },
    },
    trend: { window: 5, samples: 1, avgDlqEntries: 0, avgReplayFailureRate: 0 },
    alerts: [
      {
        code: 'OPS_REPLAY_FAILURE_RATE_HIGH',
        severity: 'critical',
        message: 'critical route',
        channel: 'webhook',
        audience: 'mission-commander',
      },
    ],
    alertsMeta: {
      rawCount: 1,
      emittedCount: 1,
      suppressedCount: 0,
      suppressionWindowMinutes: 30,
    },
  };

  const result = await router.dispatch(report);
  assert.equal(result.attempted, 1);
  assert.equal(result.dispatched, 0);
  assert.equal(result.failed, 1);
  const records = audit.list();
  assert.equal(records.length, 1);
  assert.equal(records[0]?.outcome, 'failed');
  assert.match(records[0]?.error ?? '', /downstream-failure/);
});

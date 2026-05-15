import test from 'node:test';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import { OpsAlertAuditTrail } from '../observability/alerts/ops-alert-audit-trail';

function mkTrail(): OpsAlertAuditTrail {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-ops-audit-kpi-'));
  return new OpsAlertAuditTrail(path.join(tmp, 'ops-alert-delivery.ndjson'));
}

test('ops alert audit trail computes aggregate kpis by channel and audience', () => {
  const trail = mkTrail();

  trail.append({
    at: '2026-05-07T00:00:00.000Z',
    code: 'OPS_LOCK_CONTENTION_RECURRING',
    severity: 'warn',
    channel: 'email',
    audience: 'ops-watch',
    subject: 'email warn',
    outcome: 'delivered',
  });
  trail.append({
    at: '2026-05-07T00:01:00.000Z',
    code: 'OPS_REPLAY_FAILURE_RATE_HIGH',
    severity: 'critical',
    channel: 'webhook',
    audience: 'mission-commander',
    subject: 'webhook critical',
    outcome: 'failed',
    error: 'timeout',
  });

  const kpis = trail.computeKpis();
  assert.equal(kpis.total, 2);
  assert.equal(kpis.delivered, 1);
  assert.equal(kpis.failed, 1);
  assert.equal(kpis.deliveryRate, 0.5);
  assert.equal(kpis.failureRate, 0.5);

  assert.equal(kpis.byChannel.email.total, 1);
  assert.equal(kpis.byChannel.email.delivered, 1);
  assert.equal(kpis.byChannel.email.failed, 0);
  assert.equal(kpis.byChannel.webhook.total, 1);
  assert.equal(kpis.byChannel.webhook.delivered, 0);
  assert.equal(kpis.byChannel.webhook.failed, 1);

  assert.equal(kpis.byAudience['ops-watch'].total, 1);
  assert.equal(kpis.byAudience['ops-watch'].delivered, 1);
  assert.equal(kpis.byAudience['mission-commander'].total, 1);
  assert.equal(kpis.byAudience['mission-commander'].failed, 1);
});

test('ops alert audit trail supports filter and retention by days', () => {
  const trail = mkTrail();

  trail.append({
    at: '2026-05-01T00:00:00.000Z',
    code: 'OPS_LOCK_CONTENTION_RECURRING',
    severity: 'warn',
    channel: 'email',
    audience: 'ops-watch',
    subject: 'old record',
    outcome: 'delivered',
  });
  trail.append({
    at: '2026-05-07T00:00:00.000Z',
    code: 'OPS_REPLAY_FAILURE_RATE_HIGH',
    severity: 'critical',
    channel: 'webhook',
    audience: 'mission-commander',
    subject: 'new record',
    outcome: 'failed',
    error: 'downstream-failure',
  });

  const filtered = trail.list({ channel: 'webhook', outcome: 'failed' });
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0]?.code, 'OPS_REPLAY_FAILURE_RATE_HIGH');

  const retention = trail.applyRetention(3, new Date('2026-05-07T12:00:00.000Z'));
  assert.equal(retention.before, 2);
  assert.equal(retention.after, 1);
  assert.equal(retention.removed, 1);

  const after = trail.list();
  assert.equal(after.length, 1);
  assert.equal(after[0]?.subject, 'new record');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { OpsStatusCollector } from '../observability/ops-status';

function mkTmpBase(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-ops-'));
}

test('ops status collector reads health and replay summaries', () => {
  const base = mkTmpBase();
  const reportsDir = path.join(base, 'reports');
  const alertsDir = path.join(base, 'alerts');
  fs.mkdirSync(reportsDir, { recursive: true });
  fs.mkdirSync(alertsDir, { recursive: true });

  fs.writeFileSync(path.join(alertsDir, 'dlq.ndjson'), '{"x":1}\n{"x":2}\n', 'utf8');
  fs.writeFileSync(path.join(alertsDir, 'dlq.ndjson.lock'), 'busy', 'utf8');
  fs.writeFileSync(
    path.join(reportsDir, 'health-check-1.json'),
    JSON.stringify({ generatedAt: '2026-05-07T00:00:00.000Z', missionsTotal: 3, ok: 2, warn: 1, critical: 0 }),
    'utf8',
  );
  fs.writeFileSync(
    path.join(reportsDir, 'dlq-replay-1.json'),
    JSON.stringify({ total: 5, replayed: 3, failed: 2, processed: 5, deferred: 0, stoppedByBackpressure: false }),
    'utf8',
  );

  fs.writeFileSync(
    path.join(reportsDir, 'ops-status-older.json'),
    JSON.stringify({
      generatedAt: '2026-05-07T00:00:00.000Z',
      dlq: { entries: 4, lockActive: true, lastReplay: { replayed: 2, failed: 2 } },
    }),
    'utf8',
  );
  fs.writeFileSync(
    path.join(reportsDir, 'ops-status-newer.json'),
    JSON.stringify({
      generatedAt: '2026-05-07T00:01:00.000Z',
      dlq: { entries: 2, lockActive: false, lastReplay: { replayed: 3, failed: 0 } },
    }),
    'utf8',
  );

  const collector = new OpsStatusCollector({ reportsDir, alertsDir });
  const report = collector.collect({ trendWindow: 5, lockContentionThreshold: 1 });

  assert.equal(report.dlq.entries, 2);
  assert.equal(report.dlq.lockActive, true);
  assert.equal(report.health?.missionsTotal, 3);
  assert.equal(report.dlq.lastReplay?.failed, 2);
  assert.equal(report.dlq.lockContention.recurring, true);
  assert.equal(report.trend.samples >= 2, true);
  assert.equal(report.trend.avgDlqEntries > 0, true);
  assert.equal(report.alerts.length > 0, true);
  assert.equal(report.alerts.some((a) => a.code === 'OPS_LOCK_CONTENTION_RECURRING'), true);
  assert.equal(report.alerts.some((a) => a.code === 'OPS_REPLAY_FAILURE_RATE_HIGH'), true);
  assert.equal(report.alertsMeta.rawCount >= report.alertsMeta.emittedCount, true);

  const out = collector.exportLatest(report);
  assert.equal(fs.existsSync(out), true);
});

test('ops status suppression mutes duplicate alerts inside window', () => {
  const base = mkTmpBase();
  const reportsDir = path.join(base, 'reports');
  const alertsDir = path.join(base, 'alerts');
  fs.mkdirSync(reportsDir, { recursive: true });
  fs.mkdirSync(alertsDir, { recursive: true });

  fs.writeFileSync(path.join(alertsDir, 'dlq.ndjson'), '{"x":1}\n', 'utf8');
  fs.writeFileSync(
    path.join(reportsDir, 'ops-status-one.json'),
    JSON.stringify({
      generatedAt: '2026-05-07T00:00:00.000Z',
      dlq: { entries: 2, lockActive: true, lastReplay: { replayed: 1, failed: 1 } },
    }),
    'utf8',
  );

  const collector = new OpsStatusCollector({ reportsDir, alertsDir });
  const first = collector.collect({
    trendWindow: 3,
    lockContentionThreshold: 1,
    alertSuppressionWindowMinutes: 60,
    replayFailureRateWarn: 0.1,
  });
  const second = collector.collect({
    trendWindow: 3,
    lockContentionThreshold: 1,
    alertSuppressionWindowMinutes: 60,
    replayFailureRateWarn: 0.1,
  });

  assert.equal(first.alerts.length > 0, true);
  assert.equal(second.alerts.length, 0);
  assert.equal(second.alertsMeta.suppressedCount > 0, true);
});

test('ops status escalates warn alerts in critical market regime', () => {
  const base = mkTmpBase();
  const reportsDir = path.join(base, 'reports');
  const alertsDir = path.join(base, 'alerts');
  fs.mkdirSync(reportsDir, { recursive: true });
  fs.mkdirSync(alertsDir, { recursive: true });

  fs.writeFileSync(
    path.join(reportsDir, 'ops-status-one.json'),
    JSON.stringify({
      generatedAt: '2026-05-07T00:00:00.000Z',
      dlq: { entries: 2, lockActive: true, lastReplay: { replayed: 3, failed: 1 } },
    }),
    'utf8',
  );

  const collector = new OpsStatusCollector({ reportsDir, alertsDir });
  const report = collector.collect({
    trendWindow: 3,
    lockContentionThreshold: 1,
    replayFailureRateWarn: 0.2,
    replayFailureRateCritical: 0.9,
    alertSuppressionWindowMinutes: 0,
    marketRegime: 'critical',
  });

  assert.equal(report.alerts.some((a) => a.code === 'OPS_LOCK_CONTENTION_RECURRING' && a.severity === 'critical'), true);
  assert.equal(report.alerts.some((a) => a.code === 'OPS_REPLAY_FAILURE_RATE_HIGH' && a.severity === 'critical'), true);
});

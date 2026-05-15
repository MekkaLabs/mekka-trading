import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';
import { ObservabilityHealthCheck } from '../observability/health-check';
import { AppendOnlyStore } from '../observability/store/append-only-store';
import { MegazordRuntime } from '../workflows/megazord-runtime';

function tempMemoryBase(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-test-'));
}

test('health check reports mission integrity status', () => {
  const base = tempMemoryBase();
  const runtime = new MegazordRuntime({ memoryBaseDir: base });
  runtime.run('Health baseline mission', ['BTC-USD', 'ETH-USD'], 'normal');

  const checker = new ObservabilityHealthCheck(
    new AppendOnlyStore(path.join(base, 'audit-log')),
    path.join(base, 'audit-log'),
    path.join(base, 'reports'),
  );
  const report = checker.run();

  assert.ok(report.missionsTotal > 0);
  assert.equal(report.critical >= 0, true);
  assert.equal(report.ok >= 0, true);
  assert.equal(report.retention.alertsFiles >= 0, true);
  assert.equal(report.retention.dlqEntries >= 0, true);
});

test('health check flags critical when a mission is tampered', () => {
  const base = tempMemoryBase();
  const runtime = new MegazordRuntime({ memoryBaseDir: base });
  const run = runtime.run('Tamper health mission', ['BTC-USD', 'ETH-USD'], 'normal');

  const store = new AppendOnlyStore(path.join(base, 'audit-log'));
  store.tamperLine('events', run.missionId, 0, '{"tampered":true}');

  const checker = new ObservabilityHealthCheck(
    new AppendOnlyStore(path.join(base, 'audit-log')),
    path.join(base, 'audit-log'),
    path.join(base, 'reports'),
  );
  const report = checker.run();
  const target = report.missions.find((m) => m.missionId === run.missionId);

  assert.ok(target);
  assert.equal(target?.severity, 'critical');
});

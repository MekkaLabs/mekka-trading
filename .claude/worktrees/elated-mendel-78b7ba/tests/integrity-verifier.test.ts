import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';
import { AppendOnlyStore } from '../observability/store/append-only-store';
import { MegazordRuntime } from '../workflows/megazord-runtime';

function tempMemoryBase(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-test-'));
}

test('integrity verifier returns valid on untampered mission', () => {
  const runtime = new MegazordRuntime({ memoryBaseDir: tempMemoryBase() });
  const run = runtime.run('Integrity mission', ['BTC-USD', 'ETH-USD'], 'normal');
  const integrity = runtime.verifyMissionIntegrity(run.missionId);

  assert.equal(integrity.events.valid, true);
  assert.equal(integrity.audits.valid, true);
});

test('integrity verifier detects tampered event stream', () => {
  const base = tempMemoryBase();
  const runtime = new MegazordRuntime({ memoryBaseDir: base });
  const run = runtime.run('Tamper mission', ['BTC-USD', 'ETH-USD'], 'normal');

  const store = new AppendOnlyStore(path.join(base, 'audit-log'));
  store.tamperLine('events', run.missionId, 0, '{"tampered":true}');

  const integrity = runtime.verifyMissionIntegrity(run.missionId);
  assert.equal(integrity.events.valid, false);
  assert.match(integrity.events.reason ?? '', /(schema|broken|invalid)/i);
});

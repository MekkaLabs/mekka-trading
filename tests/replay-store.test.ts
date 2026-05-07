import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { AppendOnlyStore } from '../observability/store/append-only-store';
import { MegazordRuntime } from '../workflows/megazord-runtime';

test('runtime persists append-only events and audits and allows replay', () => {
  const runtime = new MegazordRuntime();
  const run = runtime.run('Replayable mission', ['BTC-USD', 'ETH-USD'], 'normal');
  const replay = runtime.replayMission(run.missionId);

  assert.equal(replay.missionId, run.missionId);
  assert.ok(replay.events > 0);
  assert.ok(replay.audits > 0);

  const eventsFile = path.join(process.cwd(), 'memory', 'audit-log', `${run.missionId}.events.ndjson`);
  const auditsFile = path.join(process.cwd(), 'memory', 'audit-log', `${run.missionId}.audits.ndjson`);
  assert.equal(fs.existsSync(eventsFile), true);
  assert.equal(fs.existsSync(auditsFile), true);

  const store = new AppendOnlyStore();
  const eventsIntegrity = store.verifyIntegrity('events', run.missionId);
  const auditsIntegrity = store.verifyIntegrity('audits', run.missionId);
  assert.equal(eventsIntegrity.valid, true);
  assert.equal(auditsIntegrity.valid, true);
});

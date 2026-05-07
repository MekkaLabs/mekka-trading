import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { MegazordRuntime } from '../workflows/megazord-runtime';

test('mission report export generates structured file', () => {
  const runtime = new MegazordRuntime();
  const run = runtime.run('Report mission', ['BTC-USD', 'ETH-USD'], 'normal');
  const file = runtime.exportMissionReport(run.missionId);

  assert.equal(fs.existsSync(file), true);

  const json = JSON.parse(fs.readFileSync(file, 'utf8')) as {
    missionId: string;
    schemaVersion: string;
    summary: { events: number; audits: number };
    integrity: {
      events: { valid: boolean };
      audits: { valid: boolean };
    };
    timeline: unknown[];
    auditTrail: unknown[];
  };

  assert.equal(json.missionId, run.missionId);
  assert.equal(typeof json.schemaVersion, 'string');
  assert.ok(json.summary.events > 0);
  assert.ok(json.summary.audits > 0);
  assert.equal(json.integrity.events.valid, true);
  assert.equal(json.integrity.audits.valid, true);
  assert.equal(json.timeline.length, json.summary.events);
  assert.equal(json.auditTrail.length, json.summary.audits);
});

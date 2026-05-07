import test from 'node:test';
import assert from 'node:assert/strict';
import { MegazordRuntime } from '../workflows/megazord-runtime';

test('megazord runtime completes a normal mission cycle', () => {
  const runtime = new MegazordRuntime();
  const report = runtime.run('Risk-first hyperliquid mission', ['BTC-USD', 'ETH-USD'], 'normal');

  assert.ok(report.missionId.startsWith('mission-'));
  assert.ok(report.routedSquads.length >= 2);
  assert.equal(report.accepted + report.blocked, 2);
  assert.equal(report.scenario, 'normal');
  assert.equal(report.riskRegime, 'normal');
  assert.equal(report.capabilityValidation.valid, true);
  assert.ok(report.events > 0);
  assert.ok(report.audits > 0);
});

test('drawdown scenario escalates to critical and blocks execution', () => {
  const runtime = new MegazordRuntime();
  const report = runtime.run('Risk drawdown defense', ['BTC-USD', 'ETH-USD'], 'drawdown-event');

  assert.equal(report.riskRegime, 'critical');
  assert.equal(report.accepted, 0);
  assert.equal(report.blocked, 2);
});

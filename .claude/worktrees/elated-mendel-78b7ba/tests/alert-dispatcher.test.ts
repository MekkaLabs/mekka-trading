import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { HealthAlertOrchestrator } from '../observability/alerts/dispatchers';
import { AlertDedupStore } from '../observability/alerts/dedup-store';
import { HealthReport } from '../observability/health-check';

class CaptureDispatcher {
  constructor(public readonly name: string, public sent = 0) {}

  async dispatch(): Promise<void> {
    this.sent += 1;
  }
}

function fixtureReport(): HealthReport {
  return {
    generatedAt: new Date().toISOString(),
    missionsTotal: 3,
    ok: 1,
    warn: 1,
    critical: 1,
    retention: {
      alertsFiles: 0,
      dlqEntries: 0,
      oldestAlertFileAgeHours: 0,
    },
    missions: [
      {
        missionId: 'm-ok',
        eventsValid: true,
        auditsValid: true,
        eventsChecked: 5,
        auditsChecked: 5,
        severity: 'ok',
      },
      {
        missionId: 'm-warn',
        eventsValid: true,
        auditsValid: true,
        eventsChecked: 0,
        auditsChecked: 2,
        severity: 'warn',
        reason: 'incomplete',
      },
      {
        missionId: 'm-critical',
        eventsValid: false,
        auditsValid: true,
        eventsChecked: 0,
        auditsChecked: 5,
        severity: 'critical',
        reason: 'tampered',
      },
    ],
  };
}

test('dispatches alerts for warn and critical missions', async () => {
  const webhook = new CaptureDispatcher('webhook');
  const email = new CaptureDispatcher('email');
  const dedup = new AlertDedupStore(path.join(process.cwd(), 'memory', 'alerts', 'dedup-test-1.json'));
  dedup.clear();

  const orchestrator = new HealthAlertOrchestrator(webhook as never, email as never, dedup, 30);
  const total = await orchestrator.dispatch(fixtureReport());

  assert.equal(total, 2);
  assert.equal(webhook.sent, 1);
  assert.equal(email.sent, 1);
});

test('suppresses duplicate alerts within dedup window', async () => {
  const webhook = new CaptureDispatcher('webhook');
  const email = new CaptureDispatcher('email');
  const dedup = new AlertDedupStore(path.join(process.cwd(), 'memory', 'alerts', 'dedup-test-2.json'));
  dedup.clear();

  const orchestrator = new HealthAlertOrchestrator(webhook as never, email as never, dedup, 30);
  const first = await orchestrator.dispatch(fixtureReport());
  const second = await orchestrator.dispatch(fixtureReport());

  assert.equal(first, 2);
  assert.equal(second, 0);
  assert.equal(webhook.sent, 1);
  assert.equal(email.sent, 1);
});

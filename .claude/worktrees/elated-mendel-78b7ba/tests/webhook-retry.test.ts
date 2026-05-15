import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { CircuitBreakerDispatcher, CircuitBreakerOpenError, RetryingDispatcher } from '../observability/alerts/retrying-dispatcher';
import { AlertDispatcher, AlertMessage, HealthAlertOrchestrator } from '../observability/alerts/dispatchers';
import { SignedWebhookDispatcher } from '../observability/alerts/webhook-dispatcher';
import { HealthReport } from '../observability/health-check';
import { AlertDlqStore } from '../observability/alerts/dlq-store';
import { AlertDedupStore } from '../observability/alerts/dedup-store';
import path from 'node:path';

test('retrying dispatcher retries and succeeds', async () => {
  let attempts = 0;
  const flaky: AlertDispatcher = {
    name: 'flaky',
    dispatch: async () => {
      attempts += 1;
      if (attempts < 3) throw new Error('temporary');
    },
  };

  const retry = new RetryingDispatcher(flaky, { attempts: 3, baseDelayMs: 1, maxDelayMs: 2, jitterRatio: 0 });
  await retry.dispatch({ channel: 'webhook', severity: 'critical', subject: 's', body: 'b' });
  assert.equal(attempts, 3);
});

test('signed webhook dispatcher sends hmac signature', async () => {
  let capturedSig = '';
  let capturedBody = '';

  const originalFetch = global.fetch;
  global.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    capturedSig = headers['x-mekka-signature'];
    capturedBody = String(init?.body ?? '');
    return new Response('', { status: 200 });
  }) as typeof fetch;

  try {
    const secret = 'sekret';
    const dispatcher = new SignedWebhookDispatcher({ url: 'https://example.com/hook', secret, timeoutMs: 1000 });
    const message: AlertMessage = { channel: 'webhook', severity: 'critical', subject: 's', body: 'b', missionId: 'm1' };

    await dispatcher.dispatch(message);

    const expected = crypto.createHmac('sha256', secret).update(capturedBody).digest('hex');
    assert.equal(capturedSig, expected);
  } finally {
    global.fetch = originalFetch;
  }
});

test('failed dispatch is sent to dead-letter queue', async () => {
  const failing: AlertDispatcher = {
    name: 'always-fail',
    dispatch: async () => {
      throw new Error('permanent failure');
    },
  };

  const dedup = new AlertDedupStore(path.join(process.cwd(), 'memory', 'alerts', 'dedup-test-dlq.json'));
  dedup.clear();
  const dlq = new AlertDlqStore(path.join(process.cwd(), 'memory', 'alerts', 'dlq-test.ndjson'));
  dlq.clear();

  const orchestrator = new HealthAlertOrchestrator(failing, failing, dedup, 30, dlq);

  const report: HealthReport = {
    generatedAt: new Date().toISOString(),
    missionsTotal: 1,
    ok: 0,
    warn: 0,
    critical: 1,
    retention: {
      alertsFiles: 0,
      dlqEntries: 0,
      oldestAlertFileAgeHours: 0,
    },
    missions: [
      {
        missionId: 'm-critical-dlq',
        eventsValid: false,
        auditsValid: true,
        eventsChecked: 0,
        auditsChecked: 5,
        severity: 'critical',
        reason: 'tampered',
      },
    ],
  };

  const dispatched = await orchestrator.dispatch(report);
  const entries = dlq.list();

  assert.equal(dispatched, 0);
  assert.equal(entries.length, 1);
  assert.match(entries[0].error, /permanent failure/i);
});

test('circuit breaker opens after threshold and blocks subsequent dispatch', async () => {
  let attempts = 0;
  const alwaysFail: AlertDispatcher = {
    name: 'always-fail',
    dispatch: async () => {
      attempts += 1;
      throw new Error('downstream-down');
    },
  };

  const breaker = new CircuitBreakerDispatcher(alwaysFail, {
    failureThreshold: 2,
    cooldownMs: 60000,
  });

  await assert.rejects(() => breaker.dispatch({ channel: 'webhook', severity: 'critical', subject: 's1', body: 'b1' }));
  await assert.rejects(() => breaker.dispatch({ channel: 'webhook', severity: 'critical', subject: 's2', body: 'b2' }));
  await assert.rejects(
    () => breaker.dispatch({ channel: 'webhook', severity: 'critical', subject: 's3', body: 'b3' }),
    (err: unknown) => err instanceof CircuitBreakerOpenError,
  );
  assert.equal(attempts, 2);
  const snapshot = breaker.snapshot();
  assert.equal(snapshot.state, 'open');
  assert.equal(snapshot.consecutiveFailures, 2);
  assert.equal(snapshot.failureThreshold, 2);
});

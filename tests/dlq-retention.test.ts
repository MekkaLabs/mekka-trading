import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { AlertDlqStore } from '../observability/alerts/dlq-store';
import { DlqReplayLockError, DlqReplayer } from '../observability/alerts/dlq-replayer';
import { AlertsRetentionManager } from '../observability/alerts/retention-manager';
import { AlertDispatcher } from '../observability/alerts/dispatchers';

test('dlq replayer clears entries after successful replay', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-dlq-'));
  const dlq = new AlertDlqStore(path.join(tmp, 'dlq.ndjson'));

  dlq.push({
    failedAt: new Date().toISOString(),
    dispatcher: 'x',
    error: 'boom',
    message: { channel: 'webhook', severity: 'critical', subject: 's', body: 'b', missionId: 'm1' },
  });

  const ok: AlertDispatcher = { name: 'ok', dispatch: async () => {} };
  const replayer = new DlqReplayer(dlq, ok, ok);
  const report = await replayer.replayAll();

  assert.equal(report.total, 1);
  assert.equal(report.replayed, 1);
  assert.equal(report.failed, 0);
  assert.equal(report.remainingInDlq, 0);
  assert.equal(report.byChannel.webhook.replayed, 1);
  assert.equal(report.stoppedByBackpressure, false);
  assert.equal(report.processed, 1);
  assert.equal(report.deferred, 0);
  assert.equal(dlq.list().length, 0);
});

test('dlq replayer keeps only failed entries after partial failure', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-dlq-'));
  const dlq = new AlertDlqStore(path.join(tmp, 'dlq.ndjson'));

  dlq.push({
    failedAt: new Date().toISOString(),
    dispatcher: 'w',
    error: 'boom-webhook',
    message: { channel: 'webhook', severity: 'critical', subject: 'webhook', body: 'b', missionId: 'm-webhook' },
  });
  dlq.push({
    failedAt: new Date().toISOString(),
    dispatcher: 'e',
    error: 'boom-email',
    message: { channel: 'email', severity: 'warn', subject: 'email', body: 'b', missionId: 'm-email' },
  });

  const failingWebhook: AlertDispatcher = { name: 'webhook-fail', dispatch: async () => {
    throw new Error('still-down');
  } };
  const okEmail: AlertDispatcher = { name: 'email-ok', dispatch: async () => {} };
  const replayer = new DlqReplayer(dlq, failingWebhook, okEmail);
  const report = await replayer.replayAll();

  assert.equal(report.total, 2);
  assert.equal(report.replayed, 1);
  assert.equal(report.failed, 1);
  assert.equal(report.remainingInDlq, 1);
  assert.equal(report.byChannel.webhook.failed, 1);
  assert.equal(report.byChannel.email.replayed, 1);
  assert.equal(report.processed, 2);
  assert.equal(report.deferred, 0);

  const pending = dlq.list();
  assert.equal(pending.length, 1);
  assert.equal(pending[0]?.message.channel, 'webhook');
});

test('dlq replayer applies backpressure with batch size and max failures', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-dlq-'));
  const dlq = new AlertDlqStore(path.join(tmp, 'dlq.ndjson'));

  dlq.push({
    failedAt: new Date().toISOString(),
    dispatcher: 'w1',
    error: 'e1',
    message: { channel: 'webhook', severity: 'critical', subject: 's1', body: 'b', missionId: 'm1' },
  });
  dlq.push({
    failedAt: new Date().toISOString(),
    dispatcher: 'w2',
    error: 'e2',
    message: { channel: 'webhook', severity: 'critical', subject: 's2', body: 'b', missionId: 'm2' },
  });
  dlq.push({
    failedAt: new Date().toISOString(),
    dispatcher: 'e3',
    error: 'e3',
    message: { channel: 'email', severity: 'warn', subject: 's3', body: 'b', missionId: 'm3' },
  });

  const failingWebhook: AlertDispatcher = { name: 'webhook-fail', dispatch: async () => {
    throw new Error('still-down');
  } };
  const okEmail: AlertDispatcher = { name: 'email-ok', dispatch: async () => {} };
  const replayer = new DlqReplayer(dlq, failingWebhook, okEmail);
  const report = await replayer.replayAll({ batchSize: 2, maxFailures: 1 });

  assert.equal(report.total, 3);
  assert.equal(report.processed, 1);
  assert.equal(report.deferred, 2);
  assert.equal(report.stoppedByBackpressure, true);
  assert.equal(report.failed, 1);
  assert.equal(report.replayed, 0);
  assert.equal(report.remainingInDlq, 3);
  assert.equal(dlq.list().length, 3);
  assert.ok(report.lockFile.endsWith('.lock'));
});

test('dlq replayer fails fast when lock already exists', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-dlq-'));
  const dlq = new AlertDlqStore(path.join(tmp, 'dlq.ndjson'));
  fs.writeFileSync(`${dlq.getPath()}.lock`, 'busy', 'utf8');

  const ok: AlertDispatcher = { name: 'ok', dispatch: async () => {} };
  const replayer = new DlqReplayer(dlq, ok, ok);

  await assert.rejects(async () => replayer.replayAll(), (err: unknown) => err instanceof DlqReplayLockError);
});

test('alerts retention removes old files and enforces max files', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mekka-ret-'));

  const files = ['a.log', 'b.log', 'c.log', 'd.log'];
  for (const f of files) {
    fs.writeFileSync(path.join(tmp, f), 'x', 'utf8');
  }

  const oldTime = Date.now() - 10 * 24 * 60 * 60 * 1000;
  fs.utimesSync(path.join(tmp, 'a.log'), oldTime / 1000, oldTime / 1000);

  const manager = new AlertsRetentionManager(tmp, { maxAgeDays: 7, maxFiles: 2 });
  const report = manager.enforce();

  const remaining = fs.readdirSync(tmp);
  assert.ok(report.removed >= 2);
  assert.ok(remaining.length <= 2);
  assert.equal(report.kept, remaining.length);
  assert.ok(report.removedByAge >= 1);
  assert.ok(report.removedByCapacity >= 0);
});

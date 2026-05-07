import fs from 'node:fs';
import path from 'node:path';
import { ConsoleEmailDispatcher, ConsoleWebhookDispatcher } from '../observability/alerts/dispatchers';
import { AlertDlqStore } from '../observability/alerts/dlq-store';
import { DlqReplayLockError, DlqReplayer } from '../observability/alerts/dlq-replayer';
import { CircuitBreakerDispatcher, RetryingDispatcher } from '../observability/alerts/retrying-dispatcher';

async function main(): Promise<void> {
  const dlq = new AlertDlqStore();
  const webhookBreaker = new CircuitBreakerDispatcher(new RetryingDispatcher(new ConsoleWebhookDispatcher()), {
    failureThreshold: 3,
    cooldownMs: 15000,
  });
  const emailBreaker = new CircuitBreakerDispatcher(new RetryingDispatcher(new ConsoleEmailDispatcher()), {
    failureThreshold: 3,
    cooldownMs: 15000,
  });
  const replayer = new DlqReplayer(dlq, webhookBreaker, emailBreaker);

  const batchSize = Number(process.env.MEKKA_DLQ_REPLAY_BATCH_SIZE);
  const maxFailures = Number(process.env.MEKKA_DLQ_REPLAY_MAX_FAILURES);
  const reportsDir = path.join(process.cwd(), 'memory', 'reports');
  fs.mkdirSync(reportsDir, { recursive: true });

  try {
    const replay = await replayer.replayAll({
      batchSize: Number.isFinite(batchSize) && batchSize > 0 ? batchSize : undefined,
      maxFailures: Number.isFinite(maxFailures) && maxFailures > 0 ? maxFailures : undefined,
    });
    const report = {
      ...replay,
      breakers: {
        webhook: webhookBreaker.snapshot(),
        email: emailBreaker.snapshot(),
      },
    };
    const outputPath = path.join(reportsDir, `dlq-replay-${Date.now()}.json`);
    fs.writeFileSync(outputPath, JSON.stringify(report, null, 2), 'utf8');

    console.log(JSON.stringify({ report, outputPath }));

    if (report.failed > 0) {
      process.exit(2);
    }
  } catch (error) {
    if (error instanceof DlqReplayLockError) {
      console.error(JSON.stringify({ error: error.message }));
      process.exit(3);
    }
    throw error;
  }
}

void main();

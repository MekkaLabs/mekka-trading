import fs from 'node:fs';
import path from 'node:path';
import { AlertDispatcher, AlertMessage } from './dispatchers';
import { AlertDlqStore, DlqEntry } from './dlq-store';

export interface DlqReplayReport {
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  total: number;
  replayed: number;
  failed: number;
  remainingInDlq: number;
  byChannel: {
    webhook: { replayed: number; failed: number };
    email: { replayed: number; failed: number };
  };
  processed: number;
  deferred: number;
  stoppedByBackpressure: boolean;
  lockFile: string;
}

export interface DlqReplayOptions {
  batchSize?: number;
  maxFailures?: number;
}

export class DlqReplayLockError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DlqReplayLockError';
  }
}

export class DlqReplayer {
  constructor(
    private readonly dlqStore: AlertDlqStore,
    private readonly webhookDispatcher: AlertDispatcher,
    private readonly emailDispatcher: AlertDispatcher,
  ) {}

  async replayAll(options: DlqReplayOptions = {}): Promise<DlqReplayReport> {
    const lockFile = `${this.dlqStore.getPath()}.lock`;
    const lockFd = this.acquireLock(lockFile);
    const started = Date.now();
    try {
      const entries = this.dlqStore.list();
      const defaultBatchSize = entries.length > 0 ? entries.length : 1;
      const batchSize = Math.max(1, options.batchSize ?? defaultBatchSize);
      const maxFailures = Math.max(1, options.maxFailures ?? Number.MAX_SAFE_INTEGER);
      const batch = entries.slice(0, batchSize);
      const pending: DlqEntry[] = [];
      let replayed = 0;
      let failed = 0;
      let processed = 0;
      let stoppedByBackpressure = false;
      const byChannel = {
        webhook: { replayed: 0, failed: 0 },
        email: { replayed: 0, failed: 0 },
      };

      for (const entry of batch) {
        if (failed >= maxFailures) {
          stoppedByBackpressure = true;
          break;
        }
        const dispatcher = this.resolveDispatcher(entry.message);
        try {
          await Promise.resolve(dispatcher.dispatch(entry.message));
          replayed += 1;
          byChannel[entry.message.channel].replayed += 1;
        } catch {
          failed += 1;
          byChannel[entry.message.channel].failed += 1;
          pending.push(entry);
        }
        processed += 1;
      }

      const deferred = entries.length - processed;
      const notProcessed = entries.slice(processed);
      this.dlqStore.replace([...pending, ...notProcessed]);
      const finished = Date.now();

      return {
        startedAt: new Date(started).toISOString(),
        finishedAt: new Date(finished).toISOString(),
        durationMs: finished - started,
        total: entries.length,
        replayed,
        failed,
        remainingInDlq: pending.length + notProcessed.length,
        byChannel,
        processed,
        deferred,
        stoppedByBackpressure,
        lockFile,
      };
    } finally {
      this.releaseLock(lockFd, lockFile);
    }
  }

  private resolveDispatcher(message: AlertMessage): AlertDispatcher {
    return message.channel === 'webhook' ? this.webhookDispatcher : this.emailDispatcher;
  }

  private acquireLock(lockFile: string): number {
    fs.mkdirSync(path.dirname(lockFile), { recursive: true });
    try {
      return fs.openSync(lockFile, 'wx');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'EEXIST') {
        throw new DlqReplayLockError(`DLQ replay lock is already active: ${lockFile}`);
      }
      throw error;
    }
  }

  private releaseLock(fd: number, lockFile: string): void {
    try {
      fs.closeSync(fd);
    } finally {
      fs.rmSync(lockFile, { force: true });
    }
  }
}

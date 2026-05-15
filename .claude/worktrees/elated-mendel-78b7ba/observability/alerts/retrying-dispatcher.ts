import { AlertDispatcher, AlertMessage } from './dispatchers';

export interface RetryPolicy {
  attempts: number;
  baseDelayMs: number;
  maxDelayMs: number;
  jitterRatio?: number;
}

export interface CircuitBreakerPolicy {
  failureThreshold: number;
  cooldownMs: number;
}

export interface CircuitBreakerSnapshot {
  name: string;
  state: 'closed' | 'open' | 'half-open';
  consecutiveFailures: number;
  openedAt?: string;
  failureThreshold: number;
  cooldownMs: number;
}

export class CircuitBreakerOpenError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CircuitBreakerOpenError';
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function withJitter(baseDelay: number, jitterRatio: number): number {
  const spread = baseDelay * jitterRatio;
  const jitter = (Math.random() * 2 - 1) * spread;
  return Math.max(0, Math.round(baseDelay + jitter));
}

export class RetryingDispatcher implements AlertDispatcher {
  name: string;

  constructor(
    private readonly inner: AlertDispatcher,
    private readonly policy: RetryPolicy = { attempts: 3, baseDelayMs: 250, maxDelayMs: 2000, jitterRatio: 0.2 },
  ) {
    this.name = `retry:${inner.name}`;
  }

  async dispatch(message: AlertMessage): Promise<void> {
    let attempt = 0;
    let lastError: unknown;

    while (attempt < this.policy.attempts) {
      try {
        await Promise.resolve(this.inner.dispatch(message));
        return;
      } catch (error) {
        lastError = error;
        attempt += 1;
        if (attempt >= this.policy.attempts) break;

        const rawDelay = Math.min(this.policy.baseDelayMs * 2 ** (attempt - 1), this.policy.maxDelayMs);
        const delay = withJitter(rawDelay, this.policy.jitterRatio ?? 0);
        await sleep(delay);
      }
    }

    throw lastError instanceof Error ? lastError : new Error('Unknown dispatch failure');
  }
}

type CircuitState = 'closed' | 'open' | 'half-open';

export class CircuitBreakerDispatcher implements AlertDispatcher {
  name: string;
  private state: CircuitState = 'closed';
  private consecutiveFailures = 0;
  private openedAt = 0;

  constructor(
    private readonly inner: AlertDispatcher,
    private readonly policy: CircuitBreakerPolicy = { failureThreshold: 3, cooldownMs: 10000 },
  ) {
    this.name = `circuit:${inner.name}`;
  }

  async dispatch(message: AlertMessage): Promise<void> {
    this.transitionByTime();

    if (this.state === 'open') {
      throw new CircuitBreakerOpenError(`Circuit open for dispatcher ${this.inner.name}`);
    }

    try {
      await Promise.resolve(this.inner.dispatch(message));
      this.consecutiveFailures = 0;
      this.state = 'closed';
    } catch (error) {
      this.consecutiveFailures += 1;
      if (this.consecutiveFailures >= this.policy.failureThreshold) {
        this.state = 'open';
        this.openedAt = Date.now();
      } else if (this.state === 'half-open') {
        this.state = 'open';
        this.openedAt = Date.now();
      }

      throw error instanceof Error ? error : new Error(String(error));
    }
  }

  snapshot(): CircuitBreakerSnapshot {
    this.transitionByTime();
    return {
      name: this.name,
      state: this.state,
      consecutiveFailures: this.consecutiveFailures,
      openedAt: this.openedAt > 0 ? new Date(this.openedAt).toISOString() : undefined,
      failureThreshold: this.policy.failureThreshold,
      cooldownMs: this.policy.cooldownMs,
    };
  }

  private transitionByTime(): void {
    if (this.state !== 'open') return;
    if (Date.now() - this.openedAt >= this.policy.cooldownMs) {
      this.state = 'half-open';
    }
  }
}

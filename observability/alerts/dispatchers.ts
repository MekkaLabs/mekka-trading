import { HealthReport, HealthSeverity, MissionHealth } from '../health-check';
import { AlertDedupStore } from './dedup-store';
import { AlertDlqStore } from './dlq-store';

export interface AlertMessage {
  channel: 'webhook' | 'email';
  severity: HealthSeverity;
  subject: string;
  body: string;
  missionId?: string;
}

export interface AlertDispatcher {
  name: string;
  dispatch(message: AlertMessage): void | Promise<void>;
}

export class ConsoleWebhookDispatcher implements AlertDispatcher {
  name = 'console-webhook';

  dispatch(message: AlertMessage): void {
    console.log(
      JSON.stringify({
        dispatcher: this.name,
        channel: message.channel,
        severity: message.severity,
        subject: message.subject,
        missionId: message.missionId,
      }),
    );
  }
}

export class ConsoleEmailDispatcher implements AlertDispatcher {
  name = 'console-email';

  dispatch(message: AlertMessage): void {
    console.log(
      JSON.stringify({
        dispatcher: this.name,
        channel: message.channel,
        severity: message.severity,
        subject: message.subject,
        missionId: message.missionId,
      }),
    );
  }
}

function toMessage(mission: MissionHealth): AlertMessage {
  const severity = mission.severity;
  const subject = `[Mekka:${severity.toUpperCase()}] Mission ${mission.missionId}`;
  const body = `Mission ${mission.missionId} health status=${severity}. reason=${mission.reason ?? 'none'}`;

  return {
    channel: severity === 'critical' ? 'webhook' : 'email',
    severity,
    subject,
    body,
    missionId: mission.missionId,
  };
}

function dedupKey(message: AlertMessage): string {
  return `${message.severity}:${message.missionId ?? 'unknown'}:${message.subject}`;
}

export class HealthAlertOrchestrator {
  constructor(
    private readonly webhookDispatcher: AlertDispatcher = new ConsoleWebhookDispatcher(),
    private readonly emailDispatcher: AlertDispatcher = new ConsoleEmailDispatcher(),
    private readonly dedupStore: AlertDedupStore = new AlertDedupStore(),
    private readonly dedupWindowMinutes = 30,
    private readonly dlqStore: AlertDlqStore = new AlertDlqStore(),
  ) {}

  async dispatch(report: HealthReport): Promise<number> {
    const targets = report.missions.filter((m) => m.severity === 'warn' || m.severity === 'critical');
    const now = new Date();
    let dispatched = 0;

    for (const mission of targets) {
      const message = toMessage(mission);
      const key = dedupKey(message);

      if (!this.dedupStore.shouldDispatch(key, now, this.dedupWindowMinutes)) {
        continue;
      }

      try {
        if (message.channel === 'webhook') await Promise.resolve(this.webhookDispatcher.dispatch(message));
        else await Promise.resolve(this.emailDispatcher.dispatch(message));

        this.dedupStore.markDispatched(key, now);
        dispatched += 1;
      } catch (error) {
        this.dlqStore.push({
          failedAt: new Date().toISOString(),
          dispatcher: message.channel === 'webhook' ? this.webhookDispatcher.name : this.emailDispatcher.name,
          error: error instanceof Error ? error.message : String(error),
          message,
        });
      }
    }

    return dispatched;
  }
}

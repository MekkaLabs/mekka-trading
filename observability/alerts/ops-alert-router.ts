import { AlertDispatcher, AlertMessage } from './dispatchers';
import { OpsAlert, OpsStatusReport } from '../ops-status';
import { OpsAlertAuditTrail } from './ops-alert-audit-trail';

export interface OpsAlertDispatchResult {
  attempted: number;
  dispatched: number;
  failed: number;
}

export class OpsAlertRouter {
  constructor(
    private readonly webhookDispatcher: AlertDispatcher,
    private readonly emailDispatcher: AlertDispatcher,
    private readonly auditTrail: OpsAlertAuditTrail = new OpsAlertAuditTrail(),
  ) {}

  async dispatch(report: OpsStatusReport): Promise<OpsAlertDispatchResult> {
    let dispatched = 0;
    let failed = 0;

    for (const alert of report.alerts) {
      const message = this.toAlertMessage(alert, report.generatedAt);
      const target = alert.channel === 'webhook' ? this.webhookDispatcher : this.emailDispatcher;
      try {
        await Promise.resolve(target.dispatch(message));
        this.auditTrail.append({
          at: new Date().toISOString(),
          code: alert.code,
          severity: alert.severity,
          channel: alert.channel,
          audience: alert.audience,
          subject: message.subject,
          outcome: 'delivered',
        });
        dispatched += 1;
      } catch (error) {
        this.auditTrail.append({
          at: new Date().toISOString(),
          code: alert.code,
          severity: alert.severity,
          channel: alert.channel,
          audience: alert.audience,
          subject: message.subject,
          outcome: 'failed',
          error: error instanceof Error ? error.message : String(error),
        });
        failed += 1;
      }
    }

    return {
      attempted: report.alerts.length,
      dispatched,
      failed,
    };
  }

  private toAlertMessage(alert: OpsAlert, generatedAt: string): AlertMessage {
    const subject = `[Mekka:OPS:${alert.severity.toUpperCase()}] ${alert.code}`;
    const body = `${alert.message} audience=${alert.audience} generatedAt=${generatedAt}`;
    return {
      channel: alert.channel,
      severity: alert.severity,
      subject,
      body,
      missionId: 'ops-control-tower',
    };
  }
}

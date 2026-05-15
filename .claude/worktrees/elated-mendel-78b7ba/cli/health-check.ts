import { ConsoleEmailDispatcher, ConsoleWebhookDispatcher, HealthAlertOrchestrator } from '../observability/alerts/dispatchers';
import { CircuitBreakerDispatcher, RetryingDispatcher } from '../observability/alerts/retrying-dispatcher';
import { SignedWebhookDispatcher } from '../observability/alerts/webhook-dispatcher';
import { ObservabilityHealthCheck } from '../observability/health-check';

async function main(): Promise<void> {
  const checker = new ObservabilityHealthCheck();
  const report = checker.run();
  const outputPath = checker.exportLatest();

  const webhookUrl = process.env.MEKKA_ALERT_WEBHOOK_URL;
  const webhookSecret = process.env.MEKKA_ALERT_WEBHOOK_SECRET;

  const retryingWebhookDispatcher =
    webhookUrl && webhookSecret
      ? new RetryingDispatcher(new SignedWebhookDispatcher({ url: webhookUrl, secret: webhookSecret }))
      : new ConsoleWebhookDispatcher();

  const webhookDispatcher = new CircuitBreakerDispatcher(retryingWebhookDispatcher, {
    failureThreshold: 3,
    cooldownMs: 15000,
  });
  const emailDispatcher = new CircuitBreakerDispatcher(new RetryingDispatcher(new ConsoleEmailDispatcher()), {
    failureThreshold: 3,
    cooldownMs: 15000,
  });

  const alerts = new HealthAlertOrchestrator(webhookDispatcher, emailDispatcher);
  const dispatched = await alerts.dispatch(report);

  console.log(
    JSON.stringify({
      summary: {
        missionsTotal: report.missionsTotal,
        ok: report.ok,
        warn: report.warn,
        critical: report.critical,
        alertsDispatched: dispatched,
        retention: report.retention,
      },
      outputPath,
    }),
  );

  if (report.critical > 0) {
    process.exit(2);
  }
}

void main();

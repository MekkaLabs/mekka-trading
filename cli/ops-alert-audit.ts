import { OpsAlertAuditTrail, OpsAlertDeliveryFilter } from '../observability/alerts/ops-alert-audit-trail';

function asChannel(value: string | undefined): OpsAlertDeliveryFilter['channel'] {
  return value === 'webhook' || value === 'email' ? value : undefined;
}

function asAudience(value: string | undefined): OpsAlertDeliveryFilter['audience'] {
  return value === 'mission-commander' || value === 'ops-watch' ? value : undefined;
}

function asSeverity(value: string | undefined): OpsAlertDeliveryFilter['severity'] {
  return value === 'warn' || value === 'critical' ? value : undefined;
}

function asOutcome(value: string | undefined): OpsAlertDeliveryFilter['outcome'] {
  return value === 'delivered' || value === 'failed' ? value : undefined;
}

function readSince(minutesRaw: string | undefined): string | undefined {
  const minutes = Number(minutesRaw);
  if (!Number.isFinite(minutes) || minutes <= 0) return undefined;
  return new Date(Date.now() - minutes * 60 * 1000).toISOString();
}

const trail = new OpsAlertAuditTrail();
const retentionDays = Number(process.env.MEKKA_OPS_ALERT_AUDIT_RETENTION_DAYS);
const filter: OpsAlertDeliveryFilter = {
  channel: asChannel(process.env.MEKKA_OPS_ALERT_AUDIT_CHANNEL),
  audience: asAudience(process.env.MEKKA_OPS_ALERT_AUDIT_AUDIENCE),
  severity: asSeverity(process.env.MEKKA_OPS_ALERT_AUDIT_SEVERITY),
  outcome: asOutcome(process.env.MEKKA_OPS_ALERT_AUDIT_OUTCOME),
  code: process.env.MEKKA_OPS_ALERT_AUDIT_CODE,
  since: readSince(process.env.MEKKA_OPS_ALERT_AUDIT_SINCE_MINUTES),
};

const limitRaw = Number(process.env.MEKKA_OPS_ALERT_AUDIT_LIMIT);
if (Number.isFinite(limitRaw) && limitRaw > 0) {
  filter.limit = Math.floor(limitRaw);
}

const retention =
  Number.isFinite(retentionDays) && retentionDays > 0 ? trail.applyRetention(retentionDays) : undefined;
const records = trail.list(filter);
const kpis = trail.computeKpis(filter);

console.log(
  JSON.stringify({
    generatedAt: new Date().toISOString(),
    filter,
    retention,
    kpis,
    records,
  }),
);

if (kpis.failed > 0) {
  process.exit(2);
}

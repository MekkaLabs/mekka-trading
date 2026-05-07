import fs from 'node:fs';
import path from 'node:path';

export interface OpsAlertDeliveryRecord {
  at: string;
  code: string;
  severity: 'warn' | 'critical';
  channel: 'webhook' | 'email';
  audience: 'mission-commander' | 'ops-watch';
  subject: string;
  outcome: 'delivered' | 'failed';
  error?: string;
}

export interface OpsAlertDeliveryFilter {
  channel?: OpsAlertDeliveryRecord['channel'];
  audience?: OpsAlertDeliveryRecord['audience'];
  severity?: OpsAlertDeliveryRecord['severity'];
  outcome?: OpsAlertDeliveryRecord['outcome'];
  code?: string;
  since?: string;
  limit?: number;
}

export interface OpsAlertDeliveryKpis {
  total: number;
  delivered: number;
  failed: number;
  deliveryRate: number;
  failureRate: number;
  byChannel: Record<OpsAlertDeliveryRecord['channel'], { total: number; delivered: number; failed: number; deliveryRate: number }>;
  byAudience: Record<OpsAlertDeliveryRecord['audience'], { total: number; delivered: number; failed: number; deliveryRate: number }>;
}

export interface OpsAlertRetentionResult {
  before: number;
  after: number;
  removed: number;
  cutoffAt: string;
}

export class OpsAlertAuditTrail {
  constructor(private readonly filePath: string = path.join(process.cwd(), 'memory', 'alerts', 'ops-alert-delivery.ndjson')) {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
  }

  append(record: OpsAlertDeliveryRecord): void {
    fs.appendFileSync(this.filePath, `${JSON.stringify(record)}\n`, 'utf8');
  }

  list(filter: OpsAlertDeliveryFilter = {}): OpsAlertDeliveryRecord[] {
    const records = this.readAll();
    const sinceTs = filter.since ? Date.parse(filter.since) : Number.NaN;

    const filtered = records.filter((record) => {
      if (filter.channel && record.channel !== filter.channel) return false;
      if (filter.audience && record.audience !== filter.audience) return false;
      if (filter.severity && record.severity !== filter.severity) return false;
      if (filter.outcome && record.outcome !== filter.outcome) return false;
      if (filter.code && record.code !== filter.code) return false;
      if (Number.isFinite(sinceTs) && Date.parse(record.at) < sinceTs) return false;
      return true;
    });

    if (!filter.limit || filter.limit <= 0) return filtered;
    return filtered.slice(Math.max(0, filtered.length - filter.limit));
  }

  computeKpis(filter: OpsAlertDeliveryFilter = {}): OpsAlertDeliveryKpis {
    const records = this.list(filter);
    const totals = this.computeTotals(records);

    const byChannel: OpsAlertDeliveryKpis['byChannel'] = {
      webhook: this.computeTotals(records.filter((record) => record.channel === 'webhook')),
      email: this.computeTotals(records.filter((record) => record.channel === 'email')),
    };

    const byAudience: OpsAlertDeliveryKpis['byAudience'] = {
      'mission-commander': this.computeTotals(records.filter((record) => record.audience === 'mission-commander')),
      'ops-watch': this.computeTotals(records.filter((record) => record.audience === 'ops-watch')),
    };

    return {
      ...totals,
      byChannel,
      byAudience,
    };
  }

  applyRetention(days: number, now: Date = new Date()): OpsAlertRetentionResult {
    const safeDays = Number.isFinite(days) && days > 0 ? days : 0;
    const records = this.readAll();
    const before = records.length;
    const cutoffMs = now.getTime() - safeDays * 24 * 60 * 60 * 1000;
    const cutoffAt = new Date(cutoffMs).toISOString();

    const retained = safeDays === 0 ? records : records.filter((record) => Date.parse(record.at) >= cutoffMs);
    this.writeAll(retained);

    return {
      before,
      after: retained.length,
      removed: before - retained.length,
      cutoffAt,
    };
  }

  clear(): void {
    fs.writeFileSync(this.filePath, '', 'utf8');
  }

  private computeTotals(records: OpsAlertDeliveryRecord[]): {
    total: number;
    delivered: number;
    failed: number;
    deliveryRate: number;
    failureRate: number;
  } {
    const total = records.length;
    const delivered = records.filter((record) => record.outcome === 'delivered').length;
    const failed = total - delivered;
    const deliveryRate = total > 0 ? Number((delivered / total).toFixed(4)) : 0;
    const failureRate = total > 0 ? Number((failed / total).toFixed(4)) : 0;

    return {
      total,
      delivered,
      failed,
      deliveryRate,
      failureRate,
    };
  }

  private readAll(): OpsAlertDeliveryRecord[] {
    if (!fs.existsSync(this.filePath)) return [];
    return fs
      .readFileSync(this.filePath, 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as OpsAlertDeliveryRecord)
      .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  }

  private writeAll(records: OpsAlertDeliveryRecord[]): void {
    if (records.length === 0) {
      this.clear();
      return;
    }

    const payload = records.map((record) => JSON.stringify(record)).join('\n');
    fs.writeFileSync(this.filePath, `${payload}\n`, 'utf8');
  }
}

import fs from 'node:fs';
import path from 'node:path';

interface DlqReplaySummary {
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  total?: number;
  replayed?: number;
  failed?: number;
  remainingInDlq?: number;
  processed?: number;
  deferred?: number;
  stoppedByBackpressure?: boolean;
}

interface HealthSummary {
  generatedAt?: string;
  missionsTotal?: number;
  ok?: number;
  warn?: number;
  critical?: number;
}

export interface OpsAlert {
  code: 'OPS_LOCK_CONTENTION_RECURRING' | 'OPS_REPLAY_FAILURE_RATE_HIGH';
  severity: 'warn' | 'critical';
  message: string;
  channel: 'webhook' | 'email';
  audience: 'mission-commander' | 'ops-watch';
}

interface OpsAlertDedupRecord {
  lastEmittedAt: string;
}

type OpsAlertDedupState = Record<string, OpsAlertDedupRecord>;

export interface OpsStatusReport {
  generatedAt: string;
  dlq: {
    entries: number;
    lockActive: boolean;
    lockPath: string;
    lastReplay?: DlqReplaySummary;
    lockContention: {
      recentWindow: number;
      occurrences: number;
      recurring: boolean;
    };
  };
  health?: HealthSummary;
  trend: {
    window: number;
    samples: number;
    avgDlqEntries: number;
    avgReplayFailureRate: number;
  };
  alerts: OpsAlert[];
  alertsMeta: {
    rawCount: number;
    emittedCount: number;
    suppressedCount: number;
    suppressionWindowMinutes: number;
  };
}

export interface OpsStatusPaths {
  reportsDir: string;
  alertsDir: string;
}

export interface OpsStatusOptions {
  trendWindow?: number;
  lockContentionThreshold?: number;
  replayFailureRateWarn?: number;
  replayFailureRateCritical?: number;
  alertSuppressionWindowMinutes?: number;
  marketRegime?: 'normal' | 'elevated' | 'critical';
}

export class OpsStatusCollector {
  constructor(
    private readonly paths: OpsStatusPaths = {
      reportsDir: path.join(process.cwd(), 'memory', 'reports'),
      alertsDir: path.join(process.cwd(), 'memory', 'alerts'),
    },
  ) {
    fs.mkdirSync(this.paths.reportsDir, { recursive: true });
    fs.mkdirSync(this.paths.alertsDir, { recursive: true });
  }

  collect(options: OpsStatusOptions = {}): OpsStatusReport {
    const trendWindow = Math.max(1, options.trendWindow ?? 5);
    const lockContentionThreshold = Math.max(1, options.lockContentionThreshold ?? 2);
    const replayFailureRateWarn = clamp01(options.replayFailureRateWarn ?? 0.25);
    const replayFailureRateCritical = clamp01(options.replayFailureRateCritical ?? 0.5);
    const suppressionWindowMinutes = Math.max(0, options.alertSuppressionWindowMinutes ?? 30);
    const marketRegime = options.marketRegime ?? 'normal';
    const lockPath = path.join(this.paths.alertsDir, 'dlq.ndjson.lock');
    const dlqPath = path.join(this.paths.alertsDir, 'dlq.ndjson');
    const recentOps = this.readRecentOpsReports(trendWindow);
    const trend = this.buildTrend(recentOps, trendWindow);
    const lockOccurrences = recentOps.filter((x) => x.lockActive).length;

    const lockContention = {
      recentWindow: trendWindow,
      occurrences: lockOccurrences,
      recurring: lockOccurrences >= lockContentionThreshold,
    };

    const rawAlerts = this.buildAlerts({
      lockContention,
      trend,
      replayFailureRateWarn,
      replayFailureRateCritical,
      marketRegime,
    });
    const suppression = this.applySuppression(rawAlerts, suppressionWindowMinutes);

    const report: OpsStatusReport = {
      generatedAt: new Date().toISOString(),
      dlq: {
        entries: this.countNdjsonEntries(dlqPath),
        lockActive: fs.existsSync(lockPath),
        lockPath,
        lastReplay: this.readLatestDlqReplay(),
        lockContention,
      },
      health: this.readLatestHealthSummary(),
      trend,
      alerts: suppression.emitted,
      alertsMeta: {
        rawCount: rawAlerts.length,
        emittedCount: suppression.emitted.length,
        suppressedCount: suppression.suppressed,
        suppressionWindowMinutes,
      },
    };

    return report;
  }

  private dedupPath(): string {
    return path.join(this.paths.alertsDir, 'ops-alert-dedup.json');
  }

  private readDedupState(): OpsAlertDedupState {
    const file = this.dedupPath();
    if (!fs.existsSync(file)) return {};
    try {
      const parsed = JSON.parse(fs.readFileSync(file, 'utf8')) as unknown;
      if (!parsed || typeof parsed !== 'object') return {};
      return parsed as OpsAlertDedupState;
    } catch {
      return {};
    }
  }

  private writeDedupState(state: OpsAlertDedupState): void {
    fs.writeFileSync(this.dedupPath(), JSON.stringify(state, null, 2), 'utf8');
  }

  private applySuppression(
    alerts: OpsAlert[],
    windowMinutes: number,
  ): { emitted: OpsAlert[]; suppressed: number } {
    if (windowMinutes <= 0) return { emitted: alerts, suppressed: 0 };

    const state = this.readDedupState();
    const now = Date.now();
    const windowMs = windowMinutes * 60 * 1000;
    const emitted: OpsAlert[] = [];
    let suppressed = 0;

    for (const alert of alerts) {
      const key = `${alert.code}:${alert.severity}`;
      const last = state[key];
      const lastTs = last ? Date.parse(last.lastEmittedAt) : Number.NaN;
      const withinWindow = Number.isFinite(lastTs) && now - lastTs < windowMs;
      if (withinWindow) {
        suppressed += 1;
        continue;
      }

      emitted.push(alert);
      state[key] = { lastEmittedAt: new Date(now).toISOString() };
    }

    this.writeDedupState(state);
    return { emitted, suppressed };
  }

  private buildAlerts(input: {
    lockContention: OpsStatusReport['dlq']['lockContention'];
    trend: OpsStatusReport['trend'];
    replayFailureRateWarn: number;
    replayFailureRateCritical: number;
    marketRegime: 'normal' | 'elevated' | 'critical';
  }): OpsAlert[] {
    const alerts: OpsAlert[] = [];

    if (input.lockContention.recurring) {
      alerts.push({
        code: 'OPS_LOCK_CONTENTION_RECURRING',
        severity: this.adjustSeverityByRegime('warn', input.marketRegime),
        message: `DLQ lock contention recurring in ${input.lockContention.occurrences}/${input.lockContention.recentWindow} recent snapshots.`,
        channel: input.marketRegime === 'critical' ? 'webhook' : 'email',
        audience: input.marketRegime === 'critical' ? 'mission-commander' : 'ops-watch',
      });
    }

    if (input.trend.avgReplayFailureRate >= input.replayFailureRateCritical) {
      alerts.push({
        code: 'OPS_REPLAY_FAILURE_RATE_HIGH',
        severity: this.adjustSeverityByRegime('critical', input.marketRegime),
        message: `Average replay failure rate ${input.trend.avgReplayFailureRate} exceeded critical threshold ${input.replayFailureRateCritical}.`,
        channel: 'webhook',
        audience: 'mission-commander',
      });
    } else if (input.trend.avgReplayFailureRate >= input.replayFailureRateWarn) {
      const severity = this.adjustSeverityByRegime('warn', input.marketRegime);
      alerts.push({
        code: 'OPS_REPLAY_FAILURE_RATE_HIGH',
        severity,
        message: `Average replay failure rate ${input.trend.avgReplayFailureRate} exceeded warning threshold ${input.replayFailureRateWarn}.`,
        channel: severity === 'critical' ? 'webhook' : 'email',
        audience: severity === 'critical' ? 'mission-commander' : 'ops-watch',
      });
    }

    return alerts;
  }

  private adjustSeverityByRegime(base: OpsAlert['severity'], regime: 'normal' | 'elevated' | 'critical'): OpsAlert['severity'] {
    if (base === 'critical') return 'critical';
    if (regime === 'critical') return 'critical';
    return 'warn';
  }

  exportLatest(report: OpsStatusReport): string {
    const file = path.join(this.paths.reportsDir, `ops-status-${Date.now()}.json`);
    fs.writeFileSync(file, JSON.stringify(report, null, 2), 'utf8');
    return file;
  }

  private countNdjsonEntries(filePath: string): number {
    if (!fs.existsSync(filePath)) return 0;
    return fs
      .readFileSync(filePath, 'utf8')
      .split('\n')
      .filter(Boolean).length;
  }

  private readLatestDlqReplay(): DlqReplaySummary | undefined {
    const latest = this.findLatestByPrefix('dlq-replay-');
    if (!latest) return undefined;
    const parsed = this.safeParse(latest);
    if (!parsed || typeof parsed !== 'object') return undefined;
    const obj = parsed as Record<string, unknown>;
    return {
      startedAt: asOptionalString(obj.startedAt),
      finishedAt: asOptionalString(obj.finishedAt),
      durationMs: asOptionalNumber(obj.durationMs),
      total: asOptionalNumber(obj.total),
      replayed: asOptionalNumber(obj.replayed),
      failed: asOptionalNumber(obj.failed),
      remainingInDlq: asOptionalNumber(obj.remainingInDlq),
      processed: asOptionalNumber(obj.processed),
      deferred: asOptionalNumber(obj.deferred),
      stoppedByBackpressure: asOptionalBoolean(obj.stoppedByBackpressure),
    };
  }

  private readLatestHealthSummary(): HealthSummary | undefined {
    const latest = this.findLatestByPrefix('health-check-');
    if (!latest) return undefined;
    const parsed = this.safeParse(latest);
    if (!parsed || typeof parsed !== 'object') return undefined;
    const obj = parsed as Record<string, unknown>;
    return {
      generatedAt: asOptionalString(obj.generatedAt),
      missionsTotal: asOptionalNumber(obj.missionsTotal),
      ok: asOptionalNumber(obj.ok),
      warn: asOptionalNumber(obj.warn),
      critical: asOptionalNumber(obj.critical),
    };
  }

  private readRecentOpsReports(window: number): Array<{ dlqEntries: number; lockActive: boolean; replayFailureRate?: number }> {
    const files = fs
      .readdirSync(this.paths.reportsDir)
      .filter((name) => name.startsWith('ops-status-') && name.endsWith('.json'))
      .map((name) => path.join(this.paths.reportsDir, name))
      .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)
      .slice(0, window);

    return files
      .map((file) => this.safeParse(file))
      .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
      .map((obj) => {
        const dlq = obj.dlq as Record<string, unknown> | undefined;
        const lastReplay = dlq?.lastReplay as Record<string, unknown> | undefined;
        const replayed = asOptionalNumber(lastReplay?.replayed);
        const failed = asOptionalNumber(lastReplay?.failed);
        const total = (replayed ?? 0) + (failed ?? 0);
        const replayFailureRate = total > 0 ? (failed ?? 0) / total : undefined;

        return {
          dlqEntries: asOptionalNumber(dlq?.entries) ?? 0,
          lockActive: asOptionalBoolean(dlq?.lockActive) ?? false,
          replayFailureRate,
        };
      });
  }

  private buildTrend(
    samples: Array<{ dlqEntries: number; lockActive: boolean; replayFailureRate?: number }>,
    window: number,
  ): OpsStatusReport['trend'] {
    if (samples.length === 0) {
      return {
        window,
        samples: 0,
        avgDlqEntries: 0,
        avgReplayFailureRate: 0,
      };
    }

    const avgDlqEntries = samples.reduce((acc, s) => acc + s.dlqEntries, 0) / samples.length;
    const rates = samples.map((s) => s.replayFailureRate).filter((x): x is number => typeof x === 'number');
    const avgReplayFailureRate = rates.length > 0 ? rates.reduce((a, b) => a + b, 0) / rates.length : 0;

    return {
      window,
      samples: samples.length,
      avgDlqEntries: Number(avgDlqEntries.toFixed(2)),
      avgReplayFailureRate: Number(avgReplayFailureRate.toFixed(4)),
    };
  }

  private findLatestByPrefix(prefix: string): string | undefined {
    const files = fs
      .readdirSync(this.paths.reportsDir)
      .filter((name) => name.startsWith(prefix) && name.endsWith('.json'))
      .map((name) => path.join(this.paths.reportsDir, name));
    if (files.length === 0) return undefined;
    files.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
    return files[0];
  }

  private safeParse(filePath: string): unknown {
    try {
      return JSON.parse(fs.readFileSync(filePath, 'utf8')) as unknown;
    } catch {
      return undefined;
    }
  }
}

function asOptionalString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function asOptionalNumber(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined;
}

function asOptionalBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

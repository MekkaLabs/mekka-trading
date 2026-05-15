import fs from 'node:fs';
import path from 'node:path';
import { AppendOnlyStore } from './store/append-only-store';

export type HealthSeverity = 'ok' | 'warn' | 'critical';

export interface MissionHealth {
  missionId: string;
  eventsValid: boolean;
  auditsValid: boolean;
  eventsChecked: number;
  auditsChecked: number;
  severity: HealthSeverity;
  reason?: string;
}

export interface HealthReport {
  generatedAt: string;
  missionsTotal: number;
  ok: number;
  warn: number;
  critical: number;
  missions: MissionHealth[];
  retention: {
    alertsFiles: number;
    dlqEntries: number;
    oldestAlertFileAgeHours: number;
  };
}

export class ObservabilityHealthCheck {
  constructor(
    private readonly store: AppendOnlyStore = new AppendOnlyStore(),
    private readonly baseDir: string = path.join(process.cwd(), 'memory', 'audit-log'),
    private readonly outputDir: string = path.join(process.cwd(), 'memory', 'reports'),
  ) {
    fs.mkdirSync(this.outputDir, { recursive: true });
  }

  run(): HealthReport {
    const missionIds = this.listMissionIds();
    const missions: MissionHealth[] = missionIds.map((missionId) => {
      const events = this.store.verifyIntegrity('events', missionId);
      const audits = this.store.verifyIntegrity('audits', missionId);

      let severity: HealthSeverity = 'ok';
      let reason: string | undefined;

      if (!events.valid || !audits.valid) {
        severity = 'critical';
        reason = events.reason ?? audits.reason ?? 'Integrity check failure';
      } else if (events.checked === 0 || audits.checked === 0) {
        severity = 'warn';
        reason = 'Mission has incomplete stream data';
      }

      return {
        missionId,
        eventsValid: events.valid,
        auditsValid: audits.valid,
        eventsChecked: events.checked,
        auditsChecked: audits.checked,
        severity,
        reason,
      };
    });

    return {
      generatedAt: new Date().toISOString(),
      missionsTotal: missions.length,
      ok: missions.filter((m) => m.severity === 'ok').length,
      warn: missions.filter((m) => m.severity === 'warn').length,
      critical: missions.filter((m) => m.severity === 'critical').length,
      missions,
      retention: this.getRetentionMetrics(),
    };
  }

  exportLatest(): string {
    const report = this.run();
    const file = path.join(this.outputDir, `health-check-${Date.now()}.json`);
    fs.writeFileSync(file, JSON.stringify(report, null, 2), 'utf8');
    return file;
  }

  private listMissionIds(): string[] {
    if (!fs.existsSync(this.baseDir)) return [];

    const files = fs.readdirSync(this.baseDir);
    const ids = new Set<string>();

    for (const f of files) {
      const m = f.match(/^(mission-[^.]+)\.(events|audits)\.ndjson$/);
      if (m) ids.add(m[1]);
    }

    return Array.from(ids).sort();
  }

  private getRetentionMetrics(): { alertsFiles: number; dlqEntries: number; oldestAlertFileAgeHours: number } {
    const alertsDir = path.join(process.cwd(), 'memory', 'alerts');
    if (!fs.existsSync(alertsDir)) {
      return { alertsFiles: 0, dlqEntries: 0, oldestAlertFileAgeHours: 0 };
    }

    const files = fs
      .readdirSync(alertsDir)
      .map((name) => ({ name, full: path.join(alertsDir, name) }))
      .filter((f) => fs.statSync(f.full).isFile());

    const dlq = files.find((f) => f.name === 'dlq.ndjson');
    const dlqEntries =
      dlq && fs.existsSync(dlq.full)
        ? fs
            .readFileSync(dlq.full, 'utf8')
            .split('\n')
            .filter(Boolean).length
        : 0;

    if (files.length === 0) {
      return { alertsFiles: 0, dlqEntries, oldestAlertFileAgeHours: 0 };
    }

    const now = Date.now();
    const oldestMtime = Math.min(...files.map((f) => fs.statSync(f.full).mtimeMs));
    const oldestAlertFileAgeHours = Number(((now - oldestMtime) / (1000 * 60 * 60)).toFixed(2));

    return {
      alertsFiles: files.length,
      dlqEntries,
      oldestAlertFileAgeHours,
    };
  }
}

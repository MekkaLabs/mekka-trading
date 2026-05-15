import fs from 'node:fs';
import path from 'node:path';
import { AuditRecord } from '../audit-trail';
import { DomainEvent } from '../event-pipeline';
import { AppendOnlyStore, OBSERVABILITY_SCHEMA_VERSION } from '../store/append-only-store';

export interface MissionReport {
  missionId: string;
  generatedAt: string;
  schemaVersion: string;
  summary: {
    events: number;
    audits: number;
    firstEventAt?: string;
    lastEventAt?: string;
  };
  integrity: {
    events: { valid: boolean; checked: number; reason?: string };
    audits: { valid: boolean; checked: number; reason?: string };
  };
  timeline: DomainEvent[];
  auditTrail: AuditRecord[];
}

export class MissionReporter {
  constructor(
    private readonly store: AppendOnlyStore,
    private readonly outputDir: string = path.join(process.cwd(), 'memory', 'reports'),
  ) {
    fs.mkdirSync(this.outputDir, { recursive: true });
  }

  buildReport(missionId: string): MissionReport {
    const eventsEnvelopes = this.store.replay<DomainEvent>('events', missionId);
    const auditsEnvelopes = this.store.replay<AuditRecord>('audits', missionId);
    const events = eventsEnvelopes.map((e) => e.record);
    const audits = auditsEnvelopes.map((a) => a.record);

    const eventsIntegrity = this.store.verifyIntegrity<DomainEvent>('events', missionId);
    const auditsIntegrity = this.store.verifyIntegrity<AuditRecord>('audits', missionId);

    return {
      missionId,
      generatedAt: new Date().toISOString(),
      schemaVersion: OBSERVABILITY_SCHEMA_VERSION,
      summary: {
        events: events.length,
        audits: audits.length,
        firstEventAt: events[0]?.createdAt,
        lastEventAt: events.at(-1)?.createdAt,
      },
      integrity: {
        events: {
          valid: eventsIntegrity.valid,
          checked: eventsIntegrity.checked,
          reason: eventsIntegrity.reason,
        },
        audits: {
          valid: auditsIntegrity.valid,
          checked: auditsIntegrity.checked,
          reason: auditsIntegrity.reason,
        },
      },
      timeline: events,
      auditTrail: audits,
    };
  }

  exportReport(missionId: string): string {
    const report = this.buildReport(missionId);
    const file = path.join(this.outputDir, `${missionId}.report.json`);
    fs.writeFileSync(file, JSON.stringify(report, null, 2), 'utf8');
    return file;
  }
}

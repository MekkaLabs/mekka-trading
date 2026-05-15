import { AppendOnlyStore } from './store/append-only-store';
import type { SqliteMirror } from './sqlite-mirror';

export interface AuditRecord {
  kind: 'trade' | 'execution';
  actor: string;
  data: Record<string, unknown>;
  missionId?: string;
  timestamp: string;
}

export class AuditTrail {
  private readonly records: AuditRecord[] = [];

  constructor(
    private readonly store?: AppendOnlyStore,
    private readonly mirror?: SqliteMirror,
  ) {}

  add(kind: AuditRecord['kind'], actor: string, data: Record<string, unknown>, missionId?: string): AuditRecord {
    const record: AuditRecord = {
      kind,
      actor,
      data,
      missionId,
      timestamp: new Date().toISOString(),
    };
    this.records.push(record);
    if (this.store && missionId) {
      this.store.append('audits', missionId, record);
    }
    // Story 032b — mirror to SQLite for Python pipeline visibility
    this.mirror?.mirrorAudit(record);
    return record;
  }

  all(): AuditRecord[] {
    return [...this.records];
  }
}

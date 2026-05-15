import { AppendOnlyStore } from './store/append-only-store';

export interface AuditRecord {
  kind: 'trade' | 'execution';
  actor: string;
  data: Record<string, unknown>;
  missionId?: string;
  timestamp: string;
}

export class AuditTrail {
  private readonly records: AuditRecord[] = [];

  constructor(private readonly store?: AppendOnlyStore) {}

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
    return record;
  }

  all(): AuditRecord[] {
    return [...this.records];
  }
}

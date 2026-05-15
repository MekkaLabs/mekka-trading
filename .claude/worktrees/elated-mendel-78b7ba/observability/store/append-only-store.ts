import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const OBSERVABILITY_SCHEMA_VERSION = '1.0.0';

export interface PersistedEnvelope<T> {
  schemaVersion: string;
  stream: 'events' | 'audits';
  missionId: string;
  prevHash: string;
  hash: string;
  record: T;
}

export interface IntegrityCheckResult {
  valid: boolean;
  checked: number;
  brokenAt?: number;
  reason?: string;
}

function computeHash<T>(input: {
  schemaVersion: string;
  stream: 'events' | 'audits';
  missionId: string;
  prevHash: string;
  record: T;
}): string {
  return crypto.createHash('sha256').update(JSON.stringify(input)).digest('hex');
}

export class AppendOnlyStore {
  constructor(private readonly baseDir: string = path.join(process.cwd(), 'memory', 'audit-log')) {
    fs.mkdirSync(this.baseDir, { recursive: true });
  }

  append<T>(stream: 'events' | 'audits', missionId: string, record: T): void {
    const file = this.filePath(stream, missionId);
    const prevHash = this.readHeadHash(stream, missionId) ?? 'GENESIS';

    const base = {
      schemaVersion: OBSERVABILITY_SCHEMA_VERSION,
      stream,
      missionId,
      prevHash,
      record,
    };

    const envelope: PersistedEnvelope<T> = {
      ...base,
      hash: computeHash(base),
    };

    fs.appendFileSync(file, `${JSON.stringify(envelope)}\n`, 'utf8');
    this.writeHeadHash(stream, missionId, envelope.hash);
  }

  replay<T>(stream: 'events' | 'audits', missionId: string): PersistedEnvelope<T>[] {
    const file = this.filePath(stream, missionId);
    if (!fs.existsSync(file)) return [];

    return fs
      .readFileSync(file, 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as PersistedEnvelope<T>);
  }

  verifyIntegrity<T>(stream: 'events' | 'audits', missionId: string): IntegrityCheckResult {
    const records = this.replay<T>(stream, missionId);
    let expectedPrev = 'GENESIS';

    for (let i = 0; i < records.length; i += 1) {
      const r = records[i];
      if (r.schemaVersion !== OBSERVABILITY_SCHEMA_VERSION) {
        return {
          valid: false,
          checked: i,
          brokenAt: i,
          reason: `Schema mismatch at entry ${i}`,
        };
      }

      if (r.prevHash !== expectedPrev) {
        return {
          valid: false,
          checked: i,
          brokenAt: i,
          reason: `Broken hash chain at entry ${i}`,
        };
      }

      const recalculated = computeHash({
        schemaVersion: r.schemaVersion,
        stream: r.stream,
        missionId: r.missionId,
        prevHash: r.prevHash,
        record: r.record,
      });

      if (recalculated !== r.hash) {
        return {
          valid: false,
          checked: i,
          brokenAt: i,
          reason: `Invalid hash at entry ${i}`,
        };
      }

      expectedPrev = r.hash;
    }

    return { valid: true, checked: records.length };
  }

  tamperLine(stream: 'events' | 'audits', missionId: string, lineIndex: number, replacement: string): void {
    const file = this.filePath(stream, missionId);
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    if (lineIndex < 0 || lineIndex >= lines.length || !lines[lineIndex]) return;
    lines[lineIndex] = replacement;
    fs.writeFileSync(file, lines.join('\n'), 'utf8');
  }

  private filePath(stream: 'events' | 'audits', missionId: string): string {
    return path.join(this.baseDir, `${missionId}.${stream}.ndjson`);
  }

  private headPath(stream: 'events' | 'audits', missionId: string): string {
    return path.join(this.baseDir, `${missionId}.${stream}.head`);
  }

  private readHeadHash(stream: 'events' | 'audits', missionId: string): string | undefined {
    const file = this.headPath(stream, missionId);
    if (!fs.existsSync(file)) return undefined;
    const value = fs.readFileSync(file, 'utf8').trim();
    return value || undefined;
  }

  private writeHeadHash(stream: 'events' | 'audits', missionId: string, hash: string): void {
    fs.writeFileSync(this.headPath(stream, missionId), hash, 'utf8');
  }
}

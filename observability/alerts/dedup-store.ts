import fs from 'node:fs';
import path from 'node:path';

export interface DedupRecord {
  key: string;
  lastSentAt: string;
}

export class AlertDedupStore {
  private readonly records = new Map<string, string>();

  constructor(private readonly filePath: string = path.join(process.cwd(), 'memory', 'alerts', 'dedup.json')) {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
    this.load();
  }

  shouldDispatch(key: string, now: Date, windowMinutes: number): boolean {
    const last = this.records.get(key);
    if (!last) return true;

    const diffMs = now.getTime() - new Date(last).getTime();
    return diffMs >= windowMinutes * 60_000;
  }

  markDispatched(key: string, now: Date): void {
    this.records.set(key, now.toISOString());
    this.save();
  }

  clear(): void {
    this.records.clear();
    this.save();
  }

  private load(): void {
    if (!fs.existsSync(this.filePath)) return;
    const raw = fs.readFileSync(this.filePath, 'utf8');
    if (!raw.trim()) return;
    const parsed = JSON.parse(raw) as DedupRecord[];
    for (const item of parsed) {
      this.records.set(item.key, item.lastSentAt);
    }
  }

  private save(): void {
    const lockDir = `${this.filePath}.lock`;
    const tmp = `${this.filePath}.tmp`;

    try {
      fs.mkdirSync(lockDir);
      const out: DedupRecord[] = Array.from(this.records.entries()).map(([key, lastSentAt]) => ({ key, lastSentAt }));
      fs.writeFileSync(tmp, JSON.stringify(out, null, 2), 'utf8');
      fs.renameSync(tmp, this.filePath);
    } finally {
      if (fs.existsSync(tmp)) fs.rmSync(tmp, { force: true });
      if (fs.existsSync(lockDir)) fs.rmdirSync(lockDir);
    }
  }
}

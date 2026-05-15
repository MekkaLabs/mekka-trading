import fs from 'node:fs';
import path from 'node:path';

export interface RetentionPolicy {
  maxAgeDays: number;
  maxFiles: number;
}

export interface RetentionReport {
  scannedAt: string;
  scanned: number;
  removed: number;
  kept: number;
  removedByAge: number;
  removedByCapacity: number;
}

export class AlertsRetentionManager {
  constructor(
    private readonly alertsDir: string = path.join(process.cwd(), 'memory', 'alerts'),
    private readonly policy: RetentionPolicy = { maxAgeDays: 7, maxFiles: 50 },
  ) {
    fs.mkdirSync(this.alertsDir, { recursive: true });
  }

  enforce(): RetentionReport {
    const scannedAt = new Date().toISOString();
    const files = fs
      .readdirSync(this.alertsDir)
      .map((name) => ({ name, full: path.join(this.alertsDir, name) }))
      .filter((f) => fs.statSync(f.full).isFile())
      .sort((a, b) => fs.statSync(b.full).mtimeMs - fs.statSync(a.full).mtimeMs);

    let removed = 0;
    let removedByAge = 0;
    let removedByCapacity = 0;
    const now = Date.now();
    const maxAgeMs = this.policy.maxAgeDays * 24 * 60 * 60 * 1000;

    for (const f of files) {
      const ageMs = now - fs.statSync(f.full).mtimeMs;
      if (ageMs > maxAgeMs) {
        fs.rmSync(f.full, { force: true });
        removed += 1;
        removedByAge += 1;
      }
    }

    const remaining = fs
      .readdirSync(this.alertsDir)
      .map((name) => ({ name, full: path.join(this.alertsDir, name) }))
      .filter((f) => fs.statSync(f.full).isFile())
      .sort((a, b) => fs.statSync(b.full).mtimeMs - fs.statSync(a.full).mtimeMs);

    if (remaining.length > this.policy.maxFiles) {
      const toDelete = remaining.slice(this.policy.maxFiles);
      for (const f of toDelete) {
        fs.rmSync(f.full, { force: true });
        removed += 1;
        removedByCapacity += 1;
      }
    }

    const kept = fs
      .readdirSync(this.alertsDir)
      .map((name) => ({ full: path.join(this.alertsDir, name) }))
      .filter((f) => fs.statSync(f.full).isFile()).length;

    return {
      scannedAt,
      scanned: files.length,
      removed,
      kept,
      removedByAge,
      removedByCapacity,
    };
  }
}

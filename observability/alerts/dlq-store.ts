import fs from 'node:fs';
import path from 'node:path';
import { AlertMessage } from './dispatchers';

export interface DlqEntry {
  failedAt: string;
  dispatcher: string;
  error: string;
  message: AlertMessage;
}

export class AlertDlqStore {
  constructor(private readonly filePath: string = path.join(process.cwd(), 'memory', 'alerts', 'dlq.ndjson')) {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
  }

  push(entry: DlqEntry): void {
    fs.appendFileSync(this.filePath, `${JSON.stringify(entry)}\n`, 'utf8');
  }

  list(): DlqEntry[] {
    if (!fs.existsSync(this.filePath)) return [];
    return fs
      .readFileSync(this.filePath, 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as DlqEntry);
  }

  replace(entries: DlqEntry[]): void {
    const content = entries.map((e) => JSON.stringify(e)).join('\n');
    fs.writeFileSync(this.filePath, content.length > 0 ? `${content}\n` : '', 'utf8');
  }

  clear(): void {
    fs.writeFileSync(this.filePath, '', 'utf8');
  }

  getPath(): string {
    return this.filePath;
  }
}

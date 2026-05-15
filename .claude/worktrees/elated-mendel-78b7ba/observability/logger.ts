export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEvent {
  level: LogLevel;
  message: string;
  context?: Record<string, unknown>;
  timestamp: string;
}

export class Logger {
  log(event: Omit<LogEvent, 'timestamp'>): void {
    const payload: LogEvent = { ...event, timestamp: new Date().toISOString() };
    console.log(JSON.stringify(payload));
  }

  info(message: string, context?: Record<string, unknown>): void {
    this.log({ level: 'info', message, context });
  }

  warn(message: string, context?: Record<string, unknown>): void {
    this.log({ level: 'warn', message, context });
  }

  error(message: string, context?: Record<string, unknown>): void {
    this.log({ level: 'error', message, context });
  }
}

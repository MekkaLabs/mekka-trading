import { AppendOnlyStore } from './store/append-only-store';
import type { SqliteMirror } from './sqlite-mirror';

export interface DomainEvent {
  type: string;
  source: string;
  payload: Record<string, unknown>;
  missionId?: string;
  createdAt: string;
}

export class EventPipeline {
  private readonly events: DomainEvent[] = [];

  constructor(
    private readonly store?: AppendOnlyStore,
    private readonly mirror?: SqliteMirror,
  ) {}

  publish(type: string, source: string, payload: Record<string, unknown>, missionId?: string): DomainEvent {
    const event: DomainEvent = {
      type,
      source,
      payload,
      missionId,
      createdAt: new Date().toISOString(),
    };
    this.events.push(event);
    if (this.store && missionId) {
      this.store.append('events', missionId, event);
    }
    // Story 032b — mirror to SQLite for Python pipeline visibility
    this.mirror?.mirrorEvent(event);
    return event;
  }

  list(): DomainEvent[] {
    return [...this.events];
  }
}

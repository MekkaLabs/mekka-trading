import { AppendOnlyStore } from './store/append-only-store';

export interface DomainEvent {
  type: string;
  source: string;
  payload: Record<string, unknown>;
  missionId?: string;
  createdAt: string;
}

export class EventPipeline {
  private readonly events: DomainEvent[] = [];

  constructor(private readonly store?: AppendOnlyStore) {}

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
    return event;
  }

  list(): DomainEvent[] {
    return [...this.events];
  }
}

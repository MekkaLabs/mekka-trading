# Story 013 - Dead-Letter Queue and Jitter Retry

## Goal

Add resilience for permanent alert failures and reduce synchronized retry bursts.

## Delivered

- Dead-letter queue store (`memory/alerts/dlq.ndjson`)
- Alert orchestrator integration with DLQ fallback on dispatch failure
- Retry policy enhanced with optional jitter
- Tests for DLQ path and jitter-safe retry behavior

## Checklist

- [x] DLQ store implemented
- [x] Orchestrator writes failed alerts to DLQ
- [x] Retry jitter support added
- [x] Automated tests added
- [x] Paper-only safety preserved

## Next

- Add DLQ replay command
- Add per-channel circuit breaker
- Add DLQ retention and rotation policy

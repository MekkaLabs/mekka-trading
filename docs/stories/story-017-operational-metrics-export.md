# Story 017 - Operational Metrics Export

## Goal

Provide operational visibility for alerts infrastructure with structured export focused on DLQ, lock contention, replay outcomes, and breaker state.

## Delivered

- New `ops-status` collector and CLI:
  - `run:ops-status`
  - emits consolidated operational report
  - persists snapshot into `memory/reports/ops-status-*.json`
- DLQ replay CLI now persists structured replay reports in `memory/reports/dlq-replay-*.json`
- Circuit breaker now exposes runtime `snapshot()` for observability
- Replay output now includes breaker snapshots (webhook/email)
- Tests for:
  - ops status collector summary extraction
  - circuit breaker snapshot integrity

## Checklist

- [x] Structured operational metrics implemented
- [x] Replay report persistence implemented
- [x] Breaker snapshot export implemented
- [x] Ops status CLI implemented
- [x] Tests added and passing
- [x] Paper-only safety preserved

## Next

- Add trend view for last N ops snapshots
- Emit thresholds/alerts when lock contention repeats
- Integrate ops snapshot into automated heartbeat routine

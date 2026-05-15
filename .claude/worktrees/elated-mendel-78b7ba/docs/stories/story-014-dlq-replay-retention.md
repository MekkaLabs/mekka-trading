# Story 014 - DLQ Replay and Alerts Retention

## Goal

Improve alert operations with DLQ reprocessing and retention/rotation controls.

## Delivered

- DLQ replayer with success/failure accounting
- DLQ rewrite to keep only unresolved failures
- Replay operational metrics:
  - started/finished timestamps
  - duration
  - remaining DLQ size
  - per-channel replay/failure counters
- Alerts retention manager:
  - max age policy
  - max files policy
  - retention operational metrics (kept, removed by age, removed by capacity)
- CLI commands:
  - `npm run run:replay-dlq`
  - `npm run run:alerts-retention`
- Automated tests for replay and retention behavior
- Partial replay failure test ensuring failed-only persistence

## Checklist

- [x] DLQ replay implemented
- [x] Failed-only persistence in DLQ after replay
- [x] Replay metrics/hardening implemented
- [x] Retention manager implemented
- [x] Retention metrics/hardening implemented
- [x] CLI commands added
- [x] Tests added
- [x] Partial-failure behavior validated
- [x] Paper-only safety preserved

## Next

- Add cron/heartbeat automation for DLQ replay
- Add retention metrics to health-check output
- Add replay backpressure controls

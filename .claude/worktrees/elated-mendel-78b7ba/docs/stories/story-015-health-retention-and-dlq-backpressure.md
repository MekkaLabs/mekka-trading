# Story 015 - Health Retention Metrics and DLQ Backpressure

## Goal

Increase observability operations safety with retention visibility in health-check and controlled DLQ replay throughput.

## Delivered

- `ObservabilityHealthCheck` now includes retention metrics in report output:
  - `alertsFiles`
  - `dlqEntries`
  - `oldestAlertFileAgeHours`
- DLQ replay now supports backpressure controls:
  - `batchSize`
  - `maxFailures`
  - report fields for `processed`, `deferred`, and `stoppedByBackpressure`
- CLI replay integration using environment variables:
  - `MEKKA_DLQ_REPLAY_BATCH_SIZE`
  - `MEKKA_DLQ_REPLAY_MAX_FAILURES`
- Tests expanded for:
  - partial replay failure persistence
  - batch/failure backpressure behavior
  - health-check retention metrics presence

## Checklist

- [x] Health-check retention metrics added
- [x] DLQ backpressure controls implemented
- [x] Replay report enriched with operational counters
- [x] CLI integration completed
- [x] Tests added and passing
- [x] Paper-only safety preserved

## Next

- Add scheduler-safe replay lock to avoid overlapping replay runs
- Add SLO-style thresholds and severity escalation for retention age
- Add per-channel circuit breaker for repeated downstream failures

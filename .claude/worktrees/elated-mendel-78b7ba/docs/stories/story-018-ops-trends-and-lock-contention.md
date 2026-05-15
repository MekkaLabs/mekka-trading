# Story 018 - Ops Trends and Lock Contention Signals

## Goal

Advance operational observability by adding trend analysis and recurring lock-contention detection to `ops-status`.

## Delivered

- `ops-status` now includes trend metrics:
  - `window`
  - `samples`
  - `avgDlqEntries`
  - `avgReplayFailureRate`
- `ops-status` now includes lock contention signal:
  - occurrences in recent window
  - recurring contention boolean
- Configurable via environment variables:
  - `MEKKA_OPS_TREND_WINDOW`
  - `MEKKA_OPS_LOCK_CONTENTION_THRESHOLD`
- Test coverage expanded for trend and contention signals

## Checklist

- [x] Trend metrics implemented
- [x] Lock contention recurrence detection implemented
- [x] CLI runtime configuration implemented
- [x] Tests added and passing
- [x] Paper-only safety preserved

## Next

- Emit high-contention/failed-replay alerts from ops-status
- Add SLA thresholds for avg replay failure rate
- Add rolling 24h aggregation snapshots

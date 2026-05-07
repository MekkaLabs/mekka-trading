# Story 019 - Ops Threshold Alerting

## Goal

Enable automatic operational alerting from `ops-status` based on lock contention recurrence and replay failure-rate thresholds.

## Delivered

- `ops-status` now emits structured `alerts` array
- Alert rules implemented:
  - recurring lock contention -> `OPS_LOCK_CONTENTION_RECURRING` (`warn`)
  - replay failure rate high -> `OPS_REPLAY_FAILURE_RATE_HIGH` (`warn`/`critical`)
- Configurable thresholds via environment variables:
  - `MEKKA_OPS_REPLAY_FAILURE_WARN` (default `0.25`)
  - `MEKKA_OPS_REPLAY_FAILURE_CRITICAL` (default `0.5`)
- `run:ops-status` now exits with code `2` when critical ops alerts are detected
- Test coverage updated for alert emission behavior

## Checklist

- [x] Threshold-based ops alerts implemented
- [x] Recurring lock contention alert implemented
- [x] Replay failure rate alert implemented
- [x] CLI critical exit behavior implemented
- [x] Tests updated and passing
- [x] Paper-only safety preserved

## Next

- Route ops alerts to dedicated mission commander channel
- Add suppression window to avoid repeated identical ops alerts
- Add severity mapping by market regime context

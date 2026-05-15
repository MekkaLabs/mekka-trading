# Story 016 - Replay Lock and Alert Circuit Breaker

## Goal

Prevent concurrent DLQ replay collisions and reduce repeated downstream alert failures.

## Delivered

- DLQ replay lock file (`*.lock`) with fail-fast behavior
- Dedicated `DlqReplayLockError` for operational handling
- CLI replay exit code for lock contention (`3`)
- Circuit breaker dispatcher wrapper with:
  - failure threshold
  - cooldown window
  - open/half-open/closed state transitions
- Health-check and DLQ replay CLIs now run dispatchers behind circuit breakers
- Tests for:
  - lock contention
  - circuit open behavior after threshold

## Checklist

- [x] Replay lock implemented
- [x] Lock contention error handling implemented
- [x] Circuit breaker implemented
- [x] CLI integration completed
- [x] Tests added and passing
- [x] Paper-only safety preserved

## Next

- Add persisted circuit state snapshots for process restarts
- Add structured metrics export for breaker state and lock contention rates
- Add replay scheduling guardrail with jittered startup offsets

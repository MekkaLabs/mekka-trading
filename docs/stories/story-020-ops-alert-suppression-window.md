# Story 020 - Ops Alert Suppression Window

## Goal

Avoid operational alert spam by suppressing repeated identical ops alerts within a configurable time window.

## Delivered

- Temporal suppression store for ops alerts in `memory/alerts/ops-alert-dedup.json`
- Suppression controls in `ops-status` collector:
  - `alertSuppressionWindowMinutes` (default `30`)
- `ops-status` report metadata now includes:
  - `rawCount`
  - `emittedCount`
  - `suppressedCount`
  - `suppressionWindowMinutes`
- CLI support via:
  - `MEKKA_OPS_ALERT_SUPPRESSION_MINUTES`
- Tests validating suppression behavior across consecutive runs

## Checklist

- [x] Suppression window implemented
- [x] Dedup state persistence implemented
- [x] Alert meta counters implemented
- [x] CLI integration implemented
- [x] Tests added and passing
- [x] Paper-only safety preserved

## Next

- Add suppression reset strategy per mission context
- Add observability for dedup state age and cardinality
- Add explicit alert grouping for multi-channel routing

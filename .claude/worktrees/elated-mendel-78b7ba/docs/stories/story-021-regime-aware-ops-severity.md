# Story 021 - Regime-Aware Ops Severity

## Goal

Adjust operational alert severity according to market regime risk context.

## Delivered

- `ops-status` now accepts market regime context:
  - `normal`
  - `elevated`
  - `critical`
- Regime-aware severity mapping:
  - base `critical` remains `critical`
  - base `warn` escalates to `critical` when regime is `critical`
- CLI support via:
  - `MEKKA_OPS_MARKET_REGIME`
- Tests validating severity escalation behavior under critical regime

## Checklist

- [x] Regime context input implemented
- [x] Severity mapping rules implemented
- [x] CLI integration implemented
- [x] Tests added and passing
- [x] Paper-only safety preserved

## Next

- Calibrate severity by regime + drawdown bands
- Add policy file for custom severity mapping
- Route critical ops alerts to mission commander escalation path

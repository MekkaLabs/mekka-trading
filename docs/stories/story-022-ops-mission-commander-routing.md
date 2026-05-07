# Story 022 - Ops Mission Commander Routing

## Goal

Route operational alerts to explicit channels and audiences, escalating critical ops signals to mission commander flow.

## Delivered

- `OpsAlert` now carries:
  - `channel` (`webhook` | `email`)
  - `audience` (`mission-commander` | `ops-watch`)
- Severity + regime aware channel routing:
  - critical -> webhook / mission-commander
  - warn -> email / ops-watch (unless escalated to critical by regime)
- New ops alert dispatch router:
  - `observability/alerts/ops-alert-router.ts`
- New CLI command:
  - `npm run run:ops-alerts`
  - builds ops-status snapshot and dispatches routed ops alerts
- Test coverage for channel routing and dispatch counts

## Checklist

- [x] Channel/audience model implemented
- [x] Mission commander escalation path implemented
- [x] Ops alert router implemented
- [x] CLI integration implemented
- [x] Tests added and passing
- [x] Paper-only safety preserved

## Next

- Add delivery audit trail for ops alerts
- Add per-audience delivery retries and SLOs
- Add external webhook/email adapter interfaces (still mock by default)

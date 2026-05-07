# Story 010 - Alert Dispatch and Severity Routing

## Goal

Add operational alert dispatch routing based on health-check severity for proactive monitoring.

## Delivered

- Alert dispatcher interfaces and mock adapters:
  - console-webhook
  - console-email
- Routing policy:
  - `critical` -> webhook channel
  - `warn` -> email channel
- Health-check CLI now dispatches alerts and reports `alertsDispatched`
- Test coverage for routing behavior

## Checklist

- [x] Dispatcher abstraction
- [x] Severity-based routing
- [x] Health-check integration
- [x] Dispatch count in output
- [x] Automated test
- [x] Paper-only safety preserved

## Next

- Add real webhook adapter with signed payload
- Add SMTP/provider adapter with retry policy
- Add dedup window to avoid alert storms

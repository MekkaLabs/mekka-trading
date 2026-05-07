# Story 024 - Ops Alert Audit KPIs, Inspection CLI, and Retention

## Context
Story 23 introduced append-only delivery auditing for ops alerts (`delivered`/`failed`).
Story 24 extends it with aggregate delivery KPIs, CLI-level inspection, and retention policy controls.

## Scope
- Add aggregate KPIs by channel and audience.
- Add filtering and inspection for audit records.
- Add retention policy for the delivery audit trail.

## Deliverables
- `observability/alerts/ops-alert-audit-trail.ts`
  - filtering by channel/audience/severity/outcome/code/since/limit
  - aggregate KPIs (`deliveryRate`, `failureRate`) global and by channel/audience
  - retention by age in days with structured prune result
- `cli/ops-alert-audit.ts`
  - inspection/export of filtered records + KPIs
  - optional retention execution before inspection
  - non-zero exit when failed deliveries are present
- `tests/ops-alert-audit-trail.test.ts`
  - KPI aggregation coverage
  - filter + retention coverage
- `package.json`
  - script `run:ops-alert-audit`

## Operational Environment Variables
- `MEKKA_OPS_ALERT_AUDIT_CHANNEL`
- `MEKKA_OPS_ALERT_AUDIT_AUDIENCE`
- `MEKKA_OPS_ALERT_AUDIT_SEVERITY`
- `MEKKA_OPS_ALERT_AUDIT_OUTCOME`
- `MEKKA_OPS_ALERT_AUDIT_CODE`
- `MEKKA_OPS_ALERT_AUDIT_SINCE_MINUTES`
- `MEKKA_OPS_ALERT_AUDIT_LIMIT`
- `MEKKA_OPS_ALERT_AUDIT_RETENTION_DAYS`

## Acceptance
- KPI output is deterministic for the same audit input.
- Filtering works without mutating source records.
- Retention removes only records older than cutoff.
- CLI output is structured JSON and includes `kpis`, `records`, and `retention` (when applied).

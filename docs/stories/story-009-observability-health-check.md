# Story 009 - Observability Health Check and Alert Policy

## Goal

Provide an operational health-check layer that scans mission integrity and outputs actionable alert severity.

## Delivered

- Observability health check service
- Severity policy:
  - `ok`: streams intact
  - `warn`: incomplete mission stream
  - `critical`: integrity failure/tamper detected
- Exported health report (`memory/reports/health-check-*.json`)
- CLI command:
  - `npm run run:health-check`
- CI-friendly non-zero exit on critical findings

## Checklist

- [x] Mission scan implemented
- [x] Alert severity policy implemented
- [x] Health report export implemented
- [x] CLI command implemented
- [x] Tests for normal and critical path
- [x] Paper-only safety preserved

## Next

- Schedule recurring health checks
- Add alert dispatch adapters (email/webhook)
- Add SLA metrics over rolling windows

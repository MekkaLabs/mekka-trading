# Story 006 - Mission Report Export

## Goal

Provide a structured mission report export with timeline and audit trail for operational review and post-mission analysis.

## Delivered

- Mission reporter module
- JSON export in `memory/reports/<mission-id>.report.json`
- Runtime API for report export
- CLI command:
  - `npm run run:export-report -- <mission-id>`
- Automated tests for export integrity

## Checklist

- [x] Mission summary export
- [x] Timeline export (events)
- [x] Audit trail export
- [x] CLI report export
- [x] Regression test
- [x] Paper-only safety preserved

## Next

- Add signed report manifests
- Add compressed archival bundles for long missions
- Add redaction layer for sensitive metadata

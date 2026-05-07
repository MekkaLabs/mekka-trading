# Story 011 - Alert Deduplication and Anti-Storm Window

## Goal

Prevent alert storms by suppressing duplicate health alerts within a configurable time window.

## Delivered

- Persistent dedup store (`memory/alerts/dedup.json`)
- Dedup key strategy by severity + mission + subject
- Configurable dedup window (default: 30 minutes)
- Alert suppression integrated into dispatch orchestrator
- Tests for normal dispatch and duplicate suppression

## Checklist

- [x] Dedup store implemented
- [x] Time window policy implemented
- [x] Dispatcher integration completed
- [x] Duplicate suppression tested
- [x] Paper-only safety preserved

## Next

- Add per-severity dedup windows
- Add burst-threshold escalation path
- Add alert suppression observability metrics

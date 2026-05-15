# Story 004 - Append-Only Observability and Replay

## Goal

Create persistent append-only observability streams and mission replay capability for operational investigation.

## Delivered

- Append-only NDJSON store for:
  - event stream
  - audit stream
- Mission-scoped persistence (`missionId` propagated)
- Runtime replay API (`replayMission`)
- CLI replay command (`npm run run:replay -- <mission-id>`)
- Regression tests for persistence and replay

## Checklist

- [x] Persistent event store adapter
- [x] Persistent audit store adapter
- [x] Mission metadata propagation
- [x] Replay capability by mission id
- [x] CLI replay command
- [x] Tests for replay integrity
- [x] Paper-only safety preserved

## Next

- Add event schema versioning and signatures
- Add mission timeline visualization export
- Add retention policy + compaction strategy (without mutating append-only source)

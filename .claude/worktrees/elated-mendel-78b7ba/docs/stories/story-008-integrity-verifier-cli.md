# Story 008 - Offline Integrity Verifier CLI

## Goal

Provide offline integrity verification tooling and operational alerting for tamper-evident observability streams.

## Delivered

- Integrity verifier runtime API (`verifyMissionIntegrity`)
- CLI command:
  - `npm run run:verify-integrity -- <mission-id>`
- Non-zero exit on integrity failure (CI-friendly)
- Optional store tamper helper for controlled test simulation
- Tests for valid and tampered streams

## Checklist

- [x] Offline verifier API
- [x] CLI verifier
- [x] Non-zero exit on failure
- [x] Tamper detection test
- [x] Paper-only safety preserved

## Next

- Wire verifier into scheduled health checks
- Add alert routing policy for integrity failures
- Export signed integrity attestations

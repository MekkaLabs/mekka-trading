# Story 039 — DailyPerformanceWriter

## Context

Story 034 delivered Deadpool, a deterministic analytics agent that can produce a
`PerformanceReport` on demand. Story 038 wired Deadpool into the dashboard's
`/api/performance` endpoint. But neither story persisted the result — every
call to `/api/performance` re-computed from scratch and left no historical
record.

Story 039 closes that loop: a lightweight service (`DailyPerformanceWriter`)
runs Deadpool exactly once per UTC calendar day, upserts the result into the
`perf_reports` table, and emits a `DAILY_PERF_REPORT` audit event so the full
payload is replay-queryable.

---

## Goal

- Guarantee one Deadpool snapshot per UTC day is written to `perf_reports`
- Provide upsert semantics so a second run on the same day overwrites, not
  duplicates
- Surface the result via audit log so Deadpool's own history is recoverable
- Enable future gate H2 historical tracking without touching existing code

---

## Scope Delivered

### `src/persistence/models.py`
- Added `PerfReportRecord` (table `perf_reports`):
  `id, date_utc (unique), verdict, win_rate_pct, total_pnl_usd,
  max_drawdown_pct, wolverine_endorse_pct, days_with_data, payload, created_at`

### `src/persistence/repository.py`
- `save_perf_report(date_utc, verdict, …, payload)` — upsert (delete+insert)
  keyed on `date_utc`; returns row id
- `get_latest_perf_report()` — most recent `PerfReportRecord` by `date_utc`,
  or `None`

### `src/services/daily_performance_writer.py`
- `DailyPerformanceWriter(repo, *, window_days=30)`
  - `maybe_run() → bool` — runs only if `_last_run_date != today_utc`;
    returns `True` when a new report was written
  - `run_now(*, today=None)` — forces a Deadpool run unconditionally; used by
    tests and manual triggers
  - Uses `Deadpool = None` module-level sentinel for patchability in tests

### `tests/test_phase18_daily_perf_writer.py`
- 25 tests covering: date gate, upsert semantics, correct field mapping,
  audit event emission, sentinel patching, repository read/write with
  in-memory SQLite

---

## Hard Rules Maintained

- No test touches the real SQLite database (`MEKKA_DB_URL = sqlite+aiosqlite://`)
- Deadpool never imported at module level — sentinel pattern preserved
- `save_perf_report` is idempotent: two calls for the same date produce one row

---

## Acceptance

```
pytest tests/test_phase18_daily_perf_writer.py -v   # all green
pytest -x -q                                         # full suite green
```

---

## What's Next

- Wire `DailyPerformanceWriter.maybe_run()` into Nick Fury's main loop
- Story 040: `/api/perf_history` dashboard endpoint reading `perf_reports`
- Gate H2 auto-check can query `get_latest_perf_report()` for cached results

---

## Files Changed

| File | Change |
|------|--------|
| `src/persistence/models.py` | Added `PerfReportRecord` |
| `src/persistence/repository.py` | Added `save_perf_report`, `get_latest_perf_report`; imported `PerfReportRecord` |
| `src/services/daily_performance_writer.py` | NEW — `DailyPerformanceWriter` service |
| `tests/test_phase18_daily_perf_writer.py` | NEW — 25 tests |
| `docs/stories/story-039-daily-perf-writer.md` | NEW (this file) |
| `docs/stories/INDEX.md` | Added Milestone 12, stories 038–039 |
| `docs/HANDOFF.md` | Header + §8 table updated |

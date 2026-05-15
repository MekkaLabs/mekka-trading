# Story 012 - Signed Webhook and Retry Policy

## Goal

Harden alert delivery with signed webhook payloads and retry/backoff policy while preserving mock fallback.

## Delivered

- Signed webhook dispatcher (`HMAC-SHA256` in `x-mekka-signature`)
- Retrying dispatcher (attempts + exponential backoff)
- Health-check CLI integration via env vars:
  - `MEKKA_ALERT_WEBHOOK_URL`
  - `MEKKA_ALERT_WEBHOOK_SECRET`
- Async alert orchestrator support
- Tests for retry behavior and webhook signature integrity

## Checklist

- [x] Signed webhook adapter
- [x] Retry/backoff wrapper
- [x] CLI integration with safe fallback
- [x] Signature validation test
- [x] Retry test
- [x] Paper-only safety preserved

## Next

- Add dead-letter queue for permanently failed alerts
- Add jitter strategy to reduce synchronized retries
- Add per-channel circuit breaker

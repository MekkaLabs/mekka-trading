"""Tests — vault_context helper (Story #72 — Neural graph / Second brain).

Contract (see src/services/vault_context.py):
  1. Off-by-default — without ``vault_enrichment_enabled=True``, always
     returns "".
  2. Fail-silent — any exception inside recall() returns "".
  3. Bounded latency — wait_for(1.5s); timeout returns "".
  4. Bounded output — caps at ``max_chars``.
  5. Cached — same (symbol, topic) within TTL re-uses the block.
  6. No side effects — never writes, never raises to caller.

These tests monkeypatch JeanGrey entirely so they're hermetic and don't
touch the real vault on disk.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.services import vault_context as vc


@dataclass
class _FakeHit:
    title: str
    source: str
    snippet: str
    score: float = 1.0


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Drop the module-level cache between tests."""
    vc.clear_cache()
    yield
    vc.clear_cache()


def _enable_flag(monkeypatch, value: bool):
    """Pretend ``settings.vault_enrichment_enabled`` is ``value``."""
    class _S:
        vault_enrichment_enabled = value
    # Patch the lazy import path used inside _is_enabled().
    import src.config.settings as real_settings
    monkeypatch.setattr(real_settings, "settings", _S(), raising=True)


@pytest.mark.asyncio
async def test_flag_off_returns_empty_string(monkeypatch):
    """Default behavior — feature disabled, no recall ever called."""
    _enable_flag(monkeypatch, False)

    class _JG:
        def recall(self, **kw):
            raise AssertionError("recall should NOT be invoked when flag is off")

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())

    out = await vc.vault_context_for("BTC")
    assert out == ""


@pytest.mark.asyncio
async def test_flag_on_with_hits_formats_block(monkeypatch):
    """Flag on + recall returns hits → formatted block with title+snippet."""
    _enable_flag(monkeypatch, True)

    hits = [
        _FakeHit(title="BTC accumulation zone", source="vault:notes/btc.md",
                 snippet="Strong support at 60k, accumulation since…"),
        _FakeHit(title="Recent BEARISH calls", source="decision_memory",
                 snippet="3 SHORT closed -2% avg"),
    ]

    class _JG:
        async def recall(self, **kw):
            return hits

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())

    out = await vc.vault_context_for("BTC", topic="bullish")
    assert "Vault Context" in out
    assert "BTC" in out
    assert "accumulation zone" in out
    assert "decision_memory" in out
    assert "support at 60k" in out


@pytest.mark.asyncio
async def test_flag_on_with_no_hits_returns_empty(monkeypatch):
    """Flag on + recall returns empty list → empty string (no header)."""
    _enable_flag(monkeypatch, True)

    class _JG:
        async def recall(self, **kw):
            return []

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())
    out = await vc.vault_context_for("BTC")
    assert out == ""


@pytest.mark.asyncio
async def test_recall_exception_returns_empty(monkeypatch):
    """Recall raises → fail-silent, returns empty string (no crash)."""
    _enable_flag(monkeypatch, True)

    class _JG:
        async def recall(self, **kw):
            raise RuntimeError("disk error")

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())
    out = await vc.vault_context_for("BTC")
    assert out == ""  # no exception propagated


@pytest.mark.asyncio
async def test_recall_timeout_returns_empty(monkeypatch):
    """Recall takes >1.5s → wait_for times out → empty string."""
    _enable_flag(monkeypatch, True)

    class _JG:
        async def recall(self, **kw):
            await asyncio.sleep(5.0)  # way past RECALL_TIMEOUT_S
            return [_FakeHit("nope", "vault:x", "y")]

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())
    # Speed up the test by shrinking the timeout
    monkeypatch.setattr(vc, "RECALL_TIMEOUT_S", 0.05)

    out = await vc.vault_context_for("BTC")
    assert out == ""


@pytest.mark.asyncio
async def test_output_bounded_by_max_chars(monkeypatch):
    """Block longer than max_chars is truncated with marker."""
    _enable_flag(monkeypatch, True)

    big_snip = "X" * 5000
    hits = [_FakeHit("huge", "vault:a", big_snip)]

    class _JG:
        async def recall(self, **kw):
            return hits

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())
    out = await vc.vault_context_for("BTC", max_chars=500)
    assert len(out) <= 500
    assert "truncated" in out


@pytest.mark.asyncio
async def test_cache_within_ttl_avoids_second_recall(monkeypatch):
    """Two calls within TTL → recall is invoked only once."""
    _enable_flag(monkeypatch, True)

    call_count = {"n": 0}
    hits = [_FakeHit("ok", "vault:x", "ctx")]

    class _JG:
        async def recall(self, **kw):
            call_count["n"] += 1
            return hits

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())

    out1 = await vc.vault_context_for("BTC", topic="bullish")
    out2 = await vc.vault_context_for("BTC", topic="bullish")

    assert out1 == out2
    assert call_count["n"] == 1, "Second call should hit cache"


@pytest.mark.asyncio
async def test_cache_keyed_by_symbol_and_topic(monkeypatch):
    """Different (symbol, topic) keys do NOT share cache."""
    _enable_flag(monkeypatch, True)

    call_count = {"n": 0}

    class _JG:
        async def recall(self, **kw):
            call_count["n"] += 1
            return [_FakeHit(f"q-{call_count['n']}", "vault:x", "ctx")]

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())

    await vc.vault_context_for("BTC", topic="bullish")
    await vc.vault_context_for("ETH", topic="bullish")
    await vc.vault_context_for("BTC", topic="bearish")

    # 3 distinct keys → 3 recall calls
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_empty_result_also_cached(monkeypatch):
    """Recall returning [] is cached too — avoids beating Jean Grey on cold vault."""
    _enable_flag(monkeypatch, True)
    call_count = {"n": 0}

    class _JG:
        async def recall(self, **kw):
            call_count["n"] += 1
            return []

    monkeypatch.setattr("src.agents.jean_grey.JeanGrey", lambda: _JG())

    await vc.vault_context_for("BTC")
    await vc.vault_context_for("BTC")

    assert call_count["n"] == 1

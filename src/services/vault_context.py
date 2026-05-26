"""src/services/vault_context.py
======================================
Story #72 — Neural Graph / Vault Enrichment for Agents.

Layer that lets agents consult the Obsidian vault (the "second brain"
curated by Jean Grey) for symbol/topic context before deciding, WITHOUT
changing their decision path.

Design tenets — read these before touching anything here:

  1. **Read-only.** This module never writes to the vault or to DB. It
     only ranks and trims existing notes.

  2. **Opt-in feature flag.** ``settings.vault_enrichment_enabled`` is
     ``False`` by default — caller code paths reduce to early-return.
     Operator must set ``VAULT_ENRICHMENT_ENABLED=true`` in .env.

  3. **Fail-silent.** Any exception inside ``vault_context_for()``
     returns an empty string. Trading must NEVER fail because the
     vault is slow / corrupt / missing.

  4. **Bounded latency.** Wraps Jean Grey's ``recall()`` in
     ``asyncio.wait_for`` with a 1.5s timeout. If recall is slow the
     enrichment is skipped — the prompt still goes out, just without
     the vault block.

  5. **Bounded output.** The returned context block is hard-capped at
     ``max_chars`` chars. Larger contexts don't help the LLM, cost
     tokens, and inflate latency.

  6. **TTL cache.** Vault contents change rarely (operator edits at most
     a few notes per day). Same (symbol, topic) within ``cache_ttl_s``
     returns the cached block — keeps the loop fast.

  7. **No side effects on trading agents.** Agents that consume this
     helper get either a non-empty enrichment string or ``""``. They
     concat it to their prompt. They never branch on its content.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Constants — kept module-level so tests can monkeypatch easily
# ---------------------------------------------------------------------------

#: Hard timeout for a single recall() call (seconds).
RECALL_TIMEOUT_S: float = 1.5

#: Max chars in the returned context block. The block is appended to the
#: LLM prompt; anything above this just inflates tokens without helping.
DEFAULT_MAX_CHARS: int = 2_000

#: Cache TTL (seconds). Vault content is curated daily by the operator;
#: a few minutes of staleness is fine and keeps the loop cheap.
CACHE_TTL_S: float = 300.0


@dataclass
class _CacheEntry:
    block: str
    expires_at: float


# Process-wide cache. Keyed by (symbol_upper, topic_lower).
_CACHE: dict[tuple[str, str], _CacheEntry] = {}


def _is_enabled() -> bool:
    """Read the feature flag at call time so toggling in .env / restart
    takes effect without re-importing the consumer module."""
    try:
        from src.config.settings import settings  # noqa: WPS433
        return bool(getattr(settings, "vault_enrichment_enabled", False))
    except Exception:
        # If settings can't be loaded, fail closed (no enrichment).
        return False


def _format_block(hits: list, symbol: str, max_chars: int) -> str:
    """Render a list of RecallHit into a compact prompt block."""
    if not hits:
        return ""

    lines = [
        f"=== Vault Context — {symbol} (Second Brain) ===",
        "",
        (
            "These are excerpts from the operator's curated knowledge vault "
            "(Obsidian) that may be relevant. They are NOT trade signals — "
            "use them only to refine your reasoning. Conflicting vault "
            "notes mean you should be more cautious, not less."
        ),
        "",
    ]
    for i, h in enumerate(hits, 1):
        title = getattr(h, "title", "(untitled)") or "(untitled)"
        source = getattr(h, "source", "") or ""
        snippet = (getattr(h, "snippet", "") or "").strip()
        lines.append(f"[{i}] {title}  ({source})")
        if snippet:
            lines.append(f"    {snippet}")
        lines.append("")

    block = "\n".join(lines).rstrip()
    if len(block) > max_chars:
        block = block[: max_chars - 20].rstrip() + "\n…[truncated]"
    return block


async def vault_context_for(
    symbol: str,
    topic: Optional[str] = None,
    *,
    limit: int = 4,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Return a formatted vault-context block for ``symbol`` + ``topic``.

    Returns an empty string when:
      - ``vault_enrichment_enabled`` is False (default)
      - ``recall()`` raises or times out
      - the vault has no relevant hits
      - any unexpected error occurs (fail-silent contract)

    Args:
        symbol: trading pair / asset ticker (e.g. "BTC"). Always included
            in the recall query.
        topic: optional extra context terms (e.g. "support resistance"
            or "fear greed regime"). Concatenated to the query.
        limit: max hits to fetch from Jean Grey (default 4 — balances
            signal vs prompt-bloat).
        max_chars: hard cap on returned block size.
    """
    if not _is_enabled():
        return ""

    sym_key = (symbol or "").upper().strip()
    topic_key = (topic or "").lower().strip()
    cache_key = (sym_key, topic_key)

    # Cache check — vault rarely changes, no need to re-rank every cycle.
    now = time.monotonic()
    entry = _CACHE.get(cache_key)
    if entry is not None and entry.expires_at > now:
        return entry.block

    block = ""
    try:
        # Import is lazy to avoid pulling jean_grey at module load. This
        # also lets tests monkeypatch JeanGrey before the helper hits it.
        from src.agents.jean_grey import JeanGrey  # noqa: WPS433

        query = sym_key
        if topic_key:
            query = f"{sym_key} {topic_key}"

        recall_coro = JeanGrey().recall(query=query, limit=limit)
        hits = await asyncio.wait_for(recall_coro, timeout=RECALL_TIMEOUT_S)
        block = _format_block(hits or [], symbol=sym_key, max_chars=max_chars)
    except asyncio.TimeoutError:
        # Recall slow → skip enrichment, never block the trading loop.
        logger.debug(
            f"[vault_context] recall timeout for {sym_key!r} "
            f"({RECALL_TIMEOUT_S}s) — enrichment skipped"
        )
    except Exception as exc:  # noqa: BLE001
        # Anything else: log debug and return empty. The contract is that
        # vault enrichment is best-effort and never raises to the caller.
        logger.debug(
            f"[vault_context] recall failed for {sym_key!r}: "
            f"{type(exc).__name__}: {exc}"
        )

    # Cache even the empty result so a cold vault doesn't beat up Jean Grey.
    _CACHE[cache_key] = _CacheEntry(block=block, expires_at=now + CACHE_TTL_S)
    return block


def clear_cache() -> None:
    """Drop the entire (symbol, topic) cache. Used by tests and when the
    operator manually edits the vault and wants the next cycle to pick
    up the change immediately."""
    _CACHE.clear()

"""
src/agents/doctor_strange.py
=============================
Doctor Strange — Macro Probability Analyst

Data sources:
1. CryptoPanic API  — crypto news + sentiment (free tier)
2. Alternative.me Fear & Greed Index (public, no auth)
3. CoinGecko Global — BTC dominance (public)

Returns `SentimentData` with a composite score -1.0 → +1.0.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

from src.agents.base import AgentError, BaseAgent
from src.config.settings import settings
from src.models.market_data import SentimentData

_CRYPTOPANIC_URL = "https://cryptopanic.com/api/free/v1/posts/"
_FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
_COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
_TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _get_json(session: aiohttp.ClientSession, url: str, params: Optional[dict] = None) -> dict:
    async with session.get(url, params=params, timeout=_TIMEOUT) as resp:
        if resp.status != 200:
            raise AgentError("DoctorStrange", f"HTTP {resp.status} from {url}")
        return await resp.json(content_type=None)


async def _fetch_fear_greed(session: aiohttp.ClientSession) -> Optional[int]:
    try:
        data = await _get_json(session, _FEAR_GREED_URL)
        return max(0, min(100, int(data["data"][0]["value"])))
    except Exception:
        return None


async def _fetch_btc_dominance(session: aiohttp.ClientSession) -> Optional[float]:
    try:
        data = await _get_json(session, _COINGECKO_GLOBAL_URL)
        return round(float(data["data"]["market_cap_percentage"]["btc"]), 2)
    except Exception:
        return None


async def _fetch_cryptopanic(session: aiohttp.ClientSession, api_key: str, symbol: str) -> tuple[float, list[str]]:
    if not api_key:
        return 0.0, []
    # [C3] Restrict to posts from the last 8 hours to prevent stale news from
    # inflating the sentiment score. Format: ISO 8601 UTC timestamp.
    published_after = (
        datetime.now(timezone.utc) - timedelta(hours=8)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "auth_token": api_key,
        "currencies": symbol,
        "filter": "hot",
        "kind": "news",
        "public": "true",
        "published_after": published_after,
    }
    try:
        data = await _get_json(session, _CRYPTOPANIC_URL, params=params)
        results = data.get("results", [])
    except Exception:
        return 0.0, []

    headlines: list[str] = []
    weights: list[float] = []
    for post in results[:20]:
        title = post.get("title", "").strip()
        if title:
            headlines.append(title)
        votes = post.get("votes", {})
        pos = float(votes.get("positive", 0))
        neg = float(votes.get("negative", 0))
        imp = float(votes.get("important", 0))
        total = pos + neg + imp
        if total > 0:
            weights.append((pos - neg) / total)

    score = float(sum(weights) / len(weights)) if weights else 0.0
    return score, headlines[:10]


class DoctorStrange(BaseAgent[SentimentData]):
    """
    Macro Probability Analyst — aggregates CryptoPanic + Fear&Greed + BTC dominance.

    Usage: sentiment = await DoctorStrange().run(symbol="BTC")
    """

    def __init__(self) -> None:
        super().__init__(
            "DoctorStrange",
            "Macro Probability Analyst",
            timeout_s=30.0,  # Fear & Greed API + sentiment fetches
        )

    async def _run(self, symbol: str = "BTC") -> SentimentData:  # type: ignore[override]
        async with aiohttp.ClientSession() as session:
            fg_task = asyncio.create_task(_fetch_fear_greed(session))
            dom_task = asyncio.create_task(_fetch_btc_dominance(session))
            cp_task = asyncio.create_task(
                _fetch_cryptopanic(session, settings.cryptopanic_api_key, symbol)
            )
            fear_greed, btc_dom, (cp_score, headlines) = await asyncio.gather(
                fg_task, dom_task, cp_task
            )

        # Normalize Fear & Greed: 0-100 → -1 to +1
        fg_score = ((fear_greed - 50.0) / 50.0) if fear_greed is not None else 0.0

        # BTC dominance modifier
        dom_score = 0.0
        if btc_dom is not None:
            dom_score = -0.3 if btc_dom > 60 else (0.2 if btc_dom < 40 else 0.0)

        # Weighted composite
        parts: list[tuple[float, float]] = []  # (score, weight)
        if fear_greed is not None:
            parts.append((fg_score, 0.45))
        if settings.sentiment_enabled and headlines:
            parts.append((cp_score, 0.35))
        if btc_dom is not None:
            parts.append((dom_score, 0.20))

        if parts:
            total_w = sum(w for _, w in parts)
            composite = sum(s * w for s, w in parts) / total_w
            composite = max(-1.0, min(1.0, composite))
        else:
            composite = 0.0

        # Review-fix (2026-06-01): se NENHUMA fonte respondeu (parts vazio),
        # score=0.0 não distingue 'neutro real' de 'não consegui medir' →
        # data_available=False (ProfessorX conta como fonte ausente).
        _has_data = len(parts) > 0

        self._log.info(
            f"[DoctorStrange] {symbol} score={composite:+.3f} "
            f"fg={fear_greed} dom={btc_dom} headlines={len(headlines)} "
            f"data_available={_has_data}"
        )

        return SentimentData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=round(composite, 4),
            fear_greed_index=fear_greed,
            btc_dominance=btc_dom,
            headlines=headlines,
            data_available=_has_data,
        )

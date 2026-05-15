"""
src/agents/professor_x.py
=========================
Professor X — Swarm Coordinator

Runs the Layer-1 analysis agents (Superman, Doctor Strange, Black Panther,
Thor, Aquaman, Spider-Man) in parallel and assembles their outputs into a
single `MarketAnalysis` bundle ready to feed Vision.

Failure isolation
-----------------
Each agent runs inside `asyncio.gather(..., return_exceptions=True)`. If any
single agent fails, Professor X logs the error and continues with the other
fields set to None. The only required output is Superman (chart). If
Superman fails, Professor X re-raises — no decision can be made without
technical analysis.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from src.agents.aquaman import Aquaman
from src.agents.base import AgentError, BaseAgent
from src.agents.black_panther import BlackPanther
from src.agents.doctor_strange import DoctorStrange
from src.agents.spider_man import SpiderMan
from src.agents.superman import Superman
from src.agents.thor import Thor
from src.models.market_data import (
    LiquidityData,
    MarketAnalysis,
    MarketData,
    OnchainData,
    SentimentData,
    VolatilityData,
)


class ProfessorX(BaseAgent[MarketAnalysis]):
    """
    Swarm Coordinator — orchestrates Layer-1 agents in parallel.

    Usage:
        analysis = await ProfessorX().run(symbol="BTC")
    """

    def __init__(self) -> None:
        super().__init__(
            codename="ProfessorX",
            role="Swarm Coordinator — parallel analysis-layer orchestration",
        )
        self._superman: Optional[Superman] = None
        self._strange = DoctorStrange()
        self._panther = BlackPanther()
        self._thor = Thor()
        self._aquaman = Aquaman()
        self._spider = SpiderMan()

    async def close(self) -> None:
        if self._superman is not None:
            await self._superman.close()
            self._superman = None

    async def _run(self, symbol: str) -> MarketAnalysis:  # type: ignore[override]
        # Lazy init Superman (it owns a CCXT exchange instance)
        if self._superman is None:
            self._superman = Superman()

        # 1. Superman first — required (no chart = no decision)
        try:
            chart: MarketData = await self._superman.run(symbol=symbol)
        except AgentError as exc:
            self._log.error(f"[ProfessorX] Superman failed for {symbol}: {exc}")
            raise

        # 2. Layer-1 fan-out (independent of each other)
        sentiment_task = asyncio.create_task(self._strange.run(symbol=symbol))
        onchain_task = asyncio.create_task(self._panther.run(symbol=symbol))
        thor_task = asyncio.create_task(self._thor.run(market_data=chart))
        aquaman_task = asyncio.create_task(self._aquaman.run(symbol=symbol))

        results = await asyncio.gather(
            sentiment_task,
            onchain_task,
            thor_task,
            aquaman_task,
            return_exceptions=True,
        )

        sentiment = self._coerce(results[0], "DoctorStrange", SentimentData)
        onchain = self._coerce(results[1], "BlackPanther", OnchainData)
        volatility = self._coerce(results[2], "Thor", VolatilityData)
        liquidity = self._coerce(results[3], "Aquaman", LiquidityData)

        # 3. Spider-Man depends on chart + onchain — run last
        try:
            anomaly = await self._spider.run(
                symbol=symbol,
                market_data=chart,
                onchain_data=onchain,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[ProfessorX] SpiderMan skipped: {exc}")
            anomaly = None

        analysis = MarketAnalysis(
            chart=chart,
            sentiment=sentiment,
            onchain=onchain,
            volatility=volatility,
            liquidity=liquidity,
            anomaly=anomaly,
        )

        self._log.info(
            f"[ProfessorX] {symbol} analysis assembled — "
            f"safe_to_trade={analysis.is_safe_to_trade}"
        )
        return analysis

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _coerce(self, value, agent_name: str, expected_type):
        """Log-and-skip pattern for partial failures."""
        if isinstance(value, Exception):
            self._log.warning(
                f"[ProfessorX] {agent_name} failed: {value} — proceeding without it"
            )
            return None
        if not isinstance(value, expected_type):
            self._log.warning(
                f"[ProfessorX] {agent_name} returned unexpected type "
                f"{type(value).__name__}, expected {expected_type.__name__}"
            )
            return None
        return value

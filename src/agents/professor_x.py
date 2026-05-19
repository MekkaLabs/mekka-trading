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
from src.agents.flash import Flash
from src.agents.spider_man import SpiderMan
from src.agents.superman import Superman
from src.agents.thor import Thor
from src.config.settings import settings
from src.models.market_data import (
    LiquidityData,
    MarketAnalysis,
    MarketData,
    OnchainData,
    SentimentData,
    VolatilityData,
)
from src.models.signal import MomentumSignal


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
        self._flash = Flash()  # [C5] Momentum scalper — advisory

    async def close(self) -> None:
        if self._superman is not None:
            await self._superman.close()
            self._superman = None

    async def _run(self, symbol: str) -> MarketAnalysis:  # type: ignore[override]
        # Lazy init Superman (it owns a CCXT exchange instance)
        if self._superman is None:
            self._superman = Superman()

        # 1. Superman — primary TF (required; no chart = no decision)
        try:
            chart: MarketData = await self._superman.run(symbol=symbol)
        except AgentError as exc:
            self._log.error(f"[ProfessorX] Superman failed for {symbol}: {exc}")
            raise

        # [C1] Superman — confirmation TF (1h by default, best-effort)
        confirmation_chart: Optional[MarketData] = None
        conf_tf = settings.confirmation_timeframe
        if conf_tf and conf_tf != settings.primary_timeframe:
            try:
                confirmation_chart = await self._superman.run(
                    symbol=symbol, timeframe=conf_tf
                )
            except Exception as exc:  # noqa: BLE001
                self._log.warning(
                    f"[ProfessorX] Superman confirmation TF {conf_tf} failed: {exc}"
                )

        # 2. Layer-1 fan-out (independent of each other)
        # [C5] Flash runs alongside other agents — uses recent_closes from chart
        sentiment_task = asyncio.create_task(self._strange.run(symbol=symbol))
        onchain_task = asyncio.create_task(self._panther.run(symbol=symbol))
        thor_task = asyncio.create_task(self._thor.run(market_data=chart))
        aquaman_task = asyncio.create_task(self._aquaman.run(symbol=symbol))
        flash_task = asyncio.create_task(
            self._flash.run(
                symbol=symbol,
                recent_prices=chart.recent_closes,
            )
        )

        results = await asyncio.gather(
            sentiment_task,
            onchain_task,
            thor_task,
            aquaman_task,
            flash_task,
            return_exceptions=True,
        )

        sentiment = self._coerce(results[0], "DoctorStrange", SentimentData)
        onchain = self._coerce(results[1], "BlackPanther", OnchainData)
        volatility = self._coerce(results[2], "Thor", VolatilityData)
        liquidity = self._coerce(results[3], "Aquaman", LiquidityData)
        momentum = self._coerce(results[4], "Flash", MomentumSignal)  # [C5]

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
            confirmation_chart=confirmation_chart,  # [C1]
            sentiment=sentiment,
            onchain=onchain,
            volatility=volatility,
            liquidity=liquidity,
            anomaly=anomaly,
            momentum=momentum,  # [C5]
        )

        # ── Story 243 — Multiagent Debate (Milestone 39) ──────────────────────
        # Optional: run DebateModerator between L1 agents before handing off to
        # Vision. Gated by settings.debate_enabled (default False).
        debate_verdict = await self._maybe_run_debate(analysis, symbol)
        if debate_verdict is not None:
            analysis = analysis.model_copy(update={"debate_verdict": debate_verdict})

        self._log.info(
            f"[ProfessorX] {symbol} analysis assembled — "
            f"safe_to_trade={analysis.is_safe_to_trade} "
            f"confirmation_tf={conf_tf if confirmation_chart else 'N/A'} "
            f"momentum={getattr(getattr(momentum, 'direction', None), 'value', 'N/A')}"
            + (
                f" | debate={debate_verdict.consensus_action}({debate_verdict.consensus_confidence:.0%})"
                if debate_verdict else ""
            )
        )
        return analysis

    async def _maybe_run_debate(self, analysis: "MarketAnalysis", symbol: str):
        """
        Story 243 — Executa o DebateModerator se debate_enabled=True nas settings.

        Returns DebateVerdict ou None se debate desabilitado / falhar.
        """
        try:
            from src.config.settings import settings as _settings
            if not _settings.debate_enabled:
                return None

            from src.services.debate_moderator import DebateModerator
            from src.services.debate_verdict_logger import DebateVerdictLogger

            moderator = DebateModerator(
                max_rounds=_settings.debate_max_rounds,
                consensus_threshold=_settings.debate_consensus_threshold,
            )
            # Contexto simplificado para o debate (evitar serialização pesada)
            context = {
                "trend":            getattr(analysis.chart, "trend", ""),
                "macro_sentiment":  getattr(analysis.sentiment, "overall_sentiment", ""),
                "fear_greed_index": getattr(analysis.sentiment, "fear_greed_index", 50),
                "funding_rate":     getattr(analysis.onchain, "funding_rate", 0),
                "atr_pct":          getattr(analysis.volatility, "atr_pct", 2.0),
                "spread_pct":       getattr(analysis.liquidity, "estimated_slippage_pct", 0.05),
            }
            verdict = await moderator.run(context=context, symbol=symbol)

            # Log assíncrono (fire-and-forget)
            asyncio.create_task(
                DebateVerdictLogger().log(verdict, symbol=symbol)
            )
            return verdict
        except Exception as exc:
            self._log.warning(f"[ProfessorX] debate skipped: {exc}")
            return None

    # ------------------------------------------------------------------
    # Story 050 — Symbol validation (Altcoins toggle safety net)
    # ------------------------------------------------------------------

    async def validate_symbols(self, symbols: list[str]) -> list[str]:
        """
        Delegate to Superman to filter ``symbols`` against exchange markets.

        Lazily inits Superman if not yet connected. Never raises — returns
        the original list unchanged on any failure so the cycle continues.
        """
        if self._superman is None:
            self._superman = Superman()
        return await self._superman.validate_symbols(symbols)

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

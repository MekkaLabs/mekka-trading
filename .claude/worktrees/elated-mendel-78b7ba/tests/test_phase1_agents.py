"""
tests/test_phase1_agents.py
============================
Unit tests for Phase 1 — Analysis Agents (Fase 1).

Tests use mocks and stubs — no real API calls.
Run with: pytest tests/test_phase1_agents.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.market_data import (
    AnomalySeverity,
    MarketData,
    OnchainData,
    SentimentData,
    Trend,
    VolatilityData,
    VolatilityRegime,
    WhaleSignal,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable MarketData
# ---------------------------------------------------------------------------

def _btc_market_data(**overrides) -> MarketData:
    defaults = dict(
        symbol="BTC",
        timestamp=datetime.now(timezone.utc),
        timeframe="4h",
        price=65_000.0,
        rsi_14=55.0,
        ema_20=64_000.0,
        ema_50=62_000.0,
        bb_upper=68_000.0,
        bb_lower=60_000.0,
        bb_mid=64_000.0,
        macd=150.0,
        macd_signal=100.0,
        macd_hist=50.0,
        atr_14=1_500.0,  # ATR% ≈ 2.3% → MEDIUM
        volume=5_000.0,
        volume_ma=4_000.0,
        trend=Trend.BULLISH,
        trend_strength=0.7,
    )
    defaults.update(overrides)
    return MarketData(**defaults)


# ---------------------------------------------------------------------------
# Thor tests (pure computation — no mocks needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thor_medium_regime():
    from src.agents.thor import Thor
    md = _btc_market_data(price=65_000.0, atr_14=1_500.0)  # 2.3% → MEDIUM
    agent = Thor()
    result: VolatilityData = await agent.run(market_data=md)
    assert result.symbol == "BTC"
    assert result.volatility_regime == VolatilityRegime.MEDIUM
    assert result.suggested_position_size_multiplier == 1.0


@pytest.mark.asyncio
async def test_thor_extreme_regime():
    from src.agents.thor import Thor
    md = _btc_market_data(price=65_000.0, atr_14=5_000.0)  # 7.7% → EXTREME
    agent = Thor()
    result: VolatilityData = await agent.run(market_data=md)
    assert result.volatility_regime == VolatilityRegime.EXTREME
    assert result.suggested_position_size_multiplier == 0.3


@pytest.mark.asyncio
async def test_thor_low_regime():
    from src.agents.thor import Thor
    md = _btc_market_data(price=65_000.0, atr_14=500.0)  # 0.77% → LOW
    agent = Thor()
    result: VolatilityData = await agent.run(market_data=md)
    assert result.volatility_regime == VolatilityRegime.LOW
    assert result.suggested_position_size_multiplier == 1.2


@pytest.mark.asyncio
async def test_thor_missing_atr():
    from src.agents.thor import Thor
    md = _btc_market_data(atr_14=None)
    agent = Thor()
    result: VolatilityData = await agent.run(market_data=md)
    # Should default to MEDIUM (2%)
    assert result.volatility_regime == VolatilityRegime.MEDIUM


@pytest.mark.asyncio
async def test_thor_realized_vol():
    from src.agents.thor import Thor
    import math
    md = _btc_market_data(atr_14=1_500.0)
    # 7 days × 6 candles + 1 = 43 prices needed
    prices = [65_000.0 * (1 + 0.001 * i) for i in range(50)]
    agent = Thor()
    result: VolatilityData = await agent.run(market_data=md, price_history=prices)
    assert result.realized_vol_7d is not None
    assert result.realized_vol_7d >= 0


# ---------------------------------------------------------------------------
# Spider-Man tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spiderman_clean_market():
    from src.agents.spider_man import SpiderMan
    md = _btc_market_data()
    agent = SpiderMan()
    report = await agent.run(symbol="BTC", market_data=md)
    assert report.severity == AnomalySeverity.NONE
    assert not report.should_pause
    assert len(report.anomalies_detected) == 0


@pytest.mark.asyncio
async def test_spiderman_flash_crash():
    from src.agents.spider_man import SpiderMan
    # Price 10% below EMA-20
    md = _btc_market_data(price=57_600.0, ema_20=64_000.0)
    agent = SpiderMan()
    report = await agent.run(symbol="BTC", market_data=md)
    assert report.severity == AnomalySeverity.HIGH
    assert report.should_pause is True
    assert any("Flash crash" in a for a in report.anomalies_detected)


@pytest.mark.asyncio
async def test_spiderman_volume_spike():
    from src.agents.spider_man import SpiderMan
    md = _btc_market_data(volume=25_000.0, volume_ma=4_000.0)  # 6.25× spike
    agent = SpiderMan()
    report = await agent.run(symbol="BTC", market_data=md)
    assert report.severity == AnomalySeverity.LOW
    assert any("Volume spike" in a for a in report.anomalies_detected)


@pytest.mark.asyncio
async def test_spiderman_extreme_funding():
    from src.agents.spider_man import SpiderMan
    md = _btc_market_data()
    oc = OnchainData(symbol="BTC", funding_rate=0.005)  # 0.5%/hr → extreme
    agent = SpiderMan()
    report = await agent.run(symbol="BTC", market_data=md, onchain_data=oc)
    assert report.severity >= AnomalySeverity.MEDIUM
    assert any("funding" in a.lower() for a in report.anomalies_detected)


@pytest.mark.asyncio
async def test_spiderman_agent_divergence():
    from src.agents.spider_man import SpiderMan
    md = _btc_market_data(trend=Trend.BULLISH, trend_strength=0.8)
    oc = OnchainData(symbol="BTC", signal=WhaleSignal.DISTRIBUTION)
    agent = SpiderMan()
    report = await agent.run(symbol="BTC", market_data=md, onchain_data=oc)
    assert any("divergence" in a.lower() for a in report.anomalies_detected)


@pytest.mark.asyncio
async def test_spiderman_extreme_rsi_overbought():
    from src.agents.spider_man import SpiderMan
    md = _btc_market_data(rsi_14=88.0)
    agent = SpiderMan()
    report = await agent.run(symbol="BTC", market_data=md)
    assert any("RSI" in a and "overbought" in a for a in report.anomalies_detected)


# ---------------------------------------------------------------------------
# Doctor Strange tests (mocked HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_doctor_strange_no_api_key():
    """With no CryptoPanic key, should still return a score from F&G + dominance."""
    from src.agents.doctor_strange import DoctorStrange

    mock_fg = {"data": [{"value": "75"}]}       # Greed
    mock_cg = {"data": {"market_cap_percentage": {"btc": 55.0}}}

    with patch("src.agents.doctor_strange.settings") as mock_settings:
        mock_settings.cryptopanic_api_key = ""
        mock_settings.sentiment_enabled = False
        mock_settings.is_mainnet = False

        with patch("src.agents.doctor_strange._get_json", new_callable=AsyncMock) as mock_get:
            async def fake_get(session, url, params=None):
                if "alternative.me" in url:
                    return mock_fg
                if "coingecko" in url:
                    return mock_cg
                return {}

            mock_get.side_effect = fake_get
            agent = DoctorStrange()
            result: SentimentData = await agent.run(symbol="BTC")

    assert result.symbol == "BTC"
    assert -1.0 <= result.score <= 1.0
    assert result.fear_greed_index == 75
    # Greed → positive score
    assert result.score > 0


# ---------------------------------------------------------------------------
# Base agent tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_agent_error_wrapping():
    from src.agents.base import AgentError, BaseAgent

    class BrokenAgent(BaseAgent[None]):
        def __init__(self):
            super().__init__("Test", "test role")

        async def _run(self):
            raise ValueError("something went wrong")

    agent = BrokenAgent()
    with pytest.raises(AgentError) as exc_info:
        await agent.run()
    assert "Test" in str(exc_info.value)


@pytest.mark.asyncio
async def test_base_agent_success():
    from src.agents.base import BaseAgent

    class OkAgent(BaseAgent[str]):
        def __init__(self):
            super().__init__("TestOk", "ok role")

        async def _run(self):
            return "success"

    agent = OkAgent()
    result = await agent.run()
    assert result == "success"

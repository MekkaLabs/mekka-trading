"""Regressão dos fixes da revisão profunda de agentes (2026-06-01).

- Spider-Man fail-SAFE: falha do detector de anomalia → pausa (não libera).
- Thor: ATR ausente → regime HIGH (sizing 0.6×), não MEDIUM/1.0×.
- VisionCritic: REJECT não é rebaixado a ENDORSE por threshold de disagreement.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _market_data(atr_14=0.5):
    from src.models.market_data import MarketData, Trend
    return MarketData(
        symbol="BTC", timestamp=datetime.now(timezone.utc), timeframe="4h",
        price=100.0, trend=Trend.NEUTRAL, trend_strength=0.5, atr_14=atr_14,
    )


# ===========================================================================
# Spider-Man fail-safe (Professor X)
# ===========================================================================

def test_spiderman_failure_synthesizes_pause():
    """Verificação de código: na falha do Spider-Man, ProfessorX sintetiza um
    AnomalyReport com should_pause=True (fail-safe), não anomaly=None (fail-open)."""
    import inspect
    from src.agents import professor_x as px

    src = inspect.getsource(px)
    # O ramo de exceção do Spider-Man agora cria AnomalyReport(should_pause=True).
    assert "should_pause=True" in src
    assert "SpiderMan unavailable" in src
    # E não atribui mais anomaly=None silenciosamente nesse ramo.
    block = src[src.index("SpiderMan FALHOU"):src.index("SpiderMan FALHOU") + 600]
    assert "anomaly = AnomalyReport(" in block


def test_synthetic_pause_report_makes_unsafe():
    """Um AnomalyReport(should_pause=True) → is_safe_to_trade=False."""
    from src.models.market_data import (
        MarketAnalysis, AnomalyReport, AnomalySeverity,
    )
    rep = AnomalyReport(symbol="BTC", severity=AnomalySeverity.HIGH, should_pause=True)
    ma = MarketAnalysis(chart=_market_data(), anomaly=rep)
    assert ma.is_safe_to_trade is False


# ===========================================================================
# Thor — ATR ausente → regime conservador
# ===========================================================================

@pytest.mark.asyncio
async def test_thor_missing_atr_defaults_to_high_regime():
    from src.agents.thor import Thor
    from src.models.market_data import VolatilityRegime

    md = _market_data(atr_14=None)  # ATR ausente
    out = await Thor().run(market_data=md)
    # Antes: MEDIUM/1.0×. Agora: HIGH/0.6× (conservador).
    assert out.volatility_regime == VolatilityRegime.HIGH
    assert out.suggested_position_size_multiplier == pytest.approx(0.6)


# ===========================================================================
# VisionCritic — REJECT não rebaixado por threshold
# ===========================================================================

def test_vision_critic_reject_not_downgraded_by_threshold():
    """Um REJECT com delta pequeno NÃO deve virar ENDORSE (é veto de segurança).
    Verificação de código: a condição de downgrade agora exige AMEND."""
    import inspect
    from src.agents import vision_critic as vc

    src = inspect.getsource(vc)
    # A condição de rebaixamento agora é específica para AMEND.
    assert "critique.action == CritiqueAction.AMEND" in src
    # E não re-chama _get_mode_params() na string de log (evita NameError).
    assert "[{_get_mode_params" not in src

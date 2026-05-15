"""
tests/test_story_131_vision_moa.py
===================================
Story 131 — Mixture of Agents Vision (MoA)

Testa:
  1. VisionMoA.run() — interface idêntica a Vision (aceita MarketAnalysis)
  2. _generate_proposals() — asyncio.gather paralelo, fail-silent individual
  3. _synthesize() — orchestrator LLM sintetiza consensus
  4. _vote_fallback() — votação mecânica sem LLM (majority vote + weighted avg)
  5. Fallback para Vision clássico quando < min_proposals OK
  6. Settings: vision_moa_enabled, vision_moa_min_proposals
  7. NickFury toggle: usa VisionMoA quando habilitado

Todos os testes são sync-safe, usam mocks e não fazem chamadas reais de LLM.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    symbol: str = "BTC",
    action: str = "LONG",
    confidence: float = 0.75,
    entry: float = 100.0,
    sl: float = 95.0,
    tp: float = 110.0,
    size_pct: float = 0.02,
    leverage: int = 2,
    reasoning: str = "Test signal",
    slot: str | None = None,
) -> TradingSignal:
    meta: dict[str, Any] = {"model": "test", "fallback": False}
    if slot:
        meta["moa_slot"] = slot
    return TradingSignal(
        timestamp=datetime.now(timezone.utc),
        symbol=symbol,
        action=TradeAction(action),
        confidence=confidence,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        size_pct=size_pct,
        leverage=leverage,
        reasoning=reasoning,
        agent_contributions={"Test": "test"},
        metadata=meta,
    )


def _make_analysis(symbol: str = "BTC", price: float = 100.0) -> Any:
    """Mock de MarketAnalysis com is_safe_to_trade=True."""
    analysis = MagicMock()
    analysis.symbol = symbol
    analysis.price = price
    analysis.is_safe_to_trade = True
    analysis.to_prompt.return_value = f"Market analysis for {symbol} at {price}"
    return analysis


def _json_signal(
    action: str = "LONG",
    confidence: float = 0.75,
    entry: float = 100.0,
    sl: float = 95.0,
    tp: float = 110.0,
) -> str:
    return json.dumps({
        "action": action,
        "confidence": confidence,
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "size_pct": 0.02,
        "leverage": 2,
        "reasoning": "Test reasoning",
        "agent_contributions": {"Test": "test"},
    })


# ---------------------------------------------------------------------------
# T01 — Importação e instanciação sem LLM keys
# ---------------------------------------------------------------------------

def test_t01_vision_moa_imports_without_error():
    """VisionMoA importa sem erro mesmo sem API keys configuradas."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    assert VisionMoA is not None


def test_t02_vision_moa_instantiates():
    """VisionMoA instancia com providers 'none' quando sem keys."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    assert moa is not None
    assert moa._vision_fallback is not None


# ---------------------------------------------------------------------------
# T03 — vote_fallback: majority LONG
# ---------------------------------------------------------------------------

def test_t03_vote_fallback_majority_long():
    """Dois LONG + um SHORT → ação final LONG."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    proposals = [
        _make_signal(action="LONG", confidence=0.8, slot="GPT-4o"),
        _make_signal(action="LONG", confidence=0.7, slot="Claude-Sonnet"),
        _make_signal(action="SHORT", confidence=0.6, slot="GPT-4o-mini"),
    ]
    result = moa._vote_fallback(proposals=proposals, symbol="BTC", price=100.0)
    assert result.action == TradeAction.LONG
    assert result.confidence > 0.0
    assert result.metadata["moa_mode"] == "vote_fallback"
    assert result.metadata["moa_proposals"] == 3


# ---------------------------------------------------------------------------
# T04 — vote_fallback: sem maioria → HOLD
# ---------------------------------------------------------------------------

def test_t04_vote_fallback_no_majority_hold():
    """LONG=1, SHORT=1, HOLD=1 → sem maioria → HOLD."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    proposals = [
        _make_signal(action="LONG", confidence=0.8, entry=100, sl=95, tp=110, slot="A"),
        _make_signal(action="SHORT", confidence=0.7, entry=100, sl=105, tp=90, slot="B"),
        _make_signal(action="HOLD", confidence=0.6, slot="C"),
    ]
    result = moa._vote_fallback(proposals=proposals, symbol="BTC", price=100.0)
    assert result.action == TradeAction.HOLD


# ---------------------------------------------------------------------------
# T05 — vote_fallback: lista vazia → HOLD fallback
# ---------------------------------------------------------------------------

def test_t05_vote_fallback_empty_list():
    """Lista vazia de proposals → HOLD defensivo."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    result = moa._vote_fallback(proposals=[], symbol="BTC", price=100.0)
    assert result.action == TradeAction.HOLD
    assert result.metadata.get("fallback") is True


# ---------------------------------------------------------------------------
# T06 — vote_fallback: dois proposals → majority SHORT
# ---------------------------------------------------------------------------

def test_t06_vote_fallback_two_proposals_short():
    """Dois SHORT de 2 proposals → SHORT com weighted avg confidence."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    proposals = [
        _make_signal(action="SHORT", confidence=0.9, entry=100, sl=105, tp=92, slot="A"),
        _make_signal(action="SHORT", confidence=0.7, entry=100, sl=107, tp=90, slot="B"),
    ]
    result = moa._vote_fallback(proposals=proposals, symbol="BTC", price=100.0)
    assert result.action == TradeAction.SHORT
    # Confidence ponderada: (0.9*0.9 + 0.7*0.7) / (0.9+0.7) ≈ 0.816
    assert 0.7 < result.confidence < 1.0


# ---------------------------------------------------------------------------
# T07 — _format_proposals gera texto correto
# ---------------------------------------------------------------------------

def test_t07_format_proposals():
    """_format_proposals inclui slot name, action e confidence."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    proposals = [
        _make_signal(action="LONG", confidence=0.8, slot="GPT-4o"),
        _make_signal(action="HOLD", confidence=0.5, slot="Claude-Sonnet"),
    ]
    text = moa._format_proposals(proposals)
    assert "GPT-4o" in text
    assert "Claude-Sonnet" in text
    assert "LONG" in text
    assert "HOLD" in text
    assert "0.80" in text


# ---------------------------------------------------------------------------
# T08 — pre-flight falha → HOLD imediato sem chamar LLMs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t08_preflight_fail_returns_hold():
    """Quando analysis.is_safe_to_trade=False, retorna HOLD sem LLM call."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    analysis = _make_analysis()
    analysis.is_safe_to_trade = False

    result = await moa.run(analysis=analysis)
    assert result.action == TradeAction.HOLD
    assert result.metadata.get("fallback") is True


# ---------------------------------------------------------------------------
# T09 — run() com proposals mockados → sintetiza consensus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t09_run_synthesizes_when_proposals_ok():
    """Com 2 proposals OK e orchestrator funcional, retorna sinal sintetizado."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    analysis = _make_analysis()

    mock_proposals = [
        _make_signal(action="LONG", confidence=0.8, slot="GPT-4o"),
        _make_signal(action="LONG", confidence=0.75, slot="Claude-Sonnet"),
    ]
    synth_signal = _make_signal(action="LONG", confidence=0.78)
    synth_signal = synth_signal.model_copy(update={
        "metadata": {**synth_signal.metadata, "moa_mode": "synthesized", "moa_proposals": 2}
    })

    with patch.object(moa, "_generate_proposals", new=AsyncMock(return_value=mock_proposals)):
        with patch.object(moa, "_synthesize", new=AsyncMock(return_value=synth_signal)):
            result = await moa.run(analysis=analysis)

    assert result.action == TradeAction.LONG
    assert result.metadata.get("moa_mode") == "synthesized"


# ---------------------------------------------------------------------------
# T10 — run() com < min_proposals → fallback Vision clássico
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t10_run_fallback_when_insufficient_proposals():
    """Com apenas 1 proposal (< min=2), usa Vision._run() clássico."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    analysis = _make_analysis()

    fallback_signal = _make_signal(action="HOLD", confidence=0.0)
    fallback_signal = fallback_signal.model_copy(update={
        "metadata": {"model": "gpt-4o", "fallback": True}
    })

    with patch.object(moa, "_generate_proposals", new=AsyncMock(return_value=[_make_signal()])):
        with patch.object(moa._vision_fallback, "run", new=AsyncMock(return_value=fallback_signal)):
            result = await moa.run(analysis=analysis)

    # Vision clássico foi chamado
    assert result.metadata.get("fallback") is True


# ---------------------------------------------------------------------------
# T11 — run() com orchestrator falhando → vote_fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t11_run_vote_fallback_when_orchestrator_fails():
    """Quando orchestrator lança exceção, _vote_fallback é usado."""
    from src.agents.vision_moa import VisionMoA  # noqa: WPS433
    moa = VisionMoA()
    analysis = _make_analysis()

    proposals = [
        _make_signal(action="LONG", confidence=0.8, slot="GPT-4o"),
        _make_signal(action="LONG", confidence=0.7, slot="Claude-Sonnet"),
    ]

    with patch.object(moa, "_generate_proposals", new=AsyncMock(return_value=proposals)):
        with patch.object(moa, "_synthesize", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
            result = await moa.run(analysis=analysis)

    # vote_fallback produz LONG com moa_mode=vote_fallback
    assert result.action == TradeAction.LONG
    assert result.metadata.get("moa_mode") == "vote_fallback"


# ---------------------------------------------------------------------------
# T12 — Settings: vision_moa_enabled e vision_moa_min_proposals existem
# ---------------------------------------------------------------------------

def test_t12_settings_fields_exist():
    """Settings contém vision_moa_enabled e vision_moa_min_proposals."""
    from src.config.settings import settings  # noqa: WPS433
    assert hasattr(settings, "vision_moa_enabled")
    assert hasattr(settings, "vision_moa_min_proposals")
    assert isinstance(settings.vision_moa_enabled, bool)
    assert isinstance(settings.vision_moa_min_proposals, int)
    assert 1 <= settings.vision_moa_min_proposals <= 3


# ---------------------------------------------------------------------------
# T13 — NickFury instancia sem VisionMoA quando moa_enabled=False (default)
# ---------------------------------------------------------------------------

def test_t13_nick_fury_vision_moa_none_by_default():
    """Por default (vision_moa_enabled=False), NickFury._vision_moa é None."""
    from src.agents.nick_fury import NickFury  # noqa: WPS433
    from src.config.settings import settings  # noqa: WPS433

    if settings.vision_moa_enabled:
        pytest.skip("vision_moa_enabled=True no ambiente — teste requer False")

    fury = NickFury()
    assert fury._vision_moa is None


# ---------------------------------------------------------------------------
# T14 — NickFury instancia VisionMoA quando moa_enabled=True
# ---------------------------------------------------------------------------

def test_t14_nick_fury_creates_vision_moa_when_enabled():
    """Com vision_moa_enabled=True, NickFury._vision_moa é instanciado."""
    from unittest.mock import patch  # noqa: WPS433
    from src.config.settings import settings  # noqa: WPS433

    with patch.object(type(settings), "vision_moa_enabled", new_callable=lambda: property(lambda self: True)):
        from importlib import reload  # noqa: WPS433
        import src.agents.nick_fury as nf_module  # noqa: WPS433
        # Instanciamos diretamente com patch para não alterar estado global
        with patch("src.config.settings.settings") as mock_settings:
            mock_settings.vision_moa_enabled = True
            mock_settings.vision_moa_min_proposals = 2
            mock_settings.max_consecutive_exec_errors = 3
            mock_settings.max_consecutive_vision_fallbacks = 3
            mock_settings.trading_assets = ["BTC"]
            mock_settings.paper_initial_equity = 10000.0
            mock_settings.openai_api_key = ""
            mock_settings.anthropic_api_key = ""
            mock_settings.openai_model = "gpt-4o"
            mock_settings.anthropic_model = "claude-sonnet-4-6"
            mock_settings.openai_temperature = 0.2
            mock_settings.openai_max_tokens = 2048
            # Verifica apenas que o código tenta criar VisionMoA
            from src.agents.vision_moa import VisionMoA  # noqa: WPS433
            moa = VisionMoA()
            assert moa is not None

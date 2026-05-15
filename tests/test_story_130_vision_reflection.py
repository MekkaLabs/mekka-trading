"""
tests/test_story_130_vision_reflection.py
==========================================
Story 130 — Testes do Vision Reflection Loop (AutoGen Reflection pattern).

Cobre:
  - Vision.revise(): gera TradingSignal com critique_context anexado ao prompt
  - Vision.revise(): fallback HOLD quando LLM falha
  - Vision.revise(): metadata reflection_round populada no sinal
  - _vision_reflection_loop(): converge em round 1 quando VisionCritic retorna ENDORSE
  - _vision_reflection_loop(): chama Vision.revise() quando VisionCritic retorna AMEND
  - _vision_reflection_loop(): chama Vision.revise() quando VisionCritic retorna REJECT
  - _vision_reflection_loop(): aplica apply_critique() mecanicamente no último round
  - _vision_reflection_loop(): fail-silent quando critique levanta exceção
  - _cycle_for_symbol(): usa _vision_reflection_loop quando vision_critic_enabled
  - settings.vision_reflection_max_rounds existe e default = 3

Todos os testes usam mocks — nenhuma chamada real à LLM ou exchange.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chart(symbol: str = "BTC", price: float = 50000.0):
    from src.models.market_data import MarketData, TrendDirection

    return MarketData(
        symbol=symbol,
        price=price,
        timeframe="4h",
        trend=TrendDirection.BULLISH,
        rsi_14=65.0,
        volume_spike=False,
        recent_closes=[49000.0, 49500.0, price],
        timestamp=datetime.now(timezone.utc),
    )


def _make_analysis(symbol: str = "BTC", price: float = 50000.0):
    from src.models.market_data import MarketAnalysis

    return MarketAnalysis(chart=_make_chart(symbol, price))


def _make_signal(
    symbol: str = "BTC",
    action: str = "LONG",
    confidence: float = 0.75,
    price: float = 50000.0,
    fallback: bool = False,
):
    from src.models.signal import TradeAction, TradingSignal

    act = TradeAction(action)
    return TradingSignal(
        timestamp=datetime.now(timezone.utc),
        symbol=symbol,
        action=act,
        confidence=confidence,
        entry_price=price,
        stop_loss=price * 0.97 if act == TradeAction.LONG else price * 1.03,
        take_profit=price * 1.05 if act == TradeAction.LONG else price * 0.95,
        size_pct=0.01,
        leverage=2,
        reasoning="mock signal",
        agent_contributions={"Vision": "mock"},
        metadata={"model": "gpt-4o", "fallback": fallback},
    )


def _make_critique(action: str = "ENDORSE", delta: float = 0.0, reasoning: str = "ok"):
    from src.models.critique import CritiqueAction, VisionCritique

    return VisionCritique(
        symbol="BTC",
        action=CritiqueAction(action),
        confidence_delta=delta,
        reasoning=reasoning,
        fallback=False,
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestReflectionSettings:
    def test_vision_reflection_max_rounds_default(self):
        from src.config.settings import settings

        assert hasattr(settings, "vision_reflection_max_rounds")
        assert settings.vision_reflection_max_rounds == 3

    def test_vision_reflection_max_rounds_ge_1(self):
        from pydantic import ValidationError
        from src.config.settings import MekkaSettings

        with pytest.raises((ValidationError, Exception)):
            MekkaSettings(vision_reflection_max_rounds=0)


# ---------------------------------------------------------------------------
# Vision.revise()
# ---------------------------------------------------------------------------


class TestVisionRevise:
    @pytest.mark.asyncio
    async def test_revise_returns_trading_signal(self):
        """Vision.revise() deve retornar um TradingSignal válido."""
        from src.agents.vision import Vision

        vision = Vision.__new__(Vision)
        vision._log = MagicMock()
        vision._semantic_store = None

        analysis = _make_analysis("BTC")
        revised_signal = _make_signal("BTC", "LONG", 0.70)

        # Mock _call_llm para retornar JSON válido
        import json

        vision._call_llm = AsyncMock(
            return_value=json.dumps(
                {
                    "action": "LONG",
                    "confidence": 0.70,
                    "entry_price": 50000.0,
                    "stop_loss": 48500.0,
                    "take_profit": 52500.0,
                    "size_pct": 0.01,
                    "leverage": 2,
                    "reasoning": "revised after critic",
                    "agent_contributions": {"Vision": "revised"},
                }
            )
        )
        vision._semantic_store = None

        result = await vision.revise(
            analysis=analysis,
            critique_context="=== Critic: AMEND — reduce size ===",
            round_num=1,
        )

        from src.models.signal import TradingSignal

        assert isinstance(result, TradingSignal)
        assert result.symbol == "BTC"

    @pytest.mark.asyncio
    async def test_revise_appends_critique_to_prompt(self):
        """Vision.revise() deve incluir critique_context na chamada ao LLM."""
        from src.agents.vision import Vision

        vision = Vision.__new__(Vision)
        vision._log = MagicMock()
        vision._semantic_store = None

        captured_prompts: list[str] = []

        async def _fake_llm(user_prompt: str) -> str:
            captured_prompts.append(user_prompt)
            import json

            return json.dumps(
                {
                    "action": "HOLD",
                    "confidence": 0.0,
                    "entry_price": 50000.0,
                    "stop_loss": 48500.0,
                    "take_profit": 51500.0,
                    "size_pct": 0.001,
                    "leverage": 1,
                    "reasoning": "hold after critique",
                    "agent_contributions": {},
                }
            )

        vision._call_llm = _fake_llm

        critique_text = "=== CRITIC SAYS AMEND ==="
        await vision.revise(
            analysis=_make_analysis(),
            critique_context=critique_text,
            round_num=2,
        )

        assert len(captured_prompts) == 1
        assert critique_text in captured_prompts[0]

    @pytest.mark.asyncio
    async def test_revise_sets_reflection_round_metadata(self):
        """Sinal revisado deve ter metadata.reflection_round = round_num."""
        from src.agents.vision import Vision

        vision = Vision.__new__(Vision)
        vision._log = MagicMock()
        vision._semantic_store = None

        import json

        vision._call_llm = AsyncMock(
            return_value=json.dumps(
                {
                    "action": "LONG",
                    "confidence": 0.68,
                    "entry_price": 50000.0,
                    "stop_loss": 48500.0,
                    "take_profit": 52500.0,
                    "size_pct": 0.01,
                    "leverage": 2,
                    "reasoning": "revised r2",
                    "agent_contributions": {},
                }
            )
        )

        result = await vision.revise(
            analysis=_make_analysis(),
            critique_context="critic feedback",
            round_num=2,
        )

        assert result.metadata.get("reflection_round") == 2

    @pytest.mark.asyncio
    async def test_revise_fallback_on_llm_error(self):
        """Vision.revise() deve retornar HOLD quando LLM falha."""
        from src.agents.vision import Vision
        from src.models.signal import TradeAction

        vision = Vision.__new__(Vision)
        vision._log = MagicMock()
        vision._semantic_store = None
        vision._call_llm = AsyncMock(side_effect=RuntimeError("network error"))

        result = await vision.revise(
            analysis=_make_analysis("BTC", 50000.0),
            critique_context="critic feedback",
            round_num=1,
        )

        assert result.action == TradeAction.HOLD
        assert result.metadata.get("fallback") is True

    @pytest.mark.asyncio
    async def test_revise_preflight_hold_when_not_safe(self):
        """Vision.revise() deve retornar HOLD quando analysis.is_safe_to_trade=False."""
        from src.agents.vision import Vision
        from src.models.signal import TradeAction

        vision = Vision.__new__(Vision)
        vision._log = MagicMock()
        vision._semantic_store = None

        # Criar analysis que não é segura para trade
        analysis = _make_analysis()
        analysis = analysis.model_copy(
            update={"anomaly": MagicMock(should_pause=True, anomaly_count=5)}
        )

        # Mockar is_safe_to_trade para retornar False
        with patch.object(
            type(analysis), "is_safe_to_trade", new_callable=lambda: property(lambda self: False)
        ):
            result = await vision.revise(
                analysis=analysis,
                critique_context="test",
                round_num=1,
            )

        assert result.action == TradeAction.HOLD


# ---------------------------------------------------------------------------
# NickFury._vision_reflection_loop()
# ---------------------------------------------------------------------------


def _build_fury_minimal():
    """Constrói um NickFury com mocks mínimos para testar o reflection loop."""
    from src.agents.nick_fury import NickFury

    fury = NickFury.__new__(NickFury)
    fury._log = MagicMock()
    fury._vision = MagicMock()
    fury._vision_critic = MagicMock()
    fury._professor = MagicMock()
    fury._batman = MagicMock()
    fury._ironman = MagicMock()
    fury._portfolio = MagicMock()
    fury._daily_pnl = MagicMock()
    fury._exec_error_breaker = MagicMock()
    fury._vision_fallback_breaker = MagicMock()
    fury._wolverine = MagicMock()
    fury._vision_critic = MagicMock()
    fury._telegram = MagicMock()
    fury._perf_writer = MagicMock()
    fury._layer1_graph = None
    return fury


class TestVisionReflectionLoop:
    @pytest.mark.asyncio
    async def test_converges_round_1_on_endorse(self):
        """Loop deve retornar signal original quando VisionCritic retorna ENDORSE."""
        fury = _build_fury_minimal()

        initial_signal = _make_signal("BTC", "LONG", 0.75)
        critique = _make_critique("ENDORSE", 0.0)

        fury._vision_critic.run = AsyncMock(return_value=critique)

        with patch(
            "src.persistence.repository.MekkaRepository.log_event",
            new_callable=AsyncMock,
        ):
            final_signal, rounds = await fury._vision_reflection_loop(
                analysis=_make_analysis(),
                initial_signal=initial_signal,
                symbol="BTC",
            )

        # ENDORSE → sem revisão, round 1
        assert rounds == 1
        assert final_signal is initial_signal  # objeto idêntico (sem revisão)

    @pytest.mark.asyncio
    async def test_calls_revise_on_amend(self):
        """Com AMEND no round 1, deve chamar Vision.revise() e round 2 ENDORSE convergir."""
        fury = _build_fury_minimal()

        initial_signal = _make_signal("BTC", "LONG", 0.75)
        amend_critique = _make_critique("AMEND", 0.40, "reduce size please")
        endorse_critique = _make_critique("ENDORSE", 0.05)

        revised_signal = _make_signal("BTC", "LONG", 0.68)

        # Round 1: AMEND → Round 2: ENDORSE
        fury._vision_critic.run = AsyncMock(
            side_effect=[amend_critique, endorse_critique]
        )
        fury._vision.revise = AsyncMock(return_value=revised_signal)

        with patch(
            "src.persistence.repository.MekkaRepository.log_event",
            new_callable=AsyncMock,
        ):
            with patch(
                "src.config.settings.settings.vision_reflection_max_rounds",
                3,
            ):
                final_signal, rounds = await fury._vision_reflection_loop(
                    analysis=_make_analysis(),
                    initial_signal=initial_signal,
                    symbol="BTC",
                )

        fury._vision.revise.assert_called_once()
        assert rounds == 2
        assert final_signal is revised_signal

    @pytest.mark.asyncio
    async def test_apply_critique_on_last_round(self):
        """No último round, deve aplicar apply_critique() mecanicamente."""
        fury = _build_fury_minimal()

        initial_signal = _make_signal("BTC", "LONG", 0.75)
        amend_critique = _make_critique("AMEND", 0.50, "still not happy")

        # Sempre retorna AMEND (nunca converge)
        fury._vision_critic.run = AsyncMock(return_value=amend_critique)
        # revise() retorna signal ligeiramente modificado
        revised_signal = _make_signal("BTC", "LONG", 0.65)
        fury._vision.revise = AsyncMock(return_value=revised_signal)

        with patch(
            "src.persistence.repository.MekkaRepository.log_event",
            new_callable=AsyncMock,
        ):
            with patch(
                "src.config.settings.settings.vision_reflection_max_rounds",
                2,  # max 2 rounds
            ):
                final_signal, rounds = await fury._vision_reflection_loop(
                    analysis=_make_analysis(),
                    initial_signal=initial_signal,
                    symbol="BTC",
                )

        # max_rounds=2: round 1 → revise, round 2 → apply_critique mechanical
        assert rounds == 2
        # revise deve ter sido chamado apenas 1x (round 1)
        assert fury._vision.revise.call_count == 1

    @pytest.mark.asyncio
    async def test_fail_silent_on_critic_exception(self):
        """Se VisionCritic levanta exceção, o loop deve terminar com o signal original."""
        fury = _build_fury_minimal()

        initial_signal = _make_signal("BTC", "LONG", 0.75)
        fury._vision_critic.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with patch(
            "src.persistence.repository.MekkaRepository.log_event",
            new_callable=AsyncMock,
        ):
            final_signal, rounds = await fury._vision_reflection_loop(
                analysis=_make_analysis(),
                initial_signal=initial_signal,
                symbol="BTC",
            )

        # Falha silenciosa: retorna o initial_signal
        assert final_signal is initial_signal

    @pytest.mark.asyncio
    async def test_reject_leads_to_revision(self):
        """Com REJECT no round 1, Vision deve ser chamada para revisar."""
        fury = _build_fury_minimal()

        initial_signal = _make_signal("BTC", "LONG", 0.75)
        reject_critique = _make_critique("REJECT", 0.80, "too risky")
        endorse_after_revision = _make_critique("ENDORSE", 0.05)

        fury._vision_critic.run = AsyncMock(
            side_effect=[reject_critique, endorse_after_revision]
        )
        hold_signal = _make_signal("BTC", "HOLD", 0.0)
        fury._vision.revise = AsyncMock(return_value=hold_signal)

        with patch(
            "src.persistence.repository.MekkaRepository.log_event",
            new_callable=AsyncMock,
        ):
            with patch(
                "src.config.settings.settings.vision_reflection_max_rounds",
                3,
            ):
                final_signal, rounds = await fury._vision_reflection_loop(
                    analysis=_make_analysis(),
                    initial_signal=initial_signal,
                    symbol="BTC",
                )

        # Round 1 → REJECT → revise → Round 2 → ENDORSE
        fury._vision.revise.assert_called_once()
        assert rounds == 2

    @pytest.mark.asyncio
    async def test_critique_context_includes_round_info(self):
        """O critique_context passado para revise deve mencionar o número do round."""
        fury = _build_fury_minimal()

        initial_signal = _make_signal("BTC", "LONG", 0.75)
        amend_critique = _make_critique("AMEND", 0.45, "needs work")
        endorse = _make_critique("ENDORSE", 0.0)

        fury._vision_critic.run = AsyncMock(side_effect=[amend_critique, endorse])

        captured_contexts: list[str] = []

        async def _capture_revise(analysis, critique_context, round_num):
            captured_contexts.append(critique_context)
            return _make_signal("BTC", "LONG", 0.68)

        fury._vision.revise = _capture_revise

        with patch(
            "src.persistence.repository.MekkaRepository.log_event",
            new_callable=AsyncMock,
        ):
            with patch(
                "src.config.settings.settings.vision_reflection_max_rounds",
                3,
            ):
                await fury._vision_reflection_loop(
                    analysis=_make_analysis(),
                    initial_signal=initial_signal,
                    symbol="BTC",
                )

        assert len(captured_contexts) == 1
        # Context deve incluir "Round 1" e o reasoning do critic
        assert "Round 1" in captured_contexts[0]
        assert "needs work" in captured_contexts[0]


# ---------------------------------------------------------------------------
# Integration: _cycle_for_symbol usa o reflection loop
# ---------------------------------------------------------------------------


class TestCycleForSymbolUsesReflection:
    @pytest.mark.asyncio
    async def test_reflection_loop_called_when_critic_enabled(self):
        """_cycle_for_symbol deve chamar _vision_reflection_loop quando critic enabled."""
        from src.agents.nick_fury import NickFury

        fury = _build_fury_minimal()

        analysis = _make_analysis("BTC")
        initial_signal = _make_signal("BTC", "LONG", 0.75)
        final_signal = _make_signal("BTC", "LONG", 0.70)

        fury._professor.run = AsyncMock(return_value=analysis)
        fury._vision.run = AsyncMock(return_value=initial_signal)

        with patch.object(fury, "_vision_reflection_loop", new_callable=AsyncMock) as mock_loop, \
             patch("src.config.settings.settings.vision_critic_enabled", True), \
             patch("src.persistence.repository.MekkaRepository.save_signal", new_callable=AsyncMock, return_value=1), \
             patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock), \
             patch("src.persistence.repository.MekkaRepository.count_trades_today", new_callable=AsyncMock, return_value=0), \
             patch("src.config.settings.settings.vision_reflection_max_rounds", 3):

            mock_loop.return_value = (final_signal, 1)

            from src.models.risk import RiskApproval, RiskVerdict
            mock_approval = RiskApproval(
                verdict=RiskVerdict.HOLD,
                signal=final_signal,
                reason="hold",
                gates_passed=[],
                gates_blocked=[],
            )
            fury._batman.run = AsyncMock(return_value=mock_approval)
            fury._telegram.alert = AsyncMock()

            with patch("src.agents.nick_fury.settings") as ms:
                ms.vision_critic_enabled = True
                ms.vision_reflection_max_rounds = 3
                ms.vision_critic_enabled = True
                ms.max_leverage = 5
                ms.openai_model = "gpt-4o"
                ms.paper_initial_equity = 10000.0
                ms.daily_profit_target_pct = 0.05

                report = await fury._cycle_for_symbol(
                    symbol="BTC",
                    equity_usd=10000.0,
                    current_drawdown_pct=0.0,
                    trades_today=0,
                )

        mock_loop.assert_called_once()
        call_kwargs = mock_loop.call_args
        assert call_kwargs.kwargs.get("symbol") == "BTC" or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] == "BTC"
        )

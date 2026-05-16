"""
tests/test_story_133_vision_pre_reasoning.py
=============================================
Story 133 — Vision Pre-Reasoning: reflect before generating TradingSignal.

Testes isolados — sem chamadas reais à OpenAI.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vision():
    """Instancia Vision com LLMClient mockado."""
    mock_llm = MagicMock()
    mock_llm.active_provider = "openai"
    mock_llm.close = AsyncMock()
    mock_llm.chat = AsyncMock()

    with patch("src.agents.vision.make_llm_client", return_value=mock_llm):
        from src.agents.vision import Vision
        v = Vision()
        v._llm = mock_llm
        return v, mock_llm


def _make_analysis(symbol: str = "BTC", price: float = 50000.0, is_safe: bool = True):
    """Cria MarketAnalysis mínima para os testes."""
    from unittest.mock import MagicMock
    analysis = MagicMock()
    analysis.symbol = symbol
    analysis.price = price
    analysis.is_safe_to_trade = is_safe
    analysis.to_prompt.return_value = f"MarketAnalysis for {symbol} at ${price}"
    return analysis


_SAMPLE_REASONING = (
    "**Signal Alignment**: Bullish momentum across timeframes with strong RSI. "
    "Slight conflict from elevated funding rate.\n"
    "**Key Risks**: High funding rate may signal overextension; low liquidity on ask side.\n"
    "**Preliminary Bias**: LONG, confidence MED."
)

_SAMPLE_SIGNAL_JSON = (
    '{"action":"LONG","confidence":0.72,"entry_price":50000,"stop_loss":49000,'
    '"take_profit":52000,"size_pct":0.02,"leverage":2,'
    '"reasoning":"Strong bullish setup.","agent_contributions":{"Superman":"bullish"}}'
)


# ---------------------------------------------------------------------------
# Tests — _pre_reason()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPreReason:
    async def test_pre_reason_returns_llm_text(self):
        vision, mock_llm = _make_vision()
        mock_llm.chat = AsyncMock(return_value=_SAMPLE_REASONING)

        result = await vision._pre_reason("some analysis prompt")
        assert "Signal Alignment" in result
        assert "Preliminary Bias" in result

    async def test_pre_reason_empty_response_returns_empty(self):
        vision, mock_llm = _make_vision()
        mock_llm.chat = AsyncMock(return_value="   ")

        result = await vision._pre_reason("prompt")
        assert result == ""

    async def test_pre_reason_short_response_returns_empty(self):
        vision, mock_llm = _make_vision()
        mock_llm.chat = AsyncMock(return_value="OK")  # < 20 chars

        result = await vision._pre_reason("prompt")
        assert result == ""

    async def test_pre_reason_strips_whitespace(self):
        vision, mock_llm = _make_vision()
        mock_llm.chat = AsyncMock(return_value="  " + _SAMPLE_REASONING + "  ")

        result = await vision._pre_reason("prompt")
        assert not result.startswith(" ")
        assert not result.endswith(" ")


# ---------------------------------------------------------------------------
# Tests — _run() integration with pre-reasoning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPreReasoningInRun:
    async def test_pre_reasoning_injected_in_prompt_when_enabled(self):
        """Quando habilitado, o reasoning deve aparecer no prompt final."""
        vision, mock_llm = _make_vision()
        vision._semantic_store = None

        # Primeira call = pre-reasoning, segunda = signal JSON
        mock_llm.chat = AsyncMock(side_effect=[_SAMPLE_REASONING, _SAMPLE_SIGNAL_JSON])

        analysis = _make_analysis()
        with patch("src.agents.vision.settings") as mock_settings:
            mock_settings.vision_pre_reasoning_enabled = True
            mock_settings.vision_critic_enabled = False

            signal = await vision._run(analysis)

        assert mock_llm.chat.call_count == 2
        # Segunda chamada deve conter o pre-reasoning no prompt
        second_call_args = mock_llm.chat.call_args_list[1]
        user_prompt = second_call_args[0][1]  # positional arg [1] = user_prompt
        assert "Pre-Analysis Reasoning" in user_prompt
        assert "Signal Alignment" in user_prompt

    async def test_pre_reasoning_disabled_by_default(self):
        """Quando desabilitado, _run() faz apenas 1 call LLM."""
        vision, mock_llm = _make_vision()
        vision._semantic_store = None

        mock_llm.chat = AsyncMock(return_value=_SAMPLE_SIGNAL_JSON)

        analysis = _make_analysis()
        with patch("src.agents.vision.settings") as mock_settings:
            mock_settings.vision_pre_reasoning_enabled = False

            signal = await vision._run(analysis)

        # Apenas 1 call: sem pre-reasoning
        assert mock_llm.chat.call_count == 1

    async def test_pre_reasoning_fail_silent(self):
        """Se _pre_reason() falha, _run() continua normalmente com 1 call."""
        vision, mock_llm = _make_vision()
        vision._semantic_store = None

        # Primeira call (pre-reasoning) lança exceção, segunda gera sinal
        mock_llm.chat = AsyncMock(side_effect=[Exception("API timeout"), _SAMPLE_SIGNAL_JSON])

        analysis = _make_analysis()
        with patch("src.agents.vision.settings") as mock_settings:
            mock_settings.vision_pre_reasoning_enabled = True

            signal = await vision._run(analysis)

        # Deve ter tentado pre-reasoning (1 call) + sinal (1 call)
        assert mock_llm.chat.call_count == 2
        # Sinal deve ser válido apesar do erro no pre-reasoning
        assert signal.action is not None

    async def test_pre_reasoning_skipped_when_not_safe(self):
        """Se is_safe_to_trade=False, retorna HOLD sem qualquer LLM call."""
        vision, mock_llm = _make_vision()
        vision._semantic_store = None
        mock_llm.chat = AsyncMock(return_value=_SAMPLE_SIGNAL_JSON)

        analysis = _make_analysis(is_safe=False)
        with patch("src.agents.vision.settings") as mock_settings:
            mock_settings.vision_pre_reasoning_enabled = True

            signal = await vision._run(analysis)

        mock_llm.chat.assert_not_called()
        assert signal.action.value == "HOLD"

    async def test_pre_reasoning_injected_before_json_instruction(self):
        """O prompt final deve terminar com instrução para emitir JSON."""
        vision, mock_llm = _make_vision()
        vision._semantic_store = None

        calls = []

        async def capture_chat(system, user):
            calls.append((system, user))
            if len(calls) == 1:
                return _SAMPLE_REASONING
            return _SAMPLE_SIGNAL_JSON

        mock_llm.chat = capture_chat

        analysis = _make_analysis()
        with patch("src.agents.vision.settings") as mock_settings:
            mock_settings.vision_pre_reasoning_enabled = True

            await vision._run(analysis)

        assert len(calls) == 2
        final_user_prompt = calls[1][1]
        assert "produce the final TradingSignal JSON" in final_user_prompt


# ---------------------------------------------------------------------------
# Tests — Settings
# ---------------------------------------------------------------------------

class TestSettings133:
    def test_settings_has_pre_reasoning_field(self):
        from src.config.settings import settings
        assert hasattr(settings, "vision_pre_reasoning_enabled")

    def test_default_is_false(self):
        from src.config.settings import settings
        assert settings.vision_pre_reasoning_enabled is False


# ---------------------------------------------------------------------------
# Tests — _PRE_REASONING_SYSTEM prompt
# ---------------------------------------------------------------------------

class TestPreReasoningPrompt:
    def test_system_prompt_exists(self):
        from src.agents.vision import _PRE_REASONING_SYSTEM
        assert len(_PRE_REASONING_SYSTEM) > 50

    def test_system_prompt_requests_three_sections(self):
        from src.agents.vision import _PRE_REASONING_SYSTEM
        assert "Signal Alignment" in _PRE_REASONING_SYSTEM
        assert "Key Risks" in _PRE_REASONING_SYSTEM
        assert "Preliminary Bias" in _PRE_REASONING_SYSTEM

    def test_system_prompt_no_json_instruction(self):
        """Pre-reasoning não deve pedir JSON output."""
        from src.agents.vision import _PRE_REASONING_SYSTEM
        # Deve pedir texto livre, não JSON
        assert "NOT to produce a trade signal" in _PRE_REASONING_SYSTEM

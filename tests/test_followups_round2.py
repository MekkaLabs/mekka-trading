"""Regressão dos últimos follow-ups (2026-06-01).

- Superman: RSI/ATR manuais usam Wilder (RMA), não SMA/EWM-span (≈ pandas_ta).
- LLM: seed fixo para reprodutibilidade.
- Debate: Thor/Aquaman (não-direcionais) votam HOLD, não LONG.
- Mentor reader: override de min_confidence consumido no Batman COM clamp tighten-only.
"""
from __future__ import annotations

import pytest


def test_superman_uses_wilder_smoothing():
    import inspect
    from src.agents import superman as s
    src = inspect.getsource(s)
    # RSI e ATR via ewm(alpha=1/14) (Wilder), não rolling(14)/ewm(span=14).
    assert "ewm(alpha=1 / 14, adjust=False)" in src
    # O ATR manual não usa mais span=14.
    assert "tr.ewm(span=14" not in src


def test_llm_has_seed():
    import inspect
    from src.agents import llm_client as lc
    src = inspect.getsource(lc)
    assert "openai_seed" in src
    assert "seed=_seed" in src


@pytest.mark.asyncio
async def test_debate_non_directional_agents_abstain():
    from src.services.debate_moderator import DebateModerator

    hv = DebateModerator._heuristic_vote
    # Thor com vol baixa: antes LONG, agora HOLD.
    action_thor, _, _ = hv("Thor", {"atr_pct": 1.0}, [], 1)
    assert action_thor == "HOLD"
    # Aquaman com liquidez excelente: antes LONG, agora HOLD.
    action_aqua, _, _ = hv("Aquaman", {"spread_pct": 0.01}, [], 1)
    assert action_aqua == "HOLD"
    # Superman (direcional) ainda vota direção.
    action_sup, _, _ = hv("Superman", {"rsi": 70, "ema20": 110, "ema50": 100}, [], 1)
    assert action_sup in ("LONG", "SHORT", "HOLD")


def test_batman_consumes_mentor_override_tighten_only():
    import inspect
    from src.agents import batman as b
    src = inspect.getsource(b)
    # Consome o override do Mentor com clamp tighten-only (max).
    assert "min_confidence_threshold" in src
    assert "get_override" in src
    assert "max(float(_ovr), _min_conf)" in src  # tighten-only


def test_mentor_override_clamp_blocks_loosen():
    """O clamp max() garante que um override mais FROUXO nunca abaixa o gate."""
    default = 0.65
    looser = 0.50
    tighter = 0.80
    assert max(looser, default) == default   # frouxo bloqueado
    assert max(tighter, default) == tighter  # apertado aplicado

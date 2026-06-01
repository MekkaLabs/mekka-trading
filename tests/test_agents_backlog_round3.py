"""Regressão do backlog de agentes — rodada 3 (2026-06-01).

- MoA: _vote_fallback envolvido (não quebra never-raises) + aplica clamps do Vision.
- base.py: CancelledError tratado explicitamente (propaga, não vira AgentError).
- Cable adapter: funding 8h → horário (unidade única com Black Panther/Hyperliquid).
"""
from __future__ import annotations

import pytest


# ===========================================================================
# Cable adapter — normalização de unidade do funding (8h → horário)
# ===========================================================================

@pytest.mark.asyncio
async def test_cable_funding_normalized_to_hourly():
    from unittest.mock import patch, AsyncMock
    from src.services import cable_regime_adapter as ad

    # Cable reporta funding 8h = 0.008 (0.8%/8h). Esperado injetar 0.001/h.
    with patch.object(ad, "is_enabled", return_value=True), \
         patch.object(ad, "get_cable_snapshot", AsyncMock(return_value={"dummy": True})), \
         patch.object(ad, "extract_funding_for_symbol", return_value=0.008):
        # analysis com onchain.funding_rate ausente (None) → injeta
        class _OnChain:
            funding_rate = None
        class _Analysis:
            onchain = _OnChain()
        res = await ad.enrich_analysis_with_cable(_Analysis(), "BTC")

    assert res["applied"] is True
    assert res["funding_rate"] == pytest.approx(0.008 / 8.0)   # horário
    assert res["funding_rate_8h"] == pytest.approx(0.008)       # 8h cru preservado


def test_cable_adapter_converts_in_source():
    import inspect
    from src.services import cable_regime_adapter as ad
    src = inspect.getsource(ad.enrich_analysis_with_cable)
    assert "cable_funding / 8.0" in src
    assert "cable_funding_hourly" in src


# ===========================================================================
# MoA — vote_fallback protegido + clamps de segurança
# ===========================================================================

def test_moa_vote_fallback_wrapped_and_clamps_applied():
    import inspect
    from src.agents import vision_moa as vm
    src = inspect.getsource(vm.VisionMoA.run if hasattr(vm.VisionMoA, "run") else vm.VisionMoA._run)
    # vote_fallback envolto + fallback HOLD.
    assert "vote fallback crashou" in src or "_fallback_hold" in src
    # clamps determinísticos do Vision aplicados no caminho MoA.
    assert "_apply_degraded_quality_clamp" in src
    assert "_apply_flash_scalp_hard_block" in src


# ===========================================================================
# base.py — CancelledError explícito
# ===========================================================================

def test_base_agent_handles_cancelled_error():
    import inspect
    from src.agents import base as b
    src = inspect.getsource(b.BaseAgent.run)
    assert "except asyncio.CancelledError" in src

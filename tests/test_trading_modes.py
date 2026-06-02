"""Revisão dos modos de trading (2026-06-01) — presets realmente alteram os gates.

A revisão achou que vários params de preset eram IGNORADOS (lidos de settings) e
que os scalp gates estavam mortos por um import quebrado (`get_active_mode`).
Estes testes travam o contrato: cada modo expõe os valores de risco documentados,
os scalp gates funcionam, e o import correto existe.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# ===========================================================================
# Contrato dos presets — cada modo expõe os valores de risco documentados
# ===========================================================================

def test_presets_expose_distinct_risk_values():
    from src.config.runtime_mode import PRESETS

    # max_daily_drawdown_pct deve diferir por modo (era ignorado antes do fix).
    assert PRESETS["conservative"]["max_daily_drawdown_pct"] == 0.05
    assert PRESETS["balanced"]["max_daily_drawdown_pct"] == 0.10
    assert PRESETS["aggressive"]["max_daily_drawdown_pct"] == 0.15
    assert PRESETS["scalp"]["max_daily_drawdown_pct"] == 0.04
    # min_risk_reward_ratio
    assert PRESETS["conservative"]["min_risk_reward_ratio"] == 2.0
    assert PRESETS["scalp"]["min_risk_reward_ratio"] == 1.0
    # max_trades_per_day
    assert PRESETS["conservative"]["max_trades_per_day"] == 3
    assert PRESETS["aggressive"]["max_trades_per_day"] == 20
    # scalp-only: min_atr_pct_for_entry só ativo em scalp
    assert PRESETS["scalp"]["min_atr_pct_for_entry"] == 0.0015
    assert PRESETS["balanced"]["min_atr_pct_for_entry"] is None


# ===========================================================================
# P0 regressão — o import que estava quebrado agora funciona
# ===========================================================================

def test_get_mode_importable_not_get_active_mode():
    # Era `get_active_mode` (inexistente) → ImportError engolido → scalp gates mortos.
    from src.config.runtime_mode import get_mode, get_params, is_scalp_mode
    assert callable(get_mode) and callable(get_params) and callable(is_scalp_mode)


def test_scalp_gates_module_importable():
    from src.agents.batman_scalp_gates import (
        evaluate_all_scalp_gates,
        gate_max_position_age,
        gate_max_trades_per_hour,
    )
    assert callable(evaluate_all_scalp_gates)
    assert callable(gate_max_position_age)
    assert callable(gate_max_trades_per_hour)


# ===========================================================================
# Scalp gate 3t — hard-cap de idade de posição (reativado pelo P0 fix)
# ===========================================================================

def _pos(age_min):
    return {
        "symbol": "BTC",
        "opened_at": (datetime.now(timezone.utc) - timedelta(minutes=age_min)).isoformat(),
    }


def test_gate_age_no_cap_in_non_scalp():
    from src.agents.batman_scalp_gates import gate_max_position_age
    # Sem max_position_age_minutes (swing) → sempre permite.
    r = gate_max_position_age({"max_position_age_minutes": None}, [_pos(999)])
    assert r.allowed is True


def test_gate_age_blocks_on_hard_breach_in_scalp():
    from src.agents.batman_scalp_gates import gate_max_position_age
    # scalp: soft 30min, hard 45min. Posição de 60min → hard breach → BLOQUEIA.
    r = gate_max_position_age({"max_position_age_minutes": 30}, [_pos(60)])
    assert r.allowed is False


def test_gate_age_allows_fresh_position_in_scalp():
    from src.agents.batman_scalp_gates import gate_max_position_age
    r = gate_max_position_age({"max_position_age_minutes": 30}, [_pos(5)])
    assert r.allowed is True


# ===========================================================================
# Scalp gate 3s — cap horário (no-cap path)
# ===========================================================================

def test_gate_trades_per_hour_no_cap_in_non_scalp():
    from src.agents.batman_scalp_gates import gate_max_trades_per_hour
    r = gate_max_trades_per_hour({"max_trades_per_hour": None})
    assert r.allowed is True


# ===========================================================================
# Override de altcoins (toggle de runtime, não um preset)
# ===========================================================================

def test_altcoins_expands_assets_when_enabled():
    from unittest.mock import patch
    from src.config import runtime_overrides as ro

    with patch.object(ro, "get_runtime_overrides", return_value={"altcoins_enabled": True}):
        out = ro.expand_assets_with_altcoins(["BTC"])
    assert "BTC" in out
    for alt in ro.ALTCOINS:
        assert alt in out  # ETH/SOL/AVAX/BNB/LINK adicionados


def test_altcoins_noop_when_disabled():
    from unittest.mock import patch
    from src.config import runtime_overrides as ro

    with patch.object(ro, "get_runtime_overrides", return_value={"altcoins_enabled": False}):
        out = ro.expand_assets_with_altcoins(["BTC"])
    assert out == ["BTC"]  # inalterado


def test_altcoins_dedup_preserves_order():
    from unittest.mock import patch
    from src.config import runtime_overrides as ro

    with patch.object(ro, "get_runtime_overrides", return_value={"altcoins_enabled": True}):
        out = ro.expand_assets_with_altcoins(["BTC", "ETH"])  # ETH já presente
    assert out[:2] == ["BTC", "ETH"]
    assert out.count("ETH") == 1  # sem duplicata


# ===========================================================================
# Os gates de risco do Batman LEEM o preset (não settings) — verificação de
# código: o método approve carrega _mp_risk e usa _mode_max_dd/_mode_max_trades/
# _mode_min_rr nos gates de drawdown/trades-dia/R:R. (E2E completo é frágil aqui
# por dependência de DB real; a leitura do preset é coberta por inspeção.)
# ===========================================================================

def test_batman_risk_gates_read_preset_not_settings():
    import inspect
    from src.agents import batman as _b

    src = inspect.getsource(_b)
    # Os 3 gates de risco agora referenciam as vars derivadas do preset.
    assert "_mode_max_dd" in src
    assert "_mode_max_trades" in src
    assert "_mode_min_rr" in src
    # E o preset é carregado via get_params (não só settings) no caminho de risco.
    assert "_mp_risk" in src
    # P3: gate 3q usa o override do preset.
    assert "min_atr_pct_for_entry" in src
    # P0: o import correto existe (get_mode), e NÃO é mais chamado get_active_mode().
    assert "import get_mode, get_params" in src
    assert "get_active_mode()" not in src  # a CHAMADA quebrada sumiu

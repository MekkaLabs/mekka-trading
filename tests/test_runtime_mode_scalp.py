"""
tests/test_runtime_mode_scalp.py
==================================
Cobertura do novo preset 'scalp' adicionado em runtime_mode.py.

Foco:
  - preset shape válido
  - backward-compat: presets antigos não quebraram (ganharam campos None)
  - helper is_scalp_mode
  - SCALP_MODES frozenset extensível
"""

from __future__ import annotations

import pytest

from src.config.runtime_mode import (
    DEFAULT_MODE,
    PRESETS,
    SCALP_MODES,
    VALID_MODES,
    get_params,
    is_scalp_mode,
    set_mode,
)


# Campos novos esperados em TODOS os presets (mesmo no-op nos antigos)
_SCALP_FIELDS = (
    "max_trades_per_hour",
    "max_position_age_minutes",
    "scalp_primary_timeframe",
    "scalp_confirmation_timeframe",
    "main_loop_interval_seconds",
    "flash_is_proposer",
    "min_atr_pct_for_entry",
)


class TestPresetShape:
    def test_scalp_preset_exists(self):
        assert "scalp" in PRESETS
        assert "scalp" in VALID_MODES

    def test_scalp_has_all_scalp_fields(self):
        scalp = PRESETS["scalp"]
        for field in _SCALP_FIELDS:
            assert field in scalp, f"scalp preset missing field: {field}"

    def test_scalp_values_are_active(self):
        """Scalp preset deve ter VALORES (não None) para campos scalp."""
        scalp = PRESETS["scalp"]
        assert scalp["max_trades_per_hour"] == 6
        assert scalp["max_position_age_minutes"] == 30
        assert scalp["scalp_primary_timeframe"] == "5m"
        assert scalp["scalp_confirmation_timeframe"] == "1m"
        assert scalp["main_loop_interval_seconds"] == 120
        assert scalp["flash_is_proposer"] is True
        assert scalp["min_atr_pct_for_entry"] == pytest.approx(0.0015)

    def test_scalp_risk_caps_apertados(self):
        scalp = PRESETS["scalp"]
        # Position size menor que aggressive (5%) e balanced (2%)
        assert scalp["max_position_size_pct"] <= 0.02
        # Leverage menor que aggressive (10x)
        assert scalp["max_leverage"] <= 5
        # Drawdown apertado pq mais trades
        assert scalp["max_daily_drawdown_pct"] <= 0.05
        # Trading assets restritos aos mais líquidos
        assert set(scalp["trading_assets"]).issubset({"BTC", "ETH"})


class TestBackwardCompat:
    """Presets antigos (conservative, balanced, aggressive) ganharam os campos
    scalp como None / False — código que ler get_params() não pode crashar."""

    @pytest.mark.parametrize("mode", ["conservative", "balanced", "aggressive"])
    def test_old_presets_have_scalp_fields(self, mode):
        preset = PRESETS[mode]
        for field in _SCALP_FIELDS:
            assert field in preset, f"{mode} missing {field}"

    @pytest.mark.parametrize("mode", ["conservative", "balanced", "aggressive"])
    def test_old_presets_scalp_fields_are_noop(self, mode):
        preset = PRESETS[mode]
        # Todos None ou False — caller usa fallback (settings.py default)
        assert preset["max_trades_per_hour"] is None
        assert preset["max_position_age_minutes"] is None
        assert preset["scalp_primary_timeframe"] is None
        assert preset["scalp_confirmation_timeframe"] is None
        assert preset["main_loop_interval_seconds"] is None
        assert preset["flash_is_proposer"] is False
        assert preset["min_atr_pct_for_entry"] is None

    @pytest.mark.parametrize("mode", ["conservative", "balanced", "aggressive"])
    def test_old_presets_traditional_fields_intact(self, mode):
        """Campos originais (max_position_size_pct, etc) não foram tocados."""
        preset = PRESETS[mode]
        assert "max_position_size_pct" in preset
        assert "max_leverage" in preset
        assert "max_trades_per_day" in preset
        assert "trading_assets" in preset


class TestIsScalpMode:
    def test_scalp_in_scalp_modes(self):
        assert "scalp" in SCALP_MODES

    def test_balanced_not_in_scalp_modes(self):
        assert "balanced" not in SCALP_MODES

    def test_is_scalp_with_explicit_mode(self):
        assert is_scalp_mode("scalp") is True
        assert is_scalp_mode("balanced") is False
        assert is_scalp_mode("aggressive") is False
        assert is_scalp_mode("conservative") is False

    def test_is_scalp_with_current_mode(self):
        set_mode("scalp")
        try:
            assert is_scalp_mode() is True
            set_mode("balanced")
            assert is_scalp_mode() is False
        finally:
            set_mode(DEFAULT_MODE)

    def test_is_scalp_unknown_mode_returns_false(self):
        assert is_scalp_mode("nonexistent_mode") is False
        assert is_scalp_mode(None) in (True, False)  # depende do current


class TestSetModeScalp:
    def test_can_set_scalp_mode(self):
        try:
            # set_mode retorna o dict do preset, não a string
            result = set_mode("scalp")
            assert isinstance(result, dict)
            assert result["flash_is_proposer"] is True
            params = get_params()
            assert params["flash_is_proposer"] is True
            assert params["main_loop_interval_seconds"] == 120
            assert is_scalp_mode() is True
        finally:
            set_mode(DEFAULT_MODE)

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            set_mode("ultra_scalp_xyz")

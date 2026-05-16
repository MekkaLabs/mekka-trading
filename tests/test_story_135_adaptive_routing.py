"""
tests/test_story_135_adaptive_routing.py
=========================================
Story 135 — Adaptive Layer 1 Routing: ProfessorX decide quais agentes
Layer 1 executar baseado no regime de mercado (ATR%).

Testes isolados — sem LangGraph real.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.langgraph.layer1_graph import (
    _classify_regime,
    _decide_skip_set,
    _REGIME_EXTREME,
    _REGIME_HIGH,
    _REGIME_LOW,
    _REGIME_NORMAL,
)


# ---------------------------------------------------------------------------
# _classify_regime
# ---------------------------------------------------------------------------

class TestClassifyRegime:
    def test_none_chart_returns_normal(self):
        assert _classify_regime(None) == _REGIME_NORMAL

    def test_missing_atr_returns_normal(self):
        assert _classify_regime({"rsi_14": 60}) == _REGIME_NORMAL

    def test_atr_extreme(self):
        assert _classify_regime({"atr_pct": 6.0}) == _REGIME_EXTREME

    def test_atr_high(self):
        assert _classify_regime({"atr_pct": 3.5}) == _REGIME_HIGH

    def test_atr_normal(self):
        assert _classify_regime({"atr_pct": 1.0}) == _REGIME_NORMAL

    def test_atr_low(self):
        assert _classify_regime({"atr_pct": 0.3}) == _REGIME_LOW

    def test_boundary_extreme(self):
        # exatamente 5.0 não é > 5.0 → HIGH
        assert _classify_regime({"atr_pct": 5.0}) == _REGIME_HIGH

    def test_boundary_high(self):
        # exatamente 2.0 não é > 2.0 → NORMAL
        assert _classify_regime({"atr_pct": 2.0}) == _REGIME_NORMAL

    def test_boundary_low(self):
        # exatamente 0.5 não é < 0.5 → NORMAL
        assert _classify_regime({"atr_pct": 0.5}) == _REGIME_NORMAL

    def test_regime_field_passthrough(self):
        """Se atr_pct ausente mas regime field presente, usa-o."""
        assert _classify_regime({"regime": "EXTREME"}) == _REGIME_EXTREME
        assert _classify_regime({"regime": "LOW"}) == _REGIME_LOW

    def test_atr_percent_alias(self):
        """Aceita 'atr_percent' como alias de 'atr_pct'."""
        assert _classify_regime({"atr_percent": 6.0}) == _REGIME_EXTREME


# ---------------------------------------------------------------------------
# _decide_skip_set — routing disabled
# ---------------------------------------------------------------------------

class TestDecideSkipSetDisabled:
    def test_routing_disabled_returns_empty(self):
        with patch("src.config.settings.settings") as mock_s:
            mock_s.layer1_routing_enabled = False
            result = _decide_skip_set({"atr_pct": 10.0})
        assert result == []

    def test_routing_disabled_even_extreme_vol(self):
        with patch("src.config.settings.settings") as mock_s:
            mock_s.layer1_routing_enabled = False
            result = _decide_skip_set({"atr_pct": 99.0})
        assert result == []


# ---------------------------------------------------------------------------
# _decide_skip_set — defaults por regime
# ---------------------------------------------------------------------------

class TestDecideSkipSetDefaults:
    def _enabled_settings(self, **kwargs):
        """Mock settings com routing habilitado e overrides opcionais."""
        mock = type("Settings", (), {
            "layer1_routing_enabled": True,
            "layer1_routing_normal_skip": None,
            "layer1_routing_high_skip": None,
            "layer1_routing_extreme_skip": None,
            "layer1_routing_low_skip": None,
        })()
        for k, v in kwargs.items():
            setattr(mock, k, v)
        return mock

    def test_normal_regime_empty_skip(self):
        with patch("src.config.settings.settings", self._enabled_settings()):
            result = _decide_skip_set({"atr_pct": 1.0})
        assert result == []

    def test_high_regime_skips_flash(self):
        with patch("src.config.settings.settings", self._enabled_settings()):
            result = _decide_skip_set({"atr_pct": 3.5})
        assert result == ["flash"]

    def test_extreme_regime_skips_sentiment_flash(self):
        with patch("src.config.settings.settings", self._enabled_settings()):
            result = _decide_skip_set({"atr_pct": 6.0})
        assert "sentiment" in result
        assert "flash" in result

    def test_low_regime_skips_onchain_flash(self):
        with patch("src.config.settings.settings", self._enabled_settings()):
            result = _decide_skip_set({"atr_pct": 0.2})
        assert "onchain" in result
        assert "flash" in result

    def test_none_chart_normal_no_skip(self):
        with patch("src.config.settings.settings", self._enabled_settings()):
            result = _decide_skip_set(None)
        assert result == []


# ---------------------------------------------------------------------------
# _decide_skip_set — settings overrides
# ---------------------------------------------------------------------------

class TestDecideSkipSetOverrides:
    def test_custom_extreme_skip(self):
        with patch("src.config.settings.settings") as mock_s:
            mock_s.layer1_routing_enabled = True
            mock_s.layer1_routing_extreme_skip = "thor,aquaman"
            result = _decide_skip_set({"atr_pct": 6.0})
        assert "thor" in result
        assert "aquaman" in result
        assert "flash" not in result  # não está no override customizado

    def test_custom_high_skip_empty_string(self):
        """Override com string vazia = não pular nada no HIGH."""
        with patch("src.config.settings.settings") as mock_s:
            mock_s.layer1_routing_enabled = True
            mock_s.layer1_routing_high_skip = ""
            result = _decide_skip_set({"atr_pct": 3.5})
        assert result == []

    def test_csv_parsing(self):
        """CSV com espaços extras deve ser limpo."""
        with patch("src.config.settings.settings") as mock_s:
            mock_s.layer1_routing_enabled = True
            mock_s.layer1_routing_normal_skip = " sentiment , flash "
            result = _decide_skip_set({"atr_pct": 1.0})
        assert result == ["sentiment", "flash"]


# ---------------------------------------------------------------------------
# Layer1State skip_set field
# ---------------------------------------------------------------------------

class TestLayer1StateSkipSet:
    def test_skip_set_field_exists(self):
        from src.langgraph.layer1_graph import Layer1State
        # TypedDict — verifica que o campo está nas annotations
        assert "skip_set" in Layer1State.__annotations__


# ---------------------------------------------------------------------------
# Settings fields
# ---------------------------------------------------------------------------

class TestSettings135:
    def test_routing_fields_exist(self):
        from src.config.settings import settings
        assert hasattr(settings, "layer1_routing_enabled")
        assert hasattr(settings, "layer1_routing_normal_skip")
        assert hasattr(settings, "layer1_routing_high_skip")
        assert hasattr(settings, "layer1_routing_extreme_skip")
        assert hasattr(settings, "layer1_routing_low_skip")

    def test_default_disabled(self):
        from src.config.settings import settings
        assert settings.layer1_routing_enabled is False

    def test_default_extreme_skip(self):
        from src.config.settings import settings
        assert "sentiment" in settings.layer1_routing_extreme_skip
        assert "flash" in settings.layer1_routing_extreme_skip

"""
tests/test_story_158_signal_validator.py
==========================================
Story 158 — SignalValidator: Linter-on-Edit Pré-Batman.

Inspirado no mecanismo de linting do SWE-agent:
  "Edits are validated by a built-in linter, with syntactically invalid
   changes automatically rejected."
  "At each step, malformed generations trigger an error response that
   prompts the model to try again until a valid generation is received."

Testa:
- ValidationResult: is_valid, errors, warnings, error_summary, has_warnings, to_dict
- SignalValidator._check_symbol: vazio, uppercase
- SignalValidator._check_confidence: LONG/SHORT mínimos, HOLD sem restrição
- SignalValidator._check_geometry: SL/TP/entry coerência LONG e SHORT
- SignalValidator._check_risk_reward: R:R mínimo, warning zona baixa
- SignalValidator._check_total_risk: size_pct × leverage <= 20%
- SignalValidator._check_reasoning: warning se vazio/curto
- validate(): fail-silent — nunca levanta exceção
- get_signal_validator() singleton / reset
- Sinal completamente válido passa sem erros
"""

from __future__ import annotations

from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers para criar sinais mock sem depender de TradingSignal real
# ---------------------------------------------------------------------------

def _make_signal(
    symbol: str = "BTC",
    action: str = "LONG",
    confidence: float = 0.70,
    entry_price: float = 100.0,
    stop_loss: float = 90.0,
    take_profit: float = 120.0,
    size_pct: float = 0.05,
    leverage: int = 2,
    reasoning: str = "Strong bullish momentum confirmed by RSI and volume.",
) -> MagicMock:
    """Cria um mock de TradingSignal com os valores fornecidos."""
    from unittest.mock import MagicMock
    sig = MagicMock()
    sig.symbol = symbol
    sig.confidence = confidence
    sig.entry_price = entry_price
    sig.stop_loss = stop_loss
    sig.take_profit = take_profit
    sig.size_pct = size_pct
    sig.leverage = leverage
    sig.reasoning = reasoning

    # Mock TradeAction enum
    action_map = {"LONG": "LONG", "SHORT": "SHORT", "HOLD": "HOLD"}
    sig.action = action_map.get(action, action)
    return sig


def _load_modules():
    """Carrega SignalValidator e TradeAction mockando dependências."""
    import sys
    import types
    import importlib.util

    # Mock loguru
    if 'loguru' not in sys.modules:
        loguru_mod = types.ModuleType('loguru')
        class FL:
            def warning(self, *a, **k): pass
            def debug(self, *a, **k): pass
            def error(self, *a, **k): pass
            def info(self, *a, **k): pass
        loguru_mod.logger = FL()
        sys.modules['loguru'] = loguru_mod

    # Mock src.models.signal com TradeAction
    src_mod = types.ModuleType('src')
    src_models = types.ModuleType('src.models')
    src_signal = types.ModuleType('src.models.signal')

    class TradeAction:
        LONG = "LONG"
        SHORT = "SHORT"
        HOLD = "HOLD"

    src_signal.TradeAction = TradeAction
    sys.modules.setdefault('src', src_mod)
    sys.modules.setdefault('src.models', src_models)
    sys.modules['src.models.signal'] = src_signal

    # Load signal_validator
    spec = importlib.util.spec_from_file_location(
        'src.services.signal_validator',
        'src/services/signal_validator.py',
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules['src.services.signal_validator'] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# TestValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_valid_result_no_errors(self):
        mod = _load_modules()
        vr = mod.ValidationResult(is_valid=True, symbol="BTC")
        assert vr.is_valid is True
        assert vr.errors == []
        assert vr.warnings == []

    def test_error_summary_empty_when_no_errors(self):
        mod = _load_modules()
        vr = mod.ValidationResult(is_valid=True, symbol="ETH")
        assert vr.error_summary == ""

    def test_error_summary_format(self):
        mod = _load_modules()
        vr = mod.ValidationResult(is_valid=False, symbol="BTC", errors=["bad geometry", "low confidence"])
        summary = vr.error_summary
        assert "SIGNAL_INVALID(BTC)" in summary
        assert "bad geometry" in summary
        assert "low confidence" in summary

    def test_has_warnings_false_when_empty(self):
        mod = _load_modules()
        vr = mod.ValidationResult(is_valid=True, symbol="BTC")
        assert vr.has_warnings is False

    def test_has_warnings_true_when_present(self):
        mod = _load_modules()
        vr = mod.ValidationResult(is_valid=True, symbol="BTC", warnings=["low R:R"])
        assert vr.has_warnings is True

    def test_to_dict_structure(self):
        mod = _load_modules()
        vr = mod.ValidationResult(is_valid=True, symbol="BTC", errors=[], warnings=["warn1"])
        d = vr.to_dict()
        assert d["is_valid"] is True
        assert d["symbol"] == "BTC"
        assert d["errors"] == []
        assert d["warnings"] == ["warn1"]


# ---------------------------------------------------------------------------
# TestCheckSymbol
# ---------------------------------------------------------------------------

class TestCheckSymbol:
    def test_valid_symbol_no_error(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(symbol="BTC")
        result = v.validate(sig)
        assert "symbol" not in " ".join(result.errors)

    def test_empty_symbol_error(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(symbol="")
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("symbol" in e for e in result.errors)

    def test_whitespace_symbol_error(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(symbol="   ")
        result = v.validate(sig)
        assert result.is_valid is False

    def test_lowercase_symbol_warning(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(symbol="btc")
        result = v.validate(sig)
        # lowercase gera warning, não erro (signal ainda pode ser válido se resto ok)
        assert any("uppercase" in w or "btc" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# TestCheckConfidence
# ---------------------------------------------------------------------------

class TestCheckConfidence:
    def test_long_confidence_ok(self):
        mod = _load_modules()
        v = mod.SignalValidator(min_confidence_long=0.55)
        sig = _make_signal(action="LONG", confidence=0.60)
        result = v.validate(sig)
        assert not any("confidence" in e for e in result.errors)

    def test_long_confidence_too_low(self):
        mod = _load_modules()
        v = mod.SignalValidator(min_confidence_long=0.55)
        sig = _make_signal(action="LONG", confidence=0.40)
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("confidence" in e for e in result.errors)

    def test_short_confidence_ok(self):
        mod = _load_modules()
        v = mod.SignalValidator(min_confidence_short=0.60)
        sig = _make_signal(
            action="SHORT",
            confidence=0.65,
            entry_price=100.0,
            stop_loss=110.0,   # SHORT: SL > entry
            take_profit=85.0,  # SHORT: TP < entry
        )
        result = v.validate(sig)
        assert not any("confidence" in e for e in result.errors)

    def test_short_confidence_too_low(self):
        mod = _load_modules()
        v = mod.SignalValidator(min_confidence_short=0.60)
        sig = _make_signal(
            action="SHORT",
            confidence=0.50,
            entry_price=100.0,
            stop_loss=110.0,
            take_profit=85.0,
        )
        result = v.validate(sig)
        assert any("confidence" in e for e in result.errors)

    def test_hold_no_confidence_restriction(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(action="HOLD", confidence=0.01)
        result = v.validate(sig)
        assert not any("confidence" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestCheckGeometry
# ---------------------------------------------------------------------------

class TestCheckGeometry:
    def test_long_valid_geometry(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(
            action="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
        )
        result = v.validate(sig)
        assert not any("stop_loss" in e or "take_profit" in e for e in result.errors)

    def test_long_sl_above_entry_error(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(
            action="LONG",
            entry_price=100.0,
            stop_loss=105.0,   # SL > entry — INVÁLIDO
            take_profit=120.0,
        )
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("stop_loss" in e for e in result.errors)

    def test_long_tp_below_entry_error(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(
            action="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=95.0,  # TP < entry — INVÁLIDO
        )
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("take_profit" in e for e in result.errors)

    def test_short_valid_geometry(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(
            action="SHORT",
            entry_price=100.0,
            stop_loss=110.0,  # SL > entry — CORRETO para SHORT
            take_profit=85.0,  # TP < entry — CORRETO para SHORT
            confidence=0.65,
        )
        result = v.validate(sig)
        assert not any("stop_loss" in e or "take_profit" in e for e in result.errors)

    def test_short_sl_below_entry_error(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(
            action="SHORT",
            entry_price=100.0,
            stop_loss=90.0,  # SL < entry — INVÁLIDO para SHORT
            take_profit=85.0,
            confidence=0.65,
        )
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("stop_loss" in e for e in result.errors)

    def test_entry_price_zero_error(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(action="LONG", entry_price=0.0)
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("entry_price" in e for e in result.errors)

    def test_hold_no_geometry_check(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(action="HOLD", entry_price=0.0, stop_loss=0.0, take_profit=0.0)
        result = v.validate(sig)
        # HOLD não tem restrição geométrica
        assert not any("entry_price" in e or "geometry" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestCheckRiskReward
# ---------------------------------------------------------------------------

class TestCheckRiskReward:
    def test_good_rr_no_error(self):
        mod = _load_modules()
        v = mod.SignalValidator(min_risk_reward=1.0)
        # risk = 10, reward = 20, R:R = 2.0
        sig = _make_signal(
            action="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
        )
        result = v.validate(sig)
        assert not any("Risk/Reward" in e for e in result.errors)

    def test_poor_rr_error(self):
        mod = _load_modules()
        v = mod.SignalValidator(min_risk_reward=1.0)
        # risk = 10, reward = 5, R:R = 0.5 < 1.0
        sig = _make_signal(
            action="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=105.0,
        )
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("Risk/Reward" in e for e in result.errors)

    def test_low_rr_warning(self):
        mod = _load_modules()
        v = mod.SignalValidator(min_risk_reward=1.0)
        # risk = 10, reward = 12, R:R = 1.2 → warning (< 1.5)
        sig = _make_signal(
            action="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=112.0,
        )
        result = v.validate(sig)
        assert result.is_valid is True  # não bloqueia
        assert any("Risk/Reward" in w or "ratio" in w.lower() for w in result.warnings)

    def test_hold_no_rr_check(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(action="HOLD")
        result = v.validate(sig)
        assert not any("Risk/Reward" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestCheckTotalRisk
# ---------------------------------------------------------------------------

class TestCheckTotalRisk:
    def test_acceptable_risk(self):
        mod = _load_modules()
        v = mod.SignalValidator(max_total_risk_pct=0.20)
        # 5% × 2× = 10% < 20%
        sig = _make_signal(size_pct=0.05, leverage=2)
        result = v.validate(sig)
        assert not any("Total risk" in e for e in result.errors)

    def test_excessive_risk_error(self):
        mod = _load_modules()
        v = mod.SignalValidator(max_total_risk_pct=0.20)
        # 10% × 5× = 50% > 20%
        sig = _make_signal(size_pct=0.10, leverage=5)
        result = v.validate(sig)
        assert result.is_valid is False
        assert any("Total risk" in e for e in result.errors)

    def test_approaching_limit_warning(self):
        mod = _load_modules()
        v = mod.SignalValidator(max_total_risk_pct=0.20)
        # 6% × 3× = 18% > 75% do limite (15%) → warning; 18% < 20% → sem erro
        sig = _make_signal(size_pct=0.06, leverage=3)
        result = v.validate(sig)
        assert result.is_valid is True
        assert any("risk" in w.lower() for w in result.warnings)

    def test_hold_no_risk_check(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(action="HOLD", size_pct=0.99, leverage=100)
        result = v.validate(sig)
        assert not any("Total risk" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestCheckReasoning
# ---------------------------------------------------------------------------

class TestCheckReasoning:
    def test_good_reasoning_no_warning(self):
        mod = _load_modules()
        v = mod.SignalValidator(require_reasoning=True, min_reasoning_chars=10)
        sig = _make_signal(reasoning="Bullish divergence on RSI with volume spike.")
        result = v.validate(sig)
        assert not any("reasoning" in w.lower() for w in result.warnings)

    def test_empty_reasoning_warning(self):
        mod = _load_modules()
        v = mod.SignalValidator(require_reasoning=True)
        sig = _make_signal(reasoning="")
        result = v.validate(sig)
        assert any("reasoning" in w.lower() for w in result.warnings)

    def test_short_reasoning_warning(self):
        mod = _load_modules()
        v = mod.SignalValidator(require_reasoning=True, min_reasoning_chars=10)
        sig = _make_signal(reasoning="ok")  # 2 chars < 10
        result = v.validate(sig)
        assert any("reasoning" in w.lower() for w in result.warnings)

    def test_no_reasoning_required_ok(self):
        mod = _load_modules()
        v = mod.SignalValidator(require_reasoning=False)
        sig = _make_signal(reasoning="")
        result = v.validate(sig)
        assert not any("reasoning" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# TestValidateFullSignal
# ---------------------------------------------------------------------------

class TestValidateFullSignal:
    def test_perfect_long_signal_passes(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(
            symbol="BTC",
            action="LONG",
            confidence=0.75,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            size_pct=0.05,
            leverage=2,
            reasoning="Strong bullish momentum confirmed by RSI and volume data.",
        )
        result = v.validate(sig)
        assert result.is_valid is True
        assert result.errors == []

    def test_perfect_short_signal_passes(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(
            symbol="ETH",
            action="SHORT",
            confidence=0.70,
            entry_price=3000.0,
            stop_loss=3200.0,
            take_profit=2700.0,
            size_pct=0.05,
            leverage=2,
            reasoning="Bearish divergence on MACD with declining volume.",
        )
        result = v.validate(sig)
        assert result.is_valid is True
        assert result.errors == []

    def test_hold_signal_always_passes(self):
        mod = _load_modules()
        v = mod.SignalValidator()
        sig = _make_signal(action="HOLD", confidence=0.01, reasoning="")
        result = v.validate(sig)
        # HOLD não tem restrições de confidence, geometry, R:R, risk
        assert len(result.errors) == 0

    def test_multiple_errors_accumulated(self):
        """Validator acumula todos os erros antes de retornar."""
        mod = _load_modules()
        v = mod.SignalValidator(min_confidence_long=0.55, min_risk_reward=1.0)
        sig = _make_signal(
            action="LONG",
            confidence=0.30,       # erro: confidence baixa
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=102.0,     # R:R = 0.2 — erro
            size_pct=0.20,
            leverage=5,            # total risk = 100% — erro
        )
        result = v.validate(sig)
        assert result.is_valid is False
        assert len(result.errors) >= 2  # múltiplos erros

    def test_fail_silent_on_broken_signal(self):
        """validate() nunca levanta exceção mesmo com input completamente inválido."""
        mod = _load_modules()
        v = mod.SignalValidator()
        broken = MagicMock()
        broken.symbol = None  # vai quebrar .strip()
        broken.action = object()
        broken.confidence = "not_a_number"
        broken.entry_price = None
        broken.stop_loss = None
        broken.take_profit = None
        broken.size_pct = None
        broken.leverage = None
        broken.reasoning = None
        # Não deve levantar exceção
        result = v.validate(broken)
        assert result is not None
        assert isinstance(result.is_valid, bool)


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_signal_validator_returns_instance(self):
        mod = _load_modules()
        mod.reset_signal_validator()
        v = mod.get_signal_validator()
        assert isinstance(v, mod.SignalValidator)

    def test_singleton_same_instance(self):
        mod = _load_modules()
        mod.reset_signal_validator()
        v1 = mod.get_signal_validator()
        v2 = mod.get_signal_validator()
        assert v1 is v2

    def test_kwargs_creates_new_instance(self):
        mod = _load_modules()
        mod.reset_signal_validator()
        v1 = mod.get_signal_validator()
        v2 = mod.get_signal_validator(min_confidence_long=0.99)
        assert v1 is not v2

    def test_reset_clears_singleton(self):
        mod = _load_modules()
        v1 = mod.get_signal_validator()
        mod.reset_signal_validator()
        v2 = mod.get_signal_validator()
        # Após reset, deve criar nova instância
        assert v1 is not v2

"""
src/services/signal_validator.py
==================================
Story 158 — SignalValidator: Linter-on-Edit Pré-Batman.

Inspirado no mecanismo de linting do SWE-agent (SWE-agent/SWE-agent):

  "Edits are validated by a built-in linter, with syntactically invalid
   changes automatically rejected. The integrated linter detects and prevents
   syntax errors at edit time, forcing the agent to issue corrective actions
   and thereby reducing compounding mistakes from a single faulty edit."

  "At each step, malformed generations trigger an error response that prompts
   the model to try again until a valid generation is received."

Adaptação para Mekka Trading:
  O TradingSignal já tem validação Pydantic (Story 028), MAS:
  - Pydantic valida em construction time — erros aparecem tarde no pipeline
  - Batman tem gates que dependem de signal correto para funcionar bem
  - Um signal malformado pode passar pelo Pydantic e ainda ser "válido" porém incoerente

  O SignalValidator adiciona uma camada de validação semântica ANTES do Batman:
  1. Campos de geometria (SL/TP/entry coherência estrita)
  2. Confidence mínima por tipo de ação
  3. Risk/reward ratio mínimo aceitável
  4. Size_pct proporcional à leverage (risco total)
  5. Symbol não-vazio e uppercase
  6. Reasoning não-vazio (signal precisa de justificativa)

  Se ValidationResult.is_valid is False:
    → NickFury emite CycleEvent SIGNAL_INVALID
    → Pula para próximo símbolo SEM chamar Batman
    → Batman não desperdiça gates em signal incoerente

Design (não-intrusivo):
  - SignalValidator é ADITIVO — não modifica Batman nem Vision
  - Retorna ValidationResult com is_valid + errors + warnings
  - Erros bloqueiam (is_valid=False); warnings são informativos
  - Fail-silent: se validator explode internamente → retorna is_valid=True
    (seguro para não interromper trading em caso de bug no validator)

Uso:
    from src.services.signal_validator import SignalValidator

    validator = SignalValidator()
    result = validator.validate(signal)

    if not result.is_valid:
        # log + skip
        return CycleReport(symbol=signal.symbol, error=result.error_summary)

    # Prosseguir para Batman normalmente
    approval = await batman.analyze(...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger

if TYPE_CHECKING:
    from src.models.signal import TradingSignal


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """
    Resultado da validação de um TradingSignal.

    - `is_valid`: False bloqueia o pipeline; True permite continuar
    - `errors`: lista de erros que causaram is_valid=False
    - `warnings`: problemas não-bloqueantes (logged apenas)
    - `symbol`: símbolo do signal validado (para logging)
    """
    is_valid: bool
    symbol: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def error_summary(self) -> str:
        """String resumida dos erros para CycleReport.error."""
        if not self.errors:
            return ""
        return f"SIGNAL_INVALID({self.symbol}): " + "; ".join(self.errors)

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "symbol": self.symbol,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# SignalValidator
# ---------------------------------------------------------------------------

class SignalValidator:
    """
    Valida semanticamente um TradingSignal antes do Batman.

    Cada check_ method:
    - Retorna True se OK, False se bloqueante
    - Adiciona mensagem a errors (bloqueante) ou warnings (não-bloqueante)
    - É fail-silent (try/except interno)

    Thresholds configuráveis via construtor para facilitar testes.
    """

    def __init__(
        self,
        min_confidence_long: float = 0.55,
        min_confidence_short: float = 0.60,
        min_confidence_hold: float = 0.0,   # HOLD sempre passa
        min_risk_reward: float = 1.0,        # R:R mínimo aceitável
        max_total_risk_pct: float = 0.20,    # size_pct * leverage <= 20%
        require_reasoning: bool = True,
        min_reasoning_chars: int = 10,
    ) -> None:
        self._min_conf_long = min_confidence_long
        self._min_conf_short = min_confidence_short
        self._min_conf_hold = min_confidence_hold
        self._min_rr = min_risk_reward
        self._max_total_risk = max_total_risk_pct
        self._require_reasoning = require_reasoning
        self._min_reasoning_chars = min_reasoning_chars

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def validate(self, signal: "TradingSignal") -> ValidationResult:
        """
        Valida um TradingSignal e retorna ValidationResult.

        Fail-silent: se o validator crashar internamente, retorna is_valid=True
        para não interromper o trading cycle.

        Checks executados (em ordem):
          1. Symbol não-vazio e uppercase
          2. Confidence mínima por tipo de ação
          3. Geometria SL/TP/entry (LONG e SHORT)
          4. Risk/reward ratio mínimo
          5. Total risk (size_pct × leverage)
          6. Reasoning presente (se require_reasoning=True)
        """
        try:
            errors: list[str] = []
            warnings: list[str] = []

            # Executar todos os checks
            self._check_symbol(signal, errors, warnings)
            self._check_confidence(signal, errors, warnings)
            self._check_geometry(signal, errors, warnings)
            self._check_risk_reward(signal, errors, warnings)
            self._check_total_risk(signal, errors, warnings)
            self._check_reasoning(signal, errors, warnings)

            is_valid = len(errors) == 0

            result = ValidationResult(
                is_valid=is_valid,
                symbol=getattr(signal, "symbol", ""),
                errors=errors,
                warnings=warnings,
            )

            # Log warnings even when valid
            if result.has_warnings and is_valid:
                for w in warnings:
                    logger.debug(
                        f"[SignalValidator] WARNING {result.symbol}: {w}"
                    )

            if not is_valid:
                logger.warning(
                    f"[SignalValidator] INVALID signal for {result.symbol}: "
                    + "; ".join(errors)
                )

            return result

        except Exception as exc:  # noqa: BLE001
            # Fail-silent: validator bug não bloqueia trading
            logger.error(f"[SignalValidator] Internal error: {exc}")
            return ValidationResult(is_valid=True, symbol=getattr(signal, "symbol", ""))

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_symbol(
        self,
        signal: "TradingSignal",
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """Symbol deve existir e não ser vazio."""
        try:
            sym = getattr(signal, "symbol", "")
            if not sym or not sym.strip():
                errors.append("symbol is empty")
                return
            if sym != sym.upper():
                warnings.append(
                    f"symbol '{sym}' is not uppercase — expected '{sym.upper()}'"
                )
        except Exception:  # noqa: BLE001
            pass

    def _check_confidence(
        self,
        signal: "TradingSignal",
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """
        Confidence mínima por tipo de ação.

        SWE-agent equivalente: parse error → model must retry.
        Aqui: confidence insuficiente → signal rejeitado pre-Batman.
        """
        try:
            from src.models.signal import TradeAction  # lazy import

            action = getattr(signal, "action", None)
            confidence = getattr(signal, "confidence", 0.0)

            if action == TradeAction.LONG and confidence < self._min_conf_long:
                errors.append(
                    f"LONG confidence {confidence:.2f} < minimum {self._min_conf_long:.2f}"
                )
            elif action == TradeAction.SHORT and confidence < self._min_conf_short:
                errors.append(
                    f"SHORT confidence {confidence:.2f} < minimum {self._min_conf_short:.2f}"
                )
            # HOLD: sem restrição de confidence
        except Exception:  # noqa: BLE001
            pass

    def _check_geometry(
        self,
        signal: "TradingSignal",
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """
        Valida geometria SL/TP/entry estritamente.

        O Pydantic model_validator já verifica isso, mas pode ter sido
        criado com mode='before' e contornar a validação.
        Esta é uma segunda camada de defesa (defense-in-depth).

        LONG:  stop_loss < entry_price < take_profit
        SHORT: take_profit < entry_price < stop_loss
        """
        try:
            from src.models.signal import TradeAction

            action = getattr(signal, "action", None)
            entry = getattr(signal, "entry_price", 0.0)
            sl = getattr(signal, "stop_loss", 0.0)
            tp = getattr(signal, "take_profit", 0.0)

            if action == TradeAction.HOLD:
                return  # HOLD: sem restrição geométrica

            if entry <= 0:
                errors.append(f"entry_price must be > 0 (got {entry})")
                return

            if action == TradeAction.LONG:
                if sl >= entry:
                    errors.append(
                        f"LONG: stop_loss ({sl}) must be < entry ({entry})"
                    )
                if tp <= entry:
                    errors.append(
                        f"LONG: take_profit ({tp}) must be > entry ({entry})"
                    )

            elif action == TradeAction.SHORT:
                if sl <= entry:
                    errors.append(
                        f"SHORT: stop_loss ({sl}) must be > entry ({entry})"
                    )
                if tp >= entry:
                    errors.append(
                        f"SHORT: take_profit ({tp}) must be < entry ({entry})"
                    )

        except Exception:  # noqa: BLE001
            pass

    def _check_risk_reward(
        self,
        signal: "TradingSignal",
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """
        Risk/Reward ratio deve ser >= min_risk_reward.

        R:R = |take_profit - entry| / |entry - stop_loss|
        R:R < 1.0 significa que o potencial de ganho é menor que o risco.
        """
        try:
            from src.models.signal import TradeAction

            action = getattr(signal, "action", None)
            if action == TradeAction.HOLD:
                return

            entry = getattr(signal, "entry_price", 0.0)
            sl = getattr(signal, "stop_loss", 0.0)
            tp = getattr(signal, "take_profit", 0.0)

            risk = abs(entry - sl)
            reward = abs(tp - entry)

            if risk <= 0:
                return  # já validado por _check_geometry

            rr = reward / risk
            if rr < self._min_rr:
                errors.append(
                    f"Risk/Reward ratio {rr:.2f} < minimum {self._min_rr:.2f} "
                    f"(reward={reward:.2f}, risk={risk:.2f})"
                )
            elif rr < 1.5:
                warnings.append(
                    f"Low Risk/Reward ratio {rr:.2f} — consider wider TP"
                )

        except Exception:  # noqa: BLE001
            pass

    def _check_total_risk(
        self,
        signal: "TradingSignal",
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """
        Risco total = size_pct × leverage.

        Se size_pct=0.05 e leverage=5, o risco total efetivo é 25% do equity.
        Limite configurável via max_total_risk_pct (default 20%).
        """
        try:
            from src.models.signal import TradeAction

            action = getattr(signal, "action", None)
            if action == TradeAction.HOLD:
                return

            size_pct = getattr(signal, "size_pct", 0.0)
            leverage = getattr(signal, "leverage", 1)
            total_risk = size_pct * leverage

            if total_risk > self._max_total_risk:
                errors.append(
                    f"Total risk {total_risk*100:.1f}% (size={size_pct*100:.1f}% × "
                    f"lev={leverage}×) exceeds maximum {self._max_total_risk*100:.0f}%"
                )
            elif total_risk > self._max_total_risk * 0.75:
                warnings.append(
                    f"High total risk {total_risk*100:.1f}% — approaching limit"
                )

        except Exception:  # noqa: BLE001
            pass

    def _check_reasoning(
        self,
        signal: "TradingSignal",
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """
        Reasoning deve estar presente e ter conteúdo mínimo.

        SWE-agent equivalente: 'thought' component is mandatory in TAO loop.
        Um signal sem reasoning é suspeito — Vision pode estar hallucinating.
        """
        try:
            if not self._require_reasoning:
                return

            reasoning = getattr(signal, "reasoning", "")
            if not reasoning or not reasoning.strip():
                warnings.append(
                    "reasoning is empty — signal has no LLM justification"
                )
            elif len(reasoning.strip()) < self._min_reasoning_chars:
                warnings.append(
                    f"reasoning too short ({len(reasoning.strip())} chars) "
                    f"— minimum {self._min_reasoning_chars}"
                )
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Singleton (configuração default)
# ---------------------------------------------------------------------------

_default_validator: Optional["SignalValidator"] = None


def get_signal_validator(**kwargs: Any) -> SignalValidator:
    """
    Retorna o SignalValidator singleton com configuração default.

    Passe kwargs para sobrescrever thresholds (ex: em testes).
    Se kwargs for passado, sempre cria nova instância.
    """
    global _default_validator
    if kwargs or _default_validator is None:
        _default_validator = SignalValidator(**kwargs)
    return _default_validator


def reset_signal_validator() -> None:
    """Reseta singleton — usado em testes."""
    global _default_validator
    _default_validator = None

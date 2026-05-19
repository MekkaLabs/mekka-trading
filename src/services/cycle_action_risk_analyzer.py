"""
src/services/cycle_action_risk_analyzer.py
===========================================
Story 201 — CycleActionRiskAnalyzer: classificação de risco de ações
antes da execução, inspirado no SecurityAnalyzer do OpenHands.

Inspirado no padrão OpenHands SecurityAnalyzer / LLM Risk Analyzer
(All-Hands-AI/OpenHands, Issue #10462, CLI --llm-approve flag):
  "SecurityAnalyzer predicts security_risk for every agent action:
   Low / Medium / High. Each action passes through the analyzer before
   execution. High-risk actions can be blocked or require confirmation.
   The LLM-based analyzer uses a prompt to evaluate the action's intent
   and potential side effects."

No OpenHands:
  SecurityAnalyzer recebe uma Action e retorna um SecurityRisk (LOW/MEDIUM/HIGH).
  Ações de HIGH risk podem ser bloqueadas ou pausadas para confirmação humana.
  O analyzer LLM-based usa um system prompt especializado para avaliar
  intenção e efeitos colaterais de cada ação (execução de código, I/O, etc.)

No Mekka, o equivalente é:
  CycleActionRiskAnalyzer avalia o risco de cada ação do pipeline antes
  da execução. Clasifica em LOW/MEDIUM/HIGH com base em regras heurísticas
  (sem LLM call — sincrônico e instantâneo). O risk score é usado em
  NickFury para decidir se passa direto, loga um aviso ou bloqueia.

  Ações avaliadas:
    OPEN_LONG / OPEN_SHORT — risco depende de notional, leverage, regime
    CLOSE_POSITION         — LOW (reduz exposição)
    HOLD                   — LOW (sem movimento)
    MARKET_ORDER           — MEDIUM (slippage imprevisível)
    LIMIT_ORDER            — LOW (preço controlado)
    SCALE_IN               — HIGH se posição já existente
    FORCE_LIQUIDATE        — HIGH sempre

Arquitetura
-----------
  ActionRiskLevel       — enum LOW / MEDIUM / HIGH
  RiskAssessment        — resultado da análise com justificativa
  CycleActionRiskAnalyzer
    ├── analyze(action_type, symbol, notional, leverage, regime, **ctx) → RiskAssessment
    ├── is_safe(assessment, threshold) → bool
    ├── get_recent(symbol, limit) → List[RiskAssessment]
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# ActionRiskLevel
# ---------------------------------------------------------------------------

class ActionRiskLevel(str, Enum):
    """
    Nível de risco de uma ação de trading.

    Mapeamento com OpenHands SecurityRisk:
      LOW    ←→ SecurityRisk.LOW    (ação segura, executa diretamente)
      MEDIUM ←→ SecurityRisk.MEDIUM (loga aviso, monitora de perto)
      HIGH   ←→ SecurityRisk.HIGH   (bloqueia ou requer confirmação)
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def numeric(self) -> int:
        return {"LOW": 1, "MEDIUM": 2, "HIGH": 3}[self.value]


# ---------------------------------------------------------------------------
# RiskAssessment
# ---------------------------------------------------------------------------

@dataclass
class RiskAssessment:
    """
    Resultado da análise de risco de uma ação.

    Equivalente ao output do SecurityAnalyzer do OpenHands:
    risk level + justificativa + contexto da ação avaliada.
    """
    symbol: str
    action_type: str
    risk_level: ActionRiskLevel
    reason: str
    notional: float = 0.0
    leverage: float = 1.0
    regime: str = "UNKNOWN"
    timestamp: float = field(default_factory=time.monotonic)
    blocked: bool = False  # True se a ação foi bloqueada pelo analyzer

    def to_log_line(self) -> str:
        blocked_tag = " [BLOCKED]" if self.blocked else ""
        return (
            f"RISK:{self.risk_level.value}{blocked_tag} | {self.symbol} | "
            f"action={self.action_type} | notional=${self.notional:.0f} | "
            f"leverage={self.leverage}x | {self.reason}"
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action_type": self.action_type,
            "risk_level": self.risk_level.value,
            "reason": self.reason,
            "notional": self.notional,
            "leverage": self.leverage,
            "regime": self.regime,
            "blocked": self.blocked,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# CycleActionRiskAnalyzer
# ---------------------------------------------------------------------------

# Mapeamento base de risco por tipo de ação
_BASE_RISK: Dict[str, ActionRiskLevel] = {
    "HOLD": ActionRiskLevel.LOW,
    "CLOSE_POSITION": ActionRiskLevel.LOW,
    "LIMIT_ORDER": ActionRiskLevel.LOW,
    "REDUCE_POSITION": ActionRiskLevel.LOW,
    "OPEN_LONG": ActionRiskLevel.MEDIUM,
    "OPEN_SHORT": ActionRiskLevel.MEDIUM,
    "MARKET_ORDER": ActionRiskLevel.MEDIUM,
    "SCALE_IN": ActionRiskLevel.HIGH,
    "FORCE_LIQUIDATE": ActionRiskLevel.HIGH,
    "REVERSE_POSITION": ActionRiskLevel.HIGH,
}


class CycleActionRiskAnalyzer:
    """
    Classifica o risco de ações do pipeline antes da execução.

    Padrão OpenHands SecurityAnalyzer:
    - Avalia cada ação com base em heurísticas (notional, leverage, regime)
    - Retorna RiskAssessment com nível LOW/MEDIUM/HIGH + razão
    - HIGH risk → pode bloquear a ação (configurable block_on_high)
    - Fail-silent: erros no analyzer não travam o pipeline

    Uso:
        analyzer = get_cycle_action_risk_analyzer()
        assessment = analyzer.analyze(
            action_type="OPEN_LONG",
            symbol="BTC",
            notional=5000.0,
            leverage=3.0,
            regime="VOLATILE",
        )
        if not analyzer.is_safe(assessment):
            return "HOLD"  # bloqueia a ação
    """

    def __init__(
        self,
        block_on_high: bool = True,
        high_notional_threshold: float = 10_000.0,
        high_leverage_threshold: float = 5.0,
        max_assessments: int = 200,
    ) -> None:
        self.block_on_high = block_on_high
        self.high_notional_threshold = high_notional_threshold
        self.high_leverage_threshold = high_leverage_threshold
        self.max_assessments = max_assessments

        self._assessments: List[RiskAssessment] = []
        self._total_analyzed: int = 0
        self._total_blocked: int = 0
        self._by_level: Dict[str, int] = {}

    def analyze(
        self,
        action_type: str,
        symbol: str,
        notional: float = 0.0,
        leverage: float = 1.0,
        regime: str = "UNKNOWN",
        **context: Any,
    ) -> RiskAssessment:
        """
        Analisa o risco de uma ação.

        Args:
            action_type: Tipo da ação (OPEN_LONG, HOLD, etc.)
            symbol:      Símbolo do ativo
            notional:    Valor nocional em USD
            leverage:    Alavancagem aplicada
            regime:      Regime de mercado atual
            **context:   Contexto adicional (confidence, position_size, etc.)

        Returns:
            RiskAssessment com nível de risco e justificativa.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        action = action_type.upper()

        # Risco base pelo tipo de ação
        base_risk = _BASE_RISK.get(action, ActionRiskLevel.MEDIUM)
        reasons: List[str] = [f"action={action} (base={base_risk.value})"]
        risk_level = base_risk

        # Escalada por notional alto
        if notional > self.high_notional_threshold and risk_level != ActionRiskLevel.HIGH:
            risk_level = ActionRiskLevel.HIGH
            reasons.append(f"notional ${notional:.0f} > ${self.high_notional_threshold:.0f}")

        # Escalada por alavancagem alta
        if leverage > self.high_leverage_threshold and risk_level != ActionRiskLevel.HIGH:
            risk_level = ActionRiskLevel.HIGH
            reasons.append(f"leverage {leverage}x > {self.high_leverage_threshold}x")

        # Escalada por regime VOLATILE/CRASH
        if regime.upper() in ("VOLATILE", "CRASH", "PANIC") and risk_level == ActionRiskLevel.MEDIUM:
            risk_level = ActionRiskLevel.HIGH
            reasons.append(f"regime={regime} (high-risk regime)")

        # Confiança baixa escala risco
        confidence = float(context.get("confidence", 1.0))
        if confidence < 0.5 and risk_level == ActionRiskLevel.LOW:
            risk_level = ActionRiskLevel.MEDIUM
            reasons.append(f"confidence={confidence:.2f} < 0.5")

        blocked = self.block_on_high and risk_level == ActionRiskLevel.HIGH

        assessment = RiskAssessment(
            symbol=sym,
            action_type=action,
            risk_level=risk_level,
            reason="; ".join(reasons),
            notional=notional,
            leverage=leverage,
            regime=regime,
            blocked=blocked,
        )

        self._assessments.append(assessment)
        if len(self._assessments) > self.max_assessments:
            self._assessments = self._assessments[-self.max_assessments:]

        self._total_analyzed += 1
        self._by_level[risk_level.value] = self._by_level.get(risk_level.value, 0) + 1
        if blocked:
            self._total_blocked += 1

        log_level = "warning" if risk_level == ActionRiskLevel.HIGH else "debug"
        getattr(logger, log_level)(f"[RiskAnalyzer] {assessment.to_log_line()}")
        return assessment

    def is_safe(
        self,
        assessment: RiskAssessment,
        threshold: ActionRiskLevel = ActionRiskLevel.HIGH,
    ) -> bool:
        """
        Retorna True se o assessment é seguro para execução.

        Args:
            assessment: RiskAssessment retornado por analyze()
            threshold:  Nível máximo aceitável (default: bloqueia HIGH)

        Returns:
            True se risk_level < threshold (em ordem LOW < MEDIUM < HIGH).
        """
        return assessment.risk_level.numeric < threshold.numeric

    def get_recent(self, symbol: Optional[str] = None, limit: int = 20) -> List[RiskAssessment]:
        """Retorna assessments recentes, opcionalmente filtrados por símbolo."""
        assessments = self._assessments
        if symbol:
            sym = symbol.upper()
            assessments = [a for a in assessments if a.symbol == sym]
        return assessments[-limit:]

    def summary(self) -> dict:
        return {
            "total_analyzed": self._total_analyzed,
            "total_blocked": self._total_blocked,
            "by_level": self._by_level,
            "block_on_high": self.block_on_high,
            "high_notional_threshold": self.high_notional_threshold,
            "high_leverage_threshold": self.high_leverage_threshold,
            "assessments_stored": len(self._assessments),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_analyzer: Optional[CycleActionRiskAnalyzer] = None


def get_cycle_action_risk_analyzer() -> CycleActionRiskAnalyzer:
    """Retorna o singleton global do CycleActionRiskAnalyzer."""
    global _analyzer
    if _analyzer is None:
        try:
            from src.config.settings import settings
            block_on_high = bool(getattr(settings, "risk_analyzer_block_on_high", True))
            high_notional = float(getattr(settings, "risk_analyzer_high_notional", 10_000.0))
            high_leverage = float(getattr(settings, "risk_analyzer_high_leverage", 5.0))
        except Exception:  # noqa: BLE001
            block_on_high = True
            high_notional = 10_000.0
            high_leverage = 5.0
        _analyzer = CycleActionRiskAnalyzer(
            block_on_high=block_on_high,
            high_notional_threshold=high_notional,
            high_leverage_threshold=high_leverage,
        )
    return _analyzer


def reset_cycle_action_risk_analyzer() -> None:
    """Reseta o singleton — para testes."""
    global _analyzer
    _analyzer = None

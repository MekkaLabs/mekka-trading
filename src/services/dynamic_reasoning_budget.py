"""
src/services/dynamic_reasoning_budget.py
==========================================
Story 181 — DynamicReasoningBudget: ajuste dinâmico de max_tokens Vision.

Inspirado no padrão Aider --thinking-tokens / --reasoning-effort:
  "Added /think-tokens command to set thinking token budget with support
   for human-readable formats and /reasoning-effort command to control
   model reasoning level."

No Aider, o usuário pode definir o orçamento de raciocínio antes de cada
instrução. No Mekka, o orçamento é ajustado automaticamente com base no
regime de mercado detectado pelo MarketRegimeDetector (Story 146):

  VOLATILE → max_tokens = 4096  (ciclo perigoso, raciocínio máximo)
  BULL     → max_tokens = 2048  (tendência clara, raciocínio moderado)
  BEAR     → max_tokens = 2048  (tendência clara, raciocínio moderado)
  SIDEWAYS → max_tokens = 1024  (mercado incerto, raciocínio mínimo)

Isso reduz o custo LLM em ~50% em regimes SIDEWAYS sem sacrificar
qualidade de sinal nos ciclos críticos (VOLATILE/BULL/BEAR).

Budget também é ajustado pela importância do símbolo:
  LARGE_CAP (BTC/ETH) → multiplicador 1.5×
  MID_CAP             → multiplicador 1.0×
  SMALL_CAP           → multiplicador 0.8×

Uso
---
    from src.services.dynamic_reasoning_budget import get_reasoning_budget

    budget = get_reasoning_budget()
    max_tokens = budget.get_max_tokens(regime="VOLATILE", cap_tier="LARGE_CAP")
    # → 4096 * 1.5 = 6144

    # Integração no Vision:
    llm_params = {"max_tokens": max_tokens, ...}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Constantes de budget
# ---------------------------------------------------------------------------

# Base tokens por regime (equivalente ao --thinking-tokens do Aider)
_REGIME_BASE_TOKENS: dict[str, int] = {
    "VOLATILE":    4096,
    "BULL":        2048,
    "STRONG_BULL": 2048,
    "BEAR":        2048,
    "STRONG_BEAR": 2048,
    "SIDEWAYS":    1024,
    "UNKNOWN":     2048,  # default seguro
}

# Multiplicadores por cap tier (equivalente ao reasoning-effort do Aider)
_CAP_TIER_MULTIPLIERS: dict[str, float] = {
    "LARGE_CAP": 1.5,   # BTC/ETH — maior atenção
    "MID_CAP":   1.0,   # SOL/BNB/etc
    "SMALL_CAP": 0.8,   # altcoins — custo reduzido
    "UNKNOWN":   1.0,
}

# Limites absolutos
_MIN_TOKENS = 512
_MAX_TOKENS = 8192


# ---------------------------------------------------------------------------
# BudgetDecision
# ---------------------------------------------------------------------------

@dataclass
class BudgetDecision:
    """
    Resultado de uma decisão de orçamento de tokens.
    """
    regime: str
    cap_tier: str
    base_tokens: int
    multiplier: float
    final_tokens: int
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "cap_tier": self.cap_tier,
            "base_tokens": self.base_tokens,
            "multiplier": self.multiplier,
            "final_tokens": self.final_tokens,
            "reasoning": self.reasoning,
        }


# ---------------------------------------------------------------------------
# DynamicReasoningBudget
# ---------------------------------------------------------------------------

class DynamicReasoningBudget:
    """
    Ajusta o orçamento de tokens do Vision dinamicamente com base no
    regime de mercado e cap tier do símbolo.

    Padrão Aider --thinking-tokens: adapta profundidade de raciocínio
    ao contexto atual ao invés de usar um valor fixo.
    """

    def __init__(
        self,
        regime_tokens: dict[str, int] | None = None,
        cap_multipliers: dict[str, float] | None = None,
        min_tokens: int = _MIN_TOKENS,
        max_tokens: int = _MAX_TOKENS,
        default_regime: str = "UNKNOWN",
        default_cap_tier: str = "MID_CAP",
    ) -> None:
        self._regime_tokens = regime_tokens or dict(_REGIME_BASE_TOKENS)
        self._cap_multipliers = cap_multipliers or dict(_CAP_TIER_MULTIPLIERS)
        self._min_tokens = min_tokens
        self._max_tokens = max_tokens
        self._default_regime = default_regime
        self._default_cap_tier = default_cap_tier

    def get_max_tokens(
        self,
        regime: str = "",
        cap_tier: str = "",
    ) -> int:
        """
        Retorna o max_tokens recomendado para a combinação regime + cap_tier.

        Args:
            regime: string do regime ("VOLATILE", "BULL", "BEAR", "SIDEWAYS", ...)
            cap_tier: string do cap tier ("LARGE_CAP", "MID_CAP", "SMALL_CAP")

        Returns:
            Número de tokens (int), entre min_tokens e max_tokens.
        """
        regime_key = (regime or self._default_regime).upper()
        cap_key = (cap_tier or self._default_cap_tier).upper()

        base = self._regime_tokens.get(regime_key, self._regime_tokens[self._default_regime])
        mult = self._cap_multipliers.get(cap_key, self._cap_multipliers[self._default_cap_tier])

        raw = int(base * mult)
        final = max(self._min_tokens, min(self._max_tokens, raw))
        return final

    def decide(
        self,
        regime: str = "",
        cap_tier: str = "",
    ) -> BudgetDecision:
        """
        Retorna uma BudgetDecision completa com raciocínio para logs/auditoria.
        """
        regime_key = (regime or self._default_regime).upper()
        cap_key = (cap_tier or self._default_cap_tier).upper()

        base = self._regime_tokens.get(regime_key, self._regime_tokens[self._default_regime])
        mult = self._cap_multipliers.get(cap_key, self._cap_multipliers[self._default_cap_tier])

        raw = int(base * mult)
        final = max(self._min_tokens, min(self._max_tokens, raw))

        reasoning = (
            f"regime={regime_key}({base} base) × cap_tier={cap_key}({mult}×) "
            f"= {raw} → clamped to {final}"
        )

        return BudgetDecision(
            regime=regime_key,
            cap_tier=cap_key,
            base_tokens=base,
            multiplier=mult,
            final_tokens=final,
            reasoning=reasoning,
        )

    def get_reasoning_effort(self, regime: str = "", cap_tier: str = "") -> str:
        """
        Retorna uma string de esforço compatível com APIs que usam
        reasoning_effort ao invés de max_tokens (e.g. OpenAI o-series).

        VOLATILE/LARGE_CAP → "high"
        BULL/BEAR           → "medium"
        SIDEWAYS/SMALL_CAP  → "low"
        """
        tokens = self.get_max_tokens(regime=regime, cap_tier=cap_tier)
        if tokens >= 3000:
            return "high"
        elif tokens >= 1500:
            return "medium"
        else:
            return "low"

    def summary(self) -> dict:
        """Resumo de todos os budgets configurados."""
        return {
            "regime_tokens": self._regime_tokens,
            "cap_multipliers": self._cap_multipliers,
            "min_tokens": self._min_tokens,
            "max_tokens": self._max_tokens,
            "examples": {
                "VOLATILE/LARGE_CAP": self.get_max_tokens("VOLATILE", "LARGE_CAP"),
                "VOLATILE/MID_CAP":   self.get_max_tokens("VOLATILE", "MID_CAP"),
                "BULL/LARGE_CAP":     self.get_max_tokens("BULL", "LARGE_CAP"),
                "SIDEWAYS/SMALL_CAP": self.get_max_tokens("SIDEWAYS", "SMALL_CAP"),
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_budget: Optional[DynamicReasoningBudget] = None


def get_reasoning_budget() -> DynamicReasoningBudget:
    """Retorna o singleton global do DynamicReasoningBudget."""
    global _budget
    if _budget is None:
        try:
            from src.config.settings import settings
            max_t = int(getattr(settings, "vision_max_tokens", _MAX_TOKENS))
            min_t = int(getattr(settings, "vision_min_tokens", _MIN_TOKENS))
        except Exception:  # noqa: BLE001
            max_t = _MAX_TOKENS
            min_t = _MIN_TOKENS
        _budget = DynamicReasoningBudget(
            min_tokens=min_t,
            max_tokens=max_t,
        )
    return _budget


def reset_reasoning_budget() -> None:
    """Reseta o singleton — para testes."""
    global _budget
    _budget = None

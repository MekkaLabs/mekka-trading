"""
src/strategies/
================
Be Water Framework — pool adaptativo de estratégias.

Cada estratégia é uma "forma de luta" (jiu-jitsu inspired). O sistema
sente o regime do mercado via ``RegimeDetector``, escolhe estratégias
compatíveis via ``StrategySelector``, e aloca capital via
``CapitalAllocator`` baseado em performance histórica por
(strategy × regime).

Princípios:
- Não força entrada: se nenhum regime claro → FLAT
- Múltiplas ativas: 2 regimes coexistindo → 2 estratégias rodam
- Auto-evolução: estratégia ruim por 30d → aposenta; variante boa → promove
- Aprendizado por regime: cada estratégia tem performance trackeada
  por contexto, não em média global

Inspirado em Bruce Lee: "Be water, my friend."
"""

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyContext,
    StrategySignal,
)

__all__ = [
    "BaseStrategy",
    "RegimeFitness",
    "StrategyContext",
    "StrategySignal",
]

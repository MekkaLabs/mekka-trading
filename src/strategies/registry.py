"""
src/strategies/registry.py
============================
Registry centralizado de todas as estratégias do Be Water Framework.

Responsabilidades:
- Mapear nome → classe BaseStrategy
- Instanciar estratégias de forma idempotente (cache no módulo)
- Importar opcionais com try/except (fail-silent quando o outro agente
  ainda não criou o arquivo)
- Expor metadata declarativa pra dashboard (regime fitness incluído)

Padrões:
- FAIL-SILENT: importação ausente NÃO derruba o módulo, só omite a
  estratégia do registro
- READ-ONLY a partir do dashboard: ``list_available_strategies`` retorna
  uma lista nova a cada chamada (não vaza referência interna)
- DETERMINÍSTICO: ``get_all_strategies`` retorna em ordem fixa
  (declaration order)
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from .base import BaseStrategy, MarketRegime

# ---------------------------------------------------------------------------
# Imports obrigatórios — estratégias core já existentes
# ---------------------------------------------------------------------------

from .scalp import ScalpStrategy
from .swing import SwingStrategy
from .mean_reversion import MeanReversionStrategy
from .momentum_rider import MomentumRiderStrategy

# ---------------------------------------------------------------------------
# Imports opcionais — Be Water Framework expansion
# (Outro agente pode criar/remover estes arquivos sem quebrar o registry.)
# ---------------------------------------------------------------------------

try:
    from .scalp_aggressive import ScalpAggressiveStrategy  # type: ignore[assignment]
except Exception as _exc:  # noqa: BLE001
    ScalpAggressiveStrategy = None  # type: ignore[assignment]
    logger.debug("registry: ScalpAggressiveStrategy unavailable ({})", _exc)

try:
    from .breakout import BreakoutStrategy  # type: ignore[assignment]
except Exception as _exc:  # noqa: BLE001
    BreakoutStrategy = None  # type: ignore[assignment]
    logger.debug("registry: BreakoutStrategy unavailable ({})", _exc)

try:
    from .range_trader import RangeTraderStrategy  # type: ignore[assignment]
except Exception as _exc:  # noqa: BLE001
    RangeTraderStrategy = None  # type: ignore[assignment]
    logger.debug("registry: RangeTraderStrategy unavailable ({})", _exc)

try:
    from .funding_arbitrage import FundingArbitrageStrategy  # type: ignore[assignment]
except Exception as _exc:  # noqa: BLE001
    FundingArbitrageStrategy = None  # type: ignore[assignment]
    logger.debug("registry: FundingArbitrageStrategy unavailable ({})", _exc)


# ---------------------------------------------------------------------------
# Registry — declaration order é a ordem de retorno
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, type[BaseStrategy]] = {
    "Scalp": ScalpStrategy,
    "Swing": SwingStrategy,
    "MeanReversion": MeanReversionStrategy,
    "MomentumRider": MomentumRiderStrategy,
}

# Estratégias opcionais — só registra se a importação funcionou
_OPTIONAL: list[tuple[str, Optional[type[BaseStrategy]]]] = [
    ("ScalpAggressive", ScalpAggressiveStrategy),
    ("Breakout", BreakoutStrategy),
    ("RangeTrader", RangeTraderStrategy),
    ("FundingArbitrage", FundingArbitrageStrategy),
]
for _name, _cls in _OPTIONAL:
    if _cls is not None:
        _REGISTRY[_name] = _cls


# Cache de instâncias — evita reinstanciar a cada chamada
_INSTANCES: dict[str, BaseStrategy] = {}


def _instantiate(name: str, cls: type[BaseStrategy]) -> Optional[BaseStrategy]:
    """Instancia uma estratégia uma vez (cached). Fail-silent."""
    if name in _INSTANCES:
        return _INSTANCES[name]
    try:
        inst = cls()
        _INSTANCES[name] = inst
        return inst
    except Exception as exc:  # noqa: BLE001
        logger.warning("registry: failed to instantiate {} ({})", name, exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_all_strategies() -> list[BaseStrategy]:
    """Instancia todas as estratégias registradas.

    Retorna em ordem de declaração (core primeiro, opcionais depois).
    Estratégias que falham na instância são silenciosamente omitidas.
    """
    out: list[BaseStrategy] = []
    for name, cls in _REGISTRY.items():
        inst = _instantiate(name, cls)
        if inst is not None:
            out.append(inst)
    return out


def get_strategy(name: str) -> Optional[BaseStrategy]:
    """Instancia uma estratégia específica por nome. Case-insensitive."""
    key = (name or "").strip()
    # Tenta match exato primeiro, depois case-insensitive
    cls = _REGISTRY.get(key)
    if cls is None:
        lowered = key.lower()
        for k, v in _REGISTRY.items():
            if k.lower() == lowered:
                cls = v
                key = k
                break
    if cls is None:
        return None
    return _instantiate(key, cls)


def list_strategy_names() -> list[str]:
    """Apenas nomes (ordem de declaração)."""
    return list(_REGISTRY.keys())


def list_available_strategies() -> list[dict]:
    """Metadata declarativa pra dashboard.

    Inclui limites de risco + fitness por regime (todos os regimes da enum).
    """
    out: list[dict] = []
    for name, cls in _REGISTRY.items():
        inst = _instantiate(name, cls)
        if inst is None:
            continue
        try:
            fitness = inst.regime_fitness()
            fitness_map = {
                regime.value: round(fitness.score(regime), 3)
                for regime in MarketRegime
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("registry: fitness lookup failed for {} ({})", name, exc)
            fitness_map = {regime.value: 0.0 for regime in MarketRegime}
        out.append({
            "name": inst.name,
            "description": inst.description,
            "max_position_size_pct": float(inst.max_position_size_pct),
            "max_leverage": int(inst.max_leverage),
            "min_confidence_to_trade": float(inst.min_confidence_to_trade),
            "regime_fitness": fitness_map,
        })
    return out


__all__ = [
    "get_all_strategies",
    "get_strategy",
    "list_strategy_names",
    "list_available_strategies",
]

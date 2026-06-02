"""
src/strategies/base.py
========================
Contrato abstrato para todas as "formas de luta" do Be Water Framework.

Cada estratégia implementa:
- ``regime_fitness(regime)``: quão compatível com o regime de mercado atual
- ``generate_signal(context)``: dado análise + capital alocado, sinal trade
- ``risk_params()``: stop loss / take profit / max position size

Princípios:
- READ-ONLY no MarketAnalysis (não muta)
- FAIL-SILENT: exceptions → sinal HOLD com error metadata
- BOUNDED: cada estratégia conhece seus limites de risco
- DECLARATIVE: regime_fitness retorna score 0-1, não decide alocação
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Market Regimes — 7 categorias canônicas
# ---------------------------------------------------------------------------


class MarketRegime(str, Enum):
    """Classificação canônica do regime de mercado.

    RegimeDetector mapeia métricas (ATR, ADX, BB width, etc) para um destes.
    Estratégias declaram regime_fitness pra cada um.
    """
    LOW_VOL_RANGE = "low_vol_range"          # ATR baixo, ADX < 20, BB tight
    LOW_VOL_TRENDING = "low_vol_trending"    # ATR baixo, ADX > 25
    HIGH_VOL_TRENDING_UP = "high_vol_trending_up"      # ATR alto, ADX > 30, MA up
    HIGH_VOL_TRENDING_DOWN = "high_vol_trending_down"  # ATR alto, ADX > 30, MA down
    HIGH_VOL_CHOPPY = "high_vol_choppy"      # ATR alto, ADX < 20 (no trend)
    BREAKOUT = "breakout"                    # Range → expansion súbita (BB squeeze rompido)
    FUNDING_EXTREME = "funding_extreme"      # Funding rate > +0.05% ou < -0.05%
    UNCLEAR = "unclear"                      # Dados insuficientes ou métrica conflitante


# ---------------------------------------------------------------------------
# RegimeFitness — declaração de compatibilidade
# ---------------------------------------------------------------------------


@dataclass
class RegimeFitness:
    """Score 0-1 de quão bem a estratégia funciona em cada regime.

    Estratégia declara seus números preferidos. Selector combina com
    performance histórica empírica pra decidir alocação.

    Exemplo (Scalp):
        RegimeFitness(
            high_vol_choppy=0.95,    # adora vol choppy
            high_vol_trending_up=0.6,
            high_vol_trending_down=0.6,
            breakout=0.4,            # pode perder em ruptura rápida
            low_vol_range=0.1,       # quase morre em low vol
            low_vol_trending=0.2,
            funding_extreme=0.3,
            unclear=0.0,             # nunca opera unclear
        )
    """

    low_vol_range: float = 0.0
    low_vol_trending: float = 0.0
    high_vol_trending_up: float = 0.0
    high_vol_trending_down: float = 0.0
    high_vol_choppy: float = 0.0
    breakout: float = 0.0
    funding_extreme: float = 0.0
    unclear: float = 0.0

    def score(self, regime: MarketRegime) -> float:
        """Retorna fitness 0-1 pra o regime dado. Clamp [0,1]."""
        v = getattr(self, regime.value, 0.0)
        return max(0.0, min(1.0, float(v)))


# ---------------------------------------------------------------------------
# StrategyContext — input para generate_signal
# ---------------------------------------------------------------------------


@dataclass
class StrategyContext:
    """Tudo que uma estratégia precisa pra decidir.

    Encapsula análise + alocação + contexto temporal. Read-only.
    """
    symbol: str
    analysis: Any                # MarketAnalysis — read-only
    regime: MarketRegime
    regime_confidence: float     # 0-1, do RegimeDetector
    allocated_usd: float         # quanto de banca disponível pra esta estratégia
    current_equity_usd: float
    open_positions_count: int = 0
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# StrategySignal — output de generate_signal
# ---------------------------------------------------------------------------


class StrategyAction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"                # não há sinal claro
    FLAT = "FLAT"                # explicitly stay out


@dataclass
class StrategySignal:
    """Output de uma estratégia. Compatível com Vision/Batman/IronMan.

    Quando ``action=HOLD`` ou ``FLAT``, demais campos podem ser ignorados.
    Stop loss e take profit em PREÇO absoluto (não percentual) — Batman
    cuida de converter.

    metadata.strategy_name é OBRIGATÓRIO para tracking.
    """
    strategy_name: str
    symbol: str
    action: StrategyAction
    confidence: float             # 0-1 da própria estratégia
    size_pct: float = 0.0         # fração do allocated_usd a usar (0-1)
    leverage: int = 1
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "action": self.action.value,
            "confidence": self.confidence,
            "size_pct": self.size_pct,
            "leverage": self.leverage,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "rationale": self.rationale,
            "metadata": self.metadata,
            "generated_at": self.generated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# BaseStrategy abstract
# ---------------------------------------------------------------------------


class BaseStrategy(ABC):
    """
    Contrato pra todas as estratégias.

    Subclasses implementam ``regime_fitness`` e ``generate_signal``.
    O resto (logging, error handling) é DRY no base.
    """

    # Subclasses sobrescrevem
    name: str = "BaseStrategy"
    description: str = ""

    # Limites declarativos — Batman valida no commit do trade
    max_position_size_pct: float = 0.02   # 2% do equity por padrão
    max_leverage: int = 3
    min_confidence_to_trade: float = 0.6

    def __init__(self) -> None:
        from loguru import logger
        self._log = logger.bind(strategy=self.name)

    # ---------------- shared schema helpers ----------------
    # Real MarketData usa: atr_14, rsi_14, price, ema_20, bb_mid, trend (enum)
    # Mocks/tests podem usar: atr, rsi, close, ema_21, bb_middle
    # Estes helpers tentam ambos os nomes (fail-silent → None)

    @staticmethod
    def _chart_get(chart: Any, *names: str) -> Any:
        """Tenta múltiplos nomes de atributo/chave. Retorna 1º não-None."""
        for n in names:
            val = None
            if hasattr(chart, n):
                val = getattr(chart, n)
            elif isinstance(chart, dict):
                val = chart.get(n)
            if val is not None:
                return val
        return None

    @classmethod
    def _atr(cls, chart: Any) -> Any:
        return cls._chart_get(chart, "atr", "atr_14")

    @classmethod
    def _rsi(cls, chart: Any) -> Any:
        return cls._chart_get(chart, "rsi", "rsi_14")

    @classmethod
    def _close(cls, chart: Any) -> Any:
        return cls._chart_get(chart, "close", "price")

    @classmethod
    def _ema_short(cls, chart: Any) -> Any:
        """EMA curta — tenta 9, 20, 21."""
        return cls._chart_get(chart, "ema_9", "ema_20", "ema_21")

    @classmethod
    def _ema_mid(cls, chart: Any) -> Any:
        """EMA média — 21, 20, 50."""
        return cls._chart_get(chart, "ema_21", "ema_20", "ema_50")

    @classmethod
    def _ema_long(cls, chart: Any) -> Any:
        return cls._chart_get(chart, "ema_200", "ema_50")

    @classmethod
    def _bb_middle(cls, chart: Any) -> Any:
        return cls._chart_get(chart, "bb_middle", "bb_mid")

    @classmethod
    def _volume_elevated(cls, chart: Any) -> bool:
        """True quando volume está elevated.

        Suporta: volume_elevated (bool), volume_spike (bool),
        volume vs volume_ma (derivado).
        """
        val = cls._chart_get(chart, "volume_elevated", "volume_spike")
        if val is not None:
            return bool(val)
        # Derive: volume > volume_ma
        v = cls._chart_get(chart, "volume")
        v_ma = cls._chart_get(chart, "volume_ma")
        if v is not None and v_ma is not None and v_ma > 0:
            return float(v) > float(v_ma)
        return False

    # ---------------- abstract API ----------------

    @abstractmethod
    def regime_fitness(self) -> RegimeFitness:
        """Declara compatibilidade com cada regime (estática por estratégia).

        Score 0-1 por regime. Selector pondera com performance histórica
        empírica em runtime.
        """

    @abstractmethod
    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        """Gera sinal trade para o contexto atual.

        Sempre retornar StrategySignal (mesmo que HOLD). NUNCA levantar
        exception — capturar e retornar HOLD com metadata["error"].
        """

    # ---------------- shared helpers ----------------

    def fitness_for(self, regime: MarketRegime) -> float:
        """Wrapper safe: regime_fitness().score(regime)."""
        try:
            return self.regime_fitness().score(regime)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[{self.name}] fitness lookup failed: {exc}")
            return 0.0

    def _hold(self, symbol: str, reason: str, **meta: Any) -> StrategySignal:
        """Helper: gera HOLD com rationale."""
        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            action=StrategyAction.HOLD,
            confidence=0.0,
            rationale=reason,
            metadata=meta,
        )

    def _flat(self, symbol: str, reason: str, **meta: Any) -> StrategySignal:
        """Helper: gera FLAT (explicitly stay out)."""
        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            action=StrategyAction.FLAT,
            confidence=0.0,
            rationale=reason,
            metadata=meta,
        )

    def safe_signal(self, context: StrategyContext) -> StrategySignal:
        """
        Public entry: chama generate_signal com try/except + validação.
        Use isto em vez de generate_signal direto.
        """
        try:
            sig = self.generate_signal(context)
            # Sanitize
            if sig.confidence < self.min_confidence_to_trade and sig.action in (
                StrategyAction.LONG, StrategyAction.SHORT,
            ):
                return self._hold(
                    context.symbol,
                    reason=f"confidence {sig.confidence:.2f} below min {self.min_confidence_to_trade}",
                    rejected_signal=sig.action.value,
                )
            if sig.size_pct > self.max_position_size_pct:
                sig.size_pct = self.max_position_size_pct
                sig.metadata["size_capped"] = True
            if sig.leverage > self.max_leverage:
                sig.leverage = self.max_leverage
                sig.metadata["leverage_capped"] = True
            return sig
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[{self.name}] generate_signal failed: {exc}")
            return self._hold(
                context.symbol,
                reason=f"strategy error: {exc}",
                error=str(exc),
            )

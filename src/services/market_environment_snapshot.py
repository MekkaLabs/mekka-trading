"""
src/services/market_environment_snapshot.py
========================================
Story 192 — MarketEnvironmentSnapshot: captura de estado do ambiente entre ciclos.

Inspirado no padrão SWE-agent Environment State Capture:
  "Between steps, the environment state is captured (working directory, open files,
   last command output) and shown to agent as context. The ACI uses guardrails to
   prevent common mistakes based on the current environment state."

No SWE-agent, o ambiente é o sistema de arquivos + shell state. Entre cada turn,
o estado é capturado e disponibilizado como contexto para o agente decidir sua
próxima ação baseado em *onde ele está*, não apenas na instrução recebida.

No Mekka, o "ambiente" é o mercado: preço, regime, OI, funding rate, posição atual.
`MarketEnvironmentSnapshot` captura esse estado no início do ciclo e o disponibiliza
para múltiplos consumidores:
  - IncrementalCycleSkip (Story 187): diff preciso entre snapshots consecutivos
  - CycleTrajectory (Story 188): input_summary de cada step
  - Vision: bloco de contexto de ambiente
  - Dashboard: "current market environment" endpoint

Arquitetura
-----------
  EnvironmentSnapshot — snapshot imutável do estado do mercado
  MarketEnvironmentSnapshotStore
    ├── capture(symbol, analysis) → EnvironmentSnapshot
    ├── get_latest(symbol) → EnvironmentSnapshot | None
    ├── diff(symbol) → EnvironmentDiff  (vs snapshot anterior)
    ├── get_prompt_block(symbol) → str
    └── summary() → dict

Uso em NickFury._cycle_for_symbol (logo após analysis = await professor.run())
----------------------------------------------------------------------
    from src.services.market_environment_snapshot import get_env_snapshot_store

    _snap = get_env_snapshot_store().capture(symbol, analysis=analysis)
    _diff = get_env_snapshot_store().diff(symbol)  # para IncrementalCycleSkip
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# EnvironmentSnapshot
# ---------------------------------------------------------------------------

@dataclass
class EnvironmentSnapshot:
    """
    Snapshot imutável do estado do mercado em um instante.

    Equivalente ao "environment state" do SWE-agent — capturado entre steps
    para dar contexto ao agente sobre "onde o mercado está agora".
    """
    symbol: str
    price: float
    regime: str = "UNKNOWN"
    cap_tier: str = "UNKNOWN"

    # Indicadores técnicos
    rsi: Optional[float] = None
    atr: Optional[float] = None
    volume_ratio: Optional[float] = None       # volume / avg_volume
    trend: str = "NEUTRAL"                     # "UP", "DOWN", "NEUTRAL"

    # Macro / derivativos (se disponíveis)
    funding_rate: Optional[float] = None       # funding rate da perp
    open_interest: Optional[float] = None      # OI em USD
    fear_greed_index: Optional[int] = None     # 0-100

    # Posição atual (se houver)
    has_open_position: bool = False
    current_pnl_usd: Optional[float] = None

    # Meta
    cycle_id: str = ""
    captured_at: float = field(default_factory=time.monotonic)

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.captured_at

    def to_prompt_block(self) -> str:
        """Bloco compacto para injeção no prompt Vision."""
        lines = [f"=== Market Environment: {self.symbol} ==="]
        lines.append(f"  Price        : {self.price:,.4f}")
        lines.append(f"  Regime       : {self.regime}")
        lines.append(f"  Cap Tier     : {self.cap_tier}")
        lines.append(f"  Trend        : {self.trend}")
        if self.rsi is not None:
            lines.append(f"  RSI(14)      : {self.rsi:.1f}")
        if self.atr is not None:
            lines.append(f"  ATR(14)      : {self.atr:.4f}")
        if self.volume_ratio is not None:
            lines.append(f"  Volume Ratio : {self.volume_ratio:.2f}x avg")
        if self.funding_rate is not None:
            lines.append(f"  Funding Rate : {self.funding_rate:.4%}")
        if self.open_interest is not None:
            lines.append(f"  Open Interest: ${self.open_interest:,.0f}")
        if self.fear_greed_index is not None:
            level = "Extreme Fear" if self.fear_greed_index < 25 else (
                "Fear" if self.fear_greed_index < 45 else (
                    "Neutral" if self.fear_greed_index < 55 else (
                        "Greed" if self.fear_greed_index < 75 else "Extreme Greed"
                    )
                )
            )
            lines.append(f"  Fear & Greed : {self.fear_greed_index} ({level})")
        if self.has_open_position:
            pnl_str = f"{self.current_pnl_usd:+.2f} USD" if self.current_pnl_usd is not None else "?"
            lines.append(f"  Open Position: YES (PnL: {pnl_str})")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "regime": self.regime,
            "cap_tier": self.cap_tier,
            "rsi": self.rsi,
            "atr": self.atr,
            "volume_ratio": self.volume_ratio,
            "trend": self.trend,
            "funding_rate": self.funding_rate,
            "open_interest": self.open_interest,
            "fear_greed_index": self.fear_greed_index,
            "has_open_position": self.has_open_position,
            "current_pnl_usd": self.current_pnl_usd,
            "cycle_id": self.cycle_id,
            "age_seconds": round(self.age_seconds, 1),
        }


# ---------------------------------------------------------------------------
# EnvironmentDiff
# ---------------------------------------------------------------------------

@dataclass
class EnvironmentDiff:
    """Diff entre dois snapshots consecutivos."""
    symbol: str
    price_delta_pct: float          # variação percentual do preço
    regime_changed: bool            # True se regime mudou
    prev_regime: str
    curr_regime: str
    has_prev_snapshot: bool = False # False = não há snapshot anterior

    @property
    def is_material_change(self) -> bool:
        """True se a mudança é material o suficiente para justificar novo LLM call."""
        return (
            abs(self.price_delta_pct) > 0.002  # > 0.2%
            or self.regime_changed
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price_delta_pct": round(self.price_delta_pct, 5),
            "regime_changed": self.regime_changed,
            "prev_regime": self.prev_regime,
            "curr_regime": self.curr_regime,
            "is_material_change": self.is_material_change,
            "has_prev_snapshot": self.has_prev_snapshot,
        }


# ---------------------------------------------------------------------------
# MarketEnvironmentSnapshotStore
# ---------------------------------------------------------------------------

class MarketEnvironmentSnapshotStore:
    """
    Store de snapshots de ambiente de mercado por símbolo.

    Padrão SWE-agent: ambiente é capturado entre steps para dar contexto
    ao agente. Aqui: estado do mercado é capturado entre ciclos.
    """

    def __init__(self, max_history: int = 3) -> None:
        self._current: Dict[str, EnvironmentSnapshot] = {}    # latest per symbol
        self._previous: Dict[str, EnvironmentSnapshot] = {}   # second-latest per symbol
        self._max_history = max_history

    def capture(self, symbol: str, analysis: Any = None, cycle_id: str = "") -> EnvironmentSnapshot:
        """
        Captura e armazena um snapshot do estado atual do mercado.

        Args:
            symbol: símbolo do ativo
            analysis: MarketAnalysis (se disponível, extrai campos automaticamente)
            cycle_id: ID do ciclo atual

        Returns:
            EnvironmentSnapshot criado.
        """
        sym = symbol.upper()

        # Promove current → previous
        if sym in self._current:
            self._previous[sym] = self._current[sym]

        # Extrai campos do analysis se disponível
        price = 0.0
        regime = "UNKNOWN"
        cap_tier = "UNKNOWN"
        rsi = None
        atr = None
        trend = "NEUTRAL"
        volume_ratio = None
        funding_rate = None
        open_interest = None

        if analysis is not None:
            try:
                price = float(getattr(analysis, "price", 0) or 0)
            except Exception:  # noqa: BLE001
                pass
            try:
                chart = getattr(analysis, "chart", None)
                if chart:
                    rsi = float(getattr(chart, "rsi_14", None) or 0) or None
                    atr = float(getattr(chart, "atr_14", None) or 0) or None
                    volume_ratio = float(getattr(chart, "volume_ratio", None) or 0) or None
                    trend_dir = getattr(chart, "trend", "NEUTRAL")
                    trend = str(trend_dir).upper() if trend_dir else "NEUTRAL"
            except Exception:  # noqa: BLE001
                pass
            try:
                meta = getattr(analysis, "signal_metadata", None) or {}
                regime = meta.get("market_regime", "UNKNOWN")
                cap_tier = meta.get("cap_tier", "UNKNOWN")
            except Exception:  # noqa: BLE001
                pass

        snap = EnvironmentSnapshot(
            symbol=sym,
            price=price,
            regime=regime,
            cap_tier=cap_tier,
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
            trend=trend,
            funding_rate=funding_rate,
            open_interest=open_interest,
            cycle_id=cycle_id,
        )
        self._current[sym] = snap

        logger.debug(
            f"[EnvSnapshot] captured {sym} price={price:.4f} "
            f"regime={regime} cycle={cycle_id}"
        )
        return snap

    def get_latest(self, symbol: str) -> Optional[EnvironmentSnapshot]:
        """Retorna o snapshot mais recente do símbolo."""
        return self._current.get(symbol.upper())

    def diff(self, symbol: str) -> EnvironmentDiff:
        """
        Calcula diff entre o snapshot atual e o anterior.

        Útil para IncrementalCycleSkip decidir se precisa re-executar Vision.
        """
        sym = symbol.upper()
        curr = self._current.get(sym)
        prev = self._previous.get(sym)

        if curr is None:
            return EnvironmentDiff(
                symbol=sym, price_delta_pct=0.0,
                regime_changed=False, prev_regime="", curr_regime="",
                has_prev_snapshot=False,
            )

        if prev is None:
            return EnvironmentDiff(
                symbol=sym, price_delta_pct=0.0,
                regime_changed=False, prev_regime="", curr_regime=curr.regime,
                has_prev_snapshot=False,
            )

        price_delta = (curr.price - prev.price) / prev.price if prev.price > 0 else 0.0
        regime_changed = curr.regime.upper() != prev.regime.upper()

        return EnvironmentDiff(
            symbol=sym,
            price_delta_pct=price_delta,
            regime_changed=regime_changed,
            prev_regime=prev.regime,
            curr_regime=curr.regime,
            has_prev_snapshot=True,
        )

    def get_prompt_block(self, symbol: str) -> str:
        """Retorna o bloco de prompt do snapshot mais recente."""
        snap = self.get_latest(symbol)
        return snap.to_prompt_block() if snap else ""

    def summary(self) -> dict:
        return {
            "symbols_tracked": len(self._current),
            "snapshots": {
                sym: snap.to_dict()
                for sym, snap in self._current.items()
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[MarketEnvironmentSnapshotStore] = None


def get_env_snapshot_store() -> MarketEnvironmentSnapshotStore:
    """Retorna o singleton global do MarketEnvironmentSnapshotStore."""
    global _store
    if _store is None:
        _store = MarketEnvironmentSnapshotStore()
    return _store


def reset_env_snapshot_store() -> None:
    """Reseta o singleton — para testes."""
    global _store
    _store = None

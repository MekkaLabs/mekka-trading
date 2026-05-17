"""
src/services/cycle_incremental_guard.py
========================================
Story 187 — IncrementalCycleSkip: pula Vision LLM call se nada material mudou.

Inspirado no padrão MetaGPT Incremental Development:
  "The incremental development process tracks what changed between runs and
   only re-processes affected stages. The Product Manager is prompted to refine
   specific elements due to incremental development — skipping untouched areas
   to avoid wasted LLM calls and context churn."

No MetaGPT, IncrementalChangeContext compara o estado atual com o snapshot
anterior e só re-executa stages cujos inputs mudaram. O equivalente no Mekka
é checar se o mercado mudou o suficiente para justificar um novo LLM call em
Vision — se preço/regime são praticamente iguais ao ciclo anterior, reusar
o sinal anterior economiza tempo, custo e reduz rate-limit risk.

Lógica de skip:
  1. Δprice < price_threshold_pct (ex: 0.2%)     AND
  2. regime_str == último regime visto              AND
  3. último sinal tem idade < max_signal_age_s (ex: 120s)
  → skip = True: retorna último sinal, emite evento CYCLE_SKIPPED

Arquitetura
-----------
  CycleCheckpoint — snapshot do último ciclo por símbolo
  IncrementalCycleGuard
    ├── should_skip(symbol, current_price, current_regime) → (bool, str)
    ├── update(symbol, price, regime, signal)
    └── summary() → dict

Uso em NickFury._cycle_for_symbol (após Vision, antes do lint)
--------------------------------------------------------------
    from src.services.cycle_incremental_guard import get_cycle_incremental_guard

    _guard = get_cycle_incremental_guard()
    _skip, _skip_reason = _guard.should_skip(symbol, current_price=analysis.price, current_regime=_regime)
    if _skip and last_signal is not None:
        self._log.debug(f"[NickFury:187] IncrementalCycleSkip: {_skip_reason}")
        signal = last_signal  # reusa sinal anterior
        # ... emite CYCLE_SKIPPED event
    else:
        signal = await self._vision.run(analysis=analysis)
        _guard.update(symbol, price=analysis.price, regime=_regime, signal=signal)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# CycleCheckpoint
# ---------------------------------------------------------------------------

@dataclass
class CycleCheckpoint:
    """
    Snapshot do último ciclo concluído para um símbolo.

    Equivalente ao IncrementalChangeContext do MetaGPT — armazena o
    "estado anterior" para comparação com o ciclo atual.
    """
    symbol: str
    last_price: float
    last_regime: str
    last_signal: Any          # TradingSignal ou None
    recorded_at: float = field(default_factory=time.monotonic)
    skip_count: int = 0       # vezes que este checkpoint foi reutilizado

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.recorded_at

    def to_dict(self) -> dict:
        signal_summary = None
        if self.last_signal is not None:
            try:
                signal_summary = {
                    "action": self.last_signal.action.value,
                    "confidence": self.last_signal.confidence,
                }
            except Exception:  # noqa: BLE001
                signal_summary = str(self.last_signal)
        return {
            "symbol": self.symbol,
            "last_price": self.last_price,
            "last_regime": self.last_regime,
            "age_seconds": round(self.age_seconds, 1),
            "skip_count": self.skip_count,
            "signal": signal_summary,
        }


# ---------------------------------------------------------------------------
# IncrementalCycleGuard
# ---------------------------------------------------------------------------

class IncrementalCycleGuard:
    """
    Guarda de skip incremental — verifica se Vision LLM call pode ser pulado.

    Padrão MetaGPT Incremental Development: compara estado atual com snapshot
    anterior e decide se o estágio precisa re-executar ou pode ser skipado.
    """

    def __init__(
        self,
        price_threshold_pct: float = 0.002,    # 0.2% de variação mínima
        max_signal_age_s: float = 120.0,         # máximo 2 minutos de reutilização
    ) -> None:
        self._checkpoints: Dict[str, CycleCheckpoint] = {}
        self._price_threshold_pct = price_threshold_pct
        self._max_signal_age_s = max_signal_age_s
        self._total_skips: int = 0
        self._total_checks: int = 0

    def should_skip(
        self,
        symbol: str,
        current_price: float,
        current_regime: str = "UNKNOWN",
    ) -> Tuple[bool, str]:
        """
        Decide se o estágio Vision pode ser pulado para este símbolo.

        Condições para skip (todas devem ser verdadeiras):
          1. Existe um checkpoint anterior para o símbolo
          2. Δprice < price_threshold_pct
          3. current_regime == last_regime
          4. Idade do checkpoint < max_signal_age_s
          5. Existe um sinal anterior válido para reutilizar

        Returns:
            (should_skip: bool, reason: str)
        """
        self._total_checks += 1
        sym = symbol.upper()

        cp = self._checkpoints.get(sym)
        if cp is None:
            return False, "no_checkpoint"

        # Condição 4: checkpoint muito antigo
        if cp.age_seconds > self._max_signal_age_s:
            return False, f"checkpoint_expired(age={cp.age_seconds:.0f}s > {self._max_signal_age_s}s)"

        # Condição 5: sem sinal anterior
        if cp.last_signal is None:
            return False, "no_previous_signal"

        # Condição 3: regime mudou
        if cp.last_regime.upper() != current_regime.upper():
            return False, f"regime_changed({cp.last_regime}→{current_regime})"

        # Condição 2: preço variou demais
        if cp.last_price > 0:
            price_delta_pct = abs(current_price - cp.last_price) / cp.last_price
            if price_delta_pct > self._price_threshold_pct:
                return False, f"price_moved({price_delta_pct:.3%} > {self._price_threshold_pct:.3%})"

        # Tudo OK → pode skipar
        return True, (
            f"incremental_skip(price_stable, regime={current_regime}, "
            f"age={cp.age_seconds:.0f}s)"
        )

    def update(
        self,
        symbol: str,
        price: float,
        regime: str,
        signal: Any,
    ) -> CycleCheckpoint:
        """
        Atualiza o checkpoint após um ciclo completo (Vision executou normalmente).

        Deve ser chamado SEMPRE que Vision rodar — para que o próximo ciclo
        tenha dados frescos para decidir se pode skipar.

        Args:
            symbol: símbolo do ativo
            price: preço atual (analysis.price)
            regime: regime de mercado atual
            signal: TradingSignal gerado pelo Vision

        Returns:
            CycleCheckpoint atualizado.
        """
        sym = symbol.upper()
        cp = CycleCheckpoint(
            symbol=sym,
            last_price=float(price),
            last_regime=str(regime).upper(),
            last_signal=signal,
        )
        self._checkpoints[sym] = cp
        logger.debug(
            f"[IncrementalCycleGuard] checkpoint updated {sym} "
            f"price={price:.4f} regime={regime}"
        )
        return cp

    def register_skip(self, symbol: str) -> None:
        """Registra que o skip foi efetivamente utilizado (incrementa contadores)."""
        self._total_skips += 1
        sym = symbol.upper()
        cp = self._checkpoints.get(sym)
        if cp:
            cp.skip_count += 1

    def get_last_signal(self, symbol: str) -> Optional[Any]:
        """Retorna o último sinal armazenado para o símbolo, ou None."""
        cp = self._checkpoints.get(symbol.upper())
        return cp.last_signal if cp else None

    def invalidate(self, symbol: str) -> bool:
        """Remove o checkpoint de um símbolo (force re-execute Vision). Retorna True se existia."""
        sym = symbol.upper()
        existed = sym in self._checkpoints
        self._checkpoints.pop(sym, None)
        return existed

    @property
    def skip_rate(self) -> float:
        return self._total_skips / self._total_checks if self._total_checks > 0 else 0.0

    def summary(self) -> dict:
        return {
            "symbols_tracked": len(self._checkpoints),
            "total_checks": self._total_checks,
            "total_skips": self._total_skips,
            "skip_rate": round(self.skip_rate, 3),
            "price_threshold_pct": self._price_threshold_pct,
            "max_signal_age_s": self._max_signal_age_s,
            "checkpoints": {
                sym: cp.to_dict()
                for sym, cp in self._checkpoints.items()
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_guard: Optional[IncrementalCycleGuard] = None


def get_cycle_incremental_guard() -> IncrementalCycleGuard:
    """
    Retorna o singleton global do IncrementalCycleGuard.
    Parâmetros lidos de settings (com fallback para defaults seguros).
    """
    global _guard
    if _guard is None:
        try:
            from src.config.settings import settings
            price_thr = float(getattr(settings, "incremental_price_threshold_pct", 0.002))
            max_age   = float(getattr(settings, "incremental_max_signal_age_s", 120.0))
        except Exception:  # noqa: BLE001
            price_thr = 0.002
            max_age   = 120.0
        _guard = IncrementalCycleGuard(
            price_threshold_pct=price_thr,
            max_signal_age_s=max_age,
        )
    return _guard


def reset_cycle_incremental_guard() -> None:
    """Reseta o singleton — para testes."""
    global _guard
    _guard = None

"""
src/services/breakers.py
========================
Consecutive-event circuit breakers (Story 029a — Safety Net).
Story 138 — Circuit Breaker Matrix (gaps): RateWindowBreaker, StalePriceDetector, SpreadBreaker.

A `ConsecutiveBreaker` watches a stream of boolean observations (hit /
no-hit). Each `observe(hit=True)` increments an internal streak; each
`observe(hit=False)` resets it. When the streak reaches `threshold`,
the breaker is **TRIPPED** and the caller is expected to take action
(typically engage the kill switch).

The breaker itself is **passive** — it does not engage the kill switch
or write to audit log. Separation of concerns: the breaker counts; the
orchestrator decides what to do when it trips. This keeps the service
free of agent dependencies and easier to test.

Usage
-----
    breaker = ConsecutiveBreaker(name="exec_error", threshold=3)
    if breaker.observe(execution.status == ExecutionStatus.ERROR):
        engage_kill_switch(f"3 consecutive exec errors")
        await audit.log_event(...)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


@dataclass
class ConsecutiveBreaker:
    """Stateful counter of consecutive boolean hits."""

    name: str
    threshold: int
    streak: int = 0
    trip_count: int = 0  # how many times the breaker has tripped lifetime

    def __post_init__(self) -> None:
        if self.threshold < 1:
            raise ValueError(f"threshold must be >= 1, got {self.threshold}")

    def observe(self, hit: bool) -> bool:
        """
        Record one observation. Returns True iff this observation tripped
        the breaker (i.e. streak crossed threshold on this call).
        """
        if hit:
            self.streak += 1
            if self.streak == self.threshold:
                # Trip exactly once per crossing; further hits keep streak
                # incrementing but don't re-trip until a reset happens.
                self.trip_count += 1
                return True
            return False
        # Non-hit resets the streak
        self.streak = 0
        return False

    def reset(self) -> None:
        """Manually clear the streak (used after kill switch is released)."""
        self.streak = 0

    @property
    def is_armed(self) -> bool:
        """True when the breaker is currently above zero (warm)."""
        return self.streak > 0

    def summary(self) -> str:
        return (
            f"[Breaker:{self.name}] streak={self.streak}/{self.threshold} "
            f"trips_lifetime={self.trip_count}"
        )


# ---------------------------------------------------------------------------
# Story 138 — RateWindowBreaker
# ---------------------------------------------------------------------------

class RateWindowBreaker:
    """
    Story 138 — Sliding-window error rate circuit breaker.

    Mantém uma janela deslizante das últimas `window` observações booleanas.
    Dispara quando a taxa de erros (True observations) excede `max_error_rate`.

    Uso típico: LLM error rate, API timeout rate.

    Exemplo:
        breaker = RateWindowBreaker("llm_errors", window=10, max_error_rate=0.5)
        if breaker.observe(is_error):
            enter_degraded_mode()
    """

    def __init__(self, name: str, window: int = 10, max_error_rate: float = 0.5) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        if not 0.0 < max_error_rate <= 1.0:
            raise ValueError("max_error_rate must be in (0, 1]")
        self.name = name
        self.window = window
        self.max_error_rate = max_error_rate
        self._history: Deque[bool] = deque(maxlen=window)
        self.trip_count: int = 0
        self._tripped_at_last_observe: bool = False

    def observe(self, hit: bool) -> bool:
        """
        Registra uma observação. Retorna True se a taxa de erro ultrapassou
        max_error_rate NESTA observação (transição para tripped).
        """
        self._history.append(hit)
        if len(self._history) < self.window:
            self._tripped_at_last_observe = False
            return False
        error_rate = sum(self._history) / len(self._history)
        tripped = error_rate >= self.max_error_rate
        if tripped and not self._tripped_at_last_observe:
            self.trip_count += 1
        self._tripped_at_last_observe = tripped
        return tripped and (sum(self._history) == sum(list(self._history)[-1:]) + sum(list(self._history)[:-1]))

    @property
    def error_rate(self) -> float:
        """Taxa de erro atual na janela (0.0–1.0)."""
        if not self._history:
            return 0.0
        return sum(self._history) / len(self._history)

    @property
    def is_tripped(self) -> bool:
        """True se a taxa atual está acima de max_error_rate."""
        return self.error_rate >= self.max_error_rate and len(self._history) >= self.window

    def reset(self) -> None:
        """Limpa o histórico (após recovery do LLM)."""
        self._history.clear()
        self._tripped_at_last_observe = False

    def summary(self) -> str:
        return (
            f"[RateBreaker:{self.name}] rate={self.error_rate:.1%} "
            f"window={len(self._history)}/{self.window} "
            f"threshold={self.max_error_rate:.1%} tripped={self.is_tripped}"
        )


# ---------------------------------------------------------------------------
# Story 138 — StalePriceDetector
# ---------------------------------------------------------------------------

class StalePriceDetector:
    """
    Story 138 — Detecta feed de preço frozen (stale).

    Mantém os últimos `window` preços observados. Dispara quando todos
    são idênticos (variação percentual < `min_variation_pct`), indicando
    que o feed pode estar travado.

    Uso típico: verificar antes de cada ciclo se o preço mudou.

    Exemplo:
        detector = StalePriceDetector("BTC_price", window=3, min_variation_pct=0.0001)
        if detector.observe(current_price):
            halt_new_entries(f"Stale price detected: {current_price}")
    """

    def __init__(
        self,
        name: str,
        window: int = 3,
        min_variation_pct: float = 0.0001,
    ) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        self.name = name
        self.window = window
        self.min_variation_pct = min_variation_pct
        self._prices: Deque[float] = deque(maxlen=window)
        self.trip_count: int = 0

    def observe(self, price: float) -> bool:
        """
        Registra um preço. Retorna True se a janela está cheia E todos os
        preços são idênticos (variação < min_variation_pct).
        """
        self._prices.append(price)
        if len(self._prices) < self.window:
            return False
        prices = list(self._prices)
        min_p, max_p = min(prices), max(prices)
        if min_p <= 0:
            return False
        variation = (max_p - min_p) / min_p
        stale = variation < self.min_variation_pct
        if stale:
            self.trip_count += 1
        return stale

    @property
    def last_price(self) -> Optional[float]:
        return self._prices[-1] if self._prices else None

    def reset(self) -> None:
        """Limpa o histórico (após feed recuperar)."""
        self._prices.clear()

    def summary(self) -> str:
        prices = list(self._prices)
        var_str = "N/A"
        if len(prices) >= 2 and min(prices) > 0:
            var_str = f"{(max(prices) - min(prices)) / min(prices):.6%}"
        return (
            f"[StalePriceDetector:{self.name}] "
            f"window={len(self._prices)}/{self.window} "
            f"variation={var_str} trips={self.trip_count}"
        )


# ---------------------------------------------------------------------------
# Story 138 — SpreadBreaker
# ---------------------------------------------------------------------------

class SpreadBreaker:
    """
    Story 138 — Detecta spread anormalmente elevado.

    Mantém média móvel do spread (ask - bid) / mid. Dispara quando o
    spread atual é > `max_spread_multiplier` vezes a média histórica.

    Skip-trade semântica: não tripa permanentemente, avalia por tick.

    Exemplo:
        breaker = SpreadBreaker("BTC_spread", history_window=20, max_spread_multiplier=3.0)
        if breaker.observe(bid=50000, ask=50010):
            skip_this_trade("Spread anormal")
    """

    def __init__(
        self,
        name: str,
        history_window: int = 20,
        max_spread_multiplier: float = 3.0,
        min_spread_pct: float = 0.0001,
    ) -> None:
        self.name = name
        self.history_window = history_window
        self.max_spread_multiplier = max_spread_multiplier
        self.min_spread_pct = min_spread_pct
        self._history: Deque[float] = deque(maxlen=history_window)
        self.skip_count: int = 0

    def observe(self, bid: float, ask: float) -> bool:
        """
        Registra bid/ask. Retorna True se o spread atual é anormal
        (> max_spread_multiplier × média histórica).
        """
        if bid <= 0 or ask <= 0 or ask < bid:
            return False
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / mid
        self._history.append(spread_pct)

        if len(self._history) < max(3, self.history_window // 4):
            # Janela insuficiente para baseline — não tripa
            return False

        avg_spread = sum(self._history) / len(self._history)
        if avg_spread < self.min_spread_pct:
            return False  # spread histórico ínfimo — não usar como baseline

        abnormal = spread_pct > self.max_spread_multiplier * avg_spread
        if abnormal:
            self.skip_count += 1
        return abnormal

    @property
    def avg_spread_pct(self) -> float:
        if not self._history:
            return 0.0
        return sum(self._history) / len(self._history)

    def reset(self) -> None:
        self._history.clear()

    def summary(self) -> str:
        return (
            f"[SpreadBreaker:{self.name}] "
            f"avg_spread={self.avg_spread_pct:.4%} "
            f"multiplier={self.max_spread_multiplier}× "
            f"skips={self.skip_count}"
        )

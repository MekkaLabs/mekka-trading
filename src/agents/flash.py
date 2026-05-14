"""
src/agents/flash.py
====================
Flash — Momentum Scalper (Story 033).

Flash detecta micro-momentum dentro de uma janela curta — o objetivo é
identificar bursts/reversões intra-candle que mereçam atenção do
operador (ou, no futuro, de Vision em um sub-cycle tático). Em v1
Flash é **read-only e advisory**: emite `MomentumSignal` que vai pro
audit log; nenhum agente downstream consome ainda.

Hard rules
----------
- **Read-only.** Flash não chama Iron Man, não toca o exchange.
- **Stateless por chamada.** Cada `run()` é independente; sem
  memória interna entre cycles. O caller passa o histórico relevante.
- **Determinístico.** Sem LLM. Cálculos puros sobre price + volume.
- **Defensivo.** Histórico curto demais → SIDEWAYS com strength=0.
- **Não dispara entrada.** Em v1 não modifica o pipeline principal.
  Story futura pode usar `MomentumSignal.is_strong` como gating de
  entry timing.
"""

from __future__ import annotations

import time
from typing import Optional

from src.agents.base import BaseAgent
from src.models.signal import MomentumDirection, MomentumSignal


# ---------------------------------------------------------------------------
# Tunable thresholds (locais — não inflando settings ainda)
# ---------------------------------------------------------------------------
_MIN_HISTORY = 6                  # need ≥6 prices for stable signal
_BURST_PCT_UP = 0.005             # +0.5% net move = up burst
_BURST_PCT_DOWN = -0.005          # -0.5% net move = down burst
_VOLUME_SPIKE_THRESHOLD = 1.5     # current volume / avg ≥ this → spike
_DEFAULT_WINDOW_SECONDS = 300     # default 5-min window
# Story 050 — Circuit breaker: minimum seconds between runs for the same symbol.
# Prevents audit log spam and redundant computations in fast cycles.
_CACHE_TTL_SECONDS = 60           # 1 minute cool-down per symbol


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _classify_direction(net_pct: float) -> MomentumDirection:
    if net_pct >= _BURST_PCT_UP:
        return MomentumDirection.UP
    if net_pct <= _BURST_PCT_DOWN:
        return MomentumDirection.DOWN
    return MomentumDirection.SIDEWAYS


def _strength_score(net_pct: float, volume_mult: float) -> float:
    """
    Combine net price move with volume amplification into a 0..1
    strength score. Saturates at 1.0.
    """
    # Baseline strength from net move (saturates at 2× the burst threshold)
    move_component = min(abs(net_pct) / (_BURST_PCT_UP * 2), 1.0)
    # Volume amplifier: 1× volume → 0.5; 2× → 1.0; capped
    vol_component = min(max(volume_mult - 0.5, 0.0) / 1.5, 1.0)
    # Weighted combo
    return round(min(move_component * 0.7 + vol_component * 0.3, 1.0), 4)


class Flash(BaseAgent[MomentumSignal]):
    """
    Momentum Scalper. Reads a short price/volume history slice and
    emits a `MomentumSignal`.

    Usage
    -----
        signal = await Flash().run(
            symbol="BTC",
            recent_prices=[64500, 64580, 64640, 64710, 64790, 64860],
            recent_volumes=[120, 140, 160, 200, 240, 260],
        )
        if signal.is_strong:
            # Story-future: gate Vision entry timing on this
            ...
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Flash",
            role="Momentum Scalper — intra-candle burst detector",
        )
        # Story 050 — per-symbol result cache: {symbol: (timestamp, MomentumSignal)}
        # Acts as a circuit breaker: if called again within _CACHE_TTL_SECONDS,
        # returns the cached result without recomputing or logging.
        self._cache: dict[str, tuple[float, MomentumSignal]] = {}

    async def _run(  # type: ignore[override]
        self,
        symbol: str,
        recent_prices: Optional[list[float]] = None,
        recent_volumes: Optional[list[float]] = None,
        window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    ) -> MomentumSignal:
        """
        Parameters
        ----------
        symbol         : Asset symbol, e.g. 'BTC'
        recent_prices  : Chronological list of recent close/last prices
                         (most-recent last). Need ≥ _MIN_HISTORY entries.
        recent_volumes : Optional volume series aligned with recent_prices.
                         Used to compute a volume multiplier vs. the mean
                         of the window.
        window_seconds : How many seconds the input represents — populated
                         into the output `entry_window_seconds` so a future
                         consumer knows how fresh the signal is.
        """
        # Story 050 — Circuit breaker: return cached result if still fresh
        now = time.monotonic()
        cached = self._cache.get(symbol)
        if cached is not None:
            ts_cached, sig_cached = cached
            if now - ts_cached < _CACHE_TTL_SECONDS:
                self._log.debug(
                    f"[Flash] {symbol} — cache hit ({now - ts_cached:.0f}s < {_CACHE_TTL_SECONDS}s TTL)"
                )
                return sig_cached

        prices = list(recent_prices or [])
        volumes = list(recent_volumes or [])

        # Defensive: insufficient data → SIDEWAYS, strength=0
        if len(prices) < _MIN_HISTORY:
            sig = MomentumSignal(
                symbol=symbol,
                direction=MomentumDirection.SIDEWAYS,
                strength=0.0,
                entry_window_seconds=int(window_seconds),
                price_change_pct=0.0,
                volume_multiplier=1.0,
                notes=f"Insufficient price history ({len(prices)} < {_MIN_HISTORY})",
            )
            self._log.info(sig.summary())
            self._cache[symbol] = (now, sig)
            return sig

        first = float(prices[0])
        last = float(prices[-1])
        net_pct = _safe_div(last - first, first) if first > 0 else 0.0
        direction = _classify_direction(net_pct)

        # Volume amplification (optional)
        volume_mult = 1.0
        if volumes and len(volumes) == len(prices):
            try:
                avg_vol = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
                if avg_vol > 0:
                    volume_mult = float(volumes[-1]) / avg_vol
            except (TypeError, ZeroDivisionError, ValueError):
                volume_mult = 1.0

        strength = _strength_score(net_pct, volume_mult)

        notes_bits = [
            f"{direction.value} {net_pct:+.3%} over {len(prices)}pts",
            f"vol×{volume_mult:.2f}",
        ]
        if volume_mult >= _VOLUME_SPIKE_THRESHOLD and direction != MomentumDirection.SIDEWAYS:
            notes_bits.append("VOLUME-CONFIRMED")

        sig = MomentumSignal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            entry_window_seconds=int(window_seconds),
            price_change_pct=round(net_pct, 6),
            volume_multiplier=round(volume_mult, 4),
            notes=" | ".join(notes_bits),
        )
        self._log.info(sig.summary())
        self._cache[symbol] = (now, sig)  # Story 050 — update circuit breaker cache
        return sig

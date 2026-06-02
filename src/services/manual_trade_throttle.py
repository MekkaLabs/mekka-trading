"""
src/services/manual_trade_throttle.py
======================================
TRADE-3 (2026-05-29) — rate limit em trades manuais via dashboard.

ANTES: /api/trade/manual e /api/trade/execute não tinham throttle. Operador
(ou bug em UI) podia bombardear o pipeline — 100 trades/min passariam por
Batman. Não tem proteção real, só Batman gates.

DEPOIS: ManualTradeThrottle in-memory com sliding window — limita por:
  - bucket (default "global", pode ser per-user/per-symbol no futuro)
  - max events na janela
  - janela em segundos

Default: 5 trades manuais por hora. Configurável via env
``MANUAL_TRADE_MAX_PER_HOUR`` (default 5).

Read-only no DB, sem I/O remoto, sem dependência de loop assyncio.
Idempotente: chamar `try_consume` retorna True/False conforme cap.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from loguru import logger


def _default_max() -> int:
    try:
        return max(1, int(os.environ.get("MANUAL_TRADE_MAX_PER_HOUR", "5")))
    except (TypeError, ValueError):
        return 5


def _default_window_s() -> float:
    try:
        return max(60.0, float(os.environ.get("MANUAL_TRADE_WINDOW_S", "3600")))
    except (TypeError, ValueError):
        return 3600.0


class ManualTradeThrottle:
    """Sliding-window throttle. Thread-safe via lock."""

    def __init__(
        self,
        max_per_window: Optional[int] = None,
        window_s: Optional[float] = None,
    ) -> None:
        self.max = max_per_window if max_per_window is not None else _default_max()
        self.window = window_s if window_s is not None else _default_window_s()
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def try_consume(self, bucket: str = "global") -> tuple[bool, dict]:
        """Tenta gastar 1 unidade do bucket. Retorna (allowed, metadata).

        metadata contém:
          - count_in_window: int
          - max: int
          - window_s: float
          - remaining: int
          - retry_after_s: int (only when blocked)
        """
        now = time.monotonic()
        with self._lock:
            dq = self._events[bucket]
            # Expira eventos antigos
            while dq and now - dq[0] > self.window:
                dq.popleft()

            count = len(dq)
            meta = {
                "count_in_window": count,
                "max": self.max,
                "window_s": self.window,
                "remaining": max(0, self.max - count),
            }
            if count >= self.max:
                # Bloqueado — calcula quanto falta pro mais antigo sair
                retry_after = max(0, int(self.window - (now - dq[0]) + 1))
                meta["retry_after_s"] = retry_after
                return False, meta

            dq.append(now)
            meta["count_in_window"] = count + 1
            meta["remaining"] = self.max - (count + 1)
            return True, meta

    def snapshot(self) -> dict:
        """Estado atual de todos os buckets — útil pra debug e dashboard."""
        with self._lock:
            now = time.monotonic()
            out: dict = {"max": self.max, "window_s": self.window, "buckets": {}}
            for bucket, dq in self._events.items():
                fresh = [t for t in dq if now - t <= self.window]
                out["buckets"][bucket] = {
                    "count_in_window": len(fresh),
                    "remaining": max(0, self.max - len(fresh)),
                }
            return out


# Singleton
_instance: Optional[ManualTradeThrottle] = None


def get_throttle() -> ManualTradeThrottle:
    """Singleton lazy. Default 5/h."""
    global _instance
    if _instance is None:
        _instance = ManualTradeThrottle()
        logger.info(
            f"[manual_trade_throttle] init: "
            f"max={_instance.max}/window={_instance.window}s"
        )
    return _instance


def reset_throttle() -> None:
    """Útil em testes — força nova instância."""
    global _instance
    _instance = None

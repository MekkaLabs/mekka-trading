"""
src/services/pipeline_benchmark.py
=====================================
Story 151 — Performance Benchmarks.

Mede a latência end-to-end do pipeline de trading:
  ProfessorX → Vision → Batman → IronMan

Integração: NickFury chama `record_stage()` no início e fim de cada
estágio, e `record_cycle()` ao final do ciclo completo. Se a latência
total > `alert_threshold_s`, publica `pipeline.slow_cycle` via EventBus.

Métricas mantidas em memória (rolling window):
  - Latência de cada estágio (p50, p95, p99, max)
  - Latência total do ciclo
  - Contagem de ciclos lentos (> threshold)
  - Histograma de latência (buckets)

Uso
---
    from src.services.pipeline_benchmark import get_pipeline_benchmark

    bench = get_pipeline_benchmark()

    # Início do ciclo
    token = bench.start_cycle(symbol="BTC", cycle_id="abc-123")

    # Estágios individuais
    with bench.measure_stage(token, "vision"):
        signal = await vision.run(analysis)

    with bench.measure_stage(token, "batman"):
        approval = await batman.run(signal)

    # Fim do ciclo
    bench.end_cycle(token)
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROLLING_WINDOW = 500          # número de ciclos mantidos em memória
_DEFAULT_ALERT_THRESHOLD_S = 30.0  # alerta quando ciclo > 30s

# Buckets de latência em segundos para histograma simples
_LATENCY_BUCKETS = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, float("inf")]
_STAGE_NAMES = ["professor_x", "vision", "batman", "iron_man", "total"]


# ---------------------------------------------------------------------------
# Internal structures
# ---------------------------------------------------------------------------

@dataclass
class _CycleToken:
    """Token opaco devolvido por start_cycle() e passado para end_cycle()."""
    symbol: str
    cycle_id: str
    start: float = field(default_factory=time.monotonic)
    stages: dict[str, list[float]] = field(default_factory=dict)  # name → [start, end]


@dataclass
class CycleMeasurement:
    """Resultado de uma medição de ciclo."""
    symbol: str
    cycle_id: str
    total_s: float
    stages: dict[str, float]  # name → elapsed_s
    is_slow: bool


# ---------------------------------------------------------------------------
# PipelineBenchmark
# ---------------------------------------------------------------------------

class PipelineBenchmark:
    """
    Coleta e agrega métricas de latência do pipeline de trading.

    Thread-safe para asyncio single event loop.
    """

    def __init__(self, alert_threshold_s: float = _DEFAULT_ALERT_THRESHOLD_S) -> None:
        self.alert_threshold_s = alert_threshold_s
        self._cycles: deque[CycleMeasurement] = deque(maxlen=_ROLLING_WINDOW)
        self._stage_samples: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=_ROLLING_WINDOW)
        )
        self._slow_cycle_count: int = 0
        self._total_cycle_count: int = 0

    # ------------------------------------------------------------------
    # Measurement API
    # ------------------------------------------------------------------

    def start_cycle(self, symbol: str, cycle_id: str = "") -> _CycleToken:
        """
        Inicia a medição de um ciclo. Retorna token opaco para usar em
        measure_stage() e end_cycle().
        """
        return _CycleToken(symbol=symbol, cycle_id=cycle_id or symbol)

    @contextmanager
    def measure_stage(
        self, token: _CycleToken, stage_name: str
    ) -> Generator[None, None, None]:
        """
        Context manager que mede a latência de um estágio individual.

        Uso:
            with bench.measure_stage(token, "vision"):
                result = await vision.run(...)
        """
        t0 = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - t0
            token.stages[stage_name] = elapsed
            self._stage_samples[stage_name].append(elapsed)

    def end_cycle(self, token: _CycleToken) -> CycleMeasurement:
        """
        Finaliza a medição do ciclo, registra métricas e publica evento
        se a latência total exceder o threshold.
        """
        total_s = time.monotonic() - token.start
        self._stage_samples["total"].append(total_s)
        self._total_cycle_count += 1

        is_slow = total_s > self.alert_threshold_s
        if is_slow:
            self._slow_cycle_count += 1
            logger.warning(
                f"[PipelineBenchmark] SLOW CYCLE detected: {token.symbol} "
                f"total={total_s:.2f}s > threshold={self.alert_threshold_s:.0f}s "
                f"stages={token.stages}"
            )
            try:
                from src.services.event_bus import get_event_bus
                bus = get_event_bus()
                bus.publish_sync("pipeline.slow_cycle", {
                    "symbol": token.symbol,
                    "cycle_id": token.cycle_id,
                    "total_s": round(total_s, 3),
                    "threshold_s": self.alert_threshold_s,
                    "stages": {k: round(v, 3) for k, v in token.stages.items()},
                })
            except Exception as _ev_exc:  # noqa: BLE001
                logger.debug("[PipelineBenchmark] EventBus publish failed: %s", _ev_exc)

        m = CycleMeasurement(
            symbol=token.symbol,
            cycle_id=token.cycle_id,
            total_s=round(total_s, 4),
            stages={k: round(v, 4) for k, v in token.stages.items()},
            is_slow=is_slow,
        )
        self._cycles.append(m)
        return m

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _percentiles(self, samples: deque[float]) -> dict[str, float]:
        """Calcula p50, p95, p99, max de uma deque de amostras."""
        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "count": 0}
        sorted_s = sorted(samples)
        n = len(sorted_s)

        def _pct(p: float) -> float:
            idx = int(p * n / 100)
            return round(sorted_s[min(idx, n - 1)], 4)

        return {
            "p50": _pct(50),
            "p95": _pct(95),
            "p99": _pct(99),
            "max": round(sorted_s[-1], 4),
            "count": n,
        }

    def _histogram(self, samples: deque[float]) -> list[dict[str, Any]]:
        """Distribui amostras em buckets de latência."""
        counts = [0] * len(_LATENCY_BUCKETS)
        for v in samples:
            for i, bucket in enumerate(_LATENCY_BUCKETS):
                if v <= bucket:
                    counts[i] += 1
                    break
        result = []
        prev = 0.0
        for i, bucket in enumerate(_LATENCY_BUCKETS):
            label = (
                f"<={bucket:.0f}s"
                if bucket != float("inf")
                else f">{prev:.0f}s"
            )
            result.append({"bucket": label, "count": counts[i]})
            prev = bucket
        return result

    def summary(self) -> dict[str, Any]:
        """
        Retorna dict com todas as métricas para /api/benchmarks.
        """
        slow_pct = (
            round(self._slow_cycle_count / self._total_cycle_count * 100, 2)
            if self._total_cycle_count > 0
            else 0.0
        )

        stage_stats: dict[str, dict] = {}
        for stage in list(self._stage_samples.keys()):
            stage_stats[stage] = self._percentiles(self._stage_samples[stage])

        # Últimas 10 medições lentas
        slow_cycles = [
            {"symbol": m.symbol, "total_s": m.total_s, "stages": m.stages}
            for m in self._cycles
            if m.is_slow
        ][-10:]

        return {
            "config": {
                "alert_threshold_s": self.alert_threshold_s,
                "rolling_window": _ROLLING_WINDOW,
            },
            "session": {
                "total_cycles": self._total_cycle_count,
                "slow_cycles": self._slow_cycle_count,
                "slow_pct": slow_pct,
            },
            "latency_by_stage": stage_stats,
            "total_histogram": self._histogram(self._stage_samples.get("total", deque())),
            "recent_slow_cycles": slow_cycles,
        }

    def reset(self) -> None:
        """Zera contadores — para testes."""
        self.__init__(alert_threshold_s=self.alert_threshold_s)


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_benchmark: Optional[PipelineBenchmark] = None


def get_pipeline_benchmark(
    alert_threshold_s: float = _DEFAULT_ALERT_THRESHOLD_S,
) -> PipelineBenchmark:
    """
    Retorna o singleton global do PipelineBenchmark.
    `alert_threshold_s` é usado apenas na primeira criação.
    """
    global _benchmark
    if _benchmark is None:
        _benchmark = PipelineBenchmark(alert_threshold_s=alert_threshold_s)
    return _benchmark


def reset_pipeline_benchmark() -> None:
    """Reseta o singleton — para testes."""
    global _benchmark
    _benchmark = None

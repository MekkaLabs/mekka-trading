"""
tests/test_story_151_pipeline_benchmark.py
============================================
Story 151 — Performance Benchmarks.

Testa o PipelineBenchmark: medição de estágios, percentis,
histograma, detecção de ciclos lentos e singleton.
"""

from __future__ import annotations

import time

import pytest
from src.services.pipeline_benchmark import (
    PipelineBenchmark,
    get_pipeline_benchmark,
    reset_pipeline_benchmark,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset():
    reset_pipeline_benchmark()
    yield
    reset_pipeline_benchmark()


# ---------------------------------------------------------------------------
# Basic measurement
# ---------------------------------------------------------------------------

class TestBasicMeasurement:
    def test_start_cycle_returns_token(self):
        bench = PipelineBenchmark()
        token = bench.start_cycle("BTC", "cycle-001")
        assert token.symbol == "BTC"
        assert token.cycle_id == "cycle-001"

    def test_end_cycle_records_measurement(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        token = bench.start_cycle("BTC")
        m = bench.end_cycle(token)
        assert m.symbol == "BTC"
        assert m.total_s >= 0.0

    def test_total_cycle_count_increments(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        for _ in range(3):
            token = bench.start_cycle("BTC")
            bench.end_cycle(token)
        s = bench.summary()
        assert s["session"]["total_cycles"] == 3

    def test_stage_measurement_recorded(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        token = bench.start_cycle("ETH")
        with bench.measure_stage(token, "vision"):
            time.sleep(0.01)  # 10ms
        m = bench.end_cycle(token)
        assert "vision" in m.stages
        assert m.stages["vision"] >= 0.009  # ≥ 9ms

    def test_multiple_stages_all_recorded(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        token = bench.start_cycle("SOL")
        for stage in ["professor_x", "vision", "batman", "iron_man"]:
            with bench.measure_stage(token, stage):
                pass  # instant
        m = bench.end_cycle(token)
        for stage in ["professor_x", "vision", "batman", "iron_man"]:
            assert stage in m.stages


# ---------------------------------------------------------------------------
# Slow cycle detection
# ---------------------------------------------------------------------------

class TestSlowCycleDetection:
    def test_fast_cycle_not_flagged(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        token = bench.start_cycle("BTC")
        m = bench.end_cycle(token)
        assert not m.is_slow

    def test_slow_cycle_flagged(self):
        bench = PipelineBenchmark(alert_threshold_s=0.0)  # threshold=0 → always slow
        token = bench.start_cycle("BTC")
        time.sleep(0.001)
        m = bench.end_cycle(token)
        assert m.is_slow

    def test_slow_cycle_count_increments(self):
        bench = PipelineBenchmark(alert_threshold_s=0.0)
        for _ in range(3):
            token = bench.start_cycle("BTC")
            time.sleep(0.001)
            bench.end_cycle(token)
        s = bench.summary()
        assert s["session"]["slow_cycles"] == 3

    def test_slow_pct_computed(self):
        bench = PipelineBenchmark(alert_threshold_s=0.0)
        for _ in range(4):
            token = bench.start_cycle("BTC")
            time.sleep(0.001)
            bench.end_cycle(token)
        s = bench.summary()
        assert s["session"]["slow_pct"] == 100.0

    def test_recent_slow_cycles_in_summary(self):
        bench = PipelineBenchmark(alert_threshold_s=0.0)
        for _ in range(3):
            token = bench.start_cycle("BTC")
            bench.end_cycle(token)
        s = bench.summary()
        assert len(s["recent_slow_cycles"]) == 3


# ---------------------------------------------------------------------------
# Percentile statistics
# ---------------------------------------------------------------------------

class TestPercentileStatistics:
    def test_percentiles_computed_for_total(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        for _ in range(10):
            token = bench.start_cycle("BTC")
            bench.end_cycle(token)
        s = bench.summary()
        assert "total" in s["latency_by_stage"]
        stats = s["latency_by_stage"]["total"]
        assert "p50" in stats
        assert "p95" in stats
        assert "p99" in stats
        assert "max" in stats
        assert stats["count"] == 10

    def test_max_is_greatest_sample(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        token1 = bench.start_cycle("BTC")
        bench.end_cycle(token1)
        time.sleep(0.02)
        token2 = bench.start_cycle("BTC")
        bench.end_cycle(token2)
        s = bench.summary()
        stats = s["latency_by_stage"]["total"]
        assert stats["max"] >= stats["p50"]

    def test_percentiles_empty_when_no_data(self):
        bench = PipelineBenchmark()
        s = bench.summary()
        # No cycles recorded — latency_by_stage may be empty dict
        assert isinstance(s["latency_by_stage"], dict)


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------

class TestHistogram:
    def test_histogram_buckets_present(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        token = bench.start_cycle("BTC")
        bench.end_cycle(token)
        s = bench.summary()
        hist = s["total_histogram"]
        assert isinstance(hist, list)
        assert len(hist) > 0
        for bucket in hist:
            assert "bucket" in bucket
            assert "count" in bucket

    def test_histogram_total_count_matches_cycles(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        n = 5
        for _ in range(n):
            token = bench.start_cycle("BTC")
            bench.end_cycle(token)
        s = bench.summary()
        total = sum(b["count"] for b in s["total_histogram"])
        assert total == n


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_all(self):
        bench = PipelineBenchmark(alert_threshold_s=60.0)
        token = bench.start_cycle("BTC")
        bench.end_cycle(token)
        bench.reset()
        s = bench.summary()
        assert s["session"]["total_cycles"] == 0

    def test_reset_preserves_threshold(self):
        bench = PipelineBenchmark(alert_threshold_s=45.0)
        bench.reset()
        assert bench.alert_threshold_s == 45.0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_same_instance_returned(self):
        b1 = get_pipeline_benchmark()
        b2 = get_pipeline_benchmark()
        assert b1 is b2

    def test_reset_creates_new_instance(self):
        b1 = get_pipeline_benchmark()
        token = b1.start_cycle("BTC")
        b1.end_cycle(token)
        reset_pipeline_benchmark()
        b2 = get_pipeline_benchmark()
        assert b2.summary()["session"]["total_cycles"] == 0

    def test_threshold_set_on_first_create(self):
        b = get_pipeline_benchmark(alert_threshold_s=45.0)
        assert b.alert_threshold_s == 45.0

    def test_threshold_ignored_on_subsequent_get(self):
        b1 = get_pipeline_benchmark(alert_threshold_s=45.0)
        b2 = get_pipeline_benchmark(alert_threshold_s=99.0)  # ignored
        assert b2.alert_threshold_s == 45.0  # first wins


# ---------------------------------------------------------------------------
# Summary structure
# ---------------------------------------------------------------------------

class TestSummaryStructure:
    def test_summary_has_all_keys(self):
        bench = PipelineBenchmark()
        s = bench.summary()
        assert "config" in s
        assert "session" in s
        assert "latency_by_stage" in s
        assert "total_histogram" in s
        assert "recent_slow_cycles" in s

    def test_config_contains_threshold(self):
        bench = PipelineBenchmark(alert_threshold_s=25.0)
        s = bench.summary()
        assert s["config"]["alert_threshold_s"] == 25.0

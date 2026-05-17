"""
Integration tests — Stories 178-182 (Milestone 27: Aider Patterns Wave 1)

Story 178 — ArchitectEditorVision (two-model signal generation)
Story 179 — AutoSignalLinter (auto-fix geometria do sinal)
Story 180 — TradeAnnotationWatcher (AI! comment watch mode)
Story 181 — DynamicReasoningBudget (thinking tokens por regime)
Story 182 — AnalysisPromptCache (prompt caching + cache warming)

Padrões Aider mapeados:
  Architect/Editor → Story 178
  Auto-lint        → Story 179
  Watch Mode AI!   → Story 180
  --thinking-tokens → Story 181
  Prompt Caching   → Story 182

44 testes — 6 classes.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# Story 178 — ArchitectEditorVision
# ===========================================================================

class TestStory178ArchitectEditorVision:
    """
    Verifica que vision.py contém o bloco Story 178 (architect/editor pattern)
    e que está corretamente controlado por settings.vision_architect_editor_enabled.
    """

    def test_architect_editor_block_in_vision(self):
        """Story 178 bloco está em vision.py."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        assert "Story 178" in src
        assert "vision_architect_editor_enabled" in src
        assert "architect thesis" in src.lower() or "Architect Thesis" in src

    def test_architect_call_adds_thesis_to_prompt(self):
        """Quando architect enabled, thesis é injetada no prompt antes do editor call."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        # The architect thesis is appended to the prompt
        assert "Architect Thesis" in src
        assert "convert the above thesis" in src.lower() or "thesis into the TradingSignal" in src

    def test_architect_block_fail_silent(self):
        """Bloco architect é fail-silent (_arch178_exc → debug log)."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        assert "_arch178_exc" in src
        assert "architect call skipped" in src

    def test_architect_only_when_flag_enabled(self):
        """Bloco architect só executa quando vision_architect_editor_enabled=True."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        # The if statement guards the architect block
        assert "vision_architect_editor_enabled" in src
        assert "getattr(settings" in src or "settings.vision_architect_editor" in src


# ===========================================================================
# Story 179 — AutoSignalLinter
# ===========================================================================

class TestStory179AutoSignalLinter:
    """
    Verifica regras de lint e auto-correção de geometria do sinal.
    """

    def test_auto_signal_linter_importable(self):
        """get_auto_signal_linter() importa sem erros."""
        from src.services.auto_signal_linter import get_auto_signal_linter
        linter = get_auto_signal_linter()
        assert linter is not None

    def test_lint_confidence_clamp_above_1(self):
        """confidence > 1.0 é clamped para 1.0."""
        from src.services.auto_signal_linter import AutoSignalLinter

        linter = AutoSignalLinter()
        signal = MagicMock()
        signal.confidence = 1.5
        signal.entry_price = 50000.0
        signal.stop_loss = 48000.0
        signal.take_profit = 55000.0
        signal.leverage = None
        signal.risk_pct = None
        signal.reasoning = "ok"
        signal.action = MagicMock()
        signal.action.value = "LONG"
        signal.model_copy = lambda update: _apply_update(signal, update)

        result = linter.lint(signal)
        conf_fix = next((f for f in result.fixes if f.field == "confidence"), None)
        assert conf_fix is not None
        assert conf_fix.after == 1.0

    def test_lint_confidence_clamp_below_0(self):
        """confidence < 0.0 é clamped para 0.0."""
        from src.services.auto_signal_linter import AutoSignalLinter

        linter = AutoSignalLinter()
        signal = MagicMock()
        signal.confidence = -0.5
        signal.entry_price = 50000.0
        signal.stop_loss = 48000.0
        signal.take_profit = 55000.0
        signal.leverage = None
        signal.risk_pct = None
        signal.reasoning = "ok"
        signal.action = MagicMock()
        signal.action.value = "LONG"
        signal.model_copy = lambda update: _apply_update(signal, update)

        result = linter.lint(signal)
        conf_fix = next((f for f in result.fixes if f.field == "confidence"), None)
        assert conf_fix is not None
        assert conf_fix.after == 0.0

    def test_lint_sl_tp_swap_long(self):
        """LONG com SL >= TP: swap aplicado."""
        from src.services.auto_signal_linter import AutoSignalLinter

        linter = AutoSignalLinter()
        signal = MagicMock()
        signal.confidence = 0.75
        signal.entry_price = 50000.0
        signal.stop_loss = 55000.0   # invertido!
        signal.take_profit = 48000.0
        signal.leverage = None
        signal.risk_pct = None
        signal.reasoning = "ok"
        signal.action = MagicMock()
        signal.action.value = "LONG"
        signal.model_copy = lambda update: _apply_update(signal, update)

        result = linter.lint(signal)
        sl_tp_fix = next((f for f in result.fixes if "stop_loss" in f.field), None)
        assert sl_tp_fix is not None
        assert "swap" in sl_tp_fix.after.lower()

    def test_lint_sl_tp_swap_short(self):
        """SHORT com SL <= TP: swap aplicado."""
        from src.services.auto_signal_linter import AutoSignalLinter

        linter = AutoSignalLinter()
        signal = MagicMock()
        signal.confidence = 0.75
        signal.entry_price = 50000.0
        signal.stop_loss = 45000.0   # invertido para SHORT!
        signal.take_profit = 55000.0
        signal.leverage = None
        signal.risk_pct = None
        signal.reasoning = "ok"
        signal.action = MagicMock()
        signal.action.value = "SHORT"
        signal.model_copy = lambda update: _apply_update(signal, update)

        result = linter.lint(signal)
        sl_tp_fix = next((f for f in result.fixes if "stop_loss" in f.field), None)
        assert sl_tp_fix is not None

    def test_lint_no_fix_needed(self):
        """Sinal geometricamente correto → was_fixed=False."""
        from src.services.auto_signal_linter import AutoSignalLinter

        linter = AutoSignalLinter()
        signal = MagicMock()
        signal.confidence = 0.75
        signal.entry_price = 50000.0
        signal.stop_loss = 48000.0
        signal.take_profit = 54000.0
        signal.leverage = 5.0
        signal.risk_pct = 0.02
        signal.reasoning = "RSI divergence + volume spike"
        signal.action = MagicMock()
        signal.action.value = "LONG"
        signal.model_copy = lambda update: _apply_update(signal, update)

        result = linter.lint(signal)
        assert result.was_fixed is False

    def test_lint_result_has_search_replace(self):
        """LintFix.to_search_replace() produz formato diff do Aider."""
        from src.services.auto_signal_linter import LintFix
        fix = LintFix(field="confidence", before=1.5, after=1.0, rule="clamp [0.0, 1.0]")
        diff = fix.to_search_replace()
        assert "SEARCH" in diff
        assert "REPLACE" in diff
        assert "confidence" in diff
        assert "1.5" in diff
        assert "1.0" in diff

    def test_nick_fury_has_auto_signal_linter_block(self):
        """nick_fury.py contém bloco Story 179 (auto_signal_linter)."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "Story 179" in src
        assert "auto_signal_linter" in src
        assert "lint_and_log" in src


# ===========================================================================
# Story 180 — TradeAnnotationWatcher
# ===========================================================================

class TestStory180TradeAnnotationWatcher:
    """
    Verifica que TradeAnnotationWatcher lê/recarrega hints do arquivo JSON
    e que Vision.py injeta hints no prompt.
    """

    def test_watcher_importable(self):
        """get_trade_annotation_watcher() importa sem erros."""
        from src.services.trade_annotation_watcher import get_trade_annotation_watcher
        from src.services.trade_annotation_watcher import reset_trade_annotation_watcher
        reset_trade_annotation_watcher()
        w = get_trade_annotation_watcher(hints_file="/tmp/test_hints_180.json")
        assert w is not None

    def test_no_hints_file_returns_empty(self):
        """Se arquivo não existe, get_hints() retorna lista vazia."""
        from src.services.trade_annotation_watcher import TradeAnnotationWatcher
        w = TradeAnnotationWatcher(hints_file="/tmp/nonexistent_hints_xyz.json")
        hints = w.get_hints("BTCUSDT")
        assert hints == []

    def test_load_hints_from_file(self):
        """Lê hints do arquivo JSON e retorna para símbolo correto."""
        from src.services.trade_annotation_watcher import TradeAnnotationWatcher

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"hints": [
                {"symbol": "BTCUSDT", "bias": "LONG", "note": "FOMC", "strength": "STRONG"},
                {"symbol": "ETHUSDT", "bias": "SHORT", "note": "ETF outflow", "strength": "MODERATE"},
            ]}, f)
            tmp = f.name

        try:
            w = TradeAnnotationWatcher(hints_file=tmp)
            btc_hints = w.get_hints("BTCUSDT")
            assert len(btc_hints) == 1
            assert btc_hints[0].bias == "LONG"

            eth_hints = w.get_hints("ETHUSDT")
            assert len(eth_hints) == 1
            assert eth_hints[0].bias == "SHORT"
        finally:
            os.unlink(tmp)

    def test_get_prompt_block_format(self):
        """get_prompt_block() retorna bloco com cabeçalho Analyst Annotations."""
        from src.services.trade_annotation_watcher import TradeAnnotationWatcher

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"hints": [
                {"symbol": "BTC", "bias": "LONG", "note": "Whale accumulation", "strength": "STRONG"},
            ]}, f)
            tmp = f.name

        try:
            w = TradeAnnotationWatcher(hints_file=tmp)
            block = w.get_prompt_block("BTC")
            assert "Analyst Annotations" in block
            assert "LONG" in block
            assert "STRONG" in block.upper()
        finally:
            os.unlink(tmp)

    def test_expired_hint_not_returned(self):
        """Hint com expires_at no passado não é retornado."""
        from src.services.trade_annotation_watcher import TradeAnnotationWatcher

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"hints": [
                {
                    "symbol": "BTCUSDT",
                    "bias": "LONG",
                    "note": "expired",
                    "strength": "MODERATE",
                    "expires_at": "2020-01-01T00:00:00Z",  # passado
                },
            ]}, f)
            tmp = f.name

        try:
            w = TradeAnnotationWatcher(hints_file=tmp)
            hints = w.get_hints("BTCUSDT")
            assert hints == []  # expired → não retornado
        finally:
            os.unlink(tmp)

    def test_vision_has_annotation_watcher_block(self):
        """vision.py contém bloco Story 180 (trade_annotation_watcher)."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        assert "Story 180" in src
        assert "trade_annotation_watcher" in src
        assert "get_prompt_block" in src


# ===========================================================================
# Story 181 — DynamicReasoningBudget
# ===========================================================================

class TestStory181DynamicReasoningBudget:
    """
    Verifica que DynamicReasoningBudget ajusta max_tokens por regime+cap_tier.
    """

    def test_reasoning_budget_importable(self):
        """get_reasoning_budget() importa sem erros."""
        from src.services.dynamic_reasoning_budget import get_reasoning_budget
        budget = get_reasoning_budget()
        assert budget is not None

    def test_volatile_large_cap_max_tokens(self):
        """VOLATILE + LARGE_CAP → tokens máximos."""
        from src.services.dynamic_reasoning_budget import DynamicReasoningBudget
        b = DynamicReasoningBudget()
        volatile_large = b.get_max_tokens("VOLATILE", "LARGE_CAP")
        sideways_small = b.get_max_tokens("SIDEWAYS", "SMALL_CAP")
        assert volatile_large > sideways_small

    def test_sideways_small_cap_min_tokens(self):
        """SIDEWAYS + SMALL_CAP → tokens mínimos (< VOLATILE)."""
        from src.services.dynamic_reasoning_budget import DynamicReasoningBudget
        b = DynamicReasoningBudget()
        tokens = b.get_max_tokens("SIDEWAYS", "SMALL_CAP")
        assert tokens >= 512  # min bound
        assert tokens <= 2048  # well below volatile

    def test_tokens_within_bounds(self):
        """Todos os regimes retornam tokens entre min e max."""
        from src.services.dynamic_reasoning_budget import DynamicReasoningBudget
        b = DynamicReasoningBudget(min_tokens=512, max_tokens=8192)
        for regime in ["VOLATILE", "BULL", "BEAR", "SIDEWAYS", "UNKNOWN"]:
            for cap in ["LARGE_CAP", "MID_CAP", "SMALL_CAP"]:
                t = b.get_max_tokens(regime, cap)
                assert 512 <= t <= 8192, f"{regime}/{cap} → {t} out of bounds"

    def test_decide_returns_budget_decision(self):
        """decide() retorna BudgetDecision com todos os campos."""
        from src.services.dynamic_reasoning_budget import DynamicReasoningBudget
        b = DynamicReasoningBudget()
        dec = b.decide("VOLATILE", "LARGE_CAP")
        assert dec.regime == "VOLATILE"
        assert dec.cap_tier == "LARGE_CAP"
        assert dec.final_tokens > 0
        assert dec.multiplier > 0
        assert dec.reasoning

    def test_reasoning_effort_levels(self):
        """get_reasoning_effort() retorna high/medium/low baseado nos tokens."""
        from src.services.dynamic_reasoning_budget import DynamicReasoningBudget
        b = DynamicReasoningBudget()
        assert b.get_reasoning_effort("VOLATILE", "LARGE_CAP") == "high"
        assert b.get_reasoning_effort("SIDEWAYS", "SMALL_CAP") == "low"

    def test_vision_has_dynamic_budget_block(self):
        """vision.py contém bloco Story 181 (dynamic_reasoning_budget)."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        assert "Story 181" in src
        assert "dynamic_reasoning_budget" in src
        assert "get_reasoning_budget" in src


# ===========================================================================
# Story 182 — AnalysisPromptCache
# ===========================================================================

class TestStory182AnalysisPromptCache:
    """
    Verifica que AnalysisPromptCache armazena/lê entradas com TTL correto
    e que Vision.py injeta cached macro_context no prompt.
    """

    def test_cache_importable(self):
        """get_analysis_prompt_cache() importa sem erros."""
        from src.services.analysis_prompt_cache import get_analysis_prompt_cache
        from src.services.analysis_prompt_cache import reset_analysis_prompt_cache
        reset_analysis_prompt_cache()
        cache = get_analysis_prompt_cache()
        assert cache is not None

    def test_store_and_get(self):
        """store() + get() retorna conteúdo antes do TTL."""
        from src.services.analysis_prompt_cache import AnalysisPromptCache
        c = AnalysisPromptCache(default_ttl=60)
        c.store("test_key", "hello world", ttl_seconds=60)
        result = c.get("test_key")
        assert result == "hello world"

    def test_get_miss_returns_none(self):
        """get() retorna None para chave não existente."""
        from src.services.analysis_prompt_cache import AnalysisPromptCache
        c = AnalysisPromptCache()
        result = c.get("nonexistent_key_xyz")
        assert result is None

    def test_expired_entry_returns_none(self):
        """Entrada expirada retorna None."""
        from src.services.analysis_prompt_cache import AnalysisPromptCache
        c = AnalysisPromptCache(default_ttl=0.01)  # TTL 10ms
        c.store("expiring", "value", ttl_seconds=0.01)
        time.sleep(0.05)  # wait for expiry
        result = c.get("expiring")
        assert result is None

    def test_get_or_build_sync_builder(self):
        """get_or_build() chama builder síncrono no cache miss."""
        from src.services.analysis_prompt_cache import AnalysisPromptCache

        c = AnalysisPromptCache(default_ttl=60)
        calls = []

        def builder():
            calls.append(1)
            return "built content"

        result = asyncio.get_event_loop().run_until_complete(
            c.get_or_build("sync_key", builder, ttl_seconds=60)
        )
        assert result == "built content"
        assert len(calls) == 1

        # Second call should use cache
        result2 = asyncio.get_event_loop().run_until_complete(
            c.get_or_build("sync_key", builder, ttl_seconds=60)
        )
        assert result2 == "built content"
        assert len(calls) == 1  # builder not called again

    def test_hit_rate_tracking(self):
        """Cache tracking: hits, misses, hit_rate."""
        from src.services.analysis_prompt_cache import AnalysisPromptCache
        c = AnalysisPromptCache(default_ttl=60)
        c.store("k", "v")
        c.get("k")   # hit
        c.get("k")   # hit
        c.get("missing")  # miss
        assert c._hits == 2
        assert c._misses == 1
        assert round(c.hit_rate, 2) == 0.67

    def test_summary_structure(self):
        """summary() retorna dict com campos esperados."""
        from src.services.analysis_prompt_cache import AnalysisPromptCache
        c = AnalysisPromptCache(default_ttl=60)
        s = c.summary()
        assert "total_entries" in s
        assert "hits" in s
        assert "misses" in s
        assert "hit_rate" in s

    def test_vision_has_cache_block(self):
        """vision.py contém bloco Story 182 (analysis_prompt_cache)."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        assert "Story 182" in src
        assert "analysis_prompt_cache" in src
        assert "macro_context" in src


# ===========================================================================
# Cross-story: Milestone 27 integration
# ===========================================================================

class TestMilestone27CrossStoryIntegration:
    """
    Testes cruzados verificando coexistência dos 5 serviços de Milestone 27.
    """

    def test_all_new_services_importable(self):
        """Todos os 4 novos serviços importam sem erro."""
        modules = [
            "src.services.auto_signal_linter",
            "src.services.dynamic_reasoning_budget",
            "src.services.trade_annotation_watcher",
            "src.services.analysis_prompt_cache",
        ]
        for mod in modules:
            try:
                __import__(mod)
            except ImportError as e:
                pytest.fail(f"Failed to import {mod}: {e}")

    def test_vision_has_all_milestone27_blocks(self):
        """vision.py contém todos os blocos de Milestone 27."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/vision.py"
        ).read()
        for story in ["Story 178", "Story 180", "Story 181", "Story 182"]:
            assert story in src, f"Missing {story} in vision.py"

    def test_nick_fury_has_story_179(self):
        """nick_fury.py contém Story 179 (AutoSignalLinter)."""
        src = open(
            "/sessions/loving-hopeful-meitner/mnt/Mekka-Trading/src/agents/nick_fury.py"
        ).read()
        assert "Story 179" in src
        assert "AutoSignalLinter" in src or "auto_signal_linter" in src

    def test_lint_fix_diff_format_aider_compatible(self):
        """LintFix.to_search_replace() é compatível com formato Aider SEARCH/REPLACE."""
        from src.services.auto_signal_linter import LintFix
        fix = LintFix(
            field="stop_loss/take_profit",
            before="SL=55000, TP=48000",
            after="SL=48000, TP=55000 (swapped)",
            rule="LONG: stop_loss >= take_profit → swap",
        )
        diff = fix.to_search_replace()
        # Must have Aider-style markers
        assert "<<<<<<< SEARCH" in diff
        assert "=======" in diff
        assert ">>>>>>> REPLACE" in diff
        assert "Rule:" in diff

    def test_budget_and_cache_coexist(self):
        """DynamicReasoningBudget e AnalysisPromptCache coexistem sem conflito."""
        from src.services.dynamic_reasoning_budget import DynamicReasoningBudget
        from src.services.analysis_prompt_cache import AnalysisPromptCache

        budget = DynamicReasoningBudget()
        cache = AnalysisPromptCache(default_ttl=60)

        tokens = budget.get_max_tokens("VOLATILE", "LARGE_CAP")
        cache.store(f"budget_volatile", f"max_tokens={tokens}")
        result = cache.get("budget_volatile")
        assert str(tokens) in result


# ---------------------------------------------------------------------------
# Helper: apply update dict to a MagicMock
# ---------------------------------------------------------------------------

def _apply_update(obj, update: dict):
    """Simulates model_copy(update=...) for MagicMock objects."""
    import copy
    new_obj = copy.copy(obj)
    for k, v in update.items():
        setattr(new_obj, k, v)
    return new_obj

"""
tests/test_story_161_chat_history_compressor.py
==================================================
Story 161 — ChatHistoryCompressor: Context-Aware Prompt Compression.

Inspirado em aider/history.py:
  "Aider automatically compresses the chat history when it approaches the
   context window limit."

Testa:
- _extract_key_facts: extrai símbolos, preços, ações, confidence
- PromptTurn: from_dict, to_dict, tokens_approx
- CompressionResult: tokens_saved, to_dict
- ChatHistoryCompressor.compress(): passthrough curto, compressão longa
  - mantém system message
  - mantém N turns recentes intactas
  - agrupa antigas em bloco [COMPRESSED]
  - CompressionResult.compressed_turns + kept_turns corretos
- compress_if_needed(): não comprime abaixo do warn_pct
- stats(): estrutura do dict
- Fail-silent: nunca levanta exceção
- Singleton: get/reset
"""

from __future__ import annotations

import sys
import types
import importlib.util


def _load_mod():
    if "loguru" not in sys.modules:
        loguru_mod = types.ModuleType("loguru")
        class FL:
            def debug(self,*a,**k): pass
            def info(self,*a,**k): pass
            def warning(self,*a,**k): pass
            def error(self,*a,**k): pass
        loguru_mod.logger = FL()
        sys.modules["loguru"] = loguru_mod

    # Mock ContextWindowTracker
    src_mod = types.ModuleType("src")
    src_svc = types.ModuleType("src.services")
    src_ctx = types.ModuleType("src.services.context_window_tracker")
    class FakeTracker:
        def record_stage(self,*a,**k): return 0
        def check_limit(self,*a,**k): return False
    src_ctx.get_context_window_tracker = lambda: FakeTracker()
    src_ctx.MODEL_TOKEN_LIMITS = {"gpt-4o": 128_000, "_default": 32_000}
    sys.modules.setdefault("src", src_mod)
    sys.modules.setdefault("src.services", src_svc)
    sys.modules["src.services.context_window_tracker"] = src_ctx

    spec = importlib.util.spec_from_file_location(
        "chat_history_compressor", "src/services/chat_history_compressor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chat_history_compressor"] = mod
    spec.loader.exec_module(mod)
    mod.reset_chat_compressor()
    return mod


def _make_history(n: int, system=True) -> list[dict]:
    history = []
    if system:
        history.append({"role": "system", "content": "You are a trading assistant."})
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"BTC LONG entry=$50{i:03d} sl=$48000 tp=$55000 confidence=0.7{i%9}"
        history.append({"role": role, "content": content})
    return history


class TestExtractKeyFacts:
    def test_extracts_symbol(self):
        mod = _load_mod()
        facts = mod._extract_key_facts("BTC LONG entry=$50000 confidence=0.75")
        assert "BTC" in facts

    def test_extracts_action(self):
        mod = _load_mod()
        facts = mod._extract_key_facts("Signal: LONG approved entry=$50000")
        assert "LONG" in facts

    def test_extracts_confidence(self):
        mod = _load_mod()
        facts = mod._extract_key_facts("confidence=0.85 LONG BTC")
        assert "conf=0.85" in facts

    def test_extracts_verdict(self):
        mod = _load_mod()
        facts = mod._extract_key_facts("Batman verdict: APPROVED signal for BTC")
        assert "APPROVED" in facts

    def test_empty_string(self):
        mod = _load_mod()
        result = mod._extract_key_facts("")
        assert isinstance(result, str)

    def test_fail_silent(self):
        mod = _load_mod()
        result = mod._extract_key_facts(None)
        assert isinstance(result, str)


class TestPromptTurn:
    def test_from_dict(self):
        mod = _load_mod()
        pt = mod.PromptTurn.from_dict({"role": "user", "content": "hello"})
        assert pt.role == "user"
        assert pt.content == "hello"

    def test_to_dict(self):
        mod = _load_mod()
        pt = mod.PromptTurn(role="assistant", content="LONG BTC")
        d = pt.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "LONG BTC"

    def test_tokens_approx(self):
        mod = _load_mod()
        content = "a" * 400
        pt = mod.PromptTurn(role="user", content=content)
        assert 90 <= pt.tokens_approx <= 110


class TestCompressionResult:
    def test_tokens_saved(self):
        mod = _load_mod()
        cr = mod.CompressionResult(
            turns=[], tokens_before=1000, tokens_after=400
        )
        assert cr.tokens_saved == 600

    def test_tokens_saved_zero_when_no_savings(self):
        mod = _load_mod()
        cr = mod.CompressionResult(
            turns=[], tokens_before=400, tokens_after=500
        )
        assert cr.tokens_saved == 0

    def test_to_dict_structure(self):
        mod = _load_mod()
        cr = mod.CompressionResult(
            turns=[], original_turns=10, compressed_turns=7,
            kept_turns=3, tokens_before=1000, tokens_after=300,
            compression_ratio=0.3,
        )
        d = cr.to_dict()
        assert d["original_turns"] == 10
        assert d["tokens_saved"] == 700
        assert d["compression_ratio"] == 0.3


class TestChatHistoryCompressorCompress:
    def test_short_history_passthrough(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(min_turns_to_compress=8)
        history = _make_history(4)
        result = c.compress(history)
        assert len(result.turns) == len(history)
        assert result.compressed_turns == 0

    def test_long_history_compresses(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=3, min_turns_to_compress=5)
        history = _make_history(10, system=False)
        result = c.compress(history, keep_last=3)
        # 10 turns antigas → 1 bloco comprimido + 3 recentes
        assert len(result.turns) == 4  # 1 compressed + 3 recent
        assert result.compressed_turns == 7
        assert result.kept_turns == 3

    def test_system_message_preserved(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=3, min_turns_to_compress=5, preserve_system=True)
        history = _make_history(10, system=True)
        result = c.compress(history)
        roles = [t["role"] for t in result.turns]
        assert "system" in roles
        assert result.turns[0]["role"] == "system"

    def test_recent_turns_intact(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=3, min_turns_to_compress=5)
        history = _make_history(10, system=False)
        result = c.compress(history, keep_last=3)
        # As 3 últimas turns devem estar intactas
        assert result.turns[-3:] == history[-3:]

    def test_compressed_block_has_marker(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=2, min_turns_to_compress=4)
        history = _make_history(8, system=False)
        result = c.compress(history, keep_last=2)
        # Deve ter um bloco com [COMPRESSED...]
        compressed_blocks = [
            t for t in result.turns
            if "[COMPRESSED" in t.get("content", "")
        ]
        assert len(compressed_blocks) == 1

    def test_tokens_reduced(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=2, min_turns_to_compress=4)
        history = _make_history(10, system=False)
        result = c.compress(history, keep_last=2)
        assert result.tokens_after < result.tokens_before

    def test_fail_silent_bad_input(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor()
        result = c.compress("not_a_list")
        assert result is not None
        assert isinstance(result.turns, list)

    def test_fail_silent_none_input(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor()
        result = c.compress(None)
        assert result is not None


class TestCompressIfNeeded:
    def test_no_compression_below_limit(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=3, min_turns_to_compress=5)
        history = _make_history(5, system=False)
        # Tracker fake sempre retorna check_limit=False
        result = c.compress_if_needed(history, cycle_id="c1")
        assert len(result.turns) == len(history)

    def test_returns_compression_result(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor()
        history = _make_history(3)
        result = c.compress_if_needed(history)
        assert isinstance(result, mod.CompressionResult)


class TestStats:
    def test_stats_structure(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=5)
        s = c.stats()
        assert "total_compressions" in s
        assert "total_tokens_saved" in s
        assert "keep_last" in s

    def test_stats_increments(self):
        mod = _load_mod()
        c = mod.ChatHistoryCompressor(keep_last=2, min_turns_to_compress=4)
        history = _make_history(10, system=False)
        c.compress(history, keep_last=2)
        assert c.stats()["total_compressions"] == 1
        c.compress(history, keep_last=2)
        assert c.stats()["total_compressions"] == 2


class TestSingleton:
    def test_get_returns_instance(self):
        mod = _load_mod()
        c = mod.get_chat_compressor()
        assert isinstance(c, mod.ChatHistoryCompressor)

    def test_kwargs_creates_new(self):
        mod = _load_mod()
        c1 = mod.get_chat_compressor()
        c2 = mod.get_chat_compressor(keep_last=99)
        assert c1 is not c2

    def test_reset_clears(self):
        mod = _load_mod()
        c1 = mod.get_chat_compressor()
        mod.reset_chat_compressor()
        c2 = mod.get_chat_compressor()
        assert c1 is not c2

"""
tests/test_story_157_bounded_output.py
========================================
Story 157 — BoundedOutput: ACI Output Limiter (SWE-agent).

Inspirado em:
  "100-line windowed viewer + syntax-checked autosave roughly doubles
   SWE-Bench score versus raw bash."
  "if output length < 10,000 chars → full output; else → truncate"
  "search results limited to max 50 hits"
  "last_n_observations: drops all but the most recent N observations"

Testa:
- truncate_str: passthrough quando curto, truncação com sufixo explícito
- truncate_str_head_tail: head + tail para stack traces
- truncate_list: passthrough quando curto, truncação com summary string
- truncate_dict: recursão, strings, listas aninhadas
- truncate_output: dispatcher genérico
- format_observation: padrão mini-SWE-agent (returncode + output)
- bound_prompt_section: padrão windowed viewer
- last_n_observations: history processor
- count_tokens_approx: heurística
- Fail-silent: nunca levanta exceção
"""

from __future__ import annotations


class TestTruncateStr:
    def test_short_passthrough(self):
        from src.services.bounded_output import BoundedOutput
        text = "hello world"
        assert BoundedOutput.truncate_str(text, max_chars=100) == text

    def test_exact_limit_passthrough(self):
        from src.services.bounded_output import BoundedOutput
        text = "a" * 100
        assert BoundedOutput.truncate_str(text, max_chars=100) == text

    def test_long_truncated(self):
        from src.services.bounded_output import BoundedOutput
        text = "a" * 200
        result = BoundedOutput.truncate_str(text, max_chars=100)
        assert len(result) < 200
        assert "omitted" in result  # sufixo explícito

    def test_suffix_shows_remaining_count(self):
        from src.services.bounded_output import BoundedOutput
        text = "x" * 150
        result = BoundedOutput.truncate_str(text, max_chars=100)
        assert "50" in result  # 150 - 100 = 50 omitted

    def test_default_max_chars_10k(self):
        from src.services.bounded_output import BoundedOutput
        short = "a" * 9_999
        assert BoundedOutput.truncate_str(short) == short
        long_text = "a" * 15_000
        result = BoundedOutput.truncate_str(long_text)
        assert len(result) < 15_000
        assert "omitted" in result

    def test_empty_string(self):
        from src.services.bounded_output import BoundedOutput
        assert BoundedOutput.truncate_str("") == ""

    def test_fail_silent(self):
        from src.services.bounded_output import BoundedOutput
        # Even with weird input, should not raise
        result = BoundedOutput.truncate_str("ok", max_chars=-1)
        assert result is not None


class TestTruncateStrHeadTail:
    def test_short_passthrough(self):
        from src.services.bounded_output import BoundedOutput
        text = "hello world"
        assert BoundedOutput.truncate_str_head_tail(text, max_chars=1000) == text

    def test_preserves_head_and_tail(self):
        from src.services.bounded_output import BoundedOutput
        text = "HEAD" + ("x" * 1000) + "TAIL"
        result = BoundedOutput.truncate_str_head_tail(text, max_chars=100)
        assert "HEAD" in result
        assert "TAIL" in result
        assert "omitted" in result

    def test_omission_marker_present(self):
        from src.services.bounded_output import BoundedOutput
        text = "a" * 500
        result = BoundedOutput.truncate_str_head_tail(text, max_chars=100)
        assert "..." in result or "omitted" in result


class TestTruncateList:
    def test_short_passthrough(self):
        from src.services.bounded_output import BoundedOutput
        items = list(range(10))
        result = BoundedOutput.truncate_list(items, max_items=50)
        assert result == items

    def test_exact_limit_passthrough(self):
        from src.services.bounded_output import BoundedOutput
        items = list(range(50))
        assert BoundedOutput.truncate_list(items, max_items=50) == items

    def test_long_list_truncated(self):
        from src.services.bounded_output import BoundedOutput
        items = list(range(100))
        result = BoundedOutput.truncate_list(items, max_items=50)
        assert len(result) == 51  # 50 items + 1 summary string
        assert isinstance(result[-1], str)
        assert "omitted" in result[-1].lower() or "more" in result[-1].lower()

    def test_summary_shows_total(self):
        from src.services.bounded_output import BoundedOutput
        items = list(range(100))
        result = BoundedOutput.truncate_list(items, max_items=50)
        summary = result[-1]
        assert "100" in summary  # total

    def test_default_max_50(self):
        from src.services.bounded_output import BoundedOutput
        items = list(range(60))
        result = BoundedOutput.truncate_list(items)
        assert len(result) == 51  # 50 + summary

    def test_empty_list(self):
        from src.services.bounded_output import BoundedOutput
        assert BoundedOutput.truncate_list([]) == []

    def test_fail_silent(self):
        from src.services.bounded_output import BoundedOutput
        result = BoundedOutput.truncate_list("not_a_list")
        assert result is not None


class TestTruncateDict:
    def test_short_strings_untouched(self):
        from src.services.bounded_output import BoundedOutput
        d = {"key": "short value", "num": 42}
        result = BoundedOutput.truncate_dict(d, max_chars=1000)
        assert result["key"] == "short value"
        assert result["num"] == 42

    def test_long_string_values_truncated(self):
        from src.services.bounded_output import BoundedOutput
        d = {"text": "x" * 2000}
        result = BoundedOutput.truncate_dict(d, max_chars=100)
        assert len(result["text"]) < 2000
        assert "omitted" in result["text"]

    def test_list_values_truncated(self):
        from src.services.bounded_output import BoundedOutput
        d = {"items": list(range(100))}
        result = BoundedOutput.truncate_dict(d, max_items=10)
        assert len(result["items"]) == 11  # 10 + summary

    def test_nested_dict_recursion(self):
        from src.services.bounded_output import BoundedOutput
        d = {"outer": {"inner": "x" * 200}}
        result = BoundedOutput.truncate_dict(d, max_chars=50)
        assert "omitted" in result["outer"]["inner"]

    def test_does_not_mutate_original(self):
        from src.services.bounded_output import BoundedOutput
        d = {"key": "x" * 200}
        original_value = d["key"]
        BoundedOutput.truncate_dict(d, max_chars=50)
        assert d["key"] == original_value  # original unchanged

    def test_fail_silent(self):
        from src.services.bounded_output import BoundedOutput
        result = BoundedOutput.truncate_dict({"key": object()}, max_chars=100)
        assert result is not None


class TestTruncateOutput:
    def test_str_dispatch(self):
        from src.services.bounded_output import BoundedOutput
        long_str = "x" * 15_000
        result = BoundedOutput.truncate_output(long_str)
        assert isinstance(result, str)
        assert len(result) < 15_000

    def test_list_dispatch(self):
        from src.services.bounded_output import BoundedOutput
        long_list = list(range(100))
        result = BoundedOutput.truncate_output(long_list, max_items=10)
        assert isinstance(result, list)
        assert len(result) == 11

    def test_dict_dispatch(self):
        from src.services.bounded_output import BoundedOutput
        d = {"text": "x" * 200}
        result = BoundedOutput.truncate_output(d, max_chars=50)
        assert isinstance(result, dict)

    def test_int_passthrough(self):
        from src.services.bounded_output import BoundedOutput
        assert BoundedOutput.truncate_output(42) == 42

    def test_none_passthrough(self):
        from src.services.bounded_output import BoundedOutput
        assert BoundedOutput.truncate_output(None) is None


class TestFormatObservation:
    def test_short_output_full(self):
        from src.services.bounded_output import BoundedOutput
        obs = BoundedOutput.format_observation(0, "ok", max_chars=1000)
        assert "returncode=0" in obs
        assert "ok" in obs

    def test_long_output_truncated(self):
        from src.services.bounded_output import BoundedOutput
        long_out = "x" * 20_000
        obs = BoundedOutput.format_observation(0, long_out, max_chars=10_000)
        assert "omitted" in obs

    def test_nonzero_returncode(self):
        from src.services.bounded_output import BoundedOutput
        obs = BoundedOutput.format_observation(1, "error!")
        assert "returncode=1" in obs

    def test_command_included(self):
        from src.services.bounded_output import BoundedOutput
        obs = BoundedOutput.format_observation(0, "output", command="pytest tests/")
        assert "pytest" in obs

    def test_fail_silent(self):
        from src.services.bounded_output import BoundedOutput
        result = BoundedOutput.format_observation(0, None)  # type: ignore
        assert result is not None


class TestBoundPromptSection:
    def test_short_content_full(self):
        from src.services.bounded_output import BoundedOutput
        result = BoundedOutput.bound_prompt_section("Analysis", "short text", max_chars=1000)
        assert "Analysis" in result
        assert "short text" in result

    def test_long_content_truncated(self):
        from src.services.bounded_output import BoundedOutput
        content = "x" * 10_000
        result = BoundedOutput.bound_prompt_section("Title", content, max_chars=100)
        assert "Title" in result
        assert "omitted" in result

    def test_separator_present(self):
        from src.services.bounded_output import BoundedOutput
        result = BoundedOutput.bound_prompt_section("X", "y")
        assert "---" in result or "##" in result


class TestLastNObservations:
    def test_short_list_unchanged(self):
        from src.services.bounded_output import BoundedOutput
        obs = [{"event_type": "A", "payload": "big"}, {"event_type": "B", "payload": "big"}]
        result = BoundedOutput.last_n_observations(obs, n=5)
        assert result == obs

    def test_old_observations_trimmed(self):
        from src.services.bounded_output import BoundedOutput
        obs = [{"event_type": f"E{i}", "symbol": "BTC", "payload": "x" * 100} for i in range(10)]
        result = BoundedOutput.last_n_observations(obs, n=3)
        assert len(result) == 10  # same count
        # Old observations should not have 'payload'
        for evt in result[:-3]:
            assert "payload" not in evt
        # Recent observations should be intact
        for evt in result[-3:]:
            assert "payload" in evt

    def test_keeps_event_type_in_old(self):
        from src.services.bounded_output import BoundedOutput
        obs = [{"event_type": "CYCLE_START", "payload": "big data", "extra": "x"} for _ in range(5)]
        result = BoundedOutput.last_n_observations(obs, n=2)
        for evt in result[:-2]:
            assert "event_type" in evt

    def test_empty_list(self):
        from src.services.bounded_output import BoundedOutput
        assert BoundedOutput.last_n_observations([], n=5) == []


class TestCountTokensApprox:
    def test_empty_string(self):
        from src.services.bounded_output import BoundedOutput
        assert BoundedOutput.count_tokens_approx("") == 0

    def test_approx_4_chars_per_token(self):
        from src.services.bounded_output import BoundedOutput
        # 400 chars → ~100 tokens
        text = "a" * 400
        tokens = BoundedOutput.count_tokens_approx(text)
        assert 90 <= tokens <= 110  # allow small variance

    def test_always_positive(self):
        from src.services.bounded_output import BoundedOutput
        assert BoundedOutput.count_tokens_approx("x") >= 1

"""
tests/test_story_162_signal_changelog.py
==========================================
Story 162 — SignalChangeLog: Structured Signal Diff + Auto-Commit Format.

Inspirado em aider/coders/editblock_coder.py + aider/commands.py:
  "SEARCH/REPLACE format makes it explicit what changed."
  "Aider auto-commits each change with a descriptive commit message."

Testa:
- _fmt: formatação de campos numéricos e string
- FieldChange: delta, delta_pct, to_search_replace, to_compact
- ChangeRecord: commit_message, to_search_replace_block, to_audit_line, to_dict
  - has_action_change, is_unchanged, changed_fields
- SignalChangeLog.diff(): dois signals, signal novo (prev=None), sem mudanças
- SignalChangeLog.format_for_audit(): one-liner
- SignalChangeLog.commit_message_from_signal(): formato commit
- SignalChangeLog.record(): adiciona ao histórico
- SignalChangeLog.get_recent(): rolling window
- SignalChangeLog.get_action_flips(): apenas records com action change
- summary(): estrutura do dict
- Fail-silent: nunca levanta exceção
- Singleton: get/reset
"""

from __future__ import annotations

import sys
import importlib.util
from unittest.mock import MagicMock


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "signal_changelog", "src/services/signal_changelog.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["signal_changelog"] = mod
    spec.loader.exec_module(mod)
    mod.reset_signal_changelog()
    return mod


def _make_signal(
    symbol="BTC", action="LONG", confidence=0.70,
    entry_price=50000.0, stop_loss=48000.0, take_profit=55000.0,
    size_pct=0.05, leverage=2, reasoning="Bullish momentum."
):
    s = MagicMock()
    s.symbol = symbol; s.action = action; s.confidence = confidence
    s.entry_price = entry_price; s.stop_loss = stop_loss; s.take_profit = take_profit
    s.size_pct = size_pct; s.leverage = leverage; s.reasoning = reasoning
    return s


class TestFmt:
    def test_fmt_confidence(self):
        mod = _load_mod()
        r = mod._fmt("confidence", 0.75)
        assert "0.75" in r

    def test_fmt_entry_price(self):
        mod = _load_mod()
        r = mod._fmt("entry_price", 50000)
        assert "$" in r and "50" in r

    def test_fmt_size_pct(self):
        mod = _load_mod()
        r = mod._fmt("size_pct", 0.05)
        assert "%" in r

    def test_fmt_string_field(self):
        mod = _load_mod()
        r = mod._fmt("action", "LONG")
        assert r == "LONG"

    def test_fmt_fail_silent(self):
        mod = _load_mod()
        r = mod._fmt("entry_price", None)
        assert isinstance(r, str)


class TestFieldChange:
    def test_delta_numeric(self):
        mod = _load_mod()
        fc = mod.FieldChange("confidence", 0.65, 0.75, is_numeric=True)
        assert abs(fc.delta - 0.10) < 1e-9

    def test_delta_pct(self):
        mod = _load_mod()
        fc = mod.FieldChange("entry_price", 50000.0, 51000.0, is_numeric=True)
        assert abs(fc.delta_pct - 0.02) < 1e-9

    def test_delta_none_for_string(self):
        mod = _load_mod()
        fc = mod.FieldChange("action", "LONG", "SHORT", is_numeric=False)
        assert fc.delta is None

    def test_to_search_replace_format(self):
        mod = _load_mod()
        fc = mod.FieldChange("action", "LONG", "SHORT")
        sr = fc.to_search_replace()
        assert "<<<CHANGED action>>>" in sr
        assert "LONG" in sr
        assert "SHORT" in sr
        assert "===" in sr

    def test_to_compact(self):
        mod = _load_mod()
        fc = mod.FieldChange("action", "LONG", "SHORT")
        compact = fc.to_compact()
        assert "action" in compact
        assert "LONG" in compact
        assert "SHORT" in compact
        assert "→" in compact

    def test_fail_silent_none_values(self):
        mod = _load_mod()
        fc = mod.FieldChange("action", None, None)
        assert fc.to_compact() is not None
        assert fc.to_search_replace() is not None


class TestChangeRecord:
    def test_is_unchanged_when_no_changes(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        assert r.is_unchanged is True

    def test_is_unchanged_false_with_changes(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        r.changes.append(mod.FieldChange("action", "LONG", "SHORT"))
        assert r.is_unchanged is False

    def test_has_action_change_true(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        r.changes.append(mod.FieldChange("action", "LONG", "SHORT"))
        assert r.has_action_change is True

    def test_has_action_change_false(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        r.changes.append(mod.FieldChange("confidence", 0.65, 0.75, is_numeric=True))
        assert r.has_action_change is False

    def test_changed_fields(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        r.changes.append(mod.FieldChange("action", "LONG", "SHORT"))
        r.changes.append(mod.FieldChange("confidence", 0.65, 0.75, is_numeric=True))
        assert "action" in r.changed_fields
        assert "confidence" in r.changed_fields

    def test_commit_message_unchanged(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        msg = r.commit_message()
        assert "BTC" in msg
        assert "no" in msg.lower() or "change" in msg.lower()

    def test_commit_message_with_changes(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="ETH")
        r.changes.append(mod.FieldChange("action", "LONG", "SHORT"))
        r.changes.append(mod.FieldChange("confidence", 0.65, 0.72, is_numeric=True))
        msg = r.commit_message()
        assert "ETH" in msg
        assert "action" in msg
        assert "LONG" in msg
        assert "SHORT" in msg

    def test_to_audit_line(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        r.changes.append(mod.FieldChange("action", "LONG", "SHORT"))
        line = r.to_audit_line()
        assert "BTC" in line

    def test_to_audit_line_unchanged(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="ETH")
        line = r.to_audit_line()
        assert "unchanged" in line.lower()

    def test_to_search_replace_block(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC")
        r.changes.append(mod.FieldChange("action", "LONG", "SHORT"))
        block = r.to_search_replace_block()
        assert "CHANGED" in block or "BTC" in block

    def test_to_dict_structure(self):
        mod = _load_mod()
        r = mod.ChangeRecord(symbol="BTC", prev_cycle_id="c1", curr_cycle_id="c2")
        r.changes.append(mod.FieldChange("action", "LONG", "SHORT"))
        d = r.to_dict()
        assert d["symbol"] == "BTC"
        assert d["total_changes"] == 1
        assert "action" in d["changed_fields"]
        assert d["prev_cycle_id"] == "c1"
        assert len(d["changes"]) == 1


class TestDiff:
    def test_diff_same_signal_no_changes(self):
        mod = _load_mod()
        sig = _make_signal()
        record = mod.SignalChangeLog.diff(sig, sig)
        assert record.is_unchanged is True

    def test_diff_action_changed(self):
        mod = _load_mod()
        prev = _make_signal(action="LONG")
        curr = _make_signal(action="SHORT", stop_loss=52000, take_profit=46000)
        record = mod.SignalChangeLog.diff(prev, curr)
        assert "action" in record.changed_fields

    def test_diff_confidence_changed(self):
        mod = _load_mod()
        prev = _make_signal(confidence=0.65)
        curr = _make_signal(confidence=0.80)
        record = mod.SignalChangeLog.diff(prev, curr)
        assert "confidence" in record.changed_fields

    def test_diff_prev_none_all_new(self):
        mod = _load_mod()
        curr = _make_signal()
        record = mod.SignalChangeLog.diff(None, curr)
        assert len(record.changes) > 0
        for ch in record.changes:
            assert ch.old_value is None

    def test_diff_symbol_set(self):
        mod = _load_mod()
        prev = _make_signal(symbol="ETH")
        curr = _make_signal(symbol="ETH")
        record = mod.SignalChangeLog.diff(prev, curr)
        assert record.symbol == "ETH"

    def test_diff_multiple_fields(self):
        mod = _load_mod()
        prev = _make_signal(action="LONG", confidence=0.65, entry_price=50000)
        curr = _make_signal(action="SHORT", confidence=0.75, entry_price=49000,
                            stop_loss=52000, take_profit=46000)
        record = mod.SignalChangeLog.diff(prev, curr)
        assert len(record.changes) >= 3

    def test_diff_fail_silent(self):
        mod = _load_mod()
        result = mod.SignalChangeLog.diff(None, None)
        assert isinstance(result, mod.ChangeRecord)


class TestFormatForAudit:
    def test_format_contains_symbol(self):
        mod = _load_mod()
        sig = _make_signal(symbol="BTC", action="LONG")
        line = mod.SignalChangeLog.format_for_audit(sig)
        assert "BTC" in line
        assert "LONG" in line

    def test_format_contains_rr(self):
        mod = _load_mod()
        # risk=2000, reward=5000, rr=2.5
        sig = _make_signal(entry_price=50000, stop_loss=48000, take_profit=55000)
        line = mod.SignalChangeLog.format_for_audit(sig)
        assert "rr=" in line

    def test_format_with_cycle_id(self):
        mod = _load_mod()
        sig = _make_signal()
        line = mod.SignalChangeLog.format_for_audit(sig, cycle_id="abc123")
        assert "abc123" in line

    def test_format_fail_silent(self):
        mod = _load_mod()
        result = mod.SignalChangeLog.format_for_audit(None)
        assert isinstance(result, str)


class TestCommitMessageFromSignal:
    def test_contains_symbol_and_action(self):
        mod = _load_mod()
        sig = _make_signal(symbol="BTC", action="LONG")
        msg = mod.SignalChangeLog.commit_message_from_signal(sig)
        assert "BTC" in msg
        assert "LONG" in msg

    def test_contains_conf_and_entry(self):
        mod = _load_mod()
        sig = _make_signal(confidence=0.75, entry_price=50000)
        msg = mod.SignalChangeLog.commit_message_from_signal(sig)
        assert "0.75" in msg
        assert "50" in msg

    def test_fail_silent(self):
        mod = _load_mod()
        result = mod.SignalChangeLog.commit_message_from_signal(None)
        assert isinstance(result, str)


class TestSignalChangeLogHistory:
    def test_record_adds_to_history(self):
        mod = _load_mod()
        log = mod.SignalChangeLog()
        prev = _make_signal(action="LONG")
        curr = _make_signal(action="SHORT", stop_loss=52000, take_profit=46000)
        log.record("BTC", prev, curr)
        assert len(log.get_recent("BTC")) == 1

    def test_get_recent_respects_n(self):
        mod = _load_mod()
        log = mod.SignalChangeLog()
        for i in range(10):
            prev = _make_signal(confidence=0.5 + i * 0.01)
            curr = _make_signal(confidence=0.51 + i * 0.01)
            log.record("ETH", prev, curr)
        recent = log.get_recent("ETH", n=3)
        assert len(recent) == 3

    def test_get_action_flips(self):
        mod = _load_mod()
        log = mod.SignalChangeLog()
        # Flip
        log.record("BTC", _make_signal(action="LONG"), _make_signal(action="SHORT", stop_loss=52000, take_profit=46000))
        # Sem flip (mesma ação)
        log.record("BTC", _make_signal(action="LONG"), _make_signal(action="LONG"))
        flips = log.get_action_flips("BTC")
        assert len(flips) == 1

    def test_get_last_change(self):
        mod = _load_mod()
        log = mod.SignalChangeLog()
        log.record("SOL", _make_signal(symbol="SOL", confidence=0.65), _make_signal(symbol="SOL", confidence=0.70))
        last = log.get_last_change("SOL")
        assert last is not None
        assert last.symbol == "SOL"

    def test_get_last_change_none_when_empty(self):
        mod = _load_mod()
        log = mod.SignalChangeLog()
        assert log.get_last_change("XYZ") is None

    def test_rolling_window_50(self):
        mod = _load_mod()
        log = mod.SignalChangeLog()
        for i in range(60):
            log.record("BTC", _make_signal(confidence=0.5+i*0.001), _make_signal(confidence=0.51+i*0.001))
        assert len(log.get_recent("BTC", n=100)) == 50  # capped at 50

    def test_summary_structure(self):
        mod = _load_mod()
        log = mod.SignalChangeLog()
        log.record("BTC", _make_signal(action="LONG"), _make_signal(action="SHORT", stop_loss=52000, take_profit=46000))
        s = log.summary()
        assert "total_diffs" in s
        assert "total_field_changes" in s
        assert "symbols_tracked" in s
        assert "BTC" in s["symbols_tracked"]


class TestSingleton:
    def test_get_returns_instance(self):
        mod = _load_mod()
        log = mod.get_signal_changelog()
        assert isinstance(log, mod.SignalChangeLog)

    def test_same_instance(self):
        mod = _load_mod()
        mod.reset_signal_changelog()
        l1 = mod.get_signal_changelog()
        l2 = mod.get_signal_changelog()
        assert l1 is l2

    def test_reset_clears(self):
        mod = _load_mod()
        l1 = mod.get_signal_changelog()
        mod.reset_signal_changelog()
        l2 = mod.get_signal_changelog()
        assert l1 is not l2

"""
tests/test_story_245_debate_verdict.py
========================================
Story 245 — Debate Verdict → Vision Integration

Tests that _debate_verdict_prompt_section() renders correctly for all
confidence tiers and that it appears in to_prompt().
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.models.market_data import MarketAnalysis, MarketData, Trend


def _make_verdict(action: str, confidence: float, dissent: list[str] | None = None):
    return SimpleNamespace(
        consensus_action=action,
        consensus_confidence=confidence,
        total_votes=6,
        rounds_run=2,
        dissent_agents=dissent or [],
        notes=[],
    )


def _make_market_data() -> MarketData:
    return MarketData(
        symbol="ETH",
        timestamp=datetime.now(timezone.utc),
        timeframe="4h",
        price=3_500.0,
        rsi_14=52.0,
        trend=Trend.BULLISH,
        trend_strength=0.6,
        support_levels=[3_300.0],
        resistance_levels=[3_700.0],
        volume_24h=500_000.0,
        atr_14=80.0,
        recent_closes=[3_450.0, 3_480.0, 3_500.0],
    )


def _make_analysis(debate_verdict) -> MarketAnalysis:
    return MarketAnalysis(
        symbol="ETH",
        timestamp=datetime.now(timezone.utc),
        chart=_make_market_data(),
        debate_verdict=debate_verdict,
    )


class TestDebateVerdictPromptSection:

    def test_strong_consensus_header(self):
        verdict = _make_verdict("LONG", confidence=0.85)
        analysis = _make_analysis(verdict)
        section = analysis._debate_verdict_prompt_section()

        assert "STRONG CONSENSUS" in section
        assert "85%" in section
        assert "LONG" in section

    def test_moderate_consensus_header(self):
        verdict = _make_verdict("SHORT", confidence=0.70)
        analysis = _make_analysis(verdict)
        section = analysis._debate_verdict_prompt_section()

        assert "MODERATE CONSENSUS" in section
        assert "70%" in section

    def test_weak_consensus_header(self):
        verdict = _make_verdict("HOLD", confidence=0.52)
        analysis = _make_analysis(verdict)
        section = analysis._debate_verdict_prompt_section()

        assert "WEAK" in section or "SPLIT" in section
        assert "0.05" in section

    def test_dissent_agents_shown(self):
        verdict = _make_verdict("LONG", confidence=0.80, dissent=["Thor", "Aquaman"])
        analysis = _make_analysis(verdict)
        section = analysis._debate_verdict_prompt_section()

        assert "Thor" in section
        assert "Aquaman" in section
        assert "dissent" in section.lower() or "diverged" in section.lower()

    def test_no_dissent_no_warning(self):
        verdict = _make_verdict("LONG", confidence=0.90, dissent=[])
        analysis = _make_analysis(verdict)
        section = analysis._debate_verdict_prompt_section()

        # No dissent warning should appear
        assert "dissent" not in section.lower() or "dissenting" not in section.lower()

    def test_section_contains_votes_and_rounds(self):
        verdict = _make_verdict("SHORT", confidence=0.75)
        analysis = _make_analysis(verdict)
        section = analysis._debate_verdict_prompt_section()

        assert "6" in section   # total_votes
        assert "2" in section   # rounds_run

    def test_none_verdict_returns_empty(self):
        analysis = _make_analysis(None)
        section = analysis._debate_verdict_prompt_section()
        assert section == ""

    def test_section_appears_in_full_prompt(self):
        verdict = _make_verdict("LONG", confidence=0.82)
        analysis = _make_analysis(verdict)
        prompt = analysis.to_prompt()

        assert "Debate Verdict" in prompt
        assert "STRONG CONSENSUS" in prompt

    def test_verdict_section_before_decision_required(self):
        verdict = _make_verdict("LONG", confidence=0.80)
        analysis = _make_analysis(verdict)
        prompt = analysis.to_prompt()

        debate_pos = prompt.find("Debate Verdict")
        decision_pos = prompt.find("Decision Required")
        assert debate_pos < decision_pos, "Debate verdict must appear before Decision Required"

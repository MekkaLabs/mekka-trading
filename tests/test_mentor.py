"""Tests — Mentor (T1 closing learning loop, 2026-05-25).

Mentor distills resolved outcomes + recent rejections + drawdown proximity
into typed ParameterSuggestion. Conservative bias: only tightenings get
``can_auto_apply=True``; loosenings always require human review.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.mentor import (
    Mentor,
    MentorReport,
    ParameterSuggestion,
    _LOW_WIN_RATE_THRESHOLD,
    _MIN_TRADES_FOR_LEARNING,
)


@pytest.fixture
def silent_io(monkeypatch):
    """Stub out external IO so unit tests don't touch the real DB / audit."""
    async def _no_audit(*args, **kwargs):
        return None

    async def _empty_audits(*args, **kwargs):
        return []

    async def _no_drawdown():
        return 0.0

    monkeypatch.setattr(
        "src.persistence.repository.MekkaRepository.log_event", _no_audit
    )
    monkeypatch.setattr(
        "src.persistence.repository.MekkaRepository.list_recent_audit", _empty_audits
    )
    monkeypatch.setattr(
        "src.persistence.repository.MekkaRepository.get_today_drawdown_pct",
        _no_drawdown,
    )
    return monkeypatch


@pytest.mark.asyncio
async def test_no_data_produces_no_suggestions(silent_io):
    """No resolved outcomes + no rejections + no drawdown → empty report."""
    with patch.object(
        Mentor, "_collect_winrate_evidence", AsyncMock(return_value={"n": 0, "win_rate": None})
    ), patch.object(
        Mentor, "_collect_rejection_evidence", AsyncMock(return_value={"n": 0, "rejection_rate": None})
    ), patch.object(
        Mentor, "_collect_drawdown_evidence",
        AsyncMock(return_value={"drawdown_pct": 0.0, "limit_pct": 0.10}),
    ):
        report = await Mentor().run()
    assert report.is_empty
    assert isinstance(report, MentorReport)


@pytest.mark.asyncio
async def test_low_winrate_triggers_tighten_min_confidence(silent_io):
    """Win rate < 35% with enough samples → tighten min_confidence (auto-applicable)."""
    fake_wr = {"n": 20, "wins": 5, "losses": 15, "neutral": 0, "win_rate": 0.25}
    with patch.object(
        Mentor, "_collect_winrate_evidence", AsyncMock(return_value=fake_wr)
    ), patch.object(
        Mentor, "_collect_rejection_evidence", AsyncMock(return_value={"n": 0, "rejection_rate": None})
    ), patch.object(
        Mentor, "_collect_drawdown_evidence",
        AsyncMock(return_value={"drawdown_pct": 0.0, "limit_pct": 0.10}),
    ):
        report = await Mentor().run()
    assert len(report.suggestions) == 1
    s = report.suggestions[0]
    assert s.parameter_name == "min_confidence"
    assert s.direction == "tighten"
    assert s.suggested_value > s.current_value
    assert s.can_auto_apply is True
    assert "win rate" in s.reason.lower()


@pytest.mark.asyncio
async def test_high_winrate_proposes_loosen_but_not_auto(silent_io):
    """Win rate > 65% with N≥20 → suggest loosening, but can_auto_apply=False."""
    fake_wr = {"n": 30, "wins": 22, "losses": 8, "neutral": 0, "win_rate": 22 / 30}
    with patch.object(
        Mentor, "_collect_winrate_evidence", AsyncMock(return_value=fake_wr)
    ), patch.object(
        Mentor, "_collect_rejection_evidence", AsyncMock(return_value={"n": 0, "rejection_rate": None})
    ), patch.object(
        Mentor, "_collect_drawdown_evidence",
        AsyncMock(return_value={"drawdown_pct": 0.0, "limit_pct": 0.10}),
    ):
        report = await Mentor().run()
    s = next((x for x in report.suggestions if x.parameter_name == "min_confidence"), None)
    assert s is not None
    assert s.direction == "loosen"
    assert s.suggested_value < s.current_value
    assert s.can_auto_apply is False  # NEVER auto-loosen


@pytest.mark.asyncio
async def test_below_min_trades_silent(silent_io):
    """Win rate < threshold but N below minimum → no suggestion (not enough data)."""
    fake_wr = {"n": _MIN_TRADES_FOR_LEARNING - 1, "win_rate": 0.20}
    with patch.object(
        Mentor, "_collect_winrate_evidence", AsyncMock(return_value=fake_wr)
    ), patch.object(
        Mentor, "_collect_rejection_evidence", AsyncMock(return_value={"n": 0, "rejection_rate": None})
    ), patch.object(
        Mentor, "_collect_drawdown_evidence",
        AsyncMock(return_value={"drawdown_pct": 0.0, "limit_pct": 0.10}),
    ):
        report = await Mentor().run()
    assert report.is_empty


@pytest.mark.asyncio
async def test_high_rejection_rate_proposes_review(silent_io):
    """Batman rejecting > 80% → suggest loosening (human-only)."""
    fake_rej = {"n": 20, "rejected": 18, "rejection_rate": 0.90}
    with patch.object(
        Mentor, "_collect_winrate_evidence", AsyncMock(return_value={"n": 0, "win_rate": None})
    ), patch.object(
        Mentor, "_collect_rejection_evidence", AsyncMock(return_value=fake_rej)
    ), patch.object(
        Mentor, "_collect_drawdown_evidence",
        AsyncMock(return_value={"drawdown_pct": 0.0, "limit_pct": 0.10}),
    ):
        report = await Mentor().run()
    s = next((x for x in report.suggestions if x.parameter_name == "min_confidence"), None)
    assert s is not None
    assert s.direction == "loosen"
    assert s.can_auto_apply is False
    assert "batman" in s.reason.lower()


@pytest.mark.asyncio
async def test_drawdown_near_limit_proposes_tighter_cap(silent_io):
    """Drawdown ≥ 70% of daily limit → tighten max_daily_drawdown_pct."""
    fake_dd = {"drawdown_pct": 0.08, "limit_pct": 0.10}  # 80% of limit
    with patch.object(
        Mentor, "_collect_winrate_evidence", AsyncMock(return_value={"n": 0, "win_rate": None})
    ), patch.object(
        Mentor, "_collect_rejection_evidence", AsyncMock(return_value={"n": 0, "rejection_rate": None})
    ), patch.object(
        Mentor, "_collect_drawdown_evidence", AsyncMock(return_value=fake_dd)
    ):
        report = await Mentor().run()
    s = next(
        (x for x in report.suggestions if x.parameter_name == "max_daily_drawdown_pct"),
        None,
    )
    assert s is not None
    assert s.direction == "tighten"
    assert s.suggested_value < s.current_value
    assert s.can_auto_apply is True
    # Tightening risk cap should have high confidence
    assert s.confidence >= 0.5


def test_parameter_suggestion_env_line():
    """Suggestion should produce a valid env line for .env paste."""
    s = ParameterSuggestion(
        parameter_name="min_confidence",
        current_value=0.65,
        suggested_value=0.70,
        direction="tighten",
        reason="test",
        evidence={"n": 20},
    )
    line = s.to_env_line()
    assert line == "MEKKA_MIN_CONFIDENCE=0.7"


@pytest.mark.asyncio
async def test_failure_in_one_collector_does_not_block_others(silent_io):
    """If win-rate collector raises, drawdown and rejection still produce suggestions."""
    fake_dd = {"drawdown_pct": 0.08, "limit_pct": 0.10}
    with patch.object(
        Mentor, "_collect_winrate_evidence", AsyncMock(side_effect=RuntimeError("db down"))
    ), patch.object(
        Mentor, "_collect_rejection_evidence", AsyncMock(return_value={"n": 0, "rejection_rate": None})
    ), patch.object(
        Mentor, "_collect_drawdown_evidence", AsyncMock(return_value=fake_dd)
    ):
        report = await Mentor().run()
    # Should still produce the drawdown suggestion despite winrate failure
    names = [s.parameter_name for s in report.suggestions]
    assert "max_daily_drawdown_pct" in names

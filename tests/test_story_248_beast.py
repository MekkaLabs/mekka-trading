"""
tests/test_story_248_beast.py
================================
Story 248 — Beast: Continuous System Improvement Agent

Tests proposal generation from synthetic trade stats and gate data.
All repository calls are mocked — no DB or network access.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.beast import Beast, BeastReport, ImprovementProposal


def _make_trade(pnl: float, symbol: str = "BTC", confidence: float = 0.70):
    return SimpleNamespace(pnl_usd=pnl, symbol=symbol, confidence=confidence)


def _make_event(gate_id: str):
    return SimpleNamespace(payload={"gate_id": gate_id})


class TestBeastProposals:

    @pytest.mark.asyncio
    async def test_low_win_rate_generates_high_priority_proposal(self):
        """Win rate < 45% → HIGH priority proposal."""
        trades = [_make_trade(pnl) for pnl in ([-50, -30, 20, -40, -60, 10, -20, -15, 40, -10])]
        beast = Beast()

        with (
            patch("src.agents.beast.Beast._send_report", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_closed_trades_since",
                  new_callable=AsyncMock, return_value=trades),
            patch("src.persistence.repository.MekkaRepository.get_events_since",
                  new_callable=AsyncMock, return_value=[]),
        ):
            report = await beast.run(period_days=7)

        high = report.high_priority
        assert len(high) >= 1
        titles = [p.title for p in high]
        assert any("Win rate" in t or "win rate" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_good_win_rate_no_win_rate_proposal(self):
        """Win rate ≥ 55% → no win rate proposal."""
        trades = [_make_trade(pnl) for pnl in ([60, 70, 80, 90, 100, -20, 55, 65, 75, 40])]
        beast = Beast()

        with (
            patch("src.agents.beast.Beast._send_report", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_closed_trades_since",
                  new_callable=AsyncMock, return_value=trades),
            patch("src.persistence.repository.MekkaRepository.get_events_since",
                  new_callable=AsyncMock, return_value=[]),
        ):
            report = await beast.run(period_days=7)

        titles = [p.title for p in report.proposals]
        assert not any("Win rate" in t for t in titles)

    @pytest.mark.asyncio
    async def test_gate_concentration_proposal(self):
        """A gate firing >40% of all rejections → MEDIUM proposal."""
        # Gate 3c fires 5 out of 8 times = 62.5%
        events = (
            [_make_event("3c")] * 5
            + [_make_event("3d")] * 2
            + [_make_event("3e")] * 1
        )
        beast = Beast()

        with (
            patch("src.agents.beast.Beast._send_report", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_closed_trades_since",
                  new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_events_since",
                  new_callable=AsyncMock, return_value=events),
        ):
            report = await beast.run(period_days=7)

        gate_proposals = [p for p in report.proposals if "3c" in p.title or "3c" in p.evidence]
        assert len(gate_proposals) >= 1
        assert gate_proposals[0].impact == "MEDIUM"

    @pytest.mark.asyncio
    async def test_no_trades_returns_empty_proposals(self):
        """With zero trades, Beast returns a report with no proposals from trade analysis."""
        beast = Beast()

        with (
            patch("src.agents.beast.Beast._send_report", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_closed_trades_since",
                  new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_events_since",
                  new_callable=AsyncMock, return_value=[]),
        ):
            report = await beast.run(period_days=7)

        # No crash — returns a valid BeastReport
        assert isinstance(report, BeastReport)
        assert report.total_trades_analyzed == 0

    @pytest.mark.asyncio
    async def test_report_sorted_by_priority(self):
        """Proposals are sorted HIGH → MEDIUM → LOW."""
        trades = [_make_trade(pnl) for pnl in ([-50, -30, -40, -60, -10, 20, -20, -15, 40, -25])]
        beast = Beast()

        with (
            patch("src.agents.beast.Beast._send_report", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_closed_trades_since",
                  new_callable=AsyncMock, return_value=trades),
            patch("src.persistence.repository.MekkaRepository.get_events_since",
                  new_callable=AsyncMock, return_value=[]),
        ):
            report = await beast.run(period_days=7)

        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        for i in range(len(report.proposals) - 1):
            assert (
                priority_order[report.proposals[i].impact]
                <= priority_order[report.proposals[i + 1].impact]
            )

    @pytest.mark.asyncio
    async def test_health_score_in_range(self):
        """Health score is always between 0 and 100."""
        beast = Beast()

        with (
            patch("src.agents.beast.Beast._send_report", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_closed_trades_since",
                  new_callable=AsyncMock, return_value=[]),
            patch("src.persistence.repository.MekkaRepository.get_events_since",
                  new_callable=AsyncMock, return_value=[]),
        ):
            report = await beast.run(period_days=7)

        assert 0.0 <= report.system_health_score <= 100.0

    def test_improvement_proposal_telegram_block(self):
        """ImprovementProposal.to_telegram_block() renders correctly."""
        proposal = ImprovementProposal(
            title="Teste",
            description="Descrição de teste",
            impact="HIGH",
            area="signal_quality",
            evidence="Win rate 40%",
            suggested_story="Story 250 — Recalibrar Vision",
        )
        block = proposal.to_telegram_block()
        assert "🔴" in block
        assert "Teste" in block
        assert "Story 250" in block
        assert "signal_quality" in block

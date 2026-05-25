"""Tests — cobertura básica para agentes sem teste dedicado (IMP-e9854bad0a39).

Cobertura mínima para 3 agentes críticos sem teste anterior:
- PortfolioManager (read-only equity snapshot)
- Sage (measurement loop)
- Galactus (premortem specialist)

Cada um com 2-3 testes cobrindo: happy path, fail-silent degradation,
e edge case de input vazio.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Galactus
# ============================================================================


@pytest.mark.asyncio
async def test_galactus_empty_proposals_returns_empty_report():
    """No proposals → empty report, no errors."""
    from src.agents.galactus import Galactus, PremortemReport

    report = await Galactus().run(proposals=[])
    assert isinstance(report, PremortemReport)
    assert len(report.verdicts) == 0
    assert report.errors == []


@pytest.mark.asyncio
async def test_galactus_processes_dict_proposals():
    """Galactus accepts plain dict proposals and returns verdicts."""
    from src.agents.galactus import Galactus

    proposals = [
        {
            "title": "Test proposal A",
            "description": "Synthetic",
            "impact": "HIGH",
            "area": "risk",
            "evidence": "test",
        },
        {
            "title": "Test proposal B",
            "description": "Synthetic 2",
            "impact": "LOW",
            "area": "infra",
            "evidence": "test",
        },
    ]
    report = await Galactus().run(proposals=proposals)
    assert len(report.verdicts) == 2
    titles = {v.proposal_title for v in report.verdicts}
    assert titles == {"Test proposal A", "Test proposal B"}


@pytest.mark.asyncio
async def test_galactus_handles_object_proposals():
    """Galactus accepts non-dict objects with the same fields (duck-typed)."""
    from src.agents.galactus import Galactus

    class FakeProposal:
        title = "Object proposal"
        description = "Synthetic"
        impact = "MEDIUM"
        area = "infra"
        evidence = "test"

    report = await Galactus().run(proposals=[FakeProposal()])
    assert len(report.verdicts) == 1
    assert report.verdicts[0].proposal_title == "Object proposal"


# ============================================================================
# Sage
# ============================================================================


@pytest.fixture
def sage_temp_paths(tmp_path, monkeypatch):
    """Redirect Sage's JSON files to a temp dir."""
    from src.agents import sage

    monkeypatch.setattr(sage, "_BASELINES_FILE", tmp_path / "sage_baselines.json")
    monkeypatch.setattr(
        sage, "_IMPROVEMENT_BASELINES_FILE", tmp_path / "sage_improvement_baselines.json"
    )
    monkeypatch.setattr(sage, "_DECISIONS_FILE", tmp_path / "improvement_decisions.json")
    return tmp_path


@pytest.mark.asyncio
async def test_sage_first_run_only_writes_baseline(sage_temp_paths):
    """First Sage run has no history → returns no proposals."""
    from src.agents.sage import Sage

    with patch.object(
        Sage, "_snapshot", AsyncMock(return_value={
            "ts": "2026-05-25T00:00:00+00:00",
            "win_rate": 0.5,
            "profit_factor": 1.2,
            "closed_trades": 5,
            "errors_24h": 0,
        })
    ):
        props = await Sage().scan()
    assert props == []


def test_sage_kpi_handles_missing_decisions_file(sage_temp_paths):
    """When decisions.json doesn't exist, kpi() must return safe defaults."""
    from src.agents.sage import Sage

    out = Sage().kpi()
    assert out is not None
    assert "accepted" in out
    assert "acceptance_rate" in out
    assert out["accepted"] == 0


def test_sage_improvement_evaluations_handles_missing_files(sage_temp_paths):
    """No improvement baselines → returns empty evaluation, never raises."""
    from src.agents.sage import Sage

    out = Sage().improvement_evaluations()
    assert isinstance(out, dict)


# ============================================================================
# PortfolioManager
# ============================================================================


@pytest.mark.asyncio
async def test_portfolio_manager_paper_fallback_on_exchange_error(monkeypatch):
    """When exchange call raises, PortfolioManager returns a PAPER_FALLBACK
    snapshot rather than blowing up the cycle."""
    from src.agents.portfolio_manager import PortfolioManager
    from src.models.portfolio import EquitySnapshot

    pm = PortfolioManager()
    pm._run_hyperliquid = AsyncMock(side_effect=RuntimeError("hl down"))
    pm._run_ccxt_exchange = AsyncMock(side_effect=RuntimeError("ccxt down"))
    pm._load_cached_snapshot = MagicMock(return_value=None)

    result = await pm._run()
    assert isinstance(result, EquitySnapshot)
    # Source should be PAPER_FALLBACK so consumers know the data is degraded
    assert "FALLBACK" in (result.source or "").upper() or result.source == "PAPER_FALLBACK"


@pytest.mark.asyncio
async def test_portfolio_manager_uses_cache_on_failure(monkeypatch):
    """If exchange fails but cache exists, use the cache instead of fallback."""
    from src.agents.portfolio_manager import PortfolioManager
    from src.models.portfolio import EquitySnapshot

    cached = EquitySnapshot(
        equity_usd=5000.0,
        available_balance_usd=4800.0,
        margin_used_usd=200.0,
        positions=[],
        source="BINANCE",
    )

    pm = PortfolioManager()
    pm._run_hyperliquid = AsyncMock(side_effect=RuntimeError("hl down"))
    pm._run_ccxt_exchange = AsyncMock(side_effect=RuntimeError("ccxt down"))
    pm._load_cached_snapshot = MagicMock(return_value=cached)

    result = await pm._run()
    assert result.equity_usd == 5000.0
    assert result.source == "BINANCE"

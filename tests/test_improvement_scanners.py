"""
tests/test_improvement_scanners.py
==================================
Unit tests for the new Continuous Improvement Department scanners:
CodeAuditor, RiskScanner, OpsScanner, Ice Man, Sage.

Focus on pure logic + fail-silent guarantees that need no live DB/network:
  - version parsing/comparison (Ice Man)
  - path → area mapping (CodeAuditor)
  - regression detection (Sage) — the core measurement loop
  - datetime normalization helpers
  - ImprovementProposal shape contract
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.beast import ImprovementProposal
from src.agents.code_auditor import _area_for_path
from src.agents.ice_man import _parse_ver
from src.agents.risk_scanner import _aware as risk_aware
from src.agents.ops_scanner import _aware as ops_aware
from src.agents.sage import Sage
from pathlib import Path


# ---------------------------------------------------------------------------
# Ice Man — version parsing/comparison
# ---------------------------------------------------------------------------

def test_parse_ver_basic():
    assert _parse_ver("4.5.52") == (4, 5, 52)
    assert _parse_ver("1.0") == (1, 0)
    assert _parse_ver("2.3.4.5") == (2, 3, 4, 5)


def test_parse_ver_handles_garbage():
    # Non-numeric chunks coerce to 0, never raises.
    assert _parse_ver("v4.5.52") == (4, 5, 52)
    assert _parse_ver("") == (0,)
    assert _parse_ver("abc") == (0,)


def test_parse_ver_ordering():
    assert _parse_ver("4.5.54") > _parse_ver("4.5.52")
    assert _parse_ver("5.0.0") > _parse_ver("4.9.9")
    assert _parse_ver("4.5.52") == _parse_ver("4.5.52")


# ---------------------------------------------------------------------------
# CodeAuditor — path → area mapping
# ---------------------------------------------------------------------------

def test_area_for_path_frontend():
    assert _area_for_path(Path("src/dashboard/static/app.js")) == "frontend"
    assert _area_for_path(Path("src/dashboard/static/style.css")) == "frontend"


def test_area_for_path_backend():
    assert _area_for_path(Path("src/dashboard/server.py")) == "backend"
    assert _area_for_path(Path("src/agents/iron_man.py")) == "backend"


# ---------------------------------------------------------------------------
# Datetime normalization (Risk/Ops scanners)
# ---------------------------------------------------------------------------

def test_aware_normalizes_naive():
    naive = datetime(2026, 5, 21, 12, 0, 0)
    for fn in (risk_aware, ops_aware):
        out = fn(naive)
        assert out.tzinfo is not None
        assert out.utcoffset().total_seconds() == 0


def test_aware_passthrough_and_none():
    aware = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    assert risk_aware(aware) == aware
    assert risk_aware(None) is None


# ---------------------------------------------------------------------------
# Sage — regression detection (the measurement loop)
# ---------------------------------------------------------------------------

def _snap(win_rate=None, errors_24h=0, closed_trades=0):
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "win_rate": win_rate, "profit_factor": None,
        "closed_trades": closed_trades, "errors_24h": errors_24h,
    }


def test_sage_first_run_no_proposals():
    # No history → only establish baseline, never propose.
    out = Sage()._detect_regressions(_snap(win_rate=40, closed_trades=20), history=[])
    assert out == []


def test_sage_winrate_regression_flagged():
    history = [_snap(win_rate=60, closed_trades=20) for _ in range(3)]
    cur = _snap(win_rate=45, closed_trades=20)  # 60 → 45 = 15pp drop (> 10pp)
    out = Sage()._detect_regressions(cur, history)
    titles = " ".join(p.title for p in out)
    assert any("win rate" in p.title.lower() for p in out)
    assert any(p.impact == "HIGH" for p in out)


def test_sage_winrate_small_drop_not_flagged():
    history = [_snap(win_rate=60, closed_trades=20) for _ in range(3)]
    cur = _snap(win_rate=55, closed_trades=20)  # only 5pp drop
    out = Sage()._detect_regressions(cur, history)
    assert not any("win rate" in p.title.lower() for p in out)


def test_sage_winrate_ignored_with_few_trades():
    history = [_snap(win_rate=60, closed_trades=20) for _ in range(3)]
    cur = _snap(win_rate=30, closed_trades=3)  # big drop but < min trades
    out = Sage()._detect_regressions(cur, history)
    assert not any("win rate" in p.title.lower() for p in out)


def test_sage_error_spike_flagged():
    history = [_snap(win_rate=50, errors_24h=2, closed_trades=20) for _ in range(3)]
    cur = _snap(win_rate=50, errors_24h=8, closed_trades=20)  # >= 2x base and >= 5
    out = Sage()._detect_regressions(cur, history)
    assert any("erro" in p.title.lower() for p in out)


# ---------------------------------------------------------------------------
# Proposal shape contract
# ---------------------------------------------------------------------------

def test_proposal_shape():
    p = ImprovementProposal(
        title="x", description="d", impact="HIGH", area="research", evidence="e",
    )
    assert p.impact in ("HIGH", "MEDIUM", "LOW")
    assert p.title and p.area and p.evidence
    block = p.to_telegram_block()
    assert "x" in block

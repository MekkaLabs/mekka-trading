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


# ---------------------------------------------------------------------------
# scan() end-to-end — RiskScanner / OpsScanner (com audit_log mockado)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402


class _AuditRow:
    """Fake AuditRecord para alimentar os scanners."""

    def __init__(self, event, severity="INFO", agent="X", payload=None, message="", age_min=1):
        from datetime import timedelta
        self.event = event
        self.severity = severity
        self.agent = agent
        self.payload = payload or {}
        self.message = message
        self.timestamp = datetime.now(timezone.utc) - timedelta(minutes=age_min)


def _patch_audit(rows):
    return patch(
        "src.persistence.repository.MekkaRepository.list_recent_audit",
        AsyncMock(return_value=rows),
    )


@pytest.mark.asyncio
async def test_risk_scanner_flags_repeated_kill_switch():
    from src.agents.risk_scanner import RiskScanner

    rows = [
        _AuditRow("DAILY_DRAWDOWN_KILL_SWITCH", severity="CRITICAL", agent="NickFury"),
        _AuditRow("DAILY_LOSS_USD_KILL_SWITCH", severity="CRITICAL", agent="NickFury"),
    ]
    with _patch_audit(rows), \
         patch("src.agents.batman.is_kill_switch_active", return_value=False):
        out = await RiskScanner()._scan_kill_switch(period_days=7)
    assert len(out) == 1
    assert out[0].area == "risk"
    assert "2" in out[0].title


@pytest.mark.asyncio
async def test_risk_scanner_single_kill_not_flagged():
    from src.agents.risk_scanner import RiskScanner

    rows = [_AuditRow("DAILY_DRAWDOWN_KILL_SWITCH", severity="CRITICAL")]
    with _patch_audit(rows), \
         patch("src.agents.batman.is_kill_switch_active", return_value=False):
        out = await RiskScanner()._scan_kill_switch(period_days=7)
    assert out == []  # 1 evento < threshold 2


@pytest.mark.asyncio
async def test_ops_scanner_flags_recurring_error():
    from src.agents.ops_scanner import OpsScanner

    rows = [_AuditRow("WRITE_ERROR", severity="ERROR", agent="DailyPnLWriter") for _ in range(4)]
    with _patch_audit(rows):
        out = await OpsScanner()._scan_audit_errors(period_days=7)
    assert len(out) >= 1
    assert "DailyPnLWriter" in out[0].title and "4" in out[0].title


@pytest.mark.asyncio
async def test_ops_scanner_below_threshold_not_flagged():
    from src.agents.ops_scanner import OpsScanner

    rows = [_AuditRow("WRITE_ERROR", severity="ERROR", agent="DailyPnLWriter") for _ in range(2)]
    with _patch_audit(rows):
        out = await OpsScanner()._scan_audit_errors(period_days=7)
    assert out == []  # 2 < threshold 3


@pytest.mark.asyncio
async def test_scanners_fail_silent_on_empty_audit():
    """Guard-rail: scanners são fail-silent — audit vazio → lista, sem erro."""
    from src.agents.risk_scanner import RiskScanner
    from src.agents.ops_scanner import OpsScanner

    with _patch_audit([]), \
         patch("src.agents.batman.is_kill_switch_active", return_value=False):
        assert isinstance(await RiskScanner().scan(period_days=7), list)
        assert isinstance(await OpsScanner().scan(period_days=7), list)


# ---------------------------------------------------------------------------
# Sage v2 — atribuição por-melhoria (before/after de uma entrega específica)
# ---------------------------------------------------------------------------

def _patch_sage(decisions, baselines, saved_sink):
    return (
        patch.object(Sage, "_load_decisions_raw", return_value=decisions),
        patch.object(Sage, "_load_improvement_baselines", return_value=baselines),
        patch.object(Sage, "_save_improvement_baselines",
                     lambda self, d: saved_sink.update(d)),
    )


def test_sage_v2_first_sight_captures_baseline():
    """Primeira vez que Sage vê uma melhoria aceita → captura baseline, sem proposta."""
    saved = {}
    p1, p2, p3 = _patch_sage({"rec1": {"status": "accepted"}}, {}, saved)
    with p1, p2, p3:
        out = Sage()._track_deliveries({"win_rate": 55.0, "closed_trades": 20, "errors_24h": 1})
    assert out == []
    assert saved.get("rec1", {}).get("verdict") == "pending"
    assert saved["rec1"]["win_rate"] == 55.0


def test_sage_v2_regression_after_delivery_flagged():
    """Win rate cai >= 8pp após a entrega → verdict regression + proposta."""
    base = {"rec1": {"captured_at": "x", "win_rate": 60.0, "errors_24h": 1, "verdict": "pending"}}
    p1, p2, p3 = _patch_sage({"rec1": {"status": "accepted"}}, base, {})
    with p1, p2, p3:
        out = Sage()._track_deliveries({"win_rate": 50.0, "closed_trades": 20})  # -10pp
    assert any("regress" in pr.title.lower() for pr in out)
    assert out[0].area == "measurement"


def test_sage_v2_effective_no_council_noise():
    """Win rate sobe >= 8pp → verdict effective, sem proposta (baixo ruído)."""
    base = {"rec1": {"win_rate": 50.0, "verdict": "pending"}}
    p1, p2, p3 = _patch_sage({"rec1": {"status": "accepted"}}, base, {})
    with p1, p2, p3:
        out = Sage()._track_deliveries({"win_rate": 62.0, "closed_trades": 20})  # +12pp
    assert out == []


def test_sage_v2_neutral_when_few_trades():
    """Poucos trades fechados → não avalia (sem verdict forçado, sem proposta)."""
    base = {"rec1": {"win_rate": 60.0, "verdict": "pending"}}
    p1, p2, p3 = _patch_sage({"rec1": {"status": "accepted"}}, base, {})
    with p1, p2, p3:
        out = Sage()._track_deliveries({"win_rate": 40.0, "closed_trades": 3})  # < MIN_CLOSED
    assert out == []


def test_sage_v2_evaluations_counts():
    """improvement_evaluations agrega verdicts por categoria."""
    base = {
        "a": {"verdict": "effective"},
        "b": {"verdict": "regression"},
        "c": {"verdict": "pending"},
        "d": {"verdict": "neutral"},
    }
    with patch.object(Sage, "_load_improvement_baselines", return_value=base):
        ev = Sage().improvement_evaluations()
    assert ev["tracked"] == 4
    assert ev["counts"] == {"effective": 1, "neutral": 1, "regression": 1, "pending": 1}


# ---------------------------------------------------------------------------
# CodeAuditor._scan_large_files — threshold (com _SRC controlado)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_auditor_flags_huge_file(tmp_path):
    from src.agents import code_auditor as ca

    big = tmp_path / "monster.py"
    big.write_text("\n".join(f"x = {i}" for i in range(ca._HUGE_FILE_LINES + 10)))
    small = tmp_path / "ok.py"
    small.write_text("x = 1\n")

    with patch.object(ca, "_SRC", tmp_path), patch.object(ca, "_REPO_ROOT", tmp_path):
        out = await ca.CodeAuditor()._scan_large_files()

    assert any("monster.py" in p.evidence for p in out)
    huge = [p for p in out if "monster.py" in p.evidence][0]
    assert huge.impact == "HIGH"  # >= _HUGE_FILE_LINES


@pytest.mark.asyncio
async def test_code_auditor_ignores_small_files(tmp_path):
    from src.agents import code_auditor as ca

    (tmp_path / "tiny.py").write_text("x = 1\n")
    with patch.object(ca, "_SRC", tmp_path), patch.object(ca, "_REPO_ROOT", tmp_path):
        out = await ca.CodeAuditor()._scan_large_files()
    assert out == []  # nada acima do limite

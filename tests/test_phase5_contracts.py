"""
tests/test_phase5_contracts.py
==============================
Phase 5 — Contract hardening meta-tests (Story 028).

These tests don't exercise behavior; they cristalize **contracts** so
future drift breaks the build instead of slipping into runtime.

Coverage:
  • HeroName has 15 members and matches agents/registry.ts entries
  • AgentEvent contains every event code currently emitted
  • utc_now returns timezone-aware UTC
  • CycleReport is a Pydantic BaseModel and round-trips
  • DailyPnLSnapshot is a Pydantic BaseModel and round-trips
  • Critical models all carry schema_version=1
  • Promptable / AuditPayloadable Protocols match the right models
  • Dashboard HERO_LAYER includes PortfolioManager (Story 028 drift fix)

Run: pytest tests/test_phase5_contracts.py -v
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel


# ===========================================================================
# Foundations
# ===========================================================================


def test_utc_now_is_timezone_aware():
    from src.utils.time import utc_now

    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0


def test_utc_today_iso_format():
    from src.utils.time import utc_today_iso

    today = utc_today_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", today), today


# ===========================================================================
# HeroName enum
# ===========================================================================


def test_hero_name_has_15_members():
    from src.models.heroes import HeroName

    members = list(HeroName)
    assert len(members) == 15, f"Expected 15 heroes, got {len(members)}"


def test_hero_name_matches_registry_ts():
    """Every HeroName.value must be present (case+space-insensitive) in registry.ts."""
    from src.models.heroes import HeroName

    repo_root = Path(__file__).resolve().parent.parent
    registry_ts = (repo_root / "agents" / "registry.ts").read_text(encoding="utf-8")
    ts_codenames = set(re.findall(r"codename:\s*['\"]([^'\"]+)['\"]", registry_ts))

    def normalize(s: str) -> str:
        return s.strip().replace("-", "").replace(" ", "").lower()

    ts_normalized = {normalize(c) for c in ts_codenames}
    enum_normalized = {normalize(h.value) for h in HeroName}

    missing_in_ts = enum_normalized - ts_normalized
    missing_in_enum = ts_normalized - enum_normalized
    assert not missing_in_ts, f"In HeroName but missing in registry.ts: {missing_in_ts}"
    assert not missing_in_enum, f"In registry.ts but missing in HeroName: {missing_in_enum}"


def test_hero_name_normalize_handles_known_variants():
    from src.models.heroes import HeroName

    assert HeroName.normalize("IronMan") == HeroName.IRON_MAN
    assert HeroName.normalize("iron man") == HeroName.IRON_MAN
    assert HeroName.normalize("Spider-Man") == HeroName.SPIDER_MAN
    assert HeroName.normalize("doctorstrange") == HeroName.DOCTOR_STRANGE

    with pytest.raises(ValueError):
        HeroName.normalize("Joker")


# ===========================================================================
# AgentEvent enum
# ===========================================================================


_KNOWN_EVENT_CODES_IN_USE = {
    # Lifecycle
    "BOOT", "SHUTDOWN", "CYCLE_SKIPPED", "CYCLE_ERROR", "MONITOR_HEARTBEAT",
    # Risk
    "RISK_APPROVED", "RISK_REDUCED", "RISK_REJECTED", "RISK_KILL_SWITCH",
    # Execution
    "EXEC_FILLED", "EXEC_PARTIAL", "EXEC_REJECTED", "EXEC_PAPER",
    "EXEC_ERROR", "EXEC_SKIPPED",
    # Portfolio
    "SNAPSHOT_HYPERLIQUID", "SNAPSHOT_PAPER_FALLBACK",
    # Daily PnL writer
    "WRITE_ERROR",
}


def test_agent_event_covers_known_codes():
    from src.models.events import AgentEvent

    enum_values = {e.value for e in AgentEvent}
    missing = _KNOWN_EVENT_CODES_IN_USE - enum_values
    assert not missing, f"Event codes used in production but missing in AgentEvent: {missing}"


# ===========================================================================
# CycleReport — Pydantic
# ===========================================================================


def test_cycle_report_is_pydantic():
    from src.models.orchestration import CycleReport

    assert issubclass(CycleReport, BaseModel)


def test_cycle_report_minimal_construction_and_roundtrip():
    from src.models.orchestration import CycleReport

    r = CycleReport(symbol="BTC", error="just a sanity error")
    assert r.symbol == "BTC"
    assert r.error == "just a sanity error"
    assert r.is_executed() is False

    payload = r.to_audit_payload()
    assert payload["symbol"] == "BTC"
    assert payload["schema_version"] == 1

    # Round-trip through JSON
    revived = CycleReport.model_validate(payload)
    assert revived.symbol == "BTC"
    assert revived.error == "just a sanity error"


def test_cycle_report_re_export_in_nick_fury():
    """Backward-compat: the old import path keeps working."""
    from src.agents.nick_fury import CycleReport as NF_CycleReport
    from src.models.orchestration import CycleReport

    assert NF_CycleReport is CycleReport


# ===========================================================================
# DailyPnLSnapshot — Pydantic
# ===========================================================================


def test_daily_pnl_snapshot_is_pydantic():
    from src.services.daily_pnl_writer import DailyPnLSnapshot

    assert issubclass(DailyPnLSnapshot, BaseModel)


def test_daily_pnl_snapshot_roundtrip():
    from src.services.daily_pnl_writer import DailyPnLSnapshot

    snap = DailyPnLSnapshot(
        date_utc="2026-05-07",
        starting_equity=10_000.0,
        ending_equity=10_500.0,
        peak_equity=11_000.0,
        pnl_usd=500.0,
        pnl_pct=0.05,
        drawdown_pct=500 / 11_000.0,
        trades_count=3,
        is_paper=True,
    )
    assert snap.schema_version == 1
    payload = snap.to_audit_payload()
    revived = DailyPnLSnapshot.model_validate(payload)
    assert revived.peak_equity == 11_000.0


# ===========================================================================
# schema_version on all critical models
# ===========================================================================


@pytest.mark.parametrize(
    "import_path,model_name",
    [
        ("src.models.signal", "TradingSignal"),
        ("src.models.risk", "RiskApproval"),
        ("src.models.execution", "ExecutionResult"),
        ("src.models.portfolio", "EquitySnapshot"),
        ("src.models.market_data", "MarketAnalysis"),
        ("src.models.orchestration", "CycleReport"),
        ("src.models.errors", "AgentErrorReport"),
    ],
)
def test_critical_model_has_schema_version(import_path, model_name):
    """Every critical model on the runtime path must carry schema_version."""
    import importlib

    module = importlib.import_module(import_path)
    Model = getattr(module, model_name)
    fields = Model.model_fields
    assert "schema_version" in fields, (
        f"{model_name} missing schema_version field — required for migration safety"
    )
    # Default must be 1 for the initial schema
    assert fields["schema_version"].default == 1


# ===========================================================================
# Protocols
# ===========================================================================


def test_promptable_protocol_matches_market_models():
    from src.models.market_data import (
        MarketData,
        SentimentData,
        OnchainData,
        VolatilityData,
        LiquidityData,
        AnomalyReport,
    )
    from src.models.protocols import Promptable

    md = MarketData(
        symbol="BTC",
        timestamp=datetime.now(timezone.utc),
        timeframe="4h",
        price=65_000.0,
    )
    assert isinstance(md, Promptable)


def test_audit_payloadable_protocol_matches_orchestration_models():
    from src.models.orchestration import CycleReport
    from src.models.errors import AgentErrorReport
    from src.models.protocols import AuditPayloadable

    cr = CycleReport(symbol="BTC")
    assert isinstance(cr, AuditPayloadable)

    err = AgentErrorReport(
        agent="Vision",
        error_class="RuntimeError",
        message="boom",
        fallback_taken=True,
    )
    assert isinstance(err, AuditPayloadable)


# ===========================================================================
# AgentErrorReport
# ===========================================================================


def test_agent_error_report_round_trip_and_summary():
    from src.models.errors import AgentErrorReport

    err = AgentErrorReport(
        agent="Vision",
        error_class="TimeoutError",
        message="OpenAI timed out",
        fallback_taken=True,
        payload={"model": "gpt-4o"},
    )
    assert err.schema_version == 1
    assert "FALLBACK" in err.summary()
    payload = err.to_audit_payload()
    revived = AgentErrorReport.model_validate(payload)
    assert revived.error_class == "TimeoutError"


# ===========================================================================
# Dashboard HERO_LAYER
# ===========================================================================


def test_dashboard_hero_layer_includes_portfolio_manager():
    from src.dashboard.server import HERO_LAYER

    assert "PortfolioManager" in HERO_LAYER
    assert HERO_LAYER["PortfolioManager"] == "L4"


def test_dashboard_hero_layer_keys_are_pascalcase_no_spaces():
    """Keys in HERO_LAYER use the no-space form ('IronMan', not 'Iron Man')."""
    from src.dashboard.server import HERO_LAYER

    for key in HERO_LAYER:
        assert " " not in key, f"HERO_LAYER key has space: {key!r}"
        assert "-" not in key, f"HERO_LAYER key has hyphen: {key!r}"

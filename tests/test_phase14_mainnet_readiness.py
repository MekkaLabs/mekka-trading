"""
tests/test_phase14_mainnet_readiness.py
========================================
Story 036 — Mainnet Readiness Pre-Flight tests.

Covers:
  1. Settings double-gate — ValueError when paper_trading=False + live_trading_confirmed=False
  2. Settings accepts paper_trading=False + live_trading_confirmed=True
  3. Settings is_live property
  4. Settings mode_label combinations
  5. IronMan runtime double-gate — REJECTED when live_trading_confirmed=False at runtime
  6. preflight_mainnet checks: env_vars, kill_switch, risk_limits, authorization_file
  7. PreflightReport: all_pass, fail_count, warn_count helpers

Implementation note:
  Settings is constructed via direct kwargs throughout — no sys.modules manipulation.
  Pydantic v2 BaseSettings gives precedence to explicit kwargs over env vars, so
  passing fields directly tests the validators without polluting the module cache.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal required kwargs for a valid Settings construction
# ---------------------------------------------------------------------------

_REQUIRED = dict(
    openai_api_key="sk-test-placeholder",
    hyperliquid_private_key="aabbccdd" * 8,
    hyperliquid_wallet_address="0x" + "d" * 40,
)


def _settings(**overrides):
    """Construct a Settings instance with minimal required fields + overrides.

    Uses direct kwargs — NO sys.modules manipulation. Pydantic v2 BaseSettings
    gives explicit constructor kwargs the highest precedence, so validators run
    against the values we pass without touching the environment.
    """
    from src.config.settings import Settings

    return Settings(**{**_REQUIRED, **overrides})


# ===========================================================================
# 1 — Settings double-gate validator
# ===========================================================================

class TestSettingsDoubleGate:
    """[036] live_trading_double_gate model_validator enforces the two-key rule."""

    def test_paper_true_confirmed_false_ok(self):
        """Normal paper-trading startup — no error."""
        s = _settings(paper_trading=True, live_trading_confirmed=False)
        assert s.paper_trading is True
        assert s.live_trading_confirmed is False

    def test_paper_true_confirmed_true_ok(self):
        """confirmed=True is harmless when paper_trading=True."""
        s = _settings(paper_trading=True, live_trading_confirmed=True)
        assert s.paper_trading is True
        assert s.live_trading_confirmed is True

    def test_paper_false_confirmed_true_ok(self):
        """The explicit double opt-in: both gates open."""
        s = _settings(paper_trading=False, live_trading_confirmed=True)
        assert s.paper_trading is False
        assert s.live_trading_confirmed is True

    def test_paper_false_confirmed_false_raises(self):
        """Accidental live attempt: validator must raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)):
            _settings(paper_trading=False, live_trading_confirmed=False)

    def test_double_gate_error_message_mentions_live_trading(self):
        """Error must mention LIVE_TRADING_CONFIRMED so operator knows what to fix."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)) as exc_info:
            _settings(paper_trading=False, live_trading_confirmed=False)

        err_text = str(exc_info.value)
        assert "LIVE_TRADING_CONFIRMED" in err_text or "live_trading" in err_text.lower()

    def test_double_gate_error_message_mentions_docs(self):
        """Error must mention docs/MAINNET-AUTHORIZATION.md for discoverability."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)) as exc_info:
            _settings(paper_trading=False, live_trading_confirmed=False)

        err_text = str(exc_info.value)
        assert "MAINNET-AUTHORIZATION" in err_text or "mainnet" in err_text.lower()


# ===========================================================================
# 2 — Settings is_live property
# ===========================================================================

class TestIsLiveProperty:
    """[036] is_live returns True only when both gates are open."""

    def test_is_live_false_when_paper(self):
        s = _settings(paper_trading=True, live_trading_confirmed=False)
        assert s.is_live is False

    def test_is_live_false_when_paper_even_with_confirmed(self):
        s = _settings(paper_trading=True, live_trading_confirmed=True)
        assert s.is_live is False  # paper=True overrides

    def test_is_live_true_when_both_gates_open(self):
        s = _settings(paper_trading=False, live_trading_confirmed=True)
        assert s.is_live is True


# ===========================================================================
# 3 — Settings mode_label
# ===========================================================================

class TestModeLabelProperty:
    """[036] mode_label reflects all three valid combinations."""

    def test_mode_label_paper_default(self):
        s = _settings(paper_trading=True, live_trading_confirmed=False)
        assert s.mode_label == "PAPER"

    def test_mode_label_paper_with_confirmed(self):
        s = _settings(paper_trading=True, live_trading_confirmed=True)
        assert s.mode_label == "PAPER"

    def test_mode_label_live(self):
        s = _settings(paper_trading=False, live_trading_confirmed=True)
        assert s.mode_label == "LIVE"


# ===========================================================================
# 4 — IronMan runtime double-gate (belt-and-suspenders)
# ===========================================================================

class TestIronManRuntimeDoubleGate:
    """[036] IronMan._run() returns REJECTED if live_trading_confirmed is off at runtime."""

    @pytest.mark.asyncio
    async def test_iron_man_blocked_when_gate_not_set(self):
        """IronMan returns REJECTED when paper=False but live_trading_confirmed=False."""
        from src.agents.iron_man import IronMan
        from src.models.execution import ExecutionStatus
        from src.models.risk import RiskApproval, RiskVerdict
        from src.models.signal import TradeAction, TradingSignal

        signal = TradingSignal(
            symbol="BTC",
            action=TradeAction.LONG,
            confidence=0.85,
            entry_price=50_000.0,
            stop_loss=48_000.0,
            take_profit=55_000.0,
            size_pct=0.02,
            leverage=3,
            reasoning="gate test",
        )
        approval = RiskApproval(
            symbol="BTC",
            verdict=RiskVerdict.APPROVED,
            adjusted_size_pct=0.02,
            adjusted_leverage=3,
        )

        import src.agents.iron_man as im_module

        mock_settings = MagicMock()
        mock_settings.paper_trading = False
        mock_settings.live_trading_confirmed = False
        mock_settings.hyperliquid_network = "testnet"

        with patch.object(im_module, "settings", mock_settings):
            agent = IronMan()
            result = await agent.run(signal=signal, approval=approval, equity_usd=10_000.0)

        assert result.status == ExecutionStatus.REJECTED
        assert "LIVE_TRADING_CONFIRMED" in (result.error or "")

    @pytest.mark.asyncio
    async def test_iron_man_paper_path_when_paper_true(self):
        """IronMan takes paper path normally when paper_trading=True."""
        from src.agents.iron_man import IronMan
        from src.models.execution import ExecutionStatus
        from src.models.risk import RiskApproval, RiskVerdict
        from src.models.signal import TradeAction, TradingSignal

        signal = TradingSignal(
            symbol="ETH",
            action=TradeAction.LONG,
            confidence=0.80,
            entry_price=3_000.0,
            stop_loss=2_800.0,
            take_profit=3_300.0,
            size_pct=0.01,
            leverage=2,
            reasoning="paper path test",
        )
        approval = RiskApproval(
            symbol="ETH",
            verdict=RiskVerdict.APPROVED,
            adjusted_size_pct=0.01,
            adjusted_leverage=2,
        )

        import src.agents.iron_man as im_module

        mock_settings = MagicMock()
        mock_settings.paper_trading = True
        mock_settings.live_trading_confirmed = False
        mock_settings.paper_slippage_bps = 3.0
        mock_settings.hyperliquid_network = "testnet"

        with patch.object(im_module, "settings", mock_settings):
            agent = IronMan()
            result = await agent.run(signal=signal, approval=approval, equity_usd=10_000.0)

        assert result.status == ExecutionStatus.PAPER
        assert result.is_paper is True


# ===========================================================================
# 5 — PreflightReport model
# ===========================================================================

class TestPreflightReport:
    """[036] PreflightReport helpers: all_pass, fail_count, warn_count."""

    def _report(self):
        from scripts.preflight_mainnet import PreflightReport
        return PreflightReport()

    def test_empty_report_all_pass(self):
        r = self._report()
        assert r.all_pass is True
        assert r.fail_count == 0
        assert r.warn_count == 0

    def test_ok_does_not_affect_counts(self):
        r = self._report()
        r.ok("test_ok", "all good")
        assert r.all_pass is True
        assert r.fail_count == 0

    def test_fail_sets_all_pass_false(self):
        r = self._report()
        r.fail("test_fail", "something broke")
        assert r.all_pass is False
        assert r.fail_count == 1

    def test_warn_does_not_fail(self):
        r = self._report()
        r.warn("test_warn", "borderline")
        assert r.all_pass is True
        assert r.warn_count == 1
        assert r.fail_count == 0

    def test_mixed_results(self):
        r = self._report()
        r.ok("a", "ok")
        r.warn("b", "warn")
        r.fail("c", "fail")
        assert r.all_pass is False
        assert r.fail_count == 1
        assert r.warn_count == 1

    def test_skip_does_not_affect_pass(self):
        r = self._report()
        r.skip("s", "skipped")
        assert r.all_pass is True
        assert r.fail_count == 0


# ===========================================================================
# 6 — Individual check functions
# ===========================================================================

class TestCheckEnvVars:
    """[036] check_env_vars detects missing required keys."""

    def test_missing_required_key_fails(self):
        from scripts.preflight_mainnet import PreflightReport, check_env_vars

        with patch.dict(os.environ, {}, clear=True):
            r = PreflightReport()
            check_env_vars(r)

        fail_names = [c.name for c in r.checks if c.level == "FAIL"]
        assert "env_vars_required" in fail_names

    def test_all_required_keys_present_passes(self):
        from scripts.preflight_mainnet import PreflightReport, check_env_vars

        env = {
            "OPENAI_API_KEY": "sk-test",
            "HYPERLIQUID_PRIVATE_KEY": "aabbccdd" * 8,
            "HYPERLIQUID_WALLET_ADDRESS": "0x" + "d" * 40,
        }
        with patch.dict(os.environ, env, clear=False):
            r = PreflightReport()
            check_env_vars(r)

        pass_names = [c.name for c in r.checks if c.level == "PASS"]
        assert "env_vars_required" in pass_names

    def test_live_trading_confirmed_not_set_warns(self):
        from scripts.preflight_mainnet import PreflightReport, check_env_vars

        env = {
            "OPENAI_API_KEY": "sk-test",
            "HYPERLIQUID_PRIVATE_KEY": "aabbccdd" * 8,
            "HYPERLIQUID_WALLET_ADDRESS": "0x" + "d" * 40,
        }
        clean_env = {k: v for k, v in os.environ.items() if k != "LIVE_TRADING_CONFIRMED"}
        clean_env.update(env)
        with patch.dict(os.environ, clean_env, clear=True):
            r = PreflightReport()
            check_env_vars(r)

        warn_names = [c.name for c in r.checks if c.level == "WARN"]
        assert "env_vars_live" in warn_names

    def test_live_trading_confirmed_true_warns(self):
        """LIVE_TRADING_CONFIRMED=true must emit WARN (intentional confirmation notice)."""
        from scripts.preflight_mainnet import PreflightReport, check_env_vars

        env = {
            "OPENAI_API_KEY": "sk-test",
            "HYPERLIQUID_PRIVATE_KEY": "aabbccdd" * 8,
            "HYPERLIQUID_WALLET_ADDRESS": "0x" + "d" * 40,
            "LIVE_TRADING_CONFIRMED": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            r = PreflightReport()
            check_env_vars(r)

        live_checks = [c for c in r.checks if c.name == "env_vars_live"]
        assert live_checks, "env_vars_live check should exist"
        assert live_checks[0].level == "WARN"


class TestCheckKillSwitch:
    """[036] check_kill_switch detects active kill switch."""

    def test_kill_switch_active_fails(self):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        r = PreflightReport()
        with patch.object(pfm, "is_kill_switch_active", return_value=True), \
             patch.object(pfm, "read_kill_switch_metadata", return_value={"reason": "halted"}):
            pfm.check_kill_switch(r)

        fail_checks = [c for c in r.checks if c.level == "FAIL" and c.name == "kill_switch"]
        assert fail_checks, "kill_switch check should FAIL when active"
        assert "halted" in fail_checks[0].detail

    def test_kill_switch_inactive_passes(self):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        r = PreflightReport()
        with patch.object(pfm, "is_kill_switch_active", return_value=False):
            pfm.check_kill_switch(r)

        pass_checks = [c for c in r.checks if c.level == "PASS" and c.name == "kill_switch"]
        assert pass_checks


class TestCheckRiskLimits:
    """[036] check_risk_limits warns on looser-than-recommended mainnet values."""

    def _mock_conservative(self):
        m = MagicMock()
        m.max_position_size_pct = 0.005
        m.max_leverage = 2
        m.max_trades_per_day = 5
        m.max_open_positions = 2
        return m

    def test_conservative_limits_pass(self):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        r = PreflightReport()
        with patch.object(pfm, "settings", self._mock_conservative()):
            pfm.check_risk_limits(r)

        assert any(c.name == "risk_limits" and c.level == "PASS" for c in r.checks)

    def test_aggressive_position_size_warns(self):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        m = self._mock_conservative()
        m.max_position_size_pct = 0.10  # > 0.005

        r = PreflightReport()
        with patch.object(pfm, "settings", m):
            pfm.check_risk_limits(r)

        assert any(c.name == "risk_limits" and c.level == "WARN" for c in r.checks)

    def test_high_leverage_warns(self):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        m = self._mock_conservative()
        m.max_leverage = 10  # > 2

        r = PreflightReport()
        with patch.object(pfm, "settings", m):
            pfm.check_risk_limits(r)

        assert any(c.name == "risk_limits" and c.level == "WARN" for c in r.checks)

    def test_too_many_trades_warns(self):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        m = self._mock_conservative()
        m.max_trades_per_day = 20  # > 5

        r = PreflightReport()
        with patch.object(pfm, "settings", m):
            pfm.check_risk_limits(r)

        assert any(c.name == "risk_limits" and c.level == "WARN" for c in r.checks)


class TestCheckAuthorizationFile:
    """[036] check_authorization_file validates existence and sign-off."""

    def test_missing_file_fails(self, tmp_path):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        r = PreflightReport()
        with patch.object(pfm, "_REPO_ROOT", tmp_path):
            pfm.check_authorization_file(r)

        assert any(c.name == "authorization_file" and c.level == "FAIL" for c in r.checks)

    def test_file_without_signoff_fails(self, tmp_path):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "MAINNET-AUTHORIZATION.md").write_text("# Authorization\nNot signed yet.")

        r = PreflightReport()
        with patch.object(pfm, "_REPO_ROOT", tmp_path):
            pfm.check_authorization_file(r)

        assert any(c.name == "authorization_file" and c.level == "FAIL" for c in r.checks)

    def test_file_with_placeholder_warns(self, tmp_path):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "MAINNET-AUTHORIZATION.md").write_text(
            "GO MAINNET\nOperator: ____\nDate: 2026-05-08"
        )

        r = PreflightReport()
        with patch.object(pfm, "_REPO_ROOT", tmp_path):
            pfm.check_authorization_file(r)

        assert any(c.name == "authorization_file" and c.level == "WARN" for c in r.checks)

    def test_fully_signed_file_passes(self, tmp_path):
        from scripts import preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "MAINNET-AUTHORIZATION.md").write_text(
            "# Mainnet Authorization\n\n"
            "GO MAINNET\n\n"
            "Operator: Gustavo Vicente\n"
            "Date: 2026-05-08\n"
            "Wallet: 0xabcdef1234567890\n"
        )

        r = PreflightReport()
        with patch.object(pfm, "_REPO_ROOT", tmp_path):
            pfm.check_authorization_file(r)

        assert any(c.name == "authorization_file" and c.level == "PASS" for c in r.checks)


# ===========================================================================
# 7 — Human gates list integrity
# ===========================================================================

class TestHumanGates:
    """[036] _HUMAN_GATES contains all required reminders."""

    def test_human_gates_count(self):
        from scripts.preflight_mainnet import _HUMAN_GATES
        assert len(_HUMAN_GATES) >= 6

    def test_human_gates_ids_are_sequential(self):
        from scripts.preflight_mainnet import _HUMAN_GATES
        for i, (gate_id, _) in enumerate(_HUMAN_GATES, start=1):
            assert gate_id == f"H{i}", f"Expected H{i}, got {gate_id}"

    def test_human_gates_have_descriptions(self):
        from scripts.preflight_mainnet import _HUMAN_GATES
        for gate_id, desc in _HUMAN_GATES:
            assert len(desc) > 10, f"Gate {gate_id} description too short: {desc!r}"

    def test_wolverine_gate_present(self):
        from scripts.preflight_mainnet import _HUMAN_GATES
        descs = " ".join(d for _, d in _HUMAN_GATES)
        assert "Wolverine" in descs or "ENDORSE" in descs

    def test_testnet_gate_present(self):
        from scripts.preflight_mainnet import _HUMAN_GATES
        descs = " ".join(d for _, d in _HUMAN_GATES)
        assert "testnet" in descs.lower()


# ===========================================================================
# 8 — run_preflight integration (smoke test)
# ===========================================================================

class TestRunPreflight:
    """[036] run_preflight returns a PreflightReport (smoke test — no live env needed)."""

    def _noop(self, r):
        r.skip("noop", "patched out")

    def test_run_preflight_returns_report(self):
        """run_preflight should always return a PreflightReport, never raise."""
        import scripts.preflight_mainnet as pfm
        from scripts.preflight_mainnet import PreflightReport

        noop = self._noop
        with (
            patch.object(pfm, "check_env_vars", noop),
            patch.object(pfm, "check_settings", noop),
            patch.object(pfm, "check_kill_switch", noop),
            patch.object(pfm, "check_network", noop),
            patch.object(pfm, "check_risk_limits", noop),
            patch.object(pfm, "check_telegram", noop),
            patch.object(pfm, "check_sdk_availability", noop),
            patch.object(pfm, "check_authorization_file", noop),
        ):
            report = pfm.run_preflight()

        assert isinstance(report, PreflightReport)

    def test_run_preflight_calls_all_eight_checks(self):
        """All 8 automated check functions must be called."""
        import scripts.preflight_mainnet as pfm

        called: set[str] = set()

        def make_spy(name: str):
            def spy(r):
                called.add(name)
            return spy

        check_names = [
            "check_env_vars", "check_settings", "check_kill_switch",
            "check_network", "check_risk_limits", "check_telegram",
            "check_sdk_availability", "check_authorization_file",
        ]

        with (
            patch.object(pfm, "check_env_vars", make_spy("check_env_vars")),
            patch.object(pfm, "check_settings", make_spy("check_settings")),
            patch.object(pfm, "check_kill_switch", make_spy("check_kill_switch")),
            patch.object(pfm, "check_network", make_spy("check_network")),
            patch.object(pfm, "check_risk_limits", make_spy("check_risk_limits")),
            patch.object(pfm, "check_telegram", make_spy("check_telegram")),
            patch.object(pfm, "check_sdk_availability", make_spy("check_sdk_availability")),
            patch.object(pfm, "check_authorization_file", make_spy("check_authorization_file")),
        ):
            pfm.run_preflight()

        for name in check_names:
            assert name in called, f"{name} was not called by run_preflight()"

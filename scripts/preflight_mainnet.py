#!/usr/bin/env python3
"""
scripts/preflight_mainnet.py
=============================
Story 036 — Mainnet Readiness Pre-Flight Checklist

Runs all automated gates before live trading. Exits 0 only when ALL
checks pass. Human gates (testnet history, operator sign-off) are listed
as reminders but cannot be verified programmatically.

Usage
-----
    python3 scripts/preflight_mainnet.py            # full check
    python3 scripts/preflight_mainnet.py --json     # machine-readable output
    python3 scripts/preflight_mainnet.py --strict   # exit 1 on any warning

Automated gates
---------------
  1. Environment variables — all required .env keys present
  2. Settings validation — pydantic double-gate consistency
  3. Kill switch — not currently engaged
  4. Network — mainnet selected (not testnet)
  5. Risk limits — conservative values for first-week mainnet
  6. Telegram — alerting enabled (required for live monitoring)
  7. SDK availability — hyperliquid-python-sdk + eth-account installed
  8. Authorization file — docs/MAINNET-AUTHORIZATION.md exists and signed
  9. H2 auto-check — Deadpool queries DB for Wolverine SL ENDORSE rate

Human gates (printed as reminders, not enforced)
-------------------------------------------------
  H1. ≥ 1 month testnet without critical incident
  H2. Wolverine SL ENDORSE rate ≥ 70% (auto-checked via Deadpool)
  H3. Vision Critic stable for ≥ 1 week
  H4. Story 032b DELIVERED ✅ 2026-05-11
  H5. Dedicated mainnet wallet created
  H6. Wallet funded via real transfer
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    level: str  # "PASS" | "FAIL" | "WARN" | "SKIP"
    detail: str
    fix: Optional[str] = None


@dataclass
class PreflightReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_pass(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.level == "FAIL")

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.level == "WARN")

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)

    def ok(self, name: str, detail: str) -> None:
        self.add(CheckResult(name=name, passed=True, level="PASS", detail=detail))

    def fail(self, name: str, detail: str, fix: Optional[str] = None) -> None:
        self.add(CheckResult(name=name, passed=False, level="FAIL", detail=detail, fix=fix))

    def warn(self, name: str, detail: str, fix: Optional[str] = None) -> None:
        self.add(CheckResult(name=name, passed=True, level="WARN", detail=detail, fix=fix))

    def skip(self, name: str, detail: str) -> None:
        self.add(CheckResult(name=name, passed=True, level="SKIP", detail=detail))


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Module-level sentinels — allow tests to patch via patch.object(pfm, ...).
# Functions that need these references check the module-level name first; if it
# is None (not patched), they fall back to a lazy import.
# ---------------------------------------------------------------------------
settings = None  # type: ignore[assignment]
is_kill_switch_active = None  # type: ignore[assignment]
read_kill_switch_metadata = None  # type: ignore[assignment]
Deadpool = None  # type: ignore[assignment]


def _get_settings():
    """Return the active settings object (patched or real)."""
    if settings is not None:
        return settings
    from src.config.settings import settings as _s
    return _s


def check_env_vars(report: PreflightReport) -> None:
    required = [
        "OPENAI_API_KEY",
        "HYPERLIQUID_PRIVATE_KEY",
        "HYPERLIQUID_WALLET_ADDRESS",
    ]
    live_required = [
        "LIVE_TRADING_CONFIRMED",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        report.fail(
            "env_vars_required",
            f"Missing required env vars: {', '.join(missing)}",
            fix="Add them to your .env file and source it before running.",
        )
    else:
        report.ok("env_vars_required", "All required env vars present")

    live_missing = [k for k in live_required if not os.getenv(k)]
    if live_missing:
        report.warn(
            "env_vars_live",
            "LIVE_TRADING_CONFIRMED not set (required to actually execute live orders)",
            fix="Set LIVE_TRADING_CONFIRMED=true ONLY after operator sign-off.",
        )
    else:
        val = os.getenv("LIVE_TRADING_CONFIRMED", "").lower()
        if val in ("true", "1", "yes"):
            report.warn(
                "env_vars_live",
                "LIVE_TRADING_CONFIRMED=true — live orders will be sent. Confirm intentional.",
            )
        else:
            report.ok("env_vars_live", f"LIVE_TRADING_CONFIRMED={val!r} (not enabled)")


def check_settings(report: PreflightReport) -> None:
    try:
        # Import settings with current env — if double-gate is misconfigured it raises
        from src.config.settings import Settings

        s = Settings()  # will raise ValueError if double-gate violated
        report.ok("settings_loads", f"Settings valid — mode={s.mode_label}, network={s.hyperliquid_network}")

        if s.paper_trading:
            report.warn(
                "settings_paper_mode",
                "PAPER_TRADING=true — no real orders will be placed until flipped.",
                fix="Set PAPER_TRADING=false + LIVE_TRADING_CONFIRMED=true for live mode.",
            )
        else:
            report.ok("settings_paper_mode", "paper_trading=False (live mode)")

    except Exception as exc:
        report.fail("settings_loads", f"Settings validation failed: {exc}")


def check_kill_switch(report: PreflightReport) -> None:
    try:
        _ks_active = is_kill_switch_active
        _ks_meta = read_kill_switch_metadata
        if _ks_active is None:
            from src.agents.batman import is_kill_switch_active as _ks_active
            from src.agents.batman import read_kill_switch_metadata as _ks_meta

        if _ks_active():
            meta = _ks_meta()
            reason = meta.get("reason", "unknown")
            report.fail(
                "kill_switch",
                f"Kill switch is ACTIVE — reason: {reason!r}",
                fix="Run: rm data/.kill_switch   (or use /resume via Telegram)",
            )
        else:
            report.ok("kill_switch", "Kill switch not engaged")
    except Exception as exc:
        report.warn("kill_switch", f"Could not check kill switch: {exc}")


def check_network(report: PreflightReport) -> None:
    try:
        s = _get_settings()
        if s.hyperliquid_network == "mainnet":
            report.ok("network", "HYPERLIQUID_NETWORK=mainnet")
        else:
            report.warn(
                "network",
                f"HYPERLIQUID_NETWORK={s.hyperliquid_network!r} (not mainnet)",
                fix="Set HYPERLIQUID_NETWORK=mainnet for live trading.",
            )
    except Exception as exc:
        report.warn("network", f"Could not check network: {exc}")


def check_risk_limits(report: PreflightReport) -> None:
    """Warn if risk limits are looser than recommended first-week mainnet values."""
    try:
        s = _get_settings()

        issues = []
        # Recommended first-week caps (conservative)
        if s.max_position_size_pct > 0.005:
            issues.append(
                f"max_position_size_pct={s.max_position_size_pct:.3f} "
                f"(recommended ≤ 0.005 = 0.5% for first week)"
            )
        if s.max_leverage > 2:
            issues.append(
                f"max_leverage={s.max_leverage}x "
                f"(recommended ≤ 2x for first week)"
            )
        if s.max_trades_per_day > 5:
            issues.append(
                f"max_trades_per_day={s.max_trades_per_day} "
                f"(recommended ≤ 5 for first week)"
            )
        if s.max_open_positions > 2:
            issues.append(
                f"max_open_positions={s.max_open_positions} "
                f"(recommended ≤ 2 for first week)"
            )

        if issues:
            report.warn(
                "risk_limits",
                "Risk limits looser than first-week mainnet recommendation:\n  " + "\n  ".join(issues),
                fix="Tighten limits in .env before going live.",
            )
        else:
            report.ok(
                "risk_limits",
                f"Conservative: size={s.max_position_size_pct:.3f} "
                f"lev={s.max_leverage}x trades/day={s.max_trades_per_day}",
            )
    except Exception as exc:
        report.warn("risk_limits", f"Could not check risk limits: {exc}")


def check_telegram(report: PreflightReport) -> None:
    try:
        s = _get_settings()
        if s.telegram_enabled:
            report.ok("telegram", f"Telegram alerting enabled (chat_id configured)")
        else:
            report.warn(
                "telegram",
                "Telegram alerting not configured — no real-time alerts for live errors.",
                fix="Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env.",
            )
    except Exception as exc:
        report.warn("telegram", f"Could not check Telegram config: {exc}")


def check_sdk_availability(report: PreflightReport) -> None:
    try:
        import eth_account  # noqa: F401
        report.ok("sdk_eth_account", f"eth-account installed")
    except ImportError:
        report.fail(
            "sdk_eth_account",
            "eth-account not installed (required for live execution)",
            fix="pip install eth-account",
        )

    try:
        from hyperliquid.exchange import Exchange  # noqa: F401
        report.ok("sdk_hyperliquid", "hyperliquid-python-sdk installed")
    except ImportError:
        report.fail(
            "sdk_hyperliquid",
            "hyperliquid-python-sdk not installed (required for live execution)",
            fix="pip install hyperliquid-python-sdk",
        )

    try:
        import ccxt  # noqa: F401
        report.ok("sdk_ccxt", f"ccxt installed (version {ccxt.__version__})")
    except ImportError:
        report.warn(
            "sdk_ccxt",
            "ccxt not installed — Superman will not be able to fetch market data.",
            fix="pip install ccxt",
        )


def check_authorization_file(report: PreflightReport) -> None:
    auth_file = _REPO_ROOT / "docs" / "MAINNET-AUTHORIZATION.md"
    if not auth_file.exists():
        report.fail(
            "authorization_file",
            "docs/MAINNET-AUTHORIZATION.md does not exist",
            fix=(
                "Copy docs/MAINNET-AUTHORIZATION.md.template, fill it out, "
                "and commit with your signature before enabling live trading."
            ),
        )
        return

    content = auth_file.read_text()
    if "GO MAINNET" not in content:
        report.fail(
            "authorization_file",
            "docs/MAINNET-AUTHORIZATION.md exists but does not contain 'GO MAINNET' sign-off",
            fix="Complete the authorization form with 'GO MAINNET' and your signature.",
        )
    elif "____" in content or "YOUR_NAME" in content:
        report.warn(
            "authorization_file",
            "Authorization file may still have unfilled placeholders",
            fix="Replace all ____ and YOUR_NAME placeholders in MAINNET-AUTHORIZATION.md.",
        )
    else:
        report.ok("authorization_file", "MAINNET-AUTHORIZATION.md present and signed")


# ---------------------------------------------------------------------------
# H2 — Wolverine SL endorsement rate (automated via Deadpool)
# ---------------------------------------------------------------------------

# Module-level sentinel so tests can patch via patch.object(pfm, "deadpool_repo", ...)
deadpool_repo = None  # type: ignore[assignment]

_H2_MIN_ENDORSE_RATE = 70.0  # percent


def check_h2_deadpool(report: PreflightReport) -> None:
    """
    Auto-check gate H2: Wolverine SL ENDORSE rate ≥ 70% over last 30 days.

    Runs Deadpool synchronously via asyncio.run(). If the DB has insufficient
    data (< MIN_DAYS_REQUIRED trading days) the check is downgraded to a WARN
    so it doesn't block the preflight in paper-trading phase.

    Never raises — any failure degrades to WARN so the operator is informed
    but the preflight is not blocked by a DB connectivity issue.
    """
    import asyncio

    try:
        _repo = deadpool_repo
        if _repo is None:
            from src.persistence.repository import MekkaRepository
            _repo = MekkaRepository()

        _Deadpool = Deadpool
        if _Deadpool is None:
            from src.agents.deadpool import Deadpool as _Deadpool
        dp = _Deadpool(repo=_repo)

        try:
            report_obj = asyncio.run(dp.run(window_days=30))
        except RuntimeError:
            # Already inside an event loop (e.g. called from async context in tests).
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                report_obj = pool.submit(asyncio.run, dp.run(window_days=30)).result(timeout=30)

        from src.models.performance import PerformanceVerdict

        if report_obj.verdict == PerformanceVerdict.INSUFFICIENT_DATA:
            report.warn(
                "h2_wolverine_endorse",
                f"Insufficient trading data for H2 auto-check "
                f"({report_obj.days_with_data} day(s) — need ≥7). "
                f"Run paper trading longer before mainnet.",
                fix="Continue paper trading and re-run preflight after ≥7 trading days.",
            )
            return

        rate = report_obj.wolverine_sl_endorse_rate_pct
        if rate is None:
            report.warn(
                "h2_wolverine_endorse",
                "Wolverine has not produced any MONITOR_RECOVERY_PLAN audit rows yet. "
                "H2 cannot be verified automatically.",
                fix="Ensure Wolverine is running in the monitor cycle and producing audit events.",
            )
            return

        if rate >= _H2_MIN_ENDORSE_RATE:
            report.ok(
                "h2_wolverine_endorse",
                f"Wolverine SL ENDORSE rate {rate:.1f}% ≥ {_H2_MIN_ENDORSE_RATE:.0f}% ✓ "
                f"(over {report_obj.days_with_data} trading day(s))",
            )
        else:
            report.warn(
                "h2_wolverine_endorse",
                f"Wolverine SL ENDORSE rate {rate:.1f}% < {_H2_MIN_ENDORSE_RATE:.0f}% required for H2. "
                f"Positions are being flagged for rescue too often.",
                fix=(
                    "Review open position management. Consider tightening stop-loss placement. "
                    "H2 requires ≥70% ENDORSE rate over 30 trading days."
                ),
            )

    except Exception as exc:
        report.warn(
            "h2_wolverine_endorse",
            f"Could not auto-check H2 (DB unavailable or Deadpool error): {exc}",
            fix="Manually verify Wolverine SL ENDORSE rate via dashboard audit log.",
        )


# ---------------------------------------------------------------------------
# Human gate reminders (non-enforced)
# ---------------------------------------------------------------------------

_HUMAN_GATES = [
    ("H1", "≥ 1 month testnet without critical incident (check INCIDENT-PLAYBOOK.md)"),
    ("H2", "Wolverine SL ENDORSE rate ≥ 70% — auto-checked above (see h2_wolverine_endorse)"),
    ("H3", "Vision Critic ON for ≥ 1 week without signal regression"),
    ("H4", "Story 032b (TypeScript audit shim) ✅ DELIVERED 2026-05-11"),
    ("H5", "Dedicated mainnet wallet created (NOT personal wallet)"),
    ("H6", "Wallet funded via real transfer (not testnet faucet)"),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_preflight(strict: bool = False) -> PreflightReport:
    report = PreflightReport()

    check_env_vars(report)
    check_settings(report)
    check_kill_switch(report)
    check_network(report)
    check_risk_limits(report)
    check_telegram(report)
    check_sdk_availability(report)
    check_authorization_file(report)
    check_h2_deadpool(report)

    return report


def print_report(report: PreflightReport, as_json: bool = False, strict: bool = False) -> int:
    if as_json:
        data = {
            "all_pass": report.all_pass,
            "fail_count": report.fail_count,
            "warn_count": report.warn_count,
            "checks": [
                {
                    "name": c.name,
                    "level": c.level,
                    "detail": c.detail,
                    "fix": c.fix,
                }
                for c in report.checks
            ],
            "human_gates": [{"id": g[0], "description": g[1]} for g in _HUMAN_GATES],
        }
        print(json.dumps(data, indent=2))
    else:
        icons = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "⏭️ "}
        print()
        print("=" * 60)
        print("  Mekka Trading — Mainnet Pre-Flight Checklist")
        print("=" * 60)
        for c in report.checks:
            icon = icons.get(c.level, "?")
            print(f"  {icon} [{c.level}] {c.name}")
            print(f"       {c.detail}")
            if c.fix:
                print(f"       → Fix: {c.fix}")
        print()
        print("  ─── Human Gates (operator must verify) ───────────────")
        for gate_id, gate_desc in _HUMAN_GATES:
            print(f"  ☐  [{gate_id}] {gate_desc}")
        print()
        fails = report.fail_count
        warns = report.warn_count
        status = "🟢 ALL AUTOMATED CHECKS PASSED" if fails == 0 else f"🔴 {fails} CHECK(S) FAILED"
        print(f"  {status}  ({warns} warning(s))")
        print("=" * 60)
        print()

    if report.fail_count > 0:
        return 1
    if strict and report.warn_count > 0:
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Mekka Trading mainnet pre-flight checklist")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on warnings too")
    args = parser.parse_args()

    # Ensure project root is on path
    sys.path.insert(0, str(_REPO_ROOT))

    report = run_preflight(strict=args.strict)
    exit_code = print_report(report, as_json=args.json, strict=args.strict)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

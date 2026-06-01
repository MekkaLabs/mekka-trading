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

# An empty ``ANTHROPIC_API_KEY=`` / ``OPENAI_API_KEY=`` in the shell environment
# overrides the .env in pydantic-settings and would make the preflight report a
# missing LLM key even when one is configured in .env. Strip only empty values
# so the .env stays authoritative (mirrors run.py).
for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    if os.environ.get(_k, None) == "":
        del os.environ[_k]

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


def _active_exchange() -> str:
    """Resolve the active exchange (settings first, then env, default hyperliquid)."""
    try:
        return _get_settings().active_exchange
    except Exception:
        return os.getenv("ACTIVE_EXCHANGE", "hyperliquid").lower()


def check_env_vars(report: PreflightReport) -> None:
    ex = _active_exchange()
    # Credentials are exchange-specific: only the ACTIVE exchange's keys are
    # required. This keeps the preflight honest for Binance/Bybit instead of
    # demanding Hyperliquid wallet keys that aren't used.
    _per_exchange = {
        "hyperliquid": ["HYPERLIQUID_PRIVATE_KEY", "HYPERLIQUID_WALLET_ADDRESS"],
        "bybit": ["BYBIT_API_KEY", "BYBIT_API_SECRET"],
        "binance": ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
    }
    # Vision uses OpenAI as primary with Anthropic as fallback — at least ONE
    # LLM provider key must be present (not necessarily OpenAI).
    required = list(_per_exchange.get(ex, _per_exchange["hyperliquid"]))
    live_required = [
        "LIVE_TRADING_CONFIRMED",
    ]

    # Resolve a key from the process env first, then from loaded settings (which
    # read .env via pydantic). os.getenv alone false-fails when keys live in
    # .env but aren't exported into the shell — settings is the source of truth.
    _s = None
    try:
        _s = _get_settings()
    except Exception:
        _s = None

    _settings_map = {
        "OPENAI_API_KEY": "openai_api_key",
        "HYPERLIQUID_PRIVATE_KEY": "hyperliquid_private_key",
        "HYPERLIQUID_WALLET_ADDRESS": "hyperliquid_wallet_address",
        "BYBIT_API_KEY": "bybit_api_key",
        "BYBIT_API_SECRET": "bybit_api_secret",
        "BINANCE_API_KEY": "binance_api_key",
        "BINANCE_API_SECRET": "binance_api_secret",
    }

    def _present(key: str) -> bool:
        if os.getenv(key):
            return True
        attr = _settings_map.get(key)
        return bool(attr and _s is not None and getattr(_s, attr, None))

    # At least one LLM provider (OpenAI primary, Anthropic fallback).
    _llm_ok = (
        _present("OPENAI_API_KEY")
        or bool(os.getenv("ANTHROPIC_API_KEY"))
        or bool(_s is not None and getattr(_s, "anthropic_api_key", None))
    )

    missing = [k for k in required if not _present(k)]
    if not _llm_ok:
        missing.append("OPENAI_API_KEY or ANTHROPIC_API_KEY")
    if missing:
        report.fail(
            "env_vars_required",
            f"Missing required credentials for ACTIVE_EXCHANGE={ex}: {', '.join(missing)}",
            fix="Add them to your .env file (or export them) before running.",
        )
    else:
        report.ok("env_vars_required", f"All required credentials present (exchange={ex})")

    live_confirmed = bool(_s and getattr(_s, "live_trading_confirmed", False)) or (
        os.getenv("LIVE_TRADING_CONFIRMED", "").lower() in ("true", "1", "yes")
    )
    if not live_confirmed:
        report.warn(
            "env_vars_live",
            "LIVE_TRADING_CONFIRMED not set (required to actually execute live orders)",
            fix="Set LIVE_TRADING_CONFIRMED=true ONLY after operator sign-off.",
        )
    else:
        report.warn(
            "env_vars_live",
            "LIVE_TRADING_CONFIRMED=true — live orders will be sent. Confirm intentional.",
        )


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
        ex = s.active_exchange
        if ex == "hyperliquid":
            if s.hyperliquid_network == "mainnet":
                report.ok("network", "hyperliquid network=mainnet")
            else:
                report.warn(
                    "network",
                    f"HYPERLIQUID_NETWORK={s.hyperliquid_network!r} (not mainnet)",
                    fix="Set HYPERLIQUID_NETWORK=mainnet for live trading.",
                )
        elif ex == "bybit":
            if not getattr(s, "bybit_testnet", False):
                report.ok("network", "bybit network=mainnet (BYBIT_TESTNET=false)")
            else:
                report.warn(
                    "network",
                    "BYBIT_TESTNET=true (not mainnet)",
                    fix="Set BYBIT_TESTNET=false for live trading.",
                )
        elif ex == "binance":
            if not getattr(s, "binance_testnet", False):
                report.ok("network", "binance network=mainnet (BINANCE_TESTNET=false)")
            else:
                report.warn(
                    "network",
                    "BINANCE_TESTNET=true (not mainnet)",
                    fix="Set BINANCE_TESTNET=false for live trading.",
                )
        else:
            report.warn("network", f"Unknown ACTIVE_EXCHANGE={ex!r}")
    except Exception as exc:
        report.warn("network", f"Could not check network: {exc}")


def check_risk_limits(report: PreflightReport) -> None:
    """Gate de limites de risco conservadores para a 1ª semana de mainnet.

    M5 (2026-06-01 audit): thresholds alinhados ao docs/MAINNET-AUTHORIZATION.md
    (size ≤ 0.1%, lev ≤ 2x, ≤ 3 trades/dia) e promovidos a FAIL em mainnet+live
    (antes eram só WARN e usavam 0.5%). O hard clamp do Batman já força 0.1%/2x;
    o preflight agora exige coerência ANTES de operar com dinheiro real.
    """
    try:
        s = _get_settings()
        live = not bool(s.paper_trading)
        try:
            is_testnet = bool(s.exchange_is_testnet(s.active_exchange))
        except Exception:  # noqa: BLE001
            is_testnet = True
        mainnet_live = live and not is_testnet

        issues = []
        # Recommended first-week caps (conservative — per MAINNET-AUTHORIZATION).
        if s.max_position_size_pct > 0.001:
            issues.append(
                f"max_position_size_pct={s.max_position_size_pct:.4f} "
                f"(recomendado ≤ 0.001 = 0.1% na 1ª semana)"
            )
        if s.max_leverage > 2:
            issues.append(
                f"max_leverage={s.max_leverage}x (recomendado ≤ 2x na 1ª semana)"
            )
        if s.max_trades_per_day > 3:
            issues.append(
                f"max_trades_per_day={s.max_trades_per_day} (recomendado ≤ 3 na 1ª semana)"
            )
        if s.max_open_positions > 2:
            issues.append(
                f"max_open_positions={s.max_open_positions} (recomendado ≤ 2 na 1ª semana)"
            )

        if issues:
            detail = (
                "Limites de risco mais frouxos que a recomendação da 1ª semana:\n  "
                + "\n  ".join(issues)
            )
            fix = "Aperte os limites no .env antes de operar live (size 0.1%, lev 2x, 3 trades/dia)."
            if mainnet_live:
                report.fail("risk_limits", detail, fix=fix)
            else:
                report.warn("risk_limits", detail, fix=fix)
        else:
            report.ok(
                "risk_limits",
                f"Conservador: size={s.max_position_size_pct:.4f} "
                f"lev={s.max_leverage}x trades/dia={s.max_trades_per_day}",
            )
    except Exception as exc:
        report.warn("risk_limits", f"Could not check risk limits: {exc}")


def check_daily_loss_cap(report: PreflightReport) -> None:
    """M1 (2026-06-01 audit): o kill-switch de PERDA ABSOLUTA diária
    (max_daily_loss_usd) tem default 0.0, que o DESLIGA. Em mainnet + live isso
    é inaceitável — força FAIL para que o operador defina um teto antes de
    operar com dinheiro real. Em paper/testnet é só um WARN.
    """
    try:
        s = _get_settings()
        cap = float(getattr(s, "max_daily_loss_usd", 0.0) or 0.0)
        live = not bool(s.paper_trading)
        try:
            is_testnet = bool(s.exchange_is_testnet(s.active_exchange))
        except Exception:  # noqa: BLE001
            is_testnet = True  # conservador
        mainnet_live = live and not is_testnet

        if cap > 0:
            report.ok(
                "daily_loss_cap",
                f"Absolute daily-loss kill-switch armed: MAX_DAILY_LOSS_USD=${cap:,.2f}",
            )
        elif mainnet_live:
            report.fail(
                "daily_loss_cap",
                "MAX_DAILY_LOSS_USD=0 desliga o kill-switch de perda absoluta diária "
                "em MAINNET+LIVE.",
                fix="Defina MAX_DAILY_LOSS_USD > 0 no .env (recomendado: 2–5% do capital).",
            )
        else:
            report.warn(
                "daily_loss_cap",
                "MAX_DAILY_LOSS_USD=0 (kill-switch de perda absoluta desligado) — "
                "tolerável em paper/testnet, obrigatório antes da mainnet.",
                fix="Defina MAX_DAILY_LOSS_USD > 0 antes de ir para mainnet+live.",
            )
    except Exception as exc:  # noqa: BLE001
        report.warn("daily_loss_cap", f"Could not check daily loss cap: {exc}")


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
    ex = _active_exchange()
    hl_active = ex == "hyperliquid"

    # eth-account + hyperliquid SDK are only required when Hyperliquid is the
    # active execution venue. On Binance/Bybit, CCXT is the execution path, so
    # a missing HL SDK is informational, not a hard failure.
    try:
        import eth_account  # noqa: F401
        report.ok("sdk_eth_account", "eth-account installed")
    except ImportError:
        if hl_active:
            report.fail(
                "sdk_eth_account",
                "eth-account not installed (required for Hyperliquid live execution)",
                fix="pip install eth-account",
            )
        else:
            report.ok("sdk_eth_account", f"eth-account not needed (exchange={ex})")

    try:
        from hyperliquid.exchange import Exchange  # noqa: F401
        report.ok("sdk_hyperliquid", "hyperliquid-python-sdk installed")
    except ImportError:
        if hl_active:
            report.fail(
                "sdk_hyperliquid",
                "hyperliquid-python-sdk not installed (required for live execution)",
                fix="pip install hyperliquid-python-sdk",
            )
        else:
            report.ok("sdk_hyperliquid", f"hyperliquid SDK not needed (exchange={ex})")

    # CCXT is required for Binance/Bybit execution; informational for HL.
    try:
        import ccxt  # noqa: F401
        report.ok("sdk_ccxt", f"ccxt installed (version {ccxt.__version__})")
    except ImportError:
        if hl_active:
            report.warn(
                "sdk_ccxt",
                "ccxt not installed — Superman will not be able to fetch market data.",
                fix="pip install ccxt",
            )
        else:
            report.fail(
                "sdk_ccxt",
                f"ccxt not installed (required for {ex} live execution)",
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
    check_daily_loss_cap(report)
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

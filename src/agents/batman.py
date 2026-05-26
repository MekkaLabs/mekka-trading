"""
src/agents/batman.py
====================
Batman — Risk Guardian

Deterministic, no-LLM validator. Sits between Vision and Iron Man.
Receives a `TradingSignal` plus optional context (VolatilityData,
LiquidityData, current portfolio state) and emits a `RiskApproval`.

Hard limits enforced
--------------------
  • size_pct ≤ settings.max_position_size_pct (default 2%)
  • leverage ≤ settings.max_leverage (default 5x)
  • confidence ≥ settings.min_confidence_threshold (default 0.65)
  • risk/reward ≥ settings.min_risk_reward_ratio (default 1.5)
  • daily drawdown ≤ settings.max_daily_drawdown_pct (default 10%)
  • max_open_positions, max_trades_per_day breakers
  • kill_switch flag (file-based or env-based) → instant KILL_SWITCH verdict
  • action == HOLD → REJECTED (nothing to execute)

Adjustments applied (verdict = REDUCED)
---------------------------------------
  • Apply Thor's volatility size multiplier
  • Penalize when Aquaman.liquidity_score < 0.4
  • Cap at hard limits if LLM requested more

Hard rule: Batman NEVER approves anything when paper_trading=False AND
the operator has not explicitly disabled the live-block (intentional friction).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.agents.base import BaseAgent
from src.config.settings import settings
from src.models.market_data import LiquidityData, VolatilityData, VolatilityRegime
from src.models.portfolio import PositionSummary
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Correlation groups — assets that tend to move together in crypto cycles.
# A signal in a LONG direction with N already-open LONGs in the same group
# is flagged as a correlated directional bet.
# ---------------------------------------------------------------------------
_CORRELATION_GROUPS: list[frozenset[str]] = [
    # Majors (BTC + large-caps highly correlated in bull/bear regimes)
    frozenset({"BTC", "ETH", "SOL", "BNB", "AVAX", "MATIC", "ARB", "OP", "APT", "SUI"}),
    # Meme/speculative coins (move together during risk-on episodes)
    frozenset({"DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI"}),
]


def _find_correlation_group(symbol: str) -> frozenset[str] | None:
    """Return the correlation group containing ``symbol``, or None."""
    for group in _CORRELATION_GROUPS:
        if symbol in group:
            return group
    return None


# ---------------------------------------------------------------------------
# Kill switch — operator-controllable file flag
# ---------------------------------------------------------------------------

_KILL_SWITCH_FILE = Path("data/.kill_switch")
_KILL_SWITCH_ENV = "MEKKA_KILL_SWITCH"


def is_kill_switch_active() -> bool:
    """
    Check the kill switch from two sources:
      1. Env var MEKKA_KILL_SWITCH=1 (transient, restart-clearing)
      2. File at data/.kill_switch (persistent, requires manual delete)
    """
    if os.getenv(_KILL_SWITCH_ENV) == "1":
        return True
    return _KILL_SWITCH_FILE.exists()


def engage_kill_switch(reason: str, agent: str = "system") -> None:
    """Persist a kill-switch flag with a structured JSON payload."""
    _KILL_SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reason": reason,
        "agent": agent,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    _KILL_SWITCH_FILE.write_text(json.dumps(payload) + "\n")


def read_kill_switch_metadata() -> dict:
    """
    Read kill-switch metadata. Returns empty dict if not engaged.
    Handles legacy plain-text files gracefully (pre-squad-fixes format).
    """
    if not _KILL_SWITCH_FILE.exists():
        return {}
    raw = _KILL_SWITCH_FILE.read_text().strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Legacy format: plain text reason
        return {"reason": raw, "agent": "legacy", "timestamp_utc": None}


def release_kill_switch() -> None:
    """Manually clear the persistent kill-switch."""
    if _KILL_SWITCH_FILE.exists():
        _KILL_SWITCH_FILE.unlink()


# ---------------------------------------------------------------------------
# Batman Agent
# ---------------------------------------------------------------------------


class Batman(BaseAgent[RiskApproval]):
    """
    Risk Guardian — last gate before execution.

    Usage:
        approval = await Batman().run(
            signal=trading_signal,
            volatility=vol_data,           # optional
            liquidity=liq_data,            # optional
            current_drawdown_pct=0.04,     # optional, from portfolio state
            open_positions=2,              # optional
            trades_today=4,                # optional
        )
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Batman",
            role="Risk Guardian — deterministic validation gate",
            # Batman roda ~15 gates, alguns async (MTF, funding, ATR) que fazem
            # network. Cada um fail-open com seu próprio timeout interno
            # (~5-10s). Worst case empilhado: ~30s. Acima disso é hang real.
            timeout_s=45.0,
        )

    # ------------------------------------------------------------------
    # Gate helpers (#73 refactor — incremental Extract Method).
    #
    # Cada helper extrai UM gate do _run() preservando a lógica BYTE-A-BYTE.
    # Contract:
    #   - Recebe state mutável (reasons, breached) — mesma referência do _run
    #   - Retorna ``RiskApproval`` se o gate REJECT (short-circuit)
    #   - Retorna ``None`` para continuar o pipeline
    # Nenhum helper introduz nova lógica de risco — só muda escopo.
    # Todos são pure-sync exceto onde o gate original era async.
    # ------------------------------------------------------------------

    def _gate_3m_min_notional(
        self,
        signal: TradingSignal,
        equity_usd: float,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3m — Minimum trade notional (Story 096).

        Reject signals that would produce a micro-position smaller than
        min_trade_notional_usd (fees would exceed potential PnL).
        """
        if settings.min_trade_notional_usd > 0 and equity_usd > 0:
            _planned_notional = equity_usd * signal.size_pct * signal.leverage
            if _planned_notional < settings.min_trade_notional_usd:
                reasons.append(
                    f"[3m] Min notional: planned ${_planned_notional:.2f} < "
                    f"min ${settings.min_trade_notional_usd:.2f} — micro-position rejected."
                )
                breached.append("min_trade_notional_usd")
                return RiskApproval(
                    symbol=symbol,
                    verdict=RiskVerdict.REJECTED,
                    reasons=reasons,
                    breached_limits=breached,
                )
        return None

    async def _gate_3l_max_trades_per_symbol_day(
        self,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3l — Max trades per symbol per day (Story 086).

        Prevents over-trading a single symbol within the same UTC day.
        Counts FILLED + PAPER trades already executed today for ``symbol``.
        Fails open: DB error → gate skipped silently.
        """
        if settings.max_trades_per_symbol_day < 99:
            try:
                from src.persistence.repository import MekkaRepository as _Repo  # noqa: WPS433
                _sym_today = await _Repo.count_trades_today_for_symbol(symbol)
                if _sym_today >= settings.max_trades_per_symbol_day:
                    reasons.append(
                        f"[3l] Max trades/symbol/day: {symbol} already has "
                        f"{_sym_today} trade(s) today "
                        f"(limit={settings.max_trades_per_symbol_day})."
                    )
                    breached.append("max_trades_per_symbol_day")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                    )
                else:
                    reasons.append(
                        f"[3l] Trades/{symbol}/day OK: {_sym_today}/{settings.max_trades_per_symbol_day}"
                    )
            except Exception as _tpsd_exc:  # noqa: BLE001
                self._log.debug("[Batman] Max trades/symbol/day gate skipped: %s", _tpsd_exc)
        return None

    async def _gate_3n_symbol_weekly_drawdown(
        self,
        equity_usd: float,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3n — Max drawdown per symbol per week (Story 100).

        Rejects new entries in a symbol that has already lost more than
        max_symbol_drawdown_pct × equity this UTC week.
        Fails open: DB error → gate skipped silently.
        """
        if settings.max_symbol_drawdown_pct < 1.0 and equity_usd > 0:
            try:
                from src.persistence.repository import MekkaRepository as _Repo2  # noqa: WPS433
                _sym_week_pnl = await _Repo2.get_symbol_week_pnl(symbol)
                _sym_draw_limit = -(equity_usd * settings.max_symbol_drawdown_pct)
                if _sym_week_pnl < _sym_draw_limit:
                    reasons.append(
                        f"[3n] Symbol weekly drawdown: {symbol} PnL this week "
                        f"${_sym_week_pnl:.2f} < limit ${_sym_draw_limit:.2f} "
                        f"({settings.max_symbol_drawdown_pct:.1%} of equity)."
                    )
                    breached.append("max_symbol_drawdown_pct")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                    )
            except Exception as _msd_exc:  # noqa: BLE001
                self._log.debug("[Batman] Symbol weekly drawdown gate skipped: %s", _msd_exc)
        return None

    async def _gate_3h_mtf_confluence(
        self,
        signal: TradingSignal,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> tuple[Optional[RiskApproval], TradingSignal]:
        """Gate 3h — Multi-Timeframe Confluence (Story 072).

        Checks that the prevailing trend on a higher timeframe (default 4h)
        agrees with the signal direction before approving entry.

        Rules:
          - LONG signal + DOWNTREND on HTF → REDUCED (size × 0.6) or REJECTED
          - SHORT signal + UPTREND on HTF  → REDUCED (size × 0.6) or REJECTED
          - NEUTRAL HTF  → pass-through (no penalty)
          - Confirming trend → positive note in reasons

        The hard-reject mode is controlled by settings.mtf_reject_on_opposite.
        Falls open on any error — never blocks due to infra failure.

        Returns:
          (RiskApproval or None, possibly-modified signal)
        """
        if not settings.mtf_confluence_enabled:
            return None, signal
        try:
            from src.analytics.trend import compute_htf_trend as _htf, HTFTrend as _HTFTrend  # noqa: WPS433
            _htf_trend = await _htf(
                symbol=symbol,
                interval=settings.mtf_interval,
                lookback=settings.mtf_lookback_candles,
            )
            _sig_dir = signal.action.value.lower()  # "long" or "short"
            _opposing = (
                (_sig_dir == "long"  and _htf_trend == _HTFTrend.DOWNTREND) or
                (_sig_dir == "short" and _htf_trend == _HTFTrend.UPTREND)
            )
            _confirming = (
                (_sig_dir == "long"  and _htf_trend == _HTFTrend.UPTREND) or
                (_sig_dir == "short" and _htf_trend == _HTFTrend.DOWNTREND)
            )

            if _opposing:
                if settings.mtf_reject_on_opposite:
                    reasons.append(
                        f"MTF Confluence VETO: {_sig_dir.upper()} signal opposes "
                        f"{settings.mtf_interval} trend ({_htf_trend.value}) — hard reject."
                    )
                    breached.append("mtf_confluence_reject")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                        metadata={"htf_trend": _htf_trend.value, "htf_interval": settings.mtf_interval},
                    ), signal
                else:
                    _mtf_mult = 0.60
                    _prev_size = signal.size_pct
                    signal = signal.model_copy(
                        update={"size_pct": round(signal.size_pct * _mtf_mult, 6)}
                    )
                    reasons.append(
                        f"MTF Confluence WARNING: {_sig_dir.upper()} opposes "
                        f"{settings.mtf_interval} {_htf_trend.value} → "
                        f"size ×{_mtf_mult:.0%} ({_prev_size:.4f} → {signal.size_pct:.4f})"
                    )
                    breached.append("mtf_confluence_penalty")
            elif _confirming:
                reasons.append(
                    f"MTF Confluence OK: {_sig_dir.upper()} confirmed by "
                    f"{settings.mtf_interval} {_htf_trend.value}."
                )
            else:
                reasons.append(
                    f"MTF Confluence NEUTRAL: {settings.mtf_interval} trend is "
                    f"{_htf_trend.value} — no confluence bonus or penalty."
                )
        except Exception as _mtf_exc:  # noqa: BLE001
            self._log.debug(f"[Batman] MTF confluence gate skipped: {_mtf_exc}")
        return None, signal

    async def _gate_3i_funding_rate(
        self,
        signal: TradingSignal,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> tuple[Optional[RiskApproval], TradingSignal]:
        """Gate 3i — Funding Rate (Story 075).

        Extreme funding rates signal overcrowded positioning that is
        expensive to hold and prone to violent reversals (long/short squeezes).

        Rules (configurable thresholds):
          LONG:  rate ≥ block → REJECT; rate ≥ warn → size × 0.60
          SHORT: rate ≤ block → REJECT; rate ≤ warn → size × 0.60

        Falls open on any network/cache error — never blocks due to infra failure.

        Returns:
          (RiskApproval or None, possibly-modified signal)
        """
        if not settings.funding_gate_enabled:
            return None, signal
        try:
            from src.analytics.funding import get_funding_rate_pct as _get_fr  # noqa: WPS433
            _fr_pct = await _get_fr(symbol)
            if _fr_pct is not None:
                _sig_dir = signal.action.value.lower()
                _fr_label = f"{_fr_pct:+.5f}%/8h"

                if _sig_dir == "long":
                    if _fr_pct >= settings.funding_long_block_pct:
                        reasons.append(
                            f"Funding Rate VETO: rate {_fr_label} ≥ "
                            f"block threshold {settings.funding_long_block_pct:+.4f}% "
                            f"— LONG is extremely expensive, high squeeze risk."
                        )
                        breached.append("funding_rate_block")
                        return RiskApproval(
                            symbol=symbol,
                            verdict=RiskVerdict.REJECTED,
                            reasons=reasons,
                            breached_limits=breached,
                            metadata={"funding_rate_pct": _fr_pct},
                        ), signal
                    elif _fr_pct >= settings.funding_long_warn_pct:
                        _fr_mult = 0.60
                        _prev_fr = signal.size_pct
                        signal = signal.model_copy(
                            update={"size_pct": round(signal.size_pct * _fr_mult, 6)}
                        )
                        reasons.append(
                            f"Funding Rate WARNING: rate {_fr_label} elevated for LONG "
                            f"(≥ warn threshold {settings.funding_long_warn_pct:+.4f}%) "
                            f"→ size ×{_fr_mult:.0%} ({_prev_fr:.4f} → {signal.size_pct:.4f})"
                        )
                        breached.append("funding_rate_penalty")
                    else:
                        reasons.append(f"Funding Rate OK: {_fr_label} within normal range for LONG.")

                elif _sig_dir == "short":
                    if _fr_pct <= settings.funding_short_block_pct:
                        reasons.append(
                            f"Funding Rate VETO: rate {_fr_label} ≤ "
                            f"block threshold {settings.funding_short_block_pct:+.4f}% "
                            f"— SHORT is extremely expensive, high short-squeeze risk."
                        )
                        breached.append("funding_rate_block")
                        return RiskApproval(
                            symbol=symbol,
                            verdict=RiskVerdict.REJECTED,
                            reasons=reasons,
                            breached_limits=breached,
                            metadata={"funding_rate_pct": _fr_pct},
                        ), signal
                    elif _fr_pct <= settings.funding_short_warn_pct:
                        _fr_mult = 0.60
                        _prev_fr = signal.size_pct
                        signal = signal.model_copy(
                            update={"size_pct": round(signal.size_pct * _fr_mult, 6)}
                        )
                        reasons.append(
                            f"Funding Rate WARNING: rate {_fr_label} elevated for SHORT "
                            f"(≤ warn threshold {settings.funding_short_warn_pct:+.4f}%) "
                            f"→ size ×{_fr_mult:.0%} ({_prev_fr:.4f} → {signal.size_pct:.4f})"
                        )
                        breached.append("funding_rate_penalty")
                    else:
                        reasons.append(f"Funding Rate OK: {_fr_label} within normal range for SHORT.")
        except Exception as _fr_exc:  # noqa: BLE001
            self._log.debug(f"[Batman] Funding rate gate skipped: {_fr_exc}")
        return None, signal

    async def _gate_3p_directional_bias(
        self,
        signal: TradingSignal,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3p — Directional bias guard (Story 106).

        Reject new entries when the last N completed trades were all in
        the same direction (all LONG or all SHORT), indicating the
        model may have a runaway directional bias.
        Fails open: DB error → gate skipped silently.
        """
        if settings.max_same_direction_streak < 99:
            try:
                from src.persistence.repository import MekkaRepository as _Repo3p  # noqa: WPS433
                _dir_trades = await _Repo3p.list_recent_closed_trades(
                    limit=settings.max_same_direction_streak
                )
                if len(_dir_trades) >= settings.max_same_direction_streak:
                    _sides = [
                        (getattr(t, "side", "") or "").upper()
                        for t in _dir_trades[: settings.max_same_direction_streak]
                    ]
                    if len(set(_sides)) == 1 and _sides[0] in ("LONG", "SHORT"):
                        _dom_side = _sides[0]
                        _new_side = (signal.action.value if hasattr(signal.action, "value") else str(signal.action)).upper()
                        if _new_side == _dom_side:
                            reasons.append(
                                f"[3p] Directional bias: últimos "
                                f"{settings.max_same_direction_streak} trades todos "
                                f"{_dom_side} — novo sinal {_new_side} rejeitado."
                            )
                            breached.append("max_same_direction_streak")
                            # Story 112 — audit gate rejection
                            try:
                                await _Repo3p.log_event(
                                    agent="Batman", event="GATE_REJECTED", severity="WARNING",
                                    symbol=symbol,
                                    message=reasons[-1],
                                    payload={"gate_id": "3p", "symbol": symbol,
                                             "reason": reasons[-1], "breached": list(breached)},
                                )
                            except Exception:  # noqa: BLE001
                                pass
                            return RiskApproval(
                                symbol=symbol,
                                verdict=RiskVerdict.REJECTED,
                                reasons=reasons,
                                breached_limits=breached,
                            )
            except Exception as _db_exc:  # noqa: BLE001
                self._log.debug("[Batman] Directional bias gate skipped: %s", _db_exc)
        return None

    async def _gate_3q_min_atr(
        self,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3q — Min ATR filter (Story 110).

        Reject signals when the symbol's ATR% is below min_atr_pct,
        indicating a paused/quiet market with insufficient volatility.
        0.0 (default) disables the gate. Fails open on errors.
        Emits GATE_REJECTED audit (Story 112).
        """
        if settings.min_atr_pct > 0.0:
            try:
                from src.analytics.atr import compute_atr_pct as _atr3q  # noqa: WPS433
                _current_atr_3q = await _atr3q(
                    symbol=symbol,
                    lookback=settings.atr_lookback_candles,
                )
                if _current_atr_3q is not None and _current_atr_3q < settings.min_atr_pct:
                    reasons.append(
                        f"[3q] Min ATR: ATR% {_current_atr_3q:.4f} < mínimo "
                        f"{settings.min_atr_pct:.4f} — mercado parado."
                    )
                    breached.append("min_atr_pct")
                    # Story 112 — audit gate rejection
                    try:
                        from src.persistence.repository import MekkaRepository as _Repo3q  # noqa: WPS433
                        await _Repo3q.log_event(
                            agent="Batman", event="GATE_REJECTED", severity="WARNING",
                            symbol=symbol,
                            message=reasons[-1],
                            payload={"gate_id": "3q", "symbol": symbol,
                                     "reason": reasons[-1], "breached": list(breached),
                                     "atr_pct": round(_current_atr_3q, 6),
                                     "min_atr_pct": settings.min_atr_pct},
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                    )
            except Exception as _atr3q_exc:  # noqa: BLE001
                self._log.debug("[Batman] Min ATR gate skipped: %s", _atr3q_exc)
        return None

    def _gate_3j_trading_hours(
        self,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3j — Trading Hours (Story 076).

        Restricts new entries to a configured UTC hour window to avoid
        low-liquidity periods (e.g., Asian pre-session 00:00-06:59 UTC).

        Set trading_hours_enabled=True in settings to activate.
        Default window: 07:00-23:59 UTC (blocks 00:00-06:59 UTC).
        Does not mutate signal — sync helper.
        """
        if not settings.trading_hours_enabled:
            return None
        from datetime import datetime, timezone as _tz  # noqa: WPS433
        _now_h = datetime.now(_tz.utc).hour
        _start = settings.trading_hours_start_utc
        _end   = settings.trading_hours_end_utc

        # Handle overnight windows (e.g. start=22, end=6)
        if _start <= _end:
            _in_window = _start <= _now_h <= _end
        else:
            _in_window = _now_h >= _start or _now_h <= _end

        if not _in_window:
            _next_open = _start
            reasons.append(
                f"Trading Hours Gate: current UTC hour {_now_h:02d}:xx is outside "
                f"the allowed window {_start:02d}:00-{_end:02d}:59 UTC. "
                f"Next open: {_next_open:02d}:00 UTC."
            )
            breached.append("trading_hours")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
                metadata={"current_hour_utc": _now_h, "window": f"{_start:02d}-{_end:02d}"},
            )
        else:
            reasons.append(
                f"Trading Hours OK: {_now_h:02d}:xx UTC within window "
                f"{_start:02d}:00-{_end:02d}:59 UTC."
            )
        return None

    async def _gate_3o_consecutive_losses(
        self,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3o — Max consecutive losses (Story 102).

        Reject new entries when the last N completed trades across all
        symbols were losses (realized_pnl < 0). Resets on any win/TP.
        Fails open: DB error → gate skipped silently.
        Emits GATE_REJECTED audit (Story 112).
        """
        if settings.max_consecutive_losses < 99:
            try:
                from src.persistence.repository import MekkaRepository as _Repo3o  # noqa: WPS433
                _recent_trades = await _Repo3o.list_recent_closed_trades(
                    limit=settings.max_consecutive_losses
                )
                if len(_recent_trades) >= settings.max_consecutive_losses:
                    _all_losses = all(
                        (getattr(t, "realized_pnl_usd", None) or 0.0) < 0
                        for t in _recent_trades[: settings.max_consecutive_losses]
                    )
                    if _all_losses:
                        reasons.append(
                            f"[3o] {settings.max_consecutive_losses} perdas consecutivas "
                            f"detectadas — pausando novas entradas até próxima vitória."
                        )
                        breached.append("max_consecutive_losses")
                        # Story 112 — audit gate rejection
                        try:
                            await _Repo3o.log_event(
                                agent="Batman", event="GATE_REJECTED", severity="WARNING",
                                symbol=symbol,
                                message=reasons[-1],
                                payload={"gate_id": "3o", "symbol": symbol,
                                         "reason": reasons[-1], "breached": list(breached)},
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        return RiskApproval(
                            symbol=symbol,
                            verdict=RiskVerdict.REJECTED,
                            reasons=reasons,
                            breached_limits=breached,
                        )
            except Exception as _cl_exc:  # noqa: BLE001
                self._log.debug("[Batman] Consecutive losses gate skipped: %s", _cl_exc)
        return None

    def _gate_3b_total_capital_cap(
        self,
        signal: TradingSignal,
        symbol: str,
        equity_usd: float,
        running_notional_usd: float,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3b — Total capital cap (Story 029a — Safety Net).

        Computes the notional this signal would add (size_pct * leverage * equity).
        Checks BEFORE size adjustments so the cap is on Vision's intent, not on
        the post-Thor-multiplier value. If the intent itself blows the cap, we
        reject regardless of how much Thor would have shrunk it.

        Two caps evaluated when equity > 0:
          - Absolute cap (max_total_notional_usd) — takes precedence when set
          - Percentage cap (max_total_capital_pct of equity) — always evaluated
        """
        if equity_usd > 0:
            new_notional = equity_usd * signal.size_pct * signal.leverage
            projected_total = running_notional_usd + new_notional

            # Absolute cap takes precedence when set
            if settings.max_total_notional_usd is not None:
                if projected_total > settings.max_total_notional_usd:
                    reasons.append(
                        f"Projected total notional ${projected_total:,.2f} would "
                        f"exceed absolute cap ${settings.max_total_notional_usd:,.2f}"
                    )
                    breached.append("max_total_notional_usd")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                    )

            # Percentage cap (always evaluated when equity > 0)
            cap_pct = settings.max_total_capital_pct
            cap_usd = equity_usd * cap_pct
            if projected_total > cap_usd:
                reasons.append(
                    f"Projected total notional ${projected_total:,.2f} would "
                    f"exceed {cap_pct:.1%} of equity (${cap_usd:,.2f})"
                )
                breached.append("max_total_capital_pct")
                return RiskApproval(
                    symbol=symbol,
                    verdict=RiskVerdict.REJECTED,
                    reasons=reasons,
                    breached_limits=breached,
                )
        return None

    def _gate_3c_correlation(
        self,
        signal: TradingSignal,
        symbol: str,
        current_positions: Optional[list[PositionSummary]],
        reasons: list[str],
        breached: list[str],
    ) -> tuple[Optional[RiskApproval], TradingSignal]:
        """Gate 3c — Correlation gate (Story 057).

        Prevents the system from building a stack of same-direction positions
        in highly correlated crypto assets (e.g. 3× LONG in BTC, ETH, SOL
        simultaneously = a single unhedged market bet).

        Logic:
          - Find how many OPEN positions share the new signal's direction
            AND belong to the same correlation group.
          - If count >= reject_threshold  -> hard REJECT
          - If count >= penalty_threshold -> REDUCED with 50/60% size cut

        Returns:
          (RiskApproval or None, possibly-modified signal)
        """
        if current_positions:
            from src.config.runtime_mode import get_params as _get_mode_params  # noqa: WPS433
            _mp = _get_mode_params()
            _penalty_threshold: int = int(_mp.get("correlation_penalty_threshold", 1))
            _reject_threshold: int = int(_mp.get("correlation_reject_threshold", 2))

            _group = _find_correlation_group(signal.symbol)
            _new_side = signal.action.value.lower()  # "long" or "short"

            # Count open positions that are same-direction AND in the same group,
            # excluding the signal's own symbol (already checked by max_open_positions).
            _corr_count = 0
            for _pos in current_positions:
                _pos_sym = _pos.symbol.upper()
                if _pos_sym == signal.symbol:
                    continue  # same asset — not a correlation risk
                _pos_side = _pos.side.lower()
                if _pos_side != _new_side:
                    continue  # opposite direction — not correlated risk
                if _group and _pos_sym in _group:
                    _corr_count += 1

            _mode_label = _mp.get("label", "")
            if _corr_count >= _reject_threshold:
                reasons.append(
                    f"Correlation gate: {_corr_count} same-direction positions already open "
                    f"in correlated group (≥ reject threshold {_reject_threshold}) [{_mode_label}]"
                )
                breached.append("correlation_reject")
                return RiskApproval(
                    symbol=symbol,
                    verdict=RiskVerdict.REJECTED,
                    reasons=reasons,
                    breached_limits=breached,
                ), signal
            elif _corr_count >= _penalty_threshold:
                # Apply size reduction — severity increases with count
                _penalty_mult = max(0.4, 1.0 - (_corr_count * 0.3))
                _prev_size = signal.size_pct
                signal = signal.model_copy(
                    update={"size_pct": round(signal.size_pct * _penalty_mult, 6)}
                )
                reasons.append(
                    f"Correlation penalty: {_corr_count} same-direction position(s) in correlated "
                    f"group → size × {_penalty_mult:.0%} ({_prev_size:.4f} → {signal.size_pct:.4f}) "
                    f"[{_mode_label}]"
                )
                breached.append("correlation_penalty")
        return None, signal

    async def _gate_3d_episodic_memory(
        self,
        signal: TradingSignal,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> tuple[Optional[RiskApproval], TradingSignal]:
        """Gate 3d — Episodic Memory gate (Story 063).

        Query AgentMemoryStore for resolved historical patterns that match
        the signal's fingerprint (symbol + direction + RSI bucket + trend).

        Rules:
          - <  5 resolved memories            -> skip (insufficient data)
          - win_rate < 30% AND total >= 8     -> hard REJECT (strong failure)
          - win_rate < 45% AND total >= 5     -> warning + size reduced 20%
          - win_rate > 65% AND total >= 5     -> positive note (no override)

        Never blocks on DB error — fails open (APPROVED).

        Returns:
          (RiskApproval or None, possibly-modified signal)
        """
        try:
            from src.persistence.agent_memory import AgentMemoryStore as _AMS  # noqa: WPS433
            _rsi_raw = signal.metadata.get("rsi") if signal.metadata else None
            _trend_raw = signal.metadata.get("trend", "NEUTRAL") if signal.metadata else "NEUTRAL"
            _mem_ctx = await _AMS.query_similar(
                symbol=symbol,
                action=signal.action.value,
                rsi=float(_rsi_raw) if _rsi_raw is not None else None,
                trend=str(_trend_raw),
                limit=15,
            )
            _wr = _mem_ctx.win_rate_pct  # None if no decided trades

            if _mem_ctx.total >= 5 and _wr is not None:
                _snippet = _AMS.build_context_snippet(_mem_ctx)
                if _wr < 30.0 and _mem_ctx.total >= 8:
                    reasons.append(
                        f"Episodic memory VETO: win rate {_wr:.1f}% "
                        f"({_mem_ctx.wins}W/{_mem_ctx.losses}L) "
                        f"over {_mem_ctx.total} similar patterns — "
                        f"historical performance too weak to proceed."
                    )
                    breached.append("memory_veto")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                        metadata={"memory_context": _snippet},
                    ), signal
                elif _wr < 45.0:
                    signal = signal.model_copy(
                        update={"size_pct": round(signal.size_pct * 0.80, 6)}
                    )
                    reasons.append(
                        f"Episodic memory WARNING: win rate {_wr:.1f}% "
                        f"({_mem_ctx.wins}W/{_mem_ctx.losses}L / {_mem_ctx.total} patterns) "
                        f"→ size reduced 20%."
                    )
                    breached.append("memory_caution")
                else:
                    reasons.append(
                        f"Episodic memory OK: win rate {_wr:.1f}% "
                        f"({_mem_ctx.wins}W/{_mem_ctx.losses}L / {_mem_ctx.total} patterns)."
                    )
        except Exception as _mem_exc:  # noqa: BLE001
            self._log.debug(f"[Batman] Episodic memory gate skipped: {_mem_exc}")
        return None, signal

    async def _gate_3f_reentry_cooldown(
        self,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3f — Re-entry Cooldown Guard (Story 069).

        After Cyclops closes a position via SL, the same symbol is locked
        for ``reentry_cooldown_minutes`` minutes. Prevents revenge trading.

        Falls open on any DB error (never blocks due to infra failure).
        """
        if settings.reentry_cooldown_minutes > 0:
            try:
                from src.persistence.repository import MekkaRepository as _Repo  # noqa: WPS433
                _sl_time = await _Repo.get_last_sl_close_time(
                    symbol=symbol,
                    lookback_minutes=settings.reentry_cooldown_minutes,
                )
                if _sl_time is not None:
                    from datetime import datetime as _dt, timezone as _tz  # noqa: WPS433
                    _elapsed_min = (_dt.now(_tz.utc) - _sl_time).total_seconds() / 60
                    _remaining_min = round(settings.reentry_cooldown_minutes - _elapsed_min, 1)
                    reasons.append(
                        f"Re-entry cooldown: {symbol} had SL close {_elapsed_min:.1f}min ago "
                        f"(cooldown={settings.reentry_cooldown_minutes}min, "
                        f"remaining={max(0, _remaining_min):.1f}min)"
                    )
                    breached.append("reentry_cooldown")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                        metadata={
                            "last_sl_close_utc": _sl_time.isoformat(),
                            "elapsed_minutes": round(_elapsed_min, 2),
                            "cooldown_minutes": settings.reentry_cooldown_minutes,
                        },
                    )
            except Exception as _cd_exc:  # noqa: BLE001
                self._log.debug(f"[Batman] Re-entry cooldown gate skipped: {_cd_exc}")
        return None

    async def _gate_3g_symbol_blacklist(
        self,
        symbol: str,
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3g — Symbol Strike Counter + Auto-Blacklist (Story 071).

        If a symbol has hit its SL ``symbol_strike_limit`` times in a row,
        it is automatically blocked for ``symbol_blacklist_hours`` hours.
        A Telegram CRITICAL alert is fired on first blacklist.

        Falls open on any error (DB, file I/O, Telegram).
        """
        try:
            from src.persistence.repository import MekkaRepository as _Repo  # noqa: WPS433
            _strike_count = await _Repo.count_consecutive_sl_hits(symbol=symbol)
            if _strike_count >= settings.symbol_strike_limit:
                import json as _json  # noqa: WPS433
                from pathlib import Path as _Path  # noqa: WPS433
                from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2  # noqa: WPS433

                _bl_path = _Path("data") / f".blacklist_{symbol.upper()}.json"
                _now2 = _dt2.now(_tz2.utc)
                _bl_active = False
                _bl_data: dict = {}

                if _bl_path.exists():
                    try:
                        _bl_data = _json.loads(_bl_path.read_text())
                        _bl_since = _dt2.fromisoformat(_bl_data.get("since", ""))
                        _bl_expires = _bl_since + _td2(hours=settings.symbol_blacklist_hours)
                        if _now2 < _bl_expires:
                            _bl_active = True
                    except Exception:  # noqa: BLE001
                        pass

                if not _bl_active:
                    # Fresh blacklist — write file + fire Telegram alert
                    _bl_data = {
                        "symbol": symbol.upper(),
                        "since": _now2.isoformat(),
                        "expires": (_now2 + _td2(hours=settings.symbol_blacklist_hours)).isoformat(),
                        "consecutive_sl_hits": _strike_count,
                    }
                    try:
                        _bl_path.parent.mkdir(parents=True, exist_ok=True)
                        _bl_path.write_text(_json.dumps(_bl_data, indent=2))
                    except Exception:  # noqa: BLE001
                        pass
                    # Telegram CRITICAL alert
                    try:
                        from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                        await TelegramAlerter().send_message(
                            f"🚫 *BLACKLIST ATIVADO* — `{symbol.upper()}`\n"
                            f"*{_strike_count} SLs consecutivos* sem TP intermediário.\n"
                            f"Símbolo bloqueado por {settings.symbol_blacklist_hours:.0f}h "
                            f"(expira: {_bl_data['expires'][:16]} UTC).",
                            level="CRITICAL",
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    self._log.warning(
                        "[Batman] [3g] %s BLACKLISTED — %d consecutive SL hits "
                        "(limit=%d, duration=%.0fh)",
                        symbol, _strike_count, settings.symbol_strike_limit,
                        settings.symbol_blacklist_hours,
                    )

                # Either way: block this entry
                _expires_str = _bl_data.get("expires", "?")[:16]
                reasons.append(
                    f"Symbol blacklist: {symbol} hit {_strike_count} consecutive SL(s) "
                    f"(limit={settings.symbol_strike_limit}) → blocked until {_expires_str} UTC"
                )
                breached.append("symbol_blacklist")
                return RiskApproval(
                    symbol=symbol,
                    verdict=RiskVerdict.REJECTED,
                    reasons=reasons,
                    breached_limits=breached,
                    metadata={"consecutive_sl_hits": _strike_count, "blacklist": _bl_data},
                )
        except Exception as _bl_exc:  # noqa: BLE001
            self._log.debug(f"[Batman] Symbol blacklist gate skipped: {_bl_exc}")
        return None

    def _gate_3k_pyramid_bypass(
        self,
        signal: TradingSignal,
        symbol: str,
        open_positions: int,
        current_positions: Optional[list[PositionSummary]],
        reasons: list[str],
        breached: list[str],
    ) -> tuple[bool, TradingSignal]:
        """Gate 3k — Pyramid / Scale-In Bypass (Story 080).

        Before hard-rejecting for max_open_positions, check whether this
        signal is a pyramid opportunity: same symbol, same direction, and
        the existing position is already profitable.

        Conditions for pyramid allowance:
          1. settings.pyramid_enabled is True
          2. open_positions >= settings.max_open_positions (would otherwise block)
          3. current_positions contains a position in 'symbol'
          4. That position is in the SAME direction as signal.action
          5. That position has unrealized_pnl_usd >= pyramid_min_profit_pct% gain

        Effect: size is capped at pyramid_max_add_pct, the caller may then
        skip the max_open_positions gate for this symbol.

        Returns:
          (is_pyramid_entry, possibly-modified signal)
        """
        _is_pyramid_entry = False
        if (
            settings.pyramid_enabled
            and open_positions >= settings.max_open_positions
            and current_positions
        ):
            try:
                _signal_side = signal.action.value.lower()  # 'long' or 'short'
                for _pos in current_positions:
                    _pos_sym = (getattr(_pos, "symbol", "") or "").upper()
                    _pos_side = (getattr(_pos, "side", "") or "").lower()
                    if _pos_sym != symbol.upper():
                        continue
                    if _pos_side != _signal_side:
                        continue
                    # Check profitability threshold
                    _unreal_pnl = float(getattr(_pos, "unrealized_pnl_usd", 0) or 0)
                    _entry_p = float(getattr(_pos, "entry_price", 0) or 0)
                    _qty = float(getattr(_pos, "size", 0) or 0)
                    _notional = _entry_p * _qty if _entry_p > 0 and _qty > 0 else 0.0
                    _profit_pct = (_unreal_pnl / _notional * 100) if _notional > 0 else 0.0
                    _min_pct = settings.pyramid_min_profit_pct
                    if _profit_pct >= _min_pct:
                        _is_pyramid_entry = True
                        reasons.append(
                            f"[3k] Pyramid entry approved: existing {symbol} {_signal_side.upper()} "
                            f"position at +{_profit_pct:.2f}% unrealised profit "
                            f"(min={_min_pct:.1f}%) — scale-in with capped size."
                        )
                        # Cap size at pyramid_max_add_pct
                        if signal.size_pct > settings.pyramid_max_add_pct:
                            signal = signal.model_copy(
                                update={"size_pct": settings.pyramid_max_add_pct}
                            )
                            breached.append("pyramid_size_cap")
                        break
                    else:
                        reasons.append(
                            f"[3k] Pyramid skipped: {symbol} unrealised profit "
                            f"{_profit_pct:.2f}% < min {_min_pct:.1f}% — position not profitable enough."
                        )
            except Exception as _pyr_exc:  # noqa: BLE001
                self._log.debug("[Batman] Pyramid gate error (fail-open): %s", _pyr_exc)
        return _is_pyramid_entry, signal

    def _gate_3r_flash_divergence(
        self,
        signal: TradingSignal,
        analysis: Optional[object],
        reasons: list[str],
    ) -> float:
        """Gate 3r — Flash Momentum Divergence (Story 247).

        SOFT gate — adjusts size but does NOT veto the trade.
        When Flash signals STRONG momentum opposing the trade direction,
        returns the reduction pct (default 30%) for the section-5 size
        adjuster to apply. Fails open with 0.0 on any error.

        Returns:
          Reduction pct in [0.0, 1.0). 0.0 means "no reduction".
        """
        if analysis is None:
            return 0.0
        try:
            _momentum = getattr(analysis, "momentum", None)
            if _momentum is None:
                return 0.0
            from src.models.signal import MomentumDirection  # noqa: WPS433
            _mom_dir = getattr(_momentum, "direction", None)
            _mom_strong = getattr(_momentum, "is_strong", False)
            _flash_reduction = getattr(settings, "flash_divergence_size_reduction", 0.30)
            _signal_is_long = signal.action.upper() == "LONG"
            _diverges = (
                _mom_strong
                and _mom_dir is not None
                and (
                    (_signal_is_long and _mom_dir == MomentumDirection.DOWN)
                    or (not _signal_is_long and _mom_dir == MomentumDirection.UP)
                )
            )
            if _diverges:
                reasons.append(
                    f"[3r] Flash divergence: signal={signal.action.upper()}, "
                    f"momentum={_mom_dir.value} STRONG — "
                    f"size reduced by {_flash_reduction:.0%}."
                )
                return _flash_reduction
            if _mom_strong and _mom_dir is not None:
                reasons.append(
                    f"[3r] Flash confirms {signal.action.upper()}: "
                    f"momentum={_mom_dir.value} STRONG — no size adjustment."
                )
            return 0.0
        except Exception as _flash_exc:  # noqa: BLE001
            self._log.debug("[Batman] Flash divergence gate skipped: %s", _flash_exc)
            return 0.0

    def _gate_5b_market_regime(
        self,
        signal: TradingSignal,
        symbol: str,
        adjusted_size: float,
        adjusted_leverage: int,
        reasons: list[str],
        breached: list[str],
    ) -> tuple[Optional[RiskApproval], float, int]:
        """Gate 5b — Market Regime Gate (Story 148).

        Uses MarketRegimeDetector output (signal.metadata["market_regime"])
        to apply regime-aware adjustments:

          BEAR:     leverage capped to bear_regime_max_leverage
                    LONG rejected when signal RSI >= bear_long_max_rsi
          VOLATILE: size × volatile_regime_size_multiplier
          BULL:     no restrictions
          SIDEWAYS: no restrictions

        Fails open when metadata is missing or detector is unavailable.

        Returns:
          (RiskApproval or None, new adjusted_size, new adjusted_leverage)
        """
        if not settings.market_regime_gate_enabled:
            return None, adjusted_size, adjusted_leverage
        try:
            _regime_str = (signal.metadata or {}).get("market_regime", "")
            if _regime_str:
                _regime_str = _regime_str.upper()
                if _regime_str == "BEAR":
                    # Cap leverage for BEAR regime
                    _bear_lev = settings.bear_regime_max_leverage
                    if adjusted_leverage > _bear_lev:
                        reasons.append(
                            f"[5b] BEAR regime: leverage {adjusted_leverage}x → {_bear_lev}x"
                        )
                        breached.append("bear_regime_max_leverage")
                        adjusted_leverage = _bear_lev
                    # LONG gate: RSI must be oversold
                    _signal_rsi = (signal.metadata or {}).get("rsi")
                    if (
                        signal.action == TradeAction.LONG
                        and _signal_rsi is not None
                        and float(_signal_rsi) >= settings.bear_regime_long_max_rsi
                    ):
                        reasons.append(
                            f"[5b] BEAR regime: LONG rejected — RSI {_signal_rsi:.1f} "
                            f">= {settings.bear_regime_long_max_rsi:.0f} (not oversold enough)"
                        )
                        breached.append("bear_regime_long_rsi_gate")
                        return RiskApproval(
                            symbol=symbol,
                            verdict=RiskVerdict.REJECTED,
                            reasons=reasons,
                            breached_limits=breached,
                        ), adjusted_size, adjusted_leverage
                elif _regime_str == "VOLATILE":
                    # Reduce size in volatile regime
                    _vmult = settings.volatile_regime_size_multiplier
                    if _vmult < 1.0:
                        _prev_sz = adjusted_size
                        adjusted_size = round(adjusted_size * _vmult, 6)
                        reasons.append(
                            f"[5b] VOLATILE regime: size ×{_vmult:.2f} "
                            f"({_prev_sz:.4f} → {adjusted_size:.4f})"
                        )
                        breached.append("volatile_regime_size_reduction")
        except Exception as _regime_exc:  # noqa: BLE001
            self._log.debug("[Batman] Market regime gate skipped: %s", _regime_exc)
        return None, adjusted_size, adjusted_leverage

    def _gate_5c_asset_classifier(
        self,
        signal: TradingSignal,
        symbol: str,
        adjusted_leverage: int,
        max_lev: int,
        reasons: list[str],
        breached: list[str],
    ) -> int:
        """Gate 5c — Asset Classifier Gate (Story 149).

        Uses AssetClassifier cap tier to apply per-tier leverage limits:
          SMALL_CAP -> settings.small_cap_max_leverage
          MID_CAP   -> settings.mid_cap_max_leverage
          LARGE_CAP -> max_lev (no extra restriction)

        Falls back to AssetClassifier.cap_tier(symbol) when metadata missing.
        Fails open when classifier is unavailable.

        Returns:
          (possibly-capped) adjusted_leverage.
        """
        if not settings.asset_classifier_gate_enabled:
            return adjusted_leverage
        try:
            _cap_tier_str = (signal.metadata or {}).get("cap_tier", "")
            if not _cap_tier_str:
                # Resolve tier dynamically (stateless — no I/O)
                from src.services.asset_classifier import AssetClassifier  # noqa: WPS433
                _cap_tier_str = AssetClassifier().cap_tier(symbol).value
            _cap_tier_str = _cap_tier_str.upper()
            if _cap_tier_str == "SMALL_CAP":
                _tier_lev_cap = settings.small_cap_max_leverage
            elif _cap_tier_str == "MID_CAP":
                _tier_lev_cap = settings.mid_cap_max_leverage
            else:
                _tier_lev_cap = max_lev  # LARGE_CAP — no extra restriction
            if adjusted_leverage > _tier_lev_cap:
                reasons.append(
                    f"[5c] {_cap_tier_str}: leverage {adjusted_leverage}x → {_tier_lev_cap}x"
                )
                breached.append(f"{_cap_tier_str.lower()}_max_leverage")
                adjusted_leverage = _tier_lev_cap
        except Exception as _tier_exc:  # noqa: BLE001
            self._log.debug("[Batman] Asset classifier gate skipped: %s", _tier_exc)
        return adjusted_leverage

    def _gate_3e_portfolio_exposure(
        self,
        symbol: str,
        equity_usd: float,
        current_positions: Optional[list[PositionSummary]],
        reasons: list[str],
        breached: list[str],
    ) -> Optional[RiskApproval]:
        """Gate 3e — Portfolio Exposure Cap (Story 068).

        Prevents over-exposure across multiple simultaneous positions.
        If the sum of ALL open paper positions' notional (size × entry)
        already exceeds max_portfolio_exposure_pct of equity, block the
        new entry regardless of individual signal quality.

        Uses current_positions from NickFury's cycle snapshot — same data
        as the correlation gate (3c). Falls open on any error.
        """
        if equity_usd > 0 and current_positions:
            try:
                _open_notional = sum(
                    abs(p.size * p.entry_price) for p in current_positions
                )
                _cap_usd = equity_usd * settings.max_portfolio_exposure_pct
                if _open_notional >= _cap_usd:
                    reasons.append(
                        f"Portfolio exposure cap: open notional "
                        f"${_open_notional:,.2f} ≥ "
                        f"{settings.max_portfolio_exposure_pct:.0%} of equity "
                        f"(${_cap_usd:,.2f}) — new entry blocked"
                    )
                    breached.append("max_portfolio_exposure_pct")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                        metadata={
                            "open_notional_usd": round(_open_notional, 2),
                            "cap_usd": round(_cap_usd, 2),
                            "equity_usd": round(equity_usd, 2),
                        },
                    )
            except Exception as _exp_exc:  # noqa: BLE001
                self._log.debug(f"[Batman] Portfolio exposure gate skipped: {_exp_exc}")
        return None

    async def _run(  # type: ignore[override]
        self,
        signal: TradingSignal,
        volatility: Optional[VolatilityData] = None,
        liquidity: Optional[LiquidityData] = None,
        current_drawdown_pct: float = 0.0,
        open_positions: int = 0,
        trades_today: int = 0,
        running_notional_usd: float = 0.0,
        equity_usd: float = 0.0,
        current_positions: Optional[list[PositionSummary]] = None,
        analysis: Optional[object] = None,  # [Story 247] MarketAnalysis for Flash gate 3r
    ) -> RiskApproval:
        symbol = signal.symbol
        reasons: list[str] = []
        breached: list[str] = []

        # ---------------------------------------------------------------
        # 0. Kill switch — instant halt
        # ---------------------------------------------------------------
        if is_kill_switch_active():
            reasons.append("Kill switch is engaged — system-wide trading halt")
            breached.append("kill_switch")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.KILL_SWITCH,
                reasons=reasons,
                adjusted_size_pct=0.0,
                adjusted_leverage=1,
                breached_limits=breached,
            )

        # ---------------------------------------------------------------
        # 1. HOLD — nothing to execute, mark REJECTED for clarity
        # ---------------------------------------------------------------
        if signal.action == TradeAction.HOLD:
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=["Signal action is HOLD — no execution"],
                adjusted_size_pct=0.0,
                adjusted_leverage=1,
                breached_limits=[],
            )

        # ---------------------------------------------------------------
        # 2. Daily drawdown breaker
        # ---------------------------------------------------------------
        if current_drawdown_pct >= settings.max_daily_drawdown_pct:
            reasons.append(
                f"Daily drawdown {current_drawdown_pct:.2%} ≥ "
                f"limit {settings.max_daily_drawdown_pct:.2%}"
            )
            breached.append("max_daily_drawdown_pct")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )
        # ---------------------------------------------------------------
        # 3. Trade-count and concurrency breakers
        # ---------------------------------------------------------------

        # ── 3k. Pyramid / Scale-In Bypass — Story 080 (helper extraído #73) ──
        _is_pyramid_entry, signal = self._gate_3k_pyramid_bypass(
            signal=signal, symbol=symbol,
            open_positions=open_positions, current_positions=current_positions,
            reasons=reasons, breached=breached,
        )

        if not _is_pyramid_entry and open_positions >= settings.max_open_positions:
            reasons.append(
                f"Open positions {open_positions} ≥ "
                f"limit {settings.max_open_positions}"
            )
            breached.append("max_open_positions")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        if trades_today >= settings.max_trades_per_day:
            reasons.append(
                f"Trades today {trades_today} ≥ "
                f"daily cap {settings.max_trades_per_day}"
            )
            breached.append("max_trades_per_day")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        # ---------------------------------------------------------------
        # 3b. Total capital cap — Story 029a (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3b_result = self._gate_3b_total_capital_cap(
            signal=signal, symbol=symbol, equity_usd=equity_usd,
            running_notional_usd=running_notional_usd,
            reasons=reasons, breached=breached,
        )
        if _gate_3b_result is not None:
            return _gate_3b_result

        # ---------------------------------------------------------------
        # 3c. Correlation gate — Story 057 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3c_result, signal = self._gate_3c_correlation(
            signal=signal, symbol=symbol,
            current_positions=current_positions,
            reasons=reasons, breached=breached,
        )
        if _gate_3c_result is not None:
            return _gate_3c_result

        # ---------------------------------------------------------------
        # 3d. Episodic Memory gate — Story 063 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3d_result, signal = await self._gate_3d_episodic_memory(
            signal=signal, symbol=symbol,
            reasons=reasons, breached=breached,
        )
        if _gate_3d_result is not None:
            return _gate_3d_result

        # ---------------------------------------------------------------
        # 3e. Portfolio Exposure Cap — Story 068 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3e_result = self._gate_3e_portfolio_exposure(
            symbol=symbol, equity_usd=equity_usd,
            current_positions=current_positions,
            reasons=reasons, breached=breached,
        )
        if _gate_3e_result is not None:
            return _gate_3e_result

        # ---------------------------------------------------------------
        # 3f. Re-entry Cooldown Guard — Story 069 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3f_result = await self._gate_3f_reentry_cooldown(
            symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3f_result is not None:
            return _gate_3f_result

        # ---------------------------------------------------------------
        # 3g. Symbol Strike Counter + Auto-Blacklist — Story 071 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3g_result = await self._gate_3g_symbol_blacklist(
            symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3g_result is not None:
            return _gate_3g_result

        # ---------------------------------------------------------------
        # 3h. MTF Confluence — Story 072 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3h_result, signal = await self._gate_3h_mtf_confluence(
            signal=signal, symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3h_result is not None:
            return _gate_3h_result

        # ---------------------------------------------------------------
        # 3i. Funding Rate — Story 075 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3i_result, signal = await self._gate_3i_funding_rate(
            signal=signal, symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3i_result is not None:
            return _gate_3i_result

        # ---------------------------------------------------------------
        # 3j. Trading Hours — Story 076 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3j_result = self._gate_3j_trading_hours(
            symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3j_result is not None:
            return _gate_3j_result

        # ---------------------------------------------------------------
        # 3l. Max trades per symbol per day — Story 086 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3l_result = await self._gate_3l_max_trades_per_symbol_day(
            symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3l_result is not None:
            return _gate_3l_result

        # ---------------------------------------------------------------
        # 3m. Minimum trade notional — Story 096 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3m_result = self._gate_3m_min_notional(
            signal=signal, equity_usd=equity_usd,
            symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3m_result is not None:
            return _gate_3m_result

        # ---------------------------------------------------------------
        # 3n. Symbol weekly drawdown — Story 100 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3n_result = await self._gate_3n_symbol_weekly_drawdown(
            equity_usd=equity_usd, symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3n_result is not None:
            return _gate_3n_result

        # ---------------------------------------------------------------
        # 3o. Max consecutive losses — Story 102 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3o_result = await self._gate_3o_consecutive_losses(
            symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3o_result is not None:
            return _gate_3o_result

        # ---------------------------------------------------------------
        # 3p. Directional bias — Story 106 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3p_result = await self._gate_3p_directional_bias(
            signal=signal, symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3p_result is not None:
            return _gate_3p_result

        # ---------------------------------------------------------------
        # 3q. Min ATR filter — Story 110 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_3q_result = await self._gate_3q_min_atr(
            symbol=symbol, reasons=reasons, breached=breached,
        )
        if _gate_3q_result is not None:
            return _gate_3q_result

        # ---------------------------------------------------------------
        # 3r. Flash Momentum Divergence — Story 247 (helper extraído #73)
        # ---------------------------------------------------------------
        _flash_size_reduction_pct = self._gate_3r_flash_divergence(
            signal=signal, analysis=analysis, reasons=reasons,
        )

        # ---------------------------------------------------------------
        # 4. Confidence and R:R quality gates
        # ---------------------------------------------------------------
        if signal.confidence < settings.min_confidence_threshold:
            reasons.append(
                f"Confidence {signal.confidence:.2f} < threshold "
                f"{settings.min_confidence_threshold:.2f}"
            )
            breached.append("min_confidence_threshold")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        rr = signal.risk_reward_ratio
        if rr < settings.min_risk_reward_ratio:
            reasons.append(
                f"R:R {rr:.2f} < required {settings.min_risk_reward_ratio:.2f}"
            )
            breached.append("min_risk_reward_ratio")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        # ---------------------------------------------------------------
        # 5. Size + leverage adjustment (REDUCED if any cap hit)
        # ---------------------------------------------------------------
        adjusted_size = signal.size_pct
        adjusted_leverage = signal.leverage

        # Apply Thor multiplier
        if volatility is not None:
            mult = volatility.suggested_position_size_multiplier
            new_size = adjusted_size * mult
            if abs(new_size - adjusted_size) > 1e-9:
                reasons.append(
                    f"Thor volatility multiplier {mult:.2f}x applied "
                    f"({adjusted_size:.4f} → {new_size:.4f})"
                )
                breached.append("volatility_adjustment")
            adjusted_size = new_size

        # [Story 247] Gate 3r — Flash divergence size reduction
        if _flash_size_reduction_pct > 0.0:
            _prev_sz = adjusted_size
            adjusted_size = round(adjusted_size * (1.0 - _flash_size_reduction_pct), 6)
            breached.append("flash_divergence_reduction")
            self._log.info(
                f"[Batman] Gate 3r applied: size {_prev_sz:.4f} → {adjusted_size:.4f} "
                f"({_flash_size_reduction_pct:.0%} Flash divergence reduction)"
            )

        # Story 070 — ATR-based position sizing
        # Scale size inversely with ATR%: high volatility → smaller position.
        # atr_multiplier = clamp(atr_target_pct / current_atr_pct, min_mult, 1.0)
        # Fails open: if ATR cannot be computed, size is left unchanged.
        if settings.atr_sizing_enabled:
            try:
                from src.analytics.atr import compute_atr_pct as _atr  # noqa: WPS433
                _current_atr_pct = await _atr(
                    symbol=symbol,
                    lookback=settings.atr_lookback_candles,
                )
                if _current_atr_pct and _current_atr_pct > 0:
                    _atr_mult = min(
                        1.0,
                        max(
                            settings.atr_min_size_multiplier,
                            settings.atr_target_pct * 100 / _current_atr_pct,
                        ),
                    )
                    if _atr_mult < 0.999:
                        _prev = adjusted_size
                        adjusted_size = round(adjusted_size * _atr_mult, 6)
                        reasons.append(
                            f"ATR sizing: current ATR%={_current_atr_pct:.3f}% "
                            f"(target={settings.atr_target_pct * 100:.1f}%) → "
                            f"size ×{_atr_mult:.2f} "
                            f"({_prev:.4f} → {adjusted_size:.4f})"
                        )
                        breached.append("atr_size_reduction")
            except Exception as _atr_exc:  # noqa: BLE001
                self._log.debug("[Batman] ATR sizing skipped: %s", _atr_exc)

        # Penalize on poor liquidity
        if liquidity is not None and liquidity.liquidity_score < 0.4:
            penalty = max(0.4, liquidity.liquidity_score)  # at least 40% of size
            new_size = adjusted_size * penalty
            reasons.append(
                f"Liquidity penalty: score={liquidity.liquidity_score:.2f} → "
                f"size × {penalty:.2f}"
            )
            breached.append("liquidity_penalty")
            adjusted_size = new_size

        # Runtime mode overrides (hot-reload — no restart required)
        from src.config.runtime_mode import get_params as _get_mode_params
        _mode_params = _get_mode_params()
        _max_pos = _mode_params.get("max_position_size_pct", settings.max_position_size_pct)
        _max_lev = _mode_params.get("max_leverage", settings.max_leverage)
        _max_lev_high = _mode_params.get("max_leverage_high_regime", settings.max_leverage_high_regime)
        _max_lev_extreme = _mode_params.get("max_leverage_extreme_regime", settings.max_leverage_extreme_regime)

        # Runtime override: super_aggressive força mínimo 5%/10x (respeitando
        # o cap do Modo Global). Aplica ANTES do cap pra que UI honre o que
        # promete sem violar limites. Fix do bug "toggles silenciosos" 2026-05-25.
        try:
            from src.config.runtime_overrides import (  # noqa: WPS433
                apply_super_aggressive_to_size_lev,
                get_runtime_overrides,
            )
            _ov_batman = get_runtime_overrides()
            if _ov_batman.get("super_aggressive"):
                _new_size_sa, _new_lev_sa = apply_super_aggressive_to_size_lev(
                    adjusted_size, adjusted_leverage, _max_pos, _max_lev
                )
                if _new_size_sa > adjusted_size:
                    reasons.append(
                        f"Super Agressivo: size {adjusted_size:.2%} → {_new_size_sa:.2%} "
                        f"(mínimo 5%, capped pelo Modo Global em {_max_pos:.2%})"
                    )
                    adjusted_size = _new_size_sa
                if _new_lev_sa > adjusted_leverage:
                    reasons.append(
                        f"Super Agressivo: leverage {adjusted_leverage}x → {_new_lev_sa}x "
                        f"(mínimo 10x, capped pelo Modo Global em {_max_lev}x)"
                    )
                    adjusted_leverage = _new_lev_sa
        except Exception as _ov_exc:  # noqa: BLE001
            self._log.debug(f"[Batman] runtime override skipped: {_ov_exc}")

        # Hard cap on size
        if adjusted_size > _max_pos:
            reasons.append(
                f"Size {adjusted_size:.2%} capped to "
                f"{_max_pos:.2%}"
            )
            breached.append("max_position_size_pct")
            adjusted_size = _max_pos

        # Regime-based leverage cap (tighter than global max in HIGH/EXTREME)
        if volatility is not None:
            regime = volatility.volatility_regime
            if regime == VolatilityRegime.EXTREME:
                regime_lev_cap = _max_lev_extreme
            elif regime == VolatilityRegime.HIGH:
                regime_lev_cap = _max_lev_high
            else:
                regime_lev_cap = _max_lev
            if adjusted_leverage > regime_lev_cap:
                reasons.append(
                    f"Leverage {adjusted_leverage}x capped to {regime_lev_cap}x "
                    f"(regime={regime.value})"
                )
                breached.append(f"max_leverage_{regime.value.lower()}_regime")
                adjusted_leverage = regime_lev_cap

        # Hard cap on leverage (global ceiling regardless of regime)
        if adjusted_leverage > _max_lev:
            reasons.append(
                f"Leverage {adjusted_leverage}x capped to "
                f"{_max_lev}x"
            )
            breached.append("max_leverage")
            adjusted_leverage = _max_lev

        # ---------------------------------------------------------------
        # 5b. Market Regime Gate — Story 148 (helper extraído #73)
        # ---------------------------------------------------------------
        _gate_5b_result, adjusted_size, adjusted_leverage = self._gate_5b_market_regime(
            signal=signal, symbol=symbol,
            adjusted_size=adjusted_size, adjusted_leverage=adjusted_leverage,
            reasons=reasons, breached=breached,
        )
        if _gate_5b_result is not None:
            return _gate_5b_result

        # ---------------------------------------------------------------
        # 5c. Asset Classifier Gate — Story 149 (helper extraído #73)
        # ---------------------------------------------------------------
        adjusted_leverage = self._gate_5c_asset_classifier(
            signal=signal, symbol=symbol,
            adjusted_leverage=adjusted_leverage, max_lev=_max_lev,
            reasons=reasons, breached=breached,
        )

        # ---------------------------------------------------------------
        # 5b. Mainnet first-week HARD CLAMP (real-money safety)
        # On Binance mainnet (live, non-testnet), clamp size/leverage DOWN to the
        # conservative first-week caps so a loose config or a large model-suggested
        # size cannot risk real money. Only ever tightens; never loosens.
        # ---------------------------------------------------------------
        # Treat as "mainnet behavior" when on real mainnet OR when dry-run is on
        # (so the operator can rehearse the clamp on testnet before going live).
        _looks_mainnet = (
            settings.active_exchange == "binance"
            and not settings.paper_trading
            and (
                not bool(getattr(settings, "binance_testnet", False))
                or bool(getattr(settings, "mainnet_dry_run", False))
            )
        )
        if (
            getattr(settings, "mainnet_first_week_hard_clamp", True)
            and _looks_mainnet
        ):
            _cap_size, _cap_lev = 0.001, 2
            if adjusted_size > _cap_size:
                reasons.append(
                    f"Mainnet 1ª semana: size {adjusted_size:.4f}→{_cap_size} (clamp duro)"
                )
                adjusted_size = _cap_size
                if "mainnet_first_week_size_clamp" not in breached:
                    breached.append("mainnet_first_week_size_clamp")
            if adjusted_leverage > _cap_lev:
                reasons.append(
                    f"Mainnet 1ª semana: lev {adjusted_leverage}→{_cap_lev}x (clamp duro)"
                )
                adjusted_leverage = _cap_lev
                if "mainnet_first_week_lev_clamp" not in breached:
                    breached.append("mainnet_first_week_lev_clamp")

        # ---------------------------------------------------------------
        # 6. Final verdict
        # ---------------------------------------------------------------
        if adjusted_size <= 0:
            verdict = RiskVerdict.REJECTED
            reasons.append("Final size is zero — nothing to execute")
        elif breached:
            verdict = RiskVerdict.REDUCED
            reasons.insert(0, "Approved with adjustments")
        else:
            verdict = RiskVerdict.APPROVED
            reasons.insert(0, "All risk checks passed")

        # ---------------------------------------------------------------
        # Story 088 — Signal Quality Score (0-100)
        #
        # Composite score combining: confidence (40%), R:R ratio (30%),
        # size utilisation (15%), and absence of breaches penalty (15%).
        # Logged in the approval metadata for dashboard + audit visibility.
        # ---------------------------------------------------------------
        _conf_score  = min(100.0, signal.confidence * 100) * 0.40
        _rr_score    = min(100.0, (rr / max(settings.min_risk_reward_ratio, 0.01)) * 50) * 0.30
        _size_score  = min(100.0, (adjusted_size / max(settings.max_position_size_pct, 1e-6)) * 100) * 0.15
        _clean_score = max(0.0, 100.0 - len([b for b in breached if b not in
                          ("volatility_adjustment", "atr_size_reduction", "liquidity_penalty",
                           "pyramid_size_cap")]) * 20) * 0.15
        _signal_quality_score = round(_conf_score + _rr_score + _size_score + _clean_score, 1)

        approval = RiskApproval(
            symbol=symbol,
            verdict=verdict,
            reasons=reasons,
            adjusted_size_pct=round(adjusted_size, 6),
            adjusted_leverage=adjusted_leverage,
            breached_limits=breached,
            metadata={
                "original_size_pct": signal.size_pct,
                "original_leverage": signal.leverage,
                "confidence": signal.confidence,
                "rr": rr,
                "paper_trading": settings.paper_trading,
                "signal_quality_score": _signal_quality_score,
            },
        )

        self._log.info(
            "[Batman] verdict={} score={:.1f} symbol={} breached={}",
            verdict.value, _signal_quality_score, symbol, breached or "none",
        )
        return approval


# Backward-compatible alias kept for older tests and call sites.
BatmanAgent = Batman

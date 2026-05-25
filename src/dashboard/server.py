from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from aiohttp import WSMsgType, web

from src.config.settings import settings
from src.dashboard import severity as _severity_mod
from src.dashboard import validators as _validators_mod
from src.dashboard.payload_builders import (
    HERO_LAYER as _HERO_LAYER_FROM_BUILDERS,
    build_hero_sla as _build_hero_sla_pure,
    build_layers_snapshot as _build_layers_snapshot,
    build_risk_drilldown as _build_risk_drilldown,
    build_risk_heatmap as _build_risk_heatmap,
    build_spiderman_anomalies as _build_spiderman_anomalies,
    build_symbol_timeline as _build_symbol_timeline,
    build_timeline as _build_timeline,
)
from src.dashboard.replay_helpers import (
    compare_snapshots as _compare_snapshots,
    parse_iso_utc as _parse_iso_utc,
    slice_snapshots as _slice_snapshots,
)
from src.dashboard.severity import compute_severity as _compute_severity
from src.dashboard.severity import percentile as _percentile


def _build_hero_sla(audits: list[Any]) -> list[dict[str, Any]]:
    """Local wrapper that injects ``_percentile`` so call sites stay terse."""
    return _build_hero_sla_pure(audits, _percentile)
from src.dashboard.validators import (
    DEFAULT_WS_ORIGINS as _DEFAULT_WS_ORIGINS,
    EXTRA_WS_ORIGINS as _EXTRA_WS_ORIGINS,
    BUNDLE_NAME_RE as _BUNDLE_NAME_RE,
    SNAPSHOT_NAME_RE as _SNAPSHOT_NAME_RE,
    is_origin_allowed as _is_origin_allowed,
    is_valid_bundle_name as _is_valid_bundle_name,
    is_valid_snapshot_name as _is_valid_snapshot_name,
)
from src.persistence.repository import MekkaRepository

# Module-level sentinel — allows tests to patch via
# patch("src.dashboard.server.Deadpool").
# _handle_performance checks this first; if None, lazy-imports from deadpool module.
Deadpool = None  # type: ignore[assignment]

logger = logging.getLogger("mekka.dashboard")

# Paths are anchored to the repository root, never to the current working
# directory, so the dashboard works regardless of where it's launched from.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
SNAPSHOT_DIR = _REPO_ROOT / "data" / "dashboard_snapshots"
KILL_SWITCH_FILE = _REPO_ROOT / "data" / ".kill_switch"

# Snapshot retention. Defaults can be overridden via env so ops can tune them
# without code changes. Pruning runs lazily inside _persist_snapshot.
SNAPSHOT_RETENTION_MINUTES = int(os.environ.get("MEKKA_SNAPSHOT_RETENTION_MIN", "1440"))
INCIDENT_BUNDLE_RETENTION = int(os.environ.get("MEKKA_INCIDENT_RETENTION", "200"))

# Filename + origin validators are now in `src.dashboard.validators`. We
# re-export the names here so existing tests/imports keep working.
# (See top-of-file `from src.dashboard.validators import ...`.)

# Optional shared-secret token. When set, every mutating endpoint
# (POST/DELETE/PUT) requires the X-Mekka-Token header. GET endpoints stay
# open so observability tools (curl, scripts, screenshots) keep working.
_DASHBOARD_TOKEN = os.environ.get("MEKKA_DASHBOARD_TOKEN", "").strip()

# Drawdown alert thresholds (fractions, not percentages).
_DRAWDOWN_WARN = float(os.environ.get("MEKKA_DRAWDOWN_WARN_PCT", "0.05"))
_DRAWDOWN_CRIT = float(os.environ.get("MEKKA_DRAWDOWN_CRIT_PCT", "0.10"))

# ---------------------------------------------------------------------------
# Login rate limiter — simple in-memory sliding-window, no external deps.
# ---------------------------------------------------------------------------
import time as _time_mod

_LOGIN_MAX_ATTEMPTS = int(os.environ.get("MEKKA_LOGIN_MAX_ATTEMPTS", "5"))
_LOGIN_WINDOW_SECONDS = int(os.environ.get("MEKKA_LOGIN_WINDOW_SECONDS", "300"))  # 5 min
# {ip_str: [timestamp, ...]}  — pruned on each access to prevent unbounded growth.
_login_attempts: dict[str, list[float]] = {}

# Default Content-Security-Policy. Locks scripts/styles/images to same-origin
# plus the explicit CDNs we use. `connect-src` allows the Binance WS used by
# the live ticker. Tweak via `MEKKA_DASHBOARD_CSP` for custom deployments.
_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://unpkg.com "
    "https://s3.tradingview.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self' https://api.binance.com wss://stream.binance.com:9443 "
    "https://api.hyperliquid.xyz wss://api.hyperliquid.xyz "
    "https://api.hyperliquid-testnet.xyz wss://api.hyperliquid-testnet.xyz "
    "https://www.tradingview.com https://s.tradingview.com https://www.tradingview-widget.com; "
    "frame-src 'self' https://www.tradingview.com https://s.tradingview.com https://www.tradingview-widget.com; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_DASHBOARD_CSP = os.environ.get("MEKKA_DASHBOARD_CSP", _DEFAULT_CSP)
# Single source of truth for the hero→layer mapping. Centralised in
# `payload_builders.py` so the builders, the dashboard, and any future
# tooling all read from the same dict.
HERO_LAYER = _HERO_LAYER_FROM_BUILDERS


@web.middleware
async def _security_headers_middleware(
    request: web.Request, handler
) -> web.StreamResponse:
    """Apply baseline security headers to every response.

    Blocks framing, type-sniffing, leaks via Referrer, and forces a strict
    Content-Security-Policy. HSTS is only emitted when we're on HTTPS so
    plain-HTTP local dev doesn't get a useless preload header.
    """
    resp = await handler(request)
    # WebSocket upgrades and aiohttp internals can yield non-Response objects
    # before headers are mutable; we only set on regular responses.
    headers = getattr(resp, "headers", None)
    if headers is None:
        return resp
    # Office v2 transpiles JSX in the browser via Babel-standalone, which
    # uses `Function`/`eval` on parsed source. The strict CSP would block
    # that, so we relax `script-src` to include `unsafe-eval` ONLY for
    # paths under `/office-v2/`. The main dashboard keeps the strict CSP.
    if request.path.startswith("/office-v2") or request.path.startswith("/office-v4"):
        relaxed = _DASHBOARD_CSP.replace(
            "script-src 'self'",
            "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
        )
        headers.setdefault("Content-Security-Policy", relaxed)
    else:
        headers.setdefault("Content-Security-Policy", _DASHBOARD_CSP)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    # Dashboard embeds the Office scene via same-origin iframe.
    # DENY blocks all framing (including self), so use SAMEORIGIN.
    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=()",
    )
    if request.scheme == "https":
        headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return resp


def _json_safe_default(obj: Any) -> Any:
    """json.dumps ``default`` hook — make Pydantic models, enums and datetimes
    serializable. Event payloads can carry raw domain models (e.g.
    VolatilityData) that json can't encode; this coerces them to plain data
    instead of raising TypeError.
    """
    # Pydantic v2 model
    _dump = getattr(obj, "model_dump", None)
    if callable(_dump):
        try:
            return _dump(mode="json")
        except Exception:  # noqa: BLE001
            return _dump()
    # Enum
    if hasattr(obj, "value") and type(obj).__class__.__name__ == "EnumMeta":
        return obj.value
    # datetime / date
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return str(obj)


def _is_request_authenticated(request: web.Request) -> bool:
    """Accept any of three credentials, in order:

    1. Cookie ``mekka_session`` carrying a signed token from `/api/auth/login`.
    2. Header ``X-Mekka-Token`` set to the same signed token (curl-friendly).
    3. Header ``X-Mekka-Token`` matching the legacy shared-secret
       ``MEKKA_DASHBOARD_TOKEN`` (back-compat for scripts/CI).
    """
    from src.dashboard.auth import COOKIE_NAME, verify_token

    cookie = request.cookies.get(COOKIE_NAME, "")
    if cookie and verify_token(cookie):
        return True
    header = request.headers.get("X-Mekka-Token", "")
    if header:
        if verify_token(header):
            return True
        if _DASHBOARD_TOKEN and hmac_equals(header, _DASHBOARD_TOKEN):
            return True
    return False


def hmac_equals(a: str, b: str) -> bool:
    """Tiny constant-time string compare wrapper to keep imports tidy."""
    import hmac as _hmac
    return _hmac.compare_digest(a, b)


def _check_login_rate_limit(ip: str) -> bool:
    """Return True if the IP is within the allowed attempt window, False if blocked.

    Pruning is O(attempts) but lists stay tiny in practice (≤5 entries per IP).
    """
    now = _time_mod.time()
    cutoff = now - _LOGIN_WINDOW_SECONDS
    history = _login_attempts.get(ip, [])
    # Prune stale entries
    history = [t for t in history if t > cutoff]
    if len(history) >= _LOGIN_MAX_ATTEMPTS:
        _login_attempts[ip] = history
        return False  # blocked
    history.append(now)
    _login_attempts[ip] = history
    return True  # allowed


def _clear_login_rate_limit(ip: str) -> None:
    """Reset failed-attempt counter on successful login."""
    _login_attempts.pop(ip, None)


@web.middleware
async def _auth_middleware(
    request: web.Request, handler
) -> web.StreamResponse:
    """Require auth on mutating endpoints when any auth mechanism is enabled.

    Auth is enabled when EITHER ``MEKKA_DASHBOARD_PASSWORD`` (session login)
    OR ``MEKKA_DASHBOARD_TOKEN`` (shared secret) is configured. With both
    empty, the dashboard runs unauthenticated — same dev behaviour as before.

    Login endpoints (``/api/auth/login``) bypass the gate so users can
    actually authenticate; logout requires no auth either, since hitting
    a public ``/api/auth/logout`` just clears your own cookie.
    """
    from src.dashboard.auth import is_login_enabled

    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return await handler(request)
    # Always allow these so the auth flow itself can complete.
    if request.path in {"/api/auth/login", "/api/auth/logout"}:
        return await handler(request)
    auth_required = bool(_DASHBOARD_TOKEN) or is_login_enabled()
    if not auth_required:
        return await handler(request)
    if _is_request_authenticated(request):
        return await handler(request)
    return web.json_response(
        {"error": "authentication required — provide X-Mekka-Token header"},
        status=401,
        headers={"WWW-Authenticate": 'Mekka realm="dashboard"'},
    )


class MekkaDashboardServer:
    MARKET_BREAKER_THRESHOLD = 4
    MARKET_BREAKER_COOLDOWN_S = 20.0

    def __init__(self, controller=None) -> None:
        # Runtime control plane: o RuntimeController (opcional) é injetado por
        # run.py e dono do loop Nick Fury. Os handlers /api/system/* operam
        # sobre ele. None = nenhum controller acoplado (estado "unknown").
        self._runtime = controller
        # Per-request counter middleware. Defined inline so it can close
        # over `self._metrics`. Order matters: counter outermost, then
        # auth, then security headers (innermost = nearest the handler).
        @web.middleware
        async def _counter_middleware(request: web.Request, handler):
            self._metrics["http_requests_total"] += 1
            return await handler(request)

        self._app = web.Application(
            middlewares=[
                _counter_middleware,
                _security_headers_middleware,
                _auth_middleware,
            ]
        )
        self._sockets: set[web.WebSocketResponse] = set()
        # Bounded latency buffers — newest 240 samples each. Used by
        # /metrics to compute p50/p95 without dragging in a metrics SDK.
        self._payload_latencies_ms: list[float] = []
        self._broadcast_latencies_ms: list[float] = []
        # Internal counters/gauges exposed via /metrics in Prometheus text
        # format. Cheap to update (in-memory dict), zero cost when unused.
        self._metrics: dict[str, float] = {
            "broadcasts_total": 0.0,
            "broadcasts_errors_total": 0.0,
            "ws_connections_total": 0.0,
            "ws_connections_rejected_total": 0.0,
            "ws_messages_sent_total": 0.0,
            "ws_slow_consumers_dropped_total": 0.0,
            "snapshot_writes_total": 0.0,
            "incident_bundle_writes_total": 0.0,
            "killswitch_engaged_total": 0.0,
            "killswitch_released_total": 0.0,
            "payload_cache_hits_total": 0.0,
            "payload_cache_misses_total": 0.0,
            "http_requests_total": 0.0,
            "started_at_unix_seconds": 0.0,
        }
        self._broadcast_task: asyncio.Task[Any] | None = None
        self._daily_report_task: asyncio.Task[Any] | None = None
        self._weekly_report_task: asyncio.Task[Any] | None = None  # Story 090
        self._daily_reporter: Any | None = None  # DailyReporter, lazy import
        # Live trading panel — exchange-agnostic WebSocket price feed.
        # The pump is dispatched by `src.services.price_feed.make_price_feed`,
        # which picks the right implementation based on ACTIVE_EXCHANGE.
        # `_mark_prices` is keyed by bare Mekka symbol (BTC, ETH, …) so the
        # downstream broadcast loop never needs to know which venue it came
        # from. Kept as a plain dict (not a TypedDict) because the provider
        # mutates it in place; the empty-state contract is "missing key".
        self._live_sockets: set[web.WebSocketResponse] = set()
        self._mark_prices: dict[str, float] = {}      # symbol → mark price
        self._price_pump_task: asyncio.Task[Any] | None = None
        self._live_bcast_task: asyncio.Task[Any] | None = None
        # Drawdown monitor state (reset each UTC day)
        self._dd_peak_equity: float = 0.0           # highest equity seen today
        self._dd_alert_date: str = ""               # last UTC date alert fired
        self._dd_alerted: bool = False              # fired today?
        self._last_snapshot_minute: str | None = None
        # Kill-switch dedup: only persist a new incident bundle when the
        # state transitions from "no kill" to "kill" OR a new wall-clock
        # minute starts (whichever happens first). Without this the loop
        # would flood SNAPSHOT_DIR with one bundle every 2s.
        self._kill_state_active: bool = False
        self._last_bundle_minute: str | None = None
        # _collect_payload TTL cache (1.5s for full payload, 0.5s for the
        # lightweight overview-only variant) so the broadcast loop and
        # /api/overview don't hammer the DB on the same request burst.
        self._payload_cache: dict[bool, tuple[float, dict[str, Any]]] = {}
        # Story 041 — recommendation cache (rec_id → {recommendation + equity_usd}).
        # Capped at 20 entries (FIFO) so the server restart is the only reason
        # a rec_id is missing. Keyed by UUID string.
        self._rec_cache: dict[str, dict] = {}
        self._rec_cache_max: int = 20
        # Reusable HTTP session for Binance calls — created in _on_startup.
        self._http: aiohttp.ClientSession | None = None
        # Outbound alert dispatcher (Slack/Telegram). Lazily wired in
        # _on_startup so it shares the HTTP session and event loop.
        self._alert_dispatcher: Any = None
        self._market_cache: dict[str, tuple[float, Any]] = {}
        self._market_sem = asyncio.Semaphore(4)
        self._market_diag: dict[str, dict[str, Any]] = {}
        self._market_fail_streak: dict[str, int] = {}
        self._market_breaker_until: dict[str, float] = {}
        self._portfolio_cache: tuple[float, dict[str, Any]] | None = None
        self._portfolio_cache_lock = asyncio.Lock()
        self._portfolio_warm_task: asyncio.Task[Any] | None = None
        self._configure_routes()
        self._app.on_startup.append(self._on_startup)
        self._app.on_shutdown.append(self._on_shutdown)

    @property
    def app(self) -> web.Application:
        return self._app

    async def _get_live_portfolio_context(self, max_age_s: float = 2.0) -> dict[str, Any]:
        """Return a cached live portfolio snapshot for wallet/equity widgets."""
        loop = asyncio.get_running_loop()
        default_payload = {
            "equity_usd": 0.0,
            "available_balance_usd": 0.0,
            "margin_used_usd": 0.0,
            "open_positions_count": 0,
            "source": "UNKNOWN",
            "is_paper": settings.paper_trading,
            "is_live_ok": False,
            "error": None,
        }
        cached = self._portfolio_cache
        if cached and cached[0] > loop.time():
            return cached[1]
        if self._portfolio_cache_lock.locked():
            return cached[1] if cached else default_payload
        async with self._portfolio_cache_lock:
            cached = self._portfolio_cache
            if cached and cached[0] > loop.time():
                return cached[1]

            payload = default_payload.copy()
            try:
                from src.agents.portfolio_manager import PortfolioManager  # noqa: WPS433

                snapshot = await asyncio.wait_for(PortfolioManager().run(), timeout=6.0)
                payload = {
                    "equity_usd": float(snapshot.equity_usd or 0.0),
                    "available_balance_usd": float(snapshot.available_balance_usd or 0.0),
                    "margin_used_usd": float(snapshot.margin_used_usd or 0.0),
                    "open_positions_count": int(snapshot.open_positions_count or 0),
                    "source": snapshot.source.value,
                    "is_paper": bool(snapshot.is_paper),
                    "is_live_ok": (snapshot.source.value != "PAPER_FALLBACK") and not bool(snapshot.error),
                    "error": snapshot.error,
                }
            except Exception as exc:  # noqa: BLE001
                payload["error"] = str(exc)
                if cached:
                    stale = dict(cached[1])
                    stale["error"] = payload["error"]
                    self._portfolio_cache = (loop.time() + min(max_age_s, 2.0), stale)
                    return stale

            self._portfolio_cache = (loop.time() + max_age_s, payload)
            return payload

    async def _warm_live_portfolio_context(self) -> None:
        """Best-effort warmup so the first overview request stays responsive."""
        try:
            await self._get_live_portfolio_context(max_age_s=8.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("portfolio warmup failed: %s", exc)

    def _configure_routes(self) -> None:
        """Register all HTTP/WS routes, grouped by domain (IMP-33f2fe698672 —
        refactor server.py em routers por domínio, passo 1: agrupamento do
        registro). Todas as rotas são caminhos/prefixos distintos, então a
        ordem entre grupos é irrelevante."""
        r = self._app.router
        self._register_core_routes(r)
        self._register_replay_incident_routes(r)
        self._register_market_routes(r)
        self._register_pnl_perf_routes(r)
        self._register_risk_routes(r)
        self._register_system_routes(r)
        self._register_trade_routes(r)
        self._register_agents_memory_routes(r)
        self._register_improvement_routes(r)
        self._register_backtest_debate_routes(r)
        self._register_kernel_obs_routes(r)
        self._register_realtime_static_office_routes(r)

    # ── Domain route groups ───────────────────────────────────────────────
    def _register_core_routes(self, r) -> None:
        r.add_get("/", self._handle_index)
        r.add_get("/api/health", self._handle_health)
        r.add_get("/api/overview", self._handle_overview)
        r.add_get("/api/signals", self._handle_signals)
        r.add_get("/api/signals/export", self._handle_signals_export)
        r.add_get("/api/trades", self._handle_trades)
        r.add_get("/api/audit", self._handle_audit)
        r.add_get("/api/env", self._handle_env)
        r.add_get("/api/mainnet-readiness", self._handle_mainnet_readiness)
        r.add_get("/api/today-summary", self._handle_today_summary)
        r.add_get("/api/prefs", self._handle_prefs_get)
        r.add_post("/api/prefs", self._handle_prefs_set)
        r.add_get("/api/settings", self._handle_settings_get)
        r.add_post("/api/settings", self._handle_settings_set)
        r.add_post("/api/auth/login", self._handle_auth_login)
        r.add_post("/api/auth/logout", self._handle_auth_logout)
        r.add_get("/api/auth/me", self._handle_auth_me)
        r.add_get("/metrics", self._handle_metrics)

    def _register_replay_incident_routes(self, r) -> None:
        r.add_get("/api/replay", self._handle_replay)
        r.add_get("/api/replay/snapshots", self._handle_replay_snapshots)
        r.add_get("/api/replay/export", self._handle_replay_export)
        r.add_get("/api/replay/compare", self._handle_replay_compare)
        r.add_get("/api/replay/incident/latest", self._handle_incident_latest)
        r.add_get("/api/replay/incident/latest/download", self._handle_incident_download)
        r.add_get("/api/replay/incidents", self._handle_incidents_list)
        r.add_get("/api/replay/incident/download", self._handle_incident_download_named)
        r.add_get("/api/replay/timeseries", self._handle_replay_timeseries)
        r.add_get("/api/incidents/queue", self._handle_incidents_queue)
        r.add_get("/api/incidents/export", self._handle_incidents_export)
        r.add_get("/api/incidents/detail", self._handle_incident_detail)

    def _register_market_routes(self, r) -> None:
        r.add_get("/api/market/funding", self._handle_funding_rates)
        r.add_get("/api/market/candles", self._handle_market_candles)
        r.add_get("/api/market/depth", self._handle_market_depth)
        r.add_get("/api/market/trades", self._handle_market_trades)
        r.add_get("/api/market/diagnostics", self._handle_market_diagnostics)
        r.add_get("/api/market/status", self._handle_market_status)
        r.add_get("/api/hl/candles", self._handle_hl_candles)

    def _register_pnl_perf_routes(self, r) -> None:
        r.add_get("/api/pnl/series", self._handle_pnl_series)
        r.add_get("/api/pnl/summary", self._handle_pnl_summary)
        r.add_get("/api/pnl/benchmark", self._handle_pnl_benchmark)
        r.add_get("/api/pnl/equity-curve", self._handle_equity_curve)
        r.add_get("/api/pnl/heatmap", self._handle_pnl_heatmap)
        r.add_get("/api/pnl/hourly", self._handle_pnl_hourly)
        r.add_get("/api/performance", self._handle_performance)
        r.add_get("/api/performance/rolling", self._handle_perf_rolling)
        r.add_get("/api/performance/divergence", self._handle_perf_divergence)
        r.add_get("/api/trades/timeline", self._handle_trades_timeline)
        r.add_get("/api/trades/export", self._handle_trades_export)
        r.add_get("/api/trades/calendar", self._handle_trades_calendar)
        r.add_get("/api/leaderboard", self._handle_leaderboard)
        r.add_get("/api/session/stats", self._handle_session_stats)
        r.add_get("/api/gates/timeline", self._handle_gates_timeline)

    def _register_risk_routes(self, r) -> None:
        r.add_get("/api/killswitch/status", self._handle_killswitch_status)
        r.add_post("/api/killswitch/engage", self._handle_killswitch_engage)
        r.add_post("/api/killswitch/release", self._handle_killswitch_release)
        r.add_get("/api/risk/panel", self._handle_risk_panel)
        r.add_get("/api/risk/batman-timeline", self._handle_batman_timeline)
        r.add_get("/api/risk/regime-heatmap", self._handle_regime_heatmap)
        r.add_get("/api/risk/concentration", self._handle_concentration)

    def _register_system_routes(self, r) -> None:
        # Runtime control plane (liga/desliga/reinicia o loop de trading).
        r.add_get("/api/system/status", self._handle_system_status)
        r.add_post("/api/system/start", self._handle_system_start)
        r.add_post("/api/system/stop", self._handle_system_stop)
        r.add_post("/api/system/reboot", self._handle_system_reboot)
        r.add_get("/api/mode", self._handle_mode_get)
        r.add_post("/api/mode", self._handle_mode_set)
        r.add_get("/api/exchange", self._handle_exchange_get)
        r.add_post("/api/exchange", self._handle_exchange_set)
        r.add_get("/api/report/daily", self._handle_report_daily)
        r.add_get("/api/report/weekly", self._handle_report_weekly)

    def _register_trade_routes(self, r) -> None:
        r.add_post("/api/trade/analyze", self._handle_trade_analyze)
        r.add_post("/api/trade/execute", self._handle_trade_execute)
        r.add_post("/api/trade/manual", self._handle_trade_manual)
        r.add_post("/api/trade/manual-analyze", self._handle_trade_manual_analyze)
        r.add_get("/api/positions", self._handle_positions)
        r.add_get("/api/positions/orders", self._handle_positions_orders)
        r.add_post("/api/positions/close", self._handle_positions_close)

    def _register_agents_memory_routes(self, r) -> None:
        r.add_get("/api/agents/tasks", self._handle_agents_tasks)
        r.add_get("/api/audit/feed", self._handle_audit_feed)
        r.add_get("/api/memory/stats", self._handle_memory_stats)
        r.add_get("/api/working-memory", self._handle_working_memory)
        r.add_get("/api/cycle-sop", self._handle_cycle_sop)
        r.add_get("/api/incremental-guard", self._handle_incremental_guard)

    def _register_improvement_routes(self, r) -> None:
        r.add_get("/api/jean/health-report", self._handle_jean_health_report)
        r.add_get("/api/jean/graph", self._handle_jean_graph)
        r.add_get("/api/improvements", self._handle_improvements_get)
        r.add_post("/api/improvements/decision", self._handle_improvements_decision)
        r.add_get("/api/improvements/pr-status", self._handle_improvements_pr_status)
        r.add_post("/api/improvements/approve-pr", self._handle_improvements_approve_pr)
        r.add_post("/api/improvements/claim", self._handle_improvements_claim)
        r.add_get("/api/improvements/kpi", self._handle_improvements_kpi)
        r.add_get("/api/improvements/decision-history", self._handle_improvements_history)
        r.add_get("/api/mentor/suggestions", self._handle_mentor_suggestions)

    def _register_backtest_debate_routes(self, r) -> None:
        r.add_post("/api/backtest/run", self._handle_backtest_run)
        r.add_get("/api/backtest/result", self._handle_backtest_result)
        r.add_get("/api/backtest/history", self._handle_backtest_history)
        r.add_get("/api/debate/history", self._handle_debate_history)
        r.add_post("/api/debate/run", self._handle_debate_run)

    def _register_kernel_obs_routes(self, r) -> None:
        r.add_get("/api/cost", self._handle_cost)
        r.add_get("/api/benchmarks", self._handle_benchmarks)
        r.add_get("/api/kernel", self._handle_kernel)
        r.add_post("/api/kernel/invoke", self._handle_kernel_invoke)
        r.add_get("/api/events", self._handle_events)
        r.add_get("/api/events/stream", self._handle_events_stream)
        r.add_get("/api/step-guard", self._handle_step_guard)
        r.add_get("/api/microagents", self._handle_microagents)
        r.add_get("/api/context-window", self._handle_context_window)
        r.add_get("/api/context-window/live", self._handle_context_window_live)
        r.add_get("/api/signal-validator", self._handle_signal_validator)
        r.add_get("/api/signal-changelog", self._handle_signal_changelog)
        r.add_get("/api/repo-map", self._handle_repo_map)
        r.add_get("/api/obs/{tool_name}", self._handle_obs_tool)

    def _register_realtime_static_office_routes(self, r) -> None:
        r.add_get("/ws", self._handle_ws)
        r.add_get("/ws/live", self._handle_ws_live)
        r.add_static("/static", path=STATIC_DIR)
        # Office v2 (React + Babel-standalone) em static/office_v2/.
        office_v2_dir = STATIC_DIR / "office_v2"
        if office_v2_dir.exists():
            r.add_get("/office-v2", self._handle_office_v2_index)
            r.add_get("/office-v2/", self._handle_office_v2_index)
            r.add_static("/office-v2/", path=office_v2_dir)
        # Office v4 — novo design (living floor 2000×1200).
        office_v4_dir = STATIC_DIR / "office_v4"
        if office_v4_dir.exists():
            r.add_get("/office-v4", self._handle_office_v4_index)
            r.add_get("/office-v4/", self._handle_office_v4_index)
            r.add_static("/office-v4/", path=office_v4_dir)

    async def _on_startup(self, _: web.Application) -> None:
        await MekkaRepository.initialize()
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        self._metrics["started_at_unix_seconds"] = datetime.now(
            timezone.utc
        ).timestamp()
        # One ClientSession reused across all Binance calls. Without this each
        # _market_get_json would open/close TCP connections and could exhaust
        # file descriptors under heavy polling.
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                connector=aiohttp.TCPConnector(limit=16, ttl_dns_cache=300),
            )
        # Wire alert dispatcher after the HTTP session is up. We give the
        # dispatcher its own session because Slack/Telegram timeouts are
        # tighter (5s) than the market provider's (10s).
        from src.dashboard.alert_dispatcher import AlertDispatcher
        from src.dashboard.daily_reporter import DailyReporter
        from src.services.telegram_alerter import TelegramAlerter
        self._alert_dispatcher = AlertDispatcher()
        self._daily_reporter = DailyReporter()
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._daily_report_task = asyncio.create_task(self._daily_reporter.run_loop())
        self._weekly_report_task = asyncio.create_task(self._daily_reporter.run_weekly_loop())  # Story 090
        # Live price feed — exchange-agnostic pump. The factory inspects
        # settings.active_exchange and returns the right provider
        # (HyperliquidPriceFeed, BybitPriceFeed, …). The shared
        # `self._mark_prices` dict is mutated in place.
        from src.services.price_feed import make_price_feed  # noqa: WPS433
        self._price_pump_task = asyncio.create_task(
            make_price_feed().run(self._mark_prices)
        )
        self._live_bcast_task = asyncio.create_task(self._live_price_broadcast_loop())
        self._portfolio_warm_task = asyncio.create_task(self._warm_live_portfolio_context())
        # Startup ping — fire-and-forget, non-blocking
        asyncio.create_task(TelegramAlerter().ping(reason="dashboard startup"))
        # Story 228 — BacktestScheduler: daily auto-run at midnight UTC
        try:
            from src.services.backtest_scheduler import BacktestScheduler
            _scheduler = BacktestScheduler(symbols=["BTC", "ETH"], days=30, hour_utc=0)
            self._backtest_scheduler_task = asyncio.create_task(_scheduler.start())
        except Exception as _exc_sched:
            logger.warning("BacktestScheduler startup skipped: %s", _exc_sched)

    async def _on_shutdown(self, _: web.Application) -> None:
        if self._broadcast_task is not None:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
        if self._daily_report_task is not None:
            self._daily_report_task.cancel()
            try:
                await self._daily_report_task
            except asyncio.CancelledError:
                pass
        if self._weekly_report_task is not None:  # Story 090
            self._weekly_report_task.cancel()
            try:
                await self._weekly_report_task
            except asyncio.CancelledError:
                pass
        # BUG-005 fix: cancelar BacktestScheduler task no shutdown
        if getattr(self, "_backtest_scheduler_task", None) is not None:
            self._backtest_scheduler_task.cancel()
            try:
                await self._backtest_scheduler_task
            except asyncio.CancelledError:
                pass
        if self._daily_reporter is not None:
            try:
                await self._daily_reporter.close()
            except Exception:  # noqa: BLE001
                pass
            self._daily_reporter = None
        if self._portfolio_warm_task is not None:
            self._portfolio_warm_task.cancel()
            try:
                await self._portfolio_warm_task
            except asyncio.CancelledError:
                pass
            self._portfolio_warm_task = None
        for ws in list(self._sockets):
            await ws.close(code=1001, message=b"server shutdown")
        for ws in list(self._live_sockets):
            await ws.close(code=1001, message=b"server shutdown")
        for task in (self._price_pump_task, self._live_bcast_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._http is not None and not self._http.closed:
            await self._http.close()
            self._http = None
        if self._alert_dispatcher is not None:
            try:
                await self._alert_dispatcher.close()
            except Exception:  # noqa: BLE001
                pass
            self._alert_dispatcher = None

    async def _handle_index(self, _: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def _handle_health(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "service": "mekka-dashboard",
                "time_utc": datetime.now(timezone.utc).isoformat(),
                "network": settings.hyperliquid_network,
                "mode": settings.mode_label,
            }
        )

    async def _handle_overview(self, _: web.Request) -> web.Response:
        payload = await self._collect_payload(include_tables=False)
        return web.json_response(payload["overview"])

    async def _handle_signals(self, request: web.Request) -> web.Response:
        limit = _safe_limit(request.query.get("limit"), default=20, max_value=200)
        signals = await MekkaRepository.list_recent_signals(limit=limit)
        data = [
            {
                "id": s.id,
                "timestamp": s.timestamp.isoformat(),
                "symbol": s.symbol,
                "action": s.action,
                "confidence": s.confidence,
                "leverage": s.leverage,
                "risk_reward": s.risk_reward,
                "is_actionable": s.is_actionable,
                "reasoning": s.reasoning,
                "fallback": s.fallback,
            }
            for s in signals
        ]
        return web.json_response(data)

    async def _handle_trades(self, request: web.Request) -> web.Response:
        limit = _safe_limit(request.query.get("limit"), default=20, max_value=200)
        trades = await MekkaRepository.list_recent_trades(limit=limit)
        data = [
            {
                "id": t.id,
                "timestamp": t.timestamp.isoformat(),
                "symbol": t.symbol,
                "status": t.status,
                "is_paper": t.is_paper,
                "side": t.side,
                "quantity": t.quantity,
                "avg_price": t.avg_price,
                "notional_usd": t.notional_usd,
                "error": t.error,
            }
            for t in trades
        ]
        return web.json_response(data)

    async def _handle_audit(self, request: web.Request) -> web.Response:
        limit = _safe_limit(request.query.get("limit"), default=50, max_value=500)
        rows = await MekkaRepository.list_recent_audit(limit=limit)
        data = [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "agent": r.agent,
                "event": r.event,
                "symbol": r.symbol,
                "severity": r.severity,
                "message": r.message,
                "payload": r.payload or {},
            }
            for r in rows
        ]
        return web.json_response(data)

    async def _handle_replay_snapshots(self, _: web.Request) -> web.Response:
        files = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")],
            reverse=True,
        )
        return web.json_response({"snapshots": files})

    async def _handle_replay(self, request: web.Request) -> web.Response:
        snapshot_name = request.query.get("snapshot", "latest.json")
        if not _is_valid_snapshot_name(snapshot_name):
            return web.json_response({"error": "invalid snapshot name"}, status=400)

        path = SNAPSHOT_DIR / snapshot_name
        if not path.exists():
            return web.json_response({"error": "snapshot not found"}, status=404)

        raw = await asyncio.to_thread(path.read_text, "utf-8")
        payload = json.loads(raw)
        return web.json_response(payload)

    async def _handle_replay_export(self, request: web.Request) -> web.Response:
        start = request.query.get("start")
        end = request.query.get("end")
        start_utc = request.query.get("start_utc")
        end_utc = request.query.get("end_utc")
        export_format = (request.query.get("format") or "json").lower()

        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")])
        if not files:
            return web.json_response({"error": "no snapshots"}, status=404)

        selected = _slice_snapshots(files, start, end)
        if not selected:
            return web.json_response({"error": "empty range"}, status=404)

        rows = []
        parsed_start = _parse_iso_utc(start_utc)
        parsed_end = _parse_iso_utc(end_utc)
        for name in selected:
            raw = await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
            payload = json.loads(raw)
            ov = payload.get("overview", {})
            ts = _parse_iso_utc(ov.get("timestamp"))
            # When a UTC bound is provided, REQUIRE a parseable timestamp
            # and enforce the bound. A missing/unparseable timestamp under
            # an active filter is treated as "out of range" (exclude),
            # not "no opinion" (include) — the previous behavior silently
            # let unfiltered rows through whenever ts was None.
            if parsed_start is not None:
                if ts is None or ts < parsed_start:
                    continue
            if parsed_end is not None:
                if ts is None or ts > parsed_end:
                    continue
            rows.append(
                {
                    "snapshot": name,
                    "timestamp": ov.get("timestamp"),
                    "mode": ov.get("mode"),
                    "network": ov.get("network"),
                    "total_signals": ov.get("total_signals"),
                    "total_trades": ov.get("total_trades"),
                    "trades_today": ov.get("trades_today"),
                    "executions_today": ov.get("executions_today"),
                    "alerts_count": len(payload.get("global_alerts", [])),
                }
            )
        if not rows:
            return web.json_response({"error": "empty range after utc filter"}, status=404)

        if export_format == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            return web.Response(
                text=output.getvalue(),
                content_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=mekka-replay-export.csv"},
            )

        return web.json_response({"items": rows, "count": len(rows)})

    async def _handle_replay_compare(self, request: web.Request) -> web.Response:
        a = request.query.get("a")
        b = request.query.get("b")
        if not a or not b:
            return web.json_response({"error": "params a and b are required"}, status=400)
        if not _is_valid_snapshot_name(a) or not _is_valid_snapshot_name(b):
            return web.json_response({"error": "invalid snapshot name"}, status=400)

        path_a = SNAPSHOT_DIR / a
        path_b = SNAPSHOT_DIR / b
        if not path_a.exists() or not path_b.exists():
            return web.json_response({"error": "snapshot not found"}, status=404)

        payload_a = json.loads(await asyncio.to_thread(path_a.read_text, "utf-8"))
        payload_b = json.loads(await asyncio.to_thread(path_b.read_text, "utf-8"))
        return web.json_response(_compare_snapshots(a, payload_a, b, payload_b))

    async def _handle_incident_latest(self, _: web.Request) -> web.Response:
        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True)
        if not files:
            return web.json_response({"error": "no snapshots"}, status=404)
        for name in files:
            payload = json.loads(
                await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
            )
            alerts = payload.get("global_alerts", [])
            has_kill = any("KILL_SWITCH" in str(a.get("code", "")) for a in alerts)
            if not has_kill:
                continue
            # Baseline = the snapshot immediately preceding the incident, or
            # None if the incident itself is the oldest snapshot we have.
            # Comparing a snapshot against itself produces a useless all-zero
            # delta and confuses investigators, so we omit `compare` instead.
            idx = files.index(name)
            baseline_name: str | None = None
            compare: dict[str, Any] | None = None
            if idx + 1 < len(files):
                baseline_name = files[idx + 1]
                payload_prev = json.loads(
                    await asyncio.to_thread(
                        (SNAPSHOT_DIR / baseline_name).read_text, "utf-8"
                    )
                )
                compare = _compare_snapshots(baseline_name, payload_prev, name, payload)
            severity = _compute_severity(payload)
            return web.json_response(
                {
                    "incident_snapshot": name,
                    "baseline_snapshot": baseline_name,
                    "alerts": alerts,
                    "compare": compare,
                    "overview": payload.get("overview", {}),
                    "severity": severity,
                }
            )
        return web.json_response({"error": "no kill switch incident found"}, status=404)

    async def _handle_incident_download(self, _: web.Request) -> web.Response:
        """Direct JSON download of the most recent incident bundle.

        Prefers persisted ``incident-bundle-*.json`` files (saved automatically
        when a kill switch is detected). If none exist, falls back to building
        an in-memory bundle from the latest snapshot containing a kill switch.
        """
        bundles = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("incident-bundle-*.json")],
            reverse=True,
        )
        if bundles:
            name = bundles[0]
            raw = await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
            return web.Response(
                text=raw,
                content_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{name}"'},
            )

        # Fallback: build from latest kill-switch snapshot.
        files = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True
        )
        for name in files:
            payload = json.loads(
                await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
            )
            alerts = payload.get("global_alerts", [])
            has_kill = any("KILL_SWITCH" in str(a.get("code", "")) for a in alerts)
            if has_kill:
                bundle = {
                    "captured_at": (payload.get("overview") or {}).get("timestamp"),
                    "source_snapshot": name,
                    "overview": payload.get("overview", {}),
                    "alerts": alerts,
                    "risk_heatmap": payload.get("risk_heatmap", []),
                    "hero_sla": payload.get("hero_sla", []),
                    "severity": _compute_severity(payload),
                }
                filename = f"incident-bundle-from-{name}"
                return web.Response(
                    text=json.dumps(bundle, ensure_ascii=True),
                    content_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )

        return web.json_response({"error": "no incident bundle available"}, status=404)

    async def _handle_incidents_list(self, _: web.Request) -> web.Response:
        bundles = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("incident-bundle-*.json")],
            reverse=True,
        )
        return web.json_response({"bundles": bundles, "count": len(bundles)})

    async def _handle_incident_download_named(self, request: web.Request) -> web.Response:
        name = request.query.get("name", "")
        if not _is_valid_bundle_name(name):
            return web.json_response({"error": "invalid bundle name"}, status=400)
        path = SNAPSHOT_DIR / name
        if not path.exists():
            return web.json_response({"error": "bundle not found"}, status=404)
        raw = await asyncio.to_thread(path.read_text, "utf-8")
        return web.Response(
            text=raw,
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    async def _handle_replay_timeseries(self, request: web.Request) -> web.Response:
        """Aggregated time-series of signals/trades/alerts across snapshots.

        Used by the frontend to render Chart.js line charts in the replay panel.
        """
        limit = _safe_limit(request.query.get("limit"), default=120, max_value=720)
        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")])
        files = files[-limit:]
        if not files:
            return web.json_response({"items": [], "count": 0})

        items: list[dict[str, Any]] = []
        for name in files:
            try:
                payload = json.loads(
                    await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
                )
            except (OSError, json.JSONDecodeError):
                continue
            ov = payload.get("overview") or {}
            alerts = payload.get("global_alerts") or []
            severity = _compute_severity(payload)
            items.append(
                {
                    "snapshot": name,
                    "timestamp": ov.get("timestamp"),
                    "signals_total": int(ov.get("total_signals") or 0),
                    "trades_total": int(ov.get("total_trades") or 0),
                    "trades_today": int(ov.get("trades_today") or 0),
                    "executions_today": int(ov.get("executions_today") or 0),
                    "alerts_count": len(alerts),
                    "severity_score": severity["score"],
                    "severity_tier": severity["tier"],
                }
            )
        return web.json_response({"items": items, "count": len(items)})

    async def _handle_incidents_queue(self, request: web.Request) -> web.Response:
        """Investigation queue: snapshots ranked by incident severity score."""
        limit = _safe_limit(request.query.get("limit"), default=25, max_value=200)
        scan = _safe_limit(request.query.get("scan"), default=200, max_value=1000)
        try:
            offset = int(request.query.get("offset") or 0)
        except ValueError:
            offset = 0
        offset = max(0, min(offset, 5000))
        query = str(request.query.get("q") or "").strip().lower()
        tier_filter = str(request.query.get("tier") or "").strip().upper()
        if tier_filter and tier_filter not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            return web.json_response(
                {"error": "invalid tier filter", "allowed": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                status=400,
            )

        files = sorted(
            [p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True
        )
        files = files[:scan]
        if not files:
            return web.json_response({"items": [], "count": 0})

        items: list[dict[str, Any]] = []
        for name in files:
            try:
                payload = json.loads(
                    await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
                )
            except (OSError, json.JSONDecodeError):
                continue
            severity = _compute_severity(payload)
            if severity["score"] <= 0:
                continue
            if tier_filter and str(severity["tier"]).upper() != tier_filter:
                continue
            ov = payload.get("overview") or {}
            item = {
                "snapshot": name,
                "timestamp": ov.get("timestamp"),
                "score": severity["score"],
                "tier": severity["tier"],
                "drivers": severity["drivers"],
                "alerts": payload.get("global_alerts", []),
                "kill_switch": severity["drivers"].get("kill_switch", 0) > 0,
            }
            if query and not _incident_matches_query(item, query):
                continue
            items.append(
                item
            )
        items.sort(key=lambda x: (x["score"], x["timestamp"] or ""), reverse=True)
        page = items[offset : offset + limit]
        return web.json_response(
            {
                "items": page,
                "count": len(items),
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < len(items),
            }
        )

    async def _handle_incidents_export(self, request: web.Request) -> web.Response:
        """Export consolidated incident queue as CSV for post-mortem analysis."""
        limit = _safe_limit(request.query.get("limit"), default=500, max_value=5000)
        scan = _safe_limit(request.query.get("scan"), default=1000, max_value=5000)
        query = str(request.query.get("q") or "").strip().lower()
        tier_filter = str(request.query.get("tier") or "").strip().upper()
        if tier_filter and tier_filter not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            return web.json_response(
                {"error": "invalid tier filter", "allowed": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                status=400,
            )

        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True)[:scan]
        rows: list[dict[str, Any]] = []
        for name in files:
            try:
                payload = json.loads(
                    await asyncio.to_thread((SNAPSHOT_DIR / name).read_text, "utf-8")
                )
            except (OSError, json.JSONDecodeError):
                continue
            severity = _compute_severity(payload)
            if severity["score"] <= 0:
                continue
            if tier_filter and str(severity["tier"]).upper() != tier_filter:
                continue
            ov = payload.get("overview") or {}
            drivers = severity.get("drivers") or {}
            alerts = payload.get("global_alerts") or []
            item = {
                "snapshot": name,
                "timestamp": ov.get("timestamp"),
                "score": severity["score"],
                "tier": severity["tier"],
                "drivers": drivers,
                "alerts": alerts,
                "kill_switch": int(drivers.get("kill_switch", 0)) > 0,
            }
            if query and not _incident_matches_query(item, query):
                continue
            rows.append(
                {
                    "snapshot": name,
                    "timestamp": ov.get("timestamp"),
                    "tier": severity["tier"],
                    "score": severity["score"],
                    "alerts_count": len(alerts),
                    "kill_switch": int(drivers.get("kill_switch", 0)),
                    "critical_alerts": int(drivers.get("critical_alerts", 0)),
                    "warning_alerts": int(drivers.get("warning_alerts", 0)),
                    "anomaly_pause": int(drivers.get("anomaly_pause", 0)),
                    "breached_limits": int(drivers.get("breached_limits", 0)),
                    "sla_degraded": int(drivers.get("sla_degraded", 0)),
                    "signals_total": int(ov.get("total_signals") or 0),
                    "trades_total": int(ov.get("total_trades") or 0),
                    "trades_today": int(ov.get("trades_today") or 0),
                    "executions_today": int(ov.get("executions_today") or 0),
                }
            )

        rows.sort(key=lambda x: (x["score"], x["timestamp"] or ""), reverse=True)
        rows = rows[:limit]
        output = io.StringIO()
        fieldnames = [
            "snapshot",
            "timestamp",
            "tier",
            "score",
            "alerts_count",
            "kill_switch",
            "critical_alerts",
            "warning_alerts",
            "anomaly_pause",
            "breached_limits",
            "sla_degraded",
            "signals_total",
            "trades_total",
            "trades_today",
            "executions_today",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        suffix = tier_filter.lower() if tier_filter else "all"
        filename = f"mekka-incidents-postmortem-{suffix}.csv"
        return web.Response(
            text=output.getvalue(),
            content_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def _handle_incident_detail(self, request: web.Request) -> web.Response:
        snapshot = str(request.query.get("snapshot") or "").strip()
        if not _is_valid_snapshot_name(snapshot):
            return web.json_response({"error": "invalid snapshot name"}, status=400)
        path = SNAPSHOT_DIR / snapshot
        if not path.exists():
            return web.json_response({"error": "snapshot not found"}, status=404)

        files = sorted([p.name for p in SNAPSHOT_DIR.glob("snapshot-*.json")], reverse=True)
        if snapshot not in files:
            return web.json_response({"error": "snapshot index not found"}, status=404)
        idx = files.index(snapshot)
        baseline = files[idx + 1] if (idx + 1) < len(files) else None

        payload = json.loads(await asyncio.to_thread(path.read_text, "utf-8"))
        severity = _compute_severity(payload)
        overview = payload.get("overview") or {}
        alerts = payload.get("global_alerts") or []

        compare = None
        if baseline:
            baseline_payload = json.loads(await asyncio.to_thread((SNAPSHOT_DIR / baseline).read_text, "utf-8"))
            compare = _compare_snapshots(baseline, baseline_payload, snapshot, payload)

        return web.json_response(
            {
                "snapshot": snapshot,
                "baseline_snapshot": baseline,
                "severity": severity,
                "overview": overview,
                "alerts": alerts,
                "compare": compare,
            }
        )

    async def _handle_funding_rates(self, request: web.Request) -> web.Response:
        """
        GET /api/market/funding[?symbols=BTC,ETH,SOL]

        Returns current perpetual funding rates for the requested symbols
        (defaults to current trading mode assets).
        Primary source: Hyperliquid. Fallback: Binance USDT-M futures.
        """
        raw_symbols = request.query.get("symbols", "").strip()
        symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()] or None

        from src.dashboard.funding_provider import fetch_funding_rates
        try:
            data = await asyncio.wait_for(
                fetch_funding_rates(symbols), timeout=12.0
            )
        except asyncio.TimeoutError:
            return web.json_response(
                {"error": "funding fetch timed out", "items": [], "count": 0},
                status=504,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("funding_rates handler error: %s", exc)
            return web.json_response(
                {"error": str(exc), "items": [], "count": 0},
                status=500,
            )
        return web.json_response(data)

    async def _handle_market_candles(self, request: web.Request) -> web.Response:
        symbol = str(request.query.get("symbol") or "BTCUSDT").strip().upper()
        timeframe = str(request.query.get("timeframe") or "1h").strip()
        limit = _safe_limit(request.query.get("limit"), default=300, max_value=1000)

        if not symbol.endswith("USDT"):
            return web.json_response({"error": "only USDT pairs are supported"}, status=400)
        allowed_tf = {"1m", "5m", "15m", "1h", "4h", "1d"}
        if timeframe not in allowed_tf:
            return web.json_response(
                {"error": "invalid timeframe", "allowed": sorted(allowed_tf)},
                status=400,
            )

        url_klines = "https://api.binance.com/api/v3/klines"
        url_ticker = "https://api.binance.com/api/v3/ticker/24hr"
        params_klines = {"symbol": symbol, "interval": timeframe, "limit": limit}
        params_ticker = {"symbol": symbol}

        try:
            raw_klines = await self._market_get_json(url_klines, params_klines, ttl_s=2.0)
            ticker = await self._market_get_json(url_ticker, params_ticker, ttl_s=2.0, allow_error=True) or {}
        except asyncio.TimeoutError:
            return web.json_response({"error": "market provider timeout"}, status=504)
        except aiohttp.ClientError:
            return web.json_response({"error": "market provider unavailable"}, status=502)
        except RuntimeError as exc:
            return web.json_response({"error": str(exc)}, status=502)

        candles: list[dict[str, Any]] = []
        for row in raw_klines:
            if not isinstance(row, list) or len(row) < 6:
                continue
            candles.append(
                {
                    "time": int(row[0] // 1000),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        if not candles:
            return web.json_response({"error": "empty market data"}, status=502)

        stats = {
            "last_price": float(ticker.get("lastPrice") or candles[-1]["close"]),
            "price_change_pct_24h": float(ticker.get("priceChangePercent") or 0.0),
            "volume_24h": float(ticker.get("quoteVolume") or 0.0),
            "high_24h": float(ticker.get("highPrice") or 0.0),
            "low_24h": float(ticker.get("lowPrice") or 0.0),
        }
        return web.json_response(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "count": len(candles),
                "candles": candles,
                "stats": stats,
                "source": "binance_spot",
            }
        )

    async def _handle_market_depth(self, request: web.Request) -> web.Response:
        symbol = str(request.query.get("symbol") or "BTCUSDT").strip().upper()
        limit = _safe_limit(request.query.get("limit"), default=20, max_value=100)
        if not symbol.endswith("USDT"):
            return web.json_response({"error": "only USDT pairs are supported"}, status=400)

        url_depth = "https://api.binance.com/api/v3/depth"
        params_depth = {"symbol": symbol, "limit": limit}
        try:
            raw = await self._market_get_json(url_depth, params_depth, ttl_s=1.0)
        except asyncio.TimeoutError:
            return web.json_response({"error": "market provider timeout"}, status=504)
        except aiohttp.ClientError:
            return web.json_response({"error": "market provider unavailable"}, status=502)
        except RuntimeError as exc:
            return web.json_response({"error": str(exc)}, status=502)

        bids_raw = raw.get("bids") or []
        asks_raw = raw.get("asks") or []
        bids = [{"price": float(p), "qty": float(q)} for p, q in bids_raw[:limit]]
        asks = [{"price": float(p), "qty": float(q)} for p, q in asks_raw[:limit]]
        if not bids or not asks:
            return web.json_response({"error": "empty order book"}, status=502)

        best_bid = bids[0]["price"]
        best_ask = asks[0]["price"]
        spread = max(0.0, best_ask - best_bid)
        spread_bps = (spread / best_bid * 10000.0) if best_bid > 0 else 0.0
        bid_notional = sum(x["price"] * x["qty"] for x in bids)
        ask_notional = sum(x["price"] * x["qty"] for x in asks)
        imbalance = (bid_notional - ask_notional) / (bid_notional + ask_notional) if (bid_notional + ask_notional) > 0 else 0.0

        return web.json_response(
            {
                "symbol": symbol,
                "limit": limit,
                "bids": bids,
                "asks": asks,
                "summary": {
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread": spread,
                    "spread_bps": spread_bps,
                    "bid_notional": bid_notional,
                    "ask_notional": ask_notional,
                    "imbalance": imbalance,
                },
                "source": "binance_spot",
            }
        )

    async def _handle_market_trades(self, request: web.Request) -> web.Response:
        symbol = str(request.query.get("symbol") or "BTCUSDT").strip().upper()
        limit = _safe_limit(request.query.get("limit"), default=30, max_value=200)
        if not symbol.endswith("USDT"):
            return web.json_response({"error": "only USDT pairs are supported"}, status=400)

        url_trades = "https://api.binance.com/api/v3/aggTrades"
        params = {"symbol": symbol, "limit": limit}
        try:
            raw = await self._market_get_json(url_trades, params, ttl_s=1.0)
        except asyncio.TimeoutError:
            return web.json_response({"error": "market provider timeout"}, status=504)
        except aiohttp.ClientError:
            return web.json_response({"error": "market provider unavailable"}, status=502)
        except RuntimeError as exc:
            return web.json_response({"error": str(exc)}, status=502)

        items: list[dict[str, Any]] = []
        for row in raw:
            items.append(
                {
                    "trade_id": int(row.get("a") or 0),
                    "price": float(row.get("p") or 0.0),
                    "qty": float(row.get("q") or 0.0),
                    "timestamp": int((row.get("T") or 0) / 1000),
                    "is_sell": bool(row.get("m")),
                }
            )
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return web.json_response({"symbol": symbol, "items": items, "count": len(items), "source": "binance_spot"})

    async def _handle_market_diagnostics(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                "items": {k: _diag_public_view(v) for k, v in self._market_diag.items()},
                "cache_size": len(self._market_cache),
                "time_utc": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def _handle_market_status(self, _: web.Request) -> web.Response:
        now = asyncio.get_running_loop().time()
        items = [_diag_public_view(v) for v in self._market_diag.values()]
        open_count = sum(1 for it in items if it.get("breaker_open"))
        total_errors = sum(int(it.get("errors") or 0) for it in items)
        total_calls = sum(int(it.get("calls") or 0) for it in items)
        stale_served = sum(int(it.get("stale_served") or 0) for it in items)
        next_recovery_s = None
        if self._market_breaker_until:
            remains = [max(0.0, t - now) for t in self._market_breaker_until.values() if t > now]
            if remains:
                next_recovery_s = round(min(remains), 2)
        if not items:
            state = "unknown"
        elif open_count > 0:
            state = "degraded"
        elif total_errors > 0:
            state = "warning"
        else:
            state = "healthy"
        return web.json_response(
            {
                "state": state,
                "breaker_open_keys": open_count,
                "calls": total_calls,
                "errors": total_errors,
                "stale_served": stale_served,
                "next_recovery_s": next_recovery_s,
                "time_utc": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def _market_get_json(
        self,
        url: str,
        params: dict[str, Any],
        ttl_s: float,
        allow_error: bool = False,
    ) -> Any:
        key = f"{url}?{json.dumps(params, sort_keys=True)}"
        now = asyncio.get_running_loop().time()
        diag = self._market_diag.setdefault(
            key,
            {
                "calls": 0,
                "cache_hits": 0,
                "stale_served": 0,
                "errors": 0,
                "last_error": None,
                "last_latency_ms": None,
                "avg_latency_ms": None,
                "failure_streak": 0,
                "breaker_open": False,
                "breaker_open_until_s": None,
            },
        )
        diag["calls"] += 1
        cached = self._market_cache.get(key)
        if cached and cached[0] > now:
            diag["cache_hits"] += 1
            return cached[1]

        breaker_until = float(self._market_breaker_until.get(key) or 0.0)
        if breaker_until > now:
            diag["breaker_open"] = True
            diag["breaker_open_until_s"] = round(breaker_until - now, 2)
            if cached:
                diag["stale_served"] += 1
                return cached[1]
            if allow_error:
                return None
            raise RuntimeError("market circuit breaker open")
        diag["breaker_open"] = False
        diag["breaker_open_until_s"] = None

        delays = [0.15, 0.45, 0.9]
        last_exc: Exception | None = None
        # Reuse the long-lived ClientSession created in _on_startup; falling
        # back to a per-call session only if startup hasn't run yet (shouldn't
        # happen in production but keeps the code defensive in tests).
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                connector=aiohttp.TCPConnector(limit=16, ttl_dns_cache=300),
            )
        session = self._http
        for attempt, delay in enumerate(delays, start=1):
            start = asyncio.get_running_loop().time()
            try:
                async with self._market_sem:
                    async with session.get(url, params=params) as resp:
                        if resp.status != 200:
                            if allow_error:
                                return None
                            raise RuntimeError(f"market provider error ({resp.status})")
                        data = await resp.json()
                latency_ms = int((asyncio.get_running_loop().time() - start) * 1000)
                prev = diag["avg_latency_ms"]
                diag["last_latency_ms"] = latency_ms
                diag["avg_latency_ms"] = latency_ms if prev is None else round((prev * 0.8) + (latency_ms * 0.2), 2)
                lat_samples = diag.setdefault("latencies_ms", [])
                lat_samples.append(latency_ms)
                if len(lat_samples) > 120:
                    del lat_samples[:-120]
                self._market_cache[key] = (now + ttl_s, data)
                self._market_fail_streak[key] = 0
                diag["failure_streak"] = 0
                diag["breaker_open"] = False
                diag["breaker_open_until_s"] = None
                return data
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                diag["errors"] += 1
                diag["last_error"] = f"{type(exc).__name__}: {exc}"
                streak = int(self._market_fail_streak.get(key) or 0) + 1
                self._market_fail_streak[key] = streak
                diag["failure_streak"] = streak
                if streak >= self.MARKET_BREAKER_THRESHOLD:
                    open_until = asyncio.get_running_loop().time() + self.MARKET_BREAKER_COOLDOWN_S
                    self._market_breaker_until[key] = open_until
                    diag["breaker_open"] = True
                    diag["breaker_open_until_s"] = round(self.MARKET_BREAKER_COOLDOWN_S, 2)
                    if cached:
                        diag["stale_served"] += 1
                        return cached[1]
                if attempt >= len(delays):
                    break
                await asyncio.sleep(delay)
        if last_exc:
            raise last_exc
        raise RuntimeError("market provider unknown error")

    async def _handle_killswitch_status(self, _: web.Request) -> web.Response:
        """Read-only state of the kill switch file. Safe to expose without auth.
        UIs poll this to render the engage/release buttons accordingly."""
        active = KILL_SWITCH_FILE.exists()
        meta: dict[str, Any] = {"active": active, "path": str(KILL_SWITCH_FILE)}
        if active:
            try:
                stat = KILL_SWITCH_FILE.stat()
                meta["mtime_utc"] = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
                # Trim absurd payloads — kill switch reasons are short by spec.
                content = KILL_SWITCH_FILE.read_text(
                    encoding="utf-8", errors="replace"
                )[:512]
                meta["reason"] = content.strip() or None
            except OSError as exc:
                meta["read_error"] = str(exc)
        return web.json_response(meta)

    async def _handle_killswitch_engage(self, request: web.Request) -> web.Response:
        """Atomically create the kill-switch file. Requires confirm=ENGAGE.

        We deliberately demand a literal confirmation string in the body to
        prevent accidental engagement (e.g. CSRF replays would also have to
        guess this string in addition to the auth token).
        """
        body = await self._safe_json_body(request)
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid json body"}, status=400)
        if str(body.get("confirm") or "").upper() != "ENGAGE":
            return web.json_response(
                {"error": "missing confirm=ENGAGE in body"}, status=400
            )
        reason = str(body.get("reason") or "").strip()[:240]
        try:
            await asyncio.to_thread(KILL_SWITCH_FILE.parent.mkdir, parents=True, exist_ok=True)
            content = (
                f"engaged_at={datetime.now(timezone.utc).isoformat()}\n"
                f"reason={reason or 'manual'}\n"
                f"source=dashboard\n"
            )
            await asyncio.to_thread(KILL_SWITCH_FILE.write_text, content, "utf-8")
        except OSError as exc:
            logger.exception("killswitch engage failed: %s", exc)
            return web.json_response({"error": "fs error"}, status=500)
        try:
            await MekkaRepository.log_event(
                agent="NickFury",
                event="KILL_SWITCH_ENGAGED",
                severity="CRITICAL",
                message=f"Kill switch engaged via dashboard. Reason: {reason or '-'}",
                payload={"source": "dashboard", "reason": reason},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("killswitch audit log failed: %s", exc)
        try:
            from src.services.telegram_alerter import TelegramAlerter as _TA
            asyncio.create_task(_TA().alert(
                event="KILL_SWITCH_ENGAGED", severity="CRITICAL", agent="Batman",
                message=f"🔴 Kill switch ENGAJADO pelo dashboard. Motivo: {reason or 'manual'}. "
                        f"Toda nova execução está bloqueada.",
            ))
        except Exception:  # noqa: BLE001
            pass
        self._metrics["killswitch_engaged_total"] += 1
        # Invalidate the broadcast cache so the next /ws frame reflects the
        # new state immediately (instead of after the 1.5s TTL).
        self._payload_cache.clear()
        return web.json_response({"active": True, "reason": reason or None}, status=200)

    async def _handle_killswitch_release(self, request: web.Request) -> web.Response:
        """Remove the kill-switch file. Requires confirm=RELEASE."""
        body = await self._safe_json_body(request)
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid json body"}, status=400)
        if str(body.get("confirm") or "").upper() != "RELEASE":
            return web.json_response(
                {"error": "missing confirm=RELEASE in body"}, status=400
            )
        operator = str(body.get("operator") or "").strip()[:120]
        try:
            existed = KILL_SWITCH_FILE.exists()
            if existed:
                await asyncio.to_thread(KILL_SWITCH_FILE.unlink)
        except OSError as exc:
            logger.exception("killswitch release failed: %s", exc)
            return web.json_response({"error": "fs error"}, status=500)
        try:
            await MekkaRepository.log_event(
                agent="NickFury",
                event="KILL_SWITCH_RELEASED",
                severity="WARNING",
                message=f"Kill switch released via dashboard by {operator or 'unknown'}",
                payload={"source": "dashboard", "operator": operator, "had_file": existed},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("killswitch audit log failed: %s", exc)
        try:
            from src.services.telegram_alerter import TelegramAlerter as _TA
            asyncio.create_task(_TA().alert(
                event="KILL_SWITCH_RELEASED", severity="WARNING", agent="Batman",
                message=f"🟢 Kill switch LIBERADO pelo dashboard por {operator or 'operador'}. "
                        f"Execuções normalizadas.",
            ))
        except Exception:  # noqa: BLE001
            pass
        self._metrics["killswitch_released_total"] += 1
        self._payload_cache.clear()
        return web.json_response({"active": False, "had_file": existed}, status=200)

    # ------------------------------------------------------------------
    # Runtime control plane — liga/desliga/reinicia o loop de trading.
    # O dashboard é always-on; o RuntimeController é dono do runtime que
    # consome tokens de LLM. Desligar cancela o loop → zero token spend.
    # ------------------------------------------------------------------
    async def _handle_system_status(self, _: web.Request) -> web.Response:
        """Estado atual do runtime. Read-only; sem controller acoplado o
        estado é 'unknown' (ex.: dashboard rodando sem run.py)."""
        if self._runtime is None:
            return web.json_response({"state": "unknown", "running": False})
        return web.json_response(self._runtime.status())

    async def _handle_system_start(self, _: web.Request) -> web.Response:
        """Liga o runtime. Idempotente (o controller trata o no-op)."""
        if self._runtime is None:
            return web.json_response({"error": "no runtime controller"}, status=503)
        result = await self._runtime.start()
        return web.json_response(result)

    async def _handle_system_stop(self, request: web.Request) -> web.Response:
        """Desliga o runtime — cancela o loop e cessa todo token spend.
        Exige body {"confirm":"STOP"} para evitar parada acidental."""
        if self._runtime is None:
            return web.json_response({"error": "no runtime controller"}, status=503)
        body = await self._safe_json_body(request)
        if not isinstance(body, dict) or str(body.get("confirm") or "").upper() != "STOP":
            return web.json_response({"error": "confirm required"}, status=400)
        result = await self._runtime.stop()
        return web.json_response(result)

    async def _handle_system_reboot(self, request: web.Request) -> web.Response:
        """Reinicia o runtime (stop seguido de start). Exige
        body {"confirm":"REBOOT"}."""
        if self._runtime is None:
            return web.json_response({"error": "no runtime controller"}, status=503)
        body = await self._safe_json_body(request)
        if not isinstance(body, dict) or str(body.get("confirm") or "").upper() != "REBOOT":
            return web.json_response({"error": "confirm required"}, status=400)
        result = await self._runtime.reboot()
        return web.json_response(result)

    async def _handle_office_v2_index(self, _: web.Request) -> web.FileResponse:
        """Serve the Office v2 single-page app entrypoint."""
        return web.FileResponse(STATIC_DIR / "office_v2" / "index.html")

    async def _handle_office_v4_index(self, _: web.Request) -> web.FileResponse:
        """Serve the Office v4 (new living-floor design) entrypoint."""
        return web.FileResponse(STATIC_DIR / "office_v4" / "index.html")

    # ------------------------------------------------------------------
    # Auth flow (login / logout / whoami)
    # ------------------------------------------------------------------
    async def _handle_auth_login(self, request: web.Request) -> web.Response:
        """Operator login. Body ``{"password": "..."}`` returns a signed
        session cookie + the token in JSON for header-style use.

        When no password is configured (development default) we return 503
        to make the misconfiguration loud — the UI can decide whether to
        show the login form or hide it.
        """
        from src.dashboard.auth import (
            COOKIE_NAME, check_password, is_login_enabled, issue_token,
        )

        if not is_login_enabled():
            return web.json_response(
                {"error": "login not configured", "enabled": False},
                status=503,
            )

        # --- Rate limiting: block IPs that exceed failed-attempt threshold ---
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        client_ip = client_ip or request.remote or "unknown"
        if not _check_login_rate_limit(client_ip):
            logger.warning(
                "login rate-limit hit for ip=%s (max %d attempts / %ds window)",
                client_ip, _LOGIN_MAX_ATTEMPTS, _LOGIN_WINDOW_SECONDS,
            )
            return web.json_response(
                {"error": "too many failed attempts — try again later"},
                status=429,
                headers={"Retry-After": str(_LOGIN_WINDOW_SECONDS)},
            )

        body = await self._safe_json_body(request) or {}
        if not check_password(body.get("password")):
            return web.json_response({"error": "invalid credentials"}, status=401)

        # Successful login: clear the rate-limit counter for this IP.
        _clear_login_rate_limit(client_ip)
        import time as _time
        bundle = issue_token(subject="operator")
        # `Max-Age` is bounded by exp; HttpOnly + SameSite=Lax keep the
        # cookie out of cross-site requests; Secure is set automatically
        # by aiohttp when responding over HTTPS.
        ttl = max(60, int(bundle["expires_at"] - int(_time.time())))
        resp = web.json_response(
            {
                "authenticated": True,
                "expires_at": bundle["expires_at"],
                "subject": bundle["subject"],
                "token": bundle["token"],
            }
        )
        resp.set_cookie(
            COOKIE_NAME,
            bundle["token"],
            httponly=True,
            samesite="Lax",
            secure=request.scheme == "https",
            path="/",
            max_age=ttl,
        )
        return resp

    async def _handle_auth_logout(self, request: web.Request) -> web.Response:
        """Clear the session cookie. Always succeeds (idempotent)."""
        from src.dashboard.auth import COOKIE_NAME
        resp = web.json_response({"authenticated": False})
        resp.del_cookie(COOKIE_NAME, path="/")
        return resp

    async def _handle_auth_me(self, request: web.Request) -> web.Response:
        """Whoami / session-state probe used by the frontend."""
        from src.dashboard.auth import (
            COOKIE_NAME, is_login_enabled, verify_token,
        )

        cookie = request.cookies.get(COOKIE_NAME, "")
        payload = verify_token(cookie) if cookie else None
        return web.json_response(
            {
                "authenticated": bool(payload),
                "expires_at": (payload or {}).get("exp"),
                "subject": (payload or {}).get("sub"),
                "login_enabled": is_login_enabled(),
                "shared_secret_enabled": bool(_DASHBOARD_TOKEN),
            }
        )

    async def _handle_agents_tasks(self, _: web.Request) -> web.Response:
        """Latest task per agent — Office v2 ``fetchAgentTasks`` shape.

        Logic lives in ``office_v2_endpoints.build_agents_tasks_payload``;
        this handler just owns the timeout and error paths.
        """
        from src.dashboard.office_v2_endpoints import build_agents_tasks_payload
        try:
            audits = await asyncio.wait_for(
                MekkaRepository.list_recent_audit(limit=200), timeout=2.0
            )
        except asyncio.TimeoutError:
            return web.json_response({"error": "audit query timed out"}, status=504)
        except Exception as exc:  # noqa: BLE001
            logger.warning("agents/tasks query failed: %s", exc)
            return web.json_response({"items": {}})
        return web.json_response(build_agents_tasks_payload(audits))

    async def _handle_audit_feed(self, request: web.Request) -> web.Response:
        """Audit feed in Office v2 wire format: ``[{t, who, msg}, ...]``."""
        from src.dashboard.office_v2_endpoints import build_audit_feed_payload
        n = _safe_limit(request.query.get("n"), default=20, max_value=200)
        try:
            audits = await asyncio.wait_for(
                MekkaRepository.list_recent_audit(limit=n), timeout=2.0
            )
        except asyncio.TimeoutError:
            return web.json_response({"error": "audit query timed out"}, status=504)
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit/feed query failed: %s", exc)
            return web.json_response({"items": []})
        return web.json_response(build_audit_feed_payload(audits))

    # ------------------------------------------------------------------
    # Story 064 — Memory Stats  GET /api/memory/stats
    # ------------------------------------------------------------------

    async def _handle_memory_stats(self, _: web.Request) -> web.Response:
        """
        GET /api/memory/stats

        Returns aggregated episodic memory statistics from the
        agent_memories table (Story 063).

        Response shape
        --------------
        {
          "total": int,           // total memory entries
          "pending": int,         // awaiting resolution
          "resolved": int,        // WIN + LOSS + NEUTRAL
          "by_symbol": [          // one row per (symbol, action) combo
            {
              "symbol": str,
              "action": "LONG"|"SHORT",
              "total": int,
              "wins": int,
              "losses": int,
              "neutrals": int,
              "win_rate": float | null,  // wins / (wins+losses) * 100
              "avg_pnl": float,
              "avg_hold_h": float | null,
              "recent": [         // last 5 resolved entries
                {"outcome": str, "pnl_usd": float, "hours_ago": float|null}
              ]
            }
          ],
          "generated_at": str     // ISO-8601 UTC
        }
        """
        from datetime import datetime, timezone  # noqa: WPS433
        from sqlalchemy import select, func  # noqa: WPS433
        from src.persistence.db import get_session  # noqa: WPS433
        from src.persistence.models import AgentMemoryRecord  # noqa: WPS433

        now_utc = datetime.now(timezone.utc)

        try:
            async with get_session() as session:
                # --- totals ---
                total_q = await session.execute(
                    select(func.count()).select_from(AgentMemoryRecord)
                )
                total: int = total_q.scalar_one() or 0

                pending_q = await session.execute(
                    select(func.count()).select_from(AgentMemoryRecord).where(
                        AgentMemoryRecord.outcome == "PENDING"
                    )
                )
                pending: int = pending_q.scalar_one() or 0

                # --- by (symbol, action) ---
                rows_q = await session.execute(
                    select(AgentMemoryRecord)
                    .where(AgentMemoryRecord.outcome.in_(["WIN", "LOSS", "NEUTRAL"]))
                    .order_by(AgentMemoryRecord.timestamp.desc())
                    .limit(2000)
                )
                rows: list[AgentMemoryRecord] = list(rows_q.scalars().all())

            # group in Python
            groups: dict[tuple[str, str], list[AgentMemoryRecord]] = {}
            for r in rows:
                key = (r.symbol, r.action)
                groups.setdefault(key, []).append(r)

            by_symbol = []
            for (sym, act), grp in sorted(groups.items()):
                wins = sum(1 for r in grp if r.outcome == "WIN")
                losses = sum(1 for r in grp if r.outcome == "LOSS")
                neutrals = sum(1 for r in grp if r.outcome == "NEUTRAL")
                decided = wins + losses
                win_rate = round(100.0 * wins / decided, 1) if decided > 0 else None
                pnls = [r.pnl_usd for r in grp if r.pnl_usd is not None]
                avg_pnl = round(sum(pnls) / len(pnls), 4) if pnls else 0.0
                holds = [r.holding_hours for r in grp if r.holding_hours is not None]
                avg_hold = round(sum(holds) / len(holds), 1) if holds else None
                recent = []
                for r in grp[:5]:
                    hours_ago: float | None = None
                    if r.resolved_at:
                        ts = r.resolved_at
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        hours_ago = round((now_utc - ts).total_seconds() / 3600, 1)
                    recent.append({
                        "outcome": r.outcome,
                        "pnl_usd": round(r.pnl_usd or 0.0, 4),
                        "hours_ago": hours_ago,
                    })
                by_symbol.append({
                    "symbol": sym,
                    "action": act,
                    "total": len(grp),
                    "wins": wins,
                    "losses": losses,
                    "neutrals": neutrals,
                    "win_rate": win_rate,
                    "avg_pnl": avg_pnl,
                    "avg_hold_h": avg_hold,
                    "recent": recent,
                })

            # sort by most active first
            by_symbol.sort(key=lambda x: x["total"], reverse=True)

            return web.json_response({
                "total": total,
                "pending": pending,
                "resolved": total - pending,
                "by_symbol": by_symbol,
                "generated_at": now_utc.isoformat(),
            })

        except Exception as exc:  # noqa: BLE001
            logger.warning("[MemoryStats] query failed: %s", exc)
            return web.json_response({
                "total": 0, "pending": 0, "resolved": 0,
                "by_symbol": [], "generated_at": now_utc.isoformat(),
                "error": str(exc),
            })

    async def _handle_risk_panel(self, _: web.Request) -> web.Response:
        """
        GET /api/risk/panel — Story 073

        Returns a consolidated real-time risk snapshot for the Risk Panel
        dashboard widget. All fields are computed from the DB + settings.

        Response shape
        --------------
        {
          "exposure": {
            "open_notional_usd": float,
            "cap_usd": float,
            "cap_pct": float,
            "used_pct": float           // open_notional / cap_usd * 100
          },
          "daily_pnl": {
            "pnl_usd": float,
            "equity_usd": float,
            "pnl_pct": float,
            "profit_target_pct": float,  // pause threshold
            "kill_threshold_pct": float  // auto-kill threshold
          },
          "cooldowns": [               // symbols in re-entry cooldown
            {"symbol": str, "remaining_min": float, "expires_utc": str}
          ],
          "blacklisted": [             // symbols in auto-blacklist
            {"symbol": str, "expires_utc": str, "consecutive_sl_hits": int}
          ],
          "atrs": [                    // ATR% per trading asset
            {"symbol": str, "atr_pct": float | null}
          ],
          "generated_at": str
        }
        """
        import json as _json  # noqa: WPS433
        from datetime import datetime, timezone, timedelta  # noqa: WPS433
        from pathlib import Path  # noqa: WPS433
        from src.persistence.repository import MekkaRepository  # noqa: WPS433
        from src.analytics.atr import compute_atr_pct  # noqa: WPS433

        now_utc = datetime.now(timezone.utc)

        # ── Exposure ──────────────────────────────────────────────────
        try:
            _positions = await MekkaRepository.list_paper_filled_trades(limit=500)
            from collections import defaultdict  # noqa: WPS433
            _long_qty: dict = defaultdict(float)
            _short_qty: dict = defaultdict(float)
            _long_notional: dict = defaultdict(float)
            _short_notional: dict = defaultdict(float)
            for t in _positions:
                sym = (t.symbol or "").upper()
                qty = float(t.quantity or 0)
                price = float(t.avg_price or 0)
                if (t.side or "long").lower() == "long":
                    _long_qty[sym] += qty
                    _long_notional[sym] += qty * price
                else:
                    _short_qty[sym] += qty
                    _short_notional[sym] += qty * price
            _open_notional = 0.0
            for sym in set(_long_qty) | set(_short_qty):
                net = _long_qty[sym] - _short_qty[sym]
                if net > 1e-8:
                    _open_notional += _long_notional[sym]
                elif net < -1e-8:
                    _open_notional += _short_notional[sym]
            if settings.paper_trading:
                _equity = await MekkaRepository.get_today_peak_equity()
            else:
                _live_portfolio = await self._get_live_portfolio_context(max_age_s=2.0)
                _equity = float(_live_portfolio.get("equity_usd") or 0.0)
            _cap_usd = _equity * settings.max_portfolio_exposure_pct
            _used_pct = round(_open_notional / _cap_usd * 100, 1) if _cap_usd > 0 else 0.0
            exposure = {
                "open_notional_usd": round(_open_notional, 2),
                "cap_usd": round(_cap_usd, 2),
                "cap_pct": round(settings.max_portfolio_exposure_pct * 100, 1),
                "used_pct": _used_pct,
            }
        except Exception as _e:
            exposure = {"open_notional_usd": 0, "cap_usd": 0, "cap_pct": 20, "used_pct": 0, "error": str(_e)}

        # ── Daily PnL ──────────────────────────────────────────────────
        try:
            _pnl_usd = await MekkaRepository.get_today_pnl_usd()
            if "_equity" in dir():
                _eq = _equity
            elif settings.paper_trading:
                _eq = await MekkaRepository.get_today_peak_equity()
            else:
                _live_portfolio = await self._get_live_portfolio_context(max_age_s=2.0)
                _eq = float(_live_portfolio.get("equity_usd") or 0.0)
            _pnl_pct = round(_pnl_usd / _eq * 100, 3) if _eq > 0 else 0.0
            daily_pnl = {
                "pnl_usd": round(_pnl_usd, 2),
                "equity_usd": round(_eq, 2),
                "pnl_pct": _pnl_pct,
                "profit_target_pct": round(settings.daily_profit_target_pct * 100, 1),
                "kill_threshold_pct": round(settings.max_daily_drawdown_pct * 100, 1),
            }
        except Exception as _e:
            daily_pnl = {"pnl_usd": 0, "equity_usd": 0, "pnl_pct": 0, "profit_target_pct": 5, "kill_threshold_pct": 10, "error": str(_e)}

        # ── Cooldowns ──────────────────────────────────────────────────
        cooldowns: list[dict] = []
        if settings.reentry_cooldown_minutes > 0:
            try:
                _trading_assets = settings.trading_assets
                for _sym in _trading_assets:
                    _sl_time = await MekkaRepository.get_last_sl_close_time(
                        symbol=_sym, lookback_minutes=settings.reentry_cooldown_minutes
                    )
                    if _sl_time is not None:
                        _ts = _sl_time if _sl_time.tzinfo else _sl_time.replace(tzinfo=timezone.utc)
                        _elapsed = (now_utc - _ts).total_seconds() / 60
                        _remaining = max(0.0, settings.reentry_cooldown_minutes - _elapsed)
                        _expires = _ts + timedelta(minutes=settings.reentry_cooldown_minutes)
                        cooldowns.append({
                            "symbol": _sym.upper(),
                            "remaining_min": round(_remaining, 1),
                            "expires_utc": _expires.isoformat(),
                        })
            except Exception:  # noqa: BLE001
                pass

        # ── Blacklisted symbols ─────────────────────────────────────────
        blacklisted: list[dict] = []
        try:
            _data_dir = Path("data")
            if _data_dir.exists():
                for _bl_file in _data_dir.glob(".blacklist_*.json"):
                    try:
                        _bl = _json.loads(_bl_file.read_text())
                        _expires_str = _bl.get("expires", "")
                        if _expires_str:
                            _expires_dt = datetime.fromisoformat(_expires_str)
                            if _expires_dt.tzinfo is None:
                                _expires_dt = _expires_dt.replace(tzinfo=timezone.utc)
                            if now_utc < _expires_dt:
                                blacklisted.append({
                                    "symbol": _bl.get("symbol", ""),
                                    "expires_utc": _expires_str,
                                    "consecutive_sl_hits": _bl.get("consecutive_sl_hits", 0),
                                    "remaining_h": round((_expires_dt - now_utc).total_seconds() / 3600, 1),
                                })
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

        # ── ATR per trading asset ───────────────────────────────────────
        atrs: list[dict] = []
        if settings.atr_sizing_enabled:
            for _sym in settings.trading_assets:
                try:
                    _atr = await compute_atr_pct(_sym, lookback=settings.atr_lookback_candles)
                    atrs.append({"symbol": _sym.upper(), "atr_pct": _atr})
                except Exception:  # noqa: BLE001
                    atrs.append({"symbol": _sym.upper(), "atr_pct": None})

        return web.json_response({
            "exposure": exposure,
            "daily_pnl": daily_pnl,
            "cooldowns": cooldowns,
            "blacklisted": blacklisted,
            "atrs": atrs,
            "generated_at": now_utc.isoformat(),
        })

    async def _handle_leaderboard(self, request: web.Request) -> web.Response:
        """
        GET /api/leaderboard?days=90 — Story 079

        Returns symbol-level performance stats for the Symbol Leaderboard page.

        Response shape
        --------------
        {
          "items": [
            {
              "symbol": "BTC",
              "trades": 12,
              "wins": 8,
              "losses": 4,
              "win_rate": 0.667,       // null if no decided trades
              "total_pnl_usd": 540.0,
              "avg_pnl_usd": 45.0,
              "best_trade_usd": 210.0,
              "worst_trade_usd": -85.0,
              "sharpe": 1.23           // null if < 3 trades
            },
            ...
          ],
          "lookback_days": 90,
          "generated_at": "2026-05-14T12:00:00+00:00"
        }
        """
        from datetime import datetime, timezone  # noqa: WPS433

        qs = request.rel_url.query
        try:
            days = max(1, min(int(qs.get("days", "90")), 365))
        except (ValueError, TypeError):
            days = 90

        try:
            items = await MekkaRepository.list_symbol_stats(lookback_days=days)
        except Exception as exc:  # noqa: BLE001
            logger.warning("leaderboard query failed: %s", exc)
            items = []

        return web.json_response({
            "items": items,
            "lookback_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    async def _handle_trades_export(self, request: web.Request) -> web.Response:
        """
        GET /api/trades/export?format=csv|json&status=FILLED,PAPER&limit=5000
        Story 082 — Trade Export.

        Downloads the full trade history as CSV or JSON.
        Query params:
          format  — "csv" (default) or "json"
          status  — comma-separated status filter (default: all)
          limit   — max rows (default 5000, max 50000)
        """
        import csv as _csv  # noqa: WPS433
        import io as _io    # noqa: WPS433
        from datetime import datetime, timezone  # noqa: WPS433

        qs = request.rel_url.query
        fmt = qs.get("format", "csv").lower()
        status_raw = qs.get("status", "").strip()
        status_filter = [s.strip().upper() for s in status_raw.split(",") if s.strip()] or None
        try:
            limit = max(1, min(int(qs.get("limit", "5000")), 50_000))
        except (ValueError, TypeError):
            limit = 5_000

        try:
            rows = await MekkaRepository.export_trades(limit=limit, status_filter=status_filter)
        except Exception as exc:  # noqa: BLE001
            logger.warning("trades export failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")

        if fmt == "json":
            body = json.dumps({"trades": rows, "count": len(rows), "exported_at": ts}, indent=2)
            return web.Response(
                body=body.encode(),
                content_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="mekka_trades_{ts}.json"'},
            )

        # CSV output
        _FIELDS = [
            "id", "timestamp_utc", "symbol", "status", "side",
            "quantity", "avg_price", "notional_usd", "is_paper",
            "stop_loss", "take_profit", "realized_pnl_usd",
            "triggered_by", "trigger_reason",
            "signal_confidence", "signal_action", "risk_verdict",
        ]
        buf = _io.StringIO()
        writer = _csv.DictWriter(buf, fieldnames=_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel compat
        return web.Response(
            body=csv_bytes,
            content_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="mekka_trades_{ts}.csv"',
                "Content-Length": str(len(csv_bytes)),
            },
        )

    async def _handle_pnl_heatmap(self, request: web.Request) -> web.Response:
        """
        GET /api/pnl/heatmap?days=90 — Story 089.

        Returns a 7×24 heatmap of average trade PnL grouped by
        UTC day-of-week (0=Mon) and hour-of-day.

        Response shape
        --------------
        {
          "heatmap": {
            "0": {"9": -12.5, "14": 40.2, ...},  // Mon, hour → avg PnL
            ...
            "6": {...}                             // Sun
          },
          "max_abs": float,    // for colour scale normalisation
          "lookback_days": int,
          "generated_at": str
        }
        """
        from datetime import datetime, timezone, timedelta  # noqa: WPS433
        from collections import defaultdict  # noqa: WPS433

        qs = request.rel_url.query
        try:
            days = max(7, min(int(qs.get("days", "90")), 365))
        except (ValueError, TypeError):
            days = 90

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            rows = await MekkaRepository.export_trades(limit=50_000, status_filter=["FILLED", "PAPER"])
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=500)

        # Accumulate PnL per (weekday, hour)
        bucket_pnl: dict[tuple[int,int], list[float]] = defaultdict(list)
        for t in rows:
            ts_str = t.get("timestamp_utc")
            pnl = t.get("realized_pnl_usd")
            if not ts_str or pnl is None:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
                bucket_pnl[(ts.weekday(), ts.hour)].append(float(pnl))
            except (ValueError, TypeError):
                continue

        # Build 7×24 dict with averages
        heatmap: dict[str, dict[str, float]] = {}
        max_abs = 0.0
        for dow in range(7):
            heatmap[str(dow)] = {}
            for hr in range(24):
                pnls = bucket_pnl.get((dow, hr), [])
                if pnls:
                    avg = round(sum(pnls) / len(pnls), 2)
                    heatmap[str(dow)][str(hr)] = avg
                    max_abs = max(max_abs, abs(avg))

        return web.json_response({
            "heatmap": heatmap,
            "max_abs": round(max_abs, 2),
            "lookback_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    async def _handle_trades_calendar(self, request: web.Request) -> web.Response:
        """
        GET /api/trades/calendar?year=YYYY&month=MM — Story 107.

        Returns trade count and PnL per calendar day for the requested month.

        Response shape
        --------------
        {
          "year": int,
          "month": int,
          "days": [
            {"day": 1, "count": 3, "pnl_usd": 42.5, "win_count": 2, "loss_count": 1},
            ...
          ],
          "generated_at": str
        }
        """
        from datetime import datetime, timezone  # noqa: WPS433

        qs = request.rel_url.query
        now_utc = datetime.now(timezone.utc)
        try:
            year = int(qs.get("year", str(now_utc.year)))
        except (ValueError, TypeError):
            year = now_utc.year
        try:
            month = int(qs.get("month", str(now_utc.month)))
            month = max(1, min(month, 12))
        except (ValueError, TypeError):
            month = now_utc.month

        try:
            days_data = await MekkaRepository.get_monthly_trade_calendar(year=year, month=month)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=500)

        return web.json_response({
            "year": year,
            "month": month,
            "days": days_data,
            "generated_at": now_utc.isoformat(),
        })

    async def _handle_pnl_hourly(self, request: web.Request) -> web.Response:
        """
        GET /api/pnl/hourly?days=30 — Story 109.

        Returns PnL statistics grouped by UTC hour (0-23) for the last N days.
        Useful for identifying which hours of the day are most profitable.

        Response shape
        --------------
        {
          "hourly": {
            "9":  {"hour": 9, "avg_pnl": 12.5, "total_pnl": 125.0, "count": 10,
                   "win_count": 7, "loss_count": 3},
            ...
          },
          "lookback_days": int,
          "generated_at": str
        }
        """
        from datetime import datetime, timezone  # noqa: WPS433

        qs = request.rel_url.query
        try:
            days = max(1, min(int(qs.get("days", "30")), 365))
        except (ValueError, TypeError):
            days = 30

        try:
            hourly = await MekkaRepository.get_pnl_by_hour(days=days)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=500)

        return web.json_response({
            "hourly": hourly,
            "lookback_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    async def _handle_gates_timeline(self, request: web.Request) -> web.Response:
        """
        GET /api/gates/timeline?limit=50 — Story 112.

        Returns the most recent gate rejection events logged by Batman.
        Useful for understanding which risk gates are firing most often.

        Response shape
        --------------
        {
          "events": [
            {
              "timestamp_utc": str,
              "symbol": str,
              "gate_id": str,
              "reason": str,
              "breached": [str]
            },
            ...
          ],
          "count": int,
          "generated_at": str
        }
        """
        from datetime import datetime, timezone  # noqa: WPS433

        qs = request.rel_url.query
        try:
            limit = max(1, min(int(qs.get("limit", "50")), 500))
        except (ValueError, TypeError):
            limit = 50

        try:
            events = await MekkaRepository.get_gate_rejections(limit=limit)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=500)

        return web.json_response({
            "events": events,
            "count": len(events),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    async def _handle_signals_export(self, request: web.Request) -> web.Response:
        """
        GET /api/signals/export?format=csv|json&limit=5000 — Story 093.
        Downloads all Vision signals as CSV or JSON.
        """
        import csv as _csv  # noqa: WPS433
        import io as _io    # noqa: WPS433
        from datetime import datetime, timezone  # noqa: WPS433

        qs = request.rel_url.query
        fmt = qs.get("format", "csv").lower()
        try:
            limit = max(1, min(int(qs.get("limit", "5000")), 50_000))
        except (ValueError, TypeError):
            limit = 5_000

        try:
            rows = await MekkaRepository.export_signals(limit=limit)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=500)

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")

        if fmt == "json":
            body = json.dumps({"signals": rows, "count": len(rows), "exported_at": ts}, indent=2)
            return web.Response(
                body=body.encode(),
                content_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="mekka_signals_{ts}.json"'},
            )

        _FIELDS = ["id", "timestamp_utc", "symbol", "action", "confidence",
                   "entry_price", "stop_loss", "take_profit", "risk_reward_ratio",
                   "size_pct", "leverage", "risk_verdict", "signal_quality_score"]
        buf = _io.StringIO()
        writer = _csv.DictWriter(buf, fieldnames=_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = buf.getvalue().encode("utf-8-sig")
        return web.Response(
            body=csv_bytes,
            content_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="mekka_signals_{ts}.csv"',
                "Content-Length": str(len(csv_bytes)),
            },
        )

    async def _handle_session_stats(self, _: web.Request) -> web.Response:
        """
        GET /api/session/stats — Story 092.

        Returns today's session summary: trades, PnL, win rate, best/worst.

        Response shape
        --------------
        {
          "trades_today": int,
          "pnl_today_usd": float,
          "wins_today": int,
          "losses_today": int,
          "win_rate_today": float | null,
          "best_trade_usd": float | null,
          "worst_trade_usd": float | null,
          "equity_usd": float,
          "generated_at": str
        }
        """
        from datetime import datetime, timezone, timedelta  # noqa: WPS433

        now_utc = datetime.now(timezone.utc)
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            all_rows = await MekkaRepository.export_trades(
                limit=500, status_filter=["FILLED", "PAPER"]
            )
            today_rows = [
                r for r in all_rows
                if r.get("timestamp_utc") and
                datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=timezone.utc) >= today_start
            ]
            pnls = [r["realized_pnl_usd"] for r in today_rows if r.get("realized_pnl_usd") is not None]
            wins = sum(1 for p in pnls if p > 0)
            losses = sum(1 for p in pnls if p < 0)
            decided = wins + losses
            if settings.paper_trading:
                equity = await MekkaRepository.get_today_peak_equity()
            else:
                live_portfolio = await self._get_live_portfolio_context(max_age_s=2.0)
                equity = float(live_portfolio.get("equity_usd") or 0.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("session_stats error: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

        return web.json_response({
            "trades_today": len(today_rows),
            "pnl_today_usd": round(sum(pnls), 2) if pnls else 0.0,
            "wins_today": wins,
            "losses_today": losses,
            "win_rate_today": round(wins / decided, 3) if decided > 0 else None,
            "best_trade_usd": round(max(pnls), 2) if pnls else None,
            "worst_trade_usd": round(min(pnls), 2) if pnls else None,
            "equity_usd": round(equity, 2),
            "generated_at": now_utc.isoformat(),
        })

    async def _handle_positions_orders(self, _: web.Request) -> web.Response:
        """GET /api/positions/orders — live reduce-only SL/TP orders on the venue.
        Read-only, fail-silent: always 200 with the provider's stub shape on error."""
        from src.dashboard.positions_provider import fetch_open_orders
        try:
            return web.json_response(await fetch_open_orders(), status=200)
        except Exception as exc:  # noqa: BLE001
            logger.warning("positions/orders failed: %s", exc)
            return web.json_response(
                {"items": [], "count": 0, "source": "stub", "supported": False,
                 "message": f"error: {type(exc).__name__}"}, status=200)

    async def _handle_positions(self, _: web.Request) -> web.Response:
        """Open positions read via the Hyperliquid `info.user_state` endpoint.

        [Story 099] In paper mode, passes the current mark-price cache so
        unrealised PnL and duration are shown.  Falls back to the stub shape
        on every sad path so the dashboard never breaks.
        """
        from src.dashboard.positions_provider import fetch_positions

        # Pass cached mark prices so paper positions show live uPnL (Story 099)
        _mark_prices: dict[str, float] = dict(self._mark_prices) if self._mark_prices else {}

        try:
            data = await fetch_positions(mark_prices=_mark_prices)
        except Exception as exc:  # noqa: BLE001
            logger.exception("positions provider crashed: %s", exc)
            data = {
                "items": [],
                "count": 0,
                "source": "stub",
                "supported": False,
                "message": f"Positions provider crashed: {type(exc).__name__}",
            }
        return web.json_response(data)

    async def _handle_positions_close(self, request: web.Request) -> web.Response:
        """Close a paper position by inserting an offsetting trade record.

        Body: {"symbol": "BTC", "side": "LONG"}
        Creates a PAPER trade on the opposite side with same quantity,
        so the positions aggregator nets it out to zero.
        """
        from src.config.settings import settings as _s
        from src.models.execution import ExecutionResult, ExecutionStatus
        from datetime import datetime, timezone
        import uuid

        body = await self._safe_json_body(request)
        if not body:
            return web.json_response({"error": "body required"}, status=400)

        symbol = str(body.get("symbol", "")).upper().strip()
        side = str(body.get("side", "")).upper().strip()

        if not symbol or side not in ("LONG", "SHORT"):
            return web.json_response(
                {"error": "symbol e side (LONG|SHORT) são obrigatórios"}, status=400
            )

        # ── LIVE close (Bybit/Binance): place a real reduce-only market order
        # and cancel resting SL/TP. The paper logic below only nets the local
        # DB and would NOT close a real position — so live must take this path.
        if not _s.paper_trading:
            try:
                from src.agents.iron_man import IronMan  # noqa: WPS433
                res = await IronMan().close_position(symbol, side)
                ok = res.status.value in ("FILLED", "PARTIAL")
                if ok:
                    try:
                        res.metadata = {**(res.metadata or {}), "manual_close": True}
                        await MekkaRepository.save_trade(res)
                    except Exception as _save_exc:  # noqa: BLE001
                        logger.warning("manual live close save_trade failed: %s", _save_exc)
                    await MekkaRepository.log_event(
                        agent="Dashboard", event="POSITION_CLOSED", severity="INFO",
                        symbol=symbol,
                        message=f"Posição LIVE {symbol} {side} fechada manualmente — qty={res.quantity}",
                        payload={"order_id": res.order_id, "exchange": _s.active_exchange},
                    )
                    # Resolve 3 memory stores (063/183/186). PnL best-effort: live
                    # exit lacks entry avg without an extra exchange roundtrip, so
                    # passes 0.0 → NEUTRAL classification. Better than a silent gap.
                    try:
                        from src.services.trade_outcome_resolver import (  # noqa: WPS433
                            resolve_trade_memories as _rtm_live,
                        )
                        await _rtm_live(
                            symbol=symbol,
                            pnl_usd=0.0,
                            action=side,
                            trade_id=str(res.order_id) if res.order_id else None,
                        )
                    except Exception as _rtm_live_exc:  # noqa: BLE001
                        logger.debug(
                            "dashboard live close memory resolve skipped: %s",
                            _rtm_live_exc,
                        )
                    return web.json_response({
                        "status": "closed", "symbol": symbol, "side": side,
                        "quantity": res.quantity, "avg_price": res.avg_price,
                        "order_id": res.order_id, "is_paper": False,
                    })
                return web.json_response({
                    "status": res.status.value.lower() or "error",
                    "error": res.error or "Falha ao fechar posição live.",
                }, status=200)
            except Exception as exc:
                logger.error("live positions_close error: %s", exc, exc_info=True)
                return web.json_response({"error": f"Erro ao fechar posição live: {exc}"}, status=500)

        try:
            # Calculate open net position
            trades = await MekkaRepository.list_paper_filled_trades()
            long_qty = sum(
                t.quantity for t in trades
                if t.symbol.upper() == symbol and (t.side or "long").lower() == "long"
            )
            short_qty = sum(
                t.quantity for t in trades
                if t.symbol.upper() == symbol and (t.side or "long").lower() == "short"
            )
            net = long_qty - short_qty

            if abs(net) < 1e-8:
                return web.json_response(
                    {"error": f"Nenhuma posição aberta em {symbol}"}, status=400
                )

            # Average entry price of the open side
            if net > 0:
                open_qty = long_qty
                open_trades = [
                    t for t in trades
                    if t.symbol.upper() == symbol and (t.side or "long").lower() == "long"
                ]
            else:
                open_qty = short_qty
                open_trades = [
                    t for t in trades
                    if t.symbol.upper() == symbol and (t.side or "long").lower() == "short"
                ]

            avg_px = (
                sum(t.quantity * t.avg_price for t in open_trades) / open_qty
                if open_qty > 0 else 0.0
            )
            close_qty = abs(net)
            close_side = "short" if net > 0 else "long"

            close_result = ExecutionResult(
                timestamp=datetime.now(timezone.utc),
                symbol=symbol,
                status=ExecutionStatus.PAPER,
                is_paper=True,
                side=close_side,
                quantity=close_qty,
                avg_price=avg_px,
                notional_usd=close_qty * avg_px,
                order_id=f"CLOSE-{symbol}-{uuid.uuid4().hex[:8]}",
                metadata={"action": "manual_close"},
            )

            trade_db_id = await MekkaRepository.save_trade(close_result)

            await MekkaRepository.log_event(
                agent="Dashboard",
                event="POSITION_CLOSED",
                severity="INFO",
                symbol=symbol,
                message=f"Posição {symbol} {side} fechada manualmente — qty={close_qty:.6f} @ ${avg_px:,.2f}",
                payload={"trade_id": trade_db_id, "order_id": close_result.order_id},
            )

            # Resolve 3 memory stores (063/183/186). PnL computed from mark price
            # cache vs avg_px; falls back to 0.0 (NEUTRAL) if mark not cached.
            try:
                from src.services.trade_outcome_resolver import (  # noqa: WPS433
                    resolve_trade_memories as _rtm_paper,
                )
                _mark_paper = 0.0
                try:
                    _mp = self._mark_prices or {}
                    _mark_paper = float(_mp.get(symbol, 0.0) or 0.0)
                except Exception:  # noqa: BLE001
                    pass
                _pnl_paper = 0.0
                if _mark_paper > 0 and avg_px > 0:
                    _sign = 1.0 if side == "LONG" else -1.0
                    _pnl_paper = (_mark_paper - avg_px) * close_qty * _sign
                await _rtm_paper(
                    symbol=symbol,
                    pnl_usd=_pnl_paper,
                    action=side,
                    trade_id=close_result.order_id,
                )
            except Exception as _rtm_paper_exc:  # noqa: BLE001
                logger.debug(
                    "dashboard paper close memory resolve skipped: %s",
                    _rtm_paper_exc,
                )

            return web.json_response({
                "status": "closed",
                "symbol": symbol,
                "side": side,
                "quantity": round(close_qty, 8),
                "avg_price": round(avg_px, 2),
                "order_id": close_result.order_id,
                "trade_id": trade_db_id,
            })

        except Exception as exc:
            logger.error("positions_close error: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)

    # ── Runtime settings (Super Agressivo / Altcoins) ──────────────────────

    @staticmethod
    def _runtime_settings_path() -> "Path":
        from pathlib import Path
        return Path("data/runtime_settings.json")

    def _load_runtime_settings(self) -> dict:
        try:
            p = self._runtime_settings_path()
            if p.exists():
                return json.loads(p.read_text())
        except Exception:
            pass
        return {"super_aggressive": False, "altcoins_enabled": False}

    def _save_runtime_settings(self, data: dict) -> None:
        p = self._runtime_settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))

    async def _handle_settings_get(self, _: web.Request) -> web.Response:
        cfg = self._load_runtime_settings()
        # [Bybit] Expose active exchange so frontend can show it
        cfg.setdefault("active_exchange", settings.active_exchange)
        # B1 — expor configuração efetiva de RISCO (read-only) para o painel
        # /settings poder mostrar limites atuais sem precisar abrir .env.
        # Operator continua editando via .env + restart (segurança).
        try:
            cfg["risk_config"] = {
                "max_position_size_pct": float(getattr(settings, "max_position_size_pct", 0.02)),
                "max_leverage": int(getattr(settings, "max_leverage", 5)),
                "max_daily_drawdown_pct": float(getattr(settings, "max_daily_drawdown_pct", 0.10)),
                "max_total_capital_pct": float(getattr(settings, "max_total_capital_pct", 0.30)),
                "max_consecutive_exec_errors": int(getattr(settings, "max_consecutive_exec_errors", 3)),
                "max_consecutive_vision_fallbacks": int(getattr(settings, "max_consecutive_vision_fallbacks", 5)),
                "trading_assets": list(getattr(settings, "trading_assets", []) or []),
                "paper_trading": bool(getattr(settings, "paper_trading", True)),
                "live_trading_confirmed": bool(getattr(settings, "live_trading_confirmed", False)),
                "phantom_reconciliation_enabled": bool(getattr(settings, "phantom_reconciliation_enabled", True)),
                "mainnet_first_week_hard_clamp": bool(getattr(settings, "mainnet_first_week_hard_clamp", True)),
                "llm_cost_aware_routing": bool(getattr(settings, "llm_cost_aware_routing", False)),
                # Funding rate gate (Story 075) — bloqueia ou reduz tamanho
                # quando funding rate está em extremo (crowded positioning).
                "funding_gate_enabled": bool(getattr(settings, "funding_gate_enabled", True)),
                "funding_long_block_pct": float(getattr(settings, "funding_long_block_pct", 0.10)),
                "funding_short_block_pct": float(getattr(settings, "funding_short_block_pct", -0.10)),
                # Trading hours gate (Story 076) — só opera dentro de janela UTC.
                "trading_hours_enabled": bool(getattr(settings, "trading_hours_enabled", False)),
                "trading_hours_start_utc": int(getattr(settings, "trading_hours_start_utc", 7)),
                "trading_hours_end_utc": int(getattr(settings, "trading_hours_end_utc", 23)),
            }
        except Exception:  # noqa: BLE001
            cfg["risk_config"] = {}
        return web.json_response(cfg)

    async def _handle_settings_set(self, request: web.Request) -> web.Response:
        body = await self._safe_json_body(request)
        if not body:
            return web.json_response({"error": "body required"}, status=400)

        cfg = self._load_runtime_settings()
        if "super_aggressive" in body:
            cfg["super_aggressive"] = bool(body["super_aggressive"])
        if "altcoins_enabled" in body:
            cfg["altcoins_enabled"] = bool(body["altcoins_enabled"])

        self._save_runtime_settings(cfg)

        await MekkaRepository.log_event(
            agent="Dashboard",
            event="SETTINGS_CHANGED",
            severity="INFO",
            message=(
                f"super_aggressive={'ON' if cfg['super_aggressive'] else 'OFF'} "
                f"altcoins={'ON' if cfg['altcoins_enabled'] else 'OFF'}"
            ),
            payload=cfg,
        )

        return web.json_response({"status": "ok", "settings": cfg})

    # ── Live Price Feed ────────────────────────────────────────────────────
    # The provider implementation lives in `src.services.price_feed` and is
    # dispatched by `make_price_feed()` based on ACTIVE_EXCHANGE. The task
    # is created in `_on_startup` and shut down in `_on_shutdown` along with
    # the other background tasks.

    async def _live_price_broadcast_loop(self) -> None:
        """Push live prices + open position PnL to all /ws/live clients every 1s."""
        from src.dashboard.positions_provider import (  # noqa: WPS433
            _fetch_paper_positions,
            get_paper_equity_summary,
        )
        from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
        while True:
            try:
                await asyncio.sleep(1.0)
                if not self._live_sockets:
                    continue
                prices = dict(self._mark_prices)
                # Enrich paper positions with live mark prices + real PnL
                pos_data: dict = {}
                try:
                    if settings.paper_trading:
                        pos_data = await _fetch_paper_positions()
                    else:
                        from src.dashboard.positions_provider import fetch_positions  # noqa: WPS433
                        pos_data = await fetch_positions()
                except Exception:
                    pos_data = {}
                items = list(pos_data.get("items") or [])
                for _item in items:
                    _sym = _item.get("symbol", "")
                    _mark = (
                        prices.get(_sym)
                        or prices.get(_sym + "-PERP")
                        or prices.get(_sym.replace("-PERP", ""))
                        or _item.get("entry_price", 0.0)
                    )
                    _item["mark_price"] = _mark
                    _qty = float(_item.get("size", 0))
                    _entry = float(_item.get("entry_price", 0) or 0)
                    if _entry and _qty:
                        if (_item.get("side") or "LONG").upper() == "LONG":
                            _item["pnl_usd"] = round((_mark - _entry) * _qty, 2)
                        else:
                            _item["pnl_usd"] = round((_entry - _mark) * _qty, 2)
                        _item["pnl_pct"] = round(
                            (_item["pnl_usd"] / (_entry * _qty)) * 100, 3
                        ) if _entry * _qty else 0.0
                # [C3] Compute dynamic paper equity using mark prices
                equity_summary: dict = {}
                if settings.paper_trading:
                    try:
                        equity_summary = await get_paper_equity_summary(mark_prices=prices)
                    except Exception:
                        equity_summary = {}

                # ── Drawdown circuit-breaker monitor ──────────────────────
                # Fires a Telegram alert at most once per UTC day when
                # equity drops > max_daily_drawdown_pct from the day's peak.
                try:
                    _eq_now = float(equity_summary.get("equity_usd") or 0)
                    if _eq_now > 0:
                        _today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        # Reset dedup on new UTC day
                        if self._dd_alert_date != _today_utc:
                            self._dd_alert_date = _today_utc
                            self._dd_alerted = False
                            self._dd_peak_equity = _eq_now
                        # Update peak
                        if _eq_now > self._dd_peak_equity:
                            self._dd_peak_equity = _eq_now
                        # Check threshold
                        if (
                            not self._dd_alerted
                            and self._dd_peak_equity > 0
                        ):
                            _dd_pct = (self._dd_peak_equity - _eq_now) / self._dd_peak_equity * 100
                            _threshold = settings.max_daily_drawdown_pct * 100
                            if _dd_pct >= _threshold:
                                self._dd_alerted = True  # dedup before async call
                                asyncio.create_task(
                                    TelegramAlerter().drawdown_alert(
                                        current_equity=_eq_now,
                                        peak_equity=self._dd_peak_equity,
                                        drawdown_pct=_dd_pct,
                                        threshold_pct=_threshold,
                                    )
                                )
                                logger.warning(
                                    "[DrawdownMonitor] ALERT fired — dd=%.2f%% peak=%.2f eq=%.2f",
                                    _dd_pct, self._dd_peak_equity, _eq_now,
                                )
                except Exception as _dd_exc:
                    logger.debug("drawdown monitor error: %s", _dd_exc)

                _payload = json.dumps({
                    "type": "live_tick",
                    "prices": prices,
                    "positions": items,
                    "equity": equity_summary,
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                _stale: list[web.WebSocketResponse] = []
                for _ws in list(self._live_sockets):
                    if _ws.closed:
                        _stale.append(_ws)
                        continue
                    try:
                        await asyncio.wait_for(_ws.send_str(_payload), timeout=1.0)
                    except Exception:
                        _stale.append(_ws)
                for _ws in _stale:
                    self._live_sockets.discard(_ws)
            except asyncio.CancelledError:
                return
            except Exception as _exc:
                logger.debug("live broadcast error: %s", _exc)

    async def _handle_ws_live(self, request: web.Request) -> web.WebSocketResponse:
        """GET /ws/live — WebSocket endpoint for live Hyperliquid prices and PnL.

        The client receives JSON ticks every 1 s:
          { "type": "live_tick",
            "prices": {"BTC": 104321.0, "ETH": 3412.5, ...},
            "positions": [{... with live mark_price + pnl_usd + pnl_pct ...}],
            "ts": "2026-05-12T..." }
        """
        # Origin check — same defence as /ws
        _origin = request.headers.get("Origin")
        if not _is_origin_allowed(_origin):
            return web.Response(status=403, text="forbidden origin")

        _ws = web.WebSocketResponse(heartbeat=20)
        await _ws.prepare(request)
        self._live_sockets.add(_ws)
        try:
            # Send current snapshot immediately on connect
            if self._mark_prices:
                try:
                    await _ws.send_str(json.dumps({
                        "type": "live_tick",
                        "prices": dict(self._mark_prices),
                        "positions": [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }))
                except Exception:
                    pass
            async for _msg in _ws:
                if _msg.type == WSMsgType.TEXT and _msg.data == "ping":
                    await _ws.send_str("pong")
                elif _msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._live_sockets.discard(_ws)
        return _ws

    async def _handle_hl_candles(self, request: web.Request) -> web.Response:
        """GET /api/hl/candles?symbol=BTC&tf=15m&limit=200

        Returns OHLCV from the Hyperliquid public REST API (no CCXT needed).
        Uses POST /info with type=candleSnapshot — no auth required.
        Lightweight-charts expects { time, open, high, low, close, volume }.
        """
        _sym = str(request.query.get("symbol") or "BTC").strip().upper()
        _tf = str(request.query.get("tf") or "15m").strip()
        _limit = _safe_limit(request.query.get("limit"), default=200, max_value=500)

        _allowed_tf = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "1w"}
        if _tf not in _allowed_tf:
            return web.json_response(
                {"error": "invalid timeframe", "allowed": sorted(_allowed_tf)},
                status=400,
            )

        # ms per candle — used to compute startTime
        _tf_ms: dict[str, int] = {
            "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
            "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
            "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000, "1w": 604_800_000,
        }
        import time as _time  # noqa: WPS433
        import aiohttp as _aiohttp  # noqa: WPS433
        _now_ms = int(_time.time() * 1000)
        _start_ms = _now_ms - _limit * _tf_ms.get(_tf, 900_000)

        _hl_api = "https://api.hyperliquid.xyz/info"
        _payload = {
            "type": "candleSnapshot",
            "req": {"coin": _sym, "interval": _tf, "startTime": _start_ms, "endTime": _now_ms},
        }
        try:
            async with _aiohttp.ClientSession() as _sess:
                async with _sess.post(
                    _hl_api,
                    json=_payload,
                    timeout=_aiohttp.ClientTimeout(total=12),
                ) as _resp:
                    if _resp.status != 200:
                        _body = await _resp.text()
                        logger.warning("hl_candles API %d for %s: %s", _resp.status, _sym, _body[:200])
                        return web.json_response(
                            {"error": f"Hyperliquid API returned {_resp.status}", "detail": _body[:200]},
                            status=502,
                        )
                    _raw: list = await _resp.json(content_type=None)
        except asyncio.TimeoutError:
            return web.json_response({"error": "Hyperliquid OHLCV timeout"}, status=504)
        except Exception as _exc:
            logger.warning("hl_candles fetch error %s: %s", _sym, _exc)
            return web.json_response({"error": str(_exc)}, status=502)

        # Hyperliquid candleSnapshot response fields:
        #   t=open_time_ms, T=close_time_ms, s=coin, i=interval,
        #   o=open, h=high, l=low, c=close, v=volume, n=num_trades
        _candles = []
        for _r in (_raw or []):
            if not isinstance(_r, dict):
                continue
            try:
                _candles.append({
                    "time":   int(_r["t"]) // 1000,
                    "open":   float(_r["o"]),
                    "high":   float(_r["h"]),
                    "low":    float(_r["l"]),
                    "close":  float(_r["c"]),
                    "volume": float(_r["v"]),
                })
            except (KeyError, TypeError, ValueError):
                continue

        _last_price = self._mark_prices.get(_sym) or (_candles[-1]["close"] if _candles else 0.0)
        return web.json_response({
            "symbol": _sym,
            "tf": _tf,
            "count": len(_candles),
            "candles": _candles,
            "last_price": _last_price,
        })

    async def _handle_metrics(self, _: web.Request) -> web.Response:
        """Prometheus text-format exposition of internal counters/gauges.

        Heavy lifting (descriptor table + live gauge derivation) lives in
        :mod:`src.dashboard.metrics`; this handler is just a thin adapter
        that snapshots in-memory state and serialises it.
        """
        from src.dashboard.metrics import (
            derive_runtime_metrics,
            render_prometheus,
        )

        values = derive_runtime_metrics(
            self._metrics,
            sockets_count=len(self._sockets),
            market_diag=self._market_diag,
            market_cache_size=len(self._market_cache),
            payload_latencies_ms=self._payload_latencies_ms,
            broadcast_latencies_ms=self._broadcast_latencies_ms,
            percentile_fn=_percentile,
        )
        return web.Response(
            text=render_prometheus(values),
            content_type="text/plain",
            charset="utf-8",
        )

    async def _safe_json_body(self, request: web.Request) -> Any:
        """Read JSON body without crashing on bad/empty payloads. Returns
        None for malformed bodies; callers decide how to react."""
        try:
            return await request.json()
        except (json.JSONDecodeError, ValueError):
            return None
        except Exception:  # noqa: BLE001
            return None

    async def _handle_pnl_series(self, request: web.Request) -> web.Response:
        """Daily-PnL time series for the Equity & PnL dashboard panel.

        ``days`` clamps the window (1..365). Output is oldest-first so the
        frontend can pipe it straight into Chart.js.
        """
        days = _safe_limit(
            request.query.get("days") or request.query.get("window"),
            default=30,
            max_value=365,
        )
        rows = await MekkaRepository.list_recent_daily_pnl(limit=days)
        items = [
            {
                "date_utc": r.date_utc,
                "is_paper": bool(r.is_paper),
                "starting_equity": float(r.starting_equity or 0.0),
                "ending_equity": float(r.ending_equity or 0.0),
                "pnl_usd": float(r.pnl_usd or 0.0),
                "pnl_pct": float(r.pnl_pct or 0.0),
                "drawdown_pct": float(r.drawdown_pct or 0.0),
                "trades_count": int(r.trades_count or 0),
                "wins": int(r.wins or 0),
                "losses": int(r.losses or 0),
            }
            for r in rows
        ]
        return web.json_response({"items": items, "count": len(items), "days": days})

    async def _handle_trades_timeline(self, request: web.Request) -> web.Response:
        """Hourly buckets of executions for the last ``hours`` hours.

        Output: ``{ hours, items: [{ hour_utc, filled, paper, rejected, error,
        skipped, total }] }``. The UI renders a stacked bar chart so the
        operator can spot fill-rate regressions and execution gaps at a glance.
        """
        from collections import defaultdict
        hours = _safe_limit(request.query.get("hours"), default=24, max_value=168)
        # Optional symbol filter (B4): query ?symbol=BTC or comma-separated
        # ?symbol=BTC,ETH. Empty/missing returns all symbols (legacy behavior).
        symbol_filter_raw = (request.query.get("symbol") or "").upper().strip()
        symbol_filter = {s.strip() for s in symbol_filter_raw.split(",") if s.strip()}

        try:
            trades = await asyncio.wait_for(
                MekkaRepository.list_trades_within(hours), timeout=3.0
            )
        except asyncio.TimeoutError:
            return web.json_response({"error": "trades query timed out"}, status=504)
        except Exception as exc:  # noqa: BLE001
            logger.warning("trades/timeline query failed: %s", exc)
            return web.json_response({"items": [], "hours": hours})

        if symbol_filter:
            trades = [t for t in trades if (t.symbol or "").upper() in symbol_filter]

        # Aggregate by hour. Status enum from IronMan:
        #   FILLED / PARTIAL / PAPER / SKIPPED / REJECTED / ERROR
        STATUS_BUCKETS = {
            "FILLED": "filled", "PARTIAL": "filled",
            "PAPER": "paper",
            "REJECTED": "rejected", "ERROR": "error", "FAILED": "error",
            "SKIPPED": "skipped", "PENDING": "skipped",
        }
        buckets: dict[str, dict[str, int]] = defaultdict(
            lambda: {"filled": 0, "paper": 0, "rejected": 0, "error": 0, "skipped": 0}
        )
        for t in trades:
            ts = t.timestamp
            hour_key = ts.replace(minute=0, second=0, microsecond=0).isoformat()
            label = STATUS_BUCKETS.get(str(t.status or "").upper(), "skipped")
            buckets[hour_key][label] += 1

        items = []
        for hour, counts in sorted(buckets.items()):
            total = sum(counts.values())
            items.append({"hour_utc": hour, **counts, "total": total})
        return web.json_response({
            "hours": hours,
            "symbol_filter": sorted(symbol_filter) if symbol_filter else None,
            "count": len(items),
            "items": items,
        })

    async def _handle_pnl_benchmark(self, request: web.Request) -> web.Response:
        """Normalized benchmark series for the equity-vs-benchmark overlay.

        For each requested symbol we fetch ``days`` daily candles from the
        existing market endpoint cache and emit ``[date_utc, ratio]`` where
        ratio = close[i] / close[0] (so the curve starts at 1.0 and shows
        relative performance only — operator overlays it on equity curve).
        """
        days = _safe_limit(request.query.get("days"), default=30, max_value=180)
        symbols_raw = (request.query.get("symbols") or "BTCUSDT").upper()
        symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]
        symbols = [s if s.endswith("USDT") else f"{s}USDT" for s in symbols][:4]

        params_template = {"interval": "1d", "limit": str(days)}
        url = "https://api.binance.com/api/v3/klines"
        result: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                raw = await self._market_get_json(
                    url, {"symbol": symbol, **params_template}, ttl_s=60.0,
                    allow_error=True,
                )
            except (asyncio.TimeoutError, aiohttp.ClientError, RuntimeError) as exc:
                logger.warning("benchmark %s failed: %s", symbol, exc)
                continue
            if not raw:
                continue
            closes = []
            for row in raw:
                if not isinstance(row, list) or len(row) < 5:
                    continue
                ts_ms = int(row[0])
                close = float(row[4])
                closes.append((ts_ms, close))
            if not closes:
                continue
            base = closes[0][1] or 1.0
            points = [
                {
                    "date_utc": datetime.fromtimestamp(
                        ts_ms / 1000.0, tz=timezone.utc
                    ).strftime("%Y-%m-%d"),
                    "ratio": round(close / base, 6),
                }
                for ts_ms, close in closes
            ]
            result.append({"symbol": symbol, "points": points, "count": len(points)})

        return web.json_response({"days": days, "series": result})

    async def _handle_equity_curve(self, _: web.Request) -> web.Response:
        """
        GET /api/pnl/equity-curve — Story 077

        Builds a day-by-day equity curve from the DailyPnLRecord table.
        Computes cumulative P&L, drawdown from peak, and win-rate per day.

        Response shape
        --------------
        {
          "labels":         ["2026-05-01", ...],  // date strings
          "equity":         [10000.0, ...],        // cumulative equity (base + cum_pnl)
          "daily_pnl":      [+52.3, -18.0, ...],  // raw daily P&L USD
          "drawdown_pct":   [0.0, -0.5, ...],      // drawdown from running peak (%)
          "cum_return_pct": [0.0, 0.52, ...],      // cumulative return %
          "win_rate_30d":   float,                 // wins / total (last 30 days)
          "sharpe_30d":     float | null,
          "max_drawdown_pct": float,
          "total_days":     int,
          "winning_days":   int,
          "losing_days":    int,
          "generated_at":   str
        }
        """
        from datetime import datetime, timezone  # noqa: WPS433

        now_utc = datetime.now(timezone.utc)
        try:
            rows = await MekkaRepository.list_recent_daily_pnl(limit=180)

            if not rows:
                return web.json_response({
                    "labels": [], "equity": [], "daily_pnl": [], "drawdown_pct": [],
                    "cum_return_pct": [], "win_rate_30d": 0.0, "sharpe_30d": None,
                    "max_drawdown_pct": 0.0, "total_days": 0, "winning_days": 0,
                    "losing_days": 0, "generated_at": now_utc.isoformat(),
                })

            base_equity = settings.paper_equity_usd
            labels, equity_curve, daily_pnl, drawdown_pct, cum_return = [], [], [], [], []

            cum_pnl = 0.0
            peak = base_equity
            min_dd = 0.0

            for row in rows:
                pnl = float(row.pnl_usd or 0.0)
                cum_pnl += pnl
                eq = base_equity + cum_pnl
                peak = max(peak, eq)
                dd = (eq - peak) / peak * 100.0 if peak > 0 else 0.0
                min_dd = min(min_dd, dd)
                ret = (eq - base_equity) / base_equity * 100.0 if base_equity > 0 else 0.0

                labels.append(str(row.date_utc))
                equity_curve.append(round(eq, 2))
                daily_pnl.append(round(pnl, 2))
                drawdown_pct.append(round(dd, 3))
                cum_return.append(round(ret, 3))

            # Stats: last 30 rows
            recent = rows[-30:]
            wins = sum(1 for r in recent if (r.pnl_usd or 0) > 0)
            losses = sum(1 for r in recent if (r.pnl_usd or 0) < 0)
            total = len(recent)
            win_rate = round(wins / total * 100, 1) if total > 0 else 0.0

            # Sharpe (annualised, daily returns / std)
            sharpe = None
            pnl_pcts = [(float(r.pnl_usd or 0) / base_equity) for r in recent if base_equity > 0]
            if len(pnl_pcts) >= 5:
                import statistics  # noqa: WPS433
                avg_r = statistics.mean(pnl_pcts)
                std_r = statistics.stdev(pnl_pcts) if len(pnl_pcts) > 1 else 0
                if std_r > 1e-9:
                    sharpe = round(avg_r / std_r * (365 ** 0.5), 3)

            return web.json_response({
                "labels": labels,
                "equity": equity_curve,
                "daily_pnl": daily_pnl,
                "drawdown_pct": drawdown_pct,
                "cum_return_pct": cum_return,
                "win_rate_30d": win_rate,
                "sharpe_30d": sharpe,
                "max_drawdown_pct": round(min_dd, 3),
                "total_days": total,
                "winning_days": wins,
                "losing_days": losses,
                "generated_at": now_utc.isoformat(),
            })

        except Exception as exc:  # noqa: BLE001
            logger.warning("[EquityCurve] error: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def _handle_pnl_summary(self, request: web.Request) -> web.Response:
        days = _safe_limit(
            request.query.get("days") or request.query.get("window"),
            default=30,
            max_value=365,
        )
        try:
            data = await asyncio.wait_for(
                MekkaRepository.get_pnl_summary(window_days=days), timeout=3.0
            )
        except asyncio.TimeoutError:
            return web.json_response({"error": "pnl summary timed out"}, status=504)

        try:
            if settings.paper_trading:
                from src.dashboard.positions_provider import get_paper_equity_summary  # noqa: WPS433
                eq = await asyncio.wait_for(
                    get_paper_equity_summary(mark_prices=dict(self._mark_prices)), timeout=2.0
                )
                data["paper_equity"] = eq
                if "window" in data and eq.get("equity_usd"):
                    data["window"]["latest_equity_usd"] = eq["equity_usd"]
            else:
                live_portfolio = await self._get_live_portfolio_context(max_age_s=2.0)
                if (
                    "window" in data
                    and live_portfolio.get("is_live_ok")
                    and float(live_portfolio.get("equity_usd") or 0.0) > 0
                ):
                    data["window"]["latest_equity_usd"] = round(
                        float(live_portfolio["equity_usd"]), 2
                    )
                    data["window"]["available_balance_usd"] = round(
                        float(live_portfolio.get("available_balance_usd") or 0.0), 2
                    )
                    data["window"]["margin_used_usd"] = round(
                        float(live_portfolio.get("margin_used_usd") or 0.0), 2
                    )
                    data["window"]["wallet_source"] = live_portfolio.get("source")
        except Exception as _exc:
            logger.debug("dynamic equity summary failed: %s", _exc)

        return web.json_response(data)

    async def _handle_performance(self, request: web.Request) -> web.Response:
        """
        GET /api/performance[?days=30]

        Runs Deadpool and returns a PerformanceReport as JSON.

        Query params
        ------------
        days : int, 1–365, default 30 — rolling window for the report.

        Response shape
        --------------
        All fields from PerformanceReport.to_audit_payload(), plus
        ``generated_at`` (ISO 8601 UTC string).

        Errors
        ------
        504 — Deadpool timed out (DB slow or not initialised yet).
        500 — unexpected error.
        """
        _Deadpool = Deadpool
        if _Deadpool is None:
            from src.agents.deadpool import Deadpool as _Deadpool

        days = _safe_limit(request.query.get("days"), default=30, max_value=365)
        try:
            dp = _Deadpool(repo=MekkaRepository)
            report = await asyncio.wait_for(dp.run(window_days=days), timeout=10.0)
            return web.json_response(report.to_audit_payload())
        except asyncio.TimeoutError:
            return web.json_response(
                {"error": "performance report timed out"}, status=504
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("_handle_performance error: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    # ------------------------------------------------------------------
    # Trading Mode — GET /api/mode  POST /api/mode
    # ------------------------------------------------------------------

    async def _handle_mode_get(self, _: web.Request) -> web.Response:
        """Return current trading mode + all presets summary."""
        from src.config.runtime_mode import all_modes_summary, get_mode
        return web.json_response({
            "mode": get_mode(),
            "modes": all_modes_summary(),
        })

    async def _handle_mode_set(self, request: web.Request) -> web.Response:
        """
        POST /api/mode  body: {"mode": "aggressive"}

        Changes the active trading mode immediately (next cycle picks it up).
        Emits a MODE_CHANGED audit event.
        """
        from src.config.runtime_mode import VALID_MODES, get_params, set_mode
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON body"}, status=400)

        mode = body.get("mode", "")
        if mode not in VALID_MODES:
            return web.json_response(
                {"error": f"unknown mode '{mode}'. Valid: {VALID_MODES}"},
                status=400,
            )

        preset = set_mode(mode)

        # Emit audit event so operators can trace mode changes
        try:
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="MODE_CHANGED",
                payload={"mode": mode, "preset": preset},
                severity="INFO",
            )
        except Exception:
            pass  # audit is best-effort

        logger.info("Trading mode changed to '%s' via dashboard API", mode)
        return web.json_response({"mode": mode, "params": get_params()})

    # ------------------------------------------------------------------
    # Active Exchange — GET /api/exchange  POST /api/exchange
    # ------------------------------------------------------------------

    async def _handle_exchange_get(self, _: web.Request) -> web.Response:
        """Return active exchange + per-exchange metadata for the selector."""
        from src.config.runtime_exchange import summary
        return web.json_response(summary())

    async def _handle_exchange_set(self, request: web.Request) -> web.Response:
        """
        POST /api/exchange  body: {"exchange": "binance"}

        Switches the active exchange in memory (next cycle/action picks it up)
        and persists the choice to data/runtime_exchange.json. Rejects unknown
        exchanges or ones without configured credentials. Never touches the
        live-trading double-gate or testnet flags.
        """
        from src.config.runtime_exchange import set_exchange, summary, network_for
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid JSON body"}, status=400)

        ex = str(body.get("exchange", "")).strip().lower()
        try:
            set_exchange(ex)
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

        try:
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="EXCHANGE_CHANGED",
                severity="WARNING",
                message=f"Active exchange switched to {ex} ({network_for(ex)}) via dashboard",
                payload={"exchange": ex, "network": network_for(ex)},
            )
        except Exception:
            pass  # audit is best-effort

        # Pre-warm the newly-selected CCXT exchange so the first trade after the
        # switch is fast (load_markets ~9-18s otherwise). Fire-and-forget.
        async def _prewarm() -> None:
            try:
                if ex in ("binance", "bybit"):
                    from src.agents.iron_man import IronMan
                    await IronMan()._get_ccxt_exchange(ex)
            except Exception as _exc:  # noqa: BLE001
                logger.warning("exchange switch pre-warm failed (non-fatal): %s", _exc)

        asyncio.create_task(_prewarm())

        logger.info("Active exchange changed to '%s' via dashboard API", ex)
        return web.json_response({"ok": True, **summary()})

    async def _handle_mainnet_readiness(self, _: web.Request) -> web.Response:
        """GET /api/mainnet-readiness — run the mainnet preflight and return its
        per-gate verdicts so the operator can see go-live readiness in the
        dashboard (no CLI). Read-only, fail-silent, time-boxed."""
        import sys as _sys
        from pathlib import Path as _Path
        repo_root = str(_Path(__file__).resolve().parents[2])
        try:
            proc = await asyncio.create_subprocess_exec(
                _sys.executable, "scripts/preflight_mainnet.py", "--json",
                cwd=repo_root,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                out, _err = await asyncio.wait_for(proc.communicate(), timeout=25.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return web.json_response({"ok": False, "error": "preflight timed out"}, status=200)
            data = json.loads(out.decode("utf-8") or "{}")
            return web.json_response({"ok": True, **data}, status=200)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mainnet-readiness failed: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=200)

    async def _handle_env(self, _: web.Request) -> web.Response:
        """GET /api/env — environment & safety posture for the UI badge.

        Returns the smallest payload the operator needs to know which
        venue/environment their actions will hit. NEVER returns secrets or
        even partial credential prefixes — the operator can derive that
        from their own .env if they need it.

        The response is intentionally pessimistic on errors: if anything
        below raises, the UI keeps its "???" badge state instead of
        accidentally showing a stale safe-looking value.
        """
        if settings.active_exchange == "hyperliquid":
            network = settings.hyperliquid_network  # "testnet" | "mainnet"
        elif settings.active_exchange == "bybit":
            network = "testnet" if settings.bybit_testnet else "mainnet"
        elif settings.active_exchange == "binance":
            network = "testnet" if settings.binance_testnet else "mainnet"
        else:
            network = "unknown"

        # `mode` collapses paper/testnet/mainnet into the single label the
        # badge uses to pick a colour. Order matters: paper wins because
        # an operator in paper mode is safe even on a mainnet endpoint
        # (no real orders are sent).
        if settings.paper_trading:
            mode = "paper"
        elif network == "mainnet":
            mode = "mainnet"
        elif network == "testnet":
            mode = "testnet"
        else:
            mode = "unknown"

        return web.json_response({
            "exchange": settings.active_exchange,
            "network": network,
            "paper_trading": bool(settings.paper_trading),
            "live_confirmed": bool(settings.live_trading_confirmed),
            "mode": mode,
            # Symbols the system trades — needed by UI dropdowns (filter
            # tradesTimeline by symbol etc). Always safe to expose.
            "trading_assets": list(settings.trading_assets or []),
        })

    async def _handle_report_daily(self, request: web.Request) -> web.Response:
        """
        GET /api/report/daily[?force=1]

        Trigger the daily PnL report on-demand and return the dispatch result.
        Useful for testing webhooks and for the /report Telegram command.
        Does not require auth — reporting is read-only and non-destructive.
        """
        force = request.query.get("force", "0") not in ("0", "false", "")
        if self._daily_reporter is None:
            from src.dashboard.daily_reporter import DailyReporter
            self._daily_reporter = DailyReporter()
        try:
            result = await asyncio.wait_for(
                self._daily_reporter.send_daily_report(force=force),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            return web.json_response({"error": "report send timed out"}, status=504)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response(result)

    async def _handle_report_weekly(self, request: web.Request) -> web.Response:
        """
        GET /api/report/weekly[?force=1]

        [Story 090] Trigger the weekly Deadpool report on-demand.
        Does not require auth — reporting is read-only and non-destructive.
        """
        force = request.query.get("force", "0") not in ("0", "false", "")
        if self._daily_reporter is None:
            from src.dashboard.daily_reporter import DailyReporter
            self._daily_reporter = DailyReporter()
        try:
            result = await asyncio.wait_for(
                self._daily_reporter.send_weekly_report(force=force),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            return web.json_response({"error": "weekly report send timed out"}, status=504)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response(result)

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        # Cross-Site WebSocket Hijacking defence. Without this, any tab the
        # user has open in their browser could connect to ws://host/ws and
        # exfiltrate live signals/trades/audit. We bounce missing/foreign
        # origins before upgrading the connection.
        origin = request.headers.get("Origin")
        if not _is_origin_allowed(origin):
            self._metrics["ws_connections_rejected_total"] += 1
            logger.warning("ws rejected: origin=%r remote=%s", origin, request.remote)
            return web.Response(status=403, text="forbidden origin")

        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)

        self._sockets.add(ws)
        self._metrics["ws_connections_total"] += 1
        try:
            await ws.send_str(
                json.dumps(await self._collect_payload(include_tables=True))
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws initial payload failed: %s", exc)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT and msg.data == "ping":
                    await ws.send_str("pong")
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._sockets.discard(ws)

        return ws

    async def _broadcast_loop(self) -> None:
        # Guarantees the loop never dies silently. Any exception in payload
        # collection, persistence or WS send is logged and we sleep again so
        # connected clients keep receiving updates as soon as the issue clears.
        while True:
            try:
                await asyncio.sleep(2.0)
                if not self._sockets:
                    continue
                self._metrics["broadcasts_total"] += 1
                loop = asyncio.get_running_loop()
                tick_start = loop.time()
                snapshot = await self._collect_payload(include_tables=True)
                await self._persist_snapshot(snapshot)
                payload = json.dumps(snapshot)
                self._record_latency(
                    self._broadcast_latencies_ms,
                    (loop.time() - tick_start) * 1000.0,
                )
                stale: list[web.WebSocketResponse] = []
                # Iterate over a snapshot of the set so concurrent
                # _handle_ws add/discard calls can never raise during iteration.
                for ws in list(self._sockets):
                    if ws.closed:
                        stale.append(ws)
                        continue
                    try:
                        # Backpressure: a single slow client used to block the
                        # entire broadcast. We bound the per-client write time
                        # and drop laggards so other clients still get fresh data.
                        await asyncio.wait_for(ws.send_str(payload), timeout=2.0)
                        self._metrics["ws_messages_sent_total"] += 1
                    except (asyncio.TimeoutError, ConnectionError, RuntimeError):
                        stale.append(ws)
                    except Exception:  # noqa: BLE001
                        stale.append(ws)
                for ws in stale:
                    self._sockets.discard(ws)
                    self._metrics["ws_slow_consumers_dropped_total"] += 1
                    try:
                        await ws.close(code=1011, message=b"slow consumer")
                    except Exception:  # noqa: BLE001
                        pass
            except asyncio.CancelledError:
                # Honour shutdown — re-raise so the awaiting code (in
                # _on_shutdown) can finish cleaning up.
                raise
            except Exception as exc:  # noqa: BLE001
                self._metrics["broadcasts_errors_total"] += 1
                logger.exception("dashboard broadcast loop error: %s", exc)
                # Brief breather to avoid hot-spinning on a persistent failure.
                await asyncio.sleep(1.0)

    @staticmethod
    def _record_latency(buf: list[float], value_ms: float) -> None:
        """Append a latency sample, keeping the newest 240 in memory."""
        buf.append(value_ms)
        if len(buf) > 240:
            del buf[:-240]

    async def _collect_payload(self, include_tables: bool) -> dict:
        # Short-lived cache. The broadcast loop ticks every 2s and several
        # REST endpoints share this builder; serving the same payload twice
        # within the TTL avoids hammering the DB and keeps responses crisp.
        loop = asyncio.get_running_loop()
        ttl = 4.0 if include_tables else 2.0
        cached = self._payload_cache.get(include_tables)
        if cached and cached[0] > loop.time():
            self._metrics["payload_cache_hits_total"] += 1
            return cached[1]
        self._metrics["payload_cache_misses_total"] += 1
        build_start = loop.time()

        # Hard timeouts. If the DB hangs we fail fast and let the broadcast
        # loop's outer try/except log it rather than blocking every WS client.
        try:
            overview = await asyncio.wait_for(
                MekkaRepository.get_overview(), timeout=2.0
            )
        except asyncio.TimeoutError:
            logger.warning("get_overview timed out; serving last known payload")
            if cached:
                return cached[1]
            overview = {}
        from src.config.runtime_mode import get_mode  # noqa: WPS433
        live_portfolio = await self._get_live_portfolio_context(max_age_s=8.0)

        payload = {
            "overview": {
                **overview,
                "mode": settings.mode_label,
                "trading_mode": get_mode(),
                "paper_trading": settings.paper_trading,
                "network": settings.hyperliquid_network,
                "assets": settings.trading_assets,
                "active_exchange": settings.active_exchange,
                "equity_usd": round(float(live_portfolio.get("equity_usd") or 0.0), 2),
                "available_balance_usd": round(float(live_portfolio.get("available_balance_usd") or 0.0), 2),
                "margin_used_usd": round(float(live_portfolio.get("margin_used_usd") or 0.0), 2),
                "portfolio_source": live_portfolio.get("source"),
                "portfolio_error": live_portfolio.get("error"),
            }
        }
        if not include_tables:
            self._payload_cache[include_tables] = (loop.time() + ttl, payload)
            return payload

        try:
            signals, trades, audits, drawdown_pct = await asyncio.wait_for(
                asyncio.gather(
                    MekkaRepository.list_recent_signals(limit=12),
                    MekkaRepository.list_recent_trades(limit=12),
                    MekkaRepository.list_recent_audit(limit=80),
                    MekkaRepository.get_today_drawdown_pct(),
                ),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            logger.warning("payload tables query timed out")
            if cached:
                return cached[1]
            payload["signals"] = []
            payload["trades"] = []
            payload["audit"] = []
            payload["layers"] = []
            payload["timeline"] = []
            payload["symbol_timeline"] = []
            payload["risk_heatmap"] = []
            payload["risk_drilldown"] = []
            payload["anomalies"] = []
            payload["global_alerts"] = []
            payload["hero_sla"] = []
            payload["overview"]["drawdown_pct_today"] = 0.0
            self._payload_cache[include_tables] = (loop.time() + ttl, payload)
            return payload

        payload["signals"] = [
            {
                "timestamp": s.timestamp.isoformat(),
                "symbol": s.symbol,
                "action": s.action,
                "confidence": s.confidence,
                "is_actionable": s.is_actionable,
            }
            for s in signals
        ]
        payload["trades"] = [
            {
                "timestamp": t.timestamp.isoformat(),
                "symbol": t.symbol,
                "status": t.status,
                "side": t.side,
                "notional_usd": t.notional_usd,
                "is_paper": t.is_paper,
            }
            for t in trades
        ]
        payload["audit"] = [
            {
                "timestamp": r.timestamp.isoformat(),
                "agent": r.agent,
                "event": r.event,
                "symbol": r.symbol,
                "severity": r.severity,
                "message": r.message,
                "payload": r.payload or {},
            }
            for r in audits
        ]
        payload["layers"] = _build_layers_snapshot(audits)
        payload["timeline"] = _build_timeline(audits)
        payload["symbol_timeline"] = _build_symbol_timeline(audits)
        payload["risk_heatmap"] = _build_risk_heatmap(audits)
        payload["risk_drilldown"] = _build_risk_drilldown(audits)
        payload["anomalies"] = _build_spiderman_anomalies(audits)
        payload["global_alerts"] = _build_global_alerts(audits, drawdown_pct)
        payload["hero_sla"] = _build_hero_sla(audits)
        payload["overview"]["drawdown_pct_today"] = float(drawdown_pct or 0.0)
        self._record_latency(
            self._payload_latencies_ms,
            (loop.time() - build_start) * 1000.0,
        )
        self._payload_cache[include_tables] = (loop.time() + ttl, payload)
        return payload

    async def _persist_snapshot(self, payload: dict) -> None:
        now = datetime.now(timezone.utc)
        data = json.dumps(payload, ensure_ascii=True)
        latest = SNAPSHOT_DIR / "latest.json"
        await asyncio.to_thread(latest.write_text, data, "utf-8")

        alerts = payload.get("global_alerts", [])
        has_kill = any("KILL_SWITCH" in str(a.get("code", "")) for a in alerts)

        # Outbound webhook fan-out. Fired in a background task so disk I/O
        # below (snapshot/bundle write) doesn't wait on Slack/Telegram.
        # Dispatcher dedups internally so kill switches that linger across
        # broadcast ticks don't spam channels.
        if self._alert_dispatcher is not None and self._alert_dispatcher.has_targets:
            context = payload.get("overview") or {}
            asyncio.create_task(
                self._alert_dispatcher.dispatch(alerts, context),
            )

        # Bundle dedup. Persist a new bundle ONLY when:
        #   (a) we just transitioned from "no kill" → "kill" (front-edge), OR
        #   (b) the kill is still active but we crossed into a new wall-clock
        #       minute (so investigators get one bundle per minute of incident,
        #       not 30 per minute as before).
        # This avoids flooding SNAPSHOT_DIR with hundreds of identical bundles
        # during a sustained kill switch.
        minute_key = now.strftime("%Y%m%dT%H%M")
        if has_kill:
            transition = not self._kill_state_active
            new_minute = self._last_bundle_minute != minute_key
            if transition or new_minute:
                # Second-resolution stamps collide when two bundle-worthy
                # transitions happen inside the same wall-clock second
                # (kill → clear → kill in tests, or rapid breaker churn in
                # prod). Append a microsecond-derived suffix so each bundle
                # gets its own file even on hot loops.
                stamp = now.strftime("%Y%m%dT%H%M%S")
                suffix = f"{now.microsecond:06d}"
                bundle_name = f"incident-bundle-{stamp}-{suffix}.json"
                bundle_path = SNAPSHOT_DIR / bundle_name
                bundle_payload = {
                    "captured_at": now.isoformat(),
                    "overview": payload.get("overview", {}),
                    "alerts": alerts,
                    "risk_heatmap": payload.get("risk_heatmap", []),
                    "hero_sla": payload.get("hero_sla", []),
                    "severity": _compute_severity(payload),
                    "trigger": "transition" if transition else "minute_rollover",
                }
                await asyncio.to_thread(
                    bundle_path.write_text,
                    json.dumps(bundle_payload, ensure_ascii=True),
                    "utf-8",
                )
                self._metrics["incident_bundle_writes_total"] += 1
                self._last_bundle_minute = minute_key
            self._kill_state_active = True
        else:
            # Reset edge tracker as soon as kill clears so the next occurrence
            # generates a fresh "transition" bundle.
            self._kill_state_active = False

        if minute_key != self._last_snapshot_minute:
            self._last_snapshot_minute = minute_key
            path = SNAPSHOT_DIR / f"snapshot-{minute_key}.json"
            await asyncio.to_thread(path.write_text, data, "utf-8")
            self._metrics["snapshot_writes_total"] += 1
            # Lazy retention: prune oldest snapshots/bundles when the new
            # minute lands. Cheap (1x/min) and keeps disk usage bounded.
            await asyncio.to_thread(self._prune_snapshot_dir)

    # ------------------------------------------------------------------
    # LLM Cost Dashboard — GET /api/cost                    (Story 147)
    # ------------------------------------------------------------------

    async def _handle_cost(self, request: web.Request) -> web.Response:
        """GET /api/cost — LLM cost and token usage aggregations.

        Returns per-session totals, per-model breakdown, per-agent breakdown,
        and the last 20 individual calls for live monitoring.
        No auth required (read-only metrics).
        """
        import json as _json
        try:
            from src.services.llm_cost_tracker import get_llm_cost_tracker
            tracker = get_llm_cost_tracker(auto_register=True)
            data = tracker.summary()
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, "cost": data}),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # Pipeline Benchmarks — GET /api/benchmarks             (Story 151)
    # ------------------------------------------------------------------

    async def _handle_benchmarks(self, request: web.Request) -> web.Response:
        """GET /api/benchmarks — pipeline latency metrics.

        Returns per-stage latency percentiles (p50/p95/p99/max), slow cycle
        history, and histogram for monitoring end-to-end pipeline performance.
        Alerts when cycles exceed 30s (configured via pipeline_benchmark).
        No auth required (read-only metrics).
        """
        import json as _json
        try:
            from src.services.pipeline_benchmark import get_pipeline_benchmark
            bench = get_pipeline_benchmark()
            data = bench.summary()
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, "benchmarks": data}),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # Mekka Kernel — GET /api/kernel  POST /api/kernel/invoke (Story 153)
    # ------------------------------------------------------------------

    async def _handle_kernel(self, request: web.Request) -> web.Response:
        """GET /api/kernel — list registered plugins and tool definitions.

        Returns all @mekka_function functions exposed to LLM function calling,
        with full OpenAI-compatible schema for each tool.
        No auth required (read-only schema discovery).
        """
        import json as _json
        try:
            from src.services.mekka_kernel import get_mekka_kernel
            kernel = get_mekka_kernel()
            tag_filter = request.rel_url.query.get("tags", "").split(",") if request.rel_url.query.get("tags") else None
            return web.Response(
                content_type="application/json",
                text=_json.dumps({
                    "ok": True,
                    "plugins": kernel.plugin_names,
                    "tool_count": len(kernel.get_tool_definitions()),
                    "tools": kernel.get_tool_definitions(tags=tag_filter),
                    "function_map": kernel.get_function_map(),
                }),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    async def _handle_kernel_invoke(self, request: web.Request) -> web.Response:
        """POST /api/kernel/invoke — invoke a kernel function by tool call name.

        Body: {"name": "market__detect_regime", "arguments": {"btc_trend": "BULLISH"}}
        Returns the function result as JSON.
        Requires auth (executes agent code).
        """
        import json as _json
        try:
            body = await request.json()
            name = body.get("name", "")
            arguments = body.get("arguments", {})
            if not name:
                return web.Response(
                    content_type="application/json",
                    status=400,
                    text=_json.dumps({"ok": False, "error": "Missing 'name' field"}),
                )
            from src.services.mekka_kernel import get_mekka_kernel
            kernel = get_mekka_kernel()
            result = await kernel.invoke_from_tool_call(
                name=name,
                arguments_json=_json.dumps(arguments),
            )
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, "result": result}),
            )
        except (KeyError, ValueError) as exc:
            return web.Response(
                content_type="application/json",
                status=400,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # CycleEventLog — GET /api/events              (Story 154)
    # ------------------------------------------------------------------

    async def _handle_events(self, request: web.Request) -> web.Response:
        """GET /api/events — return CycleEventLog summary (OpenHands EventLog pattern).

        Query params:
          ?symbol=BTC   — filter events by symbol
          ?type=CYCLE_START — filter events by event_type
          ?cycle_id=abc — replay a specific cycle
          ?last=N       — return last N events (default: summary)
        """
        import json as _json
        try:
            from src.services.cycle_event_log import get_cycle_event_log
            log = get_cycle_event_log()

            symbol = request.rel_url.query.get("symbol", "")
            event_type = request.rel_url.query.get("type", "")
            cycle_id = request.rel_url.query.get("cycle_id", "")
            last_n_str = request.rel_url.query.get("last", "")

            if cycle_id:
                data = log.cycle_summary(cycle_id)
            elif symbol:
                events = log.filter_by_symbol(symbol)
                data = {"symbol": symbol, "events": [e.to_dict() for e in events]}
            elif event_type:
                events = log.filter_by_type(event_type)
                data = {"event_type": event_type, "events": [e.to_dict() for e in events]}
            elif last_n_str:
                try:
                    n = int(last_n_str)
                    events = log.last_n(n)
                    data = {"last_n": n, "events": [e.to_dict() for e in events]}
                except ValueError:
                    data = log.summary()
            else:
                data = log.summary()

            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **data}, default=_json_safe_default),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # CycleEventLog SSE Stream — GET /api/events/stream    (Story 172)
    # ------------------------------------------------------------------

    async def _handle_events_stream(self, request: web.Request) -> web.StreamResponse:
        """GET /api/events/stream — Server-Sent Events stream of CycleEventLog.

        Streams new events as they appear in the CycleEventLog rolling window.
        Clients receive a heartbeat every 15 seconds to detect disconnection.

        Query params:
          ?symbol=BTC  — filter events by symbol (optional)
          ?last=20     — seed stream with the last N events before live polling
                         (default: 10; max: 100)

        SSE format (each event):
          data: {"event_type": "CYCLE_START", "symbol": "BTC", ...}\\n\\n

        Heartbeat (every 15s, no event):
          : heartbeat\\n\\n

        Pattern based on aiohttp SSE best practices — StreamResponse with
        text/event-stream content type, async polling loop, graceful disconnect.
        """
        import json as _json
        import asyncio as _asyncio

        symbol_filter = request.rel_url.query.get("symbol", "").strip().upper()
        try:
            seed_n = max(0, min(int(request.rel_url.query.get("last", "10")), 100))
        except (ValueError, TypeError):
            seed_n = 10

        resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await resp.prepare(request)

        async def _send(payload: str) -> bool:
            """Write one SSE data frame. Returns False if client disconnected."""
            try:
                await resp.write(f"data: {payload}\n\n".encode())
                return True
            except (ConnectionResetError, asyncio.CancelledError):
                return False

        async def _heartbeat() -> bool:
            try:
                await resp.write(b": heartbeat\n\n")
                return True
            except (ConnectionResetError, asyncio.CancelledError):
                return False

        try:
            from src.services.cycle_event_log import get_cycle_event_log
            log = get_cycle_event_log()

            # --- Seed: send last N events so the UI has initial state ---
            if seed_n > 0:
                seed_events = log.last_n(seed_n)
                if symbol_filter:
                    seed_events = [e for e in seed_events if getattr(e, "symbol", "").upper() == symbol_filter]
                for ev in seed_events:
                    d = ev.to_dict() if hasattr(ev, "to_dict") else {"raw": str(ev)}
                    if not await _send(_json.dumps(d)):
                        return resp

            # --- Live polling loop ---
            # Track the last seen event count to detect new events.
            # CycleEventLog is an append-only rolling deque — we compare
            # the current deque length to detect additions.
            last_seen: int = log.total_count() if hasattr(log, "total_count") else len(log.last_n(1000))
            heartbeat_counter = 0

            while True:
                await _asyncio.sleep(1.0)  # 1-second poll interval

                # Check if client disconnected (connection_lost sets closed)
                if resp.task is not None and resp.task.done():
                    break
                if request.transport is None or request.transport.is_closing():
                    break

                # Fetch new events since last check
                try:
                    current_count = log.total_count() if hasattr(log, "total_count") else len(log.last_n(1000))
                    if current_count > last_seen:
                        delta = current_count - last_seen
                        new_events = log.last_n(min(delta, 50))
                        if symbol_filter:
                            new_events = [e for e in new_events if getattr(e, "symbol", "").upper() == symbol_filter]
                        for ev in new_events:
                            d = ev.to_dict() if hasattr(ev, "to_dict") else {"raw": str(ev)}
                            if not await _send(_json.dumps(d)):
                                return resp
                        last_seen = current_count
                except Exception:  # noqa: BLE001
                    pass  # log unavailable — keep streaming, send heartbeat

                # Heartbeat every ~15 seconds (15 × 1s poll)
                heartbeat_counter += 1
                if heartbeat_counter >= 15:
                    heartbeat_counter = 0
                    if not await _heartbeat():
                        break

        except _asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                await resp.write_eof()
            except Exception:  # noqa: BLE001
                pass

        return resp

    # ------------------------------------------------------------------
    # AgentStepGuard — GET /api/step-guard          (Story 155)
    # ------------------------------------------------------------------

    async def _handle_step_guard(self, request: web.Request) -> web.Response:
        """GET /api/step-guard — return global AgentStepGuard statistics."""
        import json as _json
        try:
            from src.services.agent_step_guard import NickFuryStepGuard
            from src.config.settings import settings
            data = {
                **NickFuryStepGuard.global_summary(),
                "configured_max_iterations": settings.agent_max_step_iterations,
                "configured_stuck_threshold": settings.agent_stuck_threshold,
            }
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **data}),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # MicroagentRegistry — GET /api/microagents     (Story 156)
    # ------------------------------------------------------------------

    async def _handle_microagents(self, request: web.Request) -> web.Response:
        """GET /api/microagents — list loaded microagents and their metadata.

        Query params:
          ?regime=BEAR — return regime-specific prompt injection text
          ?trigger=SMALL_CAP&type=risk — filter by trigger + type
        """
        import json as _json
        try:
            from src.services.microagent_registry import get_microagent_registry
            registry = get_microagent_registry()

            regime = request.rel_url.query.get("regime", "")
            trigger = request.rel_url.query.get("trigger", "")
            agent_type = request.rel_url.query.get("type", "")

            if regime:
                prompt = registry.get_regime_prompt(regime)
                data = {
                    "regime": regime,
                    "prompt_injection": prompt,
                    "has_prompt": bool(prompt),
                }
            elif trigger:
                agents = registry.get_by_trigger(trigger, agent_type=agent_type)
                data = {
                    "trigger": trigger,
                    "type_filter": agent_type,
                    "agents": [a.to_dict() for a in agents],
                }
            else:
                data = registry.summary()

            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **data}),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # ContextWindowTracker — GET /api/context-window          (Story 159)
    # ------------------------------------------------------------------

    async def _handle_context_window(self, request: web.Request) -> web.Response:
        """GET /api/context-window — Context window usage por ciclo/estágio.

        Query params:
          ?cycle_id=BTC_123 — summary de um ciclo específico
          ?top=10           — N maiores consumidores (default 10)

        Baseado no SWE-agent ContextWindowManager:
          "The LLM Controller handles context window management and
           provides visibility into token usage per pipeline stage."
        """
        import json as _json
        try:
            from src.services.context_window_tracker import get_context_window_tracker
            tracker = get_context_window_tracker()

            cycle_id = request.rel_url.query.get("cycle_id", "")
            top_n_str = request.rel_url.query.get("top", "10")
            try:
                top_n = int(top_n_str)
            except (ValueError, TypeError):
                top_n = 10

            if cycle_id:
                data = tracker.cycle_summary(cycle_id)
            else:
                data = tracker.summary()
                data["top_consumers"] = tracker.get_top_consumers(n=top_n)

            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **data}),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # SignalValidator — GET /api/signal-validator              (Story 158)
    # ------------------------------------------------------------------

    async def _handle_signal_validator(self, request: web.Request) -> web.Response:
        """GET /api/signal-validator — configuração e thresholds do validador.

        Retorna os thresholds configurados no SignalValidator singleton.
        Útil para auditoria: "por que este signal foi rejeitado?".

        Baseado no linting do SWE-agent:
          "Edits are validated by a built-in linter, with syntactically
           invalid changes automatically rejected."
        """
        import json as _json
        try:
            from src.services.signal_validator import get_signal_validator
            validator = get_signal_validator()

            data = {
                "min_confidence_long": validator._min_conf_long,
                "min_confidence_short": validator._min_conf_short,
                "min_confidence_hold": validator._min_conf_hold,
                "min_risk_reward": validator._min_rr,
                "max_total_risk_pct": validator._max_total_risk,
                "require_reasoning": validator._require_reasoning,
                "min_reasoning_chars": validator._min_reasoning_chars,
                "description": (
                    "Pre-Batman signal linter (SWE-agent pattern). "
                    "Signals failing validation are rejected before Batman gates."
                ),
            }

            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **data}),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # MekkaRepoMap — GET /api/repo-map                         (Story 160)
    # ------------------------------------------------------------------

    async def _handle_repo_map(self, request: web.Request) -> web.Response:
        """GET /api/repo-map — compact symbol map of the Mekka codebase.

        Query params:
          ?dir=agents   — filtra por subdiretório (agents/services/models)
          ?symbol=Batman — busca arquivos que contêm um símbolo
          ?format=compact — retorna string compacta pronta para prompt

        Baseado em aider/repomap.py:
          "Aider builds a tree-sitter based repository map to give the LLM
           a compact overview of the codebase."
        """
        import json as _json
        try:
            from src.services.repo_map import get_repo_map
            rmap = get_repo_map()

            dir_filter = request.rel_url.query.get("dir", "")
            symbol = request.rel_url.query.get("symbol", "")
            fmt = request.rel_url.query.get("format", "summary")

            if symbol:
                files = rmap.find_symbol(symbol)
                data = {"symbol": symbol, "found_in": files}
            elif fmt == "compact":
                dirs = (dir_filter,) if dir_filter else None
                data = {
                    "compact": rmap.to_compact_string(dirs=dirs),
                    "prompt_section": rmap.to_prompt_section(dirs=dirs),
                }
            elif dir_filter == "agents":
                data = {"agent_map": rmap.get_agent_map()}
            elif dir_filter == "services":
                data = {"service_map": rmap.get_service_map()}
            else:
                data = rmap.summary()

            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **data}),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # SignalChangeLog — GET /api/signal-changelog               (Story 162)
    # ------------------------------------------------------------------

    async def _handle_signal_changelog(self, request: web.Request) -> web.Response:
        """GET /api/signal-changelog — histórico de diffs entre signals consecutivos.

        Query params:
          ?symbol=BTC  — records recentes de um símbolo específico
          ?n=10        — número de records (default 10)
          ?flips=1     — somente records com mudança de action

        Baseado em aider/commands.py auto-commit + editblock_coder.py:
          "Aider auto-commits each change with a descriptive commit message.
           SEARCH/REPLACE format makes it explicit what changed."
        """
        import json as _json
        try:
            from src.services.signal_changelog import get_signal_changelog
            log = get_signal_changelog()

            symbol = request.rel_url.query.get("symbol", "")
            n_str = request.rel_url.query.get("n", "10")
            flips_only = request.rel_url.query.get("flips", "") == "1"

            try:
                n = int(n_str)
            except (ValueError, TypeError):
                n = 10

            if symbol:
                if flips_only:
                    records = log.get_action_flips(symbol)[-n:]
                else:
                    records = log.get_recent(symbol, n=n)
                data = {
                    "symbol": symbol,
                    "records": [r.to_dict() for r in records],
                    "total_returned": len(records),
                }
            else:
                data = log.summary()

            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **data}, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # ObservabilityPlugin widget — GET /api/obs/{tool_name}   (Story 175)
    # ------------------------------------------------------------------

    async def _handle_obs_tool(self, request: web.Request) -> web.Response:
        """GET /api/obs/{tool_name} — invoke an ObservabilityPlugin function via kernel.

        Shortcut for the dashboard to call any ObservabilityPlugin @mekka_function
        without going through the generic POST /api/kernel/invoke endpoint.

        Path param:
          {tool_name}   — one of: cycle_events, signal_changes, context_window,
                          step_guard_stats, validator_thresholds, vision_metrics,
                          vision_last_signal

        Query params forwarded as JSON arguments to the function:
          ?symbol=BTC  — for symbol-scoped functions
          ?last_n=10   — number of records
          ?cycle_id=X  — for context_window

        Pattern: each function is called as kernel.invoke("obs", fn, **query_params)
        or kernel.invoke("vision", fn, **query_params) depending on tool_name.
        """
        import json as _json
        tool_name = request.match_info.get("tool_name", "")
        query = dict(request.rel_url.query)

        # Coerce numeric params
        for k in ("last_n", "seed", "limit"):
            if k in query:
                try:
                    query[k] = int(query[k])
                except (ValueError, TypeError):
                    del query[k]

        # Map tool_name → (plugin_name, function_name)
        _TOOL_MAP = {
            "cycle_events":          ("obs",    "get_cycle_events"),
            "signal_changes":        ("obs",    "get_signal_changes"),
            "context_window":        ("obs",    "get_context_window"),
            "step_guard_stats":      ("obs",    "get_step_guard_stats"),
            "validator_thresholds":  ("obs",    "get_validator_thresholds"),
            "vision_metrics":        ("vision", "get_vision_metrics"),
            "vision_last_signal":    ("vision", "get_last_signal"),
            "vision_generate_signal":("vision", "generate_signal"),
        }

        if tool_name not in _TOOL_MAP:
            return web.Response(
                content_type="application/json",
                status=404,
                text=_json.dumps({
                    "ok": False,
                    "error": f"Unknown obs tool: '{tool_name}'",
                    "available": list(_TOOL_MAP.keys()),
                }),
            )

        plugin_name, fn_name = _TOOL_MAP[tool_name]
        try:
            from src.services.mekka_kernel import get_mekka_kernel
            kernel = get_mekka_kernel()
            result = await kernel.invoke(plugin_name, fn_name, **query)
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, "tool": tool_name, "result": result}, default=str),
            )
        except (KeyError, TypeError) as exc:
            return web.Response(
                content_type="application/json",
                status=400,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # ContextWindowTracker Live — GET /api/context-window/live (Story 177)
    # ------------------------------------------------------------------

    async def _handle_context_window_live(self, _: web.Request) -> web.Response:
        """GET /api/context-window/live — summaries de todos os ciclos ativos.

        Retorna usage em % por estágio para monitoramento em produção.
        Cada entrada mostra: cycle_id, symbol, model, stages, total_tokens,
        usage_pct, is_near_limit (>= 80%).

        Ordenado por usage_pct decrescente — ciclos mais críticos primeiro.
        """
        import json as _json
        try:
            from src.services.context_window_tracker import get_context_window_tracker
            cwt = get_context_window_tracker()

            # Tentar get_all_summaries() se disponível, senão usar summary()
            if hasattr(cwt, "get_all_summaries"):
                all_summaries = cwt.get_all_summaries()
            elif hasattr(cwt, "summary"):
                raw = cwt.summary()
                # Normalise: if summary returns a flat dict, wrap it
                if isinstance(raw, dict) and "cycles" in raw:
                    all_summaries = raw["cycles"]
                else:
                    all_summaries = [raw] if raw else []
            else:
                all_summaries = []

            # Enrich each summary with is_near_limit flag
            enriched = []
            for s in all_summaries:
                usage_pct = s.get("usage_pct", s.get("total_tokens_pct", 0.0))
                enriched.append({
                    **s,
                    "usage_pct": usage_pct,
                    "is_near_limit": usage_pct >= 0.80,
                })

            # Sort by usage_pct descending
            enriched.sort(key=lambda x: x.get("usage_pct", 0.0), reverse=True)

            return web.Response(
                content_type="application/json",
                text=_json.dumps({
                    "ok": True,
                    "count": len(enriched),
                    "cycles": enriched,
                    "global_summary": cwt.summary() if hasattr(cwt, "summary") else {},
                }, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            import json as _json
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # CycleSOP — GET /api/cycle-sop                          (Story 185)
    # ------------------------------------------------------------------

    async def _handle_cycle_sop(self, _: web.Request) -> web.Response:
        """GET /api/cycle-sop — retorna a especificação declarativa do pipeline.

        MetaGPT SOP pattern: serializa o Standard Operating Procedure do ciclo
        de trading Mekka com todos os estágios, agentes, tipos e flags de skip.
        Útil para dashboards, documentação automática e testes de conformidade.
        """
        import json as _json
        try:
            from src.services.cycle_sop import get_cycle_sop
            sop = get_cycle_sop()
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **sop.to_dict()}, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # RoleWorkingMemory — GET /api/working-memory             (Story 183)
    # ------------------------------------------------------------------

    async def _handle_working_memory(self, request: web.Request) -> web.Response:
        """GET /api/working-memory[?symbol=BTC] — retorna janela deslizante de ciclos.

        MetaGPT RoleContext.rc.memory pattern: expõe a working memory do Vision
        com os últimos ciclos por símbolo para diagnóstico e dashboards.
        """
        import json as _json
        try:
            from src.services.role_working_memory import get_role_working_memory
            mem = get_role_working_memory()
            symbol = request.rel_url.query.get("symbol", "")
            if symbol:
                records = mem.get_recent(symbol, limit=20)
                data = {
                    "ok": True,
                    "symbol": symbol.upper(),
                    "records": [r.to_dict() for r in records],
                    "count": len(records),
                }
            else:
                data = {"ok": True, **mem.summary()}
            return web.Response(
                content_type="application/json",
                text=_json.dumps(data, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ------------------------------------------------------------------
    # IncrementalCycleGuard — GET /api/incremental-guard      (Story 187)
    # ------------------------------------------------------------------

    async def _handle_incremental_guard(self, _: web.Request) -> web.Response:
        """GET /api/incremental-guard — estatísticas do IncrementalCycleSkip.

        MetaGPT Incremental Development pattern: expõe checkpoints por símbolo,
        skip_rate e thresholds configurados.
        """
        import json as _json
        try:
            from src.services.cycle_incremental_guard import get_cycle_incremental_guard
            guard = get_cycle_incremental_guard()
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **guard.summary()}, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                content_type="application/json",
                status=500,
                text=_json.dumps({"ok": False, "error": str(exc)}),
            )

    # ==================================================================
    # Milestone 36 — Backtesting Dashboard (Stories 224-228)
    # ==================================================================

    # In-memory cache: {symbol: BacktestSummary}
    _backtest_cache: dict = {}

    async def _handle_backtest_run(self, request: web.Request) -> web.Response:
        """
        POST /api/backtest/run                                   Story 224

        Body (JSON):
            symbol        : str  — ex: "BTC" (default "BTC")
            days          : int  — janela em dias (default 30, max 365)
            initial_equity: float — capital inicial USD (default 10000)
            seed          : int | null — semente para reprodutibilidade

        Response:
            BacktestSummary serializado + BenchmarkResult + Telegram status
        """
        import json as _json
        try:
            body = await request.json()
        except Exception:
            body = {}

        symbol         = str(body.get("symbol", "BTC")).upper()
        days           = min(int(body.get("days", 30)), 365)
        initial_equity = float(body.get("initial_equity", 10_000.0))
        seed           = body.get("seed", 42)

        try:
            from src.services.backtest_runner import BacktestRunner
            from src.services.backtest_benchmark import BacktestBenchmark
            from src.services.backtest_telegram_report import BacktestTelegramReport

            runner  = BacktestRunner(initial_equity=initial_equity, seed=seed)
            summary = await asyncio.wait_for(
                runner.run(symbol=symbol, days=days), timeout=30.0
            )

            # Benchmark buy-hold
            bm_result = None
            try:
                bm = BacktestBenchmark()
                bm_result = await bm.compute(
                    symbol=symbol,
                    start_date=summary.start_date,
                    end_date=summary.end_date,
                    initial_equity=initial_equity,
                )
            except Exception as exc_bm:
                logger.warning("backtest_run: benchmark error — %s", exc_bm)

            # Cache do resultado
            self.__class__._backtest_cache[symbol] = {
                "summary": summary,
                "benchmark": bm_result,
            }

            # Telegram report (fire-and-forget)
            asyncio.create_task(
                BacktestTelegramReport().send(summary, benchmark=bm_result)
            )

            payload = _backtest_summary_to_dict(summary)
            if bm_result:
                payload["benchmark"] = bm_result.to_dict()

            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **payload}, default=str),
            )
        except asyncio.TimeoutError:
            return web.json_response({"ok": False, "error": "backtest timeout (>30s)"}, status=504)
        except Exception as exc:
            logger.warning("_handle_backtest_run error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    async def _handle_backtest_result(self, request: web.Request) -> web.Response:
        """
        GET /api/backtest/result?symbol=BTC                      Story 224

        Retorna o último resultado em cache para o símbolo.
        """
        import json as _json
        symbol = request.query.get("symbol", "BTC").upper()
        cached = self.__class__._backtest_cache.get(symbol)
        if not cached:
            return web.json_response(
                {"ok": False, "error": f"Nenhum resultado em cache para {symbol}. Execute POST /api/backtest/run primeiro."},
                status=404,
            )
        payload = _backtest_summary_to_dict(cached["summary"])
        if cached.get("benchmark"):
            payload["benchmark"] = cached["benchmark"].to_dict()
        return web.Response(
            content_type="application/json",
            text=_json.dumps({"ok": True, **payload}, default=str),
        )

    async def _handle_backtest_history(self, request: web.Request) -> web.Response:
        """
        GET /api/backtest/history?symbol=BTC                     Story 228

        Retorna histórico de runs do BacktestScheduler.
        """
        import json as _json
        symbol = request.query.get("symbol", "BTC").upper()
        try:
            from src.services.backtest_scheduler import BacktestScheduler
            history = BacktestScheduler.get_history(symbol)
            items = [_backtest_summary_to_dict(s) for s in history]
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, "symbol": symbol, "history": items}, default=str),
            )
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    # ==================================================================
    # Milestone 37 — Live Performance Tracking (Stories 229-233)
    # ==================================================================

    async def _handle_perf_rolling(self, request: web.Request) -> web.Response:
        """
        GET /api/performance/rolling?days=30&symbol=BTC          Story 232

        Retorna métricas rolling: Sharpe, win_rate, expectancy, total_pnl,
        comparadas com o backtest mais recente em cache.
        """
        import json as _json
        days   = _safe_limit(request.query.get("days"), default=30, max_value=365)
        symbol = request.query.get("symbol", "BTC").upper()
        try:
            from src.services.rolling_metrics_service import RollingMetricsService
            svc = RollingMetricsService()
            result = await svc.compute(symbol=symbol, window_days=days)
            # Comparar com backtest em cache
            cached = self.__class__._backtest_cache.get(symbol)
            if cached:
                backtest_summary = cached["summary"]
                result["backtest_sharpe"]   = backtest_summary.metrics.sharpe_ratio
                result["backtest_win_rate"] = backtest_summary.metrics.win_rate
                result["backtest_days"]     = days
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **result}, default=str),
            )
        except Exception as exc:
            logger.warning("_handle_perf_rolling error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    async def _handle_perf_divergence(self, request: web.Request) -> web.Response:
        """
        GET /api/performance/divergence?symbol=BTC               Story 231

        Detecta divergências entre performance real e backtest.
        """
        import json as _json
        symbol = request.query.get("symbol", "BTC").upper()
        try:
            from src.services.divergence_alerter import DivergenceAlerter
            alerter = DivergenceAlerter()
            cached  = self.__class__._backtest_cache.get(symbol)
            backtest_summary = cached["summary"] if cached else None
            result = await alerter.check(symbol=symbol, backtest=backtest_summary)
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, **result}, default=str),
            )
        except Exception as exc:
            logger.warning("_handle_perf_divergence error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    # ==================================================================
    # Milestone 38 — Risk Dashboard Avançado (Stories 234-238)
    # ==================================================================

    async def _handle_batman_timeline(self, request: web.Request) -> web.Response:
        """
        GET /api/risk/batman-timeline?limit=100                  Story 235

        Retorna timeline de verdicts do Batman (APPROVED/REDUCED/REJECTED)
        com timestamp, símbolo, verdict, motivo e tamanho reduzido.
        """
        import json as _json
        limit = _safe_limit(request.query.get("limit"), default=100, max_value=500)
        sym_filter = (request.query.get("symbol") or "").strip().upper()
        try:
            rows = await MekkaRepository.list_recent_audit(limit=limit * 3)
            batman_rows = [
                r for r in rows
                if (r.agent or "").lower() == "batman"
                and r.payload
            ][-limit:]

            # BUG-006 fix: filtrar por símbolo se informado
            if sym_filter and sym_filter != "ALL":
                batman_rows = [
                    r for r in batman_rows
                    if (r.symbol or "").upper() == sym_filter
                ]

            timeline = []
            for r in batman_rows:
                p = r.payload or {}
                timeline.append({
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "symbol":    r.symbol or p.get("symbol"),
                    "verdict":   p.get("verdict") or r.event,
                    "reason":    p.get("reason") or p.get("message", ""),
                    "original_size_pct": p.get("original_size_pct"),
                    "approved_size_pct": p.get("approved_size_pct"),
                    "drawdown_pct":      p.get("daily_pnl_pct"),
                })

            return web.Response(
                content_type="application/json",
                text=_json.dumps({
                    "ok": True,
                    "symbol": sym_filter or "ALL",
                    "count": len(timeline),
                    "timeline": timeline,
                }, default=str),
            )
        except Exception as exc:
            logger.warning("_handle_batman_timeline error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    async def _handle_regime_heatmap(self, request: web.Request) -> web.Response:
        """
        GET /api/risk/regime-heatmap?days=30                     Story 236

        Retorna mapa de calor: quantos ciclos por regime × símbolo × hora do dia.
        """
        import json as _json
        from collections import defaultdict
        days = _safe_limit(request.query.get("days"), default=30, max_value=90)
        try:
            rows = await MekkaRepository.list_recent_audit(limit=5000)
            # Filtrar por janela de tempo. Timestamps do DB podem ser naive;
            # normaliza para UTC-aware antes de comparar com o cutoff aware
            # (senão: "can't compare offset-naive and offset-aware datetimes").
            from datetime import timedelta

            def _aware(dt: Any) -> Any:
                if dt is not None and getattr(dt, "tzinfo", None) is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            rows = [r for r in rows if r.timestamp and _aware(r.timestamp) >= cutoff]

            # Contagem por regime e hora UTC
            regime_hour: dict = defaultdict(lambda: defaultdict(int))
            regime_counts: dict = defaultdict(int)

            for r in rows:
                p = r.payload or {}
                regime = p.get("regime") or p.get("market_regime")
                if not regime:
                    continue
                hour = r.timestamp.hour if r.timestamp else 0
                regime_hour[regime][hour] += 1
                regime_counts[regime] += 1

            heatmap = {
                regime: {
                    "total": regime_counts[regime],
                    "by_hour": dict(sorted(hour_map.items())),
                }
                for regime, hour_map in regime_hour.items()
            }

            return web.Response(
                content_type="application/json",
                text=_json.dumps({
                    "ok": True,
                    "days": days,
                    "regimes": list(heatmap.keys()),
                    "heatmap": heatmap,
                }, default=str),
            )
        except Exception as exc:
            logger.warning("_handle_regime_heatmap error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    async def _handle_concentration(self, request: web.Request) -> web.Response:
        """
        GET /api/risk/concentration                              Story 238

        Retorna concentração de risco por símbolo: % do capital alocado,
        número de trades abertos e drawdown por símbolo.
        """
        import json as _json
        from collections import defaultdict
        try:
            # BUG-007 fix: usar list_recent_trades para funcionar em mainnet também
            all_trades = await MekkaRepository.list_recent_trades(limit=500)
            trades = [t for t in all_trades if t.status in ("FILLED", "PAPER")]

            notional_by_sym: dict = defaultdict(float)
            count_by_sym: dict    = defaultdict(int)
            pnl_by_sym: dict      = defaultdict(float)

            total_notional = 0.0
            for t in trades:
                sym = (t.symbol or "UNKNOWN").upper()
                qty   = float(t.quantity or 0)
                price = float(t.avg_price or 0)
                pnl   = float(t.pnl_usd or 0) if hasattr(t, "pnl_usd") else 0.0
                notional = qty * price
                notional_by_sym[sym] += notional
                count_by_sym[sym]    += 1
                pnl_by_sym[sym]      += pnl
                total_notional       += notional

            symbols_data = []
            for sym, notional in sorted(notional_by_sym.items(), key=lambda x: -x[1]):
                pct = (notional / total_notional * 100) if total_notional > 0 else 0.0
                symbols_data.append({
                    "symbol":        sym,
                    "notional_usd":  round(notional, 2),
                    "concentration_pct": round(pct, 2),
                    "trade_count":   count_by_sym[sym],
                    "pnl_usd":       round(pnl_by_sym[sym], 2),
                })

            return web.Response(
                content_type="application/json",
                text=_json.dumps({
                    "ok": True,
                    "total_notional_usd": round(total_notional, 2),
                    "symbol_count": len(symbols_data),
                    "concentration": symbols_data,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }, default=str),
            )
        except Exception as exc:
            logger.warning("_handle_concentration error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    # ==================================================================
    # Milestone 39 — Multiagent Debate (Stories 239-243)
    # ==================================================================

    async def _handle_debate_run(self, request: web.Request) -> web.Response:
        """
        POST /api/debate/run                                     Story 239

        Body (JSON):
            symbol  : str  — ex: "BTC" (default "BTC")
            rounds  : int  — número de rodadas (default 2, max 5)
            agents  : list[str] | null — lista de agentes (default: todos L1)

        Response:
            DebateVerdict serializado + tabela de votos
        """
        import json as _json
        try:
            body = await request.json()
        except Exception:
            body = {}

        symbol  = str(body.get("symbol", "BTC")).upper()
        rounds  = min(int(body.get("rounds", 2)), 5)
        agents  = body.get("agents") or None  # None = usa DEFAULT_AGENTS

        try:
            from src.services.debate_moderator import DebateModerator
            from src.services.debate_verdict_logger import DebateVerdictLogger
            from src.services.consensus_weighter import ConsensusWeighter

            moderator = DebateModerator(max_rounds=rounds)
            verdict   = await asyncio.wait_for(
                moderator.run(context={}, agents=agents, symbol=symbol),
                timeout=15.0,
            )

            # Persistir no audit_log
            asyncio.create_task(DebateVerdictLogger().log(verdict, symbol=symbol))

            weighter = ConsensusWeighter()
            return web.Response(
                content_type="application/json",
                text=_json.dumps({
                    "ok": True,
                    "symbol": symbol,
                    **verdict.to_dict(),
                    "vote_table": weighter.summary_table(verdict.votes),
                }, default=str),
            )
        except asyncio.TimeoutError:
            return web.json_response({"ok": False, "error": "debate timeout"}, status=504)
        except Exception as exc:
            logger.warning("_handle_debate_run error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    async def _handle_debate_history(self, request: web.Request) -> web.Response:
        """
        GET /api/debate/history?symbol=BTC&limit=20             Story 242

        Retorna histórico de DebateVerdicts do audit_log.
        """
        import json as _json
        symbol = request.query.get("symbol") or None
        limit  = _safe_limit(request.query.get("limit"), default=20, max_value=100)
        try:
            from src.services.debate_verdict_logger import DebateVerdictLogger
            items = await DebateVerdictLogger().fetch_recent(symbol=symbol, limit=limit)
            return web.Response(
                content_type="application/json",
                text=_json.dumps({"ok": True, "count": len(items), "history": items}, default=str),
            )
        except Exception as exc:
            logger.warning("_handle_debate_history error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    # ------------------------------------------------------------------
    # Today Summary Widget — GET /api/today-summary
    # ------------------------------------------------------------------

    async def _handle_today_summary(self, _: web.Request) -> web.Response:
        """GET /api/today-summary — visão simplificada para leigos.

        Retorna posições abertas (paper ou live), trades recentes e P&L do dia.
        Robusto contra: sem mark prices, sem trades hoje, pnl_usd=None.
        """
        from src.dashboard.positions_provider import fetch_positions

        today_utc = datetime.now(timezone.utc).date().isoformat()
        mark_prices: dict[str, float] = dict(self._mark_prices) if self._mark_prices else {}
        has_mark_prices = bool(mark_prices)

        try:
            pos_data, trades_all, daily_pnl = await asyncio.gather(
                fetch_positions(mark_prices=mark_prices),
                MekkaRepository.list_recent_trades(limit=50),
                MekkaRepository.get_today_pnl_usd(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("_handle_today_summary error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

        # ── Posições abertas ──────────────────────────────────────────────
        open_positions = []
        open_pnl = 0.0
        open_pnl_known = False  # True quando temos mark prices reais ou uPnL nativo da exchange
        for p in (pos_data.get("items") or []):
            entry = float(p.get("entry_price") or 0.0)
            mark  = float(p.get("mark_price")  or 0.0)
            raw_pnl = p.get("pnl_usd")
            pnl   = float(raw_pnl or 0.0)
            is_paper_pos = bool(p.get("is_paper", True))
            # Para Hyperliquid/paper usamos mark prices do servidor.
            # Para Binance/Bybit live aceitamos o uPnL nativo vindo da própria exchange.
            has_server_mark = has_mark_prices and mark > 0 and abs(mark - entry) > 0.001
            has_native_live_pnl = (not is_paper_pos) and (raw_pnl is not None)
            has_upnl = has_server_mark or has_native_live_pnl
            if has_upnl:
                open_pnl += pnl
                open_pnl_known = True
            emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⏳")
            open_positions.append({
                "symbol":      p.get("symbol", ""),
                "side":        p.get("side", ""),
                "size":        round(float(p.get("size") or 0), 6),
                "entry_price": round(entry, 4),
                "mark_price":  round(mark, 4),
                "pnl_usd":     round(pnl, 2) if has_upnl else None,
                "has_upnl":    has_upnl,
                "is_paper":    is_paper_pos,
                "emoji":       emoji,
            })

        # ── Trades do dia atual ───────────────────────────────────────────
        def _trade_date(t: Any) -> str:
            ts = t.timestamp
            try:
                if hasattr(ts, "date"):
                    d = ts.date()
                    return d.isoformat()
            except Exception:
                pass
            return str(ts)[:10]

        def _fmt_trade(t: Any) -> dict:
            pnl = t.pnl_usd  # pode ser None
            pnl_val = float(pnl) if pnl is not None else None
            emoji = "✅" if (pnl_val is not None and pnl_val > 0) else (
                    "🔴" if (pnl_val is not None and pnl_val < 0) else "📋")
            return {
                "id":          t.id,
                "timestamp":   str(t.timestamp)[:16],
                "date":        str(t.timestamp)[:10],
                "symbol":      t.symbol,
                "side":        (t.side or "—").upper(),
                "status":      t.status,
                "pnl_usd":     round(pnl_val, 2) if pnl_val is not None else None,
                "notional_usd": round(float(t.notional_usd or 0.0), 2),
                "is_paper":    bool(t.is_paper),
                "emoji":       emoji,
            }

        today_trades  = [_fmt_trade(t) for t in trades_all if _trade_date(t) == today_utc]
        recent_trades = [_fmt_trade(t) for t in trades_all[:20]]  # últimos 20 independente de data

        # ── Sumário ───────────────────────────────────────────────────────
        total_pnl = round(float(daily_pnl or 0.0), 2)
        net_pnl   = round(total_pnl + (open_pnl if open_pnl_known else 0.0), 2)
        day_emoji = "🟢" if net_pnl > 0 else ("🔴" if net_pnl < 0 else "➖")

        show_quote_warning = (not open_pnl_known) and len(open_positions) > 0
        active_exchange_label = str(settings.active_exchange or "exchange").upper()

        return web.json_response({
            "ok":                True,
            "date_utc":          today_utc,
            # Posições abertas
            "open_positions":    open_positions,
            "open_count":        len(open_positions),
            "open_pnl_usd":      round(open_pnl, 2) if open_pnl_known else None,
            "has_prices":        has_mark_prices or open_pnl_known,
            "show_quote_warning": show_quote_warning,
            "quote_warning_message": (
                f"Sem cotação de mercado ao vivo na {active_exchange_label} agora. "
                "P&L das posições indisponível."
            ),
            # Trades
            "today_trades":      today_trades,
            "recent_trades":     recent_trades,
            "trades_count_today": len(today_trades),
            # P&L do dia
            "daily_pnl_usd":     total_pnl,
            "net_pnl_usd":       net_pnl if open_pnl_known else total_pnl,
            "day_emoji":         day_emoji,
            "is_paper":          settings.paper_trading,
        })

    # ------------------------------------------------------------------
    # Widget Prefs — GET /api/prefs  POST /api/prefs          (Story 042)
    # ------------------------------------------------------------------

    _PREFS_FILE = "data/widget_prefs.json"

    async def _handle_prefs_get(self, request: web.Request) -> web.Response:
        """GET /api/prefs — return server-persisted widget preferences.

        Returns ``{"prefs": {section_id: bool, ...}}`` or ``{"prefs": {}}``
        if no prefs have been saved yet. Auth not required (display-only).
        """
        import json as _json
        from pathlib import Path as _Path

        prefs_path = _Path(self._PREFS_FILE)
        try:
            if prefs_path.exists():
                raw = await asyncio.to_thread(prefs_path.read_text, "utf-8")
                data = _json.loads(raw)
                prefs = data if isinstance(data, dict) else {}
            else:
                prefs = {}
        except Exception as exc:
            logger.warning("prefs_get: could not read %s: %s", prefs_path, exc)
            prefs = {}

        return web.json_response({"prefs": prefs})

    async def _handle_prefs_set(self, request: web.Request) -> web.Response:
        """POST /api/prefs — persist widget preferences server-side.

        Body: ``{"prefs": {section_id: bool, ...}}``
        Auth required (same gate as mutating endpoints).
        """
        import json as _json
        from pathlib import Path as _Path

        body = await self._safe_json_body(request) or {}
        prefs = body.get("prefs")
        if not isinstance(prefs, dict):
            return web.json_response({"error": "Campo 'prefs' deve ser um objeto."}, status=400)

        # Sanitise: only boolean values, keys that look like section IDs
        clean: dict = {
            str(k)[:64]: bool(v)
            for k, v in prefs.items()
            if isinstance(k, str) and str(k).startswith("sec-")
        }

        prefs_path = _Path(self._PREFS_FILE)
        try:
            prefs_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                prefs_path.write_text, _json.dumps(clean, indent=2), "utf-8"
            )
        except Exception as exc:
            logger.warning("prefs_set: could not write %s: %s", prefs_path, exc)
            return web.json_response({"error": f"Falha ao salvar prefs: {exc}"}, status=500)

        return web.json_response({"saved": True, "count": len(clean)})

    # ------------------------------------------------------------------
    # TradeNow — POST /api/trade/analyze  POST /api/trade/execute
    # (Story 040 — Dashboard v2)
    # ------------------------------------------------------------------

    async def _handle_trade_analyze(self, request: web.Request) -> web.Response:
        """POST /api/trade/analyze — run agent analysis for the best trade
        opportunity right now.

        Guardrails are evaluated server-side before any agent is called.
        Returns a typed ``TradeRecommendation`` plus a guardrail checklist.
        Auth required (same gate as all mutating endpoints).

        Response shape
        --------------
        {
          "recommendation_id": str,   # opaque ID, required for /execute
          "guardrails": {
            "passed": bool,
            "checks": [{"name": str, "ok": bool, "detail": str}, ...]
          },
          "recommendation": {         # null when guardrails.passed == false
            "symbol": str,
            "direction": "LONG"|"SHORT",
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float,
            "size_pct": float,        # fraction of equity e.g. 0.02
            "confidence": float,      # 0..1
            "risk_usd": float,
            "justification": str,
            "source": "agents"|"mock",
            "agents_consensus": bool,
          },
          "is_paper": bool,
          "generated_at": str,        # ISO-8601 UTC
        }
        """
        # ── Global guard — always return JSON, never let aiohttp emit 500 text ──
        import uuid  # noqa: PLC0415 — local import so uuid is in scope for all code below
        try:
            from src.agents.batman import is_kill_switch_active
            from src.config.settings import settings as _s
            from src.config.runtime_mode import get_params
        except Exception as _import_exc:
            logger.error("trade_analyze: import failed: %s", _import_exc, exc_info=True)
            return web.json_response({
                "recommendation_id": str(uuid.uuid4()),
                "guardrails": {"passed": False, "checks": [
                    {"name": "server_ready", "ok": False,
                     "detail": f"Erro interno de inicialização: {_import_exc}"}
                ]},
                "recommendation": None,
                "is_paper": True,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }, status=200)

        generated_at = datetime.now(timezone.utc).isoformat()

        # ── Guardrail evaluation ────────────────────────────────────────
        checks: list[dict] = []

        # G1: kill switch
        ks_active = is_kill_switch_active()
        checks.append({
            "name": "kill_switch_clear",
            "ok": not ks_active,
            "detail": "Kill switch ativo — libere antes de operar" if ks_active else "Clear",
        })

        # G2: equity available
        equity_usd = await self._manual_equity_usd()
        wallet_ok = equity_usd > 0
        checks.append({
            "name": "wallet_ok",
            "ok": wallet_ok,
            "detail": f"Equity ${equity_usd:,.2f}" if wallet_ok else "Equity zero ou indisponível",
        })

        # G3: risk/drawdown headroom
        params = get_params()

        # ── Runtime overrides: Super Agressivo + Altcoins ───────────────────
        _runtime_cfg = self._load_runtime_settings()
        _super_aggressive = bool(_runtime_cfg.get("super_aggressive", False))
        _altcoins_enabled  = bool(_runtime_cfg.get("altcoins_enabled", False))
        # Confidence threshold: 55% when super_aggressive, else 70%
        _confidence_threshold = 0.55 if _super_aggressive else 0.70
        # Extra assets when altcoins enabled
        _ALTCOINS = ["ETH", "SOL", "AVAX", "BNB", "LINK"]

        max_dd = float(params.get("max_daily_drawdown_pct", _s.max_daily_drawdown_pct))
        try:
            pnl_data = await MekkaRepository.get_pnl_summary(window_days=1)
            dd_pct = float(pnl_data["window"].get("max_drawdown_pct") or 0.0)
        except Exception:
            dd_pct = 0.0
        risk_ok = dd_pct < max_dd
        checks.append({
            "name": "risk_ok",
            "ok": risk_ok,
            "detail": (
                f"Drawdown {dd_pct:.2%} < limite {max_dd:.2%}"
                if risk_ok else
                f"Drawdown {dd_pct:.2%} ≥ limite {max_dd:.2%} — não operar"
            ),
        })

        # G4: data freshness (payload cache age)
        cache_age_s = None
        if self._payload_cache:
            cached = self._payload_cache.get("overview")
            if cached and isinstance(cached, dict):
                ts_str = cached.get("as_of") or cached.get("generated_at", "")
                try:
                    from dateutil.parser import parse as _parse
                    delta = datetime.now(timezone.utc) - _parse(ts_str)
                    cache_age_s = delta.total_seconds()
                except Exception:
                    cache_age_s = None
        data_fresh = cache_age_s is None or cache_age_s < 300  # 5 min
        checks.append({
            "name": "data_fresh",
            "ok": data_fresh,
            "detail": (
                f"Cache {int(cache_age_s or 0)}s atrás" if not data_fresh
                else "Dados recentes"
            ),
        })

        all_passed = all(c["ok"] for c in checks)
        rec_id = str(uuid.uuid4())

        # ── Log TRADE_NOW_REQUESTED ─────────────────────────────────────
        try:
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_REQUESTED",
                severity="INFO",
                message=f"TradeNow analysis requested — guardrails {'passed' if all_passed else 'blocked'}",
                payload={"recommendation_id": rec_id, "guardrails": checks},
            )
        except Exception as exc:
            logger.warning("trade_now audit log failed: %s", exc)

        if not all_passed:
            return web.json_response({
                "recommendation_id": rec_id,
                "guardrails": {"passed": False, "checks": checks},
                "recommendation": None,
                "is_paper": _s.paper_trading,
                "generated_at": generated_at,
            }, status=200)

        # ── Build recommendation ─────────────────────────────────────────
        # Try to pull the latest Vision signal from DB as a real recommendation.
        # Fall back to a mock (stub) when no signal is available.
        recommendation = None
        source = "mock"
        try:
            from src.persistence.models import SignalRecord
            from src.persistence.db import get_session
            from sqlalchemy import desc, select
            async with get_session() as _sess:
                row = (
                    await _sess.execute(
                        select(SignalRecord)
                        .where(SignalRecord.is_actionable.is_(True))
                        .order_by(desc(SignalRecord.timestamp))
                        .limit(1)
                    )
                ).scalars().first()
            if row:
                entry = float(row.entry_price or 0)
                sl = float(row.stop_loss or 0)
                tp = float(row.take_profit or 0)
                size_pct = float(row.size_pct or params.get("max_position_size_pct", 0.02))
                leverage_val = int(row.leverage or params.get("max_leverage", 1) or 1)
                # Super Agressivo: boost size and leverage
                if _super_aggressive:
                    size_pct = max(size_pct, 0.05)   # mínimo 5% do capital
                    leverage_val = max(leverage_val, 10)  # mínimo 10x
                conf = float(row.confidence or 0.5)
                risk_usd = round(equity_usd * size_pct * abs(entry - sl) / entry, 2) if entry else 0.0
                recommendation = {
                    "symbol": row.symbol,
                    "direction": row.action.upper(),
                    "entry_price": entry,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "size_pct": round(size_pct, 4),
                    "leverage": leverage_val,
                    "confidence": round(conf, 3),
                    "risk_usd": risk_usd,
                    "justification": (row.reasoning or "Vision analysis")[:400],
                    "source": "agents",
                    "agents_consensus": conf >= _confidence_threshold,
                }
                source = "agents"
        except Exception as exc:
            logger.warning("trade_analyze: could not fetch latest signal: %s", exc)

        if recommendation is None:
            # Mock stub — clear TODO marker for operator awareness
            _base_assets = list(params.get("trading_assets", ["BTC"]))
            _all_assets = _base_assets + [a for a in _ALTCOINS if a not in _base_assets] if _altcoins_enabled else _base_assets
            top_asset = _all_assets[0]
            source = "mock"
            _mock_size = 0.05 if _super_aggressive else float(params.get("max_position_size_pct", 0.02))
            recommendation = {
                "symbol": top_asset,
                "direction": "LONG",
                "entry_price": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "size_pct": round(_mock_size, 4),
                "confidence": 0.0,
                "risk_usd": 0.0,
                "justification": (
                    "⚠️ MOCK — Nenhum sinal recente encontrado. "
                    "Execute um ciclo de análise dos agentes antes de operar."
                ),
                "source": "mock",
                "agents_consensus": False,
            }

        # Add consensus guardrail check
        consensus_ok = recommendation.get("agents_consensus", False)
        _thresh_label = f"{_confidence_threshold:.0%}"
        _mode_tag = " (Super Agressivo)" if _super_aggressive else ""
        checks.append({
            "name": "agents_consensus",
            "ok": consensus_ok,
            "detail": (
                f"Confiança {recommendation['confidence']:.0%} ≥ {_thresh_label}{_mode_tag}"
                if consensus_ok else
                f"Confiança {recommendation['confidence']:.0%} < {_thresh_label}{_mode_tag} — consenso insuficiente"
            ),
        })
        all_passed = all(c["ok"] for c in checks)

        # ── Log TRADE_NOW_RECOMMENDED ───────────────────────────────────
        try:
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_RECOMMENDED",
                severity="INFO",
                message=(
                    f"TradeNow recommendation: {recommendation['direction']} "
                    f"{recommendation['symbol']} conf={recommendation['confidence']:.2f} "
                    f"source={source}"
                ),
                payload={"recommendation_id": rec_id, "recommendation": recommendation},
            )
        except Exception as exc:
            logger.warning("trade_now_recommended audit log failed: %s", exc)

        # Story 041 — cache recommendation so _handle_trade_execute can look it up.
        # Store equity_usd alongside so IronMan gets accurate sizing context.
        if recommendation is not None:
            cached_entry = {**recommendation, "_equity_usd": equity_usd}
            self._rec_cache[rec_id] = cached_entry
            # FIFO eviction — keep at most self._rec_cache_max entries
            if len(self._rec_cache) > self._rec_cache_max:
                oldest_key = next(iter(self._rec_cache))
                del self._rec_cache[oldest_key]

        from src.config.settings import settings as _s2
        return web.json_response({
            "recommendation_id": rec_id,
            "guardrails": {"passed": all_passed, "checks": checks},
            "recommendation": recommendation,
            "is_paper": _s2.paper_trading,
            "generated_at": generated_at,
            "mode": {
                "super_aggressive": _super_aggressive,
                "altcoins_enabled": _altcoins_enabled,
            },
        }, status=200)

    async def _handle_trade_execute(self, request: web.Request) -> web.Response:
        """POST /api/trade/execute — execute a previously recommended trade.

        Body ``{"recommendation_id": "...", "confirmed": true}``

        CRITICAL:
          - ``confirmed`` MUST be boolean ``true`` — no execution without it.
          - Guardrails are re-evaluated server-side; client state is not trusted.
          - In paper mode, order is flagged as paper and never sent to SDK.
          - Audit events are always written regardless of outcome.

        Response shape
        --------------
        {
          "status": "submitted"|"blocked"|"rejected",
          "reason": str,
          "order_id": str|null,
          "is_paper": bool,
          "executed_at": str,
        }
        """
        from src.agents.batman import is_kill_switch_active
        from src.config.settings import settings as _s

        executed_at = datetime.now(timezone.utc).isoformat()

        body = await self._safe_json_body(request) or {}
        rec_id = str(body.get("recommendation_id") or "").strip()[:64]
        confirmed = body.get("confirmed")
        # Force-execute override (Story M22.1 — operator escape hatch).
        # When True, the Batman verdict is treated as advisory: a non-
        # executable verdict is logged with severity WARNING but the
        # order is still placed. The override is REJECTED if both
        # `paper_trading=False` AND `bybit_testnet=False`/`is_mainnet=True`
        # — i.e. the operator must be in paper mode OR on a testnet to
        # bypass risk gates. Kill switch is NOT bypassable.
        force_execute = bool(body.get("force_execute") or False)

        # Hard gate: confirmed must be exactly True (boolean)
        if confirmed is not True:
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_BLOCKED",
                severity="WARNING",
                message="TradeNow execute rejected — confirmed != true",
                payload={"recommendation_id": rec_id, "body_keys": list(body.keys())},
            )
            return web.json_response({
                "status": "rejected",
                "reason": "Campo 'confirmed' deve ser exatamente true para executar.",
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=400)

        # Re-evaluate critical guardrails server-side
        if is_kill_switch_active():
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_BLOCKED",
                severity="WARNING",
                message="TradeNow execute blocked — kill switch active",
                payload={"recommendation_id": rec_id},
            )
            return web.json_response({
                "status": "blocked",
                "reason": "Kill switch ativo — libere antes de executar ordens.",
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=200)

        # ── Story 041 — Wire IronMan broker adapter ────────────────────
        # Look up the cached recommendation from _handle_trade_analyze.
        # The cache survives until server restart or 20-entry FIFO eviction.
        cached_rec = self._rec_cache.get(rec_id)

        if cached_rec is None:
            # Recommendation not found — likely server was restarted between
            # analyze and execute, or the rec_id is stale/forged.
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_BLOCKED",
                severity="WARNING",
                message="TradeNow execute blocked — recommendation_id not in cache",
                payload={"recommendation_id": rec_id},
            )
            return web.json_response({
                "status": "blocked",
                "reason": (
                    "Recomendação não encontrada no servidor. "
                    "Execute /api/trade/analyze novamente (o servidor pode ter sido reiniciado)."
                ),
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=200)

        # Block mock recommendations at the server level (belt-and-suspenders;
        # the frontend already disables the confirm button for mock sources).
        if cached_rec.get("source") == "mock":
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_BLOCKED",
                severity="WARNING",
                message="TradeNow execute blocked — mock recommendation, no real signal",
                payload={"recommendation_id": rec_id},
            )
            return web.json_response({
                "status": "blocked",
                "reason": (
                    "Fonte da recomendação é 'mock' — nenhum sinal real disponível. "
                    "Aguarde os agentes gerarem um sinal antes de operar."
                ),
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=200)

        # ── Build TradingSignal from cached recommendation ──────────────
        order_id: str | None = None
        exec_status = "submitted"
        exec_reason = ""

        try:
            from src.models.signal import TradingSignal, TradeAction
            from src.agents.batman import Batman
            from src.agents.iron_man import IronMan
            from src.models.risk import RiskVerdict

            direction = cached_rec.get("direction", "LONG").upper()
            equity_usd = float(cached_rec.get("_equity_usd") or _s.paper_equity_usd or 10_000)

            signal = TradingSignal(
                symbol=cached_rec["symbol"],
                action=TradeAction.LONG if direction == "LONG" else TradeAction.SHORT,
                confidence=float(cached_rec.get("confidence", 0.5)),
                entry_price=float(cached_rec["entry_price"]),
                stop_loss=float(cached_rec["stop_loss"]),
                take_profit=float(cached_rec["take_profit"]),
                size_pct=float(cached_rec.get("size_pct", 0.01)),
                leverage=int(cached_rec.get("leverage", 1)),
                reasoning=str(cached_rec.get("justification", "TradeNow execution"))[:400],
            )

            # Batman risk gate
            batman = Batman()
            approval = await batman.run(signal=signal, equity_usd=equity_usd)

            if not approval.is_executable:
                # ── Force-execute escape hatch (M22.1) ───────────────────
                # If the operator explicitly opted in via force_execute=true
                # AND we are in a safe environment (paper mode OR a testnet),
                # we log the bypass at WARNING and proceed. Otherwise we
                # block exactly like before.
                bybit_safe = (
                    _s.active_exchange == "bybit" and bool(getattr(_s, "bybit_testnet", False))
                )
                binance_safe = (
                    _s.active_exchange == "binance" and bool(getattr(_s, "binance_testnet", False))
                )
                hl_safe = _s.active_exchange == "hyperliquid" and not _s.is_mainnet
                env_is_safe_for_bypass = _s.paper_trading or bybit_safe or binance_safe or hl_safe

                if force_execute and env_is_safe_for_bypass:
                    # Bypass Batman — log loudly so the audit trail makes it
                    # impossible to claim later "I didn't know that was overridden".
                    await MekkaRepository.log_event(
                        agent="Dashboard",
                        event="TRADE_NOW_FORCE_EXECUTE",
                        severity="WARNING",
                        message=(
                            f"FORCE_EXECUTE: Batman verdict {approval.verdict.value} OVERRIDDEN by operator. "
                            f"env: exchange={_s.active_exchange} paper={_s.paper_trading} "
                            f"bybit_testnet={getattr(_s,'bybit_testnet','-')}"
                        ),
                        payload={
                            "recommendation_id": rec_id,
                            "verdict": approval.verdict.value,
                            "reasons": approval.reasons,
                            "exchange": _s.active_exchange,
                            "paper_trading": _s.paper_trading,
                            "bybit_testnet": getattr(_s, "bybit_testnet", None),
                        },
                    )
                    # Build an EXECUTABLE approval so IronMan actually places
                    # the order. Merely "falling through" kept Batman's REJECTED
                    # verdict, and IronMan independently SKIPs anything that is
                    # not is_executable (qty=0). Override with the recommended
                    # size/leverage (clamped to model bounds). Safe because we
                    # already gated on paper/testnet above. Mirrors the manual
                    # trade handler's force path.
                    from src.models.risk import RiskApproval, RiskVerdict
                    approval = RiskApproval(
                        symbol=signal.symbol,
                        verdict=RiskVerdict.APPROVED,
                        reasons=["FORCE_EXECUTE (Modo Deus): override do Batman em paper/testnet"]
                                + list(approval.reasons or []),
                        adjusted_size_pct=max(0.0001, min(float(signal.size_pct), 0.10)),
                        adjusted_leverage=max(1, min(int(signal.leverage), 50)),
                        breached_limits=list(approval.breached_limits or []),
                        metadata={**(approval.metadata or {}), "force_execute": True},
                    )
                elif force_execute and not env_is_safe_for_bypass:
                    # Operator asked to force on a mainnet/live combo — REJECT.
                    # This is a hard rule: we never override risk gates against
                    # real money. The operator must drop to paper or testnet
                    # first if they want this escape hatch.
                    exec_status = "rejected"
                    exec_reason = (
                        "FORCE_EXECUTE solicitado em ambiente mainnet/live — recusado por "
                        "regra dura. Para usar este botão, alterne para paper mode "
                        "ou para uma testnet (bybit_testnet=true, binance_testnet=true, "
                        "ou hyperliquid_network=testnet)."
                    )
                    await MekkaRepository.log_event(
                        agent="Dashboard",
                        event="TRADE_NOW_FORCE_EXECUTE_REJECTED",
                        severity="ERROR",
                        message=exec_reason,
                        payload={
                            "recommendation_id": rec_id,
                            "exchange": _s.active_exchange,
                            "paper_trading": _s.paper_trading,
                            "bybit_testnet": getattr(_s, "bybit_testnet", None),
                            "is_mainnet": _s.is_mainnet,
                        },
                    )
                    return web.json_response({
                        "status": "rejected",
                        "reason": exec_reason,
                        "order_id": None,
                        "is_paper": _s.paper_trading,
                        "executed_at": executed_at,
                    }, status=200)
                else:
                    # No force flag — normal block path.
                    exec_status = "blocked"
                    exec_reason = (
                        f"Batman bloqueou: {approval.verdict.value} — "
                        + (approval.reasons[0] if approval.reasons else "risco excedido")
                    )
                    await MekkaRepository.log_event(
                        agent="Dashboard",
                        event="TRADE_NOW_BLOCKED",
                        severity="WARNING",
                        message=f"TradeNow blocked by Batman verdict={approval.verdict.value}",
                        payload={
                            "recommendation_id": rec_id,
                            "verdict": approval.verdict.value,
                            "reasons": approval.reasons,
                        },
                    )
                    return web.json_response({
                        "status": "blocked",
                        "reason": exec_reason,
                        "order_id": None,
                        "is_paper": _s.paper_trading,
                        "executed_at": executed_at,
                    }, status=200)

            # IronMan execution (paper or live depending on settings.paper_trading)
            iron_man = IronMan()
            result = await iron_man.run(
                signal=signal,
                approval=approval,
                equity_usd=equity_usd,
            )

            # Persist trade to DB so it appears in the trades panel and positions
            try:
                _signal_id = cached_rec.get("signal_id") if cached_rec else None
                # Store SL/TP in metadata so positions_provider can surface them on the chart
                result.metadata = {
                    **(result.metadata or {}),
                    "stop_loss": float(cached_rec.get("stop_loss") or 0),
                    "take_profit": float(cached_rec.get("take_profit") or 0),
                }
                _trade_db_id = await MekkaRepository.save_trade(result, signal_id=_signal_id)
                logger.info(
                    "trade persisted: db_id=%d order_id=%s symbol=%s",
                    _trade_db_id, result.order_id, result.symbol,
                )
            except Exception as _save_exc:
                logger.warning("save_trade failed (non-fatal): %s", _save_exc)

            # Telegram — trade_opened para TradeNow (fire-and-forget)
            try:
                from src.services.telegram_alerter import TelegramAlerter as _TA  # noqa: WPS433
                asyncio.create_task(
                    _TA().trade_opened(execution=result, signal=signal)
                )
            except Exception:
                pass

            order_id = result.order_id
            # Map IronMan's execution status to the dashboard contract.
            # FILLED/PARTIAL/PAPER are successes; ERROR/REJECTED/SKIPPED are
            # failures the operator MUST see — never claim "submitted" when the
            # venue rejected the order (e.g. notional below min, IOC filled 0).
            ok_statuses = {"FILLED", "PARTIAL", "PAPER"}
            exec_ok = result.status.value in ok_statuses
            err_detail = getattr(result, "error", None)
            exec_status = "submitted" if exec_ok else "blocked"
            exec_reason = (
                f"{'Paper' if result.is_paper else 'Live'} order "
                f"{result.status.value} | "
                f"qty={result.quantity} avg={result.avg_price}"
            )
            if not exec_ok and err_detail:
                exec_reason += f" — {err_detail}"

            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_EXECUTED" if exec_ok else "TRADE_NOW_BLOCKED",
                severity="INFO" if exec_ok else "WARNING",
                message=(
                    f"TradeNow order {result.status.value} "
                    f"{'(paper)' if result.is_paper else '(LIVE)'} "
                    f"rec_id={rec_id} order_id={order_id}"
                ),
                payload={
                    "recommendation_id": rec_id,
                    "order_id": order_id,
                    "is_paper": result.is_paper,
                    "status": result.status.value,
                    "symbol": result.symbol,
                    "quantity": result.quantity,
                    "avg_price": result.avg_price,
                    "notional_usd": result.notional_usd,
                    "batman_verdict": approval.verdict.value,
                    "error": err_detail,
                },
            )

        except Exception as exc:
            logger.error("trade_now_execute agent call failed: %s", exc, exc_info=True)
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="TRADE_NOW_BLOCKED",
                severity="ERROR",
                message=f"TradeNow execute agent exception: {exc}",
                payload={"recommendation_id": rec_id, "error": str(exc)},
            )
            return web.json_response({
                "status": "blocked",
                "reason": f"Erro interno na execução: {exc}",
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=200)

        return web.json_response({
            "status": exec_status,
            "reason": exec_reason,
            "order_id": order_id,
            "is_paper": _s.paper_trading,
            "executed_at": executed_at,
        }, status=200)

    # ------------------------------------------------------------------
    # Manual trading (P1.1 — HANDOFF 2026-05-20)
    #
    # The operator can request a trade with explicit parameters (symbol,
    # side, size, leverage, SL%, TP%, entry). Unlike /api/trade/analyze,
    # the signal originates from the OPERATOR, not Vision — but it STILL
    # flows through Batman → IronMan exactly like every other execution.
    # This honours the inviolable rule in CLAUDE.md:
    #   "NUNCA implemente lógica que bypasse Batman antes de IronMan"
    #   "NUNCA coloque ordens diretamente — toda execução passa por IronMan"
    # The previous _handle_trade_manual stub returned a fake order_id
    # without touching Batman or IronMan; that bypass is removed here.
    # ------------------------------------------------------------------

    def _build_manual_signal(self, body: dict):
        """Translate operator params into a validated TradingSignal.

        Returns a tuple ``(signal, entry_price, meta)``. Raises ``ValueError``
        with an operator-readable message on invalid input.

        Body fields: symbol, side(LONG|SHORT), size_pct(%), leverage,
        sl_pct(%), tp_pct(%), entry_price(optional → market mark price).
        """
        from src.models.signal import TradingSignal, TradeAction

        symbol = str(body.get("symbol") or "BTC").strip().upper()
        side   = str(body.get("side") or "LONG").strip().upper()
        if side not in ("LONG", "SHORT"):
            raise ValueError("side inválido (use LONG ou SHORT)")

        try:
            size_pct_in = float(body.get("size_pct") or 0)
            leverage    = int(body.get("leverage") or 0)
            sl_pct      = float(body.get("sl_pct") or 0)
            tp_pct      = float(body.get("tp_pct") or 0)
        except (TypeError, ValueError):
            raise ValueError("Parâmetros numéricos inválidos.")

        # size_pct arrives as a percentage (e.g. 2 = 2%). Convert to the
        # fraction TradingSignal expects, and clamp to the model's 10% cap.
        if not (0.1 <= size_pct_in <= 10):
            raise ValueError("size_pct fora do range permitido (0.1%–10%).")
        size_frac = round(size_pct_in / 100.0, 4)

        if not (1 <= leverage <= 50):
            raise ValueError("leverage fora do range (1–50).")
        if not (0.1 <= sl_pct <= 50):
            raise ValueError("SL% fora do range (0.1–50).")
        if not (0.1 <= tp_pct <= 100):
            raise ValueError("TP% fora do range (0.1–100).")

        # Resolve entry price — explicit value or current mark price.
        entry_in = body.get("entry_price")
        if entry_in not in (None, "", 0, "0"):
            try:
                entry_price = float(entry_in)
            except (TypeError, ValueError):
                raise ValueError("entry_price inválido.")
        else:
            entry_price = float((self._mark_prices or {}).get(symbol) or 0.0)
        if entry_price <= 0:
            raise ValueError(
                f"Sem preço de entrada para {symbol}. Informe um entry_price "
                "manual (o feed de preço ainda não tem cotação para este ativo)."
            )

        # Derive absolute SL/TP from percentages + side. The model validator
        # enforces LONG: SL < entry < TP and SHORT: TP < entry < SL.
        if side == "LONG":
            stop_loss   = round(entry_price * (1 - sl_pct / 100.0), 6)
            take_profit = round(entry_price * (1 + tp_pct / 100.0), 6)
            action = TradeAction.LONG
        else:
            stop_loss   = round(entry_price * (1 + sl_pct / 100.0), 6)
            take_profit = round(entry_price * (1 - tp_pct / 100.0), 6)
            action = TradeAction.SHORT

        signal = TradingSignal(
            symbol=symbol,
            action=action,
            confidence=1.0,  # operator conviction — manual override
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size_pct=size_frac,
            leverage=leverage,
            reasoning="Ordem manual do operador (dashboard).",
        )
        meta = {
            "size_pct_input": size_pct_in,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "entry_source": "manual" if entry_in not in (None, "", 0, "0") else "mark_price",
        }
        return signal, entry_price, meta

    async def _manual_equity_usd(self) -> float:
        """Best-effort equity lookup shared by manual analyze + execute."""
        from src.config.settings import settings as _s
        if not _s.paper_trading:
            try:
                live_portfolio = await self._get_live_portfolio_context(max_age_s=2.0)
                eq = float(live_portfolio.get("equity_usd") or 0.0)
                if live_portfolio.get("is_live_ok") and eq > 0:
                    return eq
            except Exception:
                pass
        try:
            summary = await MekkaRepository.get_pnl_summary(window_days=1)
            eq = float(summary["window"].get("latest_equity_usd") or 0.0)
            if eq > 0:
                return eq
        except Exception:
            pass
        return float(getattr(_s, "paper_equity_usd", 0.0) or 0.0) if _s.paper_trading else 0.0

    async def _handle_trade_manual_analyze(self, request: web.Request) -> web.Response:
        """POST /api/trade/manual-analyze — "pedir parecer dos robôs".

        Runs the operator's parameters through Batman (risk gate) WITHOUT
        executing. Returns the verdict, reasons, adjusted size/leverage,
        available equity and the derived SL/TP so the operator can decide.

        Body: { symbol, side, size_pct, leverage, sl_pct, tp_pct, entry_price? }
        """
        from src.config.settings import settings as _s
        from src.agents.batman import is_kill_switch_active

        generated_at = datetime.now(timezone.utc).isoformat()
        body = await self._safe_json_body(request) or {}

        try:
            signal, entry_price, meta = self._build_manual_signal(body)
        except ValueError as exc:
            return web.json_response({
                "ok": False,
                "verdict": "INVALID",
                "reason": str(exc),
                "generated_at": generated_at,
            }, status=400)

        equity_usd = await self._manual_equity_usd()
        ks_active = is_kill_switch_active()

        risk_usd = round(
            equity_usd * signal.size_pct * abs(signal.entry_price - signal.stop_loss) / signal.entry_price,
            2,
        ) if signal.entry_price else 0.0
        rr = round(signal.risk_reward_ratio, 2) if hasattr(signal, "risk_reward_ratio") else None

        verdict_payload = {
            "ok": True,
            "kill_switch_active": ks_active,
            "equity_usd": round(equity_usd, 2),
            "signal": {
                "symbol": signal.symbol,
                "side": signal.action.value.upper(),
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "size_pct": signal.size_pct,
                "leverage": signal.leverage,
                "entry_source": meta["entry_source"],
                "risk_usd": risk_usd,
                "risk_reward": rr,
            },
            "generated_at": generated_at,
        }

        # Batman parecer (advisory — no execution here).
        try:
            from src.agents.batman import Batman
            batman = Batman()
            approval = await batman.run(signal=signal, equity_usd=equity_usd)
            verdict_payload["batman"] = {
                "verdict": approval.verdict.value,
                "is_executable": approval.is_executable,
                "reasons": approval.reasons,
                "adjusted_size_pct": approval.adjusted_size_pct,
                "adjusted_leverage": approval.adjusted_leverage,
            }
        except Exception as exc:
            logger.warning("manual_analyze Batman call failed: %s", exc)
            verdict_payload["batman"] = {
                "verdict": "ERROR",
                "is_executable": False,
                "reasons": [f"Falha ao consultar Batman: {exc}"],
            }

        await MekkaRepository.log_event(
            agent="Dashboard",
            event="MANUAL_TRADE_ANALYZED",
            severity="INFO",
            message=(
                f"Parecer manual: {signal.action.value.upper()} {signal.symbol} "
                f"verdict={verdict_payload['batman'].get('verdict')}"
            ),
            payload=verdict_payload,
        )
        return web.json_response(verdict_payload, status=200)

    async def _handle_trade_manual(self, request: web.Request) -> web.Response:
        """POST /api/trade/manual — execute an operator-defined trade.

        Body: { symbol, side, size_pct, leverage, sl_pct, tp_pct,
                entry_price?, confirmed, force_execute? }

        Flows through Batman → IronMan exactly like /api/trade/execute. The
        force_execute escape hatch is honoured ONLY in paper mode or on a
        testnet (never against mainnet/live money). Kill switch is never
        bypassable.
        """
        from src.config.settings import settings as _s
        from src.agents.batman import is_kill_switch_active

        executed_at = datetime.now(timezone.utc).isoformat()
        body = await self._safe_json_body(request) or {}

        # Hard gate: confirmed must be exactly True (boolean).
        if body.get("confirmed") is not True:
            return web.json_response({
                "status": "rejected",
                "reason": "Campo 'confirmed' deve ser exatamente true para executar.",
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=400)

        force_execute = bool(body.get("force_execute") or False)

        try:
            signal, entry_price, meta = self._build_manual_signal(body)
        except ValueError as exc:
            return web.json_response({
                "status": "rejected",
                "reason": str(exc),
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=400)

        if is_kill_switch_active():
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="MANUAL_TRADE_BLOCKED",
                severity="WARNING",
                message="Manual trade blocked — kill switch active",
                payload={"symbol": signal.symbol, "side": signal.action.value},
            )
            return web.json_response({
                "status": "blocked",
                "reason": "Kill switch ativo — libere antes de operar.",
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=200)

        equity_usd = await self._manual_equity_usd()

        await MekkaRepository.log_event(
            agent="Dashboard",
            event="MANUAL_TRADE_SUBMITTED",
            severity="INFO",
            message=(
                f"Ordem manual: {signal.action.value.upper()} {signal.symbol} "
                f"size={signal.size_pct:.2%} lev={signal.leverage}x "
                f"entry={signal.entry_price} SL={signal.stop_loss} TP={signal.take_profit}"
            ),
            payload={
                "symbol": signal.symbol, "side": signal.action.value,
                "size_pct": signal.size_pct, "leverage": signal.leverage,
                "entry_price": signal.entry_price, "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit, "force_execute": force_execute,
                "entry_source": meta["entry_source"],
            },
        )

        order_id: str | None = None
        try:
            from src.agents.batman import Batman
            from src.agents.iron_man import IronMan

            batman = Batman()
            approval = await batman.run(signal=signal, equity_usd=equity_usd)

            if not approval.is_executable:
                bybit_safe = (
                    _s.active_exchange == "bybit" and bool(getattr(_s, "bybit_testnet", False))
                )
                binance_safe = (
                    _s.active_exchange == "binance" and bool(getattr(_s, "binance_testnet", False))
                )
                hl_safe = _s.active_exchange == "hyperliquid" and not _s.is_mainnet
                env_is_safe_for_bypass = _s.paper_trading or bybit_safe or binance_safe or hl_safe

                if force_execute and env_is_safe_for_bypass:
                    await MekkaRepository.log_event(
                        agent="Dashboard",
                        event="MANUAL_TRADE_FORCE_EXECUTE",
                        severity="WARNING",
                        message=(
                            f"FORCE_EXECUTE: Batman verdict {approval.verdict.value} OVERRIDDEN "
                            f"on manual trade. env: exchange={_s.active_exchange} "
                            f"paper={_s.paper_trading} bybit_testnet={getattr(_s,'bybit_testnet','-')}"
                        ),
                        payload={
                            "symbol": signal.symbol, "side": signal.action.value,
                            "verdict": approval.verdict.value, "reasons": approval.reasons,
                        },
                    )
                    # Security visibility: alert the operator on Telegram that a
                    # Batman override (Modo Deus) was used.
                    try:
                        from src.services.telegram_alerter import TelegramAlerter as _TA
                        asyncio.create_task(_TA().alert(
                            event="MANUAL_TRADE_FORCE_EXECUTE", severity="WARNING", agent="Dashboard",
                            symbol=signal.symbol,
                            message=(f"🔱 *MODO DEUS* — override do Batman ({approval.verdict.value}) "
                                     f"em {signal.symbol} {signal.action.value}. "
                                     f"Execução forçada (paper/testnet)."),
                        ))
                    except Exception:  # noqa: BLE001
                        pass
                    # Build an EXECUTABLE approval so IronMan actually places the
                    # order. Merely "falling through" kept Batman's REJECTED
                    # verdict, and IronMan independently SKIPs anything that
                    # isn't is_executable (qty=0). Override with the operator's
                    # requested size/leverage (clamped to model bounds). Safe
                    # because we already gated on paper/testnet above.
                    from src.models.risk import RiskApproval, RiskVerdict
                    approval = RiskApproval(
                        symbol=signal.symbol,
                        verdict=RiskVerdict.APPROVED,
                        reasons=["FORCE_EXECUTE (Modo Deus): override do Batman em paper/testnet"]
                                + list(approval.reasons or []),
                        adjusted_size_pct=max(0.0001, min(float(signal.size_pct), 0.10)),
                        adjusted_leverage=max(1, min(int(signal.leverage), 50)),
                        breached_limits=list(approval.breached_limits or []),
                        metadata={**(approval.metadata or {}), "force_execute": True},
                    )
                elif force_execute and not env_is_safe_for_bypass:
                    reason = (
                        "FORCE_EXECUTE solicitado em ambiente mainnet/live — recusado por "
                        "regra dura. Alterne para paper mode ou testnet primeiro."
                    )
                    await MekkaRepository.log_event(
                        agent="Dashboard",
                        event="MANUAL_TRADE_FORCE_EXECUTE_REJECTED",
                        severity="ERROR",
                        message=reason,
                        payload={"symbol": signal.symbol, "is_mainnet": _s.is_mainnet},
                    )
                    return web.json_response({
                        "status": "rejected", "reason": reason, "order_id": None,
                        "is_paper": _s.paper_trading, "executed_at": executed_at,
                    }, status=200)
                else:
                    reason = (
                        f"Batman bloqueou: {approval.verdict.value} — "
                        + (approval.reasons[0] if approval.reasons else "risco excedido")
                    )
                    await MekkaRepository.log_event(
                        agent="Dashboard",
                        event="MANUAL_TRADE_BLOCKED",
                        severity="WARNING",
                        message=f"Manual trade blocked by Batman verdict={approval.verdict.value}",
                        payload={
                            "symbol": signal.symbol, "verdict": approval.verdict.value,
                            "reasons": approval.reasons,
                        },
                    )
                    return web.json_response({
                        "status": "blocked", "reason": reason, "order_id": None,
                        "is_paper": _s.paper_trading, "executed_at": executed_at,
                    }, status=200)

            iron_man = IronMan()
            result = await iron_man.run(signal=signal, approval=approval, equity_usd=equity_usd)

            try:
                result.metadata = {
                    **(result.metadata or {}),
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "manual": True,
                }
                await MekkaRepository.save_trade(result, signal_id=None)
            except Exception as _save_exc:
                logger.warning("manual save_trade failed (non-fatal): %s", _save_exc)

            try:
                from src.services.telegram_alerter import TelegramAlerter as _TA  # noqa: WPS433
                asyncio.create_task(_TA().trade_opened(execution=result, signal=signal))
            except Exception:
                pass

            order_id = result.order_id
            # Map IronMan's execution status to the dashboard contract.
            # FILLED/PARTIAL/PAPER are successes; ERROR/REJECTED/SKIPPED are
            # failures the operator must see (don't claim "submitted" when
            # the venue rejected the order, e.g. notional below min size).
            ok_statuses = {"FILLED", "PARTIAL", "PAPER"}
            exec_ok = result.status.value in ok_statuses
            api_status = "submitted" if exec_ok else "blocked"
            err_detail = getattr(result, "error", None)
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="MANUAL_TRADE_EXECUTED" if exec_ok else "MANUAL_TRADE_BLOCKED",
                severity="INFO" if exec_ok else "WARNING",
                message=(
                    f"Manual order {result.status.value} "
                    f"{'(paper)' if result.is_paper else '(LIVE)'} "
                    f"{signal.symbol} order_id={order_id}"
                ),
                payload={
                    "order_id": order_id, "is_paper": result.is_paper,
                    "status": result.status.value, "symbol": result.symbol,
                    "quantity": result.quantity, "avg_price": result.avg_price,
                    "batman_verdict": approval.verdict.value,
                    "error": err_detail,
                },
            )
            reason = (
                f"{'Paper' if result.is_paper else 'Live'} order {result.status.value} | "
                f"qty={result.quantity} avg={result.avg_price}"
            )
            if not exec_ok and err_detail:
                low = str(err_detail).lower()
                if "10024" in str(err_detail) or "regulatory" in low or "kyc" in low:
                    reason += (" — 🚫 A Bybit recusou por restrição regulatória/KYC desta conta "
                               "(retCode 10024). Conclua o KYC na Bybit, troque de exchange, ou "
                               "ative PAPER_TRADING=true para simular a abertura da posição.")
                else:
                    reason += f" — {err_detail}"
            return web.json_response({
                "status": api_status,
                "reason": reason,
                "order_id": order_id,
                "is_paper": result.is_paper,
                "symbol": result.symbol,
                "side": signal.action.value.upper(),
                "executed_at": executed_at,
            }, status=200)

        except Exception as exc:
            logger.error("manual trade execution failed: %s", exc, exc_info=True)
            await MekkaRepository.log_event(
                agent="Dashboard",
                event="MANUAL_TRADE_BLOCKED",
                severity="ERROR",
                message=f"Manual trade exception: {exc}",
                payload={"symbol": signal.symbol, "error": str(exc)},
            )
            return web.json_response({
                "status": "blocked",
                "reason": f"Erro interno na execução: {exc}",
                "order_id": None,
                "is_paper": _s.paper_trading,
                "executed_at": executed_at,
            }, status=200)

    async def _handle_jean_health_report(self, _: web.Request) -> web.Response:
        """GET /api/jean/health-report — run Jean Grey's vault health scan.

        Returns broken wikilinks, orphan notes and duplicate candidates so
        the operator can keep the second brain tidy. Read-only (P2.1).
        """
        try:
            from src.agents.jean_grey import JeanGrey
            report = await JeanGrey().run(mode="health")
            return web.json_response(report.to_dict(), status=200)
        except Exception as exc:  # noqa: BLE001
            logger.error("jean health-report failed: %s", exc, exc_info=True)
            return web.json_response(
                {"error": f"Falha ao gerar relatório do vault: {exc}"},
                status=200,
            )

    async def _handle_jean_graph(self, _: web.Request) -> web.Response:
        """GET /api/jean/graph — link graph of the vault (second brain) for the
        neural-connections visualization. {nodes, links, total_notes,
        total_links}. CPU-bound scan runs off the event loop. Read-only.
        """
        try:
            import asyncio as _asyncio
            from src.agents.jean_grey import JeanGrey
            graph = await _asyncio.to_thread(JeanGrey().build_graph)
            return web.json_response(graph, status=200)
        except Exception as exc:  # noqa: BLE001
            logger.error("jean graph failed: %s", exc, exc_info=True)
            return web.json_response(
                {"nodes": [], "links": [], "error": str(exc)}, status=200,
            )

    # Continuous-Improvement endpoints — bodies live in
    # src/dashboard/routers/improvements.py (extracted from this file). These
    # thin forwarders keep the route registration unchanged.
    async def _handle_improvements_get(self, request: web.Request) -> web.Response:
        from src.dashboard.routers import improvements as _impr
        return await _impr.handle_get(self, request)

    async def _handle_improvements_decision(self, request: web.Request) -> web.Response:
        from src.dashboard.routers import improvements as _impr
        return await _impr.handle_decision(self, request)

    async def _handle_improvements_pr_status(self, request: web.Request) -> web.Response:
        from src.dashboard.routers import improvements as _impr
        return await _impr.handle_pr_status(self, request)

    async def _handle_improvements_kpi(self, request: web.Request) -> web.Response:
        from src.dashboard.routers import improvements as _impr
        return await _impr.handle_kpi(self, request)

    async def _handle_improvements_claim(self, request: web.Request) -> web.Response:
        from src.dashboard.routers import improvements as _impr
        return await _impr.handle_claim(self, request)

    async def _handle_improvements_history(self, request: web.Request) -> web.Response:
        from src.dashboard.routers import improvements as _impr
        return await _impr.handle_decision_history(self, request)

    async def _handle_mentor_suggestions(self, _: web.Request) -> web.Response:
        """GET /api/mentor/suggestions — Charles Xavier proposes parameter deltas."""
        try:
            from src.agents.mentor import Mentor  # noqa: WPS433
            report = await Mentor().run()
            return web.json_response(report.to_dict(), status=200)
        except Exception as exc:  # noqa: BLE001
            logger.error("mentor suggestions failed: %s", exc, exc_info=True)
            return web.json_response(
                {"error": str(exc), "suggestions": [], "observation_summary": {}},
                status=200,
            )

    async def _handle_improvements_approve_pr(self, request: web.Request) -> web.Response:
        from src.dashboard.routers import improvements as _impr
        return await _impr.handle_approve_pr(self, request)

    def _prune_snapshot_dir(self) -> None:
        """Keep only the most recent ``SNAPSHOT_RETENTION_MINUTES`` snapshots
        and ``INCIDENT_BUNDLE_RETENTION`` incident bundles. Runs in a thread
        so disk I/O never blocks the event loop."""
        try:
            snaps = sorted(SNAPSHOT_DIR.glob("snapshot-*.json"))
            for stale in snaps[:-SNAPSHOT_RETENTION_MINUTES]:
                try:
                    stale.unlink()
                except OSError:
                    pass
            bundles = sorted(SNAPSHOT_DIR.glob("incident-bundle-*.json"))
            for stale in bundles[:-INCIDENT_BUNDLE_RETENTION]:
                try:
                    stale.unlink()
                except OSError:
                    pass
        except OSError as exc:
            logger.warning("snapshot prune failed: %s", exc)


async def run_dashboard_server(
    host: str = "127.0.0.1", port: int = 8787, controller=None
) -> None:
    """Boot the dashboard. Default bind is loopback so the UI is not exposed
    on the LAN by accident; pass host='0.0.0.0' explicitly when sharing.

    ``controller`` é o RuntimeController (opcional) que liga/desliga o loop
    de trading via /api/system/*. None = control plane sem runtime acoplado.
    """
    server = MekkaDashboardServer(controller=controller)
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info("dashboard listening on http://%s:%d", host, port)

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


def _backtest_summary_to_dict(summary) -> dict:
    """Serializa BacktestSummary para dict JSON-safe (Stories 224-228)."""
    m = summary.metrics
    return {
        "symbol":              summary.symbol,
        "start_date":          summary.start_date.isoformat() if summary.start_date else None,
        "end_date":            summary.end_date.isoformat() if summary.end_date else None,
        "generated_at":        summary.generated_at.isoformat(),
        "initial_equity_usd":  summary.initial_equity_usd,
        "final_equity_usd":    round(summary.final_equity_usd, 2),
        "total_return_pct":    round(summary.total_return_pct, 4),
        "metrics": {
            "total_trades":       m.total_trades,
            "wins":               m.wins,
            "losses":             m.losses,
            "expired":            m.expired,
            "win_rate":           round(m.win_rate, 4),
            "profit_factor":      round(m.profit_factor, 4),
            "expectancy_usd":     round(m.expectancy_usd, 4),
            "avg_win_usd":        round(m.avg_win_usd, 2),
            "avg_loss_usd":       round(m.avg_loss_usd, 2),
            "avg_risk_reward":    round(m.avg_risk_reward, 4),
            "avg_confidence":     round(m.avg_confidence, 4),
            "sharpe_ratio":       round(m.sharpe_ratio, 4),
            "sortino_ratio":      round(m.sortino_ratio, 4),
            "max_drawdown_pct":   round(m.max_drawdown_pct, 4),
            "max_drawdown_usd":   round(m.max_drawdown_usd, 2),
            "total_pnl_usd":      round(m.total_pnl_usd, 2),
            "total_pnl_pct":      round(m.total_pnl_pct, 4),
            "days_covered":       round(m.days_covered, 1),
        },
        "equity_curve": [
            {
                "timestamp":     pt.timestamp.isoformat() if pt.timestamp else None,
                "equity_usd":    round(pt.equity_usd, 2),
                "trade_pnl_usd": round(pt.trade_pnl_usd, 2),
                "drawdown_pct":  round(pt.drawdown_pct, 4),
                "symbol":        pt.symbol,
                "outcome":       pt.outcome.value,
            }
            for pt in summary.equity_curve
        ],
        "trades_count": len(summary.trades),
    }


def _safe_limit(raw: str | None, default: int, max_value: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    # Negative or zero is treated as garbage input (same bucket as
    # non-numeric) — fall back to default so callers can rely on
    # `_safe_limit(...) >= 1` without an extra clamp at the call site.
    if value < 1:
        return default
    return min(value, max_value)


def _diag_public_view(diag: dict[str, Any]) -> dict[str, Any]:
    lat = [float(v) for v in diag.get("latencies_ms", []) if isinstance(v, (int, float))]
    return {
        "calls": int(diag.get("calls") or 0),
        "cache_hits": int(diag.get("cache_hits") or 0),
        "stale_served": int(diag.get("stale_served") or 0),
        "errors": int(diag.get("errors") or 0),
        "last_error": diag.get("last_error"),
        "failure_streak": int(diag.get("failure_streak") or 0),
        "breaker_open": bool(diag.get("breaker_open") or False),
        "breaker_open_until_s": diag.get("breaker_open_until_s"),
        "last_latency_ms": diag.get("last_latency_ms"),
        "avg_latency_ms": diag.get("avg_latency_ms"),
        "sample_count": len(lat),
        "p50_latency_ms": _percentile(lat, 0.5),
        "p95_latency_ms": _percentile(lat, 0.95),
    }


def _incident_matches_query(item: dict[str, Any], query: str) -> bool:
    if query in str(item.get("snapshot") or "").lower():
        return True
    if query in str(item.get("tier") or "").lower():
        return True
    for key, value in (item.get("drivers") or {}).items():
        if bool(value) and query in str(key).lower():
            return True
    for alert in (item.get("alerts") or []):
        code = str(alert.get("code") or "").lower()
        message = str(alert.get("message") or "").lower()
        if query in code or query in message:
            return True
    return False


def _build_global_alerts(
    audits: list[Any], drawdown_pct: float | None = None
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if KILL_SWITCH_FILE.exists():
        alerts.append(
            {
                "code": "KILL_SWITCH_FILE",
                "severity": "CRITICAL",
                "message": f"Kill switch file ativo em {KILL_SWITCH_FILE}",
            }
        )

    # Drawdown alerts. Two thresholds: WARN (default 5%) lights up the
    # severity score and surfaces in the UI banner; CRITICAL (default 10%)
    # bumps the score hard so the incident queue ranks it near kill-switch
    # events. Both thresholds are configurable via env.
    dd = float(drawdown_pct or 0.0)
    if dd >= _DRAWDOWN_CRIT:
        alerts.append(
            {
                "code": "DRAWDOWN_CRITICAL",
                "severity": "CRITICAL",
                "message": (
                    f"Drawdown atual {dd * 100:.2f}% >= "
                    f"{_DRAWDOWN_CRIT * 100:.2f}% (CRITICAL)"
                ),
                "drawdown_pct": dd,
            }
        )
    elif dd >= _DRAWDOWN_WARN:
        alerts.append(
            {
                "code": "DRAWDOWN_WARNING",
                "severity": "WARNING",
                "message": (
                    f"Drawdown atual {dd * 100:.2f}% >= "
                    f"{_DRAWDOWN_WARN * 100:.2f}% (WARNING)"
                ),
                "drawdown_pct": dd,
            }
        )

    # Kill-switch + CYCLE_SKIPPED banner: time-windowed, ENGAGED-only.
    # The on-disk KILL_SWITCH_FILE check above already covers current state.
    # This block surfaces RECENT activity only (last 10 min), and never raises
    # an alert for a RELEASE event — those mean the switch is OFF.
    try:
        from datetime import datetime as _dt_ks, timedelta as _td_ks, timezone as _tz_ks
        _now_ks = _dt_ks.now(_tz_ks.utc)
        _window_ks = _td_ks(minutes=10)
        _is_ks_event = lambda ev: (  # noqa: E731
            "KILL_SWITCH" in ev and "RELEASED" not in ev
        ) or "CYCLE_SKIPPED" in ev
        kill_rows = []
        for r in audits:
            ev = r.event or ""
            if not _is_ks_event(ev):
                continue
            ts = r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_tz_ks.utc)
            if (_now_ks - ts) <= _window_ks:
                kill_rows.append((ts, r))
        if kill_rows:
            kill_rows.sort(key=lambda x: x[0], reverse=True)
            ts_recent, row = kill_rows[0]
            alerts.append(
                {
                    "code": "KILL_SWITCH_EVENT",
                    "severity": "CRITICAL",
                    "message": f"{row.agent} reportou {row.event}",
                    "timestamp": ts_recent.isoformat(),
                }
            )
    except Exception:  # noqa: BLE001
        pass

    pause_rows = [r for r in audits if r.agent == "SpiderMan" and bool((r.payload or {}).get("should_pause"))]
    if pause_rows:
        row = sorted(pause_rows, key=lambda r: r.timestamp, reverse=True)[0]
        alerts.append(
            {
                "code": "ANOMALY_PAUSE",
                "severity": "WARNING",
                "message": f"Spider-Man sinalizou pausa em {row.symbol or '-'}",
                "timestamp": row.timestamp.isoformat(),
            }
        )
    return alerts

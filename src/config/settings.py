"""
src/config/settings.py
======================
Central configuration for Mekka Trading.

Reads all values from environment variables (or a .env file via python-dotenv).
Uses Pydantic v2 BaseSettings so every field is validated and typed at startup.

Usage
-----
    from src.config.settings import settings

    print(settings.trading_assets)       # ['BTC', 'ETH', 'SOL']
    print(settings.hyperliquid_network)  # 'testnet'
"""

from __future__ import annotations

from functools import cached_property
from typing import Annotated, List, Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration values for the Mekka Trading system.

    Values are loaded from environment variables and/or a .env file.
    Validation happens at import time — any missing required value raises
    immediately so the system never starts with a broken configuration.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --------------------------------------------------------------------------
    # OpenAI
    # --------------------------------------------------------------------------
    openai_api_key: str = Field(..., description="OpenAI API key (sk-...)")
    openai_model: str = Field(
        default="gpt-4o",
        description="Model used by Vision (the decision LLM)",
    )
    openai_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="LLM sampling temperature — keep low for deterministic trading decisions",
    )
    openai_max_tokens: int = Field(
        default=2048,
        gt=0,
        description="Maximum tokens in LLM response",
    )

    # --------------------------------------------------------------------------
    # Hyperliquid
    # --------------------------------------------------------------------------
    hyperliquid_private_key: str = Field(
        ..., description="EVM private key for signing Hyperliquid orders"
    )
    hyperliquid_wallet_address: str = Field(
        ..., description="EVM wallet address (0x...)"
    )
    hyperliquid_network: Literal["testnet", "mainnet"] = Field(
        default="testnet",
        description="Which Hyperliquid network to connect to",
    )

    # --------------------------------------------------------------------------
    # Multi-Exchange (Story 047 — Bybit / Binance adapter)
    # --------------------------------------------------------------------------
    active_exchange: Literal["hyperliquid", "bybit", "binance"] = Field(
        default="hyperliquid",
        alias="ACTIVE_EXCHANGE",
        description=(
            "Primary exchange for market data (Superman) and live execution (IronMan). "
            "'hyperliquid' uses the HL SDK; 'bybit'/'binance' use CCXT unified API."
        ),
    )
    bybit_api_key: str = Field(
        default="",
        description="Bybit API key (required when ACTIVE_EXCHANGE=bybit)",
    )
    bybit_api_secret: str = Field(
        default="",
        description="Bybit API secret (required when ACTIVE_EXCHANGE=bybit)",
    )
    binance_api_key: str = Field(
        default="",
        description="Binance API key (required when ACTIVE_EXCHANGE=binance)",
    )
    binance_api_secret: str = Field(
        default="",
        description="Binance API secret (required when ACTIVE_EXCHANGE=binance)",
    )

    # --------------------------------------------------------------------------
    # Telegram
    # --------------------------------------------------------------------------
    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token — leave empty to disable notifications",
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat/channel ID for notifications",
    )

    # --------------------------------------------------------------------------
    # News & Sentiment
    # --------------------------------------------------------------------------
    cryptopanic_api_key: str = Field(
        default="",
        description="CryptoPanic API key for headline sentiment — optional",
    )

    # --------------------------------------------------------------------------
    # Logging
    # --------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Loguru log level",
    )

    # --------------------------------------------------------------------------
    # Paper Trading
    # --------------------------------------------------------------------------
    paper_trading: bool = Field(
        default=True,
        description="When True, no real orders are sent to Hyperliquid",
    )

    # [036] Second explicit opt-in required for live execution.
    # BOTH paper_trading=False AND live_trading_confirmed=True must be set
    # before IronMan will touch the real exchange. Belt-and-suspenders:
    # accidental paper_trading=False (e.g. .env copy-paste) does NOT
    # expose real funds without a deliberate second env var.
    live_trading_confirmed: bool = Field(
        default=False,
        description=(
            "Explicit second opt-in for live execution. "
            "Must be True together with paper_trading=False. "
            "Set LIVE_TRADING_CONFIRMED=true only after operator sign-off in "
            "docs/MAINNET-AUTHORIZATION.md."
        ),
    )

    # --------------------------------------------------------------------------
    # Assets
    # --------------------------------------------------------------------------
    trading_assets_raw: str = Field(
        default="BTC,ETH,SOL",
        alias="TRADING_ASSETS",
        description="Comma-separated list of assets to trade",
    )

    # --------------------------------------------------------------------------
    # Risk Management
    # --------------------------------------------------------------------------
    max_position_size_pct: Annotated[float, Field(gt=0.0, le=1.0)] = Field(
        default=0.02,
        description="Maximum single position size as a fraction of equity (0.02 = 2%)",
    )
    max_leverage: Annotated[int, Field(ge=1, le=50)] = Field(
        default=5,
        description="Maximum allowed leverage for any trade",
    )
    max_leverage_high_regime: Annotated[int, Field(ge=1, le=50)] = Field(
        default=3,
        description="Maximum leverage when Thor classifies volatility as HIGH. Overrides max_leverage.",
    )
    max_leverage_extreme_regime: Annotated[int, Field(ge=1, le=50)] = Field(
        default=2,
        description="Maximum leverage when Thor classifies volatility as EXTREME. Overrides max_leverage.",
    )
    max_daily_drawdown_pct: Annotated[float, Field(gt=0.0, le=1.0)] = Field(
        default=0.10,
        description="Halt trading if daily drawdown exceeds this fraction (0.10 = 10%)",
    )
    # Story 066 — Trailing stop distance after TP1 scale-out
    trailing_stop_pct: Annotated[float, Field(gt=0.0, le=0.10)] = Field(
        default=0.015,
        description="Trailing stop distance after scale-out TP1 (0.015 = 1.5% from current mark)",
    )
    # Story 067 — Daily profit target auto-pause
    daily_profit_target_pct: Annotated[float, Field(gt=0.0, le=1.0)] = Field(
        default=0.05,
        description="Pause new signals when daily PnL reaches this fraction of equity (0.05 = 5%)",
    )
    # Story 068 — Portfolio exposure cap
    max_portfolio_exposure_pct: Annotated[float, Field(gt=0.0, le=1.0)] = Field(
        default=0.20,
        description="Block new entries if total open notional exceeds this fraction of equity (0.20 = 20%)",
    )

    # --------------------------------------------------------------------------
    # Timing (seconds)
    # --------------------------------------------------------------------------
    main_loop_interval_seconds: int = Field(
        default=14_400,  # 4 hours
        description="How often the main 4h analysis loop runs",
    )
    monitor_interval_seconds: int = Field(
        default=300,  # 5 minutes
        description="How often the position monitor (Batman) checks open positions",
    )
    daily_reset_hour_utc: int = Field(
        default=0,
        ge=0,
        le=23,
        description="UTC hour at which daily PnL and counters are reset",
    )

    # --------------------------------------------------------------------------
    # Technical Analysis
    # --------------------------------------------------------------------------
    primary_timeframe: str = Field(
        default="4h",
        description="Primary OHLCV timeframe for analysis",
    )
    confirmation_timeframe: str = Field(
        default="1h",
        description="Secondary timeframe used for signal confirmation",
    )
    candles_lookback: int = Field(
        default=200,
        description="Number of historical candles to fetch for indicator calculation",
    )

    # --------------------------------------------------------------------------
    # Order Management
    # --------------------------------------------------------------------------
    min_confidence_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Minimum Vision confidence score required to place a trade",
    )
    min_risk_reward_ratio: float = Field(
        default=1.5,
        gt=0.0,
        description="Minimum risk/reward ratio — orders below this are rejected",
    )
    max_open_positions: int = Field(
        default=3,
        ge=1,
        description="Maximum number of simultaneously open positions",
    )
    max_trades_per_day: int = Field(
        default=10,
        ge=1,
        description="Circuit breaker: stop trading after this many trades in a day",
    )

    # --------------------------------------------------------------------------
    # Database
    # --------------------------------------------------------------------------
    sqlite_db_path: str = Field(
        default="data/mekka_trading.db",
        description="Path to the SQLite database file",
    )

    # --------------------------------------------------------------------------
    # Portfolio Manager (Story 026)
    # --------------------------------------------------------------------------
    paper_slippage_bps: float = Field(
        default=3.0,
        ge=0.0,
        le=100.0,
        description=(
            "Synthetic slippage applied to paper fills (basis points). "
            "3 bps = 0.03%% of fill price. Applied in the direction that "
            "hurts the trade: higher price for LONG, lower for SHORT."
        ),
    )

    paper_equity_usd: float = Field(
        default=10_000.0,
        gt=0.0,
        description=(
            "Synthetic equity used when paper_trading=True and the live "
            "Hyperliquid clearinghouseState is unavailable. Portfolio Manager "
            "falls back to this value to keep Batman validating against a "
            "non-zero number."
        ),
    )

    # --------------------------------------------------------------------------
    # Safety Net (Story 029a)
    # --------------------------------------------------------------------------
    max_total_capital_pct: Annotated[float, Field(gt=0.0, le=1.0)] = Field(
        default=0.10,
        description=(
            "Maximum total notional deployed across all open positions, as a "
            "fraction of equity. Batman blocks any new entry that would push "
            "running notional above this cap."
        ),
    )
    max_total_notional_usd: Optional[float] = Field(
        default=None,
        description=(
            "Optional absolute cap (USD) on total notional. When set, takes "
            "precedence over max_total_capital_pct. Use as belt-and-suspenders "
            "during the first weeks on testnet."
        ),
    )
    max_consecutive_exec_errors: int = Field(
        default=3,
        ge=1,
        description=(
            "Engage kill switch after this many consecutive ExecutionStatus.ERROR "
            "outcomes from Iron Man. Counter resets on any non-error execution."
        ),
    )
    max_consecutive_vision_fallbacks: int = Field(
        default=5,
        ge=1,
        description=(
            "Engage kill switch after this many consecutive Vision fallback "
            "HOLDs (signal.metadata.fallback=True). Counter resets on any "
            "non-fallback signal."
        ),
    )

    # --------------------------------------------------------------------------
    # Vision Critic (Story 031)
    # --------------------------------------------------------------------------
    vision_critic_enabled: bool = Field(
        default=True,
        description=(
            "When True, every Vision signal is reviewed by a second LLM "
            "(Vision Critic). Adds ~1 OpenAI call per symbol per cycle. "
            "Enabled by default — disabling degrades signal quality and "
            "should only be done temporarily to reduce API costs."
        ),
    )
    vision_critic_min_disagreement: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum confidence-delta the critic must claim to AMEND or "
            "REJECT. Below this threshold the critic's verdict is downgraded "
            "to ENDORSE — small disagreements aren't worth overriding."
        ),
    )
    vision_critic_model: str = Field(
        default="",
        description=(
            "Model used by VisionCritic. Empty string = inherit openai_model. "
            "Set to 'gpt-4o-mini' to cut critic cost by ~60%% while keeping "
            "Vision on the full model."
        ),
    )
    vision_critic_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description=(
            "Sampling temperature for VisionCritic. Default 0.0 for maximum "
            "determinism and conservative bias, different from Vision's 0.2."
        ),
    )

    # --------------------------------------------------------------------------
    # Telegram alerter (Story 035)
    # --------------------------------------------------------------------------
    telegram_alert_min_severity: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="WARNING",
        description=(
            "Minimum severity for Telegram push alerts. Audit events below "
            "this threshold are skipped."
        ),
    )
    telegram_alert_events_raw: str = Field(
        default="RISK_KILL_SWITCH,EXEC_ERROR,AGENT_ERROR,WRITE_ERROR,CYCLE_ERROR",
        alias="TELEGRAM_ALERT_EVENTS",
        description=(
            "Comma-separated whitelist of event codes that trigger a "
            "Telegram alert regardless of severity (still subject to "
            "telegram_enabled). Empty string disables event-based filter."
        ),
    )
    telegram_alert_timeout_seconds: float = Field(
        default=5.0,
        gt=0.0,
        description="HTTP timeout for Telegram Bot API calls.",
    )

    # --------------------------------------------------------------------------
    # Telegram inbound (Story 035b)
    # --------------------------------------------------------------------------
    telegram_inbound_enabled: bool = Field(
        default=False,
        description=(
            "When True, TelegramInboundPoller starts long-polling getUpdates "
            "and dispatches operator commands (/status /pnl /pause /resume /positions)."
        ),
    )
    telegram_inbound_allowed_chat_ids_raw: str = Field(
        default="",
        alias="TELEGRAM_INBOUND_ALLOWED_CHAT_IDS",
        description=(
            "Comma-separated list of Telegram chat IDs that may send commands. "
            "Empty string disables the allowlist check (all chats accepted — "
            "only do this on private bots)."
        ),
    )
    telegram_inbound_poll_interval_seconds: float = Field(
        default=2.0,
        ge=0.5,
        le=30.0,
        description="Sleep between getUpdates calls (seconds).",
    )
    telegram_inbound_long_poll_timeout_seconds: int = Field(
        default=25,
        ge=1,
        le=50,
        description=(
            "Telegram long-poll timeout (seconds). Telegram holds the connection "
            "open for up to this many seconds before returning an empty result."
        ),
    )

    # ==========================================================================
    # Validators
    # ==========================================================================

    @field_validator("hyperliquid_wallet_address")
    @classmethod
    def wallet_must_be_hex(cls, v: str) -> str:
        """Ensure the wallet address looks like a hex Ethereum address."""
        if v and not v.startswith("0x"):
            raise ValueError(
                "HYPERLIQUID_WALLET_ADDRESS must start with '0x'. "
                f"Got: {v[:10]}..."
            )
        return v.lower()

    @field_validator("openai_api_key")
    @classmethod
    def openai_key_must_not_be_placeholder(cls, v: str) -> str:
        # Reject only the literal example placeholder — allow test stubs
        if v == "sk-your-openai-api-key-here" or v == "":
            raise ValueError(
                "OPENAI_API_KEY is not set. Please add a real key to your .env file."
            )
        return v

    @model_validator(mode="after")
    def warn_paper_trading(self) -> "Settings":
        """Log a clear warning when running in paper trading mode."""
        if self.paper_trading:
            # We cannot use loguru here (circular import risk at module load time)
            # The main entrypoint will log this instead.
            pass
        return self

    @model_validator(mode="after")
    def live_trading_double_gate(self) -> "Settings":
        """
        [036] Enforce the double-gate for live execution.

        Allowed combinations:
          paper_trading=True,  live_trading_confirmed=False  → PAPER (normal)
          paper_trading=True,  live_trading_confirmed=True   → PAPER (confirmed ignored)
          paper_trading=False, live_trading_confirmed=True   → LIVE  (explicit double opt-in)
          paper_trading=False, live_trading_confirmed=False  → ERROR (accidental live attempt)
        """
        if not self.paper_trading and not self.live_trading_confirmed:
            raise ValueError(
                "LIVE_TRADING_CONFIRMED must be set to 'true' when PAPER_TRADING=false. "
                "This double-gate prevents accidental live orders. "
                "Read docs/MAINNET-AUTHORIZATION.md before enabling live trading."
            )
        return self

    @property
    def is_live(self) -> bool:
        """True only when both paper_trading=False AND live_trading_confirmed=True."""
        return not self.paper_trading and self.live_trading_confirmed

    # ==========================================================================
    # Computed Properties
    # ==========================================================================

    @cached_property
    def trading_assets(self) -> List[str]:
        """Parsed list of trading asset symbols, e.g. ['BTC', 'ETH', 'SOL']."""
        return [a.strip().upper() for a in self.trading_assets_raw.split(",") if a.strip()]

    @cached_property
    def hyperliquid_base_url(self) -> str:
        """REST API base URL for the selected network."""
        if self.hyperliquid_network == "mainnet":
            return "https://api.hyperliquid.xyz"
        return "https://api.hyperliquid-testnet.xyz"

    @cached_property
    def is_mainnet(self) -> bool:
        return self.hyperliquid_network == "mainnet"

    @cached_property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @cached_property
    def telegram_alert_events(self) -> set[str]:
        """Parsed whitelist of event codes that always trigger Telegram alerts."""
        raw = (self.telegram_alert_events_raw or "").strip()
        if not raw:
            return set()
        return {tok.strip().upper() for tok in raw.split(",") if tok.strip()}

    @cached_property
    def telegram_inbound_allowed_chat_ids(self) -> set[str]:
        """Parsed set of allowed chat IDs for inbound commands. Empty = all allowed."""
        raw = (self.telegram_inbound_allowed_chat_ids_raw or "").strip()
        if not raw:
            return set()
        return {tok.strip() for tok in raw.split(",") if tok.strip()}

    @cached_property
    def sentiment_enabled(self) -> bool:
        return bool(self.cryptopanic_api_key)

    @cached_property
    def mode_label(self) -> str:
        """Human-readable label for the current trading mode."""
        if self.paper_trading:
            return "PAPER"
        if self.live_trading_confirmed:
            return "LIVE"
        return "LIVE(unconfirmed)"  # should never reach here — validator blocks it

    def summary(self) -> str:
        """Return a printable configuration summary (no secrets)."""
        lines = [
            "=" * 60,
            "  Mekka Trading — Configuration Summary",
            "=" * 60,
            f"  Mode          : {self.mode_label}",
            f"  Live confirmed: {'YES ⚠️' if self.live_trading_confirmed else 'no'}",
            f"  Network       : {self.hyperliquid_network.upper()}",
            f"  Assets        : {', '.join(self.trading_assets)}",
            f"  Max Position  : {self.max_position_size_pct * 100:.1f}% of equity",
            f"  Max Leverage  : {self.max_leverage}x",
            f"  Max Drawdown  : {self.max_daily_drawdown_pct * 100:.1f}%/day",
            f"  LLM Model     : {self.openai_model}",
            f"  Primary TF    : {self.primary_timeframe}",
            f"  Telegram      : {'enabled' if self.telegram_enabled else 'disabled'}",
            f"  Sentiment     : {'enabled' if self.sentiment_enabled else 'disabled'}",
            f"  Log Level     : {self.log_level}",
            "=" * 60,
        ]
        return "\n".join(lines)


# Module-level singleton — import this everywhere
settings = Settings()

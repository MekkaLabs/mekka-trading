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
    max_daily_drawdown_pct: Annotated[float, Field(gt=0.0, le=1.0)] = Field(
        default=0.10,
        description="Halt trading if daily drawdown exceeds this fraction (0.10 = 10%)",
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
    def sentiment_enabled(self) -> bool:
        return bool(self.cryptopanic_api_key)

    @cached_property
    def mode_label(self) -> str:
        """Human-readable label for the current trading mode."""
        return "PAPER" if self.paper_trading else "LIVE"

    def summary(self) -> str:
        """Return a printable configuration summary (no secrets)."""
        lines = [
            "=" * 60,
            "  Mekka Trading — Configuration Summary",
            "=" * 60,
            f"  Mode          : {self.mode_label}",
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

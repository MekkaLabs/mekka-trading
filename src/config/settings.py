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
    # OpenAI  (optional — falls back to Anthropic if not set)
    # --------------------------------------------------------------------------
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key (sk-...). Leave blank to use Anthropic Claude instead.",
    )
    openai_model: str = Field(
        default="gpt-4o",
        description="Model used by Vision when OpenAI is the active provider",
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
    # Anthropic Claude  (fallback when OpenAI is unavailable)
    # --------------------------------------------------------------------------
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key (sk-ant-...). Used as fallback when OpenAI fails or is not set.",
    )
    llm_prefer_anthropic: bool = Field(
        default=True,
        description=(
            "Quando True (default 2026-06-02), o LLM tenta Anthropic Claude PRIMEIRO "
            "e cai para OpenAI se Claude falhar/estiver ausente. False inverte "
            "(OpenAI primeiro, Claude fallback). A ordem efetiva sempre pula "
            "providers não configurados."
        ),
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-6",
        description="Claude model for Vision fallback (e.g. claude-sonnet-4-6, claude-opus-4-6)",
    )

    # ── Cost-aware LLM routing (B3) ──────────────────────────────────────
    # Quando ativo, agentes de SÍNTESE (DoctorStrange, Thor) usam um modelo
    # mais barato (gpt-4o-mini / Haiku), enquanto agentes de DECISÃO (Vision,
    # VisionCritic) mantêm o modelo principal. Default False = comportamento
    # legado (todos usam openai_model). Ativar reduz custo ~20-40% sem
    # impacto significativo na qualidade da decisão final.
    llm_cost_aware_routing: bool = Field(
        default=False,
        description=(
            "When True, synthesis agents (DoctorStrange, Thor) use a cheaper "
            "LLM model (default gpt-4o-mini / claude-haiku). Vision and other "
            "decision-makers continue on the primary model. Reduces cost without "
            "affecting decision quality. Default False (no behaviour change)."
        ),
    )
    llm_synthesis_model_openai: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model for synthesis tasks (when cost-aware routing enabled)",
    )
    llm_synthesis_model_anthropic: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Anthropic model for synthesis tasks (when cost-aware routing enabled)",
    )
    llm_synthesis_agents: list[str] = Field(
        default_factory=lambda: ["DoctorStrange", "Thor"],
        description=(
            "Agents whose LLM calls are routed to the cheap synthesis model "
            "when llm_cost_aware_routing=True. Match by agent_id (case-sensitive)."
        ),
    )

    # --------------------------------------------------------------------------
    # Hyperliquid
    # --------------------------------------------------------------------------
    # Credentials are optional at the field level so the system can boot with
    # ACTIVE_EXCHANGE=bybit (or binance) without supplying HL keys. The
    # `validate_active_exchange_credentials` model_validator below enforces
    # presence conditionally based on the active exchange.
    hyperliquid_private_key: str = Field(
        default="",
        description="EVM private key for signing Hyperliquid orders (required when ACTIVE_EXCHANGE=hyperliquid)",
    )
    hyperliquid_wallet_address: str = Field(
        default="",
        description="EVM wallet address 0x... (required when ACTIVE_EXCHANGE=hyperliquid)",
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
    bybit_testnet: bool = Field(
        default=True,
        alias="BYBIT_TESTNET",
        description=(
            "When True, Bybit CCXT clients call set_sandbox_mode(True) and route to "
            "testnet endpoints (api-testnet.bybit.com / stream-testnet.bybit.com). "
            "Default True so accidental key reuse never hits mainnet."
        ),
    )
    binance_api_key: str = Field(
        default="",
        description="Binance API key (required when ACTIVE_EXCHANGE=binance)",
    )
    binance_api_secret: str = Field(
        default="",
        description="Binance API secret (required when ACTIVE_EXCHANGE=binance)",
    )
    binance_testnet: bool = Field(
        default=True,
        alias="BINANCE_TESTNET",
        description=(
            "When True, Binance CCXT clients call set_sandbox_mode(True) and route to "
            "testnet endpoints. Default True to match BYBIT_TESTNET safety posture."
        ),
    )
    binance_market_type: Literal["linear", "inverse"] = Field(
        default="linear",
        alias="BINANCE_MARKET_TYPE",
        description=(
            "Binance Futures market type:\n"
            "  - 'linear' (default): USDT-Margined Futures (BTCUSDT, ETHUSDT). "
            "    Settled em USDT; PnL em USD. fapi.binance.com endpoint.\n"
            "  - 'inverse': COIN-Margined Futures (BTCUSD_PERP). Settled em coin "
            "    (BTC, ETH); PnL em coin convertido para USD via mark price. "
            "    dapi.binance.com endpoint.\n"
            "Hot-swap requer reconnect do CCXT client em IronMan (cache invalidation "
            "automática quando setting muda). NÃO mude com posições abertas — "
            "validator do trade_now bloqueia. Affects market_registry.to_ccxt "
            "(symbol formato) e contract_sizer (quantity calculation)."
        ),
    )
    scalp_mainnet_enabled: bool = Field(
        default=False,
        alias="SCALP_MAINNET_ENABLED",
        description=(
            "Hard gate adicional para o Modo Scalp: quando False (default), "
            "qualquer trade em modo='scalp' + paper_trading=False + binance_testnet=False "
            "é BLOQUEADO. Razão: scalp em loop 120s pode explodir custos LLM e "
            "ainda não foi validado em condições mainnet. Setar True só depois "
            "de validar end-to-end em testnet e estar confortável com o gasto."
        ),
    )
    binance_entry_order_type: str = Field(
        default="auto",
        description=(
            "Entry order type for CCXT execution: 'auto' | 'market' | 'limit_ioc'. "
            "'auto' resolves to 'market' on testnet (reliable fills so the full flow "
            "can be tested) and 'limit_ioc' on mainnet (slippage control)."
        ),
    )
    binance_max_entry_slippage_bps: float = Field(
        default=20.0,
        description=(
            "Max slippage (basis points) for a mainnet limit-IOC entry. The entry "
            "limit is priced to CROSS the book by up to this much (buy=ask*(1+bps), "
            "sell=bid*(1-bps)) so it fills reliably while capping slippage. 20 = 0.20%."
        ),
    )
    execution_slippage_alert_bps: float = Field(
        default=30.0,
        ge=0.0,
        description=(
            "Realized entry-slippage threshold (bps) for execution-quality "
            "alerting/learning. After a LIVE fill, IronMan compares the avg fill "
            "price vs the planned entry; if the realized slippage exceeds this, it "
            "logs a WARNING, emits an alert and records a lesson in its journal. "
            "Measurement-only (does not block — the IOC limit already caps placement)."
        ),
    )
    max_entry_price_drift_pct: float = Field(
        default=0.01,
        ge=0.0,
        description=(
            "Guard de decisão obsoleta (NickFury): antes de executar, compara o "
            "preço de mercado atual com signal.entry_price. Se o mercado andou "
            "mais que esta fração (0.01 = 1%) desde a decisão do Vision (ex.: "
            "demora na aprovação Telegram), a entrada é cancelada — a tese/SL/TP "
            "ficaram obsoletos. Set 0 para desabilitar."
        ),
    )
    learning_prune_stale_days: int = Field(
        default=30,
        ge=1,
        description=(
            "Higiene do diário de aprendizado: o Beast poda lições com mais de N "
            "dias sem atualização QUE TAMBÉM sejam nunca-reforçadas e de baixa "
            "confiança (<0.6). Lições reforçadas ou confiáveis são preservadas."
        ),
    )
    learning_loss_escalation_count: int = Field(
        default=5,
        ge=2,
        description=(
            "Quando uma lição de PREJUÍZO recorrente (Cyclops outcome-loss: mesmo "
            "símbolo/lado fechando no stop) atinge este número de reforços, o "
            "operador recebe um alerta Telegram para revisar/pausar o ativo. "
            "Transforma a memória passiva em sinal proativo."
        ),
    )
    max_entry_slippage_estimate_pct: float = Field(
        default=0.02,
        ge=0.0,
        description=(
            "Pre-trade liquidity gate (Batman): blocks the entry when Aquaman's "
            "estimated slippage for the order exceeds this fraction (0.02 = 2%). "
            "A thin book would destroy the R:R. Only blocks when liquidity data is "
            "available (data_available=True); degraded data falls back to the size "
            "penalty. Set 0 to disable the hard gate."
        ),
    )
    mainnet_dry_run: bool = Field(
        default=False,
        description=(
            "Rehearsal mode: when True, the system applies mainnet-style behavior "
            "(Batman hard clamp, limit-IOC marketable entries — never auto→market) "
            "even on testnet, so the operator can validate go-live behavior on "
            "fake money before flipping BINANCE_TESTNET=false. Default False."
        ),
    )
    mainnet_first_week_hard_clamp: bool = Field(
        default=True,
        description=(
            "When True AND running on Binance mainnet (live, non-testnet), Batman "
            "HARD-CLAMPS size to 0.1% and leverage to 2x (the conservative first-week "
            "caps) — not just a warning. Only ever tightens risk. Disable after the "
            "first week once comfortable."
        ),
    )
    phantom_reconciliation_enabled: bool = Field(
        default=True,
        description=(
            "When True (live mode only), IronMan periodically detects positions the DB "
            "thinks are open but the exchange does not have, then inserts a synthetic "
            "close to keep state consistent. Runs at boot and on every monitor cycle. "
            "Bybit/Binance only (Hyperliquid uses different bookkeeping). Audits "
            "PHANTOM_RECONCILED and alerts Telegram WARNING. Disable only when "
            "manually reconciling state."
        ),
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
    max_daily_loss_usd: Annotated[float, Field(ge=0.0)] = Field(
        default=0.0,
        description=(
            "Absolute daily-loss circuit breaker (USD). When > 0 AND today_pnl_usd "
            "<= -max_daily_loss_usd, NickFury engages the kill switch + alerts. "
            "Complements max_daily_drawdown_pct (which is %-based). 0 = disabled. "
            "Mainnet recommended: a conservative absolute floor independent of equity."
        ),
    )
    min_equity_floor_usd: Annotated[float, Field(ge=0.0)] = Field(
        default=0.0,
        description=(
            "M6 (2026-06-01 audit): piso de equity mínimo (USD). Quando > 0, o "
            "preflight de mainnet exige que o equity real da conta esteja acima "
            "deste valor antes de operar live (FAIL se abaixo ou ilegível). "
            "0 = desativado. Read-only; nunca afrouxa nenhum gate."
        ),
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
    # Story 069 — Re-entry cooldown after SL close
    reentry_cooldown_minutes: int = Field(
        default=30,
        ge=0,
        description=(
            "Minutes to block re-entry in a symbol after Cyclops closes it via SL. "
            "Set to 0 to disable. Prevents AI revenge-trading after a loss."
        ),
    )
    # Story 070 — ATR-based position sizing
    atr_sizing_enabled: bool = Field(
        default=True,
        description="Scale position size inversely with 14-period ATR volatility.",
    )
    atr_lookback_candles: int = Field(
        default=14,
        ge=5,
        le=50,
        description="Number of 1h candles used to compute ATR for sizing.",
    )
    atr_target_pct: float = Field(
        default=0.02,
        gt=0.0,
        le=0.20,
        description=(
            "Target ATR% (ATR / price). When current ATR% exceeds this, position size "
            "is scaled down proportionally. Default 2%: BTC typically trades 1.5-3%."
        ),
    )
    atr_min_size_multiplier: float = Field(
        default=0.25,
        gt=0.0,
        le=1.0,
        description="Floor for ATR size multiplier — never reduces size below this fraction.",
    )
    # Modo de Operação — switch RAIZ. Governa APENAS a execução de TRADES.
    # Ver src/config/operation_mode.py.
    #   manual    → operador aprova cada trade via Telegram
    #   automatic → trades auto-executam (gates de risco/kill-switch seguem ativos)
    # MELHORIAS SEMPRE EXIGEM APROVAÇÃO — o modo NÃO as auto-aplica (evita que um
    # clique no botão faça o worker escrever/commitar código sozinho).
    # Default 'manual' = seguro. Trocável em runtime via Telegram (/opmode) —
    # override em data/operation_mode.json tem precedência sobre este default.
    operation_mode: Literal["manual", "automatic"] = Field(
        default="manual",
        description=(
            "Root operation mode — governs TRADE execution only. 'manual' = "
            "operator approves every trade via Telegram. 'automatic' = trades "
            "auto-execute (deterministic safety gates still apply). Improvements "
            "ALWAYS require approval regardless of mode. Default 'manual'."
        ),
    )

    # Story 074 — Telegram Trade Approval
    # NB (2026-06-01): o LIGA/DESLIGA do gate de trade agora é derivado de
    # operation_mode (manual=gate ON, automatic=gate OFF) via
    # operation_mode.requires_trade_approval(). Este campo NÃO liga/desliga
    # mais o gate — fica para compatibilidade de .env e para o timeout
    # (telegram_trade_approval_timeout_s) usado quando o gate ESTÁ ativo.
    telegram_trade_approval_enabled: bool = Field(
        default=True,
        description=(
            "SUPERSEDED by operation_mode (manual=gate ON, automatic=gate OFF). "
            "Kept for .env back-compat; no longer toggles the trade-approval gate. "
            "When the gate is active (manual mode), paper auto-approves on timeout "
            "and live auto-rejects on timeout (safety-first)."
        ),
    )
    telegram_trade_approval_timeout_s: int = Field(
        default=120,
        ge=10,
        le=600,
        description="Seconds to wait for operator response before auto-approve/reject.",
    )

    # Story 075 — Funding Rate Gate
    funding_gate_enabled: bool = Field(
        default=True,
        description=(
            "Enable funding rate gate in Batman. "
            "Blocks/penalizes entries when funding rate signals extreme crowded positioning."
        ),
    )
    funding_long_block_pct: float = Field(
        default=0.10,
        gt=0.0,
        description=(
            "Block LONG entries when 8h funding rate exceeds this % "
            "(e.g. 0.10 = 0.10%/8h ≈ 109%/yr — extremely crowded long)."
        ),
    )
    funding_long_warn_pct: float = Field(
        default=0.05,
        gt=0.0,
        description=(
            "Reduce LONG size 40%% when 8h funding rate exceeds this % "
            "(e.g. 0.05 = 0.05%/8h ≈ 55%/yr — elevated long cost)."
        ),
    )
    funding_short_block_pct: float = Field(
        default=-0.10,
        lt=0.0,
        description=(
            "Block SHORT entries when 8h funding rate is below this % "
            "(e.g. -0.10 = extremely crowded short)."
        ),
    )
    funding_short_warn_pct: float = Field(
        default=-0.05,
        lt=0.0,
        description="Reduce SHORT size 40%% when 8h funding rate is below this %.",
    )

    # Story 076 — Trading Hours Gate
    trading_hours_enabled: bool = Field(
        default=False,
        description=(
            "Only allow new entries within the configured UTC hour window. "
            "Reduces noise during low-liquidity hours (e.g. Asian pre-session)."
        ),
    )
    trading_hours_start_utc: int = Field(
        default=7,
        ge=0,
        le=23,
        description="Earliest UTC hour allowed for new entries (inclusive). Default: 07:00 UTC.",
    )
    trading_hours_end_utc: int = Field(
        default=23,
        ge=0,
        le=23,
        description=(
            "Latest UTC hour allowed for new entries (inclusive). "
            "Default: 23:00 UTC (midnight block = 00:00-06:59 UTC)."
        ),
    )

    # Story 072 — Multi-Timeframe Confluence
    mtf_confluence_enabled: bool = Field(
        default=True,
        description="Enable 4h trend check before entering on lower-timeframe signal.",
    )
    mtf_interval: str = Field(
        default="4h",
        description="Higher timeframe used for confluence check (Hyperliquid interval string).",
    )
    mtf_lookback_candles: int = Field(
        default=30,
        ge=10,
        le=100,
        description="Number of HTF candles to classify the prevailing trend.",
    )
    mtf_reject_on_opposite: bool = Field(
        default=False,
        description=(
            "If True, hard-reject signals that oppose the HTF trend. "
            "If False (default), only apply a 40% size reduction (REDUCED verdict)."
        ),
    )

    # Story 086 — Max trades per symbol per day gate
    max_trades_per_symbol_day: int = Field(
        default=2,
        ge=1,
        description=(
            "Batman gate 3l: Maximum number of FILLED/PAPER trades allowed "
            "for a single symbol within a UTC calendar day. "
            "Set to 99 to effectively disable. Default 2."
        ),
    )

    # Story 091 — Dry-Run Mode
    dry_run_mode: bool = Field(
        default=False,
        description=(
            "When True, the full signal→Batman→approval pipeline runs but "
            "IronMan execution is skipped. Useful for testing strategy changes "
            "without creating real paper positions. Also toggled at runtime "
            "via /dryrun Telegram command (MEKKA_DRY_RUN=1 env var)."
        ),
    )

    # Story 094 — Minimum notional for Telegram trade alerts
    min_alert_notional_usd: float = Field(
        default=50.0,
        ge=0.0,
        description=(
            "Suppress Telegram trade alerts for trades with notional "
            "below this threshold (USD). Default $50. Set 0 to always alert."
        ),
    )

    # Story 096 — Minimum trade notional gate
    min_trade_notional_usd: float = Field(
        default=10.0,
        ge=0.0,
        description=(
            "Batman gate 3m: Reject signals where equity × size_pct × leverage "
            "would produce a notional below this threshold (USD). "
            "Prevents micro-positions that generate fees without meaningful exposure. "
            "Default $10. Set 0 to disable."
        ),
    )

    # Story 100 — Max drawdown per symbol per week
    max_symbol_drawdown_pct: float = Field(
        default=0.05,
        gt=0.0,
        le=1.0,
        description=(
            "Batman gate 3n: Reject new entries in a symbol whose cumulative "
            "realized PnL this week is worse than -(equity × max_symbol_drawdown_pct). "
            "Default 5% of equity. Set to 1.0 to disable."
        ),
    )

    # Story 102 — Max consecutive losses gate (Batman 3o)
    max_consecutive_losses: int = Field(
        default=3,
        ge=1,
        description=(
            "Batman gate 3o: Reject new entries when the last N trades across "
            "all symbols were losses (SL hit). Resets on first TP/win. "
            "Set to a high value (e.g. 99) to disable."
        ),
    )

    # Story 105 — Cyclops partial SL (close half at -0.75R)
    partial_sl_enabled: bool = Field(
        default=False,
        description=(
            "Cyclops gate: close 50% of a position when price crosses -75% "
            "of the SL range (i.e. the position is at -0.75R). "
            "Uses sentinel trade triggered_by='cyclops_partial_sl'."
        ),
    )

    # Story 106 — Directional bias guard (Batman 3p)
    max_same_direction_streak: int = Field(
        default=4,
        ge=1,
        description=(
            "Batman gate 3p: Reject new entries when the last N executed trades "
            "were all in the same direction (all LONG or all SHORT), indicating "
            "directional bias. Set to a high value (e.g. 99) to disable."
        ),
    )

    # Story 110 — Min ATR filter (Batman gate 3q)
    min_atr_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=0.10,
        description=(
            "Batman gate 3q: Reject signals when the symbol's current ATR% "
            "(ATR / price) is below this threshold — indicates a quiet/paused market. "
            "0.0 (default) disables the gate. Example: 0.005 = 0.5% ATR minimum."
        ),
    )

    # Story 247 — Flash divergence size reduction (Batman gate 3r)
    flash_divergence_size_reduction: float = Field(
        default=0.30,
        ge=0.0,
        le=0.80,
        description=(
            "Batman gate 3r: When Flash signals STRONG momentum opposing the trade "
            "direction, reduce position size_pct by this fraction. "
            "0.30 = 30% reduction. 0.0 disables the soft gate."
        ),
    )

    # Story 083 — Auto-TP Ladder (multi-level partial exits)
    tp_ladder_enabled: bool = Field(
        default=False,
        description=(
            "Enable 3-level TP ladder in Cyclops. When True, replaces the "
            "single midpoint scale-out (Story 065) with 3 graduated exits:\n"
            "  TP1 at 1/3 of range → close tp_ladder_tp1_pct of position\n"
            "  TP2 at 2/3 of range → close tp_ladder_tp2_pct of remaining\n"
            "  TP3 at full TP      → close all remaining\n"
            "After TP1, SL moves to breakeven. After TP2, SL trails."
        ),
    )
    tp_ladder_tp1_pct: float = Field(
        default=0.25,
        gt=0.0,
        lt=1.0,
        description="Fraction of position closed at TP ladder level 1 (1/3 of range). Default 25%.",
    )
    tp_ladder_tp2_pct: float = Field(
        default=0.25,
        gt=0.0,
        lt=1.0,
        description=(
            "Fraction of *remaining* position closed at TP ladder level 2 (2/3 of range). "
            "Default 25% of original (33% of remaining 75%)."
        ),
    )

    # Story 080 — Pyramid / Scale-In Entry
    pyramid_enabled: bool = Field(
        default=False,
        description=(
            "Allow adding to an existing profitable position (scale-in / pyramid) "
            "when a new confirming signal arrives. If True, Batman bypasses the "
            "max_open_positions gate for the same symbol when the existing position "
            "is profitable (unrealized_pnl_usd > 0). The added size is capped at "
            "pyramid_max_add_pct of equity."
        ),
    )
    pyramid_max_add_pct: float = Field(
        default=0.01,
        gt=0.0,
        le=0.05,
        description=(
            "Maximum size (fraction of equity) allowed for a scale-in add. "
            "Default 1% of equity — always smaller than the initial position."
        ),
    )
    pyramid_min_profit_pct: float = Field(
        default=0.5,
        ge=0.0,
        description=(
            "Minimum unrealised profit (%) the existing position must show "
            "before a pyramid entry is allowed. Default 0.5%."
        ),
    )

    # Story 071 — Symbol consecutive-SL strike counter + auto-blacklist
    symbol_strike_limit: int = Field(
        default=3,
        ge=1,
        description="Number of consecutive SL hits before a symbol is auto-blacklisted.",
    )
    symbol_blacklist_hours: float = Field(
        default=24.0,
        gt=0.0,
        description="Hours to blacklist a symbol after hitting the consecutive-SL strike limit.",
    )

    # --------------------------------------------------------------------------
    # Timing (seconds)
    # --------------------------------------------------------------------------
    main_loop_interval_seconds: int = Field(
        default=14_400,  # 4 hours
        description="How often the main 4h analysis loop runs",
    )
    testnet_main_loop_interval_seconds: int = Field(
        default=0,
        description=(
            "When > 0 AND running on a testnet, overrides main_loop_interval_seconds "
            "with this (shorter) value so the operator can watch the bot decide/trade "
            "in minutes instead of 4h. Mainnet always uses main_loop_interval_seconds."
        ),
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
    vault_enrichment_enabled: bool = Field(
        default=False,
        description=(
            "Story #72 — Neural graph / Second-brain enrichment. When True, "
            "Vision (and future consumers) augments its LLM prompt with a "
            "short block of relevant vault notes via Jean Grey's recall(). "
            "READ-ONLY: never changes decision path; fail-silent + bounded "
            "latency (1.5s timeout) + cached for 5min. Off by default — "
            "operator must enable explicitly via VAULT_ENRICHMENT_ENABLED=true."
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
    # Vision Reflection Loop (Story 130)
    # --------------------------------------------------------------------------
    vision_reflection_max_rounds: int = Field(
        default=3,
        ge=1,
        le=5,
        description=(
            "Maximum rounds in the Vision↔VisionCritic iterative reflection "
            "loop (AutoGen Reflection pattern). Each round where the critic "
            "returns AMEND or REJECT triggers a Vision revision call. "
            "The loop converges early on ENDORSE. "
            "Set to 1 to restore Story 031 one-shot behavior. "
            "Requires vision_critic_enabled=True to take effect."
        ),
    )

    # --------------------------------------------------------------------------
    # Opportunity Scanner (Story 145) — pre-scan phase before deep analysis
    # --------------------------------------------------------------------------
    opportunity_scan_enabled: bool = Field(
        default=False,
        description=(
            "When True, NickFury runs a lightweight pre-scan before deep Layer 1 "
            "analysis. Symbols are scored by volume spike, RSI extreme, ATR activity, "
            "and EMA momentum. Only the top-N scoring symbols proceed to full analysis. "
            "Set OPPORTUNITY_SCAN_ENABLED=true to activate."
        ),
    )
    opportunity_scan_top_n: int = Field(
        default=3,
        ge=1,
        le=20,
        description=(
            "Maximum number of symbols selected for deep analysis after pre-scan. "
            "When fewer symbols are configured than top_n, all proceed."
        ),
    )
    opportunity_scan_min_score: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Minimum OpportunityScore required to proceed to deep analysis. "
            "0.0 (default) disables score filtering — all non-blacklisted symbols "
            "are considered. Set to e.g. 0.1 to skip flat/quiet markets."
        ),
    )

    # --------------------------------------------------------------------------
    # Mock Realism (Story 144) — paper trading with realistic friction
    # --------------------------------------------------------------------------
    mock_realism_enabled: bool = Field(
        default=False,
        description=(
            "When True and paper_trading=True, IronMan simulates realistic "
            "market friction: random network latency (50-500ms), partial fills "
            "(50-100%% of quantity), and extra randomized slippage (0-3× base). "
            "Useful for stress-testing the pipeline before real capital. "
            "Set MOCK_REALISM_ENABLED=true to activate."
        ),
    )
    mock_realism_latency_min_ms: int = Field(
        default=50,
        ge=0,
        description="Minimum simulated exchange latency in milliseconds.",
    )
    mock_realism_latency_max_ms: int = Field(
        default=500,
        ge=0,
        description="Maximum simulated exchange latency in milliseconds.",
    )
    mock_realism_partial_fill_min_pct: float = Field(
        default=0.5,
        gt=0.0,
        le=1.0,
        description=(
            "Minimum fill ratio for partial fill simulation (0.5 = fills at least 50%%)."
        ),
    )
    mock_realism_extra_slippage_max_bps: float = Field(
        default=10.0,
        ge=0.0,
        description=(
            "Maximum additional randomized slippage in basis points on top of "
            "paper_slippage_bps. Applied uniformly at random in [0, max]."
        ),
    )

    # --------------------------------------------------------------------------
    # DEGRADED_MODE formal (Story 140)
    # --------------------------------------------------------------------------
    degraded_mode_recovery_cycles: int = Field(
        default=5,
        ge=1,
        le=20,
        description=(
            "Number of consecutive successful Vision/LLM cycles required to "
            "exit DEGRADED_MODE and resume normal operation (new entries allowed). "
            "Default 5: after 5 clean cycles in a row the system self-heals."
        ),
    )

    # --------------------------------------------------------------------------
    # Market Regime Gate — Batman adjustments by market regime (Story 148)
    # --------------------------------------------------------------------------
    market_regime_gate_enabled: bool = Field(
        default=True,
        description=(
            "When True, Batman adjusts gates based on MarketRegime (BULL/BEAR/SIDEWAYS/VOLATILE). "
            "In BEAR: leverage capped to bear_regime_max_leverage, LONGs need RSI < bear_long_max_rsi. "
            "In VOLATILE: size multiplied by volatile_regime_size_multiplier."
        ),
    )
    bear_regime_max_leverage: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Max leverage allowed when market regime is BEAR. Default 2x (half of normal 5x).",
    )
    bear_regime_long_max_rsi: float = Field(
        default=40.0,
        ge=10.0,
        le=60.0,
        description=(
            "In BEAR regime, LONG signals are only approved when the signal RSI is below this threshold. "
            "Default 40: only oversold LONG opportunities allowed in a bear market."
        ),
    )
    volatile_regime_size_multiplier: float = Field(
        default=0.7,
        ge=0.1,
        le=1.0,
        description=(
            "Position size multiplier when market regime is VOLATILE. "
            "Default 0.7: reduces position size by 30% during high-volatility regimes."
        ),
    )

    # --------------------------------------------------------------------------
    # Asset Classifier Gate — Batman adjustments by cap tier (Story 149)
    # --------------------------------------------------------------------------
    asset_classifier_gate_enabled: bool = Field(
        default=True,
        description=(
            "When True, Batman applies per-cap-tier leverage limits. "
            "SMALL_CAP → small_cap_max_leverage, MID_CAP → mid_cap_max_leverage, "
            "LARGE_CAP → normal max_leverage."
        ),
    )
    small_cap_max_leverage: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Max leverage for SMALL_CAP assets (default 2x — higher risk, smaller positions).",
    )
    mid_cap_max_leverage: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max leverage for MID_CAP assets (default 3x — moderate risk).",
    )

    # --------------------------------------------------------------------------
    # Agent Step Guard (Story 155 — OpenHands-inspired MAX_ITERATIONS guard)
    # --------------------------------------------------------------------------
    agent_max_step_iterations: int = Field(
        default=100,
        ge=5,
        le=1000,
        description=(
            "Maximum pipeline steps per agent cycle before AgentStepGuard "
            "triggers graceful abort (OpenHands MAX_ITERATIONS pattern). "
            "Prevents infinite loops without crashing the executor."
        ),
    )
    agent_stuck_threshold: int = Field(
        default=5,
        ge=2,
        le=20,
        description=(
            "Number of consecutive identical result hashes that triggers "
            "stuck-loop detection in AgentStepGuard. If the last N steps "
            "all produce the same hash → stuck → graceful abort."
        ),
    )

    # --------------------------------------------------------------------------
    # Circuit Breaker Matrix — gaps (Story 138)
    # --------------------------------------------------------------------------
    llm_error_rate_window: int = Field(
        default=10,
        ge=2,
        le=100,
        description=(
            "Sliding window size for LLM error rate circuit breaker. "
            "Counts the last N LLM calls and measures the fraction that errored."
        ),
    )
    llm_error_rate_threshold: float = Field(
        default=0.5,
        gt=0.0,
        le=1.0,
        description=(
            "If LLM error rate in the sliding window exceeds this fraction, "
            "NickFury enters DEGRADED_MODE (zero new entries). Default 0.5 = 50%."
        ),
    )
    stale_price_window: int = Field(
        default=3,
        ge=2,
        le=10,
        description=(
            "Number of consecutive identical prices before the feed is considered stale. "
            "StalePriceDetector trips when last N prices vary by < stale_price_min_variation_pct."
        ),
    )
    stale_price_min_variation_pct: float = Field(
        default=0.0001,
        gt=0.0,
        description=(
            "Minimum fractional price variation across the stale window. "
            "0.0001 = 0.01% — any change larger than this resets the stale detector."
        ),
    )
    spread_history_window: int = Field(
        default=20,
        ge=3,
        le=200,
        description="Number of ticks in the SpreadBreaker moving average window.",
    )
    spread_max_multiplier: float = Field(
        default=3.0,
        gt=1.0,
        description=(
            "Spread is considered abnormal when current_spread > "
            "spread_max_multiplier × moving_average_spread. "
            "Triggers skip-trade for the current cycle."
        ),
    )

    # --------------------------------------------------------------------------
    # Adaptive Layer 1 Routing (Story 135)
    # --------------------------------------------------------------------------
    layer1_routing_enabled: bool = Field(
        default=False,
        description=(
            "When True, a routing_node after Superman inspects the chart regime "
            "(ATR%) and selects which Layer 1 agents to skip for this cycle. "
            "Skipped agents return None immediately — MarketAnalysis is assembled "
            "from the remaining agents. Set LAYER1_ROUTING_ENABLED=true to activate."
        ),
    )
    layer1_routing_normal_skip: str = Field(
        default="",
        description="CSV of Layer 1 node names to skip in NORMAL volatility regime.",
    )
    layer1_routing_high_skip: str = Field(
        default="flash",
        description="CSV of Layer 1 node names to skip in HIGH volatility regime.",
    )
    layer1_routing_extreme_skip: str = Field(
        default="sentiment,flash",
        description=(
            "CSV of Layer 1 node names to skip in EXTREME volatility regime. "
            "In extreme vol, macro sentiment is less useful than hard price data."
        ),
    )
    layer1_routing_low_skip: str = Field(
        default="onchain,flash",
        description=(
            "CSV of Layer 1 node names to skip in LOW volatility (flat market). "
            "Whale flow and intra-candle momentum add little in consolidation."
        ),
    )

    # --------------------------------------------------------------------------
    # Vision Pre-Reasoning (Story 133)
    # --------------------------------------------------------------------------
    vision_pre_reasoning_enabled: bool = Field(
        default=False,
        description=(
            "When True, Vision makes an extra LLM call before generating the "
            "TradingSignal — asking the model to reflect on signal alignment, "
            "key risks, and preliminary bias (CrewAI Reasoning pattern). "
            "The reflection is injected into the signal prompt as context, "
            "improving decision quality at the cost of ~1 extra LLM call. "
            "Set VISION_PRE_REASONING_ENABLED=true to activate. "
            "Fails silently — Vision proceeds normally if pre-reasoning errors."
        ),
    )

    # --------------------------------------------------------------------------
    # Semantic Memory Composite Scoring (Story 132) + Consolidation (Story 134)
    # --------------------------------------------------------------------------
    semantic_memory_semantic_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Weight applied to the cosine-similarity score in the composite "
            "semantic memory ranking formula. Must sum to ~1.0 with recency and "
            "importance weights (not enforced, but recommended)."
        ),
    )
    semantic_memory_recency_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description=(
            "Weight applied to the exponential recency decay in composite scoring. "
            "Higher values prioritize recent memories over semantically similar older ones."
        ),
    )
    semantic_memory_importance_weight: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description=(
            "Weight applied to the PnL-normalized importance score in composite "
            "scoring. Higher values surface high-PnL trades more prominently."
        ),
    )
    semantic_memory_recency_half_life_days: float = Field(
        default=30.0,
        gt=0.0,
        description=(
            "Half-life in days for the exponential recency decay. "
            "A memory recorded exactly half_life_days ago receives a decay of 0.5. "
            "Smaller values age out memories faster."
        ),
    )
    semantic_memory_consolidation_enabled: bool = Field(
        default=True,
        description=(
            "When True (Story 134), duplicate-like memories are suppressed during "
            "add() and collapsed after warm_up_from_db(). Dedup threshold is "
            "controlled by semantic_memory_consolidation_threshold."
        ),
    )
    semantic_memory_consolidation_threshold: float = Field(
        default=0.92,
        ge=0.0,
        le=1.0,
        description=(
            "Cosine similarity threshold above which a candidate memory is "
            "considered a duplicate and skipped/removed. 0.92 keeps variants "
            "with ≥8% semantic difference."
        ),
    )

    # --------------------------------------------------------------------------
    # Mixture of Agents Vision (Story 131)
    # --------------------------------------------------------------------------
    vision_moa_enabled: bool = Field(
        default=False,
        description=(
            "When True, Vision uses the Mixture of Agents (MoA) pattern: "
            "3 LLMs (GPT-4o, Claude Sonnet, GPT-4o-mini) generate TradingSignal "
            "proposals in parallel, then an orchestrator synthesizes the consensus. "
            "Adds ~2 extra LLM calls per symbol per cycle but increases signal "
            "diversity and reduces single-model bias. "
            "Set VISION_MOA_ENABLED=true to activate. "
            "Requires at least OPENAI_API_KEY or ANTHROPIC_API_KEY."
        ),
    )
    vision_moa_min_proposals: int = Field(
        default=2,
        ge=1,
        le=3,
        description=(
            "Minimum number of successful proposals required for MoA synthesis. "
            "If fewer proposals succeed (due to API failures), VisionMoA falls "
            "back to the single Vision._run() path. Default 2 of 3."
        ),
    )

    # --------------------------------------------------------------------------
    # Multiagent Debate (Story 239-243 — Milestone 39)
    # --------------------------------------------------------------------------
    debate_enabled: bool = Field(
        default=False,
        description=(
            "When True, ProfessorX runs a DebateModerator round between L1 agents "
            "before forwarding MarketAnalysis to Vision. The DebateVerdict is "
            "attached to MarketAnalysis.debate_verdict and logged to audit_log. "
            "Adds 1–2 async rounds of heuristic voting (~50ms overhead). "
            "Set DEBATE_ENABLED=true to activate."
        ),
    )
    debate_max_rounds: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum debate rounds before forcing consensus. Default 2.",
    )
    debate_consensus_threshold: float = Field(
        default=0.60,
        ge=0.50,
        le=1.0,
        description=(
            "Minimum weighted vote fraction to declare consensus and stop early. "
            "Default 0.60 (60%). Lower = stops faster; higher = more rounds."
        ),
    )

    # --------------------------------------------------------------------------
    # Beast — Continuous System Improvement Agent (Story 248)
    # --------------------------------------------------------------------------
    beast_enabled: bool = Field(
        default=False,
        description=(
            "When True, Beast runs periodic system audits and sends improvement "
            "proposals via Telegram. Fully read-only — never modifies the system. "
            "Set BEAST_ENABLED=true to activate."
        ),
    )
    beast_analysis_period_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Number of days Beast looks back when auditing trade and gate stats.",
    )
    beast_schedule_cron: str = Field(
        default="0 9 * * 1",  # every Monday at 09:00 UTC
        description=(
            "Cron expression for Beast's automatic analysis schedule. "
            "Default: every Monday at 09:00 UTC (0 9 * * 1)."
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
        # Allow empty string — Claude fallback will be used instead
        if v == "sk-your-openai-api-key-here":
            return ""  # Treat the example placeholder as "not set"
        return v

    @model_validator(mode="after")
    def _llm_keys_fallback_to_dotenv(self) -> "Settings":
        """Robustez (2026-06-02): uma variável de ambiente VAZIA (ex.:
        ``ANTHROPIC_API_KEY=""`` injetada por outro processo/shell) tem
        precedência sobre o ``.env`` no pydantic e MASCARA a key real
        configurada no arquivo. Aqui, se a key resolvida estiver vazia mas o
        ``.env`` tiver valor não-vazio, usamos o do ``.env``. Fail-silent."""
        try:
            from pathlib import Path as _P  # noqa: WPS433

            from dotenv import dotenv_values  # noqa: WPS433

            env_path = _P(__file__).resolve().parents[2] / ".env"
            if not env_path.exists():
                return self
            vals = dotenv_values(str(env_path))
            for field_name, env_name in (
                ("anthropic_api_key", "ANTHROPIC_API_KEY"),
                ("openai_api_key", "OPENAI_API_KEY"),
            ):
                cur = (getattr(self, field_name, "") or "").strip()
                file_val = (vals.get(env_name) or "").strip()
                if not cur and file_val:
                    object.__setattr__(self, field_name, file_val)
        except Exception:  # noqa: BLE001
            pass  # nunca quebra a inicialização por causa disso
        return self

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

    @model_validator(mode="after")
    def validate_active_exchange_credentials(self) -> "Settings":
        """
        Enforce credentials based on ACTIVE_EXCHANGE.

        Each exchange requires its own credentials only when it is the active
        one. This allows boot with ACTIVE_EXCHANGE=bybit without supplying HL
        keys (and vice-versa). Paper mode still requires credentials because
        Superman (market data) and IronMan still build CCXT/HL clients to
        fetch live prices even when execution is simulated.
        """
        ex = self.active_exchange
        if ex == "hyperliquid":
            missing = [
                k for k, v in {
                    "HYPERLIQUID_PRIVATE_KEY": self.hyperliquid_private_key,
                    "HYPERLIQUID_WALLET_ADDRESS": self.hyperliquid_wallet_address,
                }.items() if not v
            ]
            if missing:
                raise ValueError(
                    f"ACTIVE_EXCHANGE=hyperliquid requires: {', '.join(missing)}. "
                    "Either set them in .env or change ACTIVE_EXCHANGE."
                )
        elif ex == "bybit":
            missing = [
                k for k, v in {
                    "BYBIT_API_KEY": self.bybit_api_key,
                    "BYBIT_API_SECRET": self.bybit_api_secret,
                }.items() if not v
            ]
            if missing:
                raise ValueError(
                    f"ACTIVE_EXCHANGE=bybit requires: {', '.join(missing)}. "
                    "Generate testnet keys at https://testnet.bybit.com and add to .env."
                )
        elif ex == "binance":
            missing = [
                k for k, v in {
                    "BINANCE_API_KEY": self.binance_api_key,
                    "BINANCE_API_SECRET": self.binance_api_secret,
                }.items() if not v
            ]
            if missing:
                raise ValueError(
                    f"ACTIVE_EXCHANGE=binance requires: {', '.join(missing)}."
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

    def exchange_is_testnet(self, exchange_id: str | None = None) -> bool:
        """Resolve testnet/mainnet POR exchange (não atrelado ao Hyperliquid).

        H5 fix (2026-06-01 audit): `is_mainnet` só olha `hyperliquid_network`.
        Operador em Binance mainnet com `hyperliquid_network=testnet` (default)
        fazia leitores de saldo/posições (PortfolioManager) cair em sandbox da
        Binance TESTNET enquanto o IronMan executava na MAINNET → equity fictício
        inflando sizing. Este helper é a fonte única de verdade de network por
        exchange e deve ser usado em TODOS os clients CCXT.
        """
        ex = (exchange_id or self.active_exchange or "").lower()
        if ex == "binance":
            return bool(self.binance_testnet)
        if ex == "bybit":
            return bool(self.bybit_testnet)
        if ex == "hyperliquid":
            return self.hyperliquid_network != "mainnet"
        # Desconhecido: conservador → assume testnet (nunca presumir mainnet).
        return True

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
        # Network label depends on the active exchange so operators always
        # see what they are actually pointed at (e.g. Bybit testnet vs HL mainnet).
        if self.active_exchange == "hyperliquid":
            net = self.hyperliquid_network.upper()
        elif self.active_exchange == "bybit":
            net = "TESTNET" if self.bybit_testnet else "MAINNET"
        elif self.active_exchange == "binance":
            net = "TESTNET" if self.binance_testnet else "MAINNET"
        else:  # pragma: no cover — Literal narrows this out
            net = "UNKNOWN"

        lines = [
            "=" * 60,
            "  Mekka Trading — Configuration Summary",
            "=" * 60,
            f"  Mode          : {self.mode_label}",
            f"  Live confirmed: {'YES ⚠️' if self.live_trading_confirmed else 'no'}",
            f"  Exchange      : {self.active_exchange.upper()}",
            f"  Network       : {net}",
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

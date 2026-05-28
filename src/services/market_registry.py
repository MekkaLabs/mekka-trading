"""
src/services/market_registry.py
===============================
Symbol normalisation across exchanges.

Background
----------
Mekka uses *bare* symbols internally (``BTC``, ``ETH``, ``SOL``) because that
is what humans say, what the LLM emits, and what shows up in Telegram
alerts. But each exchange speaks a different wire format:

    Mekka       Hyperliquid       Bybit/Binance (CCXT perp)   Bybit (wire/V5)
    -----       -----------       -------------------------    ---------------
    BTC         BTC               BTC/USDT:USDT                 BTCUSDT
                                  BTC/USDC:USDC (HL via CCXT)

Before this module, every conversion was inlined at the call site:
``ccxt_symbol = f"{symbol}/USDT:USDT"`` lived in ``iron_man.py``,
``superman.py``, ``positions_provider.py`` and ``price_feed.py`` — four
copies that disagreed on edge cases (HL via CCXT uses USDC; some legacy
.env values arrived as ``BTC-USD``; Bybit V5 strips slashes).

This module centralises the four conversions plus normalisation of
user-provided input:

  - ``to_mekka(any_format) -> "BTC"``      — bare canonical
  - ``to_ccxt(mekka, exchange) -> "BTC/USDT:USDT"`` — unified CCXT
  - ``to_bybit_wire(mekka) -> "BTCUSDT"``  — Bybit V5 raw
  - ``to_hyperliquid(mekka) -> "BTC"``     — HL native

The functions are deliberately tiny and pure so unit tests are cheap and
all call sites can adopt them by name without dragging behaviour
changes.
"""

from __future__ import annotations

from typing import Literal

# Bare canonical symbols Mekka uses internally. Lowercase variations,
# quote-suffix variations and dash-quote variations all collapse to this.
# We do NOT validate against a whitelist here — that is risk-engine's job.
# This module only knows about *format*.

ExchangeId = Literal["hyperliquid", "bybit", "binance"]


# ---------------------------------------------------------------------------
# Normalisation INTO the Mekka canonical form
# ---------------------------------------------------------------------------

def to_mekka(raw: str) -> str:
    """Collapse any reasonable input to a bare uppercase symbol.

    Accepts (case-insensitive):
      - ``BTC``           → ``BTC``
      - ``btc``           → ``BTC``
      - ``BTC/USDT:USDT`` → ``BTC``  (CCXT perp linear)
      - ``BTC/USDC:USDC`` → ``BTC``  (HL via CCXT)
      - ``BTC/USDT``      → ``BTC``  (spot — defensive, we never trade spot)
      - ``BTCUSDT``       → ``BTC``  (Bybit V5 wire)
      - ``BTCUSDC``       → ``BTC``  (HL V5 wire equivalent)
      - ``BTC-USD``       → ``BTC``  (legacy Hyperliquid-mock or .env typo)
      - ``BTC-PERP``      → ``BTC``  (FTX-era legacy)

    Empty/whitespace input returns ``""``. Whitespace inside the string is
    trimmed but NOT stripped between characters; we never re-segment an
    already-segmented symbol.
    """
    if not raw:
        return ""
    s = raw.strip().upper()
    if not s:
        return ""

    # CCXT unified perp: "BTC/USDT:USDT" or "BTC/USDC:USDC" → split on '/'.
    if "/" in s:
        s = s.split("/", 1)[0]
        return s

    # Dash separators: "BTC-USD", "BTC-PERP".
    if "-" in s:
        s = s.split("-", 1)[0]
        return s

    # Glued quote: "BTCUSDT", "BTCUSDC", "ETHUSDT" → strip the suffix.
    # Order matters: try the LONGEST suffix first. Otherwise "BTCBUSD"
    # would match the 3-char "USD" suffix and resolve to "BTCB" (wrong)
    # instead of "BTC" (correct). The list below is sorted by length DESC
    # for that reason — any future addition must preserve the order.
    for suffix in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(suffix) and len(s) > len(suffix):
            return s[: -len(suffix)]

    return s


# ---------------------------------------------------------------------------
# Conversion OUT to each exchange's native format
# ---------------------------------------------------------------------------

def to_ccxt(
    mekka_symbol: str,
    exchange: ExchangeId,
    market_type: str = "linear",
) -> str:
    """Bare Mekka symbol → CCXT unified perp symbol for the given exchange.

    Behaviour per exchange:
      - ``hyperliquid``: USDC-margined perp → ``BTC/USDC:USDC``
      - ``bybit``      : USDT-margined perp → ``BTC/USDT:USDT``
      - ``binance`` + ``linear`` (USDT-M):  ``BTC/USDT:USDT``
      - ``binance`` + ``inverse`` (COIN-M): ``BTC/USD:BTC`` (coin-settled)

    Args:
        mekka_symbol: bare ou qualquer formato aceito por ``to_mekka``.
        exchange: hyperliquid | bybit | binance.
        market_type: "linear" (default) ou "inverse" — só afeta binance hoje.
            Default linear preserva backward-compat com todos os callers
            que passam apenas 2 args. Reservado para futuro Bybit inverse.

    If the caller passes something that is not bare (e.g. already
    "BTC/USDT:USDT") we normalise first so the function is idempotent —
    chain-calling ``to_ccxt(to_ccxt(x, ex), ex)`` returns the same thing
    as ``to_ccxt(x, ex)``.
    """
    coin = to_mekka(mekka_symbol)
    if not coin:
        return ""
    if exchange == "hyperliquid":
        return f"{coin}/USDC:USDC"
    # Binance suporta dois market types — COIN-M usa formato inverse.
    if exchange == "binance" and market_type == "inverse":
        # CCXT COIN-M symbol: settle currency é o coin (não USDT)
        return f"{coin}/USD:{coin}"
    # Bybit linear and Binance linear use USDT-margined perp.
    return f"{coin}/USDT:USDT"


def to_bybit_wire(mekka_symbol: str) -> str:
    """Bare Mekka symbol → Bybit V5 wire format (no slash, USDT suffix).

    Used by:
      - ``BybitPriceFeed`` subscription topics: ``tickers.BTCUSDT``
      - any direct REST V5 calls that bypass CCXT
    """
    coin = to_mekka(mekka_symbol)
    if not coin:
        return ""
    return f"{coin}USDT"


def to_hyperliquid(mekka_symbol: str) -> str:
    """Bare Mekka symbol → Hyperliquid native (which is just bare uppercase).

    Hyperliquid's REST/WS APIs accept the bare coin directly, so this
    function exists purely for symmetry with ``to_ccxt`` / ``to_bybit_wire``.
    It also normalises whatever it's given so callers can pass any input
    without thinking.
    """
    return to_mekka(mekka_symbol)


# ---------------------------------------------------------------------------
# Convenience: pick the right "native" representation for the active exchange
# ---------------------------------------------------------------------------

def to_native(mekka_symbol: str, exchange: ExchangeId) -> str:
    """Return the symbol in the *native* format for the given exchange.

    Native means: what that exchange's most common API consumes directly.
      - hyperliquid → bare (``BTC``)
      - bybit       → V5 wire (``BTCUSDT``)
      - binance     → CCXT perp (``BTC/USDT:USDT``)  -- Binance has multiple
                       APIs; we standardise on the CCXT-compatible form
                       since Mekka touches Binance only through CCXT today.
    """
    if exchange == "hyperliquid":
        return to_hyperliquid(mekka_symbol)
    if exchange == "bybit":
        return to_bybit_wire(mekka_symbol)
    return to_ccxt(mekka_symbol, exchange)

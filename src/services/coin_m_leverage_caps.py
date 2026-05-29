"""
src/services/coin_m_leverage_caps.py
=====================================
COIN-2 (2026-05-29) — Per-symbol leverage caps em Binance COIN-M Futures.

ANTES: Batman validava `max_leverage` global (ex: 20x). Binance COIN-M impõe
caps por símbolo (BTCUSD_PERP 125x, ETHUSD_PERP 100x, altcoins 25-50x). Se
operador pedisse 30x em altcoin COIN-M, a request CCXT seria rejeitada pelo
exchange — operador via "execution failed" sem entender por quê.

DEPOIS: helper retorna o cap máximo permitido pelo Binance COIN-M para um
símbolo. Caller (manual_signal builder, dashboard, ou audit gate) consulta
e aplica `min(leverage_pedido, cap_coin_m)`.

Não substitui Batman — é uma primeira camada barata para mensagem clara.

Fonte: Binance Futures docs (atualizadas 2026-Q1). Caps conservadores —
quando em dúvida, retorna o limite mais baixo da tier inicial.
"""

from __future__ import annotations

from typing import Optional


# Caps por símbolo base (sem USD/USDT/USDC sufixo).
# Valores conservadores (tier 1 inicial) — Binance permite mais com
# notional grande, mas isso é raro em scalp.
COIN_M_LEVERAGE_CAPS: dict[str, int] = {
    # Top tier
    "BTC": 125,
    "ETH": 100,
    # Mid tier
    "BNB": 75,
    "SOL": 50,
    "XRP": 50,
    "DOGE": 50,
    # Lower tier (altcoins comuns em COIN-M)
    "AVAX": 50,
    "MATIC": 50,
    "DOT": 50,
    "LTC": 75,
    "BCH": 75,
    "LINK": 50,
    "ADA": 50,
    "TRX": 50,
    "ATOM": 25,
    # Fallback safe — qualquer símbolo desconhecido
}

# Default conservador para símbolos não mapeados
DEFAULT_INVERSE_CAP = 25


def cap_for_symbol(symbol: str, market_type: str = "linear") -> Optional[int]:
    """Retorna o leverage cap para um símbolo no mercado dado.

    Args:
        symbol: símbolo base (BTC, ETH, etc) — case-insensitive.
        market_type: "linear" (USDT-M) ou "inverse" (COIN-M).

    Returns:
        Cap em int (ex: 125 para BTC inverse), ou None quando market_type
        é "linear" (USDT-M tem caps similares mas Batman usa o global —
        mantém None pra não interferir no caminho USDT-M existente).
    """
    if market_type != "inverse":
        return None

    if not symbol or not isinstance(symbol, str):
        return DEFAULT_INVERSE_CAP

    base = symbol.strip().upper()
    # Remove sufixos comuns
    for suffix in ("USD_PERP", "USDT", "USDC", "USD", "PERP", "_PERP"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    base = base.rstrip("-_")

    return COIN_M_LEVERAGE_CAPS.get(base, DEFAULT_INVERSE_CAP)


def clamp_leverage(
    requested: int,
    symbol: str,
    market_type: str = "linear",
) -> tuple[int, Optional[str]]:
    """Clamp leverage ao máximo permitido COIN-M. Retorna (effective, warning).

    Em USDT-M (linear), retorna (requested, None) — fora do escopo COIN-2.
    Em COIN-M (inverse), aplica `min(requested, cap_for_symbol)`.

    Args:
        requested: leverage pedido pelo operador.
        symbol: símbolo do trade.
        market_type: "linear" ou "inverse".

    Returns:
        (effective_leverage, warning_message_or_None).
    """
    if market_type != "inverse":
        return requested, None

    cap = cap_for_symbol(symbol, market_type=market_type)
    if cap is None:
        return requested, None

    if requested > cap:
        return cap, (
            f"leverage {requested}x acima do cap COIN-M para {symbol} "
            f"({cap}x) — clamped"
        )
    return requested, None

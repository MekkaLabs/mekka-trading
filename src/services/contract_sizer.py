"""
src/services/contract_sizer.py
================================
Helper para converter notional (em USD) em quantity/contracts para placement
de ordens. Necessário porque USDT-M e COIN-M têm cálculos diferentes:

USDT-M (linear):
  quantity (in coin) = notional_usd / mark_price
  Ex: $1000 a $50,000 → 0.02 BTC

COIN-M (inverse):
  contracts = notional_usd / contract_size
  contract_size = USD por contrato (BTCUSD_PERP = $100/contract, ETHUSD_PERP = $10)
  Ex: $1000 / $100 = 10 contracts

Hard rules:
- Funções puras (sem I/O).
- Fail-loud: ValueError em inputs inválidos (mark_price <= 0, etc).
- Defaults conservadores (contract_size=100 = BTC default Binance).
- Round half-down para evitar leverage acidental por arredondamento.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

MarketType = Literal["linear", "inverse"]


# Contract sizes padrão Binance COIN-M Futures
# Fonte: https://www.binance.com/en/futures/trading-rules/quarterly
# Atualizar se Binance mudar specs.
DEFAULT_CONTRACT_SIZES_USD: dict[str, float] = {
    "BTC": 100.0,    # BTCUSD_PERP = $100/contract
    "ETH": 10.0,     # ETHUSD_PERP = $10/contract
    "BNB": 10.0,
    "ADA": 10.0,
    "XRP": 10.0,
    "DOT": 10.0,
    "LINK": 10.0,
    "DOGE": 10.0,
    "SOL": 10.0,
    "LTC": 10.0,
    "BCH": 10.0,
}


@dataclass
class SizeComputation:
    """Resultado do cálculo de tamanho."""

    quantity: float          # quantidade nativa do mercado (BTC pra linear, contracts pra inverse)
    notional_usd: float      # valor em USD que essa qty representa (sanity check)
    market_type: str
    contract_size: float | None  # None para linear; valor em USD para inverse
    rounded: bool            # True se hub round_down foi aplicado


def get_contract_size(coin: str, override: float | None = None) -> float:
    """
    Retorna contract size em USD para um coin no Binance COIN-M.
    Use override quando spec do mercado for diferente do default.
    """
    if override is not None:
        if override <= 0:
            raise ValueError(f"contract_size override must be > 0, got {override}")
        return float(override)
    coin_u = (coin or "").strip().upper()
    if coin_u in DEFAULT_CONTRACT_SIZES_USD:
        return DEFAULT_CONTRACT_SIZES_USD[coin_u]
    # Default conservador para coins desconhecidos = $10 (mesma que altcoins)
    return 10.0


# P1-6 (2026-05-28 audit): step_size por coin — defaults mais precisos
# que 0.001 (que perdia até 5% do notional em BTC). Valores baseados nos
# tick sizes reais da Binance Futures (USDT-M) para os principais ativos.
DEFAULT_STEP_SIZE_BY_COIN: dict[str, float] = {
    "BTC": 0.001,    # Binance BTCUSDT: stepSize 0.001
    "ETH": 0.001,    # Binance ETHUSDT: stepSize 0.001
    "SOL": 0.01,     # Binance SOLUSDT: stepSize 0.01
    "BNB": 0.01,     # Binance BNBUSDT: stepSize 0.01
    "LINK": 0.01,    # Binance LINKUSDT: stepSize 0.01
    "AVAX": 0.01,
    "MATIC": 1.0,
    "ADA": 1.0,
    "DOGE": 1.0,
    "XRP": 1.0,
}


def get_step_size(coin: str, override: float | None = None) -> float:
    """Resolve step size pro coin. None ou desconhecido → 0.001 (BTC-like)."""
    if override is not None:
        return override
    return DEFAULT_STEP_SIZE_BY_COIN.get((coin or "").upper(), 0.001)


def compute_size(
    notional_usd: float,
    mark_price: float,
    market_type: MarketType,
    coin: str = "",
    contract_size_override: float | None = None,
    step_size: float | None = None,
) -> SizeComputation:
    """
    Converte notional USD em quantity nativa do mercado.

    Args:
        notional_usd: valor em USD que queremos abrir como notional total
        mark_price: preço atual do ativo (USD por unidade)
        market_type: "linear" (USDT-M) ou "inverse" (COIN-M)
        coin: ticker bare (BTC, ETH, etc) — só usado em inverse
        contract_size_override: bypass do default (raro; só pra testes)
        step_size: mínimo incremento da exchange (default 0.001)

    Returns:
        SizeComputation com quantity calculada, notional resultante (sanity),
        e contract_size usado (None em linear).

    Raises:
        ValueError: se notional_usd <= 0, mark_price <= 0, ou market_type inválido.
    """
    if notional_usd <= 0:
        raise ValueError(f"notional_usd must be > 0, got {notional_usd}")
    if mark_price <= 0:
        raise ValueError(f"mark_price must be > 0, got {mark_price}")
    if market_type not in ("linear", "inverse"):
        raise ValueError(f"market_type must be 'linear' or 'inverse', got {market_type!r}")

    if market_type == "linear":
        # quantity em coin = notional_usd / mark_price
        raw_qty = notional_usd / mark_price
        # P1-6 fix: step_size resolvido por coin. Default antigo 0.001
        # perdia ~5% em BTC quando notional pequeno. Per-coin defaults
        # baseados em tick sizes reais da Binance Futures.
        effective_step = (
            step_size if step_size is not None else get_step_size(coin)
        )
        # Round down ao step_size pra não exceder notional
        rounded_qty = _round_down(raw_qty, effective_step)
        rounded = rounded_qty < raw_qty
        return SizeComputation(
            quantity=rounded_qty,
            notional_usd=rounded_qty * mark_price,
            market_type="linear",
            contract_size=None,
            rounded=rounded,
        )

    # inverse (COIN-M)
    contract_size = get_contract_size(coin, contract_size_override)
    raw_contracts = notional_usd / contract_size
    # COIN-M contracts são inteiros (integer)
    int_contracts = math.floor(raw_contracts)
    rounded = int_contracts < raw_contracts
    actual_notional = int_contracts * contract_size
    return SizeComputation(
        quantity=float(int_contracts),
        notional_usd=actual_notional,
        market_type="inverse",
        contract_size=contract_size,
        rounded=rounded,
    )


def _round_down(value: float, step: float) -> float:
    """Round down `value` ao múltiplo mais próximo de `step`."""
    if step <= 0:
        return value
    return math.floor(value / step) * step


# ---------------------------------------------------------------------------
# Convenience: convert PnL between quote (COIN-M coin) and USD
# ---------------------------------------------------------------------------


def pnl_quote_to_usd(pnl_quote: float, quote_currency: str, mark_price_usd: float) -> float:
    """
    Converte PnL no quote currency (BTC, ETH) para USD usando mark price.
    Usado em COIN-M onde PnL realizado pela exchange vem em coin.

    Args:
        pnl_quote: PnL no quote (ex: 0.0001 BTC)
        quote_currency: ticker do quote (BTC, ETH, USDT, USD)
        mark_price_usd: preço USD do quote (irrelevante para USDT/USD)

    Returns:
        PnL em USD.
    """
    if quote_currency.upper() in ("USDT", "USD", "USDC", "BUSD"):
        return float(pnl_quote)
    if mark_price_usd <= 0:
        return 0.0
    return float(pnl_quote) * float(mark_price_usd)

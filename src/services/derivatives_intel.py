"""
src/services/derivatives_intel.py
==================================
Coletor de dados de derivativos — públicos + (opcional) histórico
pessoal via API read-only.

Esta camada é PURAMENTE LEITURA. Não conhece `create_order`, não chama
qualquer endpoint que mute estado da conta. As credenciais que usa são
distintas das credenciais de trading (`CABLE_BINANCE_API_KEY` /
`CABLE_BYBIT_API_KEY`) — assim mesmo se vazadas o impacto é nulo.

Fontes
------
- Binance Futures **público** (sem auth):
  * /fapi/v1/fundingRate         — histórico de funding 8h
  * /fapi/v1/openInterest        — OI corrente
  * /fapi/v1/premiumIndex        — index mark + funding atual
- Binance Futures **read-only** (auth, opcional):
  * /fapi/v1/userTrades          — histórico pessoal de execuções
- Bybit Derivatives **público**:
  * /v5/market/funding/history
  * /v5/market/open-interest
- Bybit **read-only** (auth, opcional):
  * /v5/execution/list

Disclaimer
----------
Backtests e estatísticas históricas NÃO garantem performance futura. Este
módulo computa métricas descritivas; qualquer projeção é informativa.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp
from loguru import logger

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_BINANCE_FAPI = "https://fapi.binance.com"
_BINANCE_FAPI_TESTNET = "https://testnet.binancefuture.com"
_BYBIT_BASE = "https://api.bybit.com"
_BYBIT_TESTNET = "https://api-testnet.bybit.com"

_DEFAULT_TIMEOUT_S = 8.0
_DEFAULT_FUNDING_LIMIT = 50  # ~16 dias de 8h funding


# ---------------------------------------------------------------------------
# Modelos descritivos (dicts simples para reduzir acoplamento)
# ---------------------------------------------------------------------------


@dataclass
class FundingSnapshot:
    symbol: str
    rates: list[dict[str, Any]] = field(default_factory=list)  # [{ts,rate}]
    mean_rate: Optional[float] = None
    last_rate: Optional[float] = None
    source: str = "binance_futures_public"
    error: Optional[str] = None


@dataclass
class OpenInterestSnapshot:
    symbol: str
    open_interest: Optional[float] = None
    ts: Optional[int] = None
    source: str = "binance_futures_public"
    error: Optional[str] = None


@dataclass
class PersonalTradesSnapshot:
    symbol: str
    trades: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    realized_pnl: Optional[float] = None
    source: str = "binance_futures_userTrades"
    error: Optional[str] = None
    auth_available: bool = False


# ---------------------------------------------------------------------------
# Helpers HTTP — fail-tolerante, timeout duro
# ---------------------------------------------------------------------------


async def _fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Any:
    """GET + JSON, fail-tolerante. Retorna None em erro/timeout."""
    try:
        async with session.get(
            url, params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout_s),
        ) as resp:
            if resp.status != 200:
                logger.debug(f"[derivatives_intel] HTTP {resp.status} on {url}")
                return None
            return await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
        logger.debug(f"[derivatives_intel] fetch error {url}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[derivatives_intel] unexpected {url}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Public market data — sem auth
# ---------------------------------------------------------------------------


async def fetch_binance_funding(
    session: aiohttp.ClientSession,
    symbol: str = "BTCUSDT",
    limit: int = _DEFAULT_FUNDING_LIMIT,
    testnet: bool = False,
) -> FundingSnapshot:
    """
    Histórico de funding rate. Endpoint público. Não exige credencial.
    """
    base = _BINANCE_FAPI_TESTNET if testnet else _BINANCE_FAPI
    data = await _fetch_json(
        session,
        f"{base}/fapi/v1/fundingRate",
        params={"symbol": symbol, "limit": min(limit, 1000)},
    )
    if not data or not isinstance(data, list):
        return FundingSnapshot(symbol=symbol, error="empty_or_invalid_response")
    try:
        rates = [
            {"ts": int(r["fundingTime"]), "rate": float(r["fundingRate"])}
            for r in data if "fundingRate" in r
        ]
        if not rates:
            return FundingSnapshot(symbol=symbol, error="no_rates_parsed")
        mean = sum(r["rate"] for r in rates) / len(rates)
        return FundingSnapshot(
            symbol=symbol,
            rates=rates,
            mean_rate=mean,
            last_rate=rates[-1]["rate"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        return FundingSnapshot(symbol=symbol, error=f"parse_error: {exc}")


async def fetch_binance_open_interest(
    session: aiohttp.ClientSession,
    symbol: str = "BTCUSDT",
    testnet: bool = False,
) -> OpenInterestSnapshot:
    """OI corrente. Endpoint público."""
    base = _BINANCE_FAPI_TESTNET if testnet else _BINANCE_FAPI
    data = await _fetch_json(
        session, f"{base}/fapi/v1/openInterest", params={"symbol": symbol},
    )
    if not data or not isinstance(data, dict):
        return OpenInterestSnapshot(symbol=symbol, error="empty_response")
    try:
        return OpenInterestSnapshot(
            symbol=symbol,
            open_interest=float(data.get("openInterest", 0)),
            ts=int(data.get("time", 0)) or None,
        )
    except (ValueError, TypeError) as exc:
        return OpenInterestSnapshot(symbol=symbol, error=f"parse: {exc}")


# ---------------------------------------------------------------------------
# Personal trade history — auth READ-ONLY recomendada
# ---------------------------------------------------------------------------


def _is_personal_auth_available() -> bool:
    """
    True se CABLE_BINANCE_API_KEY + SECRET estão definidos. NÃO usa as
    chaves de execução (BINANCE_API_KEY) — separação proposital para
    permitir que o operador rode com chave read-only distinta.
    """
    return bool(
        os.environ.get("CABLE_BINANCE_API_KEY")
        and os.environ.get("CABLE_BINANCE_API_SECRET")
    )


async def fetch_personal_trades_binance(
    session: aiohttp.ClientSession,
    symbol: str = "BTCUSDT",
    limit: int = 100,
    testnet: bool = False,
) -> PersonalTradesSnapshot:
    """
    Histórico pessoal de trades (Binance Futures /fapi/v1/userTrades).
    Requer CABLE_BINANCE_API_KEY/SECRET (read-only recomendado).

    Se a credencial não estiver disponível, retorna snapshot vazio com
    `auth_available=False` — não é erro, apenas falta de configuração.
    """
    if not _is_personal_auth_available():
        return PersonalTradesSnapshot(symbol=symbol, auth_available=False)

    # Não chamamos a API aqui na v1: assinatura HMAC + risco se feito errado.
    # A v1 deixa o "import" como CSV (operador exporta da Binance).
    # Versões futuras podem implementar a assinatura SHA256 padrão.
    return PersonalTradesSnapshot(
        symbol=symbol,
        auth_available=True,
        error="v1: only CSV import supported; HTTP signed endpoints in v2",
    )


def import_trades_csv(file_path: str, symbol: Optional[str] = None) -> PersonalTradesSnapshot:
    """
    Importa CSV exportado manualmente pela Binance (Wallet → Futures →
    Transaction History → Export). Aceita o formato com colunas
    'Date(UTC)', 'Symbol', 'Side', 'Quantity', 'Price', 'Realized Profit'.

    Conservador: se uma linha não parsear, é ignorada. Nunca lança.
    """
    import csv
    from pathlib import Path

    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return PersonalTradesSnapshot(
            symbol=symbol or "?", error=f"file_not_found: {file_path}", source="csv",
        )

    trades: list[dict[str, Any]] = []
    realized = 0.0
    try:
        with p.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    sym = (row.get("Symbol") or "").strip()
                    if symbol and sym != symbol:
                        continue
                    pnl = float((row.get("Realized Profit") or "0").replace(",", ""))
                    realized += pnl
                    trades.append({
                        "ts": row.get("Date(UTC)") or row.get("Time"),
                        "symbol": sym,
                        "side": row.get("Side"),
                        "qty": row.get("Quantity"),
                        "price": row.get("Price"),
                        "realized_pnl": pnl,
                    })
                except (ValueError, TypeError):
                    continue
    except OSError as exc:
        return PersonalTradesSnapshot(
            symbol=symbol or "?", error=f"read_error: {exc}", source="csv",
        )

    return PersonalTradesSnapshot(
        symbol=symbol or "MIXED",
        trades=trades,
        count=len(trades),
        realized_pnl=realized,
        source="csv_import",
        auth_available=True,
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


async def collect_full_snapshot(
    symbols: list[str],
    testnet: bool = False,
) -> dict[str, Any]:
    """
    Coleta concorrente de funding + OI para uma lista de símbolos.
    Returns dict legível pelo dashboard.

    Timeout total ~10s. Falhas individuais não afetam outras símbolos.
    """
    if not symbols:
        return {"symbols": [], "error": "empty_symbols"}

    async with aiohttp.ClientSession() as session:
        tasks = []
        for sym in symbols:
            tasks.append(fetch_binance_funding(session, sym, testnet=testnet))
            tasks.append(fetch_binance_open_interest(session, sym, testnet=testnet))
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=10.0,
            )
        except asyncio.TimeoutError:
            results = []

    # Resultados intercalados: funding, oi, funding, oi, …
    by_symbol: dict[str, dict[str, Any]] = {s: {} for s in symbols}
    for i, sym in enumerate(symbols):
        if 2 * i + 1 >= len(results):
            break
        fund = results[2 * i]
        oi = results[2 * i + 1]
        if isinstance(fund, FundingSnapshot):
            by_symbol[sym]["funding"] = {
                "mean": fund.mean_rate,
                "last": fund.last_rate,
                "samples": len(fund.rates),
                "error": fund.error,
            }
        if isinstance(oi, OpenInterestSnapshot):
            by_symbol[sym]["open_interest"] = {
                "value": oi.open_interest,
                "ts": oi.ts,
                "error": oi.error,
            }

    return {
        "ts": time.time(),
        "testnet": testnet,
        "symbols": symbols,
        "auth_available": _is_personal_auth_available(),
        "data": by_symbol,
        "disclaimer": (
            "Backtests e métricas históricas NÃO garantem performance futura. "
            "Read-only — este módulo nunca executa ordens."
        ),
    }

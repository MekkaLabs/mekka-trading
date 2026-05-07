"""
src/agents/portfolio_manager.py
================================
Portfolio Manager — read-only account-state poller.

Sits in Layer 4 alongside Nick Fury. Each main cycle Nick Fury calls
Portfolio Manager once to get a fresh `EquitySnapshot`, then forwards
the equity figure to Iron Man and the open-positions count to Batman.

Hard rules
----------
  • READ-ONLY. Never sends orders, never moves money. Only queries
    Hyperliquid Info `/info` for `clearinghouseState` + `assetCtxs`.
  • Defensive degradation: if credentials are missing, Hyperliquid is
    unreachable, or parsing fails, Portfolio Manager returns a paper
    fallback `EquitySnapshot` with `source=PAPER_FALLBACK` and an
    `error` string — never raises.
  • Lazy import of any networking lib (aiohttp) inside `_run` to keep
    module import cheap, mirroring Iron Man / Vision pattern.
  • In paper-trading mode WITHOUT a configured wallet, returns paper
    fallback immediately (no network call).
"""

from __future__ import annotations

from typing import Any, Optional

from src.agents.base import BaseAgent
from src.config.settings import settings
from src.models.portfolio import (
    EquitySnapshot,
    EquitySource,
    PositionSummary,
)


_PLACEHOLDER_WALLET = "0x0000000000000000000000000000000000000000"


def _hl_info_url() -> str:
    return (
        "https://api.hyperliquid.xyz/info"
        if settings.is_mainnet
        else "https://api.hyperliquid-testnet.xyz/info"
    )


class PortfolioManager(BaseAgent[EquitySnapshot]):
    """
    Read-only account-state poller.

    Usage:
        snapshot = await PortfolioManager().run()
    """

    def __init__(self) -> None:
        super().__init__(
            codename="PortfolioManager",
            role="Portfolio Manager — read-only equity & positions snapshot",
        )

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _run(self) -> EquitySnapshot:  # type: ignore[override]
        wallet = (settings.hyperliquid_wallet_address or "").lower()

        # Pre-flight: no real wallet configured → paper fallback
        if not wallet or wallet == _PLACEHOLDER_WALLET:
            return self._paper_fallback(reason="No wallet configured")

        try:
            raw = await self._fetch_clearinghouse_state(wallet)
        except Exception as exc:  # noqa: BLE001
            return self._paper_fallback(
                reason=f"Hyperliquid unreachable: {type(exc).__name__}: {exc}"
            )

        try:
            snapshot = self._parse_clearinghouse_state(raw)
        except Exception as exc:  # noqa: BLE001
            return self._paper_fallback(
                reason=f"Parse failed: {type(exc).__name__}: {exc}"
            )

        self._log.info(snapshot.summary())
        return snapshot

    # ------------------------------------------------------------------
    # HL Info fetch
    # ------------------------------------------------------------------

    async def _fetch_clearinghouse_state(self, wallet: str) -> dict[str, Any]:
        """POST /info with type=clearinghouseState."""
        # Lazy import — keeps module import cheap and isolates network deps
        import aiohttp  # noqa: WPS433

        payload = {"type": "clearinghouseState", "user": wallet}
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _hl_info_url(), json=payload, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status} from Hyperliquid /info")
                data = await resp.json(content_type=None)
        if not isinstance(data, dict):
            raise RuntimeError(
                f"Unexpected clearinghouseState shape: {type(data).__name__}"
            )
        return data

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    def _parse_clearinghouse_state(self, raw: dict[str, Any]) -> EquitySnapshot:
        """
        Parse Hyperliquid clearinghouseState into an EquitySnapshot.

        Expected shape (relevant subset):
          {
            "marginSummary": { "accountValue": "12345.67", "totalMarginUsed": "234.56" },
            "withdrawable": "12000.0",
            "assetPositions": [
              {
                "type": "oneWay",
                "position": {
                  "coin": "BTC",
                  "szi": "0.5",            # signed size (negative = short)
                  "entryPx": "65000.0",
                  "unrealizedPnl": "12.34",
                  "leverage": { "value": 3 } | { "type": "cross" }
                }
              },
              ...
            ]
          }
        """
        margin = raw.get("marginSummary", {}) or {}
        equity = float(margin.get("accountValue", 0.0) or 0.0)
        margin_used = float(margin.get("totalMarginUsed", 0.0) or 0.0)
        withdrawable_raw = raw.get("withdrawable", None)
        if withdrawable_raw is not None:
            available = float(withdrawable_raw)
        else:
            available = max(equity - margin_used, 0.0)

        raw_positions = raw.get("assetPositions", []) or []
        positions: list[PositionSummary] = []
        for entry in raw_positions:
            try:
                pos = (entry or {}).get("position", {}) or {}
                szi = float(pos.get("szi", 0.0) or 0.0)
                if szi == 0.0:
                    continue
                entry_px = float(pos.get("entryPx", 0.0) or 0.0)
                if entry_px <= 0:
                    continue
                lev_raw = pos.get("leverage", {}) or {}
                lev_val: Optional[int] = None
                try:
                    raw_v = lev_raw.get("value")
                    lev_val = int(raw_v) if raw_v is not None else None
                except (TypeError, ValueError):
                    lev_val = None
                positions.append(
                    PositionSummary(
                        symbol=str(pos.get("coin", "?")).upper(),
                        side="long" if szi > 0 else "short",
                        size=abs(szi),
                        entry_price=entry_px,
                        unrealized_pnl_usd=float(pos.get("unrealizedPnl", 0.0) or 0.0),
                        leverage=lev_val,
                    )
                )
            except (TypeError, ValueError, KeyError):
                # Skip malformed entries; do not crash the snapshot
                continue

        return EquitySnapshot(
            source=EquitySource.HYPERLIQUID,
            is_paper=settings.paper_trading,
            equity_usd=equity,
            available_balance_usd=available,
            margin_used_usd=margin_used,
            open_positions_count=len(positions),
            positions=positions,
            error=None,
        )

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _paper_fallback(self, reason: str) -> EquitySnapshot:
        """
        Synthetic snapshot used whenever a real reading is impossible.

        Equity = settings.paper_equity_usd.
        Open positions = 0 (Batman will only block on max_open_positions
        when there are real positions on the books).
        """
        snap = EquitySnapshot(
            source=EquitySource.PAPER_FALLBACK,
            is_paper=True,
            equity_usd=settings.paper_equity_usd,
            available_balance_usd=settings.paper_equity_usd,
            margin_used_usd=0.0,
            open_positions_count=0,
            positions=[],
            error=reason,
        )
        self._log.warning(snap.summary())
        return snap

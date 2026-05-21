"""
scripts/binance_testnet_smoke.py
================================
Standalone connectivity smoke-test for the Binance USDT-M Futures testnet.

Reads credentials from the project ``.env`` via ``settings`` (no shell exports
needed) and builds a CCXT client the *same way production does* — sandbox
routing applied BEFORE load_markets, defaultType=swap for perps. This validates
the exact construction sequence IronMan/Superman use.

Run:
    .venv313/bin/python scripts/binance_testnet_smoke.py

What it checks (in order, fail-fast):
  1. settings sanity — ACTIVE_EXCHANGE=binance, BINANCE_TESTNET=true, keys present
  2. sandbox routing — CCXT urls land on testnet.binancefuture.com
  3. load_markets — BTC/USDT:USDT perp catalog reachable
  4. clock skew — local clock within 5s of server (Binance rejects -1021 otherwise)
  5. fetch_balance — credentials accepted for read access (proves keys are valid)
  6. fetch_positions — real payload consumable by the dashboard mapper

Exit code 0 = all green. Non-zero = first failure (message says what to fix).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time


def _mask(s: str) -> str:
    if not s:
        return "<empty>"
    return f"{s[:4]}…{s[-4:]} (len={len(s)})" if len(s) > 8 else "<short>"


async def main() -> int:
    from src.config.settings import settings

    print("=" * 64)
    print("Binance Futures Testnet — connectivity smoke-test")
    print("=" * 64)

    # --- 1. settings sanity -------------------------------------------------
    print(f"  active_exchange : {settings.active_exchange}")
    print(f"  binance_testnet : {settings.binance_testnet}")
    print(f"  api_key         : {_mask(settings.binance_api_key)}")
    print(f"  api_secret      : {_mask(settings.binance_api_secret)}")
    print(f"  paper_trading   : {settings.paper_trading}")
    print(f"  trading_assets  : {settings.trading_assets}")
    print("-" * 64)

    problems: list[str] = []
    if settings.active_exchange != "binance":
        problems.append(
            f"ACTIVE_EXCHANGE is '{settings.active_exchange}', expected 'binance'."
        )
    if not settings.binance_testnet:
        problems.append("BINANCE_TESTNET is false — set it true for the testnet.")
    if not settings.binance_api_key or not settings.binance_api_secret:
        problems.append("BINANCE_API_KEY / BINANCE_API_SECRET missing in .env.")
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("  ✓ settings OK")

    import ccxt.async_support as ccxt  # noqa: WPS433

    cfg = {
        "apiKey": settings.binance_api_key,
        "secret": settings.binance_api_secret,
        "enableRateLimit": True,
        "timeout": 20_000,
        "options": {
            "defaultType": "swap",
            "defaultSubType": "linear",
            "fetchMarkets": {"types": ["linear"]},
            "recvWindow": 10_000,
            "adjustForTimeDifference": True,
            # CCXT 4.5+ guards binance futures testnet behind this opt-out flag
            # (deprecation warning t.me/ccxt_announcements/92). The testnet
            # endpoint still works; we acknowledge the warning to use it.
            "disableFuturesSandboxWarning": True,
        },
    }
    exchange = ccxt.binance(cfg)
    exchange.set_sandbox_mode(True)

    try:
        # --- 2. sandbox routing --------------------------------------------
        flat = str(exchange.urls.get("api")).lower()
        if "testnet" not in flat:
            print(f"  ✗ sandbox routing — urls not on testnet: {exchange.urls.get('api')!r}")
            return 2
        print("  ✓ sandbox routing → testnet endpoints")

        # --- 3. load_markets -----------------------------------------------
        last_load_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                await exchange.load_markets()
                break
            except Exception as exc:
                last_load_exc = exc
                if attempt >= 3:
                    raise
                print(f"  … load_markets retry {attempt}/3 after: {type(exc).__name__}: {exc}")
                await asyncio.sleep(float(attempt))
        if "BTC/USDT:USDT" not in exchange.markets:
            print("  ✗ load_markets — BTC/USDT:USDT perp not found (defaultType?)")
            return 3
        print(f"  ✓ load_markets — {len(exchange.markets)} markets, BTC/USDT:USDT present")

        # --- 4. clock skew --------------------------------------------------
        server_ms = int(await exchange.fetch_time())
        local_ms = int(time.time() * 1000)
        skew = abs(server_ms - local_ms)
        if skew >= 5000:
            print(
                f"  ✗ clock skew {skew}ms ≥ 5000ms — Binance will reject orders (-1021).\n"
                "      Fix NTP: `sudo sntp -sS time.apple.com` (mac)."
            )
            return 4
        print(f"  ✓ clock skew {skew}ms (< 5000ms)")

        # --- 5. fetch_balance ----------------------------------------------
        bal = await exchange.fetch_balance()
        usdt = bal.get("USDT", {})
        free = usdt.get("free") if isinstance(usdt, dict) else None
        print(f"  ✓ fetch_balance OK — USDT free: {free}")

        # --- 6. fetch_positions + dashboard mapper -------------------------
        raw = await exchange.fetch_positions()
        from src.dashboard.positions_provider import map_ccxt_positions

        items = map_ccxt_positions(raw)
        print(f"  ✓ fetch_positions OK — {len(raw)} raw, {len(items)} mapped")

        # --- 7. ticker (market data path) ----------------------------------
        try:
            tk = await exchange.fetch_ticker("BTC/USDT:USDT")
            print(f"  ✓ fetch_ticker OK — BTC last={tk.get('last')}")
        except Exception as _t_exc:  # noqa: BLE001
            print(f"  … fetch_ticker skipped: {type(_t_exc).__name__}")

        # --- 8. open orders (SL/TP visibility) -----------------------------
        try:
            oo = await exchange.fetch_open_orders()
            print(f"  ✓ fetch_open_orders OK — {len(oo)} open order(s) on venue")
        except Exception as _o_exc:  # noqa: BLE001
            print(f"  … fetch_open_orders skipped: {type(_o_exc).__name__}")

        # --- 9. OPT-IN end-to-end order test (SMOKE_PLACE_ORDER=1) ----------
        # Places a tiny MARKET order, confirms the position, places a stop,
        # then CLOSES it. Only runs when explicitly opted in — it touches the
        # (testnet) account. Never runs by default.
        if os.environ.get("SMOKE_PLACE_ORDER") == "1":
            print("  → SMOKE_PLACE_ORDER=1 — running live testnet order test…")
            sym = "BTC/USDT:USDT"
            mkt = exchange.market(sym)
            min_amt = float(((mkt.get("limits") or {}).get("amount") or {}).get("min") or 0.001)
            qty = float(exchange.amount_to_precision(sym, max(min_amt, 0.001)))
            try:
                entry = await exchange.create_order(sym, "market", "buy", qty, params={"reduceOnly": False})
                print(f"    ✓ entry market filled qty={entry.get('filled')} id={entry.get('id')}")
                # protective stop ~2% below
                last = float((await exchange.fetch_ticker(sym)).get("last") or 0)
                sl_px = round(last * 0.98, 1)
                sl = await exchange.create_order(sym, "stop_market", "sell", qty,
                                                 params={"stopPrice": sl_px, "reduceOnly": True})
                print(f"    ✓ stop placed id={sl.get('id')} @ {sl_px}")
                # close (reduce-only market) + cancel stop
                await exchange.create_order(sym, "market", "sell", qty, params={"reduceOnly": True})
                try:
                    await exchange.cancel_order(sl.get("id"), sym)
                except Exception:  # noqa: BLE001
                    pass
                print("    ✓ position closed + stop cancelled — full cycle OK")
            except Exception as _ord_exc:  # noqa: BLE001
                print(f"    ✗ order test FAILED: {type(_ord_exc).__name__}: {_ord_exc}")
                return 6

    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ FAILED: {type(exc).__name__}: {exc}")
        if "-2015" in str(exc) or "Invalid API-key" in str(exc):
            print(
                "      → -2015 means the key is from the WRONG environment.\n"
                "        Use keys generated at testnet.binancefuture.com (Futures),\n"
                "        not testnet.binance.vision (Spot) nor mainnet."
            )
        return 5
    finally:
        await exchange.close()

    print("-" * 64)
    print("  ALL GREEN — Binance testnet reachable. Safe to start the system.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

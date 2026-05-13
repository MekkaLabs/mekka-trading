"""
run.py
======
Mekka Trading — Python runtime entry point.

Usage
-----
  python run.py                    # run forever (paper trading by default)
  python run.py --once             # run a single main cycle and exit
  python run.py --equity 25000     # override starting equity (USD)

Environment must define OPENAI_API_KEY, HYPERLIQUID_PRIVATE_KEY,
HYPERLIQUID_WALLET_ADDRESS. See .env.example.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger

from src.agents.nick_fury import NickFury, run_forever
from src.config.settings import settings
from src.dashboard.server import run_dashboard_server


def _configure_logger() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[agent]:<14}</cyan> | "
            "{message}"
        ),
        filter=lambda r: "agent" in r["extra"],
    )
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan> | {message}"
        ),
        filter=lambda r: "agent" not in r["extra"],
    )


async def _run_once(equity_usd: float) -> int:
    fury = NickFury()
    await fury.initialize()
    try:
        reports = await fury.run_main_cycle(equity_usd=equity_usd)
        executed = sum(1 for r in reports if r.is_executed())
        logger.info(
            f"[run] Cycle complete: {len(reports)} symbols, {executed} executed"
        )
        return 0
    finally:
        await fury.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(prog="mekka", description="Mekka Trading runtime")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single main cycle and exit",
    )
    parser.add_argument(
        "--equity",
        type=float,
        default=10_000.0,
        help="Starting equity in USD (default: 10000)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Run browser dashboard server together with runtime",
    )
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Run only the dashboard API/UI server",
    )
    parser.add_argument(
        "--dashboard-host",
        type=str,
        default="127.0.0.1",
        help=(
            "Dashboard bind host. Defaults to 127.0.0.1 so the UI is only "
            "reachable from this machine. Use 0.0.0.0 to expose it on the LAN "
            "(also set DASHBOARD_ALLOWED_ORIGINS to a non-default origin)."
        ),
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8787,
        help="Dashboard bind port (default: 8787)",
    )
    args = parser.parse_args()

    _configure_logger()
    logger.info(settings.summary())

    try:
        if args.dashboard_only:
            asyncio.run(
                run_dashboard_server(host=args.dashboard_host, port=args.dashboard_port)
            )
            return 0
        if args.once:
            return asyncio.run(_run_once(equity_usd=args.equity))
        if args.dashboard:
            async def _run_both() -> None:
                # TaskGroup (Python 3.11+) propagates the first exception and
                # cancels every sibling task. Without this, a crash inside
                # run_forever would leave the dashboard running zombie-style
                # (or vice-versa) — not what an operator expects when one
                # half of the system dies. We catch the resulting
                # ExceptionGroup as a plain Exception (it inherits from
                # Exception on 3.11+) and log every wrapped error.
                try:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(run_forever(equity_usd=args.equity))
                        tg.create_task(
                            run_dashboard_server(
                                host=args.dashboard_host,
                                port=args.dashboard_port,
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    sub = getattr(exc, "exceptions", None)
                    if sub:
                        for inner in sub:
                            logger.exception(
                                "[run] task group failure: {}", inner
                            )
                    else:
                        logger.exception("[run] task group failure: {}", exc)
                    raise

            asyncio.run(_run_both())
            return 0
        asyncio.run(run_forever(equity_usd=args.equity))
        return 0
    except KeyboardInterrupt:
        logger.info("[run] Interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())

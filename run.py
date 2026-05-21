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
import os
import sys

# Strip EMPTY LLM API-key env vars before settings load. An empty
# ``ANTHROPIC_API_KEY=`` / ``OPENAI_API_KEY=`` in the shell environment takes
# precedence over the .env file in pydantic-settings and would silently shadow
# a valid key configured in .env (observed: Vision falling back to HOLD because
# an empty env var hid the real Anthropic key). Removing only empty values
# lets the .env be authoritative while still honoring a real exported key.
for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    if os.environ.get(_k, None) == "":
        del os.environ[_k]

from loguru import logger

from src.agents.nick_fury import NickFury, run_forever
from src.config.settings import settings
from src.dashboard.server import run_dashboard_server
from src.persistence.repository import MekkaRepository
from src.runtime_controller import RuntimeController


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


async def _run_forever_with_inbound(equity_usd: float | None = None) -> None:
    """
    Like nick_fury.run_forever but also starts TelegramInboundPoller when
    ``settings.telegram_inbound_enabled`` is True.

    Creates NickFury directly (instead of delegating to the module-level
    run_forever) so the fury instance can be injected into the poller.
    """
    fury = NickFury()
    await fury.initialize()

    # Story 049 — start Telegram inbound command poller (fire-and-forget task)
    if settings.telegram_inbound_enabled:
        try:
            from src.services.telegram_inbound import TelegramInboundPoller  # noqa: WPS433
            poller = TelegramInboundPoller(
                nick_fury=fury,
                portfolio=fury._portfolio,
                repo=MekkaRepository,
            )
            asyncio.create_task(poller.run_forever(), name="telegram_inbound")
            logger.info("[run] TelegramInboundPoller started")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[run] TelegramInboundPoller failed to start (non-fatal): {}", exc)

    monitor_interval = settings.monitor_interval_seconds
    main_interval = settings.main_loop_interval_seconds
    last_main_at = 0.0

    try:
        while True:
            now = asyncio.get_event_loop().time()
            if now - last_main_at >= main_interval:
                logger.info("[NickFury] Starting main cycle")
                await fury.run_main_cycle(equity_usd=equity_usd)
                last_main_at = now
            else:
                await fury.run_monitor_cycle()
            await asyncio.sleep(monitor_interval)
    except asyncio.CancelledError:
        logger.info("[NickFury] Loop cancelled — shutting down")
    finally:
        await fury.shutdown()


async def _run_once(equity_usd: float, langgraph: bool = False) -> int:
    fury = NickFury()
    await fury.initialize()
    try:
        if langgraph:
            reports = await fury.run_with_checkpointing(equity_usd=equity_usd)
            executed = sum(1 for r in reports if r.get("execution") and r.get("execution", {}).get("status") in ("FILLED", "PAPER"))
            logger.info(
                f"[run:LG] Cycle complete: {len(reports)} symbols, {executed} executed"
            )
        else:
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
    parser.add_argument(
        "--langgraph",
        action="store_true",
        help=(
            "[Story 126] Usa LangGraph StateGraph com AsyncSqliteSaver "
            "em vez do ciclo NickFury direto. Habilita durable execution "
            "e checkpoint por símbolo. Requer: pip install langgraph "
            "langgraph-checkpoint-sqlite"
        ),
    )
    args = parser.parse_args()

    _configure_logger()
    logger.info(settings.summary())

    try:
        if args.dashboard_only:
            # Dashboard como control plane puro: cria o controller mas NÃO o
            # inicia, para que o operador ligue o runtime pela UI.
            async def _run_dashboard_only() -> None:
                controller = RuntimeController(equity_usd=args.equity)
                try:
                    await run_dashboard_server(
                        host=args.dashboard_host,
                        port=args.dashboard_port,
                        controller=controller,
                    )
                finally:
                    await controller.stop()

            asyncio.run(_run_dashboard_only())
            return 0
        if args.once:
            return asyncio.run(_run_once(equity_usd=args.equity, langgraph=args.langgraph))
        if args.dashboard:
            # Dashboard é primário (sempre ligado); o runtime de trading é de
            # propriedade do RuntimeController, que pode ligar/desligar/reiniciar
            # via UI. Bootamos rodando por padrão (preserva o comportamento
            # anterior), mas garantimos o stop() ao encerrar para que nenhuma
            # chamada de LLM continue após o shutdown.
            async def _run_both() -> None:
                # Apply a persisted runtime exchange override (set via the
                # dashboard selector) onto live settings before anything boots.
                try:
                    from src.config.runtime_exchange import apply_to_settings
                    apply_to_settings()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[run] runtime exchange override skipped: {}", exc)

                controller = RuntimeController(equity_usd=args.equity)
                # Telegram inbound poller lives in the control plane (survives
                # runtime stop/start) so /ligar, /desligar e /reboot funcionam
                # mesmo com o sistema desligado.
                poller_task = None
                if settings.telegram_inbound_enabled:
                    try:
                        from src.services.telegram_inbound import TelegramInboundPoller
                        from src.persistence.repository import MekkaRepository
                        poller = TelegramInboundPoller(controller=controller, repo=MekkaRepository)
                        controller.attach_poller(poller)
                        poller_task = asyncio.create_task(
                            poller.run_forever(), name="telegram_inbound"
                        )
                        logger.info("[run] TelegramInboundPoller started in control plane")
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("[run] TelegramInboundPoller failed (non-fatal): %s", exc)
                await controller.start()

                # Pre-warm the CCXT exchange in the background. load_markets
                # costs 9-18s on Binance testnet; warming it now means the
                # first dashboard "Executar Trade" click is fast instead of
                # paying the cold connection cost. Fire-and-forget; non-fatal.
                async def _prewarm_ccxt() -> None:
                    try:
                        if settings.active_exchange in ("binance", "bybit"):
                            from src.agents.iron_man import IronMan
                            await IronMan()._get_ccxt_exchange(settings.active_exchange)
                            logger.info(
                                "[run] CCXT exchange pre-warmed: {}",
                                settings.active_exchange,
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("[run] CCXT pre-warm failed (non-fatal): {}", exc)

                asyncio.create_task(_prewarm_ccxt(), name="ccxt_prewarm")

                try:
                    await run_dashboard_server(
                        host=args.dashboard_host,
                        port=args.dashboard_port,
                        controller=controller,
                    )
                finally:
                    if poller_task is not None:
                        poller_task.cancel()
                    await controller.stop()
                    try:
                        from src.agents.iron_man import aclose_ccxt_cache
                        await aclose_ccxt_cache()
                    except Exception:  # noqa: BLE001
                        pass

            asyncio.run(_run_both())
            return 0
        asyncio.run(_run_forever_with_inbound(equity_usd=args.equity))
        return 0
    except KeyboardInterrupt:
        logger.info("[run] Interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())

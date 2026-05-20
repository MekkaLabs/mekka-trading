"""
runtime_controller.py
=====================
In-process lifecycle controller for the Mekka trading runtime.

The dashboard is the always-on *control plane*: it never shuts itself down.
The trading runtime (the Nick Fury main/monitor loop and every agent it
drives) is owned by this controller, which can start, stop and reboot it on
demand. Stopping cancels the loop task, so no further main/monitor cycles run
— which means **no more LLM calls and therefore no token spend** while the
system is "off". Open work is drained via ``NickFury.shutdown()``.

This module deliberately keeps zero coupling to the web layer: the dashboard
holds a reference to a ``RuntimeController`` instance and calls its async
methods from request handlers. ``run.py`` constructs the controller, starts it
and hands it to the dashboard server.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from loguru import logger

from src.config.settings import settings

RuntimeState = Literal["stopped", "starting", "running", "stopping"]


class RuntimeController:
    """Owns the Nick Fury runtime loop as a cancellable asyncio task.

    Thread-/task-safety: all state transitions are guarded by an asyncio lock
    so concurrent ``start``/``stop``/``reboot`` requests from the dashboard are
    serialised.
    """

    def __init__(self, equity_usd: float | None = None) -> None:
        self._equity = equity_usd
        self._task: asyncio.Task[Any] | None = None
        self._poller_task: asyncio.Task[Any] | None = None
        self._fury: Any | None = None
        # Optional Telegram inbound poller living in the always-on control
        # plane. The controller injects/clears the runtime refs on it so the
        # operator can /ligar and /desligar from Telegram.
        self._poller: Any | None = None
        self._state: RuntimeState = "stopped"
        self._started_at: float | None = None
        self._cycles: int = 0
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    def attach_poller(self, poller: Any) -> None:
        """Wire a control-plane Telegram poller so it learns when the runtime
        starts/stops (set_runtime / clear_runtime)."""
        self._poller = poller

    # ── introspection ─────────────────────────────────────────────────────
    @property
    def state(self) -> RuntimeState:
        return self._state

    def status(self) -> dict[str, Any]:
        uptime = (
            round(time.monotonic() - self._started_at, 1)
            if (self._started_at and self._state == "running")
            else 0.0
        )
        return {
            "state": self._state,
            "running": self._state == "running",
            "uptime_seconds": uptime,
            "cycles": self._cycles,
            "paper_trading": settings.paper_trading,
            "mode": "mainnet" if getattr(settings, "is_mainnet", False) else "testnet",
            "last_error": self._last_error,
        }

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def start(self) -> dict[str, Any]:
        """Spawn the runtime loop if it is not already running."""
        async with self._lock:
            if self._state in ("running", "starting"):
                return {"ok": True, "state": self._state, "noop": True}
            self._last_error = None
            self._state = "starting"
            self._task = asyncio.create_task(self._run_loop(), name="mekka_runtime")
            logger.info("[RuntimeController] start requested → runtime task spawned")
            return {"ok": True, "state": self._state}

    async def stop(self) -> dict[str, Any]:
        """Cancel the runtime loop and drain it. Stops all token spend."""
        async with self._lock:
            if self._state == "stopped":
                return {"ok": True, "state": "stopped", "noop": True}
            self._state = "stopping"
            logger.info("[RuntimeController] stop requested → cancelling runtime task")
            if self._poller_task and not self._poller_task.done():
                self._poller_task.cancel()
            task = self._task
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[RuntimeController] runtime task ended with: {}", exc)
            self._task = None
            self._poller_task = None
            self._fury = None
            self._started_at = None
            self._state = "stopped"
            logger.info("[RuntimeController] runtime stopped — no further cycles/LLM calls")
            return {"ok": True, "state": "stopped"}

    async def reboot(self) -> dict[str, Any]:
        """Stop then start the runtime fresh."""
        logger.info("[RuntimeController] reboot requested")
        await self.stop()
        return await self.start()

    # ── internal loop ─────────────────────────────────────────────────────
    async def _run_loop(self) -> None:
        """The runtime body. Mirrors run.py's _run_forever_with_inbound, but
        owned by the controller so it can be cancelled cleanly.
        """
        from src.agents.nick_fury import NickFury  # local import: heavy module

        fury = NickFury()
        self._fury = fury
        try:
            await fury.initialize()

            # Inject runtime refs into the control-plane Telegram poller (the
            # poller itself lives in run.py so it survives stop/start, letting
            # the operator /ligar after /desligar).
            if self._poller is not None:
                try:
                    self._poller.set_runtime(fury, getattr(fury, "_portfolio", None))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[RuntimeController] poller.set_runtime failed: {}", exc)

            monitor_interval = settings.monitor_interval_seconds
            main_interval = settings.main_loop_interval_seconds
            last_main_at = 0.0

            self._state = "running"
            self._started_at = time.monotonic()
            logger.info("[RuntimeController] runtime is now RUNNING")

            while True:
                now = asyncio.get_event_loop().time()
                if now - last_main_at >= main_interval:
                    logger.info("[NickFury] Starting main cycle")
                    await fury.run_main_cycle(equity_usd=self._equity)
                    last_main_at = now
                    self._cycles += 1
                else:
                    await fury.run_monitor_cycle()
                await asyncio.sleep(monitor_interval)
        except asyncio.CancelledError:
            logger.info("[RuntimeController] runtime loop cancelled — shutting down")
            raise
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.exception("[RuntimeController] runtime loop crashed: {}", exc)
        finally:
            try:
                await fury.shutdown()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[RuntimeController] shutdown error (ignored): {}", exc)
            self._fury = None
            # Tell the control-plane poller the runtime is gone.
            if self._poller is not None:
                try:
                    self._poller.clear_runtime()
                except Exception:  # noqa: BLE001
                    pass
            # If we fell out of the loop without an explicit stop(), reflect it.
            if self._state != "stopping":
                self._state = "stopped"
                self._started_at = None

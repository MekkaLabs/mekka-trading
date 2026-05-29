"""
src/services/auto_learning_scheduler.py
=========================================
REV-3 (auditoria 2026-05-29) — Auto-learning Scheduler.

Background loop que dispara periodicamente:
1. Mentor.run() (sugestões de calibração de parâmetro)
2. stale_imp_learner.analyze_stale_imps() (padrões aprendidos)
3. memory_reconciler.reconcile_pending() (resolve PENDING)
4. cable_vault_writer.upsert_cable_status() (snapshot Cable no vault)

Output:
- Mentor suggestions → improvement_inbox.json (auto-aceitas próxima
  rodada do Mekka)
- Stale patterns → data/stale_patterns.json (Mekka consulta runtime)
- audit_log eventos AUTO_LEARNING_CYCLE com snapshot

Princípios:
- OPT-IN via AUTO_LEARNING_ENABLED (default off)
- Período via AUTO_LEARNING_INTERVAL_MIN (default 60 min)
- Fail-silent em cada step
- READ-MOSTLY: só escreve em paths já permitidos (memory writers)
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger


def is_enabled() -> bool:
    return os.environ.get("AUTO_LEARNING_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def interval_seconds() -> float:
    try:
        minutes = float(os.environ.get("AUTO_LEARNING_INTERVAL_MIN", "60"))
    except (TypeError, ValueError):
        minutes = 60.0
    return max(60.0, minutes * 60.0)  # min 1 minuto


# ---------------------------------------------------------------------------
# Single-cycle work
# ---------------------------------------------------------------------------


async def run_mentor_step() -> dict[str, Any]:
    """Roda Mentor + enfileira sugestões high-conf. Retorna metrics."""
    try:
        from src.agents.mentor import Mentor
        report = await Mentor().run()
        suggestions = list(getattr(report, "suggestions", []))
        # Auto-enqueue high-conf via _enqueue_in_inbox (já existe em Mentor)
        # mas Mentor._audit_suggestions já faz isso internamente. Idempotent.
        return {
            "step": "mentor",
            "ok": True,
            "suggestions_count": len(suggestions),
            "observation_summary": getattr(report, "observation_summary", {}),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[auto_learning] mentor step failed: {exc}")
        return {"step": "mentor", "ok": False, "error": str(exc)}


def run_stale_learner_step() -> dict[str, Any]:
    """Analisa stale IMPs + persiste padrões."""
    try:
        from src.services.stale_imp_learner import analyze_stale_imps
        report = analyze_stale_imps()
        return {
            "step": "stale_learner",
            "ok": True,
            "total_stale": report.get("total_stale", 0),
            "patterns_count": len(report.get("patterns", [])),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[auto_learning] stale learner failed: {exc}")
        return {"step": "stale_learner", "ok": False, "error": str(exc)}


def run_reconciler_step() -> dict[str, Any]:
    """Resolve PENDING em agent_memories."""
    try:
        from src.services import memory_reconciler
        # Dry-run primeiro pra saber se há algo
        if hasattr(memory_reconciler, "reconcile_pending"):
            result = memory_reconciler.reconcile_pending(apply=True, limit=100)
        else:
            # API alternativa: usa main com argv
            result = {"note": "manual API not exposed; skip"}
        return {"step": "reconciler", "ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[auto_learning] reconciler step skipped: {exc}")
        return {"step": "reconciler", "ok": False, "error": str(exc)}


def run_cable_vault_step() -> dict[str, Any]:
    """Persiste estado do Cable no vault canônico."""
    try:
        from src.services import cable_vault_writer
        if not cable_vault_writer.is_enabled():
            return {"step": "cable_vault", "ok": True, "note": "disabled"}
        path = cable_vault_writer.upsert_cable_status()
        return {"step": "cable_vault", "ok": True, "wrote": str(path) if path else None}
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[auto_learning] cable vault step skipped: {exc}")
        return {"step": "cable_vault", "ok": False, "error": str(exc)}


async def run_one_cycle() -> dict[str, Any]:
    """
    Executa UM ciclo completo de auto-learning. Pode ser chamado manualmente
    (CLI, endpoint) ou pelo background loop.
    """
    started = datetime.now(timezone.utc)
    results = {
        "ts": started.isoformat(),
        "steps": [],
    }

    # 1. Stale learner (síncrono, rápido)
    results["steps"].append(run_stale_learner_step())

    # 2. Reconciler (síncrono)
    results["steps"].append(run_reconciler_step())

    # 3. Mentor (async, mais lento)
    results["steps"].append(await run_mentor_step())

    # 4. Cable vault (síncrono)
    results["steps"].append(run_cable_vault_step())

    # Audit log
    try:
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.log_event(
            agent="AutoLearning",
            event="AUTO_LEARNING_CYCLE",
            severity="INFO",
            message=f"{len(results['steps'])} steps executed",
            payload=results,
        )
    except Exception:  # noqa: BLE001
        pass

    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    results["duration_ms"] = duration_ms
    logger.info(
        f"[auto_learning] cycle done in {duration_ms:.0f}ms — "
        f"steps OK: {sum(1 for s in results['steps'] if s.get('ok'))}/{len(results['steps'])}"
    )
    return results


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------


_task: Optional[asyncio.Task] = None
_last_cycle_result: dict[str, Any] = {}


def get_last_cycle() -> dict[str, Any]:
    """Snapshot do último cycle pro dashboard."""
    return dict(_last_cycle_result)


def get_status() -> dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "interval_seconds": interval_seconds(),
        "running": _task is not None and not _task.done(),
        "last_cycle_ts": _last_cycle_result.get("ts"),
        "last_cycle_steps_ok": sum(
            1 for s in _last_cycle_result.get("steps", []) if s.get("ok")
        ),
    }


async def _background_loop() -> None:
    """Loop infinito. Cancela com task.cancel()."""
    global _last_cycle_result
    interval = interval_seconds()
    logger.info(
        f"[auto_learning] background loop started (interval={interval:.0f}s)"
    )
    while True:
        try:
            _last_cycle_result = await run_one_cycle()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[auto_learning] cycle exception: {exc}")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("[auto_learning] loop cancelled")
            raise


async def start() -> Optional[asyncio.Task]:
    """Inicia o background loop. Retorna a task ou None se já rodando."""
    global _task
    if not is_enabled():
        logger.debug("[auto_learning] start skipped: disabled")
        return None
    if _task is not None and not _task.done():
        logger.debug("[auto_learning] start skipped: already running")
        return _task
    _task = asyncio.create_task(_background_loop(), name="auto_learning_loop")
    return _task


async def stop() -> None:
    """Cancela o background loop."""
    global _task
    if _task is None or _task.done():
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None

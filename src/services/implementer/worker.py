"""
src/services/implementer/worker.py
====================================
Worker — processa a fila ``improvement_queue.json`` em batch.

Modos de uso:

  - **CLI:** ``python3 -m src.services.implementer.worker --dry-run``
  - **Programático:** ``run_once(max_imps=3, dry_run=False)``
  - **Cron:** schedular para rodar 1x/hora

Política:

  - Só pega IMPs com ``dev_state="queued"`` há mais de 30 minutos
    (deixa operador cancelar erro de clique)
  - Cap em ``max_imps`` por execução
  - Resultado persistido em ``data/implementer_history.json``
  - Ao final, atualiza ``dev_state`` queued → in_dev (se SUCCESS)
    ou anota motivo no índice (se SKIPPED/BLOCKED/FAILED/RECIPE_ONLY)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.services.implementer.base import ImplementerResult, ImplementerStatus
from src.services.implementer.router import route_implementer

_REPO = Path(__file__).resolve().parents[3]
_QUEUE_FILE = _REPO / "data" / "improvement_queue.json"
_QUEUE_DIR = _REPO / "docs" / "improvement-queue"
_HISTORY_FILE = _REPO / "data" / "implementer_history.json"

# Não pega briefs aceitos há menos de N minutos (proteção contra clique errado)
MIN_QUEUE_AGE_MINUTES = int(os.environ.get("IMPLEMENTER_MIN_QUEUE_AGE_MIN", "30"))


# ---------------------------------------------------------------------------
# Helpers — JSON safe
# ---------------------------------------------------------------------------


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str),
                       encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.warning(f"[worker] save {path.name} failed: {exc}")
        return False


def _read_brief_from_disk(rec_id: str) -> dict[str, Any]:
    """Lê o markdown brief, extrai metadados básicos (title, area, impact, etc)."""
    import re
    brief_path = _QUEUE_DIR / f"IMP-{rec_id}.md"
    out: dict[str, Any] = {"rec_id": rec_id, "id": rec_id}
    if not brief_path.exists():
        return out
    try:
        text = brief_path.read_text(encoding="utf-8")
    except OSError:
        return out
    # YAML frontmatter (simples)
    for field in ("area", "priority", "domain", "status"):
        fm = re.search(rf"^{field}:\s*\"?([^\"\n]+)\"?\s*$", text, re.MULTILINE)
        if fm:
            out[field] = fm.group(1).strip()
    # Title da H1
    m = re.search(r"^#\s+IMP-[a-f0-9]+\s+—\s+(.+)$", text, re.MULTILINE)
    if m:
        out["title"] = m.group(1).strip()
    # Impact (vem como "**Impact:** XXX")
    im = re.search(r"\*\*Impact:\*\*\s+(\w+)", text)
    if im:
        out["impact"] = im.group(1).strip()
    # Description (entre "## Description" e próxima "##")
    dm = re.search(r"##\s+Description\s*\n+(.*?)(?=\n##\s+|\Z)", text, re.DOTALL)
    if dm:
        out["description"] = dm.group(1).strip()
    # Evidence
    em = re.search(r"##\s+Evidence\s*\n+(.*?)(?=\n##\s+|\Z)", text, re.DOTALL)
    if em:
        out["evidence"] = em.group(1).strip()
    return out


def _eligible_queued_ids(queue: dict[str, dict]) -> list[str]:
    """Filtra rec_ids com dev_state=queued há mais de MIN_QUEUE_AGE_MINUTES."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=MIN_QUEUE_AGE_MINUTES)
    out = []
    for rec_id, entry in queue.items():
        if entry.get("dev_state") != "queued":
            continue
        ts_str = entry.get("queued_at")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ts <= cutoff:
            out.append(rec_id)
    # Mais antigos primeiro
    out.sort(key=lambda r: queue[r].get("queued_at", ""))
    return out


def _append_history(result: ImplementerResult) -> None:
    history = _load_json(_HISTORY_FILE, {"runs": []})
    history["runs"].append(result.to_dict())
    history["runs"] = history["runs"][-200:]  # cap
    _save_json(_HISTORY_FILE, history)


def _audit_implementer_run(result: ImplementerResult) -> None:
    """INV-16 (2026-05-29): emite IMPLEMENTER_RAN ao audit_log.

    Antes: o worker rodava silenciosamente — único registro era o
    implementer_history.json local. Sem audit trail no DB principal,
    dashboard não conseguia mostrar "histórico de implementação".

    Map de severity:
      - SUCCESS                       → INFO
      - PARTIAL / RECIPE_ONLY         → DEBUG (não é falha real, é fallback)
      - SKIPPED                       → DEBUG
      - BLOCKED / FAILED              → WARNING

    Fail-silent — qualquer erro de I/O é só log debug.
    """
    try:
        import asyncio as _asyncio  # noqa: WPS433
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        sev_map = {
            ImplementerStatus.SUCCESS: "INFO",
            ImplementerStatus.PARTIAL: "DEBUG",
            ImplementerStatus.RECIPE_ONLY: "DEBUG",
            ImplementerStatus.SKIPPED: "DEBUG",
            ImplementerStatus.BLOCKED: "WARNING",
            ImplementerStatus.FAILED: "WARNING",
        }
        severity = sev_map.get(result.status, "DEBUG")

        payload = {
            "rec_id": result.rec_id,
            "agent": result.agent,
            "status": result.status.value,
            "layer_used": result.layer_used,
            "files_changed": result.files_changed[:10],
            "n_files": len(result.files_changed),
            "lines_changed": result.lines_changed,
            "commit_sha": result.commit_sha,
            "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms,
        }
        message = (
            f"IMP-{result.rec_id} {result.status.value} "
            f"({result.layer_used or 'no-layer'}, "
            f"{len(result.files_changed)} files, {result.lines_changed} lines)"
        )

        async def _emit() -> None:
            await MekkaRepository.log_event(
                agent="ImplementerWorker",
                event="IMPLEMENTER_RAN",
                severity=severity,
                message=message,
                payload=payload,
            )

        # Roda no loop existente se já houver, senão cria um one-shot.
        try:
            loop = _asyncio.get_running_loop()
            loop.create_task(_emit())
        except RuntimeError:
            _asyncio.run(_emit())
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[worker] IMPLEMENTER_RAN emit skipped: {exc}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_once(max_imps: int = 3, dry_run: bool = False) -> dict[str, Any]:
    """
    Processa até ``max_imps`` IMPs queued. Retorna sumário.
    """
    started = datetime.now()
    queue = _load_json(_QUEUE_FILE, {})
    if not queue:
        return {"processed": 0, "reason": "queue empty"}

    eligible = _eligible_queued_ids(queue)
    if not eligible:
        return {"processed": 0, "reason": "no eligible IMPs"}

    results: list[dict[str, Any]] = []
    success_count = 0

    for rec_id in eligible[:max_imps]:
        brief = _read_brief_from_disk(rec_id)
        if not brief.get("area"):
            logger.warning(f"[worker] IMP-{rec_id} sem area — pulando")
            continue

        implementer = route_implementer(brief, dry_run=dry_run)
        if implementer is None:
            continue

        logger.info(
            f"[worker] processing IMP-{rec_id} via {implementer.name} "
            f"(area={brief['area']})"
        )
        result = implementer.implement(brief)
        results.append(result.to_dict())
        _append_history(result)
        _audit_implementer_run(result)

        # Atualiza dev_state do índice + brief.md
        if result.status == ImplementerStatus.SUCCESS:
            success_count += 1
            try:
                from src.services.improvement_queue import update_brief_status
                update_brief_status(
                    rec_id, "in_dev",
                    claimer=implementer.name,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[worker] could not update dev_state: {exc}")

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    summary = {
        "processed": len(results),
        "success": success_count,
        "duration_ms": duration_ms,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "results": results,
    }
    logger.info(
        f"[worker] done: {summary['processed']} processed, "
        f"{success_count} success, {duration_ms}ms"
    )
    return summary


# ---------------------------------------------------------------------------
# MEM-AUDIT-4 (2026-05-29) — Background loop
# ---------------------------------------------------------------------------
#
# Diagnóstico: 101 briefs queued, 1 IMPLEMENTER_RAN em 7 dias.
# Causa raiz: worker era invocável só via CLI manual. Sem loop → IMPs
# se acumulam pra sempre.
#
# Fix: loop opt-in que roda `run_once()` em intervalo regular.
# DEFAULT: dry_run=True (não comita) — operador precisa setar explicit
# IMPLEMENTER_WORKER_AUTO_APPLY=true pra desligar dry-run.
# Cap conservador: max_imps=3 por ciclo, intervalo 15 min default.

import asyncio as _asyncio

_background_task: "Optional[_asyncio.Task]" = None


def _operation_is_automatic() -> bool:
    """True quando operation_mode == 'automatic'. Fail-safe: False se indisponível."""
    try:
        from src.config.operation_mode import is_automatic  # noqa: WPS433
        return is_automatic()
    except Exception:  # noqa: BLE001
        return False


def worker_is_enabled() -> bool:
    """O worker do squad roda quando QUALQUER um for verdadeiro:
      - operation_mode == 'automatic' (switch raiz), OU
      - env IMPLEMENTER_WORKER_ENABLED=true (opt-in legado).
    Em modo 'manual' (default) fica OFF — o operador conduz as melhorias."""
    env_opt_in = os.environ.get("IMPLEMENTER_WORKER_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )
    return env_opt_in or _operation_is_automatic()


def worker_should_apply() -> bool:
    """Aplica de verdade (não dry-run) quando QUALQUER um for verdadeiro:
      - operation_mode == 'automatic' (switch raiz), OU
      - env IMPLEMENTER_WORKER_AUTO_APPLY=true (opt-in legado).
    Em modo 'manual' o worker no máximo prepara em dry-run; o operador aplica."""
    env_opt_in = os.environ.get("IMPLEMENTER_WORKER_AUTO_APPLY", "false").lower() in (
        "1", "true", "yes", "on"
    )
    return env_opt_in or _operation_is_automatic()


def worker_interval_seconds() -> float:
    try:
        m = float(os.environ.get("IMPLEMENTER_WORKER_INTERVAL_MIN", "15"))
    except (TypeError, ValueError):
        m = 15.0
    return max(60.0, m * 60.0)


def worker_max_per_cycle() -> int:
    try:
        return max(1, int(os.environ.get("IMPLEMENTER_WORKER_MAX_PER_CYCLE", "3")))
    except (TypeError, ValueError):
        return 3


async def _background_loop() -> None:
    """Loop infinito. Cancela com task.cancel()."""
    interval = worker_interval_seconds()
    max_imps = worker_max_per_cycle()
    dry = not worker_should_apply()
    logger.info(
        f"[implementer_worker] background loop started "
        f"(interval={interval:.0f}s, max={max_imps}/cycle, dry_run={dry})"
    )
    while True:
        try:
            result = run_once(max_imps=max_imps, dry_run=dry)
            if result.get("processed", 0) > 0:
                logger.info(
                    f"[implementer_worker] cycle: "
                    f"{result.get('processed')} processed, "
                    f"{result.get('success', 0)} success"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[implementer_worker] cycle exception: {exc}")
        try:
            await _asyncio.sleep(interval)
        except _asyncio.CancelledError:
            logger.info("[implementer_worker] loop cancelled")
            raise


async def start_background() -> "Optional[_asyncio.Task]":
    """Inicia o background loop. Retorna a task ou None se desabilitado."""
    global _background_task
    if not worker_is_enabled():
        logger.debug("[implementer_worker] start skipped: disabled (set IMPLEMENTER_WORKER_ENABLED=true)")
        return None
    if _background_task is not None and not _background_task.done():
        logger.debug("[implementer_worker] start skipped: already running")
        return _background_task
    _background_task = _asyncio.create_task(_background_loop(), name="implementer_worker_loop")
    return _background_task


async def stop_background() -> None:
    """Cancela o loop."""
    global _background_task
    if _background_task is None or _background_task.done():
        return
    _background_task.cancel()
    try:
        await _background_task
    except _asyncio.CancelledError:
        pass
    _background_task = None


def get_background_status() -> dict[str, Any]:
    """Snapshot pro dashboard / /api/implementer/status."""
    return {
        "enabled": worker_is_enabled(),
        "auto_apply": worker_should_apply(),
        "interval_seconds": worker_interval_seconds(),
        "max_per_cycle": worker_max_per_cycle(),
        "running": _background_task is not None and not _background_task.done(),
    }


def history_summary(limit: int = 20) -> dict[str, Any]:
    """Snapshot pro dashboard."""
    h = _load_json(_HISTORY_FILE, {"runs": []})
    runs = h.get("runs", [])
    if not runs:
        return {"total": 0, "recent": [], "by_status": {}}
    by_status: dict[str, int] = {}
    for r in runs:
        s = r.get("status", "?")
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "total": len(runs),
        "recent": runs[-limit:],
        "by_status": by_status,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Implementer worker — processa fila de IMPs")
    ap.add_argument("--max", type=int, default=3, help="Max IMPs por run")
    ap.add_argument("--dry-run", action="store_true", help="Aplica mudanças mas não commita")
    args = ap.parse_args()
    out = run_once(max_imps=args.max, dry_run=args.dry_run)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

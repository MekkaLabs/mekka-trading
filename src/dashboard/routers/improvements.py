"""
src/dashboard/routers/improvements.py
======================================
Continuous-Improvement Department HTTP handlers, extracted from server.py.

These were methods on ``MekkaDashboardServer``; they now live here as functions
taking the ``server`` instance. server.py keeps the route registration and
delegates to these (one-line forwarders), so behaviour is identical — this only
moves the bodies out of the 6.7k-line server.py (CodeAuditor/Cypher finding).
"""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from src.persistence.repository import MekkaRepository

logger = logging.getLogger("mekka.dashboard.improvements")


async def handle_get(server, request: web.Request) -> web.Response:
    """GET /api/improvements[?fresh=1] — run the Mekka improvement council."""
    fresh = request.rel_url.query.get("fresh") in ("1", "true", "yes")
    try:
        import time as _time
        from src.agents.mekka import Mekka
        now = _time.monotonic()
        cached = getattr(server, "_impr_cache", None)
        if not fresh and cached and (now - cached[0]) < 20.0:
            return web.json_response(cached[1], status=200)
        report = await Mekka().run(period_days=7)
        report_dict = report.to_dict()
        server._impr_cache = (now, report_dict)
        try:
            if not hasattr(server, "_impr_notified"):
                server._impr_notified = set()
            pend = [r for r in (getattr(report, "recommendations", []) or [])
                    if getattr(r, "status", "pending") == "pending"]
            fresh_recs = [r for r in pend if getattr(r, "id", None) and r.id not in server._impr_notified]
            if fresh_recs:
                from src.services.telegram_alerter import TelegramAlerter as _TA
                alerter = _TA()
                for r in fresh_recs[:5]:
                    server._impr_notified.add(r.id)
                    asyncio.create_task(alerter.improvement_proposed(r))
        except Exception as _push_exc:  # noqa: BLE001
            logger.debug("improvement Telegram push skipped: %s", _push_exc)
        return web.json_response(report_dict, status=200)
    except Exception as exc:  # noqa: BLE001
        logger.error("improvements council failed: %s", exc, exc_info=True)
        return web.json_response(
            {"error": f"Falha ao montar o conselho de melhorias: {exc}",
             "recommendations": [], "summary": {}},
            status=200,
        )


async def handle_decision(server, request: web.Request) -> web.Response:
    """POST /api/improvements/decision — operator accepts/rejects a rec."""
    body = await server._safe_json_body(request) or {}
    rec_id = str(body.get("id") or "").strip()[:64]
    status = str(body.get("status") or "").strip().lower()
    if not rec_id or status not in ("accepted", "rejected", "pending"):
        return web.json_response(
            {"ok": False, "reason": "Parâmetros inválidos (id + status accepted|rejected|pending)."},
            status=400,
        )
    rec_payload = body.get("rec") if isinstance(body.get("rec"), dict) else None
    server._impr_cache = None
    try:
        from src.agents.mekka import Mekka
        queued_path: str | None = None
        # Passa `rec` para record_decision ativar o bridge hook
        # (snapshot Sage ANTES + write-back no vault). Pre-2026-05-27 esta
        # chamada era sem `rec=`, o que silenciosamente desativava o bridge
        # — bridge.json nunca era criado em 54 IMPs aceitas.
        if status == "accepted" and rec_payload is not None:
            rec_payload.setdefault("id", rec_id)
            ok = Mekka().record_decision(rec_id, status, rec=rec_payload)
            from src.services import improvement_queue
            queued_path = improvement_queue.enqueue_brief(rec_payload) or None
        else:
            ok = Mekka().record_decision(rec_id, status)
        await MekkaRepository.log_event(
            agent="Dashboard",
            event="IMPROVEMENT_DECISION",
            severity="INFO",
            message=f"Operador {status} recomendação {rec_id}",
            payload={"id": rec_id, "status": status, "ok": ok, "queued": queued_path},
        )
        return web.json_response(
            {"ok": ok, "id": rec_id, "status": status, "queued": queued_path},
            status=200,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("improvement decision failed: %s", exc, exc_info=True)
        return web.json_response({"ok": False, "reason": str(exc)}, status=200)


async def handle_pr_status(server, _: web.Request) -> web.Response:
    """GET /api/improvements/pr-status — dev/PR lifecycle per recommendation."""
    try:
        from src.services import pr_tracker
        return web.json_response(pr_tracker.get_pr_status(), status=200)
    except Exception as exc:  # noqa: BLE001
        logger.error("pr-status failed: %s", exc, exc_info=True)
        return web.json_response({}, status=200)


async def handle_decision_history(server, request: web.Request) -> web.Response:
    """GET /api/improvements/decision-history — últimas N decisões do operador.

    Lê audit_log eventos IMPROVEMENT_DECISION + IMPROVEMENT_CLAIMED +
    IMPROVEMENT_PR_APPROVED para dar visibilidade do trabalho do operador.
    Default limit=20.
    """
    try:
        from src.persistence.repository import MekkaRepository as _MR  # noqa: WPS433

        limit_raw = request.query.get("limit", "20")
        try:
            limit = max(1, min(int(limit_raw), 200))
        except (TypeError, ValueError):
            limit = 20

        rows = await _MR.list_recent_audit(limit=500)
        relevant_events = (
            "IMPROVEMENT_DECISION",
            "IMPROVEMENT_CLAIMED",
            "IMPROVEMENT_PR_APPROVED",
        )
        filtered = [r for r in rows if r.event in relevant_events][:limit]
        out = [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "agent": r.agent,
                "event": r.event,
                "severity": r.severity,
                "message": r.message,
                "payload": r.payload or {},
            }
            for r in filtered
        ]
        return web.json_response({"history": out, "count": len(out)}, status=200)
    except Exception as exc:  # noqa: BLE001
        logger.error("decision-history failed: %s", exc, exc_info=True)
        return web.json_response({"history": [], "count": 0, "error": str(exc)}, status=200)


async def handle_kpi(server, _: web.Request) -> web.Response:
    """GET /api/improvements/kpi — department KPI from Sage."""
    out: dict = {"kpi": {}, "latest_snapshot": None, "impact": None}
    try:
        from src.agents.sage import Sage  # noqa: WPS433
        sage = Sage()
        out["kpi"] = sage.kpi()
        out["impact"] = sage.improvement_evaluations()  # Sage v2 per-improvement verdicts
        history = sage._load_history()
        if history:
            out["latest_snapshot"] = history[-1]
    except Exception as exc:  # noqa: BLE001
        logger.warning("improvements kpi failed: %s", exc)
    return web.json_response(out, status=200)


async def handle_claim(server, request: web.Request) -> web.Response:
    """POST /api/improvements/claim — mark accepted brief as in_dev.

    Body: {"id": "<rec_id>", "claimer": "<name|email>"}
    Lets the operator/dev signal "I'm implementing this" so the inbox
    distinguishes work-in-progress from dead-letter queued briefs.
    """
    body = await server._safe_json_body(request) or {}
    rec_id = str(body.get("id") or "").strip()[:64]
    claimer = str(body.get("claimer") or "dev").strip()[:64]
    if not rec_id:
        return web.json_response(
            {"ok": False, "reason": "id obrigatório."}, status=400
        )
    try:
        from src.services import pr_tracker  # noqa: WPS433

        result = pr_tracker.claim_brief(rec_id, claimer=claimer)
        server._impr_cache = None
        await MekkaRepository.log_event(
            agent="Dashboard",
            event="IMPROVEMENT_CLAIMED",
            severity="INFO",
            message=f"{claimer} reivindicou implementação de {rec_id}",
            payload={"rec_id": rec_id, "claimer": claimer, **result},
        )
        return web.json_response({"ok": result.get("ok", False), **result}, status=200)
    except Exception as exc:  # noqa: BLE001
        logger.error("claim failed: %s", exc, exc_info=True)
        return web.json_response({"ok": False, "reason": str(exc)}, status=200)


async def handle_approve_pr(server, request: web.Request) -> web.Response:
    """POST /api/improvements/approve-pr — operator approves a rec's PR."""
    body = await server._safe_json_body(request) or {}
    rec_id = str(body.get("rec_id") or "").strip()[:64]
    confirm = str(body.get("confirm") or "").strip().upper()
    try:
        pr_number = int(body.get("pr_number"))
    except (TypeError, ValueError):
        pr_number = 0
    if not rec_id or pr_number <= 0:
        return web.json_response(
            {"ok": False, "reason": "rec_id e pr_number são obrigatórios."},
            status=400,
        )
    if confirm != "APPROVE":
        return web.json_response(
            {"ok": False, "reason": "confirm=APPROVE obrigatório."}, status=400,
        )
    do_merge = bool(body.get("merge", False))
    try:
        from src.services import pr_tracker
        result = pr_tracker.approve_pr(rec_id, pr_number, do_merge=do_merge)
        if result.get("ok") and not result.get("merged"):
            pr_tracker.mark_merged(rec_id)
        server._impr_cache = None
        await MekkaRepository.log_event(
            agent="Dashboard",
            event="IMPROVEMENT_PR_APPROVED",
            severity="INFO",
            message=f"Operador aprovou PR #{pr_number} ({rec_id}) merge={do_merge}",
            payload={"rec_id": rec_id, "pr_number": pr_number, **result},
        )
        return web.json_response({"ok": result.get("ok", False), **result}, status=200)
    except Exception as exc:  # noqa: BLE001
        logger.error("approve-pr failed: %s", exc, exc_info=True)
        return web.json_response({"ok": False, "reason": str(exc)}, status=200)

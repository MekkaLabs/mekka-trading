"""
src/dashboard/office_v2_endpoints.py
====================================
Helpers for the Office v2 React app's data needs:

- ``build_agents_tasks_payload`` — folds recent audit rows into the
  ``{ items: { stationId: human-message } }`` shape Office v2 expects.
- ``build_audit_feed_payload``   — formats audit rows as ``[{t, who, msg}]``.

Pure data shaping. The aiohttp handler stays in `server.py` and decides
how to wrap these into a response, including timeouts and error handling.
"""

from __future__ import annotations

from typing import Any, Iterable


# Display name → Office v2 station id. Anything not in this map is dropped
# because Office v2 ships with a fixed roster of pixel stations.
AGENT_TO_STATION: dict[str, str] = {
    "Superman": "superman",
    "DoctorStrange": "doctorstrange",
    "BlackPanther": "blackpanther",
    "Thor": "thor",
    "Aquaman": "aquaman",
    "SpiderMan": "spiderman",
    "Vision": "vision",
    "ProfessorX": "professorx",
    "Batman": "batman",
    "IronMan": "ironman",
    "NickFury": "nickfury",
    "PortfolioManager": "portfolio",
    "DailyPnLWriter": "dailypnl",
}


def build_agents_tasks_payload(audits: Iterable[Any]) -> dict[str, Any]:
    """Latest task per agent. Walks audits newest-first (caller passes
    rows in that order) and keeps the first hit for each station id."""
    latest: dict[str, str] = {}
    for row in audits:
        station = AGENT_TO_STATION.get(row.agent)
        if not station or station in latest:
            continue
        event = row.event or ""
        sym = f" ({row.symbol})" if row.symbol else ""
        msg = row.message or event
        latest[station] = f"{event}{sym} — {msg}"[:160]
        if len(latest) == len(AGENT_TO_STATION):
            break
    return {"items": latest, "count": len(latest)}


def build_audit_feed_payload(audits: Iterable[Any]) -> dict[str, Any]:
    """Audit rows in the wire shape Office v2's `fetchFeedEvents` expects.

    Each item is ``{ t: HH:MM:SS, who: AgentName, msg: str(<=160) }``.
    Messages are truncated to keep the payload light over the wire.
    """
    items = [
        {
            "t": r.timestamp.strftime("%H:%M:%S"),
            "who": r.agent,
            "msg": (r.message or r.event or "—")[:160],
        }
        for r in audits
    ]
    return {"items": items, "count": len(items)}

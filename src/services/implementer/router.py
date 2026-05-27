"""
src/services/implementer/router.py
====================================
Router — escolhe o agente vertical pelo ``area`` do brief.

Áreas mapeadas:

  agents      → AgentsImplementer
  backend     → BackendImplementer
  frontend    → FrontendImplementer
  dashboard   → DashboardImplementer
  vault       → AgentsImplementer (proxy — TODOs no vault são metadata sobre código)
  ops, memory, risk, etc → BackendImplementer (default)

Fallback: BackendImplementer (mais conservador).
"""

from __future__ import annotations

from typing import Any, Optional

from src.services.implementer.agents import (
    AgentsImplementer,
    BackendImplementer,
    DashboardImplementer,
    FrontendImplementer,
)
from src.services.implementer.base import BaseImplementer

_REGISTRY: dict[str, type[BaseImplementer]] = {
    "agents": AgentsImplementer,
    "backend": BackendImplementer,
    "frontend": FrontendImplementer,
    "dashboard": DashboardImplementer,
    # Áreas que mapeiam pra implementer existente
    "vault": AgentsImplementer,       # TODOs no vault tipicamente são sobre agentes
    "memory": BackendImplementer,
    "ops": BackendImplementer,
    "risk": BackendImplementer,
    "risk_gates": BackendImplementer,
    "trading_logic": AgentsImplementer,
    "architecture": BackendImplementer,
    "research": BackendImplementer,
    "calibration": AgentsImplementer,
    "ux": FrontendImplementer,
}


def route_implementer(
    brief: dict[str, Any], dry_run: bool = False,
) -> Optional[BaseImplementer]:
    """
    Devolve o implementer apropriado pro brief, ou None se a área é desconhecida.
    """
    area = str(brief.get("area") or "").lower()
    cls = _REGISTRY.get(area) or BackendImplementer  # fallback
    return cls(dry_run=dry_run)


def list_areas() -> dict[str, str]:
    """Mapa area → nome do implementer (pra debug/dashboard)."""
    return {a: cls.__name__ for a, cls in _REGISTRY.items()}

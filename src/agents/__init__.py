"""
src/agents/__init__.py
======================
Mekka Trading — Agent registry.

Layer 1 — Market Analysis (run in parallel by Professor X):
  Superman       → Technical Analysis (OHLCV + indicators)
  DoctorStrange  → Macro Sentiment (CryptoPanic + Fear&Greed + Dominance)
  BlackPanther   → Onchain Intelligence (funding, OI, whale flow)
  Thor           → Volatility Engine (ATR regime + sizing multiplier)
  Aquaman        → Liquidity Analyst (order book depth + slippage)
  SpiderMan      → Anomaly Detector (flash crashes, divergences)

Layer 2 — Strategy:
  Vision         → Predictive Analyst (GPT-4o decision maker)
  ProfessorX     → Swarm Coordinator (parallel Layer-1 fan-out)
  VisionCritic   → Second-look LLM (off by default, Story 031)

Layer 3 — Risk & Execution:
  Batman         → Risk Guardian (deterministic validation gate)
  IronMan        → Hyperliquid Execution Engineer

Layer 4 — Command & Control:
  NickFury         → Mission Commander (top-level orchestrator)
  PortfolioManager → Read-only equity & open-positions snapshot
  Wolverine        → Recovery Agent (monitor cycle + intraday backstop)

Layer 1.5 — Tactical Sub-Loop:
  Flash            → Momentum Scalper (read-only, advisory)

Imports are lazy to keep optional dependencies (ccxt, openai,
hyperliquid-python-sdk) from being pulled at package import time.
"""

from __future__ import annotations

__all__ = [
    "BaseAgent",
    "AgentError",
    # Layer 1 — Analysis
    "Superman",
    "DoctorStrange",
    "BlackPanther",
    "Thor",
    "Aquaman",
    "SpiderMan",
    # Layer 2 — Strategy
    "Vision",
    "ProfessorX",
    "VisionCritic",
    # Layer 3 — Risk & Execution
    "Batman",
    "IronMan",
    # Layer 4 — Command & Control
    "NickFury",
    "PortfolioManager",
    "Wolverine",
    # Layer 1.5 — Tactical
    "Flash",
]


def __getattr__(name: str):  # noqa: N807 — module-level __getattr__
    """Lazy-load agents on first access."""
    if name == "BaseAgent":
        from src.agents.base import BaseAgent
        return BaseAgent
    if name == "AgentError":
        from src.agents.base import AgentError
        return AgentError
    if name == "Superman":
        from src.agents.superman import Superman
        return Superman
    if name == "DoctorStrange":
        from src.agents.doctor_strange import DoctorStrange
        return DoctorStrange
    if name == "BlackPanther":
        from src.agents.black_panther import BlackPanther
        return BlackPanther
    if name == "Thor":
        from src.agents.thor import Thor
        return Thor
    if name == "Aquaman":
        from src.agents.aquaman import Aquaman
        return Aquaman
    if name == "SpiderMan":
        from src.agents.spider_man import SpiderMan
        return SpiderMan
    if name == "Vision":
        from src.agents.vision import Vision
        return Vision
    if name == "ProfessorX":
        from src.agents.professor_x import ProfessorX
        return ProfessorX
    if name == "VisionCritic":
        from src.agents.vision_critic import VisionCritic
        return VisionCritic
    if name == "Batman":
        from src.agents.batman import Batman
        return Batman
    if name == "IronMan":
        from src.agents.iron_man import IronMan
        return IronMan
    if name == "NickFury":
        from src.agents.nick_fury import NickFury
        return NickFury
    if name == "PortfolioManager":
        from src.agents.portfolio_manager import PortfolioManager
        return PortfolioManager
    if name == "Wolverine":
        from src.agents.wolverine import Wolverine
        return Wolverine
    if name == "Flash":
        from src.agents.flash import Flash
        return Flash
    raise AttributeError(f"module 'src.agents' has no attribute {name!r}")

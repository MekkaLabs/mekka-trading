"""
src/models/heroes.py
====================
Canonical roster of hero codenames.

Single source of truth for "Vision", "Batman", "Nick Fury" et al. Used
by:
  • `BaseAgent.__init__(codename=...)` — accepts string OR `HeroName`
  • `MekkaRepository.log_event(agent=...)` — accepts string OR `HeroName.value`
  • `dashboard/server.py::HERO_LAYER` — keys are `HeroName.value`
  • `agents/registry.ts` — names match `HeroName.value` exactly
  • `scripts/check_roster_consistency.py` — normalizes against this enum

The `value` of each member is the **display form** (with spaces and
hyphens), so it matches `agents/registry.ts` 1:1.
"""

from __future__ import annotations

from enum import Enum


class HeroName(str, Enum):
    """The 15 canonical Mekka Trading hero codenames."""

    # Layer 1 — Market Analysis
    SUPERMAN = "Superman"
    DOCTOR_STRANGE = "Doctor Strange"
    BLACK_PANTHER = "Black Panther"
    THOR = "Thor"
    AQUAMAN = "Aquaman"
    SPIDER_MAN = "Spider-Man"

    # Layer 2 — Strategy
    VISION = "Vision"
    PROFESSOR_X = "Professor X"

    # Layer 3 — Risk & Execution
    BATMAN = "Batman"
    IRON_MAN = "Iron Man"

    # Layer 4 — Command & Control
    NICK_FURY = "Nick Fury"
    PORTFOLIO_MANAGER = "Portfolio Manager"

    # Pending (Story 029+)
    WOLVERINE = "Wolverine"
    FLASH = "Flash"
    DEADPOOL = "Deadpool"

    @classmethod
    def normalize(cls, raw: str) -> "HeroName":
        """
        Best-effort lookup that tolerates spaces and hyphens.

        Examples
        --------
        >>> HeroName.normalize("IronMan").value
        'Iron Man'
        >>> HeroName.normalize("Spider-Man").value
        'Spider-Man'
        >>> HeroName.normalize("doctorstrange").value
        'Doctor Strange'
        """
        key = raw.strip().replace("-", "").replace(" ", "").lower()
        for member in cls:
            if member.value.replace("-", "").replace(" ", "").lower() == key:
                return member
        raise ValueError(f"Unknown hero codename: {raw!r}")

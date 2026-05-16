"""
src/services/microagent_registry.py
=====================================
Story 156 — MicroagentRegistry: Regime-Aware Prompts via Markdown Microagents.

Inspirado no sistema de Microagents do OpenHands (OpenHands/OpenHands):
  "Micro-agents are lightweight agents instantiated from natural language
   or minimal interface demonstration, automatable via system message and
   I/O specification alone."
  "Microagents are Markdown files that can include frontmatter for
   configuration, located either in microagents/ (public) or
   .openhands/microagents/ (repository-specific)."

Adaptação para Mekka Trading:
  - Arquivos `.md` em `microagents/` com frontmatter YAML simplificado
  - Cada microagent injeta texto adicional no system prompt do Vision
  - Carregamento automático por regime de mercado (BULL/BEAR/VOLATILE/SIDEWAYS)
  - Suporte a tipos: market (Vision), risk (Batman), system (Nick Fury)
  - Sem nova dependência (usa `re` + `pathlib`)

Formato do arquivo .md:

    ---
    name: bear_market_advisor
    type: market
    triggers: [BEAR, SIDEWAYS]
    ---
    ## Bear Market Trading Rules

    When the market is bearish:
    - Prefer SHORT positions with high confidence (>= 0.80)
    - Reduce position size by 30% vs. bull targets
    - Avoid LONG positions unless RSI < 30 (extreme oversold)

Uso:
    from src.services.microagent_registry import get_microagent_registry

    registry = get_microagent_registry()
    prompt_injection = registry.get_regime_prompt("BEAR")
    # → "## bear_market_advisor\\n\\nWhen the market is bearish:..."

Integração com Vision:
    system_prompt += "\\n\\n" + get_microagent_registry().get_regime_prompt(regime)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Microagent dataclass
# ---------------------------------------------------------------------------

@dataclass
class Microagent:
    """
    A loaded microagent from a .md file.

    Immutable after construction — the content is the prompt injection text.
    """
    name: str
    type: str           # "market" | "risk" | "system"
    triggers: list[str] # e.g. ["BULL", "BEAR"] — uppercased at load time
    content: str        # markdown body (the actual prompt injection)
    source_path: str = ""

    def matches(self, trigger: str, agent_type: str = "") -> bool:
        """True if this microagent should be active for the given trigger."""
        trigger_matches = trigger.upper() in self.triggers
        type_matches = (agent_type == "") or (self.type == agent_type)
        return trigger_matches and type_matches

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "triggers": self.triggers,
            "source": self.source_path,
            "content_length": len(self.content),
        }


# ---------------------------------------------------------------------------
# MicroagentRegistry
# ---------------------------------------------------------------------------

class MicroagentRegistry:
    """
    Registry that loads and indexes microagent .md files.

    Load order:
      1. `microagents/` directory (project-wide, public)
      2. `.openhands/microagents/` directory (repo-specific, mirrors OpenHands)

    Frontmatter is parsed with a minimal regex parser — no PyYAML dependency.
    """

    # Regex: matches "---\n<frontmatter>\n---\n" at start of file
    _FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    # Regex: matches "key: value" lines in frontmatter
    _KV_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)
    # Regex: matches "[item1, item2, item3]" list syntax
    _LIST_RE = re.compile(r"^\[([^\]]*)\]$")

    _SEARCH_DIRS = ["microagents", ".openhands/microagents"]

    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        """
        Args:
            base_dir: Root directory for resolving microagent paths.
                      Defaults to current working directory.
        """
        self._base = Path(base_dir) if base_dir else Path.cwd()
        self._agents: dict[str, Microagent] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> int:
        """
        Scan microagent directories and load all .md files with frontmatter.

        Returns the number of microagents successfully loaded.
        Safe to call multiple times — reloads on each call.
        """
        self._agents.clear()
        count = 0

        for subdir in self._SEARCH_DIRS:
            search_path = self._base / subdir
            if not search_path.exists():
                continue

            for md_path in sorted(search_path.rglob("*.md")):
                try:
                    agent = self._parse_file(md_path)
                    if agent is not None:
                        self._agents[agent.name] = agent
                        count += 1
                        logger.debug(
                            f"[MicroagentRegistry] Loaded {agent.name} "
                            f"(type={agent.type} triggers={agent.triggers})"
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        f"[MicroagentRegistry] Failed to load {md_path}: {exc}"
                    )

        self._loaded = True
        logger.info(
            f"[MicroagentRegistry] Loaded {count} microagents "
            f"from {[str(self._base / d) for d in self._SEARCH_DIRS]}"
        )
        return count

    def _ensure_loaded(self) -> None:
        """Lazy-load on first read access."""
        if not self._loaded:
            self.load()

    def _parse_file(self, path: Path) -> Optional[Microagent]:
        """Parse a .md file and return a Microagent, or None if no frontmatter."""
        text = path.read_text(encoding="utf-8")

        # Must start with frontmatter
        fm_match = self._FRONTMATTER_RE.match(text)
        if not fm_match:
            return None  # plain .md without frontmatter — skip

        frontmatter_text = fm_match.group(1)
        body = text[fm_match.end():].strip()

        if not body:
            return None  # empty body — skip

        # Parse key-value pairs from frontmatter
        meta: dict[str, str | list[str]] = {}
        for kv in self._KV_RE.finditer(frontmatter_text):
            key = kv.group(1).strip()
            raw_val = kv.group(2).strip()

            list_match = self._LIST_RE.match(raw_val)
            if list_match:
                items = [v.strip() for v in list_match.group(1).split(",") if v.strip()]
                meta[key] = items
            else:
                meta[key] = raw_val

        name = str(meta.get("name", path.stem))
        agent_type = str(meta.get("type", "market"))

        triggers_raw = meta.get("triggers", [])
        if isinstance(triggers_raw, list):
            triggers = [t.upper() for t in triggers_raw if t]
        else:
            triggers = [str(triggers_raw).upper()]

        return Microagent(
            name=name,
            type=agent_type,
            triggers=triggers,
            content=body,
            source_path=str(path),
        )

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def get_by_trigger(
        self,
        trigger: str,
        agent_type: str = "",
    ) -> list[Microagent]:
        """
        Return all microagents that match the given trigger (and optionally type).

        Example:
            registry.get_by_trigger("BEAR", agent_type="market")
        """
        self._ensure_loaded()
        return [
            a for a in self._agents.values()
            if a.matches(trigger, agent_type)
        ]

    def get_regime_prompt(self, regime: str) -> str:
        """
        Return concatenated prompt injection for all market-type microagents
        matching the given market regime.

        Used by Vision to inject regime-specific trading guidance:
            system_prompt += "\\n\\n" + registry.get_regime_prompt(regime)

        Returns empty string if no matching microagents (safe for string concat).
        """
        agents = self.get_by_trigger(regime, agent_type="market")
        if not agents:
            return ""
        sections = [f"## Microagent: {a.name}\n\n{a.content}" for a in agents]
        return "\n\n---\n\n".join(sections)

    def get_risk_prompt(self, trigger: str) -> str:
        """Prompt injection for risk-type microagents (Batman integration)."""
        agents = self.get_by_trigger(trigger, agent_type="risk")
        if not agents:
            return ""
        return "\n\n".join(f"## Risk Microagent: {a.name}\n\n{a.content}" for a in agents)

    def get(self, name: str) -> Optional[Microagent]:
        """Get a specific microagent by name."""
        self._ensure_loaded()
        return self._agents.get(name)

    def list_all(self) -> list[dict]:
        """List all loaded microagents (for GET /api/microagents)."""
        self._ensure_loaded()
        return [a.to_dict() for a in self._agents.values()]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of microagents currently loaded."""
        self._ensure_loaded()
        return len(self._agents)

    def summary(self) -> dict:
        """Summary for GET /api/microagents endpoint."""
        self._ensure_loaded()
        by_type: dict[str, int] = {}
        by_trigger: dict[str, int] = {}
        for a in self._agents.values():
            by_type[a.type] = by_type.get(a.type, 0) + 1
            for t in a.triggers:
                by_trigger[t] = by_trigger.get(t, 0) + 1

        return {
            "total": self.count,
            "by_type": by_type,
            "by_trigger": by_trigger,
            "agents": self.list_all(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[MicroagentRegistry] = None


def get_microagent_registry(base_dir: Optional[str | Path] = None) -> MicroagentRegistry:
    """
    Return the global MicroagentRegistry singleton.

    `base_dir` is only used on first call (construction).
    Defaults to current working directory.
    """
    global _instance
    if _instance is None:
        _instance = MicroagentRegistry(base_dir=base_dir)
    return _instance


def reset_microagent_registry() -> None:
    """Destroy singleton — used in tests."""
    global _instance
    _instance = None

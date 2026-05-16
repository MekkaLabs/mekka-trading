"""
tests/test_story_156_microagent_registry.py
=============================================
Story 156 — MicroagentRegistry: Regime-Aware Prompts via Markdown Microagents.

Inspirado no sistema de microagents do OpenHands:
  "Microagents are Markdown files that can include frontmatter for
   configuration, located either in microagents/ (public) or
   .openhands/microagents/ (repository-specific)."

Testa:
- Microagent dataclass: matches(), to_dict()
- MicroagentRegistry: load(), _parse_file(), get_by_trigger(), get_regime_prompt()
- Frontmatter parsing (name, type, triggers como lista)
- Lazy loading (ensure_loaded)
- Singleton + reset
- Integração com arquivos de microagents reais do projeto
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers — cria arquivos .md temporários para testes
# ---------------------------------------------------------------------------

def _write_md(dir_path: Path, filename: str, content: str) -> Path:
    p = dir_path / filename
    p.write_text(content, encoding="utf-8")
    return p


BULL_MD = """\
---
name: test_bull_advisor
type: market
triggers: [BULL]
---
## Bull Market Rules

- Prefer LONG positions
- Confidence >= 0.65
"""

BEAR_MD = """\
---
name: test_bear_advisor
type: market
triggers: [BEAR, SIDEWAYS]
---
## Bear Market Rules

- Require confidence >= 0.75
- Avoid LONGs in downtrend
"""

VOLATILE_MD = """\
---
name: test_volatile_advisor
type: market
triggers: [VOLATILE]
---
## Volatile Rules

- Reduce size by 30%
"""

RISK_MD = """\
---
name: test_risk_small_cap
type: risk
triggers: [SMALL_CAP]
---
## Small Cap Risk

- Max leverage 2x
"""

NO_FRONTMATTER_MD = """\
# Just a plain markdown file

No frontmatter here.
"""

EMPTY_BODY_MD = """\
---
name: empty_body
type: market
triggers: [BULL]
---
"""


# ---------------------------------------------------------------------------
# Microagent dataclass
# ---------------------------------------------------------------------------

class TestMicroagent:
    def test_matches_trigger_and_type(self):
        from src.services.microagent_registry import Microagent
        a = Microagent(name="bull", type="market", triggers=["BULL"], content="text")
        assert a.matches("BULL", agent_type="market")
        assert a.matches("BULL")  # type filter empty = match all
        assert not a.matches("BEAR")
        assert not a.matches("BULL", agent_type="risk")

    def test_matches_case_insensitive_trigger(self):
        from src.services.microagent_registry import Microagent
        a = Microagent(name="bear", type="market", triggers=["BEAR", "SIDEWAYS"], content="")
        assert a.matches("bear")
        assert a.matches("sideways")
        assert a.matches("SIDEWAYS")

    def test_to_dict_structure(self):
        from src.services.microagent_registry import Microagent
        a = Microagent(
            name="test", type="risk", triggers=["SMALL_CAP"],
            content="x" * 100, source_path="/tmp/test.md"
        )
        d = a.to_dict()
        assert d["name"] == "test"
        assert d["type"] == "risk"
        assert d["triggers"] == ["SMALL_CAP"]
        assert d["content_length"] == 100


# ---------------------------------------------------------------------------
# MicroagentRegistry — parsing
# ---------------------------------------------------------------------------

class TestMicroagentRegistryParsing:
    def test_loads_bull_microagent(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "bull.md", BULL_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            count = registry.load()
            assert count == 1
            assert registry.count == 1

    def test_loads_multiple_microagents(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "bull.md", BULL_MD)
            _write_md(md_dir, "bear.md", BEAR_MD)
            _write_md(md_dir, "volatile.md", VOLATILE_MD)
            _write_md(md_dir, "risk.md", RISK_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            count = registry.load()
            assert count == 4

    def test_skips_no_frontmatter(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "plain.md", NO_FRONTMATTER_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            count = registry.load()
            assert count == 0

    def test_skips_empty_body(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "empty.md", EMPTY_BODY_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            count = registry.load()
            assert count == 0

    def test_empty_directory_returns_zero(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = MicroagentRegistry(base_dir=tmpdir)
            count = registry.load()
            assert count == 0

    def test_missing_directory_returns_zero(self):
        from src.services.microagent_registry import MicroagentRegistry
        registry = MicroagentRegistry(base_dir="/nonexistent/path/xyz")
        count = registry.load()
        assert count == 0

    def test_parses_name_from_frontmatter(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "bull.md", BULL_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            registry.load()
            agent = registry.get("test_bull_advisor")
            assert agent is not None
            assert agent.name == "test_bull_advisor"

    def test_parses_triggers_as_list(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "bear.md", BEAR_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            registry.load()
            agent = registry.get("test_bear_advisor")
            assert agent is not None
            assert "BEAR" in agent.triggers
            assert "SIDEWAYS" in agent.triggers

    def test_parses_type_correctly(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "risk.md", RISK_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            registry.load()
            agent = registry.get("test_risk_small_cap")
            assert agent is not None
            assert agent.type == "risk"

    def test_content_is_body_without_frontmatter(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(md_dir, "bull.md", BULL_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            registry.load()
            agent = registry.get("test_bull_advisor")
            assert agent is not None
            assert "Bull Market Rules" in agent.content
            assert "---" not in agent.content  # frontmatter stripped


# ---------------------------------------------------------------------------
# MicroagentRegistry — query paths
# ---------------------------------------------------------------------------

class TestMicroagentRegistryQuery:
    def _make_registry(self, tmpdir: Path) -> "MicroagentRegistry":
        from src.services.microagent_registry import MicroagentRegistry
        md_dir = tmpdir / "microagents"
        md_dir.mkdir()
        _write_md(md_dir, "bull.md", BULL_MD)
        _write_md(md_dir, "bear.md", BEAR_MD)
        _write_md(md_dir, "volatile.md", VOLATILE_MD)
        _write_md(md_dir, "risk.md", RISK_MD)
        registry = MicroagentRegistry(base_dir=str(tmpdir))
        registry.load()
        return registry

    def test_get_by_trigger_bull(self, tmp_path):
        registry = self._make_registry(tmp_path)
        agents = registry.get_by_trigger("BULL")
        assert len(agents) == 1
        assert agents[0].name == "test_bull_advisor"

    def test_get_by_trigger_bear_sideways(self, tmp_path):
        registry = self._make_registry(tmp_path)
        bear = registry.get_by_trigger("BEAR")
        sideways = registry.get_by_trigger("SIDEWAYS")
        assert len(bear) == 1
        assert len(sideways) == 1
        assert bear[0].name == sideways[0].name  # same microagent

    def test_get_by_trigger_with_type_filter(self, tmp_path):
        registry = self._make_registry(tmp_path)
        # SMALL_CAP with type=risk → 1 match
        agents = registry.get_by_trigger("SMALL_CAP", agent_type="risk")
        assert len(agents) == 1
        # SMALL_CAP with type=market → 0 matches
        market_agents = registry.get_by_trigger("SMALL_CAP", agent_type="market")
        assert len(market_agents) == 0

    def test_get_by_trigger_unknown(self, tmp_path):
        registry = self._make_registry(tmp_path)
        agents = registry.get_by_trigger("UNKNOWN_REGIME")
        assert agents == []

    def test_get_regime_prompt_bull(self, tmp_path):
        registry = self._make_registry(tmp_path)
        prompt = registry.get_regime_prompt("BULL")
        assert "Bull Market Rules" in prompt
        assert len(prompt) > 0

    def test_get_regime_prompt_bear(self, tmp_path):
        registry = self._make_registry(tmp_path)
        prompt = registry.get_regime_prompt("BEAR")
        assert "Bear Market Rules" in prompt

    def test_get_regime_prompt_unknown_returns_empty(self, tmp_path):
        registry = self._make_registry(tmp_path)
        prompt = registry.get_regime_prompt("UNKNOWN")
        assert prompt == ""

    def test_get_risk_prompt(self, tmp_path):
        registry = self._make_registry(tmp_path)
        prompt = registry.get_risk_prompt("SMALL_CAP")
        assert "Small Cap Risk" in prompt

    def test_list_all(self, tmp_path):
        registry = self._make_registry(tmp_path)
        agents = registry.list_all()
        assert len(agents) == 4
        names = [a["name"] for a in agents]
        assert "test_bull_advisor" in names

    def test_summary_structure(self, tmp_path):
        registry = self._make_registry(tmp_path)
        s = registry.summary()
        assert s["total"] == 4
        assert "by_type" in s
        assert "by_trigger" in s
        assert s["by_type"]["market"] == 3  # bull, bear, volatile
        assert s["by_type"]["risk"] == 1

    def test_lazy_loading_on_first_read(self):
        from src.services.microagent_registry import MicroagentRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = Path(tmpdir) / "microagents"
            md_dir.mkdir()
            _write_md(Path(md_dir), "bull.md", BULL_MD)
            registry = MicroagentRegistry(base_dir=tmpdir)
            # Do NOT call load() explicitly — first query triggers it
            assert not registry._loaded
            agents = registry.get_by_trigger("BULL")
            assert registry._loaded
            assert len(agents) == 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestMicroagentRegistrySingleton:
    def setup_method(self):
        from src.services.microagent_registry import reset_microagent_registry
        reset_microagent_registry()

    def teardown_method(self):
        from src.services.microagent_registry import reset_microagent_registry
        reset_microagent_registry()

    def test_singleton_same_instance(self):
        from src.services.microagent_registry import get_microagent_registry
        r1 = get_microagent_registry()
        r2 = get_microagent_registry()
        assert r1 is r2

    def test_reset_creates_fresh(self):
        from src.services.microagent_registry import get_microagent_registry, reset_microagent_registry
        r1 = get_microagent_registry()
        reset_microagent_registry()
        r2 = get_microagent_registry()
        assert r1 is not r2


# ---------------------------------------------------------------------------
# Integration — real microagents/ directory
# ---------------------------------------------------------------------------

class TestRealMicroagents:
    """Verify that the built-in microagent files load correctly."""

    def test_real_microagents_directory_exists(self):
        """The project should have a microagents/ directory."""
        import os
        # Try to find microagents dir relative to project root
        for candidate in ["microagents", "../microagents"]:
            if Path(candidate).exists():
                assert True
                return
        # If running from tests/ dir, check parent
        project_root = Path(__file__).parent.parent
        ma_dir = project_root / "microagents"
        assert ma_dir.exists(), f"microagents/ not found at {ma_dir}"

    def test_real_microagents_load(self):
        """All built-in microagent files should parse without errors."""
        from src.services.microagent_registry import MicroagentRegistry
        project_root = Path(__file__).parent.parent
        registry = MicroagentRegistry(base_dir=str(project_root))
        count = registry.load()
        assert count >= 4, f"Expected at least 4 built-in microagents, got {count}"

    def test_bull_regime_prompt_available(self):
        """BULL regime should have a prompt injection from built-in microagents."""
        from src.services.microagent_registry import MicroagentRegistry
        project_root = Path(__file__).parent.parent
        registry = MicroagentRegistry(base_dir=str(project_root))
        registry.load()
        prompt = registry.get_regime_prompt("BULL")
        assert len(prompt) > 50, "BULL prompt injection too short or missing"

    def test_bear_regime_prompt_available(self):
        from src.services.microagent_registry import MicroagentRegistry
        project_root = Path(__file__).parent.parent
        registry = MicroagentRegistry(base_dir=str(project_root))
        registry.load()
        prompt = registry.get_regime_prompt("BEAR")
        assert len(prompt) > 50

    def test_volatile_regime_prompt_available(self):
        from src.services.microagent_registry import MicroagentRegistry
        project_root = Path(__file__).parent.parent
        registry = MicroagentRegistry(base_dir=str(project_root))
        registry.load()
        prompt = registry.get_regime_prompt("VOLATILE")
        assert len(prompt) > 50

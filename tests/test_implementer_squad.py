"""
tests/test_implementer_squad.py
=================================
Suite cobrindo o Implementer Squad: safety, cost, deterministic patterns,
recipe fallback, router.

Não testa execução LLM real (mock fora de escopo desta sessão); testa que
LLM layer falha graceful quando `IMPLEMENTER_LLM_ENABLED=false`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.implementer import cost, safety
from src.services.implementer.base import (
    ImplementerResult,
    ImplementerStatus,
)
from src.services.implementer.layers import deterministic, recipe, llm
from src.services.implementer.router import route_implementer, list_areas


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------


class TestSafetyProtected:
    def test_settings_protected(self):
        assert safety.is_protected("src/config/settings.py")

    def test_batman_protected(self):
        assert safety.is_protected("src/agents/batman.py")

    def test_iron_man_protected(self):
        assert safety.is_protected("src/agents/iron_man.py")

    def test_env_protected(self):
        assert safety.is_protected(".env")
        assert safety.is_protected(".env.example")

    def test_data_dir_protected(self):
        assert safety.is_protected("data/anything.json")
        assert safety.is_protected("data/memory/x.json")

    def test_normal_agent_not_protected(self):
        assert not safety.is_protected("src/agents/superman.py")
        assert not safety.is_protected("src/agents/vision.py")
        assert not safety.is_protected("src/services/foo.py")


class TestSafetyBlast:
    def test_within_caps(self):
        ok, reason = safety.check_blast_radius(["a.py", "b.py"], 100)
        assert ok, reason

    def test_too_many_files(self):
        files = [f"f{i}.py" for i in range(safety.MAX_FILES_PER_IMP + 1)]
        ok, reason = safety.check_blast_radius(files, 50)
        assert not ok
        assert "too many files" in reason

    def test_too_many_lines(self):
        ok, reason = safety.check_blast_radius(
            ["a.py"], safety.MAX_LINES_PER_IMP + 1
        )
        assert not ok
        assert "too many lines" in reason


# ---------------------------------------------------------------------------
# Cost cap
# ---------------------------------------------------------------------------


class TestCost:
    def test_estimate_cost_known_model(self):
        # Sonnet: $3/M input, $15/M output → 1M+1M = 3+15 = 18
        c = cost.estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert c == 18.0

    def test_estimate_cost_unknown_falls_back(self):
        # Modelo desconhecido cai pra Sonnet (conservador)
        c = cost.estimate_cost_usd("invented-model-9000", 1_000_000, 0)
        assert c == 3.0

    def test_under_cap_starts_true(self, tmp_path, monkeypatch):
        # Move COST_FILE pra tmp pra não bagunçar prod
        monkeypatch.setattr(cost, "_COST_FILE", tmp_path / "costs.json")
        ok, _ = cost.is_under_cap()
        assert ok


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class TestRouter:
    def test_route_by_area(self):
        impl = route_implementer({"area": "backend"})
        assert impl.name == "BackendImplementer"
        impl = route_implementer({"area": "frontend"})
        assert impl.name == "FrontendImplementer"
        impl = route_implementer({"area": "agents"})
        assert impl.name == "AgentsImplementer"
        impl = route_implementer({"area": "dashboard"})
        assert impl.name == "DashboardImplementer"

    def test_route_unknown_area_fallback(self):
        impl = route_implementer({"area": "unknown_xyz"})
        # Fallback é BackendImplementer (mais conservador)
        assert impl.name == "BackendImplementer"

    def test_route_vault_to_agents(self):
        impl = route_implementer({"area": "vault"})
        assert impl.name == "AgentsImplementer"

    def test_list_areas_complete(self):
        areas = list_areas()
        for key in ("agents", "backend", "frontend", "dashboard"):
            assert key in areas


# ---------------------------------------------------------------------------
# Deterministic patterns
# ---------------------------------------------------------------------------


class TestDeterministicPatterns:
    def test_pattern_add_test_stub_matches(self):
        brief = {
            "title": "Cobertura: 5 services sem teste",
            "description": "Faltam: `foo`, `bar`, `baz`",
            "area": "backend",
        }
        p = deterministic.detect_pattern(brief)
        assert p.matched
        assert p.name == "add_test_stub"
        assert "foo" in p.payload["candidates"]

    def test_pattern_no_match_for_refactor(self):
        # Refator de arquivo grande NÃO deve casar (precisa LLM/recipe)
        brief = {
            "title": "Refatorar iron_man.py (2203 linhas)",
            "description": "arquivo muito grande",
            "area": "agents",
        }
        p = deterministic.detect_pattern(brief)
        assert not p.matched

    def test_pattern_remove_todo_requires_keyword(self):
        # Falso match anterior: 'iron_man.py: 1785 linhas' tinha :número
        # mas o regex era genérico demais. Hoje exige palavra TODO/FIXME/XXX/HACK
        # próxima — então este brief sobre tamanho de arquivo não deve casar.
        brief = {
            "title": "iron_man.py com 1785 linhas",
            "description": "arquivo muito grande, considerar refatorar",
            "evidence": "src/agents/iron_man.py: 1785 linhas",
        }
        p = deterministic.detect_pattern(brief)
        assert not p.matched, "não deve casar com brief sobre tamanho de arquivo"

    def test_pattern_remove_todo_matches_with_keyword(self):
        brief = {
            "title": "TODO em foo.py:42",
            "description": "remover TODO inline",
            "evidence": "foo.py:42 — TODO: cleanup needed",
        }
        p = deterministic.detect_pattern(brief)
        assert p.matched
        assert p.name == "remove_inline_todo"
        assert p.payload["path"] == "foo.py"
        assert p.payload["line"] == 42


# ---------------------------------------------------------------------------
# Recipe fallback
# ---------------------------------------------------------------------------


class TestRecipe:
    def test_write_recipe_creates_file(self, tmp_path, monkeypatch):
        # Redireciona _RECIPES_DIR pra tmp
        monkeypatch.setattr(recipe, "_RECIPES_DIR", tmp_path)
        brief = {
            "rec_id": "abc12345",
            "title": "Test recipe",
            "area": "backend",
            "impact": "MEDIUM",
            "description": "do X",
        }
        result = ImplementerResult(
            rec_id="abc12345", agent="test", status=ImplementerStatus.SKIPPED,
        )
        path_str = recipe.write_recipe(brief, result)
        assert path_str
        assert Path(path_str).exists()
        assert result.status == ImplementerStatus.RECIPE_ONLY
        assert result.layer_used == "recipe"
        text = Path(path_str).read_text(encoding="utf-8")
        assert "IMP-abc12345" in text
        assert "Test recipe" in text
        assert "Passos sugeridos" in text


# ---------------------------------------------------------------------------
# LLM layer (gated)
# ---------------------------------------------------------------------------


class TestLLMGate:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("IMPLEMENTER_LLM_ENABLED", raising=False)
        assert not llm.is_llm_enabled()

    def test_enabled_with_flag(self, monkeypatch):
        monkeypatch.setenv("IMPLEMENTER_LLM_ENABLED", "true")
        assert llm.is_llm_enabled()

    def test_try_apply_disabled_returns_false(self, monkeypatch):
        monkeypatch.delenv("IMPLEMENTER_LLM_ENABLED", raising=False)
        result = ImplementerResult(
            rec_id="x", agent="test", status=ImplementerStatus.SKIPPED,
        )
        applied = llm.try_apply({"rec_id": "x", "title": "y"}, result)
        assert not applied
        assert "disabled" in result.reason.lower()

    def test_try_apply_enabled_but_not_authorized_returns_false(self, monkeypatch):
        # Sem IMPLEMENTER_LLM_AUTHORIZED, fica em skeleton mode
        monkeypatch.setenv("IMPLEMENTER_LLM_ENABLED", "true")
        monkeypatch.delenv("IMPLEMENTER_LLM_AUTHORIZED", raising=False)
        result = ImplementerResult(
            rec_id="x", agent="test", status=ImplementerStatus.SKIPPED,
        )
        applied = llm.try_apply({"rec_id": "x", "title": "y"}, result)
        assert not applied
        assert "skeleton" in result.reason.lower() or "auth" in result.reason.lower()


# ---------------------------------------------------------------------------
# End-to-end via implementer
# ---------------------------------------------------------------------------


class TestImplementerLifecycle:
    def test_dry_run_no_pattern_writes_recipe(self, tmp_path, monkeypatch):
        # Redireciona recipes pra tmp
        monkeypatch.setattr(recipe, "_RECIPES_DIR", tmp_path)
        # LLM disabled (default)
        monkeypatch.delenv("IMPLEMENTER_LLM_ENABLED", raising=False)
        brief = {
            "rec_id": "test01",
            "id": "test01",
            "title": "Algo complexo — refator multi-file",
            "area": "backend",
            "impact": "MEDIUM",
            "description": "Não casa com nenhum pattern",
        }
        impl = route_implementer(brief, dry_run=True)
        result = impl.implement(brief)
        # Sem pattern + sem LLM = recipe
        assert result.status == ImplementerStatus.RECIPE_ONLY
        assert result.layer_used == "recipe"
        assert result.recipe_path

    def test_protected_path_blocked(self, monkeypatch):
        # Pattern remove_inline_todo apontando pra path protegido
        brief = {
            "rec_id": "test02",
            "id": "test02",
            "title": "TODO em src/agents/iron_man.py:42",
            "area": "agents",
            "impact": "LOW",
            "description": "TODO: cleanup",
            "evidence": "src/agents/iron_man.py:42 — TODO",
        }
        impl = route_implementer(brief, dry_run=True)
        result = impl.implement(brief)
        # iron_man.py é protegido → BLOCKED
        assert result.status == ImplementerStatus.BLOCKED
        assert "PROTECTED" in result.reason

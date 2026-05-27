"""
tests/test_vertical_scanners.py
=================================
Suite cobrindo os 4 scanners verticais novos:
agents_scanner, backend_scanner, frontend_scanner, dashboard_scanner.

Cada teste:
  - valida que ``scan_proposals(N)`` retorna list[ImprovementProposal]
  - valida que cada proposal tem area = vertical correta
  - valida fail-silent (não levanta exceção mesmo com filesystem corrupto)
"""

from __future__ import annotations

import pytest

from src.agents.beast import ImprovementProposal
from src.agents.agents_scanner import scan_proposals as scan_agents
from src.agents.backend_scanner import scan_proposals as scan_backend
from src.agents.frontend_scanner import scan_proposals as scan_frontend
from src.agents.dashboard_scanner import scan_proposals as scan_dashboard


def _validate_proposals(proposals, expected_area: str, max_n: int):
    """Helper: cada proposta deve ser ImprovementProposal com area correta."""
    assert isinstance(proposals, list)
    assert len(proposals) <= max_n
    for p in proposals:
        assert isinstance(p, ImprovementProposal)
        assert p.title
        assert p.impact in ("HIGH", "MEDIUM", "LOW")
        assert p.area == expected_area, (
            f"proposal '{p.title}' tem area '{p.area}', esperado '{expected_area}'"
        )
        assert p.evidence
        assert p.description


class TestAgentsScanner:
    def test_returns_proposals(self):
        out = scan_agents(max_proposals=10)
        _validate_proposals(out, "agents", 10)

    def test_detects_god_files(self):
        # iron_man.py e nick_fury.py são god-files conhecidos
        out = scan_agents(max_proposals=20)
        titles = [p.title for p in out]
        assert any("iron_man" in t for t in titles), (
            f"esperava IMP sobre iron_man.py em {titles}"
        )


class TestBackendScanner:
    def test_returns_proposals(self):
        out = scan_backend(max_proposals=10)
        _validate_proposals(out, "backend", 10)

    def test_doesnt_touch_protected_paths(self):
        # Backend scanner NÃO deve propor mudança em settings.py
        # (não tem detecção dele de qualquer jeito mas double-check)
        out = scan_backend(max_proposals=20)
        for p in out:
            assert "config/settings.py" not in p.evidence


class TestFrontendScanner:
    def test_returns_proposals(self):
        out = scan_frontend(max_proposals=10)
        _validate_proposals(out, "frontend", 10)

    def test_excludes_vendored_libs(self):
        # React/Babel são libs vendored — não devem aparecer
        out = scan_frontend(max_proposals=20)
        titles = [p.title.lower() for p in out]
        for forbidden in ("react.js", "react-dom", "babel"):
            assert not any(forbidden in t for t in titles), (
                f"vendored lib '{forbidden}' apareceu em titles: {titles}"
            )

    def test_skips_legacy_dirs(self):
        # office_v2 é legacy — não deve aparecer
        out = scan_frontend(max_proposals=20)
        for p in out:
            assert "office_v2/" not in p.evidence
            assert "office-v2-src/" not in p.evidence


class TestDashboardScanner:
    def test_returns_proposals(self):
        out = scan_dashboard(max_proposals=10)
        _validate_proposals(out, "dashboard", 10)

    def test_detects_server_god_file(self):
        # server.py é gigante (~7000 linhas) — deve ser flagged
        out = scan_dashboard(max_proposals=20)
        titles = [p.title for p in out]
        assert any("server.py" in t for t in titles), (
            f"server.py deveria estar em IMPs: {titles}"
        )


class TestScannersFailSilent:
    """Mesmo com erro interno, scanners devem retornar lista (não levantar)."""

    def test_agents_fail_silent_returns_list(self, monkeypatch):
        # Força exception ao listar arquivos
        from src.agents import agents_scanner
        def broken(): raise RuntimeError("filesystem corrupted")
        monkeypatch.setattr(agents_scanner, "_iter_agents", broken)
        out = scan_agents()
        assert out == []

    def test_backend_fail_silent_returns_list(self, monkeypatch):
        from src.agents import backend_scanner
        def broken(): raise RuntimeError("oops")
        monkeypatch.setattr(backend_scanner, "_iter_backend_files", broken)
        out = scan_backend()
        assert out == []

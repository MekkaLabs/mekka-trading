"""
tests/test_prompt_engineering.py
=================================
Cobertura do agente Prometheus.

Áreas:
- extractor: AST + heurística de role
- auditor: scorecard determinístico
- catalog: persistência JSON, upsert idempotente, fallback
- prompt_registry bridge: register_prompt_for_audit não quebra trading
- isolamento: Prometheus indisponível não afeta runtime
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from src.prompt_engineering import Prometheus
from src.prompt_engineering.auditor import audit_text
from src.prompt_engineering.catalog import PromptCatalog, is_catalog_enabled
from src.prompt_engineering.extractor import extract_from_file
from src.prompt_engineering.models import (
    AuditDimension,
    ExtractedPrompt,
    PromptRecord,
    Scorecard,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_python_file(tmp_path: Path) -> Path:
    """Arquivo Python com 2 prompts hardcoded."""
    src = tmp_path / "fake_agent.py"
    src.write_text('''
"""Fake agent for testing."""

_SYSTEM_PROMPT = """Você é Vision, IA de trading. Seu papel é decidir.
Retorne JSON com schema TradingSignal. Nunca aja em anomalia HIGH.
Exemplo: {"action": "BUY", "confidence": 0.8}.
Considere: trend, sentiment, volatility. Evite hipóteses sem dado.
"""

_PRE_REASONING_SYSTEM = """Você analisa o contexto antes da decisão final.
Liste 3 fatores principais. Use formato markdown."""

DEBUG = "short string ignored"

X = 42
''', encoding="utf-8")
    return src


@pytest.fixture
def tmp_catalog_path(tmp_path: Path) -> Path:
    return tmp_path / "catalog.json"


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class TestExtractor:
    def test_extracts_two_prompts(self, tmp_python_file: Path) -> None:
        prompts = extract_from_file(tmp_python_file)
        assert len(prompts) == 2
        names = [p.variable_name for p in prompts]
        assert "_SYSTEM_PROMPT" in names
        assert "_PRE_REASONING_SYSTEM" in names

    def test_ignores_short_strings(self, tmp_python_file: Path) -> None:
        prompts = extract_from_file(tmp_python_file)
        names = [p.variable_name for p in prompts]
        assert "DEBUG" not in names  # "short string ignored" < 80 chars
        assert "X" not in names      # int

    def test_detects_role_system(self, tmp_python_file: Path) -> None:
        prompts = extract_from_file(tmp_python_file)
        sys_prompt = next(p for p in prompts if p.variable_name == "_SYSTEM_PROMPT")
        assert sys_prompt.detected_role == "system"

    def test_detects_role_pre_reasoning(self, tmp_python_file: Path) -> None:
        prompts = extract_from_file(tmp_python_file)
        pre = next(p for p in prompts if p.variable_name == "_PRE_REASONING_SYSTEM")
        assert pre.detected_role == "pre_reasoning"

    def test_fingerprint_stable(self, tmp_python_file: Path) -> None:
        prompts1 = extract_from_file(tmp_python_file)
        prompts2 = extract_from_file(tmp_python_file)
        for p1, p2 in zip(prompts1, prompts2):
            assert p1.fingerprint == p2.fingerprint
            assert len(p1.fingerprint) == 16

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        result = extract_from_file(tmp_path / "no_such.py")
        assert result == []

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(:\n    pass\n", encoding="utf-8")
        assert extract_from_file(bad) == []


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------


class TestAuditor:
    def test_well_formed_prompt_scores_high(self) -> None:
        text = """Você é Vision, agente de trading IA. Seu objetivo é decidir BUY/SELL/HOLD.
        Retorne JSON estrito no formato {"action": "BUY", "confidence": 0.8}.
        Passo 1: analise o trend. Passo 2: considere o sentiment.
        Nunca opere em anomalia HIGH. Evite hipóteses sem dado concreto.
        Exemplo aceito: {"action": "HOLD", "confidence": 0.4}.
        Critério de aceite: confidence ∈ [0,1].
        ```json
        {"action": "BUY"}
        ```
        """
        sc = audit_text(text)
        assert sc.score_total >= 24
        assert sc.health in {"GOOD", "EXCELLENT"}

    def test_vague_prompt_scores_low(self) -> None:
        text = "Talvez você possa tentar pensar sobre o mercado, se possível. " * 5
        sc = audit_text(text)
        assert sc.score_total < 24
        # Hallucination risk deve estar baixo
        halluc = sc.by_dimension(AuditDimension.HALLUCINATION_RISK)
        assert halluc is not None
        assert halluc.score <= 7

    def test_all_dimensions_present(self) -> None:
        sc = audit_text("Você é um agente. Retorne JSON. Nunca minta. Exemplo:```{}```")
        assert len(sc.dimensions) == 4
        dims_seen = {d.dimension for d in sc.dimensions}
        assert dims_seen == set(AuditDimension)

    def test_score_total_matches_sum(self) -> None:
        sc = audit_text("Você é um agente. Retorne JSON. Nunca minta. Passo 1: analise.")
        assert sc.score_total == sum(d.score for d in sc.dimensions)
        assert 0 <= sc.score_total <= 40

    def test_health_thresholds(self) -> None:
        sc1 = Scorecard(dimensions=[], score_total=35, recommendations=[])
        assert sc1.health == "EXCELLENT"
        sc2 = Scorecard(dimensions=[], score_total=25, recommendations=[])
        assert sc2.health == "GOOD"
        sc3 = Scorecard(dimensions=[], score_total=18, recommendations=[])
        assert sc3.health == "NEEDS_WORK"
        sc4 = Scorecard(dimensions=[], score_total=10, recommendations=[])
        assert sc4.health == "CRITICAL"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class TestCatalog:
    def _make_record(self, name: str = "test_prompt", content: str = "x" * 100) -> PromptRecord:
        prompt = ExtractedPrompt(
            source_file="src/test.py",
            variable_name="TEST",
            line_number=1,
            content=content,
            fingerprint="a" * 16,
            detected_role="system",
        )
        return PromptRecord(name=name, fingerprint="a" * 16, extracted=prompt)

    def test_save_and_load_roundtrip(self, tmp_catalog_path: Path) -> None:
        cat = PromptCatalog(path=tmp_catalog_path)
        cat.upsert(self._make_record())
        assert cat.save() is True
        assert tmp_catalog_path.exists()

        cat2 = PromptCatalog(path=tmp_catalog_path)
        records = cat2.all()
        assert len(records) == 1
        assert records[0].name == "test_prompt"

    def test_upsert_unchanged_when_same_fingerprint(self, tmp_catalog_path: Path) -> None:
        cat = PromptCatalog(path=tmp_catalog_path)
        status1 = cat.upsert(self._make_record())
        status2 = cat.upsert(self._make_record())
        assert status1 == "created"
        assert status2 == "unchanged"

    def test_upsert_updated_when_different_fingerprint(self, tmp_catalog_path: Path) -> None:
        cat = PromptCatalog(path=tmp_catalog_path)
        cat.upsert(self._make_record())
        new = self._make_record()
        new.fingerprint = "b" * 16
        new.extracted.fingerprint = "b" * 16
        status = cat.upsert(new)
        assert status == "updated"

    def test_missing_file_returns_empty(self, tmp_catalog_path: Path) -> None:
        cat = PromptCatalog(path=tmp_catalog_path)
        assert cat.load() == 0
        assert cat.all() == []

    def test_corrupt_file_returns_empty(self, tmp_catalog_path: Path) -> None:
        tmp_catalog_path.write_text("not json {", encoding="utf-8")
        cat = PromptCatalog(path=tmp_catalog_path)
        assert cat.load() == 0


# ---------------------------------------------------------------------------
# Prometheus orchestrator
# ---------------------------------------------------------------------------


class TestPrometheus:
    def test_audit_returns_scorecard(self, tmp_python_file: Path) -> None:
        p = Prometheus(repo_root=tmp_python_file.parent)
        prompts = p.extract(tmp_python_file)
        assert prompts
        sc = p.audit(prompts[0])
        assert isinstance(sc, Scorecard)
        assert 0 <= sc.score_total <= 40

    def test_register_no_op_when_disabled(self, tmp_python_file: Path, monkeypatch) -> None:
        monkeypatch.delenv("PROMETHEUS_CATALOG_ENABLED", raising=False)
        p = Prometheus(repo_root=tmp_python_file.parent)
        # passar catalog_path=None força default + flag de env
        prompts = p.extract(tmp_python_file)
        # Como construímos Prometheus() sem catalog_path explícito, catálogo
        # depende da env var. Sem ela, register() é no-op.
        # (No nosso teste vamos validar via prompt_registry bridge — abaixo.)
        sc = p.audit(prompts[0])
        # Sem env var nem catalog_path explícito → desabilitado:
        if not is_catalog_enabled():
            status, record = p.register(prompts[0], scorecard=sc)
            assert status is None
            assert record is None

    def test_register_when_enabled(
        self, tmp_python_file: Path, tmp_catalog_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("PROMETHEUS_CATALOG_ENABLED", "true")
        p = Prometheus(repo_root=tmp_python_file.parent, catalog_path=tmp_catalog_path)
        prompts = p.extract(tmp_python_file)
        sc = p.audit(prompts[0])
        status, record = p.register(prompts[0], scorecard=sc)
        assert status == "created"
        assert record is not None
        assert tmp_catalog_path.exists()

    def test_report_text_includes_score(self, tmp_python_file: Path) -> None:
        p = Prometheus(repo_root=tmp_python_file.parent)
        prompts = p.extract(tmp_python_file)
        sc = p.audit(prompts[0])
        report = p.report_text(prompts[0], sc)
        assert "SCORECARD" in report
        assert "/40" in report
        assert prompts[0].variable_name in report


# ---------------------------------------------------------------------------
# Integração com prompt_registry (NÃO quebra API existente)
# ---------------------------------------------------------------------------


class TestPromptRegistryBridge:
    def test_prompt_version_unchanged(self) -> None:
        """API histórica intacta."""
        from src.services.prompt_registry import prompt_version
        fp = prompt_version("hello world")
        assert len(fp) == 16
        assert fp == prompt_version("hello world")  # cache

    def test_register_prompt_for_audit_returns_fingerprint(self, monkeypatch) -> None:
        """Mesmo desabilitado, retorna fingerprint válido."""
        from src.services.prompt_registry import (
            prompt_version,
            register_prompt_for_audit,
        )
        monkeypatch.delenv("PROMETHEUS_CATALOG_ENABLED", raising=False)
        text = "Você é um agente. " * 10
        fp = register_prompt_for_audit(text, name="test")
        assert fp == prompt_version(text)

    def test_register_prompt_no_exception_when_disabled(self, monkeypatch) -> None:
        """Sem env var, vira no-op silencioso."""
        from src.services.prompt_registry import register_prompt_for_audit
        monkeypatch.delenv("PROMETHEUS_CATALOG_ENABLED", raising=False)
        # Não deve levantar exceção em hipótese alguma
        fp = register_prompt_for_audit("x" * 100, name="anonymous")
        assert isinstance(fp, str) and len(fp) == 16

    def test_register_prompt_handles_missing_prometheus_module(
        self, monkeypatch
    ) -> None:
        """Mesmo se importar Prometheus falhasse, não quebraria."""
        from src.services import prompt_registry as pr
        monkeypatch.setenv("PROMETHEUS_CATALOG_ENABLED", "true")
        # Forçamos uma falha simulada injetando ImportError no caminho
        # (verifica try/except interno).
        import sys
        original_module = sys.modules.get("src.prompt_engineering")
        sys.modules["src.prompt_engineering"] = None  # type: ignore[assignment]
        try:
            fp = pr.register_prompt_for_audit("x" * 100, name="failguard")
            assert isinstance(fp, str) and len(fp) == 16
        finally:
            if original_module is not None:
                sys.modules["src.prompt_engineering"] = original_module
            else:
                sys.modules.pop("src.prompt_engineering", None)


# ---------------------------------------------------------------------------
# Isolamento do trading loop
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_prompt_engineering_not_imported_by_vision_module(self) -> None:
        """
        Vision (e qualquer agente runtime) NÃO deve importar prompt_engineering.
        Isso garante que Prometheus pode falhar à vontade sem afetar trading.
        """
        vision_src = Path("src/agents/vision.py").read_text(encoding="utf-8")
        assert "from src.prompt_engineering" not in vision_src
        assert "import src.prompt_engineering" not in vision_src

    def test_trading_agents_dont_import_prometheus(self) -> None:
        agents_dir = Path("src/agents")
        for py in agents_dir.glob("*.py"):
            src = py.read_text(encoding="utf-8")
            assert "prompt_engineering" not in src, (
                f"{py.name} importa prompt_engineering — quebra isolamento"
            )

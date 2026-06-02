"""
tests/test_implementer_dryrun_no_write.py
=========================================
Regressão (2026-06-01): em dry-run o Implementer NÃO pode escrever no working
tree. Antes, deterministic.try_apply() escrevia os arquivos ANTES do check de
dry_run em _post_apply_commit, deixando o tree sujo mesmo em modo manual
(operation_mode=manual → worker dry-run).
"""

from __future__ import annotations

from pathlib import Path

from src.services.implementer.agents import BackendImplementer
from src.services.implementer.base import ImplementerStatus

_REPO = Path(__file__).resolve().parents[1]


def _brief_add_test_stub(candidate: str) -> dict:
    """Brief que casa o padrão add_test_stub com um candidato único."""
    return {
        "rec_id": "TESTDRYRUN01",
        "title": "Backend coverage: 1 services sem teste",
        "description": f"Falta teste para `{candidate}`.",
        "area": "backend",
        "evidence": "1 services sem tests/test_*.py",
    }


def test_dry_run_does_not_write_files():
    candidate = "zzz_dryrun_probe_service"
    target = _REPO / "tests" / f"test_{candidate}.py"
    assert not target.exists(), "pré-condição: arquivo-sonda não deve existir"

    impl = BackendImplementer(dry_run=True)
    result = impl.implement(_brief_add_test_stub(candidate))

    # Em dry-run: nada é escrito no disco…
    assert not target.exists(), "dry-run NÃO pode criar o arquivo de teste"
    # …e o resultado reporta que SERIA aplicado (sem commit).
    assert result.status == ImplementerStatus.PARTIAL
    assert "dry-run" in (result.reason or "").lower()

    # cleanup defensivo (caso a regressão volte, não polui o repo)
    if target.exists():
        target.unlink()


def test_dry_run_detects_pattern_without_side_effects():
    """Dry-run deve DETECTAR o padrão (para reporte) sem nenhum efeito em disco
    nem em git (não cria branch/commit)."""
    candidate = "zzz_dryrun_probe2_service"
    target = _REPO / "tests" / f"test_{candidate}.py"

    impl = BackendImplementer(dry_run=True)
    result = impl.implement(_brief_add_test_stub(candidate))

    assert not target.exists()
    # layer foi identificado (deterministic) mas nada foi escrito/commitado
    assert result.layer_used in ("deterministic", "none")
    assert result.commit_sha in (None, "")


def test_automatic_mode_enables_worker_apply(monkeypatch):
    """Contrato de melhorias AUTOMÁTICAS: operation_mode=automatic liga o worker
    E o apply real (não dry-run). manual mantém ambos OFF."""
    monkeypatch.delenv("IMPLEMENTER_WORKER_ENABLED", raising=False)
    monkeypatch.delenv("IMPLEMENTER_WORKER_AUTO_APPLY", raising=False)
    from src.config import operation_mode as om
    from src.services.implementer import worker

    # estado em memória explícito (não depende do arquivo de override real)
    om._loaded = True               # type: ignore[attr-defined]
    om._current_mode = "automatic"  # type: ignore[attr-defined]
    try:
        assert worker.worker_is_enabled() is True
        assert worker.worker_should_apply() is True   # automatic → aplica de verdade
        # manual → worker desligado (sem env opt-in)
        om._current_mode = "manual"  # type: ignore[attr-defined]
        assert worker.worker_is_enabled() is False
        assert worker.worker_should_apply() is False
    finally:
        om._reset_for_tests()

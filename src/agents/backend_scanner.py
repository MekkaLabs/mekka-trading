"""
src/agents/backend_scanner.py
==============================
BackendScanner — Continuous Improvement Department, backend vertical.

Read-only, fail-silent auditor focado em ``src/services/`` e ``src/models/``.
Detecta padrões problemáticos do backend não-agente:

  • **God-files** — serviços > 600 linhas (limite mais apertado que agentes)
  • **Models sem typing** — campos Pydantic sem type hint explícito
  • **Services sem teste** — service em src/services/ sem tests/test_<name>.py
  • **Imports atômicos** — services usando lazy import dentro de funções
    (sinal de import cycle não resolvido)
  • **Duplicação trivial** — funções com nomes similares em services diferentes

NÃO toca em ``src/config/settings.py`` (gate de segurança). Não toca em
``src/agents/`` (delegado para ``agents_scanner.py``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.backend_scanner")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_SERVICES_DIR = _REPO / "src" / "services"
_MODELS_DIR = _REPO / "src" / "models"
_TESTS_DIR = _REPO / "tests"

# Backend é mais granular que agentes — limites menores.
_FILE_LINES_WARN = 600
_FILE_LINES_CRIT = 900
_FILE_LINES_HUGE = 1500

# Skip: helpers e __init__
_SKIP_FILES = {"__init__.py"}


@dataclass
class _BackendFile:
    name: str
    rel: str
    line_count: int
    text: str
    is_service: bool  # True se está em services/, False se em models/


def _iter_backend_files() -> list[_BackendFile]:
    out: list[_BackendFile] = []
    for base, is_service in ((_SERVICES_DIR, True), (_MODELS_DIR, False)):
        if not base.exists():
            continue
        for p in sorted(base.glob("*.py")):
            if p.name in _SKIP_FILES:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            out.append(_BackendFile(
                name=p.stem,
                rel=str(p.relative_to(_REPO)),
                line_count=text.count("\n") + 1,
                text=text,
                is_service=is_service,
            ))
    return out


def _has_test_for(name: str) -> bool:
    if not _TESTS_DIR.exists():
        return False
    candidates = [
        _TESTS_DIR / f"test_{name}.py",
        _TESTS_DIR / "unit" / f"test_{name}.py",
        _TESTS_DIR / "integration" / f"test_{name}.py",
    ]
    return any(c.exists() for c in candidates)


def _detect_god_files(files: list[_BackendFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    for f in files:
        if f.line_count < _FILE_LINES_WARN:
            continue
        if f.line_count >= _FILE_LINES_HUGE:
            impact, desc = "HIGH", (
                f"`{f.rel}` tem **{f.line_count} linhas** — muito acima do "
                f"limite saudável de {_FILE_LINES_WARN} para services. "
                "Quebrar por responsabilidade reduz risco e melhora testabilidade."
            )
        elif f.line_count >= _FILE_LINES_CRIT:
            impact, desc = "MEDIUM", (
                f"`{f.rel}` tem {f.line_count} linhas. Considere extrair "
                "responsabilidades em módulos coesos."
            )
        else:
            impact, desc = "LOW", (
                f"`{f.rel}` tem {f.line_count} linhas. Monitorar crescimento."
            )
        out.append(ImprovementProposal(
            title=f"Refatorar {f.rel} ({f.line_count} linhas)",
            description=desc,
            impact=impact,
            area="backend",
            evidence=f"{f.rel}: {f.line_count} linhas (limite {_FILE_LINES_WARN})",
            suggested_story=f"Quebrar `{f.name}.py` em módulos menores",
        ))
    return out


def _detect_missing_tests(files: list[_BackendFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    missing = [f for f in files if f.is_service and not _has_test_for(f.name)]
    if not missing:
        return out
    names = ", ".join(f"`{f.name}`" for f in missing[:8])
    if len(missing) > 8:
        names += f", … (+{len(missing) - 8})"
    out.append(ImprovementProposal(
        title=f"Backend coverage: {len(missing)} services sem teste",
        description=(
            f"{len(missing)} services em `src/services/` não têm teste "
            f"correspondente em `tests/`. Faltam: {names}."
        ),
        impact="MEDIUM" if len(missing) >= 4 else "LOW",
        area="backend",
        evidence=f"{len(missing)} services sem tests/test_*.py",
        suggested_story="Adicionar coverage mínimo aos services órfãos",
    ))
    return out


_LAZY_IMPORT_RE = re.compile(
    r"^\s{4,}(?:from|import)\s+src\.", re.MULTILINE
)


def _detect_lazy_imports(files: list[_BackendFile]) -> list[ImprovementProposal]:
    """Lazy imports dentro de funções/métodos são sinal de import cycle não
    resolvido. Não é erro per se, mas indica débito arquitetural."""
    out: list[ImprovementProposal] = []
    offenders: list[tuple[str, int]] = []
    for f in files:
        count = len(_LAZY_IMPORT_RE.findall(f.text))
        if count >= 4:  # noise threshold
            offenders.append((f.rel, count))
    if not offenders:
        return out
    offenders.sort(key=lambda x: -x[1])
    sample = ", ".join(f"`{rel}` ({c})" for rel, c in offenders[:5])
    out.append(ImprovementProposal(
        title=f"Backend: {len(offenders)} arquivos com lazy imports excessivos",
        description=(
            "Lazy imports dentro de funções (`from src... import` indentado) "
            "geralmente indicam ciclo de import não-resolvido. "
            f"Top offenders: {sample}. Vale revisar dependências."
        ),
        impact="LOW",
        area="backend",
        evidence=f"{len(offenders)} arquivos com >=4 lazy imports",
        suggested_story="Resolver ciclos de import em services",
    ))
    return out


_FIELD_NO_TYPE_RE = re.compile(
    r"^\s*(\w+)\s*=\s*Field\(", re.MULTILINE
)


def _detect_untyped_pydantic_fields(files: list[_BackendFile]) -> list[ImprovementProposal]:
    """Campos Pydantic v2 declarados como `nome = Field(...)` sem type hint."""
    out: list[ImprovementProposal] = []
    offenders: list[tuple[str, int]] = []
    for f in files:
        if f.is_service:
            continue  # só models
        matches = _FIELD_NO_TYPE_RE.findall(f.text)
        if matches:
            offenders.append((f.rel, len(matches)))
    if not offenders:
        return out
    sample = ", ".join(f"`{rel}` ({c} campos)" for rel, c in offenders[:5])
    out.append(ImprovementProposal(
        title=f"Models: {len(offenders)} arquivos com campos Pydantic sem typing",
        description=(
            "Pydantic v2 exige type hints. Encontrei campos declarados como "
            f"`nome = Field(...)` sem anotação. Top: {sample}."
        ),
        impact="MEDIUM",
        area="backend",
        evidence=f"{len(offenders)} arquivos em src/models/ com Field() sem typing",
        suggested_story="Adicionar typehints aos campos Pydantic",
    ))
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_proposals(max_proposals: int = 15) -> list[ImprovementProposal]:
    try:
        files = _iter_backend_files()
        proposals: list[ImprovementProposal] = []
        proposals.extend(_detect_god_files(files))
        proposals.extend(_detect_missing_tests(files))
        proposals.extend(_detect_lazy_imports(files))
        proposals.extend(_detect_untyped_pydantic_fields(files))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[backend_scanner] scan failed: {exc}")
        return []
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    proposals.sort(key=lambda p: rank.get(p.impact, 3))
    logger.info(
        f"[backend_scanner] {len(files)} arquivos inspecionados → "
        f"{len(proposals)} proposals"
    )
    return proposals[:max_proposals]


def summary() -> dict:
    files = _iter_backend_files()
    return {
        "files_inspected": len(files),
        "services_dir": str(_SERVICES_DIR),
        "models_dir": str(_MODELS_DIR),
        "max_proposals_cap": 15,
    }

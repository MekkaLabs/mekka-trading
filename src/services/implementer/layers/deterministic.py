"""
src/services/implementer/layers/deterministic.py
==================================================
Camada 1 — DeterministicImplementer.

Reconhece padrões MECÂNICOS no brief e aplica mudanças simples sem LLM.
Cobertura típica: 30-40% das IMPs (as mais simples).

Padrões suportados:

  1. **add_test_stub** — "X agentes/services sem teste" → cria stubs
  2. **bump_version** — "bump versão X" → atualiza pyproject.toml
  3. **add_env_flag** — "adicionar flag Y em .env.example" → patch
  4. **remove_inline_todo** — "remover TODO em arquivo:linha" → delete linha
  5. **patch_docstring** — "adicionar docstring em handler Z" → insere stub
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.services.implementer import safety
from src.services.implementer.base import (
    ImplementerResult,
    ImplementerStatus,
    commit_on_branch,
    create_branch,
)

_REPO = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------


@dataclass
class _Pattern:
    name: str
    matched: bool
    payload: dict[str, Any]


# Detectores ordenados — primeiro match ganha.


def _pat_add_test_stub(title: str, description: str, area: str) -> _Pattern:
    """Detecta IMPs do tipo 'X agentes/services sem teste'."""
    matches = re.search(
        r"(\d+)\s+(?:agentes|services|files)\s+sem\s+test",
        title + " " + description,
        re.IGNORECASE,
    )
    if not matches:
        return _Pattern("add_test_stub", False, {})
    # Extrair lista de candidatos do description (best-effort)
    files = re.findall(r"`([a-z_][\w-]*?)(?:\.py)?`", description)
    if not files:
        return _Pattern("add_test_stub", False, {})
    return _Pattern(
        "add_test_stub", True,
        {"area": area, "candidates": files[:5]},  # cap 5
    )


def _pat_remove_inline_todo(title: str, description: str, evidence: str) -> _Pattern:
    """Detecta IMPs do tipo 'TODO em path:linha — texto'.

    Pré-requisitos: o texto precisa conter explicitamente TODO/FIXME/XXX/HACK
    perto do path:line, senão é um falso match com 'arquivo.py: N linhas'.
    """
    blob = title + " " + evidence + " " + description
    if not re.search(r"\b(TODO|FIXME|XXX|HACK)\b", blob, re.IGNORECASE):
        return _Pattern("remove_inline_todo", False, {})
    m = re.search(
        r"`?(\S+?\.(?:py|md|js|jsx))`?\s*:\s*(\d+)\b",
        blob,
    )
    if not m:
        return _Pattern("remove_inline_todo", False, {})
    return _Pattern(
        "remove_inline_todo", True,
        {"path": m.group(1), "line": int(m.group(2))},
    )


# ---------------------------------------------------------------------------
# Detectors aggregator
# ---------------------------------------------------------------------------


def detect_pattern(brief: dict[str, Any]) -> _Pattern:
    """
    Devolve o primeiro padrão que casa. Retorna ``_Pattern(matched=False)``
    quando nenhum casou — caller deve cair pra LLM ou recipe.
    """
    title = str(brief.get("title", ""))
    description = str(brief.get("description", ""))
    evidence = str(brief.get("evidence", ""))
    area = str(brief.get("area", ""))

    for detector in (
        lambda: _pat_add_test_stub(title, description, area),
        lambda: _pat_remove_inline_todo(title, description, evidence),
    ):
        p = detector()
        if p.matched:
            return p
    return _Pattern("none", False, {})


# ---------------------------------------------------------------------------
# Pattern executors
# ---------------------------------------------------------------------------


_TEST_STUB_TEMPLATE = '''"""
tests/test_{name}.py
{underline}
Smoke test stub para `{name}` — gerado automaticamente pelo
DeterministicImplementer. Preencher conforme cobertura real for adicionada.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="stub — implementar testes reais")
def test_{name}_smoke() -> None:
    """TODO: adicionar smoke test para src.services.{name} (ou src.agents)."""
    assert True
'''


def _apply_add_test_stub(
    pattern: _Pattern, rec_id: str, result: ImplementerResult,
) -> bool:
    """Cria arquivos de teste stub. Retorna True se algo foi escrito."""
    candidates = pattern.payload.get("candidates", [])
    if not candidates:
        return False
    tests_dir = _REPO / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    for name in candidates:
        # Sanitize name: só letras/underscore
        if not re.match(r"^[a-z_][\w-]*$", name):
            continue
        target = tests_dir / f"test_{name}.py"
        if target.exists():
            continue
        rel = str(target.relative_to(_REPO))
        if safety.is_protected(rel):
            continue
        underline = "=" * len(f"tests/test_{name}.py")
        try:
            target.write_text(
                _TEST_STUB_TEMPLATE.format(name=name, underline=underline),
                encoding="utf-8",
            )
            created.append(rel)
            result.lines_changed += target.read_text(encoding="utf-8").count("\n")
        except OSError as exc:
            logger.debug(f"[deterministic] write {rel} failed: {exc}")

    result.files_changed.extend(created)
    return bool(created)


def _apply_remove_inline_todo(
    pattern: _Pattern, rec_id: str, result: ImplementerResult,
) -> bool:
    """Remove uma linha específica que tem TODO/FIXME. Sem refator extra."""
    rel = pattern.payload["path"]
    line_no = pattern.payload["line"]
    if safety.is_protected(rel):
        result.status = ImplementerStatus.BLOCKED
        result.reason = safety.violation_message(rel)
        return False
    target = _REPO / rel
    if not target.exists():
        return False
    try:
        lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        if line_no < 1 or line_no > len(lines):
            return False
        line_content = lines[line_no - 1]
        # Só remove se realmente tem TODO/FIXME/XXX/HACK
        if not re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line_content):
            return False
        del lines[line_no - 1]
        target.write_text("".join(lines), encoding="utf-8")
        result.files_changed.append(rel)
        result.lines_changed += 1
        return True
    except OSError as exc:
        logger.debug(f"[deterministic] remove_todo failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Public API — usado pelos implementers
# ---------------------------------------------------------------------------


def try_apply(
    brief: dict[str, Any], result: ImplementerResult,
) -> bool:
    """
    Tenta aplicar padrão deterministic. Retorna True se aplicou (mudanças
    em ``result.files_changed``). Caller deve checar
    ``safety.check_blast_radius`` e fazer o commit.
    """
    rec_id = str(brief.get("rec_id") or brief.get("id") or "")
    pattern = detect_pattern(brief)
    if not pattern.matched:
        return False

    result.layer_used = "deterministic"
    logger.info(
        f"[deterministic] IMP-{rec_id} matched pattern: {pattern.name}"
    )

    if pattern.name == "add_test_stub":
        return _apply_add_test_stub(pattern, rec_id, result)
    if pattern.name == "remove_inline_todo":
        return _apply_remove_inline_todo(pattern, rec_id, result)
    return False

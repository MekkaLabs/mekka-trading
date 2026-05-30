"""
src/services/implementer/layers/deterministic.py
==================================================
Camada 1 — DeterministicImplementer.

Reconhece padrões MECÂNICOS no brief e aplica mudanças simples sem LLM.
Cobertura típica: 30-40% das IMPs (as mais simples).

Padrões suportados (REV-INV-9, 2026-05-29 — expandido de 2 → 7):

  1. **add_test_stub** — "X agentes/services sem teste" → cria stubs
  2. **remove_inline_todo** — "remover TODO em arquivo:linha" → delete linha
  3. **bump_version** — "bump version X.Y.Z" → patch em pyproject.toml
  4. **add_env_flag** — "adicionar flag Y em .env.example" → append flag
  5. **patch_docstring** — "adicionar docstring em arquivo:linha" → insere stub
  6. **add_logger_import** — "import loguru em arquivo" → adiciona import
  7. **fix_typo** — "typo em arquivo:linha (X → Y)" → substituição precisa

Cada detector é puro e idempotente: retorna ``_Pattern(matched=False)`` se
o brief não casa exatamente — sem heurística agressiva. Falso negativo é
preferível a falso positivo (que vira commit poluído).
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
    """Detecta IMPs do tipo 'X agentes/services sem teste'.

    Aceita variações: "sem teste", "sem `tests/test_*.py`", "sem cobertura
    de teste", "não têm arquivo de teste". Plural opcional "(s)" e
    keyword 'cobertura' isolada.

    MEM-FIX-7 (2026-05-30): briefs do scanner usam "29 agente(s)" e
    "cobertura de testes ausente em 29 agente(s)" — regex original era
    muito restrito (exigia "sem teste" depois do substantivo).
    """
    blob = title + " " + description
    # Padrão 1 (original): "X agentes/services sem teste"
    matches_orig = re.search(
        r"(\d+)\s+(?:agentes?|services?|files?|arquivos?|m[óo]dulos?)\(?s?\)?"
        r"\s+(?:sem|n[ãa]o\s+t[êe]m)\s+(?:test|cobertura|arquivo\s+de\s+test)",
        blob, re.IGNORECASE,
    )
    # Padrão 2 (MEM-FIX-7): "cobertura de testes ausente em X agente(s)"
    matches_inverted = re.search(
        r"cobertura\s+de\s+testes?\s+(?:ausente|faltando|n[ãa]o\s+encontrada)"
        r"\s+(?:em\s+)?(\d+)\s+(?:agentes?|services?|m[óo]dulos?)\(?s?\)?",
        blob, re.IGNORECASE,
    )
    if not (matches_orig or matches_inverted):
        return _Pattern("add_test_stub", False, {})
    # Extrair candidatos: filename em backticks (.py opcional, hifens OK)
    files = re.findall(r"`([a-z_][\w-]*?)(?:\.py)?`", description)
    # Sanitiza: remove paths como tests/test_*.py
    files = [f for f in files if not f.startswith("test") and "/" not in f and "*" not in f]
    if not files:
        return _Pattern("add_test_stub", False, {})
    return _Pattern(
        "add_test_stub", True,
        {"area": area, "candidates": files[:5]},
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


def _pat_bump_version(title: str, description: str) -> _Pattern:
    """Detecta IMPs do tipo 'bump version X.Y.Z' ou 'bump versão X.Y.Z'.

    Match requer EXPLICITAMENTE versão semver (não palpita versão atual).
    """
    blob = title + " " + description
    if not re.search(r"\bbump\s+(?:vers[ãa]o|version)\b", blob, re.IGNORECASE):
        return _Pattern("bump_version", False, {})
    m = re.search(r"(\d+\.\d+\.\d+(?:[-+][\w.]+)?)", blob)
    if not m:
        return _Pattern("bump_version", False, {})
    return _Pattern(
        "bump_version", True,
        {"new_version": m.group(1)},
    )


def _pat_add_env_flag(title: str, description: str) -> _Pattern:
    """Detecta 'adicionar flag X em .env.example' ou 'documentar env Y'.

    IMPORTANTE: .env/.env.example são PROTECTED — esse pattern só toca
    .env.example (template, sem credencial). Adicionar em .env é bloqueado
    explicitamente pelo safety guard.

    Requer match com nome de flag UPPER_SNAKE e mention de .env.example.
    """
    blob = title + " " + description
    if not re.search(r"\.env\.example\b", blob, re.IGNORECASE):
        return _Pattern("add_env_flag", False, {})
    if not re.search(r"\b(adicionar|add|documentar|expor)\b", blob, re.IGNORECASE):
        return _Pattern("add_env_flag", False, {})
    # Captura primeira flag UPPER_SNAKE com >= 3 chars
    m = re.search(r"\b([A-Z][A-Z0-9_]{2,})\b", blob)
    if not m:
        return _Pattern("add_env_flag", False, {})
    flag = m.group(1)
    # Default heurístico — se o brief menciona "true"/"false"/"=valor", captura
    val_match = re.search(rf"{flag}\s*=\s*([^\s]+)", blob)
    default_val = val_match.group(1) if val_match else "false"
    return _Pattern(
        "add_env_flag", True,
        {"flag": flag, "default": default_val},
    )


def _pat_patch_docstring(title: str, description: str, evidence: str) -> _Pattern:
    """Detecta 'adicionar docstring em arquivo:linha' ou 'sem docstring'.

    Requer path:line explícito + menção de docstring. Insere docstring stub
    na próxima linha após uma def/class (1-line stub para humano expandir).
    """
    blob = title + " " + description + " " + evidence
    if not re.search(r"\bdocstring\b", blob, re.IGNORECASE):
        return _Pattern("patch_docstring", False, {})
    m = re.search(
        r"`?(\S+?\.py)`?\s*:\s*(\d+)\b",
        blob,
    )
    if not m:
        return _Pattern("patch_docstring", False, {})
    return _Pattern(
        "patch_docstring", True,
        {"path": m.group(1), "line": int(m.group(2))},
    )


def _pat_add_logger_import(title: str, description: str) -> _Pattern:
    """Detecta 'arquivo.py sem import de loguru' ou 'falta logger import'.

    Pattern típico: scanner detecta arquivo usa logger sem importar.
    Adiciona ``from loguru import logger`` no topo (após imports stdlib).
    """
    blob = title + " " + description
    if not re.search(
        r"\b(import|importar)\b.*\b(loguru|logger)\b",
        blob, re.IGNORECASE,
    ):
        return _Pattern("add_logger_import", False, {})
    if not re.search(r"\b(falta|sem|adicionar|missing)\b", blob, re.IGNORECASE):
        return _Pattern("add_logger_import", False, {})
    # Captura arquivos .py mencionados
    files = re.findall(r"`?(\S+?\.py)`?", blob)
    files = [f for f in files if "/" in f and not f.startswith("tests/")]
    if not files:
        return _Pattern("add_logger_import", False, {})
    return _Pattern(
        "add_logger_import", True,
        {"files": files[:3]},
    )


def _pat_fix_typo(title: str, description: str, evidence: str) -> _Pattern:
    """Detecta 'typo em arquivo:linha (X → Y)' ou 'fix typo X → Y'.

    Requer SUBSTITUIÇÃO explícita (X → Y) — não chuta correção.
    """
    blob = title + " " + description + " " + evidence
    if not re.search(r"\btypo\b", blob, re.IGNORECASE):
        return _Pattern("fix_typo", False, {})
    # Padrão: "X → Y" ou "X -> Y" ou "X = Y" (em quotes)
    m = re.search(
        r'["`\']([^"`\']{2,40})["`\']\s*(?:→|->|=>|para)\s*["`\']([^"`\']{2,40})["`\']',
        blob,
    )
    if not m:
        return _Pattern("fix_typo", False, {})
    # Path obrigatório
    path_m = re.search(r"`?(\S+?\.(?:py|md))`?", blob)
    if not path_m:
        return _Pattern("fix_typo", False, {})
    return _Pattern(
        "fix_typo", True,
        {
            "path": path_m.group(1),
            "old": m.group(1),
            "new": m.group(2),
        },
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
        # Específicos primeiro (matches mais raros)
        lambda: _pat_bump_version(title, description),
        lambda: _pat_fix_typo(title, description, evidence),
        lambda: _pat_remove_inline_todo(title, description, evidence),
        lambda: _pat_patch_docstring(title, description, evidence),
        lambda: _pat_add_env_flag(title, description),
        lambda: _pat_add_logger_import(title, description),
        # Mais genéricos por último (fallback)
        lambda: _pat_add_test_stub(title, description, area),
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


def _apply_bump_version(
    pattern: _Pattern, rec_id: str, result: ImplementerResult,
) -> bool:
    """Atualiza versão no pyproject.toml. Não toca outros arquivos."""
    new_version = pattern.payload["new_version"]
    target = _REPO / "pyproject.toml"
    if not target.exists():
        return False
    rel = "pyproject.toml"
    if safety.is_protected(rel):
        result.status = ImplementerStatus.BLOCKED
        result.reason = safety.violation_message(rel)
        return False
    try:
        content = target.read_text(encoding="utf-8")
        # Match típico: version = "X.Y.Z"
        new_content, n = re.subn(
            r'^(version\s*=\s*)["\']([^"\']+)["\']',
            rf'\1"{new_version}"',
            content, count=1, flags=re.MULTILINE,
        )
        if n == 0 or new_content == content:
            return False
        target.write_text(new_content, encoding="utf-8")
        result.files_changed.append(rel)
        result.lines_changed += 1
        return True
    except OSError as exc:
        logger.debug(f"[deterministic] bump_version failed: {exc}")
        return False


def _apply_add_env_flag(
    pattern: _Pattern, rec_id: str, result: ImplementerResult,
) -> bool:
    """Append uma flag em .env.example.

    .env.example NÃO é PROTECTED (somente .env é), então safety permite.
    Mas double-check defensivo aqui.
    """
    flag = pattern.payload["flag"]
    default = pattern.payload["default"]
    rel = ".env.example"
    if safety.is_protected(rel):
        result.status = ImplementerStatus.BLOCKED
        result.reason = safety.violation_message(rel)
        return False
    target = _REPO / rel
    if not target.exists():
        return False
    try:
        content = target.read_text(encoding="utf-8")
        # Idempotente: se a flag já existe (qualquer formato), pular
        if re.search(rf"^{re.escape(flag)}\s*=", content, re.MULTILINE):
            return False
        # Append (preserva trailing newline)
        sep = "" if content.endswith("\n") else "\n"
        appended = (
            f"{sep}# {flag} — adicionado por DeterministicImplementer "
            f"({rec_id})\n{flag}={default}\n"
        )
        target.write_text(content + appended, encoding="utf-8")
        result.files_changed.append(rel)
        result.lines_changed += appended.count("\n")
        return True
    except OSError as exc:
        logger.debug(f"[deterministic] add_env_flag failed: {exc}")
        return False


def _apply_patch_docstring(
    pattern: _Pattern, rec_id: str, result: ImplementerResult,
) -> bool:
    """Insere docstring stub após uma def/class numa linha específica.

    Conservador: só insere se a linha indicada começa com 'def ' ou 'class '
    e a próxima linha NÃO é uma docstring. Caso contrário, pula.
    """
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
        text = target.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        if line_no < 1 or line_no > len(lines):
            return False
        decl_line = lines[line_no - 1]
        m = re.match(r"^(\s*)(def|class|async\s+def)\s+(\w+)", decl_line)
        if not m:
            return False
        indent = m.group(1) + "    "
        name = m.group(3)
        # Próxima linha já é docstring? skip
        next_idx = line_no  # 0-based index of next line
        # Achar primeira linha não vazia depois do decl
        while next_idx < len(lines) and lines[next_idx].strip() == "":
            next_idx += 1
        if next_idx < len(lines) and re.match(
            r'^\s*("""|\'\'\')',
            lines[next_idx],
        ):
            return False
        stub = (
            f'{indent}"""TODO: documentar {name}. '
            f"(stub inserido por IMP-{rec_id})\"\"\"\n"
        )
        lines.insert(line_no, stub)
        target.write_text("".join(lines), encoding="utf-8")
        result.files_changed.append(rel)
        result.lines_changed += 1
        return True
    except OSError as exc:
        logger.debug(f"[deterministic] patch_docstring failed: {exc}")
        return False


def _apply_add_logger_import(
    pattern: _Pattern, rec_id: str, result: ImplementerResult,
) -> bool:
    """Adiciona ``from loguru import logger`` em arquivos.

    Conservador: só insere se o arquivo USA ``logger.`` mas NÃO importa.
    Idempotente (skip se já tem o import).
    """
    files = pattern.payload.get("files", [])
    if not files:
        return False
    edited = 0
    for rel in files:
        if safety.is_protected(rel):
            continue
        target = _REPO / rel
        if not target.exists() or not target.is_file():
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except OSError:
            continue
        if "from loguru import logger" in content or "import loguru" in content:
            continue
        # Sanity: o arquivo realmente usa logger.?
        if not re.search(r"\blogger\.", content):
            continue
        # Inserir após primeiro bloco de imports
        lines = content.splitlines(keepends=True)
        insert_at = 0
        for i, line in enumerate(lines[:50]):
            if re.match(r"^(from |import )", line):
                insert_at = i + 1
        new_line = "from loguru import logger\n"
        lines.insert(insert_at, new_line)
        try:
            target.write_text("".join(lines), encoding="utf-8")
        except OSError:
            continue
        result.files_changed.append(rel)
        result.lines_changed += 1
        edited += 1
    return edited > 0


def _apply_fix_typo(
    pattern: _Pattern, rec_id: str, result: ImplementerResult,
) -> bool:
    """Substituição precisa (exact-match) em um arquivo. Sem regex."""
    rel = pattern.payload["path"]
    old = pattern.payload["old"]
    new = pattern.payload["new"]
    if safety.is_protected(rel):
        result.status = ImplementerStatus.BLOCKED
        result.reason = safety.violation_message(rel)
        return False
    target = _REPO / rel
    if not target.exists():
        return False
    try:
        content = target.read_text(encoding="utf-8")
        if old not in content:
            return False
        # Conservador: só substitui se ÚNICO match (evita over-replacement)
        occurrences = content.count(old)
        if occurrences != 1:
            return False
        new_content = content.replace(old, new, 1)
        target.write_text(new_content, encoding="utf-8")
        result.files_changed.append(rel)
        result.lines_changed += 1
        return True
    except OSError as exc:
        logger.debug(f"[deterministic] fix_typo failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Public API — usado pelos implementers
# ---------------------------------------------------------------------------


_EXECUTORS = {
    "add_test_stub": _apply_add_test_stub,
    "remove_inline_todo": _apply_remove_inline_todo,
    "bump_version": _apply_bump_version,
    "add_env_flag": _apply_add_env_flag,
    "patch_docstring": _apply_patch_docstring,
    "add_logger_import": _apply_add_logger_import,
    "fix_typo": _apply_fix_typo,
}


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

    executor = _EXECUTORS.get(pattern.name)
    if executor is None:
        return False
    return executor(pattern, rec_id, result)

"""
src/agents/code_auditor.py
==========================
CodeAuditor — Continuous Improvement Department, dev-squad scanner.

Read-only, fail-silent auditor of the *repository itself*. It auto-detects
developer-facing technical debt that previously could only enter the council
via the manual inbox (e.g. "refactor server.py"):

  • Large files            — modules over a line threshold → refactor candidates
  • TODO / FIXME / HACK    — explicit debt markers left in code
  • Missing tests          — src/ modules without a matching tests/ file
  • ruff findings          — lints (run with a short timeout; optional)

Every finding becomes an ``ImprovementProposal`` (reusing Beast's dataclass) so
the Mekka council can consolidate it exactly like a Beast/inbox proposal.

Design contract (mirrors Beast):
  • read-only — never writes, never executes trade/order code
  • fail-silent — any error → log + return partial/empty, never raises
  • evidence-based — every proposal carries concrete numbers/paths
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.code_auditor")

# Repo root: src/agents/code_auditor.py → parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_TESTS = _REPO_ROOT / "tests"

# Thresholds (conservative — only flag clear debt).
_LARGE_FILE_LINES = 1500
_HUGE_FILE_LINES = 4000
_LONG_FUNCTION_LINES = 120  # functions longer than this are refactor candidates
_MAX_PROPOSALS_PER_KIND = 5
# Match debt markers only in COMMENTS (``# TODO``), so we don't match string
# literals like a marker tuple in this very file.
_TODO_RE = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
_RUFF_TIMEOUT_S = 20.0

# Files we never propose to touch (safety gates — protected by L1-L4).
_PROTECTED_HINTS = ("settings.py", "kill_switch", "killswitch")

# Files where _scan_todo_markers should self-exclude: this file defines the
# regex `_TODO_RE` as a Python string literal containing the marker words
# (TODO|FIXME|HACK|XXX), which the scanner would otherwise match on itself
# and report as "6 TODOs in code_auditor.py" — a perpetual false positive.
_TODO_SCAN_EXCLUDE = ("code_auditor.py",)


def _area_for_path(path: Path) -> str:
    """Map a source path to a council 'area' (drives domain = dev-squad)."""
    s = str(path).replace("\\", "/")
    if "/dashboard/static/" in s or s.endswith((".js", ".css", ".html")):
        return "frontend"
    if "/dashboard/" in s:
        return "backend"
    return "backend"


class CodeAuditor:
    """Dev-squad scanner. Usage: ``proposals = await CodeAuditor().scan()``."""

    async def scan(self) -> list[ImprovementProposal]:
        proposals: list[ImprovementProposal] = []
        for fn in (
            self._scan_large_files,
            self._scan_long_functions,
            self._scan_todo_markers,
            self._scan_missing_tests,
            self._scan_ruff,
        ):
            try:
                proposals.extend(await fn())
            except Exception as exc:  # noqa: BLE001
                logger.warning("[CodeAuditor] %s failed: %s", getattr(fn, "__name__", fn), exc)
        return proposals

    # ------------------------------------------------------------------
    # Signal 1 — large files (refactor candidates)
    # ------------------------------------------------------------------
    async def _scan_large_files(self) -> list[ImprovementProposal]:
        if not _SRC.exists():
            return []
        sized: list[tuple[Path, int]] = []
        for p in _SRC.rglob("*.py"):
            if "__pycache__" in str(p):
                continue
            try:
                n = sum(1 for _ in p.open("r", encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if n >= _LARGE_FILE_LINES:
                sized.append((p, n))
        sized.sort(key=lambda t: -t[1])

        out: list[ImprovementProposal] = []
        for p, n in sized[:_MAX_PROPOSALS_PER_KIND]:
            rel = p.relative_to(_REPO_ROOT)
            # Never propose touching protected safety files.
            if any(h in str(rel) for h in _PROTECTED_HINTS):
                continue
            impact = "HIGH" if n >= _HUGE_FILE_LINES else "MEDIUM"
            out.append(ImprovementProposal(
                title=f"Refatorar {rel.name} ({n} linhas)",
                description=(
                    f"`{rel}` tem {n} linhas — acima do limite de {_LARGE_FILE_LINES}. "
                    "Arquivos grandes concentram risco, dificultam revisão e testes. "
                    "Quebrar em módulos coesos por responsabilidade."
                ),
                impact=impact,
                area=_area_for_path(p),
                evidence=f"{rel}: {n} linhas (limite {_LARGE_FILE_LINES}, enorme ≥{_HUGE_FILE_LINES}).",
                suggested_story=f"Refatorar {rel.name} em submódulos",
            ))
        return out

    # ------------------------------------------------------------------
    # Signal 1b — long functions (refactor candidates), via AST
    # ------------------------------------------------------------------
    async def _scan_long_functions(self) -> list[ImprovementProposal]:
        import ast
        if not _SRC.exists():
            return []
        longest: list[tuple[str, str, int]] = []  # (rel, func, lines)
        for p in _SRC.rglob("*.py"):
            if "__pycache__" in str(p):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except (SyntaxError, OSError, ValueError):
                continue
            rel = str(p.relative_to(_REPO_ROOT))
            if any(h in rel for h in _PROTECTED_HINTS):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(node, "end_lineno", None)
                    if end is None:
                        continue
                    span = end - node.lineno + 1
                    if span >= _LONG_FUNCTION_LINES:
                        longest.append((rel, node.name, span))
        if not longest:
            return []
        longest.sort(key=lambda t: -t[2])
        out: list[ImprovementProposal] = []
        for rel, func, span in longest[:_MAX_PROPOSALS_PER_KIND]:
            out.append(ImprovementProposal(
                title=f"Função longa: {func}() em {Path(rel).name} ({span} linhas)",
                description=(
                    f"`{func}` em `{rel}` tem {span} linhas (limite {_LONG_FUNCTION_LINES}). "
                    "Funções longas escondem complexidade e dificultam teste — extrair em helpers."
                ),
                impact="MEDIUM" if span < _LONG_FUNCTION_LINES * 3 else "HIGH",
                area=_area_for_path(Path(rel)),
                evidence=f"{rel}: {func}() = {span} linhas (limite {_LONG_FUNCTION_LINES}).",
                suggested_story=f"Quebrar {func}() em funções menores",
            ))
        return out

    # ------------------------------------------------------------------
    # Signal 2 — TODO / FIXME / HACK markers
    # ------------------------------------------------------------------
    async def _scan_todo_markers(self) -> list[ImprovementProposal]:
        if not _SRC.exists():
            return []
        counts: dict[str, int] = {}
        examples: dict[str, str] = {}
        total = 0
        for p in _SRC.rglob("*.py"):
            if "__pycache__" in str(p):
                continue
            # Self-exclude files that define the _TODO_RE literal (false positive).
            if any(excl in p.name for excl in _TODO_SCAN_EXCLUDE):
                continue
            try:
                for i, line in enumerate(p.open("r", encoding="utf-8", errors="ignore"), 1):
                    if _TODO_RE.search(line):
                        rel = str(p.relative_to(_REPO_ROOT))
                        counts[rel] = counts.get(rel, 0) + 1
                        total += 1
                        if rel not in examples:
                            examples[rel] = f"{rel}:{i} {line.strip()[:80]}"
            except OSError:
                continue
        if total == 0:
            return []
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:_MAX_PROPOSALS_PER_KIND]
        out: list[ImprovementProposal] = []
        for rel, c in top:
            if c < 3:  # only flag files with a meaningful cluster
                continue
            out.append(ImprovementProposal(
                title=f"Resolver {c} marcadores TODO/FIXME em {Path(rel).name}",
                description=(
                    f"`{rel}` acumula {c} marcadores TODO/FIXME/HACK. "
                    "Dívida explícita deixada no código — triagem e resolução."
                ),
                impact="LOW" if c < 8 else "MEDIUM",
                area=_area_for_path(Path(rel)),
                evidence=examples.get(rel, f"{rel}: {c} marcadores"),
                suggested_story=f"Limpar dívida marcada em {Path(rel).name}",
            ))
        return out

    # ------------------------------------------------------------------
    # Signal 3 — modules without tests
    # ------------------------------------------------------------------
    async def _scan_missing_tests(self) -> list[ImprovementProposal]:
        agents_dir = _SRC / "agents"
        if not agents_dir.exists() or not _TESTS.exists():
            return []
        # Index existing test file stems for cheap membership checks.
        test_blob = " ".join(
            t.name for t in _TESTS.rglob("test_*.py") if "__pycache__" not in str(t)
        )
        missing: list[str] = []
        for p in agents_dir.glob("*.py"):
            stem = p.stem
            if stem in ("__init__", "base"):
                continue
            if f"test_{stem}" not in test_blob:
                missing.append(stem)
        if not missing:
            return []
        sample = ", ".join(sorted(missing)[:10])
        return [ImprovementProposal(
            title=f"Cobertura de testes ausente em {len(missing)} agente(s)",
            description=(
                "Agentes sem teste unitário correspondente em tests/. "
                "Sistema com dinheiro real exige cobertura nos agentes de execução/decisão."
            ),
            impact="MEDIUM",
            area="backend",
            evidence=f"Sem test_*.py: {sample}{'…' if len(missing) > 10 else ''}",
            suggested_story="Adicionar testes unitários para agentes sem cobertura",
        )]

    # ------------------------------------------------------------------
    # Signal 4 — ruff findings (optional, short timeout)
    # ------------------------------------------------------------------
    async def _scan_ruff(self) -> list[ImprovementProposal]:
        import json as _json
        try:
            proc = await asyncio.create_subprocess_exec(
                "ruff", "check", "--output-format=json", "src/",
                cwd=str(_REPO_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_RUFF_TIMEOUT_S)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return []
        except (FileNotFoundError, OSError):
            return []  # ruff not installed — skip silently
        try:
            findings = _json.loads(stdout.decode("utf-8") or "[]")
        except (ValueError, UnicodeDecodeError):
            return []
        if not isinstance(findings, list) or not findings:
            return []
        by_code: dict[str, int] = {}
        for f in findings:
            code = str((f or {}).get("code") or "?")
            by_code[code] = by_code.get(code, 0) + 1
        total = len(findings)
        top = sorted(by_code.items(), key=lambda kv: -kv[1])[:5]
        top_str = ", ".join(f"{c}×{n}" for c, n in top)
        impact = "LOW" if total < 50 else "MEDIUM"
        return [ImprovementProposal(
            title=f"Resolver {total} findings do ruff",
            description=(
                f"`ruff check src/` reporta {total} findings. "
                "Padronização e qualidade reduzem bugs sutis."
            ),
            impact=impact,
            area="backend",
            evidence=f"Top regras: {top_str}",
            suggested_story="Rodar ruff --fix e revisar findings restantes",
        )]

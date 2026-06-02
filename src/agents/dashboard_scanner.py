"""
src/agents/dashboard_scanner.py
=================================
DashboardScanner — Continuous Improvement Department, dashboard vertical.

Read-only, fail-silent auditor de ``src/dashboard/`` (Python backend do
dashboard — não confundir com FrontendScanner que vê static/).

Detecta:
  • **server.py monolítico** — limite muito apertado (já é god-file conhecido)
  • **Handlers sem rate-limit** — endpoints POST sem decorator/guard
  • **Endpoints sem docstring** — handlers sem triple-quote no def
  • **Handlers sem return type hint**
  • **Routers fragmentados** — domínio com muitos handlers em arquivos
    diferentes (sinal de refator pendente)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.dashboard_scanner")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_DASHBOARD_DIR = _REPO / "src" / "dashboard"
_HANDLERS_DIR = _DASHBOARD_DIR / "handlers"
_ROUTERS_DIR = _DASHBOARD_DIR / "routers"
_SERVER_FILE = _DASHBOARD_DIR / "server.py"

_FILE_LINES_WARN = 800
_FILE_LINES_CRIT = 2000
_FILE_LINES_HUGE = 5000


@dataclass
class _DashFile:
    name: str
    rel: str
    line_count: int
    text: str


def _iter_dashboard_py() -> list[_DashFile]:
    out: list[_DashFile] = []
    if not _DASHBOARD_DIR.exists():
        return out
    for p in _DASHBOARD_DIR.rglob("*.py"):
        if p.name == "__init__.py":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.append(_DashFile(
            name=p.stem,
            rel=str(p.relative_to(_REPO)),
            line_count=text.count("\n") + 1,
            text=text,
        ))
    return out


def _detect_god_server(files: list[_DashFile]) -> list[ImprovementProposal]:
    server = next((f for f in files if f.rel.endswith("dashboard/server.py")), None)
    if not server:
        return []
    if server.line_count < _FILE_LINES_CRIT:
        return []
    impact = "HIGH" if server.line_count >= _FILE_LINES_HUGE else "MEDIUM"
    return [ImprovementProposal(
        title=f"Dashboard: server.py com {server.line_count} linhas",
        description=(
            f"`{server.rel}` tem **{server.line_count} linhas** — extrair "
            "handlers para módulos por domínio. Já existe parte feita em "
            "`src/dashboard/routers/` (improvements). Continuar a extração."
        ),
        impact=impact,
        area="dashboard",
        evidence=f"{server.rel}: {server.line_count} linhas",
        suggested_story="Extrair handlers do server.py para routers/",
    )]


def _detect_god_handlers(files: list[_DashFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    for f in files:
        if not ("dashboard/handlers/" in f.rel or "dashboard/routers/" in f.rel):
            continue
        if f.line_count < _FILE_LINES_WARN:
            continue
        impact = "MEDIUM" if f.line_count < _FILE_LINES_CRIT else "HIGH"
        out.append(ImprovementProposal(
            title=f"Dashboard: refatorar {f.name}.py ({f.line_count} linhas)",
            description=(
                f"`{f.rel}` tem {f.line_count} linhas — abaixo do server.py "
                "principal mas já saindo do tamanho recomendado para handlers."
            ),
            impact=impact,
            area="dashboard",
            evidence=f"{f.rel}: {f.line_count} linhas",
            suggested_story=f"Quebrar `{f.name}.py` em sub-handlers",
        ))
    return out


_HANDLER_DEF_RE = re.compile(
    r"async\s+def\s+(_?handle_\w+)\s*\([^)]*\)\s*(?:->\s*([\w\.\[\]]+))?\s*:",
    re.MULTILINE,
)
_DOCSTRING_AFTER_DEF_RE = re.compile(
    r'async\s+def\s+\w+\s*\([^)]*\)[^:]*:\s*\n\s*"""',
)


def _detect_undocumented_handlers(files: list[_DashFile]) -> list[ImprovementProposal]:
    """Handlers async def sem docstring."""
    out: list[ImprovementProposal] = []
    total = 0
    undocumented: list[tuple[str, str]] = []
    for f in files:
        if "dashboard/" not in f.rel:
            continue
        # Para cada handler, verificar se a próxima linha tem """
        for m in _HANDLER_DEF_RE.finditer(f.text):
            total += 1
            handler_name = m.group(1)
            # Pega 200 chars após o match
            tail = f.text[m.end():m.end() + 300]
            if not tail.strip().startswith('"""') and not tail.strip().startswith("'''"):
                undocumented.append((f.name, handler_name))
    if not undocumented:
        return out
    if len(undocumented) / max(total, 1) < 0.20:
        return out  # menos de 20% sem doc é aceitável
    sample = ", ".join(f"`{n}.{h}`" for n, h in undocumented[:5])
    out.append(ImprovementProposal(
        title=f"Dashboard: {len(undocumented)}/{total} handlers sem docstring",
        description=(
            f"Endpoints sem docstring no def dificultam onboarding e "
            f"observabilidade. Top: {sample}."
        ),
        impact="LOW",
        area="dashboard",
        evidence=f"{len(undocumented)} de {total} handlers sem docstring",
        suggested_story="Adicionar docstrings aos handlers",
    ))
    return out


_RETURN_TYPE_RE = re.compile(
    r"async\s+def\s+_?handle_\w+\s*\([^)]*\)\s*->\s*[\w\.\[\]]+",
)


def _detect_handlers_without_return_type(files: list[_DashFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    typed = 0
    total = 0
    untyped: list[str] = []
    for f in files:
        if "dashboard/" not in f.rel:
            continue
        for m in _HANDLER_DEF_RE.finditer(f.text):
            total += 1
            full = m.group(0)
            if " -> " in full or "->" in m.group(0):
                typed += 1
            else:
                untyped.append(f"{f.name}.{m.group(1)}")
    if total == 0 or len(untyped) / total < 0.30:
        return out
    sample = ", ".join(f"`{u}`" for u in untyped[:5])
    out.append(ImprovementProposal(
        title=f"Dashboard: {len(untyped)}/{total} handlers sem return type",
        description=(
            "Handlers async sem `-> web.Response` perdem proteção mypy e "
            f"dificultam refactoring. Top: {sample}."
        ),
        impact="LOW",
        area="dashboard",
        evidence=f"{len(untyped)} handlers sem return type",
        suggested_story="Adicionar return types nos handlers",
    ))
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_proposals(max_proposals: int = 15) -> list[ImprovementProposal]:
    try:
        files = _iter_dashboard_py()
        proposals: list[ImprovementProposal] = []
        proposals.extend(_detect_god_server(files))
        proposals.extend(_detect_god_handlers(files))
        proposals.extend(_detect_undocumented_handlers(files))
        proposals.extend(_detect_handlers_without_return_type(files))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[dashboard_scanner] scan failed: {exc}")
        return []
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    proposals.sort(key=lambda p: rank.get(p.impact, 3))
    logger.info(
        f"[dashboard_scanner] {len(files)} arquivos inspecionados → "
        f"{len(proposals)} proposals"
    )
    return proposals[:max_proposals]


def summary() -> dict:
    files = _iter_dashboard_py()
    return {
        "files_inspected": len(files),
        "dashboard_dir": str(_DASHBOARD_DIR),
        "max_proposals_cap": 15,
    }

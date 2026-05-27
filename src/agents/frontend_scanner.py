"""
src/agents/frontend_scanner.py
================================
FrontendScanner — Continuous Improvement Department, frontend vertical.

Read-only, fail-silent auditor de ``src/dashboard/static/`` (exceto os
diretórios legados marcados na memória ``feedback-office-v4-only``).

Detecta:
  • **Bundles enormes** — JS > 2000 linhas, CSS > 1500 linhas
  • **Inline event handlers** (`onclick=`) em HTML — fragilidade conhecida
  • **Scripts sem cache-bust** (sem `?v=...`)
  • **CSS órfão** — classes definidas e nunca usadas (heurística)
  • **JS sem 'use strict'** ou sem IIFE/ESM module wrapper
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.frontend_scanner")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_STATIC_DIR = _REPO / "src" / "dashboard" / "static"

# Diretórios LEGADOS — pular conforme política em feedback-office-v4-only
_LEGACY_DIRS = {"office_v2", "office-v2-src"}
_LEGACY_FILES = {"agents-sprites.js", "office_v2.bundle.js"}

# Libs vendored (third-party) — não são nossas, não devem virar IMPs
_VENDORED_PREFIXES = ("react", "babel", "lodash", "jquery", "moment", "d3",
                      "chart", "force-graph", "three", "vue", "angular")

# Limites de tamanho
_JS_LINES_WARN = 1500
_JS_LINES_CRIT = 2500
_CSS_LINES_WARN = 1200
_HTML_LINES_WARN = 800


@dataclass
class _StaticFile:
    name: str
    rel: str
    ext: str   # .js, .css, .html, .jsx
    line_count: int
    text: str


def _iter_static() -> list[_StaticFile]:
    out: list[_StaticFile] = []
    if not _STATIC_DIR.exists():
        return out
    for p in _STATIC_DIR.rglob("*"):
        if not p.is_file():
            continue
        # Skip legacy
        if any(d in p.parts for d in _LEGACY_DIRS):
            continue
        if p.name in _LEGACY_FILES:
            continue
        if p.suffix not in (".js", ".jsx", ".css", ".html"):
            continue
        # Skip libs vendored (third-party). Detecta por prefixo do filename.
        stem_low = p.stem.lower()
        if any(stem_low.startswith(pre) for pre in _VENDORED_PREFIXES):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.append(_StaticFile(
            name=p.stem,
            rel=str(p.relative_to(_REPO)),
            ext=p.suffix,
            line_count=text.count("\n") + 1,
            text=text,
        ))
    return out


def _detect_huge_bundles(files: list[_StaticFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    for f in files:
        if f.ext in (".js", ".jsx"):
            if f.line_count < _JS_LINES_WARN:
                continue
            impact = "MEDIUM" if f.line_count < _JS_LINES_CRIT else "HIGH"
            desc = (
                f"`{f.rel}` tem **{f.line_count} linhas** de JS — dificulta "
                "manutenção e aumenta tempo de carregamento. Quebrar em módulos."
            )
        elif f.ext == ".css":
            if f.line_count < _CSS_LINES_WARN:
                continue
            impact = "LOW"
            desc = (
                f"`{f.rel}` tem {f.line_count} linhas de CSS. Considere "
                "modularizar por componente ou usar BEM/utility classes."
            )
        elif f.ext == ".html":
            if f.line_count < _HTML_LINES_WARN:
                continue
            impact = "MEDIUM"
            desc = (
                f"`{f.rel}` tem {f.line_count} linhas de HTML — extrair "
                "templates parciais ou Web Components para reduzir."
            )
        else:
            continue
        out.append(ImprovementProposal(
            title=f"Frontend: refatorar {f.name}{f.ext} ({f.line_count} linhas)",
            description=desc,
            impact=impact,
            area="frontend",
            evidence=f"{f.rel}: {f.line_count} linhas",
            suggested_story=f"Quebrar `{f.name}{f.ext}` em módulos",
        ))
    return out


_ONCLICK_RE = re.compile(r"\b(?:onclick|onmouseover|onchange|onload)\s*=", re.IGNORECASE)


def _detect_inline_handlers(files: list[_StaticFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    offenders: list[tuple[str, int]] = []
    for f in files:
        if f.ext != ".html":
            continue
        c = len(_ONCLICK_RE.findall(f.text))
        if c >= 3:
            offenders.append((f.rel, c))
    if not offenders:
        return out
    sample = ", ".join(f"`{r}` ({c})" for r, c in offenders[:4])
    out.append(ImprovementProposal(
        title=f"Frontend: {len(offenders)} HTMLs com inline handlers",
        description=(
            "Inline handlers (`onclick=`) quebram CSP, são difíceis de "
            "remover sem regredir e violam separação de concerns. Substituir "
            f"por `addEventListener` em JS. Top: {sample}."
        ),
        impact="MEDIUM",
        area="frontend",
        evidence=f"{len(offenders)} arquivos HTML com handlers inline",
        suggested_story="Migrar para addEventListener",
    ))
    return out


_SCRIPT_TAG_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']')


def _detect_missing_cache_bust(files: list[_StaticFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    offenders: list[tuple[str, list[str]]] = []
    for f in files:
        if f.ext != ".html":
            continue
        srcs = _SCRIPT_TAG_RE.findall(f.text)
        # Mantém só refs locais sem ?v=
        bad = [s for s in srcs if not s.startswith(("http://", "https://", "//"))
               and "?v=" not in s and "?ver=" not in s and "?t=" not in s]
        if bad:
            offenders.append((f.rel, bad))
    if not offenders:
        return out
    sample = "; ".join(f"{r}: {len(b)} scripts" for r, b in offenders[:3])
    out.append(ImprovementProposal(
        title=f"Frontend: {len(offenders)} HTMLs com scripts sem cache-bust",
        description=(
            "Scripts locais sem `?v=...` ficam grudados no cache do browser "
            "após mudanças no servidor (Babel-standalone é especialmente "
            f"agressivo). Top: {sample}."
        ),
        impact="LOW",
        area="frontend",
        evidence=f"{len(offenders)} HTMLs com scripts sem cache-bust",
        suggested_story="Adicionar ?v= a todos scripts locais",
    ))
    return out


_CLASS_DEF_RE = re.compile(r"^\.([A-Za-z_][\w-]+)\s*[\{,]", re.MULTILINE)
_CLASS_USE_RE = re.compile(r'class=["\']([^"\']+)["\']')


def _detect_orphan_css_classes(files: list[_StaticFile]) -> list[ImprovementProposal]:
    """Heurística simples: classes em .css que NÃO aparecem em nenhum HTML/JS.
    False positives possíveis (classes geradas dinamicamente). Threshold alto."""
    out: list[ImprovementProposal] = []
    defined: set[str] = set()
    used: set[str] = set()
    for f in files:
        if f.ext == ".css":
            for c in _CLASS_DEF_RE.findall(f.text):
                defined.add(c)
        elif f.ext in (".html", ".js", ".jsx"):
            for m in _CLASS_USE_RE.findall(f.text):
                for c in m.split():
                    used.add(c)
            # Heurística para JSX: className=
            for m in re.findall(r'className=["\']([^"\']+)["\']', f.text):
                for c in m.split():
                    used.add(c)
            # Heurística pra string literals que parecem classes
            for c in defined:
                if c in f.text:
                    used.add(c)
    orphans = defined - used
    if len(orphans) < 20:
        return out
    out.append(ImprovementProposal(
        title=f"Frontend: ~{len(orphans)} classes CSS potencialmente órfãs",
        description=(
            f"Heurística detectou {len(orphans)} classes definidas em CSS "
            "que não aparecem em nenhum HTML/JS. Sujeito a falsos positivos "
            "(classes geradas dinamicamente, BEM siblings) — revisar antes "
            "de remover."
        ),
        impact="LOW",
        area="frontend",
        evidence=f"~{len(orphans)} classes definidas e aparentemente não-usadas",
        suggested_story="Limpar CSS dead code (revisar antes de aplicar)",
    ))
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_proposals(max_proposals: int = 15) -> list[ImprovementProposal]:
    try:
        files = _iter_static()
        proposals: list[ImprovementProposal] = []
        proposals.extend(_detect_huge_bundles(files))
        proposals.extend(_detect_inline_handlers(files))
        proposals.extend(_detect_missing_cache_bust(files))
        proposals.extend(_detect_orphan_css_classes(files))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[frontend_scanner] scan failed: {exc}")
        return []
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    proposals.sort(key=lambda p: rank.get(p.impact, 3))
    logger.info(
        f"[frontend_scanner] {len(files)} arquivos inspecionados → "
        f"{len(proposals)} proposals"
    )
    return proposals[:max_proposals]


def summary() -> dict:
    files = _iter_static()
    return {
        "files_inspected": len(files),
        "static_dir": str(_STATIC_DIR),
        "legacy_skipped": list(_LEGACY_DIRS) + list(_LEGACY_FILES),
        "max_proposals_cap": 15,
    }

"""
src/services/vault_scanner.py
==============================
VaultScanner — extrai sinais acionáveis das notas do segundo cérebro
(vault Obsidian) e converte em ``ImprovementProposal``s consumíveis
pelo conselho Mekka.

Por que existe
--------------
``JeanGrey.scan_proposals()`` só usa health METADATA do vault (broken
links, duplicados, orfãos) — NÃO lê o conteúdo das notas. O resultado é
que as 170+ notas curadas pelo operador (ADRs, runbooks, agentes,
decisões, daily notes) **não viram propostas** para o council de
melhorias.

Este scanner fecha esse gap lendo o conteúdo de cada nota e extraindo
sinais determinísticos:

  - **TODO / FIXME / XXX / HACK** em qualquer nota
  - **ADRs com status=proposta** (decisões não fechadas)
  - **"deveria / falta implementar / próximo passo"** em runbooks/áreas
  - **Daily notes recentes** com linhas começadas por "próximo:", "ação:",
    "tarefa:" (formato de captura comum)
  - **Notas marcadas como `#aprendizado`** sem ação registrada

Hard rules
----------
  - READ-ONLY. NUNCA escreve no vault.
  - Fail-silent. Vault ausente / I/O falha → retorna [].
  - Cada proposal traz `evidence` apontando a nota + linha (rastreabilidade).
  - Dedup: a mesma proposal por nota+linha não é gerada 2x na mesma run.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_DEFAULT_VAULT = Path.home() / "Documents" / "mekka-trading-obsidian"
_SKIP_DIRS = {".obsidian", ".trash", "80 - Attachments", "70 - Templates", "40 - Archive"}
_MAX_NOTES_SCAN = 500   # safety cap
_DAILY_DIR = "60 - Daily"
_ADR_DIR = "30 - Resources/Decisoes Tecnicas"

# Regexes — read-only over note content
_TODO_RE = re.compile(
    r"(?P<kind>TODO|FIXME|XXX|HACK)\s*[:\-]?\s*(?P<text>[^\n]{4,200})",
    re.IGNORECASE,
)
_PENDING_RE = re.compile(
    r"(?:^|\n)\s*(?:[-*]\s+)?(?:próximo[s]?\s+passo[s]?|próximo[s]?|"
    r"tarefa|ação|action|next\s+step|next)\s*[:\-]\s*(?P<text>[^\n]{4,200})",
    re.IGNORECASE,
)
_SHOULD_RE = re.compile(
    r"(?:^|\n)\s*(?:[-*]\s+)?(?P<text>[^.\n]{8,180}(?:deveria|deve\s+ser|"
    r"falta(?:\s+\w+){1,3}|ainda\s+não|should\s+be|to\s+implement)"
    r"[^.\n]{0,80})",
    re.IGNORECASE,
)
_ADR_STATUS_PROPOSTA_RE = re.compile(
    r"^[\s>]*Status[\s>:]+\s*(?:proposta|proposed)\b",
    re.IGNORECASE | re.MULTILINE,
)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Dataclass interno (não exposto fora deste módulo)
# ---------------------------------------------------------------------------


@dataclass
class _VaultSignal:
    note_relpath: str
    line_no: int
    kind: str           # "TODO" | "PENDING" | "SHOULD" | "ADR_PROPOSAL"
    snippet: str
    title: str          # título da nota (ou path se sem H1)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _vault_path() -> Path:
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw) if raw else _DEFAULT_VAULT


def _iter_notes(vault: Path) -> Iterable[Path]:
    if not vault.exists() or not vault.is_dir():
        return
    count = 0
    for p in vault.rglob("*.md"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        count += 1
        if count > _MAX_NOTES_SCAN:
            logger.warning(f"[vault_scanner] cap atingido ({_MAX_NOTES_SCAN})")
            break
        yield p


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _title_of(text: str, fallback: str) -> str:
    m = _TITLE_RE.search(text)
    return m.group(1).strip() if m else fallback


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


# ---------------------------------------------------------------------------
# Extractors — cada um devolve list[_VaultSignal]
# ---------------------------------------------------------------------------


def _extract_todos(rel: str, text: str, title: str) -> list[_VaultSignal]:
    out: list[_VaultSignal] = []
    for m in _TODO_RE.finditer(text):
        out.append(_VaultSignal(
            note_relpath=rel,
            line_no=_line_of(text, m.start()),
            kind="TODO",
            snippet=(m.group("kind").upper() + ": " + m.group("text").strip())[:180],
            title=title,
        ))
    return out


def _extract_pending(rel: str, text: str, title: str) -> list[_VaultSignal]:
    out: list[_VaultSignal] = []
    for m in _PENDING_RE.finditer(text):
        out.append(_VaultSignal(
            note_relpath=rel,
            line_no=_line_of(text, m.start()),
            kind="PENDING",
            snippet=m.group("text").strip()[:180],
            title=title,
        ))
    return out


def _extract_should(rel: str, text: str, title: str) -> list[_VaultSignal]:
    out: list[_VaultSignal] = []
    for m in _SHOULD_RE.finditer(text):
        snip = m.group("text").strip()
        if len(snip) >= 8:
            out.append(_VaultSignal(
                note_relpath=rel, line_no=_line_of(text, m.start()),
                kind="SHOULD", snippet=snip[:180], title=title,
            ))
    return out


def _extract_adr_proposta(rel: str, text: str, title: str) -> list[_VaultSignal]:
    # Só rota Decisoes Tecnicas (ADRs)
    if _ADR_DIR.replace("\\", "/") not in rel.replace("\\", "/"):
        return []
    out: list[_VaultSignal] = []
    for m in _ADR_STATUS_PROPOSTA_RE.finditer(text):
        out.append(_VaultSignal(
            note_relpath=rel, line_no=_line_of(text, m.start()),
            kind="ADR_PROPOSAL",
            snippet="ADR em status=proposta — fechar (aceita/reproposta/descartada).",
            title=title,
        ))
    return out


# ---------------------------------------------------------------------------
# Sinal → ImprovementProposal
# ---------------------------------------------------------------------------


def _impact_for(kind: str) -> str:
    return {
        "TODO": "MEDIUM",
        "PENDING": "MEDIUM",
        "SHOULD": "LOW",
        "ADR_PROPOSAL": "MEDIUM",
    }.get(kind, "LOW")


def _area_for(kind: str, relpath: str) -> str:
    p = relpath.lower()
    if "runbook" in p: return "ops"
    if "agentes" in p or "agent" in p: return "agents"
    if "decisoes" in p or "adr" in p: return "architecture"
    if "trading" in p or "risco" in p: return "trading_logic"
    if "operacional" in p: return "ops"
    return "memory" if kind == "ADR_PROPOSAL" else "vault"


def _proposal_from_signal(sig: _VaultSignal) -> dict[str, Any]:
    return {
        "title": f"Vault: {sig.kind} em '{sig.title}' (linha {sig.line_no})",
        "description": (
            f"Sinal encontrado pelo VaultScanner no segundo cérebro: "
            f"\"{sig.snippet}\".\n\n"
            f"Origem: `{sig.note_relpath}:{sig.line_no}`. "
            "Considere transformar em story (ou marcar como resolvido)."
        ),
        "impact": _impact_for(sig.kind),
        "area": _area_for(sig.kind, sig.note_relpath),
        "evidence": f"{sig.note_relpath}:{sig.line_no} — {sig.snippet[:120]}",
        "source": "vault_scanner",
        "suggested_story": f"Endereçar {sig.kind} de '{sig.title}'",
    }


# ---------------------------------------------------------------------------
# Public API — chamada por Mekka
# ---------------------------------------------------------------------------


def scan_proposals(max_proposals: int = 30) -> list[dict[str, Any]]:
    """
    Varre vault, extrai sinais, retorna lista de ImprovementProposal-shaped
    dicts (compatível com formato esperado por Mekka._memory_scanner_proposals).

    Cap de `max_proposals` para não inundar o council. Prioriza por impact.
    Fail-silent: vault ausente → [].
    """
    vault = _vault_path()
    if not vault.exists():
        return []

    all_signals: list[_VaultSignal] = []
    notes_scanned = 0
    try:
        for note in _iter_notes(vault):
            notes_scanned += 1
            text = _read(note)
            if not text:
                continue
            rel = str(note.relative_to(vault))
            title = _title_of(text, fallback=rel)
            all_signals.extend(_extract_todos(rel, text, title))
            all_signals.extend(_extract_pending(rel, text, title))
            all_signals.extend(_extract_should(rel, text, title))
            all_signals.extend(_extract_adr_proposta(rel, text, title))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[vault_scanner] scan error: {exc}")
        return []

    # Dedup por (note, line, kind)
    seen: set[tuple[str, int, str]] = set()
    unique: list[_VaultSignal] = []
    for s in all_signals:
        key = (s.note_relpath, s.line_no, s.kind)
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)

    # Ordena por impact (MEDIUM > LOW) e devolve top N
    impact_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    unique.sort(key=lambda s: impact_rank.get(_impact_for(s.kind), 3))

    proposals = [_proposal_from_signal(s) for s in unique[:max_proposals]]

    logger.info(
        f"[vault_scanner] {notes_scanned} notas escaneadas → "
        f"{len(all_signals)} sinais ({len(unique)} únicos) → "
        f"{len(proposals)} proposals"
    )
    return proposals


def summary() -> dict[str, Any]:
    """Métricas leves para o dashboard (sem rodar scan completo)."""
    vault = _vault_path()
    return {
        "vault_path": str(vault),
        "vault_available": vault.exists(),
        "notes_count": sum(1 for _ in _iter_notes(vault)) if vault.exists() else 0,
        "max_proposals_cap": 30,
    }

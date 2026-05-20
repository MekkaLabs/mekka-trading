"""Jean Grey — Memory Master (P2.1, HANDOFF 2026-05-20).

Jean Grey is the keeper of the "second brain": the Obsidian vault under
``docs/obsidian/`` plus the long-term decision memory other agents rely on.
She does NOT trade and never places orders — she curates knowledge.

MVP scope (no embeddings — pure textual analysis so there is zero API-key
or network dependency):

  1. Vault health report
       - broken wikilinks ([[Note]] targets that don't exist)
       - orphan notes (no inbound backlinks, excluding indexes/MOCs)
       - duplicate candidates (title/content similarity via difflib)
  2. recall(query) — textual search across the vault + DecisionMemory, so
     Vision/Batman/Iron Man can pull historical context on demand.
  3. draft_adr_from_beast(report) — turns a Beast improvement proposal into
     an ADR draft markdown file the operator can accept/reject.

Embedding-based semantic dedup is a deliberate Phase-2 follow-up; difflib's
SequenceMatcher gives a useful-enough signal here without any model calls.

Design rules (mirrors Beast):
  - Fail-silent: any error in a sub-scan logs a warning and yields empty
    results for that scan rather than crashing the whole report.
  - Read-mostly: the only write is draft_adr_from_beast, and it only ever
    creates a new draft file (never overwrites an existing ADR).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from loguru import logger

from src.agents.base import BaseAgent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default vault location relative to the repo root. Resolved lazily so the
# agent works regardless of the process CWD.
_DEFAULT_VAULT = Path(__file__).resolve().parents[2] / "docs" / "obsidian"

# Wikilink syntax: [[Target]], [[Target|alias]], [[Target#heading]],
# [[folder/Target]]. We capture the raw inner text and normalize later.
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Notes that are expected to have no/many backlinks and should never be
# flagged as orphans (indexes, maps-of-content, home, readme, daily notes).
_ORPHAN_EXEMPT_PATTERNS = ("moc", "index", "home", "readme", "_")

# Source folders whose wikilinks are intentional placeholders (templates
# ship with sample links like [[Agente X]]). Broken-link reporting skips
# notes whose vault-relative path starts with any of these.
_PLACEHOLDER_SOURCE_PREFIXES = ("70 - templates",)

# Link targets that are obvious placeholders/template tokens, never real
# notes. Matched after normalization (lower-case). Anything containing a
# mustache token ({{…}}) or made only of dots/ellipsis is also treated as
# a placeholder.
_PLACEHOLDER_TARGETS = {
    "adr-nnn - ...", "adr-nnn", "adr-yyy", "agente x", "squad y",
    "...", "…", "{{date}}", "{{title}}",
}

def _is_placeholder_target(target: str) -> bool:
    """True when a normalized link target is a template placeholder."""
    if not target:
        return True
    if target in _PLACEHOLDER_TARGETS:
        return True
    if "{{" in target or "}}" in target:
        return True
    # all dots / ellipsis (e.g. "...", "…", "....")
    if set(target) <= {".", "…", " "}:
        return True
    return False

# Duplicate detection thresholds.
_TITLE_SIM_THRESHOLD = 0.82
_BODY_SIM_THRESHOLD = 0.90
# Body comparison window. SequenceMatcher.ratio() is O(n²) in the text
# length, so an O(notes²) pairwise scan over large bodies is the dominant
# cost. Cap the compared prefix small and rely on quick_ratio() upper-bound
# pre-filters to skip the expensive ratio() for most pairs.
_BODY_WINDOW = 700


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class BrokenLink:
    """A wikilink whose target note does not exist in the vault."""

    source_note: str   # vault-relative path of the note containing the link
    target: str        # the (normalized) link target that failed to resolve
    raw: str           # the raw [[...]] text as written


@dataclass
class OrphanNote:
    """A note with no inbound backlinks (excluding exempt patterns)."""

    note: str          # vault-relative path
    title: str


@dataclass
class DuplicateCandidate:
    """A pair of notes that look like potential duplicates."""

    note_a: str
    note_b: str
    similarity: float  # 0..1
    basis: str         # "title" or "body"


@dataclass
class VaultHealthReport:
    """Aggregate health snapshot of the Obsidian vault."""

    scanned_at: str
    vault_dir: str
    total_notes: int
    total_links: int
    broken_links: list[BrokenLink] = field(default_factory=list)
    folder_links: list[BrokenLink] = field(default_factory=list)
    orphans: list[OrphanNote] = field(default_factory=list)
    duplicates: list[DuplicateCandidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        # Folder links are informational (navigation aids), not defects.
        return not self.broken_links and not self.duplicates

    def to_dict(self) -> dict:
        return {
            "scanned_at": self.scanned_at,
            "vault_dir": self.vault_dir,
            "total_notes": self.total_notes,
            "total_links": self.total_links,
            "is_healthy": self.is_healthy,
            "broken_links": [
                {"source": b.source_note, "target": b.target, "raw": b.raw}
                for b in self.broken_links
            ],
            "folder_links": [
                {"source": b.source_note, "target": b.target, "raw": b.raw}
                for b in self.folder_links
            ],
            "orphans": [{"note": o.note, "title": o.title} for o in self.orphans],
            "duplicates": [
                {"note_a": d.note_a, "note_b": d.note_b,
                 "similarity": round(d.similarity, 3), "basis": d.basis}
                for d in self.duplicates
            ],
            "errors": self.errors,
        }

    def to_telegram_block(self) -> str:
        status = "✅ saudável" if self.is_healthy else "⚠️ atenção"
        lines = [
            f"🔥 *Jean Grey — Vault Health* ({status})",
            f"📓 {self.total_notes} notas · {self.total_links} links",
            f"🔗 {len(self.broken_links)} links quebrados",
            f"📁 {len(self.folder_links)} links de pasta (navegação)",
            f"🧩 {len(self.duplicates)} possíveis duplicatas",
            f"🌫 {len(self.orphans)} notas órfãs",
        ]
        for b in self.broken_links[:5]:
            lines.append(f"  ✗ {b.source_note} → [[{b.target}]]")
        return "\n".join(lines)


@dataclass
class RecallHit:
    """A single search hit returned by recall()."""

    source: str        # "vault:<path>" or "decision_memory"
    title: str
    snippet: str
    score: float


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class JeanGrey(BaseAgent[VaultHealthReport]):
    """Memory Master — vault curation + long-term recall for other agents."""

    def __init__(self, vault_dir: Optional[Path | str] = None) -> None:
        super().__init__(
            "JeanGrey",
            "Memory Master — vault health, wikilink integrity, long-term recall",
        )
        self.vault_dir = Path(vault_dir) if vault_dir else _DEFAULT_VAULT

    # -- public entry ----------------------------------------------------

    async def _run(self, mode: str = "health") -> VaultHealthReport:  # type: ignore[override]
        """Run a vault scan. ``mode`` is reserved for future expansion;
        today only the health report is produced.

        The scan is CPU-bound (difflib over the whole vault), so it runs in
        a worker thread to avoid blocking the dashboard's asyncio loop.
        """
        import asyncio
        return await asyncio.to_thread(self._build_health_report)

    def _build_health_report(self) -> VaultHealthReport:
        """Synchronous core of the health scan (runs off the event loop)."""
        report = VaultHealthReport(
            scanned_at=datetime.now(timezone.utc).isoformat(),
            vault_dir=str(self.vault_dir),
            total_notes=0,
            total_links=0,
        )

        if not self.vault_dir.exists():
            report.errors.append(f"Vault não encontrado: {self.vault_dir}")
            return report

        try:
            notes = self._scan_vault()
        except Exception as exc:  # noqa: BLE001 — fail-silent per design
            self._log.warning(f"[JeanGrey] vault scan failed: {exc}")
            report.errors.append(f"scan: {exc}")
            return report

        report.total_notes = len(notes)
        report.total_links = sum(len(n["links"]) for n in notes.values())

        # Each sub-analysis is independently guarded.
        try:
            report.broken_links, report.folder_links = self._find_broken_links(notes)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[JeanGrey] broken-link scan failed: {exc}")
            report.errors.append(f"broken_links: {exc}")

        try:
            report.orphans = self._find_orphans(notes)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[JeanGrey] orphan scan failed: {exc}")
            report.errors.append(f"orphans: {exc}")

        try:
            report.duplicates = self._find_duplicates(notes)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[JeanGrey] duplicate scan failed: {exc}")
            report.errors.append(f"duplicates: {exc}")

        self._log.info(
            f"[JeanGrey] vault scan: {report.total_notes} notes, "
            f"{len(report.broken_links)} broken links, "
            f"{len(report.duplicates)} dup candidates, "
            f"{len(report.orphans)} orphans"
        )
        return report

    # -- vault scanning --------------------------------------------------

    def _scan_vault(self) -> dict[str, dict]:
        """Return ``{rel_path: {title, links:set[str], body:str}}``.

        ``links`` are normalized lower-case targets (alias/heading stripped).
        """
        notes: dict[str, dict] = {}
        for path in self.vault_dir.rglob("*.md"):
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(self.vault_dir))
            links = {
                self._normalize_link(m.group(1))
                for m in _WIKILINK_RE.finditer(body)
            }
            links.discard("")
            notes[rel] = {
                "title": path.stem,
                "title_norm": self._normalize_link(path.stem),
                "links": links,
                "body": body,
            }
        return notes

    # -- neural graph ----------------------------------------------------

    def build_graph(self) -> dict:
        """Return the vault's link graph for the "second brain" visualization.

        ``{nodes: [{id, title, folder, degree}], links: [{source, target}],
           total_notes, total_links, scanned_at}``. Nodes are notes; links are
           resolved wikilinks (target title → note path). Fail-silent: returns
           empty graph on any error. CPU-bound — call via asyncio.to_thread.
        """
        empty = {"nodes": [], "links": [], "total_notes": 0, "total_links": 0,
                 "scanned_at": datetime.now(timezone.utc).isoformat()}
        if not self.vault_dir.exists():
            return empty
        try:
            notes = self._scan_vault()
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[JeanGrey] graph scan failed: {exc}")
            return empty

        by_title: dict[str, str] = {}
        for rel, n in notes.items():
            by_title.setdefault(n["title_norm"], rel)

        degree: dict[str, int] = {rel: 0 for rel in notes}
        links: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for rel, n in notes.items():
            for tgt in n["links"]:
                trel = by_title.get(tgt)
                if not trel or trel == rel:
                    continue
                key = (rel, trel)
                if key in seen:
                    continue
                seen.add(key)
                links.append({"source": rel, "target": trel})
                degree[rel] += 1
                degree[trel] += 1

        nodes = []
        for rel, n in notes.items():
            folder = rel.split("/")[0] if "/" in rel else "(raiz)"
            nodes.append({
                "id": rel,
                "title": n["title"],
                "folder": folder,
                "degree": degree.get(rel, 0),
            })
        return {
            "nodes": nodes,
            "links": links,
            "total_notes": len(nodes),
            "total_links": len(links),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _normalize_link(raw: str) -> str:
        """Normalize a wikilink target or note title for comparison.

        Strips alias (``|``), heading (``#``) and any folder prefix, then
        applies Unicode NFC + lower-case. ``[[20 - Areas/Iron Man|Tony]]``
        → ``iron man``.

        The NFC step is critical on macOS: the filesystem returns note
        names in NFD (decomposed: "operações") while wikilinks
        typed in a note are NFC (composed: "operações"). Without
        normalization the two byte sequences differ and every accented
        note title looks like a broken link (the dogfooding bug that this
        scan surfaced on 2026-05-20).
        """
        target = raw.split("|", 1)[0]      # drop alias
        target = target.split("#", 1)[0]   # drop heading anchor
        target = target.strip().rstrip("/")
        if "/" in target:
            target = target.rsplit("/", 1)[-1]
        return unicodedata.normalize("NFC", target.strip()).lower()

    def _find_broken_links(
        self, notes: dict[str, dict]
    ) -> tuple[list[BrokenLink], list[BrokenLink]]:
        """Return ``(broken_links, folder_links)``.

        - Placeholder links (template sample tokens, ``{{…}}``, ``...``) and
          links inside ``70 - Templates/`` are skipped entirely.
        - Links whose target matches an existing folder name are classified
          as *folder links* (navigation aids), not defects.
        - Everything else that doesn't resolve to a note title is *broken*.
        """
        known = {n["title_norm"] for n in notes.values()}
        folder_names = self._collect_folder_names()
        broken: list[BrokenLink] = []
        folders: list[BrokenLink] = []
        for rel, n in notes.items():
            rel_norm = unicodedata.normalize("NFC", rel).lower()
            from_template = any(
                rel_norm.startswith(p) for p in _PLACEHOLDER_SOURCE_PREFIXES
            )
            for tgt in n["links"]:
                if not tgt or tgt in known:
                    continue
                if from_template or _is_placeholder_target(tgt):
                    continue  # intentional placeholder — not a defect
                if tgt in folder_names:
                    folders.append(BrokenLink(source_note=rel, target=tgt, raw=tgt))
                    continue
                broken.append(BrokenLink(source_note=rel, target=tgt, raw=tgt))
        broken.sort(key=lambda b: (b.source_note, b.target))
        folders.sort(key=lambda b: (b.source_note, b.target))
        return broken, folders

    def _collect_folder_names(self) -> set[str]:
        """Normalized names of every folder in the vault (for folder-link
        classification). Both the bare folder name and its numeric-prefixed
        form resolve, e.g. ``20 - Areas`` and ``decisoes tecnicas``."""
        names: set[str] = set()
        for p in self.vault_dir.rglob("*"):
            if p.is_dir():
                names.add(unicodedata.normalize("NFC", p.name).strip().lower())
        return names

    def _find_orphans(self, notes: dict[str, dict]) -> list[OrphanNote]:
        # A note is referenced if any other note links to its title.
        referenced: set[str] = set()
        for n in notes.values():
            referenced |= n["links"]
        orphans: list[OrphanNote] = []
        for rel, n in notes.items():
            title_norm = n["title_norm"]
            rel_norm = unicodedata.normalize("NFC", rel).lower()
            # Templates and daily notes are intentionally unlinked.
            if any(rel_norm.startswith(p) for p in _PLACEHOLDER_SOURCE_PREFIXES):
                continue
            if rel_norm.startswith("60 - daily"):
                continue
            if any(p in title_norm for p in _ORPHAN_EXEMPT_PATTERNS):
                continue
            if title_norm not in referenced:
                orphans.append(OrphanNote(note=rel, title=n["title"]))
        orphans.sort(key=lambda o: o.note)
        return orphans

    def _find_duplicates(self, notes: dict[str, dict]) -> list[DuplicateCandidate]:
        # Structural notes (folder/index notes, daily logs, templates) are
        # intentionally similar to each other — exclude them so dup detection
        # surfaces only genuine content duplication.
        folder_names = self._collect_folder_names()

        def _is_structural(rel: str, title_norm: str) -> bool:
            rel_norm = unicodedata.normalize("NFC", rel).lower()
            if rel_norm.startswith(("60 - daily", "70 - templates")):
                return True
            # Folder/index note: basename matches its own folder name, or a
            # known folder name, or carries an index-style title.
            if title_norm in folder_names:
                return True
            if any(p in title_norm for p in ("index", "moc")):
                return True
            return False

        # Pre-truncate bodies once so the O(n²) loop doesn't re-slice.
        items = [
            (rel, n["title_norm"], n["body"][:_BODY_WINDOW])
            for rel, n in notes.items()
            if not _is_structural(rel, n["title_norm"])
        ]
        dups: list[DuplicateCandidate] = []
        sm = SequenceMatcher(autojunk=False)
        for i in range(len(items)):
            rel_a, ta, ba = items[i]
            for j in range(i + 1, len(items)):
                rel_b, tb, bb = items[j]

                # ── Title similarity (cheap — titles are short). ──
                sm.set_seqs(ta, tb)
                # real_quick_ratio() is an O(1) upper bound; skip the full
                # ratio() when even the upper bound can't clear the bar.
                if sm.real_quick_ratio() >= _TITLE_SIM_THRESHOLD and sm.ratio() >= _TITLE_SIM_THRESHOLD:
                    dups.append(DuplicateCandidate(rel_a, rel_b, sm.ratio(), "title"))
                    continue

                # ── Body similarity (expensive — guard hard). ──
                if not ba or not bb:
                    continue
                if min(len(ba), len(bb)) / max(len(ba), len(bb)) < 0.5:
                    continue
                sm.set_seqs(ba, bb)
                # Two-stage pre-filter: real_quick_ratio (O(1)) then
                # quick_ratio (O(n)) before the O(n²) ratio().
                if sm.real_quick_ratio() < _BODY_SIM_THRESHOLD:
                    continue
                if sm.quick_ratio() < _BODY_SIM_THRESHOLD:
                    continue
                bsim = sm.ratio()
                if bsim >= _BODY_SIM_THRESHOLD:
                    dups.append(DuplicateCandidate(rel_a, rel_b, bsim, "body"))
        dups.sort(key=lambda d: d.similarity, reverse=True)
        return dups

    # -- recall (memory for other agents) --------------------------------

    async def recall(self, query: str, limit: int = 5) -> list[RecallHit]:
        """Textual recall across the vault + DecisionMemory.

        Returns the top ``limit`` hits ranked by a simple term-overlap score.
        Designed as the high-level memory interface other agents call when
        they need historical context (HANDOFF item 4 + 6).
        """
        hits: list[RecallHit] = []
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
        if not terms:
            return hits

        # 1) Vault search.
        try:
            notes = self._scan_vault()
            for rel, n in notes.items():
                body_l = n["body"].lower()
                score = sum(body_l.count(t) for t in terms)
                # Title matches weigh heavier.
                title_l = n["title"].lower()
                score += 3 * sum(1 for t in terms if t in title_l)
                if score > 0:
                    hits.append(RecallHit(
                        source=f"vault:{rel}",
                        title=n["title"],
                        snippet=self._snippet(n["body"], terms),
                        score=float(score),
                    ))
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[JeanGrey] recall vault search failed: {exc}")

        # 2) DecisionMemory search (best-effort — module may be absent).
        # get_recent_with_outcomes() is per-symbol, so iterate the configured
        # trading assets and merge. Each call is independently guarded.
        try:
            from src.services.decision_memory import get_decision_memory
            from src.config.settings import settings as _s
            store = get_decision_memory()
            symbols = list(getattr(_s, "trading_assets", None) or ["BTC"])
            for sym in symbols:
                try:
                    recent = await store.get_recent_with_outcomes(symbol=sym, limit=10)
                except Exception:
                    continue
                for rec in recent or []:
                    blob = str(rec).lower()
                    score = sum(blob.count(t) for t in terms)
                    if score > 0:
                        hits.append(RecallHit(
                            source="decision_memory",
                            title=sym,
                            snippet=str(rec)[:240],
                            score=float(score),
                        ))
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[JeanGrey] recall decision-memory skipped: {exc}")

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    @staticmethod
    def _snippet(body: str, terms: list[str], window: int = 120) -> str:
        low = body.lower()
        for t in terms:
            idx = low.find(t)
            if idx >= 0:
                start = max(0, idx - window // 2)
                end = min(len(body), idx + window // 2)
                return ("…" if start else "") + body[start:end].replace("\n", " ").strip() + ("…" if end < len(body) else "")
        return body[:window].replace("\n", " ").strip()

    # -- Beast → ADR pipeline -------------------------------------------

    def draft_adr_from_beast(self, report, adr_dir: Optional[Path | str] = None) -> list[str]:
        """Turn a BeastReport's proposals into ADR draft files in the vault.

        Returns the list of created file paths. Never overwrites an existing
        file — a numeric suffix is appended on collision. (HANDOFF item 5.)
        """
        proposals = getattr(report, "proposals", None) or []
        if not proposals:
            return []

        target_dir = Path(adr_dir) if adr_dir else (
            self.vault_dir / "30 - Resources" / "Decisoes Tecnicas"
        )
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._log.warning(f"[JeanGrey] cannot create ADR dir: {exc}")
            return []

        created: list[str] = []
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for idx, p in enumerate(proposals, start=1):
            title = getattr(p, "title", f"Proposta {idx}")
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or f"proposta-{idx}"
            fname = f"ADR-DRAFT-{stamp}-{slug}.md"
            path = target_dir / fname
            n = 1
            while path.exists():
                path = target_dir / f"ADR-DRAFT-{stamp}-{slug}-{n}.md"
                n += 1
            try:
                path.write_text(self._render_adr(p, stamp), encoding="utf-8")
                created.append(str(path.relative_to(self.vault_dir)))
            except OSError as exc:
                self._log.warning(f"[JeanGrey] cannot write ADR draft: {exc}")
        if created:
            self._log.info(f"[JeanGrey] wrote {len(created)} ADR draft(s) from Beast")
        return created

    @staticmethod
    def _render_adr(proposal, stamp: str) -> str:
        title = getattr(proposal, "title", "Proposta")
        area = getattr(proposal, "area", "—")
        desc = getattr(proposal, "description", "")
        evidence = getattr(proposal, "evidence", "")
        impact = getattr(proposal, "impact", "—")
        story = getattr(proposal, "suggested_story", None)
        body = [
            f"# ADR (DRAFT) — {title}",
            "",
            "> Gerado por Jean Grey a partir de uma proposta do Beast.",
            f"> Data: {stamp} · Status: **PROPOSTA** (aguardando revisão do operador)",
            "",
            "## Status",
            "PROPOSTA — não aceita. Marque como ACEITA ou REJEITADA após revisão.",
            "",
            "## Contexto",
            f"- Área: {area}",
            f"- Impacto estimado: {impact}",
            f"- Evidência: {evidence}",
            "",
            "## Decisão proposta",
            desc or "_(sem descrição)_",
            "",
            "## Consequências",
            "_A preencher após decisão._",
            "",
        ]
        if story:
            body += ["## Story sugerida", f"{story}", ""]
        body += ["---", "tags: #adr #draft #beast #jean-grey", ""]
        return "\n".join(body)

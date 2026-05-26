#!/usr/bin/env python3
"""
scripts/obsidian_coverage_audit.py
==================================
Auditoria de cobertura entre o sistema real (src/, docs/stories, docs/adr)
e as notas no vault Obsidian.

Reporta:
- AGENTES sem nota dedicada em `20 - Areas/Agentes IA/`
- SERVIÇOS sem menção em qualquer nota (`src/services/*.py`)
- MODELOS sem menção em qualquer nota (`src/models/*.py`)
- STORIES sem nota dedicada em `Stories/`
- ADRS canônicos sem reflexo no vault
- NOTAS FANTASMA (no vault, sem referente no código) — heurística
- DAILY NOTES faltantes (gap entre 1ª e última, dias sem nota)

Uso
---
    python scripts/obsidian_coverage_audit.py
    python scripts/obsidian_coverage_audit.py --vault /caminho/alt
    python scripts/obsidian_coverage_audit.py --json > audit.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VAULT = Path.home() / "Documents" / "mekka-trading-obsidian"

AGENT_DIR = "20 - Areas/Agentes IA"
STORIES_DIR = "10 - Projects/Mekka Trading/06 - Stories and Roadmap/Stories"
ADR_DIR = "30 - Resources/Decisoes Tecnicas"
DAILY_DIR = "60 - Daily"

# Utilitários que não são agentes
NON_AGENT_FILES = {"base", "llm_client"}


@dataclass
class AuditReport:
    timestamp: str
    vault: str
    agents_missing: list[str] = field(default_factory=list)
    agents_orphan_notes: list[str] = field(default_factory=list)
    services_uncovered: list[str] = field(default_factory=list)
    models_uncovered: list[str] = field(default_factory=list)
    stories_missing: list[str] = field(default_factory=list)
    adrs_missing: list[str] = field(default_factory=list)
    daily_gaps: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


def load_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def vault_notes(vault: Path) -> list[Path]:
    notes: list[Path] = []
    for p in vault.rglob("*.md"):
        if ".obsidian" in p.parts or ".trash" in p.parts:
            continue
        notes.append(p)
    return notes


def vault_corpus(vault: Path) -> str:
    chunks: list[str] = []
    for p in vault_notes(vault):
        chunks.append(load_text(p))
    return "\n".join(chunks).lower()


def audit_agents(vault: Path, corpus_lower: str) -> tuple[list[str], list[str]]:
    code = REPO_ROOT / "src" / "agents"
    code_agents = sorted(
        p.stem for p in code.glob("*.py")
        if p.stem != "__init__" and p.stem not in NON_AGENT_FILES
    )

    notes_dir = vault / AGENT_DIR
    if not notes_dir.exists():
        return code_agents, []
    note_names = {p.stem.lower() for p in notes_dir.glob("*.md")}

    missing: list[str] = []
    for a in code_agents:
        candidates = {a.lower(), a.replace("_", " ").lower(), a.replace("_", "-").lower()}
        if not any(c in note_names for c in candidates):
            missing.append(a)

    # Notas que mencionam um nome de agente, mas o nome não existe em src/agents/
    code_set: set[str] = set()
    for a in code_agents:
        code_set.add(a.lower())
        code_set.add(a.replace("_", " ").lower())
        code_set.add(a.replace("_", "-").lower())
    orphans: list[str] = []
    for note in notes_dir.glob("*.md"):
        if note.stem.startswith("_"):
            continue
        canon = note.stem.lower()
        if canon in code_set:
            continue
        # também aceita match parcial em corpus (Cypher pode ser sprite)
        # mas considera órfão se o nome não aparece como módulo Python
        orphans.append(note.stem)

    return missing, orphans


def audit_services(vault: Path, corpus_lower: str) -> list[str]:
    services_dir = REPO_ROOT / "src" / "services"
    services = sorted(p.stem for p in services_dir.glob("*.py") if p.stem != "__init__")
    uncovered: list[str] = []
    for s in services:
        tokens = {s.lower(), s.replace("_", " ").lower(), s.replace("_", "-").lower()}
        if not any(t in corpus_lower for t in tokens):
            uncovered.append(s)
    return uncovered


def audit_models(vault: Path, corpus_lower: str) -> list[str]:
    models_dir = REPO_ROOT / "src" / "models"
    models = sorted(p.stem for p in models_dir.glob("*.py") if p.stem != "__init__")
    uncovered: list[str] = []
    for m in models:
        tokens = {m.lower(), m.replace("_", " ").lower()}
        if not any(t in corpus_lower for t in tokens):
            uncovered.append(m)
    return uncovered


def audit_stories(vault: Path) -> list[str]:
    stories_dir = REPO_ROOT / "docs" / "stories"
    repo_stories: dict[int, str] = {}
    for p in stories_dir.glob("story-*.md"):
        m = re.match(r"story-(\d+)-", p.name)
        if m:
            repo_stories[int(m.group(1))] = p.name

    vault_stories_dir = vault / STORIES_DIR
    vault_numbers: set[int] = set()
    if vault_stories_dir.exists():
        for p in vault_stories_dir.glob("Story *.md"):
            m = re.match(r"Story (\d+)", p.stem)
            if m:
                vault_numbers.add(int(m.group(1)))

    missing = sorted(num for num in repo_stories if num not in vault_numbers)
    return [f"{n:03d} ({repo_stories[n]})" for n in missing]


def audit_adrs(vault: Path) -> list[str]:
    adr_dir = REPO_ROOT / "docs" / "adr"
    repo_adrs = sorted(p.name for p in adr_dir.glob("ADR-*.md"))

    vault_adr_dir = vault / ADR_DIR
    vault_titles: set[str] = set()
    if vault_adr_dir.exists():
        for p in vault_adr_dir.glob("ADR-*.md"):
            # extrai o número
            m = re.match(r"(ADR-\d+)", p.stem)
            if m:
                vault_titles.add(m.group(1))

    missing: list[str] = []
    for fname in repo_adrs:
        m = re.match(r"(ADR-\d+)", fname)
        if m and m.group(1) not in vault_titles:
            missing.append(fname)
    return missing


def audit_daily_gaps(vault: Path, lookback_days: int = 30) -> list[str]:
    daily_dir = vault / DAILY_DIR
    if not daily_dir.exists():
        return []
    existing: set[date] = set()
    for p in daily_dir.glob("*.md"):
        try:
            existing.add(datetime.strptime(p.stem, "%Y-%m-%d").date())
        except ValueError:
            continue
    if not existing:
        return []
    today = date.today()
    earliest = max(today - timedelta(days=lookback_days), min(existing))
    gaps: list[str] = []
    d = earliest
    while d <= today:
        if d not in existing and d.weekday() < 5:  # só dias úteis para não poluir
            gaps.append(d.isoformat())
        d += timedelta(days=1)
    return gaps


def build_report(vault: Path) -> AuditReport:
    corpus = vault_corpus(vault)
    missing_agents, orphan_agents = audit_agents(vault, corpus)
    services_uncov = audit_services(vault, corpus)
    models_uncov = audit_models(vault, corpus)
    stories_missing = audit_stories(vault)
    adrs_missing = audit_adrs(vault)
    daily_gaps = audit_daily_gaps(vault)

    report = AuditReport(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        vault=str(vault),
        agents_missing=missing_agents,
        agents_orphan_notes=orphan_agents,
        services_uncovered=services_uncov,
        models_uncovered=models_uncov,
        stories_missing=stories_missing,
        adrs_missing=adrs_missing,
        daily_gaps=daily_gaps,
    )
    report.summary = {
        "agents_missing": len(missing_agents),
        "agents_orphan_notes": len(orphan_agents),
        "services_uncovered": len(services_uncov),
        "models_uncovered": len(models_uncov),
        "stories_missing": len(stories_missing),
        "adrs_missing": len(adrs_missing),
        "daily_gaps": len(daily_gaps),
    }
    return report


def print_human(r: AuditReport) -> None:
    print(f"\n=== Obsidian Coverage Audit ===")
    print(f"vault: {r.vault}")
    print(f"timestamp: {r.timestamp}\n")
    print("RESUMO:")
    for k, v in r.summary.items():
        print(f"  {k:24s} {v}")
    print()

    sections = [
        ("AGENTES SEM NOTA", r.agents_missing, "src/agents/*.py sem nota dedicada"),
        ("NOTAS DE AGENTES SEM CÓDIGO", r.agents_orphan_notes, "podem ser sprites, conceitos ou agentes removidos"),
        ("SERVIÇOS SEM MENÇÃO", r.services_uncovered, "src/services/*.py não citado em nenhuma nota"),
        ("MODELOS SEM MENÇÃO", r.models_uncovered, "src/models/*.py não citado em nenhuma nota"),
        ("STORIES SEM NOTA", r.stories_missing, "docs/stories/ sem reflexo no vault"),
        ("ADRS SEM REFLEXO", r.adrs_missing, "docs/adr/ sem nota em Decisoes Tecnicas/"),
        ("DAILY NOTES FALTANTES (dias úteis)", r.daily_gaps, "sem nota em 60 - Daily/"),
    ]
    for title, items, hint in sections:
        if not items:
            print(f"--- {title}: OK ---\n")
            continue
        print(f"--- {title} ({len(items)}) — {hint} ---")
        for i in items:
            print(f"  · {i}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Auditoria de cobertura sistema -> vault")
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--json", action="store_true", help="emite JSON em vez de texto")
    args = ap.parse_args()

    if not args.vault.exists():
        print(f"vault não existe: {args.vault}", file=sys.stderr)
        return 1

    report = build_report(args.vault)

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print_human(report)

    # Exit code: 0 mesmo com gaps; auditoria é informativa
    return 0


if __name__ == "__main__":
    sys.exit(main())

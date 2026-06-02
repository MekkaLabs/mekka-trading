"""
src/services/vault_auditor.py
==============================
VAULT-INTEG-3 (2026-05-29) — Auditor unificado do vault canônico.

Substitui múltiplas one-off queries com um pipeline reutilizável que detecta:
  - Órfãos (notas sem incoming links)
  - Links quebrados (`[[TargetNote]]` sem destino)
  - Duplicatas (mesmo basename em locais diferentes)
  - Gaps em Daily (dias faltando)
  - Cobertura agente (código vs vault)
  - Densidade por pasta (volume, médias)

Importável como módulo + CLI (`python -m src.services.vault_auditor --json`).
Read-only — nunca escreve no vault. Resultado plain-JSON serializável.

Usado por:
  - GET /api/vault/audit (endpoint dashboard)
  - scripts CLI manual
  - Beast/Mentor pra detectar quando vault está degradando
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

_WIKI_LINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^|\]]+)?(?:\|[^\]]+)?\]\]")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _default_vault_path() -> Path:
    return Path.home() / "Documents" / "mekka-trading-obsidian"


def _normalize(s: str) -> str:
    """NFC normalization para evitar divergência NFD/NFC entre macOS e Linux."""
    return unicodedata.normalize("NFC", s)


@dataclass
class VaultAuditReport:
    """Snapshot completo do estado do vault."""

    vault_path: str
    vault_exists: bool
    total_notes: int = 0
    total_folders: int = 0
    total_bytes: int = 0

    duplicates: list[dict] = field(default_factory=list)
    broken_links: list[dict] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    daily_gaps: list[str] = field(default_factory=list)
    daily_range: dict = field(default_factory=dict)

    agents_code_count: int = 0
    agents_vault_count: int = 0
    agents_code_only: list[str] = field(default_factory=list)
    agents_vault_only: list[str] = field(default_factory=list)

    density_by_folder: list[dict] = field(default_factory=list)

    # Quick health flags
    health_score: int = 0      # 0-100
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _list_markdown(vault: Path) -> list[Path]:
    out: list[Path] = []
    for p in vault.rglob("*.md"):
        s = str(p)
        if "/.obsidian/" in s or "/.trash/" in s:
            continue
        out.append(p)
    return out


def _detect_agents_code_vs_vault(
    vault: Path,
    repo_root: Path,
) -> tuple[set[str], set[str]]:
    """Retorna (code_agents, vault_agents) NORMALIZADOS pra Title Case.

    Mapeia underscore_case (`black_panther`) → Title Case ('Black Panther').
    Aliases para nomes com hífen ou variantes do código.

    Helpers/utilities NÃO são tratados como agentes (filtrados explicitamente).
    """
    # Não-agentes em src/agents/ que existem por organização do código
    # mas não são personagens do roster Marvel.
    _NOT_REAL_AGENTS = {
        "Batman Scalp Gates",   # módulo de gates auxiliar do Batman
        "Llm Client",           # utility
        "Vision Moa",           # variant do Vision (Mixture of Agents)
        "Agents Scanner",       # Improvement Squad scanner (sem nota Marvel)
        "Backend Scanner",      # idem
        "Frontend Scanner",     # idem
        "Dashboard Scanner",    # idem
    }
    # Review-fix (2026-06-01): os scanners do Improvement Squad SÃO agentes (têm
    # nota no vault com codename Marvel). Antes Code Auditor/Ops Scanner/Risk
    # Scanner eram excluídos do lado CÓDIGO mas suas notas (Cypher/Domino/Forge)
    # contavam no vault → 3 falsos órfãos. Agora os aliases mapeiam codename↔arquivo.
    _VAULT_ALIASES = {
        "Spider-Man": "Spider Man",   # vault usa hífen
        "Cypher": "Code Auditor",     # Doug Ramsey = CodeAuditor
        "Domino": "Risk Scanner",     # Neena Thurman = RiskScanner
        "Forge": "Ops Scanner",       # Forge = OpsScanner
    }
    # Agentes implementados como SERVIÇO (src/services), não src/agents, mas com
    # nota no vault. Contados como "código existe" se o arquivo estiver presente.
    _SERVICE_AGENTS = {
        "Trade Outcome Resolver": repo_root / "src" / "services" / "trade_outcome_resolver.py",
    }
    code: set[str] = set()
    agents_dir = repo_root / "src" / "agents"
    if agents_dir.exists():
        for ap in agents_dir.glob("*.py"):
            if ap.name.startswith("_") or ap.name == "base.py":
                continue
            # snake → Title
            title = " ".join(w.capitalize() for w in ap.stem.split("_"))
            title_n = _normalize(title)
            if title_n in _NOT_REAL_AGENTS:
                continue
            code.add(title_n)
    for _svc_name, _svc_path in _SERVICE_AGENTS.items():
        if _svc_path.exists():
            code.add(_normalize(_svc_name))

    vault_dir = vault / "20 - Areas" / "Agentes IA"
    vault_set: set[str] = set()
    if vault_dir.exists():
        for ap in vault_dir.glob("*.md"):
            if ap.name.startswith("_") or ap.name.startswith("20 -"):
                continue
            stem = _normalize(ap.stem)
            vault_set.add(_VAULT_ALIASES.get(stem, stem))
    return code, vault_set


def _compute_density(paths: list[Path], vault: Path) -> list[dict]:
    by_folder: dict[str, list[Path]] = defaultdict(list)
    for p in paths:
        rel = p.relative_to(vault)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        by_folder[top].append(p)

    out = []
    for folder, fp_list in sorted(by_folder.items()):
        sizes = []
        for p in fp_list:
            try:
                sizes.append(p.stat().st_size)
            except OSError:
                pass
        total = sum(sizes)
        out.append({
            "folder": folder,
            "n_notes": len(fp_list),
            "total_kb": round(total / 1024, 1),
            "avg_kb": round(total / max(len(fp_list), 1) / 1024, 1),
        })
    return out


def _compute_health(report: VaultAuditReport) -> tuple[int, list[str]]:
    """Calcula health score 0-100 + lista issues."""
    score = 100
    issues: list[str] = []

    # Penalidades
    if report.broken_links:
        n = len(report.broken_links)
        score -= min(n * 2, 30)
        issues.append(f"{n} links quebrados (-{min(n*2,30)})")

    if report.duplicates:
        score -= len(report.duplicates) * 5
        issues.append(f"{len(report.duplicates)} duplicatas (-{len(report.duplicates)*5})")

    orphan_ratio = (
        len(report.orphans) / max(report.total_notes, 1) if report.total_notes else 0
    )
    if orphan_ratio > 0.3:
        penalty = int((orphan_ratio - 0.3) * 100)
        score -= penalty
        issues.append(
            f"{len(report.orphans)} órfãos ({orphan_ratio:.0%}) "
            f"(-{penalty})"
        )

    if report.daily_gaps:
        n = len(report.daily_gaps)
        score -= min(n, 15)
        issues.append(f"{n} dias sem daily note (-{min(n,15)})")

    if report.agents_code_only:
        n = len(report.agents_code_only)
        score -= min(n * 3, 20)
        issues.append(f"{n} agentes sem nota vault (-{min(n*3,20)})")

    return max(0, score), issues


def audit_vault(
    vault_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> VaultAuditReport:
    """Roda o audit completo. Read-only. Retorna VaultAuditReport."""
    vault = vault_path or _default_vault_path()
    repo = repo_root or Path(__file__).resolve().parents[2]

    report = VaultAuditReport(
        vault_path=str(vault),
        vault_exists=vault.exists(),
    )
    if not vault.exists():
        report.issues.append("vault path does not exist")
        report.health_score = 0
        return report

    all_paths = _list_markdown(vault)
    report.total_notes = len(all_paths)
    report.total_bytes = sum(p.stat().st_size for p in all_paths if p.exists())
    # folders
    folders: set[str] = set()
    for p in all_paths:
        folders.add(str(p.parent.relative_to(vault)))
    report.total_folders = len(folders)

    # 1) Duplicatas
    stems_to_paths: dict[str, list[Path]] = defaultdict(list)
    for p in all_paths:
        stems_to_paths[_normalize(p.stem)].append(p)
    for stem, plist in stems_to_paths.items():
        if len(plist) > 1:
            report.duplicates.append({
                "stem": stem,
                "count": len(plist),
                "paths": [str(p.relative_to(vault)) for p in plist],
            })

    # 2) Links — build graph.
    # Exclui targets intencionalmente externos do count "broken":
    #   - IMP-xxx: refs a briefs em docs/improvement-queue/, não em vault
    #   - Placeholders pedagógicos: "Agente X", "Squad Y", "ADR-YYY"
    #   - Pastas (não notas): "10 - Projects"
    file_index = {_normalize(p.stem): p for p in all_paths}
    incoming: dict[str, set[str]] = defaultdict(set)
    broken: list[dict] = []
    _EXTERNAL_REF_RE = re.compile(r"^IMP-[a-f0-9]{4,}", re.IGNORECASE)
    _PLACEHOLDER_TARGETS = {
        "Agente X", "Squad Y", "ADR-YYY", "ADR-XXX", "...",
        "crie um link", "10 - Projects", "MOC - XXX",
        "{{date}}", "{{title}}", "ADR-NNN - ...",
    }
    _PLACEHOLDER_PREFIX = ("{{", "ADR-NNN", "Story NNN")
    for p in all_paths:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        src = _normalize(p.stem)
        for m in _WIKI_LINK_RE.finditer(text):
            target_raw = _normalize(m.group(1).strip())
            # Obsidian aceita wiki-link path-style ("Stories/Story 001").
            # Resolve pelo último componente do path (basename).
            target = target_raw.split("/")[-1] if "/" in target_raw else target_raw
            if target in file_index:
                incoming[target].add(src)
                continue
            # Skip intentional external refs
            if _EXTERNAL_REF_RE.match(target):
                continue
            if target in _PLACEHOLDER_TARGETS:
                continue
            if any(target.startswith(pref) for pref in _PLACEHOLDER_PREFIX):
                continue
            broken.append({
                "source": str(p.relative_to(vault)),
                "target": target_raw,  # mantém o raw pra diagnóstico
            })
    report.broken_links = broken

    # 3) Órfãos — sem incoming, excluindo MOCs, índices, Home, write-only paths
    #
    # Write-only paths são onde writers automáticos criam notas que NÃO precisam
    # de incoming explícito (são lidas via dataview/MOC dinâmico):
    #   - Stories: muitas, indexadas pelo Mapa Completo de Stories.md
    #   - Daily notes: indexadas pela view Daily
    #   - regime-log: indexados via dataview Estratégias
    #   - improvements-accepted: lidos via /api/improvements
    excluded_prefixes = ("_", "Home", "Bem-vindo", "README", "VAULT-START", "LLM-CONNECT", "MOC")
    excluded_folders = (
        "70 - Templates", "00 - Inbox", "40 - Archive", "80 - Attachments",
        "60 - Daily",                              # daily notes
        "10 - Projects/Mekka Trading/06 - Stories",  # stories indexadas via Mapa
    )
    excluded_filename_patterns = (
        "regime-log",                # 20-Areas/Trading/Estratégias/YYYY-MM-DD-regime-log.md
        "improvements-accepted",     # 60-Daily/YYYY-MM-DD-improvements-accepted.md
        "prometheus-learnings",      # 60-Daily/YYYY-MM-DD-prometheus-learnings.md
        "-trades.md",                # 60-Daily/YYYY-MM-DD-trades.md
        "-mentor-",                  # mentor suggestions
        "Cable Status",              # cable_vault_writer single-file write
    )
    for stem, p in file_index.items():
        if stem in incoming:
            continue
        if any(stem.startswith(pref) for pref in excluded_prefixes):
            continue
        rel = str(p.relative_to(vault))
        if any(rel.startswith(f) for f in excluded_folders):
            continue
        if any(pat in rel for pat in excluded_filename_patterns):
            continue
        report.orphans.append(rel)
    report.orphans.sort()

    # 4) Daily gaps
    daily_dir = vault / "60 - Daily"
    dates_found: set[date] = set()
    if daily_dir.exists():
        for p in daily_dir.glob("20*.md"):
            m = _DATE_RE.match(p.stem)
            if m:
                try:
                    dates_found.add(
                        date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    )
                except ValueError:
                    pass
    if dates_found:
        d_min, d_max = min(dates_found), max(dates_found)
        all_dates = set()
        cur = d_min
        while cur <= d_max:
            all_dates.add(cur)
            cur += timedelta(days=1)
        gaps = sorted(all_dates - dates_found)
        report.daily_gaps = [g.isoformat() for g in gaps]
        report.daily_range = {
            "first": d_min.isoformat(),
            "last": d_max.isoformat(),
            "span_days": (d_max - d_min).days + 1,
            "notes_count": len(dates_found),
        }

    # 5) Cobertura agentes
    code_agents, vault_agents = _detect_agents_code_vs_vault(vault, repo)
    report.agents_code_count = len(code_agents)
    report.agents_vault_count = len(vault_agents)
    report.agents_code_only = sorted(code_agents - vault_agents)
    report.agents_vault_only = sorted(vault_agents - code_agents)

    # 6) Densidade
    report.density_by_folder = _compute_density(all_paths, vault)

    # 7) Health score
    report.health_score, report.issues = _compute_health(report)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Vault auditor")
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument("--summary", action="store_true", help="Short summary (default)")
    p.add_argument("--vault", help="Override vault path")
    args = p.parse_args()

    vault = Path(args.vault).expanduser() if args.vault else None
    report = audit_vault(vault_path=vault)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    # Summary
    print(f"## Vault Audit — {report.vault_path}")
    print(f"Status: {'EXISTS' if report.vault_exists else 'MISSING'}")
    print(f"Notes:  {report.total_notes} em {report.total_folders} pastas")
    print(f"Size:   {report.total_bytes / 1024:.1f} KB")
    print(f"Health: {report.health_score}/100")
    print()
    print(f"Duplicatas:    {len(report.duplicates)}")
    print(f"Links broken:  {len(report.broken_links)}")
    print(f"Órfãos:        {len(report.orphans)}")
    print(f"Daily gaps:    {len(report.daily_gaps)}")
    print(f"Agentes code:  {report.agents_code_count}")
    print(f"Agentes vault: {report.agents_vault_count}")
    print(f"  Sem nota:    {len(report.agents_code_only)}")
    print(f"  Sem código:  {len(report.agents_vault_only)}")
    print()
    if report.issues:
        print("Issues:")
        for i in report.issues:
            print(f"  - {i}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

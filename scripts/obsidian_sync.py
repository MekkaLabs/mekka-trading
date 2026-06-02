#!/usr/bin/env python3
"""
scripts/obsidian_sync.py
========================
Sincronizador seguro `docs/obsidian` -> vault canônico
`~/Documents/mekka-trading-obsidian`.

Princípios
----------
- One-way: o repo (docs/obsidian) é a fonte versionada; o vault recebe.
- Conservador por padrão: copia apenas arquivos NOVOS no vault.
- Detecta IDÊNTICOS (hash) e CONFLITOS (mesmo path, conteúdo divergente).
- NUNCA sobrescreve silenciosamente. Conflitos precisam de --update ou --force.
- Backup seletivo do alvo antes de qualquer overwrite explícito.
- Exclusões hard-coded protegem decisões PARA do vault e configs locais.
- Tratamento especial e opt-in para .obsidian/community-plugins.json,
  .obsidian/daily-notes.json e .obsidian/templates.json.

Status por arquivo
------------------
- NEW       → existe no source, falta no vault (será copiado em modo padrão)
- IDENTICAL → mesmo path, hash igual (no-op)
- CONFLICT  → mesmo path, hashes diferentes (precisa --update/--force)
- EXCLUDED  → casa com regra de exclusão (sempre ignorado)
- SKIPPED   → opt-in necessário (configs do .obsidian)
- BACKUP    → cópia .bak criada antes de overwrite

Uso
---
    python scripts/obsidian_sync.py                  # dry-run padrão
    python scripts/obsidian_sync.py --apply          # aplica novos arquivos
    python scripts/obsidian_sync.py --apply --update # aplica novos + sobrescreve conflitos com backup
    python scripts/obsidian_sync.py --apply --include-config # também avalia .obsidian/{community-plugins,daily-notes,templates}.json
    python scripts/obsidian_sync.py --apply --force "70 - Templates/Daily Note.md"  # overwrite explícito de UM path
    python scripts/obsidian_sync.py --vault /caminho/alternativo  # destino customizado

Saída: relatório legível + código de saída != 0 se houver CONFLICT não resolvido.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "docs" / "obsidian"
DEFAULT_VAULT = Path.home() / "Documents" / "mekka-trading-obsidian"

# Arquivos do source que NUNCA devem ir ao vault (decisão consciente da
# migração 2026-05-26 — vault organiza projetos sob 10 - Projects/Mekka Trading/).
HARD_EXCLUDED_PATHS: set[str] = {
    "10 - Projects/10 - Projects.md",
    "10 - Projects/Projeto - Mekka Trading.md",
    "10 - Projects/_Projects.md",
}

# Diretórios do source totalmente ignorados.
HARD_EXCLUDED_DIRS: set[str] = {
    ".obsidian/workspace.json",
    ".obsidian/workspace-mobile.json",
    ".obsidian/workspaces.json",
    ".obsidian/cache",
    ".obsidian/appearance.json",
    ".obsidian/graph.json",
    ".trash",
}

# No modo reverso (vault → repo), o "source" é o vault canônico. Aí precisamos
# proteger o repo de receber lixo local-only do Obsidian (workspace state, caches,
# notas operacionais que pertencem só ao operador). Atributos da política
# "Fontes de Verdade" do vault:
#   - 60 - Daily/ é vault-only (não volta ao repo)
#   - 00 - Inbox/ é vault-only (rascunhos)
#   - .obsidian/{workspace*,appearance,graph,cache} são local-only
HARD_EXCLUDED_PATHS_REVERSE: set[str] = {
    "Bem-vindo.md",        # gerado pelo Obsidian no boot do vault
    "LLM-CONNECT.md",      # config local
    "VAULT-START.md",      # config local
}
HARD_EXCLUDED_DIRS_REVERSE: set[str] = {
    "60 - Daily",
    "00 - Inbox",
    ".obsidian/workspace.json",
    ".obsidian/workspace-mobile.json",
    ".obsidian/workspaces.json",
    ".obsidian/cache",
    ".obsidian/appearance.json",
    ".obsidian/graph.json",
    ".obsidian/app.json.bak-",   # backups locais
    ".trash",
}

# Configs do .obsidian que só são tocadas com --include-config.
SOFT_EXCLUDED_CONFIGS: set[str] = {
    ".obsidian/community-plugins.json",
    ".obsidian/daily-notes.json",
    ".obsidian/templates.json",
    ".obsidian/app.json",
    ".obsidian/core-plugins.json",
}

# ---------------------------------------------------------------------------
# Modelo de resultado
# ---------------------------------------------------------------------------


@dataclass
class FileVerdict:
    rel_path: str
    status: str  # NEW | IDENTICAL | CONFLICT | EXCLUDED | SKIPPED | BACKUP_REQUIRED
    source_hash: str = ""
    target_hash: str = ""
    reason: str = ""


@dataclass
class SyncReport:
    verdicts: list[FileVerdict] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    backups: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, v: FileVerdict) -> None:
        self.verdicts.append(v)

    def count(self, status: str) -> int:
        return sum(1 for v in self.verdicts if v.status == status)

    def summary(self) -> str:
        counts = {
            "NEW": self.count("NEW"),
            "IDENTICAL": self.count("IDENTICAL"),
            "CONFLICT": self.count("CONFLICT"),
            "EXCLUDED": self.count("EXCLUDED"),
            "SKIPPED": self.count("SKIPPED"),
        }
        return " | ".join(f"{k}={v}" for k, v in counts.items())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def iter_source_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for p in source.rglob("*"):
        if p.is_file():
            files.append(p)
    return sorted(files)


def relpath(p: Path, base: Path) -> str:
    return str(p.relative_to(base))


def is_hard_excluded(rel: str, reverse: bool = False) -> bool:
    paths = HARD_EXCLUDED_PATHS_REVERSE if reverse else HARD_EXCLUDED_PATHS
    dirs = HARD_EXCLUDED_DIRS_REVERSE if reverse else HARD_EXCLUDED_DIRS
    if rel in paths:
        return True
    for prefix in dirs:
        if rel == prefix or rel.startswith(prefix + "/") or rel.startswith(prefix):
            return True
    return False


def is_soft_excluded(rel: str) -> bool:
    return rel in SOFT_EXCLUDED_CONFIGS


# ---------------------------------------------------------------------------
# Avaliação por arquivo
# ---------------------------------------------------------------------------


def evaluate(
    source_file: Path,
    source_root: Path,
    vault_root: Path,
    include_config: bool,
    forced: set[str],
    reverse: bool = False,
) -> FileVerdict:
    rel = relpath(source_file, source_root)

    if is_hard_excluded(rel, reverse=reverse):
        return FileVerdict(rel, "EXCLUDED", reason="hard-coded exclusion")

    if is_soft_excluded(rel) and not include_config and rel not in forced:
        return FileVerdict(rel, "SKIPPED", reason="config protegida — use --include-config ou --force")

    target = vault_root / rel
    sh = hash_file(source_file)

    if not target.exists():
        return FileVerdict(rel, "NEW", source_hash=sh)

    th = hash_file(target)
    if sh == th:
        return FileVerdict(rel, "IDENTICAL", source_hash=sh, target_hash=th)

    return FileVerdict(rel, "CONFLICT", source_hash=sh, target_hash=th,
                       reason="conteúdo divergente entre source e vault")


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------


def apply_copy(
    source_file: Path,
    rel: str,
    vault_root: Path,
    backup: bool,
    report: SyncReport,
) -> bool:
    target = vault_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if backup and target.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = target.with_suffix(target.suffix + f".bak-{ts}")
        try:
            shutil.copy2(target, bak)
            report.backups.append(str(bak))
        except OSError as exc:
            report.errors.append(f"backup falhou {target}: {exc}")
            return False
    try:
        shutil.copy2(source_file, target)
        report.applied.append(rel)
        return True
    except OSError as exc:
        report.errors.append(f"copy falhou {rel}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    source: Path,
    vault: Path,
    apply: bool,
    update: bool,
    include_config: bool,
    forced: set[str],
    reverse: bool = False,
) -> SyncReport:
    report = SyncReport()

    if not source.exists():
        report.errors.append(f"source não existe: {source}")
        return report
    if not vault.exists():
        report.errors.append(f"vault não existe: {vault}")
        return report

    for sf in iter_source_files(source):
        v = evaluate(sf, source, vault, include_config, forced, reverse=reverse)
        report.add(v)

        if not apply:
            continue

        if v.status == "NEW":
            apply_copy(sf, v.rel_path, vault, backup=False, report=report)
        elif v.status == "CONFLICT" and (update or v.rel_path in forced):
            apply_copy(sf, v.rel_path, vault, backup=True, report=report)
        elif v.status == "SKIPPED" and (include_config or v.rel_path in forced):
            # com include_config virou avaliável; reavalia
            target = vault / v.rel_path
            if not target.exists():
                apply_copy(sf, v.rel_path, vault, backup=False, report=report)
            else:
                th = hash_file(target)
                if th != v.source_hash and (update or v.rel_path in forced):
                    apply_copy(sf, v.rel_path, vault, backup=True, report=report)

    return report


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


def print_report(report: SyncReport, apply: bool, update: bool, vault: Path) -> int:
    print(f"\n=== Obsidian Sync — {'APLICADO' if apply else 'DRY-RUN'} ===")
    print(f"vault: {vault}")
    print(f"resumo: {report.summary()}\n")

    by_status: dict[str, list[FileVerdict]] = {}
    for v in report.verdicts:
        by_status.setdefault(v.status, []).append(v)

    for status in ["NEW", "CONFLICT", "SKIPPED", "EXCLUDED", "IDENTICAL"]:
        items = by_status.get(status, [])
        if not items:
            continue
        print(f"--- {status} ({len(items)}) ---")
        if status == "IDENTICAL":
            print(f"  (omitidos {len(items)} arquivos sem diferença)\n")
            continue
        for v in items:
            extra = f" — {v.reason}" if v.reason else ""
            print(f"  {v.rel_path}{extra}")
        print()

    if report.applied:
        print(f"--- APPLIED ({len(report.applied)}) ---")
        for a in report.applied:
            print(f"  ✓ {a}")
        print()

    if report.backups:
        print(f"--- BACKUPS ({len(report.backups)}) ---")
        for b in report.backups:
            print(f"  💾 {b}")
        print()

    if report.errors:
        print(f"--- ERRORS ({len(report.errors)}) ---")
        for e in report.errors:
            print(f"  ✗ {e}")
        print()

    unresolved_conflicts = report.count("CONFLICT") - sum(
        1 for a in report.applied if a in {v.rel_path for v in report.verdicts if v.status == "CONFLICT"}
    )

    if not apply:
        if report.count("NEW") or report.count("CONFLICT") or report.count("SKIPPED"):
            print("Dry-run: nada foi escrito. Para aplicar:")
            print("  - --apply                 (copia NEW)")
            print("  - --apply --update        (NEW + resolve CONFLICT com backup)")
            print("  - --apply --include-config (também avalia configs .obsidian)")
            print("  - --apply --force <path>   (overwrite explícito de um path)")

    if unresolved_conflicts > 0 and not (apply and update):
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Sincroniza docs/obsidian -> vault Obsidian")
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT,
                    help=f"destino (default: {DEFAULT_VAULT})")
    ap.add_argument("--source", type=Path, default=SOURCE,
                    help=f"origem (default: {SOURCE})")
    ap.add_argument("--apply", action="store_true",
                    help="aplica mudanças (default: dry-run)")
    ap.add_argument("--update", action="store_true",
                    help="resolve CONFLICTs sobrescrevendo com backup")
    ap.add_argument("--include-config", action="store_true",
                    help="também avalia .obsidian/{community-plugins,daily-notes,templates,app,core-plugins}.json")
    ap.add_argument("--force", action="append", default=[],
                    help="path relativo a forçar overwrite (pode repetir)")
    ap.add_argument("--reverse", action="store_true",
                    help="modo INVERSO: vault → docs/obsidian (versionar notas novas do vault canônico)")
    args = ap.parse_args()

    forced = set(args.force)
    # No modo reverso, source vira o vault canônico e o destino vira docs/obsidian.
    # Mantemos os argumentos --source/--vault como referência declarada do usuário:
    # se ele explicitar, respeitamos; senão usamos os defaults invertidos.
    if args.reverse:
        source = args.vault if args.vault != DEFAULT_VAULT else DEFAULT_VAULT
        vault_dest = args.source if args.source != SOURCE else SOURCE
        print(f"[REVERSE] source (canonical vault): {source}")
        print(f"[REVERSE] destination (repo): {vault_dest}")
    else:
        source = args.source
        vault_dest = args.vault

    report = run(
        source=source,
        vault=vault_dest,
        apply=args.apply,
        update=args.update,
        include_config=args.include_config,
        forced=forced,
        reverse=args.reverse,
    )
    return print_report(report, args.apply, args.update, vault_dest)


if __name__ == "__main__":
    sys.exit(main())

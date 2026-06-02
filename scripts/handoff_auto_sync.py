#!/usr/bin/env python3
"""
scripts/handoff_auto_sync.py
=============================
Detecta arquivos ``docs/HANDOFF-*.md`` novos/atualizados e chama
``improvement_vault_writer.write_handoff_summary()`` para cada um —
fechando o loop: HANDOFF gerado → resumo no daily do vault canônico.

Modos:

  - **Cron-friendly:** rode periodicamente (ex: 1x/hora) e o script
    detecta sozinho o que ainda não foi sincronizado via marker file.
  - **One-shot:** passe ``--once <path>`` para sincronizar um handoff
    específico imediatamente.

Marker: ``data/handoff_synced.json`` rastreia hash → timestamp para evitar
reescritas duplicadas no vault.

Hard rules:
  - Fail-silent: erros em um handoff não afetam os outros.
  - Não escreve no vault se ``IMPROVEMENT_VAULT_WRITER_ENABLED != true``.
  - Não modifica os HANDOFFs originais (read-only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


_DOCS = _REPO / "docs"
_MARKER_FILE = _REPO / "data" / "handoff_synced.json"


def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    try:
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()[:16]


def _load_marker() -> dict:
    if not _MARKER_FILE.exists():
        return {}
    try:
        return json.loads(_MARKER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_marker(data: dict) -> None:
    try:
        _MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MARKER_FILE.write_text(json.dumps(data, indent=2, sort_keys=True),
                                encoding="utf-8")
    except OSError as exc:
        print(f"warn: could not save marker: {exc}", file=sys.stderr)


def _iter_handoffs() -> list[Path]:
    return sorted(_DOCS.glob("HANDOFF-*.md"))


def sync_one(path: Path, marker: dict, force: bool = False) -> str:
    rel = str(path.relative_to(_REPO))
    cur_hash = _hash_file(path)
    if not cur_hash:
        return f"{rel}: SKIP (read failed)"
    seen = marker.get(rel, {})
    if seen.get("hash") == cur_hash and not force:
        return f"{rel}: SKIP (already synced, hash match)"
    try:
        from src.services import improvement_vault_writer as ivw
    except Exception as exc:
        return f"{rel}: SKIP (cannot import writer: {exc})"
    if not ivw.is_writer_enabled():
        return f"{rel}: SKIP (writer disabled — set IMPROVEMENT_VAULT_WRITER_ENABLED=true)"
    written = ivw.write_handoff_summary(path)
    if written:
        marker[rel] = {
            "hash": cur_hash,
            "synced_at": datetime.now().isoformat(timespec="seconds"),
            "target": str(written),
        }
        return f"{rel}: SYNCED → {written.name}"
    return f"{rel}: SKIP (no TL;DR or write failed)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Sincroniza HANDOFF-*.md → vault daily")
    ap.add_argument("--once", type=Path, help="Sync apenas este path")
    ap.add_argument("--force", action="store_true",
                    help="Re-sync mesmo se hash bate (use após edição manual)")
    args = ap.parse_args()

    marker = _load_marker()
    results: list[str] = []
    targets = [args.once] if args.once else _iter_handoffs()

    for p in targets:
        if not p.exists():
            results.append(f"{p}: SKIP (does not exist)")
            continue
        msg = sync_one(p, marker, force=args.force)
        results.append(msg)
        print(msg)

    _save_marker(marker)
    return 0


if __name__ == "__main__":
    sys.exit(main())

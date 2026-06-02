#!/usr/bin/env python3
"""
scripts/backfill_bridge_after_snapshots.py
============================================
Backfill: tira snapshot Sage AFTER para IMPs que já foram mergeadas
mas nunca tiveram on_improvement_pr_merged() chamado.

Contexto (auditoria 2026-05-29):
- 24 IMPs em improvement_memory_bridge.json têm "before" mas 0 têm "after"
- pr_tracker.mark_imp_merged agora chama on_improvement_pr_merged automaticamente
  (REV-1 fix), mas as IMPs já mergeadas antes desse fix ficaram sem after_kpis
- Este script roda once: pega cada IMP merged, dispara on_improvement_pr_merged

Uso:
    python3 scripts/backfill_bridge_after_snapshots.py --dry-run     # default
    python3 scripts/backfill_bridge_after_snapshots.py --apply       # roda real
    python3 scripts/backfill_bridge_after_snapshots.py --apply --limit 5

Hard rules:
- READ-ONLY no improvement_queue.json (não muta dev_state)
- Idempotent: se entry já tem "after", pula
- Fail-tolerant: erro em uma IMP não afeta as outras
- Rate-limited: sleep 1s entre cada (Sage faz queries DB)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


async def backfill_one(rec_id: str, entry: dict, dry_run: bool) -> dict:
    """Roda on_improvement_pr_merged para uma IMP. Retorna resultado."""
    result = {
        "rec_id": rec_id,
        "skipped": False,
        "reason": "",
        "before_present": bool(entry.get("before")),
        "after_present": bool(entry.get("after")),
    }
    if entry.get("after"):
        result["skipped"] = True
        result["reason"] = "already has after snapshot"
        return result
    if dry_run:
        result["reason"] = "would call on_improvement_pr_merged (dry-run)"
        return result
    try:
        from src.services.improvement_memory_bridge import on_improvement_pr_merged
        pr_num = entry.get("pr_number")
        commit_sha = entry.get("commit_sha")
        out = await on_improvement_pr_merged(
            rec_id, pr_number=pr_num, commit_sha=commit_sha,
        )
        result["reason"] = "after snapshot captured"
        result["bridge_entry_after"] = bool(out and out.get("after"))
    except Exception as exc:  # noqa: BLE001
        result["reason"] = f"error: {exc}"
    return result


async def main(args) -> int:
    bridge_file = _REPO / "data" / "improvement_memory_bridge.json"
    queue_file = _REPO / "data" / "improvement_queue.json"
    prs_file = _REPO / "data" / "improvement_prs.json"

    bridge = _load_json(bridge_file, {})
    queue = _load_json(queue_file, {})
    prs = _load_json(prs_file, {})

    # 2 fontes possíveis de "merged":
    # a) improvement_queue.json[rec_id].dev_state == "merged"
    # b) improvement_prs.json[rec_id].dev_state == "merged"
    # c) bridge entry tem merged_at/commit_sha
    candidates = []
    # Primeiro: IMPs no bridge sem after
    for rec_id, entry in bridge.items():
        if entry.get("after"):
            continue  # já fechado
        queue_entry = queue.get(rec_id, {})
        pr_entry = prs.get(rec_id, {})
        is_merged = (
            queue_entry.get("dev_state") == "merged"
            or pr_entry.get("dev_state") == "merged"
            or entry.get("merged_at")
            or entry.get("commit_sha")
        )
        if not is_merged:
            continue
        candidates.append((rec_id, entry))

    # Segundo: IMPs em prs.json merged que NÃO estão no bridge — também precisam
    for rec_id, pr_entry in prs.items():
        if rec_id in bridge:
            continue
        if pr_entry.get("dev_state") != "merged":
            continue
        # Cria entry virtual pra backfill
        candidates.append((rec_id, {
            "before": None,
            "merged_at": pr_entry.get("merged_at"),
            "pr_number": pr_entry.get("pr_number"),
        }))

    print(f"📋 Found {len(candidates)} merged IMPs without after_kpis")
    if args.limit:
        candidates = candidates[: args.limit]
        print(f"   (limited to {len(candidates)})")
    print(f"   Mode: {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    if not candidates:
        print("✓ Nothing to backfill. Bridge is complete.")
        return 0

    results = []
    for i, (rec_id, entry) in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {rec_id}")
        result = await backfill_one(rec_id, entry, dry_run=args.dry_run)
        results.append(result)
        print(f"    → {result['reason']}")
        if not args.dry_run and i < len(candidates):
            await asyncio.sleep(1.0)  # rate-limit Sage queries

    # Summary
    print()
    print("=" * 60)
    captured = sum(1 for r in results if "captured" in r["reason"])
    skipped = sum(1 for r in results if r["skipped"])
    errors = sum(1 for r in results if "error" in r["reason"])
    print(f"Summary: {captured} captured | {skipped} skipped | {errors} errors")

    if not args.dry_run:
        # Show bridge state
        bridge_after = _load_json(bridge_file, {})
        with_after = sum(1 for v in bridge_after.values() if v.get("after"))
        print(f"Bridge state: {with_after}/{len(bridge_after)} IMPs now have after_kpis")

    return 0 if errors == 0 else 1


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="Show what would be done (default)")
    g.add_argument("--apply", dest="dry_run", action="store_false",
                   help="Actually run on_improvement_pr_merged")
    p.add_argument("--limit", type=int, default=0,
                   help="Max IMPs to backfill (default: all)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(main(args)))

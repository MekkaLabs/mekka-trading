#!/usr/bin/env python3
"""
scripts/imp_reconcile.py
=========================
CLI para reconciliação semi-automática de IMPs paradas em "queued".

Lê todas as IMPs sem PR e procura commits recentes que possam tê-las
resolvido (heurística de palavras-chave + path de arquivos). Apresenta
sugestões ranqueadas.

Uso
---
    # 1) Dry-run: mostra sugestões SEM mutar nada (sempre rode primeiro)
    python scripts/imp_reconcile.py --dry-run

    # 2) JSON output (para integração com dashboard)
    python scripts/imp_reconcile.py --dry-run --json

    # 3) Reconciliar 1 IMP específica para 1 commit (interativo)
    python scripts/imp_reconcile.py --apply <rec_id> <commit_sha> [--summary "..."]

    # 4) Janela de busca (default 30 dias)
    python scripts/imp_reconcile.py --dry-run --days 60

Exit codes
----------
    0 — sucesso
    1 — erro de uso / args
    2 — operação falhou
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.services.improvement_memory_bridge import (  # noqa: E402
    auto_reconcile_dry_run,
    find_match_candidates,
    mark_resolved_manual,
)


def cmd_dry_run(args: argparse.Namespace) -> int:
    report = auto_reconcile_dry_run(days=args.days)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("=" * 70)
    print(f"  IMP RECONCILIATION DRY-RUN — janela: {report['days_searched']} dias")
    print("=" * 70)
    print(f"  IMPs paradas em 'queued': {report['total_queued']}")
    print(f"  Com candidatos de match:  {len(report['candidates'])}")
    print(f"  Sem nenhum match:         {len(report['no_match'])}")
    print("=" * 70)
    print()
    for rec_id, candidates in report["candidates"].items():
        print(f"IMP-{rec_id}")
        for i, c in enumerate(candidates, 1):
            print(f"  [{i}] score={c['score']:.2f}  {c['short_sha']}  {c['subject']}")
        print()
    if report["no_match"]:
        print(f"--- {len(report['no_match'])} IMPs sem match (verificação manual) ---")
        for rec_id in report["no_match"]:
            print(f"  · IMP-{rec_id}")
    print()
    print("Próximo passo: validar manualmente e aplicar via")
    print("  python scripts/imp_reconcile.py --apply <rec_id> <commit_sha>")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    if not args.rec_id or not args.commit_sha:
        print("erro: --apply requer <rec_id> e <commit_sha>", file=sys.stderr)
        return 1
    result = mark_resolved_manual(
        rec_id=args.rec_id, commit_sha=args.commit_sha, summary=args.summary or "",
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


def cmd_show(args: argparse.Namespace) -> int:
    matches = find_match_candidates(args.rec_id, top_n=10, days=args.days)
    if args.json:
        print(json.dumps(matches, indent=2))
    else:
        print(f"Top candidatos para IMP-{args.rec_id}:")
        for i, c in enumerate(matches, 1):
            print(f"  [{i}] score={c['score']:.2f} {c['short_sha']} {c['subject']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconciliação IMP ↔ commit")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("dry-run", help="Relatório de IMPs paradas + matches")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("show", help="Top candidatos para uma IMP específica")
    p.add_argument("rec_id")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("apply", help="Reconcilia rec_id ↔ commit_sha")
    p.add_argument("rec_id")
    p.add_argument("commit_sha")
    p.add_argument("--summary", default=None)
    p.set_defaults(func=cmd_apply)

    # Atalho: sem subcomando → dry-run (uso comum)
    ap.add_argument("--dry-run", action="store_true",
                    help="Atalho para subcomando dry-run")
    ap.add_argument("--apply", nargs="*", help="Atalho: --apply rec_id commit_sha")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--summary", default=None)

    args = ap.parse_args()

    if args.command:
        return args.func(args)
    if args.apply:
        if len(args.apply) < 2:
            print("erro: --apply <rec_id> <commit_sha>", file=sys.stderr)
            return 1
        args.rec_id, args.commit_sha = args.apply[0], args.apply[1]
        return cmd_apply(args)
    # default → dry-run
    return cmd_dry_run(args)


if __name__ == "__main__":
    sys.exit(main())

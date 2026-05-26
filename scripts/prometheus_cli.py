#!/usr/bin/env python3
"""
scripts/prometheus_cli.py
==========================
CLI do agente Prometheus — engenharia de prompts do Mekka.

Subcomandos
-----------
    audit <arquivo>          Audita todos os prompts de um arquivo Python
    audit-text               Audita texto via stdin (echo "..." | prometheus_cli audit-text)
    scan-agents [<dir>]      Lista todos os prompts encontrados (default: src/agents)
    list                     Lista catálogo persistente
    show <name>              Mostra detalhes de um prompt do catálogo
    register <arquivo>       Audita + registra TODOS os prompts no catálogo

Variáveis de ambiente
---------------------
    PROMETHEUS_CATALOG_ENABLED=true  Habilita persistência no catálogo
                                      (default: false — auditoria sempre roda)

Exit codes
----------
    0 — sucesso
    1 — erro de uso
    2 — arquivo não encontrado
    3 — nenhum prompt detectado
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.prompt_engineering import Prometheus  # noqa: E402


def cmd_audit(args: argparse.Namespace) -> int:
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"erro: arquivo não existe — {file_path}", file=sys.stderr)
        return 2

    p = Prometheus(repo_root=REPO_ROOT)
    prompts = p.extract(file_path)
    if not prompts:
        print(f"nenhum prompt detectado em {file_path} (mín. 80 chars)")
        return 3

    for prompt in prompts:
        scorecard = p.audit(prompt)
        if args.json:
            payload = {
                "prompt": prompt.model_dump(mode="json"),
                "scorecard": scorecard.model_dump(mode="json"),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(p.report_text(prompt, scorecard))
            print()
    return 0


def cmd_audit_text(args: argparse.Namespace) -> int:
    text = sys.stdin.read()
    if len(text.strip()) < 80:
        print("erro: texto curto demais (<80 chars) — provavelmente não é prompt", file=sys.stderr)
        return 1
    p = Prometheus(repo_root=REPO_ROOT)
    scorecard = p.audit_text(text)
    if args.json:
        print(json.dumps(scorecard.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        for d in scorecard.dimensions:
            print(f"{d.dimension.value.upper():22s}: {d.score}/10")
            for f in d.findings:
                print(f"  → {f}")
        print()
        print(f"SCORE GERAL: {scorecard.score_total}/40  [{scorecard.health}]")
        if scorecard.recommendations:
            print()
            print("AÇÕES RECOMENDADAS:")
            for i, rec in enumerate(scorecard.recommendations, 1):
                print(f"  {i}. {rec}")
    return 0


def cmd_scan_agents(args: argparse.Namespace) -> int:
    target = Path(args.dir).resolve() if args.dir else REPO_ROOT / "src" / "agents"
    p = Prometheus(repo_root=REPO_ROOT)
    prompts = p.scan_agents(agents_dir=target)
    if not prompts:
        print(f"nenhum prompt detectado em {target}")
        return 3
    if args.json:
        print(json.dumps(
            [pr.model_dump(mode="json") for pr in prompts],
            ensure_ascii=False, indent=2,
        ))
    else:
        print(f"{len(prompts)} prompt(s) encontrado(s) em {target}:\n")
        for pr in prompts:
            print(f"  · {pr.source_file}:{pr.line_number} — {pr.variable_name}")
            print(f"      role={pr.detected_role or 'N/A'}  len={len(pr.content)}  fp={pr.fingerprint}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    p = Prometheus(repo_root=REPO_ROOT)
    records = p.list_catalog()
    if not records:
        from src.prompt_engineering.catalog import is_catalog_enabled
        if not is_catalog_enabled():
            print("catálogo desabilitado (defina PROMETHEUS_CATALOG_ENABLED=true)")
        else:
            print("catálogo vazio")
        return 0
    if args.json:
        print(json.dumps([r.model_dump(mode="json") for r in records],
                         ensure_ascii=False, indent=2))
    else:
        print(f"{len(records)} prompt(s) no catálogo:\n")
        for r in records:
            sc = r.scorecard
            score_str = f"{sc.score_total}/40 [{sc.health}]" if sc else "(não auditado)"
            print(f"  · {r.name:40s}  {score_str}")
            print(f"      fp={r.fingerprint}  source={r.extracted.source_file}:{r.extracted.line_number}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    p = Prometheus(repo_root=REPO_ROOT)
    record = p.catalog.find_by_name(args.name) if p._catalog_enabled else None
    if not record:
        print(f"não encontrado: {args.name}", file=sys.stderr)
        return 1
    print(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    import os
    if os.environ.get("PROMETHEUS_CATALOG_ENABLED", "false").lower() not in (
        "1", "true", "yes", "on"
    ):
        print("erro: catálogo desabilitado. Rode com PROMETHEUS_CATALOG_ENABLED=true.",
              file=sys.stderr)
        return 1

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"erro: arquivo não existe — {file_path}", file=sys.stderr)
        return 2

    p = Prometheus(repo_root=REPO_ROOT)
    prompts = p.extract(file_path)
    if not prompts:
        print(f"nenhum prompt detectado em {file_path}")
        return 3

    statuses: dict[str, int] = {"created": 0, "updated": 0, "unchanged": 0}
    for prompt in prompts:
        sc = p.audit(prompt)
        status, record = p.register(prompt, scorecard=sc)
        if status:
            statuses[status] = statuses.get(status, 0) + 1
            print(f"  [{status:9s}] {record.name}  {sc.score_total}/40")

    print(f"\nresumo: {statuses}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="prometheus",
        description="Prometheus — engenharia de prompts do Mekka",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="audita prompts de um arquivo .py")
    p_audit.add_argument("file")
    p_audit.add_argument("--json", action="store_true")
    p_audit.set_defaults(func=cmd_audit)

    p_text = sub.add_parser("audit-text", help="audita texto via stdin")
    p_text.add_argument("--json", action="store_true")
    p_text.set_defaults(func=cmd_audit_text)

    p_scan = sub.add_parser("scan-agents", help="lista prompts em diretório")
    p_scan.add_argument("dir", nargs="?", default=None)
    p_scan.add_argument("--json", action="store_true")
    p_scan.set_defaults(func=cmd_scan_agents)

    p_list = sub.add_parser("list", help="lista catálogo persistente")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="mostra detalhes de prompt do catálogo")
    p_show.add_argument("name")
    p_show.set_defaults(func=cmd_show)

    p_reg = sub.add_parser("register", help="audita+registra prompts de um arquivo")
    p_reg.add_argument("file")
    p_reg.set_defaults(func=cmd_register)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

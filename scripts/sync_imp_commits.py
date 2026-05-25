#!/usr/bin/env python3
"""Sync recent git commits with the improvement PR tracker.

Detects ``[IMP-{rec_id}]`` patterns in commit messages and registers each
matching commit as a PR for that recommendation via
``pr_tracker.set_pr()``. Closes the gap where a dev would implement an
accepted brief but forget to manually call ``set_pr``, leaving the brief
stuck at ``dev_state=queued`` even though the work was done.

Usage
-----
  python scripts/sync_imp_commits.py [--limit 50] [--since '7 days ago']

Pre-push hook
-------------
Add this to ``.git/hooks/pre-push`` to auto-sync before every push:

  #!/bin/sh
  python scripts/sync_imp_commits.py --quiet || true

The script never aborts a push (returns 0 even on partial failures).

Behaviour
---------
- Pattern: ``[IMP-{12_hex_chars}]`` anywhere in the commit subject or body
- For each match, calls ``pr_tracker.set_pr(rec_id, pr_number, branch, summary)``
  where ``pr_number`` is a synthetic local ID (we have no remote PR, so we
  use the SHA-derived integer to keep entries unique)
- Idempotent: re-running the script is safe; set_pr overwrites entries with
  the same rec_id and the latest commit info wins
- Skips commits already registered at ``dev_state=merged`` (don't downgrade)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.services import pr_tracker  # noqa: E402


_PATTERN = re.compile(r"\[IMP-([0-9a-fA-F]{6,32})\]")


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
            timeout=10,
        )
        return out.stdout or ""
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"[sync_imp_commits] git failed: {exc}", file=sys.stderr)
        return ""


def _current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD").strip() or "main"


def _list_commits(limit: int, since: str | None) -> list[dict]:
    """Return list of {sha, subject, body, files} for recent commits.

    Uses two git invocations: one for SHA/subject/body (with a unique
    record separator) and one ``git show --name-only`` per SHA for the
    file list. Avoids the ambiguity of ``log --name-only`` where commit
    boundaries and file lists share newlines.
    """
    fmt = "%H%x1f%s%x1f%b%x1e"
    args = ["log", f"-{limit}", f"--pretty=format:{fmt}"]
    if since:
        args.append(f"--since={since}")
    raw = _git(*args)
    if not raw:
        return []
    commits: list[dict] = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 3:
            continue
        sha, subject, body = parts[0].strip(), parts[1], parts[2]
        if not sha:
            continue
        files_raw = _git("show", "--pretty=", "--name-only", sha)
        files = [f.strip() for f in files_raw.split("\n") if f.strip()]
        commits.append({"sha": sha, "subject": subject, "body": body, "files": files})
    return commits


def _synthetic_pr_number(sha: str) -> int:
    """Map a SHA to a stable 7-digit local PR number (avoids gh PR collision)."""
    return int(sha[:7], 16) % 10_000_000 + 90_000_000  # 9XXXXXXX range


def sync(limit: int = 50, since: str | None = None, quiet: bool = False) -> dict:
    branch = _current_branch()
    commits = _list_commits(limit=limit, since=since)
    out: dict = {"scanned": len(commits), "matched": 0, "registered": 0, "skipped_merged": 0, "errors": []}

    existing_status = pr_tracker.get_pr_status()

    for c in commits:
        text = f"{c['subject']}\n{c['body']}"
        ids = _PATTERN.findall(text)
        if not ids:
            continue
        out["matched"] += len(ids)
        for rec_id in {rid.lower()[:16] for rid in ids}:
            current = existing_status.get(rec_id) or {}
            dev_state = current.get("dev_state")
            if dev_state == "merged":
                out["skipped_merged"] += 1
                if not quiet:
                    print(f"  ↷ {rec_id[:12]} already merged — skipping {c['sha'][:7]}")
                continue
            try:
                summary = c["subject"].strip()[:200] + f" ({c['sha'][:7]})"
                r = pr_tracker.set_pr(
                    rec_id=rec_id,
                    pr_number=_synthetic_pr_number(c["sha"]),
                    branch=branch,
                    summary=summary,
                    files_changed=c["files"][:50],
                )
                if r.get("ok"):
                    out["registered"] += 1
                    if not quiet:
                        print(f"  ✔ {rec_id[:12]} ← {c['sha'][:7]} on {branch}")
                else:
                    out["errors"].append(f"{rec_id}: {r.get('error')}")
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"{rec_id}: {exc}")

    if not quiet:
        print(
            f"\n[sync_imp_commits] scanned={out['scanned']} "
            f"matched={out['matched']} registered={out['registered']} "
            f"skipped_merged={out['skipped_merged']} errors={len(out['errors'])}"
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=50, help="how many commits to scan")
    parser.add_argument("--since", type=str, default=None, help="git --since value (e.g. '7 days ago')")
    parser.add_argument("--quiet", action="store_true", help="suppress per-commit output")
    args = parser.parse_args()
    sync(limit=args.limit, since=args.since, quiet=args.quiet)
    return 0  # never block on errors


if __name__ == "__main__":
    sys.exit(main())

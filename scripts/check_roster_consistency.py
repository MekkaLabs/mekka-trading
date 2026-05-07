#!/usr/bin/env python3
"""
scripts/check_roster_consistency.py
====================================
Drift guard between AGENTS.md (human-facing roster) and
agents/registry.ts (machine-readable roster used in TS code).

If the two diverge, this script exits non-zero so CI can fail the build.

Usage
-----
    python3 scripts/check_roster_consistency.py

Exit codes
----------
    0  — rosters consistent
    1  — divergence detected (printed to stderr)
    2  — could not parse one of the files

Detection
---------
- AGENTS.md  : looks for lines starting with "- **<HeroName>**" inside
               the four "### Layer X" sections.
- registry.ts: extracts every `codename: '<HeroName>'` literal.

Heroes that exist in only one of the files are reported. Pure
ordering differences are tolerated — what matters is set equality.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = REPO_ROOT / "AGENTS.md"
REGISTRY_TS = REPO_ROOT / "agents" / "registry.ts"


def parse_agents_md(path: Path) -> set[str]:
    """Extract hero names from `- **<Name>**` bullets inside Layer sections."""
    if not path.exists():
        print(f"[FAIL] {path} not found", file=sys.stderr)
        sys.exit(2)
    pattern = re.compile(r"^\s*-\s+\*\*([A-Za-z][A-Za-z\s\-]*?)\*\*", re.MULTILINE)
    names: set[str] = set()
    inside_layer = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### Layer ") or line.startswith("### Pending heroes"):
            inside_layer = True
            continue
        if line.startswith("## ") and not line.startswith("### "):
            inside_layer = False
        if not inside_layer:
            continue
        m = pattern.match(line)
        if m:
            names.add(_normalize(m.group(1)))
    return names


def parse_registry_ts(path: Path) -> set[str]:
    """Extract every `codename: '<Name>'` from the TS registry."""
    if not path.exists():
        print(f"[FAIL] {path} not found", file=sys.stderr)
        sys.exit(2)
    pattern = re.compile(r"codename:\s*['\"]([^'\"]+)['\"]")
    return {_normalize(m) for m in pattern.findall(path.read_text(encoding="utf-8"))}


def _normalize(name: str) -> str:
    """Canonical hero name: trim, collapse spaces, drop hyphens."""
    return name.strip().replace("-", "").replace(" ", "").lower()


def main() -> int:
    md_set = parse_agents_md(AGENTS_MD)
    ts_set = parse_registry_ts(REGISTRY_TS)

    only_in_md = md_set - ts_set
    only_in_ts = ts_set - md_set

    if not only_in_md and not only_in_ts:
        print(f"[OK] Roster consistent — {len(md_set)} heroes")
        return 0

    print("[FAIL] Roster drift detected", file=sys.stderr)
    if only_in_md:
        print(
            f"  In AGENTS.md only ({len(only_in_md)}): "
            + ", ".join(sorted(only_in_md)),
            file=sys.stderr,
        )
    if only_in_ts:
        print(
            f"  In registry.ts only ({len(only_in_ts)}): "
            + ", ".join(sorted(only_in_ts)),
            file=sys.stderr,
        )
    print(
        "\nFix: update both files until they match. The hero-name "
        "comparison is case-insensitive and ignores spaces/hyphens.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
scripts/obsidian_normalize.py
=============================
One-shot vault normaliser. Converts relative wikilinks to short links
(matching app.json's newLinkFormat:"shortest"), removes the lingering
`../path/Note` style that the codex baseline used.

Why this exists
---------------
Obsidian resolves `[[Foo]]` against the vault's full file index, so
short links are robust to file moves. Relative links like
`[[../20 - Areas/Agentes IA/Nick Fury]]` break the moment any segment
in the path changes, and they bloat the diff every time a note moves.
The vault's app.json already declares `newLinkFormat: "shortest"`, so
all NEW links Obsidian creates are short — this script just brings the
existing legacy links into line.

Usage
-----
    python scripts/obsidian_normalize.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent / "docs" / "obsidian"

# Match wikilinks with a path component: [[../foo/bar]] or [[foo/bar]].
# Captures the link body so we can preserve any |alias suffix.
# Excludes pure short links like [[Foo]] (no slash) and image embeds (![[...]]).
WIKILINK_PATH = re.compile(r"(?<!!)\[\[([^\[\]\n]+?)\]\]")


def shorten(link: str) -> str:
    """Drop directory prefix from a wikilink path, keep alias."""
    # Split off alias if present (after |)
    alias = ""
    if "|" in link:
        link, alias = link.split("|", 1)
    # If the link has no slash, it's already short.
    if "/" not in link:
        return f"[[{link}|{alias}]]" if alias else f"[[{link}]]"
    # Drop directory components — keep only the last segment.
    last = link.rstrip("/").split("/")[-1]
    # Remove trailing .md if present (rare but seen).
    if last.endswith(".md"):
        last = last[:-3]
    return f"[[{last}|{alias}]]" if alias else f"[[{last}]]"


def normalise_file(p: Path, dry_run: bool) -> int:
    """Return number of replacements made (or that would have been made)."""
    text = p.read_text()
    count = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal count
        body = m.group(1)
        # Skip if body has no path separator and no .md — already short.
        if "/" not in body and not body.endswith(".md"):
            return m.group(0)
        new = shorten(body)
        if new != m.group(0):
            count += 1
        return new

    new_text = WIKILINK_PATH.sub(_sub, text)
    if count > 0 and not dry_run:
        p.write_text(new_text)
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = ap.parse_args()

    md_files = sorted(VAULT.rglob("*.md"))
    total = 0
    changed_files = 0
    for p in md_files:
        n = normalise_file(p, dry_run=args.dry_run)
        if n > 0:
            changed_files += 1
            total += n
            rel = p.relative_to(VAULT)
            print(f"  {n:3d}× {rel}")

    suffix = "(dry-run — no writes)" if args.dry_run else ""
    print(f"\nNormalised {total} wikilinks across {changed_files} files {suffix}".strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())

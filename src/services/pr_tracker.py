"""
src/services/pr_tracker.py
==========================
Tracks the GitHub PR resulting from each accepted Mekka improvement so the
operator can review/approve it from the dashboard.

State lives in ``data/improvement_prs.json`` (gitignored runtime artifact),
mapping ``rec_id -> {dev_state, pr_number?, branch?, summary?,
files_changed?, approved_at?}``.

Live enrichment uses the GitHub CLI (``gh``). Everything degrades gracefully:
if ``gh`` is missing, unauthenticated, or times out, we fall back to the
stored fields and never raise.

Hard rules
----------
  • NEVER raises — subprocess / parse failures return safe defaults.
  • NEVER runs ``gh pr merge`` unless ``do_merge=True`` is passed explicitly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_PRS_FILE = _DATA_DIR / "improvement_prs.json"

_GH_TIMEOUT = 10  # seconds

_VALID_DEV_STATES = {"queued", "in_dev", "pr_open", "merged"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _load_store() -> dict[str, dict]:
    if not _PRS_FILE.exists():
        return {}
    try:
        data = json.loads(_PRS_FILE.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_store(store: dict[str, dict]) -> bool:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _PRS_FILE.write_text(
            json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except (OSError, ValueError) as exc:
        logger.warning(f"[pr_tracker] could not persist store: {exc}")
        return False


def _gh_pr_view(pr_number: int) -> dict[str, Any] | None:
    """Return live PR JSON via ``gh``, or None on any failure."""
    if not _gh_available():
        return None
    try:
        proc = subprocess.run(
            [
                "gh", "pr", "view", str(pr_number),
                "--json", "number,url,headRefName,title,state,files",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning(f"[pr_tracker] gh pr view {pr_number} failed: {exc}")
        return None
    if proc.returncode != 0:
        logger.warning(
            f"[pr_tracker] gh pr view {pr_number} rc={proc.returncode}: "
            f"{(proc.stderr or '').strip()[:200]}"
        )
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None


def _files_from_gh(view: dict[str, Any]) -> list[str]:
    files = view.get("files")
    if not isinstance(files, list):
        return []
    out: list[str] = []
    for f in files:
        if isinstance(f, dict) and f.get("path"):
            out.append(str(f["path"]))
        elif isinstance(f, str):
            out.append(f)
    return out


def _dev_state_for(stored: dict, gh_state: str | None) -> str:
    """Resolve dev_state, advancing to 'merged' if GitHub says so."""
    if gh_state and gh_state.upper() == "MERGED":
        return "merged"
    state = str(stored.get("dev_state") or "queued")
    return state if state in _VALID_DEV_STATES else "queued"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pr_status() -> dict[str, dict]:
    """Return the PR status map for all tracked recommendations.

    Shape::

        {
          "<rec_id>": {
            "dev_state": "queued" | "in_dev" | "pr_open" | "merged",
            "pr": {
              "number": int | None,
              "url": str | None,
              "branch": str | None,
              "title": str | None,
              "summary": str | None,
              "files_changed": list[str],
            } | None
          },
          ...
        }

    Entries with a ``pr_number`` are enriched with live ``gh`` data when
    available; otherwise stored fields are used. Never raises.
    """
    store = _load_store()
    result: dict[str, dict] = {}

    for rec_id, stored in store.items():
        if not isinstance(stored, dict):
            continue

        pr_number = stored.get("pr_number")
        pr_block: dict | None = None
        gh_state: str | None = None

        if pr_number is not None:
            view = _gh_pr_view(int(pr_number)) if str(pr_number).isdigit() else None
            if view:
                gh_state = str(view.get("state") or "") or None
                pr_block = {
                    "number": view.get("number", pr_number),
                    "url": view.get("url") or stored.get("url"),
                    "branch": view.get("headRefName") or stored.get("branch"),
                    "title": view.get("title") or stored.get("summary"),
                    "summary": stored.get("summary"),
                    "files_changed": _files_from_gh(view)
                    or list(stored.get("files_changed") or []),
                }
            else:
                # Fall back to stored fields.
                pr_block = {
                    "number": pr_number,
                    "url": stored.get("url"),
                    "branch": stored.get("branch"),
                    "title": stored.get("summary"),
                    "summary": stored.get("summary"),
                    "files_changed": list(stored.get("files_changed") or []),
                }

        result[rec_id] = {
            "dev_state": _dev_state_for(stored, gh_state),
            "pr": pr_block,
        }

    return result


def mark_merged(rec_id: str) -> dict:
    """Mark a recommendation's PR as merged/delivered (dev_state='merged').

    Used in the local-only deployment where there's no remote PR to merge via
    gh: the operator's approval in the dashboard IS the delivery gate (the code
    was already committed at dev time). Never raises.
    """
    rec_id = str(rec_id or "").strip()
    if not rec_id:
        return {"ok": False, "error": "missing rec_id"}
    store = _load_store()
    entry = store.get(rec_id) or {}
    entry["dev_state"] = "merged"
    entry["merged_at"] = _now()
    store[rec_id] = entry
    ok = _save_store(store)
    return {"ok": bool(ok)}


def set_pr(
    rec_id: str,
    pr_number: int,
    branch: str,
    summary: str,
    files_changed: list[str] | None = None,
) -> dict:
    """Register a PR for a recommendation (dev workflow hook).

    Writes ``data/improvement_prs.json`` with ``dev_state="pr_open"``.
    Returns ``{"ok": bool, "error"?: str}``. Never raises.
    """
    rec_id = str(rec_id or "").strip()
    if not rec_id:
        return {"ok": False, "error": "missing rec_id"}

    store = _load_store()
    entry = store.get(rec_id) or {}
    entry.update(
        {
            "dev_state": "pr_open",
            "pr_number": int(pr_number) if str(pr_number).isdigit() or isinstance(pr_number, int) else pr_number,
            "branch": str(branch or ""),
            "summary": str(summary or ""),
            "files_changed": list(files_changed or []),
            "updated_at": _now(),
        }
    )
    store[rec_id] = entry
    if not _save_store(store):
        return {"ok": False, "error": "could not persist store"}
    logger.info(f"[pr_tracker] registered PR #{pr_number} for {rec_id}")
    return {"ok": True}


def approve_pr(rec_id: str, pr_number: int, do_merge: bool = False) -> dict:
    """Record operator approval for a PR; optionally squash-merge it.

    Returns ``{"ok": bool, "merged": bool, "error"?: str}``.

    ``gh pr merge`` is invoked ONLY when ``do_merge=True``. Never raises.
    """
    rec_id = str(rec_id or "").strip()
    if not rec_id:
        return {"ok": False, "merged": False, "error": "missing rec_id"}

    store = _load_store()
    entry = store.get(rec_id) or {}
    entry["approved_at"] = _now()
    if entry.get("pr_number") is None:
        entry["pr_number"] = pr_number
    # Ensure dev_state is at least pr_open once approved.
    if str(entry.get("dev_state") or "queued") not in ("pr_open", "merged"):
        entry["dev_state"] = "pr_open"

    merged = False
    error: str | None = None

    if do_merge:
        if not _gh_available():
            error = "gh not available"
        else:
            try:
                proc = subprocess.run(
                    ["gh", "pr", "merge", str(pr_number), "--squash"],
                    capture_output=True,
                    text=True,
                    timeout=_GH_TIMEOUT * 3,
                )
                if proc.returncode == 0:
                    merged = True
                    entry["dev_state"] = "merged"
                    entry["merged_at"] = _now()
                else:
                    error = (proc.stderr or proc.stdout or "gh pr merge failed").strip()[:300]
            except (subprocess.SubprocessError, OSError) as exc:
                error = f"gh pr merge error: {exc}"

    store[rec_id] = entry
    persisted = _save_store(store)
    if not persisted and error is None:
        error = "could not persist store"

    ok = persisted and (error is None or merged)
    out: dict = {"ok": bool(ok and (not do_merge or merged)), "merged": merged}
    if error:
        out["error"] = error
        if not merged:
            out["ok"] = False
    logger.info(f"[pr_tracker] approve_pr {rec_id} pr=#{pr_number} merged={merged}")
    return out

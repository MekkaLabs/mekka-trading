"""
src/services/improvement_queue.py
=================================
Improvement-brief inbox for the AIOS dev-squad / Claude Code.

When the operator ACCEPTS a Mekka recommendation in the "Central de Melhorias"
panel, ``enqueue_brief(rec)`` writes a structured Markdown dev brief into
``docs/improvement-queue/IMP-<rec_id>.md`` (committable, human + agent
readable) and maintains a runtime index at ``data/improvement_queue.json``.

The dev-squad consumes the queue directory as a work inbox; the index lets the
dashboard / PR tracker correlate a recommendation with its downstream PR.

Hard rules
----------
  • NEVER raises on I/O — logs a warning (loguru) and returns "" on failure.
  • Idempotent — overwriting an existing brief is fine (same rec_id).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_QUEUE_DIR = _ROOT / "docs" / "improvement-queue"
_DATA_DIR = _ROOT / "data"
_INDEX_FILE = _DATA_DIR / "improvement_queue.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _premortem(rec: dict) -> dict:
    """Normalize the premortem block.

    Mekka's ``CouncilRecommendation.to_dict()`` nests premortem fields under a
    ``premortem`` key, but accept flat fields too for robustness.
    """
    pm = rec.get("premortem")
    if isinstance(pm, dict):
        verdict = pm.get("verdict")
        hunger = pm.get("hunger")
        mitigations = pm.get("mitigations")
        failure_modes = pm.get("failure_modes")
    else:
        verdict = rec.get("premortem_verdict")
        hunger = rec.get("premortem_hunger")
        mitigations = rec.get("mitigations")
        failure_modes = rec.get("failure_modes")

    return {
        "verdict": str(verdict or "SURVIVES"),
        "hunger": hunger if hunger is not None else 0.0,
        "mitigations": _as_list(mitigations),
        "failure_modes": _as_list(failure_modes),
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _load_index() -> dict[str, dict]:
    if not _INDEX_FILE.exists():
        return {}
    try:
        return json.loads(_INDEX_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _render_brief(rec: dict, rec_id: str, created_at: str) -> str:
    title = str(rec.get("title") or "Melhoria sem título")
    area = str(rec.get("area") or "infra").lower()
    domain = str(rec.get("domain") or "dev-squad")
    priority = str(rec.get("priority") or "P3")
    impact = str(rec.get("impact") or "MEDIUM").upper()
    description = str(rec.get("description") or "").strip()
    evidence = str(rec.get("evidence") or "").strip()
    rationale = str(rec.get("rationale") or "").strip()
    decision = str(rec.get("decision") or "").strip()
    pm = _premortem(rec)

    try:
        hunger_str = f"{float(pm['hunger']):.1f}"
    except (TypeError, ValueError):
        hunger_str = str(pm["hunger"])

    def _bullets(items: list[str]) -> str:
        if not items:
            return "- _(nenhum registrado)_"
        return "\n".join(f"- {it}" for it in items)

    failure_modes = _bullets(pm["failure_modes"])
    mitigations = _bullets(pm["mitigations"])

    # YAML frontmatter — keep values simple/quoted to stay valid.
    frontmatter = (
        "---\n"
        f"rec_id: \"{rec_id}\"\n"
        "status: queued\n"
        f"domain: \"{domain}\"\n"
        f"area: \"{area}\"\n"
        f"priority: \"{priority}\"\n"
        f"created_at: \"{created_at}\"\n"
        "---\n"
    )

    body = f"""# IMP-{rec_id} — {title}

## Title

{title}

## Context / Impact

- **Domain:** {domain}
- **Area:** {area}
- **Priority:** {priority}
- **Impact:** {impact}
- **Council decision:** {decision or "_(n/a)_"}
- **Rationale:** {rationale or "_(n/a)_"}

## Description

{description or "_(sem descrição fornecida)_"}

## Galactus Premortem

- **Verdict:** {pm['verdict']}
- **Hunger:** {hunger_str}

**Failure modes:**

{failure_modes}

**Mitigations:**

{mitigations}

## Evidence

{evidence or "_(sem evidência fornecida)_"}

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id ({rec_id}) para aprovação do operador.
"""
    return frontmatter + "\n" + body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enqueue_brief(rec: dict) -> str:
    """Write a dev brief for an accepted recommendation and index it.

    Returns the brief path (str) on success, or "" on any failure.
    Idempotent: an existing brief for the same rec_id is overwritten.
    """
    if not isinstance(rec, dict):
        logger.warning("[improvement_queue] enqueue_brief: rec is not a dict")
        return ""

    rec_id = str(rec.get("id") or rec.get("rec_id") or "").strip()
    if not rec_id:
        logger.warning("[improvement_queue] enqueue_brief: missing rec id")
        return ""

    created_at = _now()
    brief_path = _QUEUE_DIR / f"IMP-{rec_id}.md"

    try:
        _QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(_render_brief(rec, rec_id, created_at), encoding="utf-8")
    except OSError as exc:
        logger.warning(f"[improvement_queue] could not write brief {rec_id}: {exc}")
        return ""

    # Maintain the runtime index (best-effort; brief is the source of truth).
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        index = _load_index()
        existing = index.get(rec_id) or {}
        index[rec_id] = {
            "path": str(brief_path),
            "queued_at": existing.get("queued_at") or created_at,
            "dev_state": "queued",
        }
        _INDEX_FILE.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, ValueError) as exc:
        logger.warning(f"[improvement_queue] could not update index {rec_id}: {exc}")
        # Brief was written successfully — still return its path.

    logger.info(f"[improvement_queue] queued brief {brief_path}")
    return str(brief_path)

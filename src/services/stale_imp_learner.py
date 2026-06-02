"""
src/services/stale_imp_learner.py
====================================
REV-2 da auditoria 2026-05-29 — Stale IMPs → aprendizado.

Problema: 71 IMPs marcadas como stale com claimer="auto-stale-zero-fila"
são descartadas SEM gerar conhecimento. Sistema repete propor IMPs
similares sem aprender que essas foram desistidas.

Solução: este service analisa as IMPs stale, extrai features
(área, source scanner, padrão do título) e:
1. Agrupa por padrão semântico (cluster)
2. Persiste em data/stale_patterns.json
3. Mekka._chronically_rejected_ids() consulta esse arquivo
4. Mekka suprime auto IMPs que casam com padrões aprendidos

Princípios:
- READ-ONLY no improvement_queue (não muta)
- Output é declarativo (operador pode revisar/editar)
- Fail-silent: erros não afetam Mekka cycle
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

_REPO = Path(__file__).resolve().parents[2]
_QUEUE_FILE = _REPO / "data" / "improvement_queue.json"
_QUEUE_DIR = _REPO / "docs" / "improvement-queue"
_PATTERNS_FILE = _REPO / "data" / "stale_patterns.json"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(data, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        import os
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.warning(f"[stale_imp_learner] save failed: {exc}")
        return False


def _read_brief_metadata(rec_id: str) -> dict[str, Any]:
    """Lê title, area, source do brief markdown."""
    path = _QUEUE_DIR / f"IMP-{rec_id}.md"
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    meta = {"rec_id": rec_id}
    # Title da H1
    m = re.search(r"^#\s+IMP-[a-f0-9]+\s+—\s+(.+)$", text, re.MULTILINE)
    if m:
        meta["title"] = m.group(1).strip()
    # Frontmatter fields
    for field in ("area", "priority", "domain"):
        fm = re.search(rf"^{field}:\s*\"?([^\"\n]+)\"?\s*$", text, re.MULTILINE)
        if fm:
            meta[field] = fm.group(1).strip()
    # Impact (vem como "**Impact:** XXX")
    im = re.search(r"\*\*Impact:\*\*\s+(\w+)", text)
    if im:
        meta["impact"] = im.group(1).strip()
    return meta


def _extract_tokens(title: str) -> set[str]:
    """Tokeniza title pra clustering simples. Remove números e palavras curtas."""
    tokens = re.findall(r"\b[a-zA-Z_/.]{4,}\b", title.lower())
    # Filtra stopwords + filenames específicos
    stop = {
        "with", "from", "this", "that", "para", "pelo", "pela",
        "antes", "depois", "code", "test",
    }
    return {t for t in tokens if t not in stop}


def analyze_stale_imps() -> dict[str, Any]:
    """
    Analisa IMPs marcadas como 'stale' no queue e gera insights:
    - Por área
    - Por padrão (token overlap)
    - Suggested suppression rules pra Mekka

    Returns relatório estruturado.
    """
    queue = _load_json(_QUEUE_FILE, {})
    stale_ids = [
        rec_id for rec_id, entry in queue.items()
        if entry.get("dev_state") == "stale"
    ]
    logger.info(f"[stale_imp_learner] analyzing {len(stale_ids)} stale IMPs")

    if not stale_ids:
        return {"total_stale": 0, "patterns": [], "insights": []}

    # Carregar metadata de cada stale
    metas: list[dict[str, Any]] = []
    for rec_id in stale_ids:
        m = _read_brief_metadata(rec_id)
        if m.get("title"):
            metas.append(m)

    # Aggregations
    by_area = Counter(m.get("area", "?") for m in metas)
    by_impact = Counter(m.get("impact", "?") for m in metas)
    by_domain = Counter(m.get("domain", "?") for m in metas)

    # Token clustering — agrupa titles com >=2 tokens em comum
    clusters: dict[frozenset, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for m in metas:
        tokens = _extract_tokens(m.get("title", ""))
        if not tokens:
            continue
        # Find cluster por overlap >=2
        best_key = None
        best_overlap = 0
        for k in clusters:
            overlap = len(tokens & k)
            if overlap >= 2 and overlap > best_overlap:
                best_key = k
                best_overlap = overlap
        if best_key:
            clusters[best_key].append(m)
            # Merge tokens
            new_key = best_key | tokens
            if new_key != best_key:
                clusters[new_key] = clusters.pop(best_key)
        else:
            clusters[frozenset(tokens)] = [m]
        seen.add(m["rec_id"])

    # Patterns = clusters with >=3 IMPs (significant)
    patterns = []
    for tokens_key, group in clusters.items():
        if len(group) >= 3:
            patterns.append({
                "tokens": sorted(tokens_key),
                "imp_count": len(group),
                "sample_titles": [g.get("title", "") for g in group[:3]],
                "areas": list(Counter(g.get("area", "?") for g in group).keys()),
                "suggestion": (
                    "Beast/Galactus should de-prioritize this pattern; "
                    "operator already passed on " + str(len(group)) + " similar"
                ),
            })

    patterns.sort(key=lambda p: -p["imp_count"])

    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total_stale": len(stale_ids),
        "by_area": dict(by_area),
        "by_impact": dict(by_impact),
        "by_domain": dict(by_domain),
        "patterns": patterns[:10],
        "insights": [
            f"Top area: {by_area.most_common(1)[0][0]} ({by_area.most_common(1)[0][1]} IMPs)"
            if by_area else "no area data",
            f"Top impact: {by_impact.most_common(1)[0][0]}" if by_impact else "no impact data",
            f"Patterns identified: {len(patterns)}",
        ],
    }

    # Persist for Mekka to consult
    _save_json(_PATTERNS_FILE, report)
    logger.info(f"[stale_imp_learner] persisted {len(patterns)} patterns to {_PATTERNS_FILE.name}")

    return report


def load_patterns() -> dict[str, Any]:
    """Used by Mekka._chronically_rejected_ids to consult learned patterns."""
    return _load_json(_PATTERNS_FILE, {"patterns": [], "total_stale": 0})


def is_proposal_blocked_by_stale_pattern(
    title: str, threshold: int = 5,
) -> tuple[bool, str]:
    """
    Verifica se uma proposal title casa com padrão stale aprendido com
    pelo menos `threshold` IMPs descartadas.

    Returns (blocked, reason).
    """
    patterns = load_patterns().get("patterns", [])
    if not patterns:
        return False, "no learned patterns"
    proposal_tokens = _extract_tokens(title)
    if not proposal_tokens:
        return False, "title has no significant tokens"
    for pat in patterns:
        if pat.get("imp_count", 0) < threshold:
            continue
        pat_tokens = set(pat.get("tokens", []))
        overlap = len(proposal_tokens & pat_tokens)
        if overlap >= 2:
            return True, (
                f"matches stale pattern (overlap={overlap}, "
                f"{pat['imp_count']} similar already discarded)"
            )
    return False, "no pattern matched"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Stale IMP learner")
    p.add_argument("--analyze", action="store_true",
                   help="Run analysis + persist patterns")
    p.add_argument("--check", type=str,
                   help="Check if a proposal title is blocked by stale pattern")
    args = p.parse_args()

    if args.check:
        blocked, reason = is_proposal_blocked_by_stale_pattern(args.check)
        print(f"Blocked: {blocked}")
        print(f"Reason: {reason}")
        return 0

    if args.analyze or True:  # default
        report = analyze_stale_imps()
        print(json.dumps(report, indent=2, default=str))
        return 0

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

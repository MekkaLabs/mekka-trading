"""
src/services/improvement_memory_bridge.py
===========================================
Bridge entre o Improvement Loop e as 6 camadas de Memória.

Resolve dois gaps reais identificados:
  1. **Loop não fechado**: melhorias aprovadas não tinham snapshot
     before/after de KPIs — impossível atribuir impacto a cada IMP.
  2. **Reconciliação manual**: 25 IMPs paradas em "queued" porque
     commits do trabalho não usaram tag [IMP-xxxxxx] no subject. O
     ``sync_imp_commits.py`` existe mas só funciona com a tag.

Este service oferece:
  - on_improvement_accepted(rec_id)  → snapshot Sage ANTES
  - on_improvement_pr_merged(rec_id) → snapshot Sage DEPOIS (agendado +7d)
  - find_match_candidates(rec_id)    → escaneia git diff vs IMP brief
  - auto_reconcile_dry_run()         → relatório das 25+ paradas
  - mark_resolved_manual(rec_id, commit_sha) → operador confirma match
  - memory_snapshot()                → agrega métricas das 6 camadas

NÃO é um agente — é um service operacional sem agência decisória.
Quem decide (accept/reject/mark_resolved) é sempre o operador via UI/CLI.

Hard rules:
  - NEVER raises — todas as operações são fail-tolerant.
  - NEVER muta IMP-*.md (read-only sobre os briefs).
  - NEVER faz commit nem push automático.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_QUEUE_DIR = _ROOT / "docs" / "improvement-queue"
_QUEUE_FILE = _DATA_DIR / "improvement_queue.json"
_DECISIONS_FILE = _DATA_DIR / "improvement_decisions.json"
_PRS_FILE = _DATA_DIR / "improvement_prs.json"
_BRIDGE_FILE = _DATA_DIR / "improvement_memory_bridge.json"  # snapshots before/after

_IMP_TAG_RE = re.compile(r"\[IMP-([a-f0-9]{12})\]", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Storage helpers — fail-silent
# ---------------------------------------------------------------------------


def _load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug(f"[bridge] load {path.name}: {exc}")
        return default


def _save_json_atomic(path: Path, data: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError as exc:
        logger.debug(f"[bridge] save {path.name}: {exc}")
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Sage snapshot wrapper — never raises
# ---------------------------------------------------------------------------


async def _sage_snapshot() -> Optional[dict]:
    """Tira snapshot Sage. None se Sage indisponível."""
    try:
        from src.agents.sage import Sage
        sage = Sage()
        snap = await sage._snapshot()
        return snap
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[bridge] sage snapshot failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Bridge state — before/after per rec_id
# ---------------------------------------------------------------------------


def _load_bridge() -> dict:
    return _load_json(_BRIDGE_FILE, {})


def _save_bridge(data: dict) -> bool:
    return _save_json_atomic(_BRIDGE_FILE, data)


# ---------------------------------------------------------------------------
# Public API — lifecycle hooks
# ---------------------------------------------------------------------------


async def on_improvement_accepted(rec_id: str) -> Optional[dict]:
    """
    Chamado quando operador aceita uma IMP. Snapshot Sage = baseline ANTES.
    Idempotente: se já existe before, não sobrescreve.
    """
    bridge = _load_bridge()
    entry = bridge.get(rec_id, {})
    if entry.get("before"):
        return entry  # já snapshot

    snap = await _sage_snapshot()
    entry["before"] = {
        "ts": _now_iso(),
        "kpis": snap or {},
        "trigger": "accepted",
    }
    bridge[rec_id] = entry
    _save_bridge(bridge)
    logger.info(f"[bridge] IMP-{rec_id} BEFORE snapshot captured")
    return entry


async def on_improvement_pr_merged(
    rec_id: str,
    pr_number: Optional[int] = None,
    commit_sha: Optional[str] = None,
) -> Optional[dict]:
    """
    Chamado quando PR vira merged. Marca timestamp, tira snapshot AFTER
    (Sage) e, se o vault writer estiver habilitado, cria nota de review
    em ``30 - Resources/Reviews/IMP-xxxxxx.md`` no vault canônico.

    A separação em fases (mark/snapshot) deixa o operador ver o gap
    temporal real entre merge e medição estável.

    Args:
        rec_id: identificador da IMP.
        pr_number: número do PR, se conhecido (opcional, vai pro vault).
        commit_sha: SHA do commit que mergeou (opcional, vai pro vault).
    """
    bridge = _load_bridge()
    entry = bridge.get(rec_id, {"before": None})
    entry["merged_at"] = _now_iso()
    if pr_number is not None:
        entry["pr_number"] = int(pr_number)
    if commit_sha:
        entry["commit_sha"] = str(commit_sha)
    if not entry.get("after"):
        snap = await _sage_snapshot()
        entry["after"] = {
            "ts": _now_iso(),
            "kpis": snap or {},
            "trigger": "merged",
        }
    bridge[rec_id] = entry
    _save_bridge(bridge)
    logger.info(f"[bridge] IMP-{rec_id} merged + AFTER snapshot captured")

    # Write-back loop — opt-in: cria nota de review no vault canônico
    # usando before/after KPIs do bridge para attribution. Fail-silent.
    try:
        from src.services import improvement_vault_writer
        if improvement_vault_writer.is_writer_enabled():
            # Reconstrói "rec" mínimo a partir do brief no disco.
            rec_dict = _read_brief_as_rec(rec_id)
            before_kpis = (entry.get("before") or {}).get("kpis")
            after_kpis = (entry.get("after") or {}).get("kpis")
            written = improvement_vault_writer.write_merged_review(
                rec=rec_dict,
                before_kpis=before_kpis,
                after_kpis=after_kpis,
                pr_number=pr_number,
                commit_sha=commit_sha,
            )
            if written:
                logger.info(f"[bridge] IMP-{rec_id} → vault review: {written.name}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[bridge] vault writer (merged) no-op: {exc}")

    return entry


# ---------------------------------------------------------------------------
# Brief reader — usado pelo write-back para reconstruir o `rec`
# ---------------------------------------------------------------------------


def _read_brief_as_rec(rec_id: str) -> dict[str, Any]:
    """
    Reconstrói um dict ``rec`` minimal a partir de ``IMP-<rec_id>.md``.
    Extrai title, area, impact, description, rationale do markdown. Fail-silent.
    """
    rec: dict[str, Any] = {"rec_id": rec_id, "id": rec_id}
    path = _QUEUE_DIR / f"IMP-{rec_id}.md"
    if not path.exists():
        return rec
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rec

    # Title da H1 (primeira linha "# IMP-xxxxxx — Título")
    m = re.search(r"^#\s+IMP-[a-f0-9]+\s+—\s+(.+)$", text, re.MULTILINE)
    if m:
        rec["title"] = m.group(1).strip()

    # Frontmatter YAML simples (area, priority, domain)
    for field in ("area", "priority", "domain"):
        fm = re.search(rf"^{field}:\s*\"?([^\"\n]+)\"?\s*$", text, re.MULTILINE)
        if fm:
            rec[field] = fm.group(1).strip()

    # Impact (vem como "**Impact:** XXX")
    im = re.search(r"\*\*Impact:\*\*\s+(\w+)", text)
    if im:
        rec["impact"] = im.group(1).strip()

    # Description (entre "## Description" e próxima "##")
    dm = re.search(r"##\s+Description\s*\n+(.*?)(?=\n##\s+|\Z)", text, re.DOTALL)
    if dm:
        rec["description"] = dm.group(1).strip()

    # Rationale (vem como "**Rationale:** ...")
    rm = re.search(r"\*\*Rationale:\*\*\s+(.+?)(?=\n[-*]\s|\n##|\Z)", text, re.DOTALL)
    if rm:
        rec["rationale"] = rm.group(1).strip()

    return rec


# ---------------------------------------------------------------------------
# Reconciliation — match queued IMPs with recent commits
# ---------------------------------------------------------------------------


def _git_log_recent(days: int = 30) -> list[dict[str, Any]]:
    """Read-only git log: hash, subject, body, files. Fail-silent."""
    try:
        out = subprocess.run(
            ["git", "log", f"--since={days} days ago",
             "--pretty=format:%H%x09%s%x09%b%x1e",
             "--name-only"],
            capture_output=True, text=True, timeout=10, cwd=str(_ROOT),
        )
        if out.returncode != 0:
            return []
    except (subprocess.SubprocessError, OSError) as exc:
        logger.debug(f"[bridge] git log: {exc}")
        return []

    commits = []
    for chunk in out.stdout.split("\x1e"):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.split("\n", 1)
        head = lines[0].split("\t")
        if len(head) < 2:
            continue
        sha = head[0]
        subject = head[1] if len(head) > 1 else ""
        body = head[2] if len(head) > 2 else ""
        files: list[str] = []
        if len(lines) > 1:
            files = [f.strip() for f in lines[1].split("\n") if f.strip()]
        commits.append({
            "sha": sha,
            "short_sha": sha[:7],
            "subject": subject,
            "body": body,
            "files": files,
            "imp_tags": _IMP_TAG_RE.findall(subject + " " + body),
        })
    return commits


def _read_imp_brief(rec_id: str) -> tuple[str, list[str]]:
    """Retorna (corpo, keywords) do IMP-*.md. Vazio se inacessível."""
    path = _QUEUE_DIR / f"IMP-{rec_id}.md"
    if not path.exists():
        return "", []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "", []
    # Heurística simples: pega palavras significativas do title + área
    title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_m.group(1) if title_m else ""
    # Palavras úteis: alfanuméricas com >= 4 chars
    keywords = list(set(re.findall(r"\b[a-zA-Z_/.]{4,}\b", title.lower())))
    return text, keywords


def _score_match(commit: dict, keywords: list[str], brief_text: str) -> float:
    """Score 0..1 de match entre um commit e uma IMP."""
    score = 0.0
    text = (commit.get("subject", "") + " " + commit.get("body", "")).lower()
    files = " ".join(commit.get("files", [])).lower()
    blob = text + " " + files

    if not keywords:
        return 0.0
    matched = sum(1 for kw in keywords if kw in blob)
    coverage = matched / max(len(keywords), 1)
    score += coverage * 0.7

    # Bonus: se IMP brief menciona um arquivo que o commit tocou
    brief_files = re.findall(r"`?(src/[a-zA-Z0-9_/.\-]+\.(?:py|js|jsx|ts|tsx))`?", brief_text)
    if brief_files:
        commit_files_set = set(commit.get("files", []))
        common = sum(1 for f in brief_files if f in commit_files_set)
        if common:
            score += min(common / max(len(brief_files), 1), 1.0) * 0.3

    return min(score, 1.0)


def find_match_candidates(rec_id: str, top_n: int = 5, days: int = 30) -> list[dict]:
    """
    Retorna até top_n commits candidatos a "ter resolvido" essa IMP.
    Score-ranked, sem mutação. Útil para reconciliação manual.
    """
    brief_text, keywords = _read_imp_brief(rec_id)
    if not keywords:
        return []
    commits = _git_log_recent(days=days)
    if not commits:
        return []
    scored = []
    for c in commits:
        # Skip se já tem o tag dessa IMP (já reconciliado)
        if rec_id in c.get("imp_tags", []):
            continue
        s = _score_match(c, keywords, brief_text)
        if s > 0.15:  # threshold mínimo de relevância
            scored.append({
                "sha": c["sha"],
                "short_sha": c["short_sha"],
                "subject": c["subject"][:120],
                "files_count": len(c.get("files", [])),
                "score": round(s, 3),
            })
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_n]


def auto_reconcile_dry_run(days: int = 30) -> dict:
    """
    Lista todas as IMPs em estado 'queued' + sugestões de match com
    commits recentes. NÃO muta nada.
    """
    queue = _load_json(_QUEUE_FILE, {})
    stuck = {
        rec_id: entry for rec_id, entry in queue.items()
        if entry.get("dev_state") in (None, "", "queued", "pending", "accepted")
    }

    report = {
        "ts": _now_iso(),
        "total_queued": len(stuck),
        "days_searched": days,
        "candidates": {},
        "no_match": [],
    }
    for rec_id in stuck:
        matches = find_match_candidates(rec_id, top_n=3, days=days)
        if matches:
            report["candidates"][rec_id] = matches
        else:
            report["no_match"].append(rec_id)
    return report


def mark_resolved_manual(rec_id: str, commit_sha: str, summary: str = "") -> dict:
    """
    Operador confirma manualmente que `commit_sha` resolveu `rec_id`.
    Atualiza pr_tracker.set_pr() com synthetic pr_number (igual ao
    sync_imp_commits.py faz).
    """
    try:
        from src.services import pr_tracker
        # Synthetic PR number: int from first 8 hex chars of SHA
        pr_number = int(commit_sha[:8], 16) % (2**31)
        result = pr_tracker.set_pr(
            rec_id=rec_id,
            pr_number=pr_number,
            branch=f"manual-reconcile-{commit_sha[:7]}",
            summary=summary or f"Manually reconciled to commit {commit_sha[:7]}",
            files_changed=[],
        )
        logger.info(f"[bridge] IMP-{rec_id} → commit {commit_sha[:7]} (manual)")
        return {"ok": True, "rec_id": rec_id, "commit_sha": commit_sha, "pr_number": pr_number, "result": result}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[bridge] mark_resolved_manual failed: {exc}")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Memory aggregation — 6 layers snapshot
# ---------------------------------------------------------------------------


def memory_snapshot() -> dict:
    """
    Agrega métricas das 6 camadas de memória. Fail-tolerant: layer
    indisponível devolve {"available": False, "error": "..."}.

    Não chama Sage (separado em sage_baselines via _sage_snapshot).
    """
    out: dict[str, Any] = {
        "ts": _now_iso(),
        "layers": {},
    }

    # 1) AgentMemory — SQLite direto (sqlite3 stdlib, síncrono).
    # Não usamos SQLAlchemy async aqui porque memory_snapshot() é chamado
    # de handlers HTTP (event loop já rodando) — `run_until_complete` daria
    # "loop is already running". sqlite3 stdlib é síncrono e ~5ms.
    try:
        import sqlite3
        from pathlib import Path as _P
        _db = _P(__file__).resolve().parents[2] / "data" / "mekka_trading.db"
        if not _db.exists():
            out["layers"]["agent_memory"] = {"available": False, "error": "db_missing"}
        else:
            conn = sqlite3.connect(str(_db))
            try:
                cur = conn.execute("SELECT COUNT(*) FROM agent_memories")
                total = cur.fetchone()[0] or 0
                cur = conn.execute(
                    "SELECT COUNT(*) FROM agent_memories WHERE outcome IN ('WIN','LOSS','NEUTRAL','ORPHAN_RECONCILED')"
                )
                resolved = cur.fetchone()[0] or 0
                cur = conn.execute(
                    "SELECT MAX(COALESCE(resolved_at, timestamp)) FROM agent_memories"
                )
                last_ts = cur.fetchone()[0]
                out["layers"]["agent_memory"] = {
                    "available": True,
                    "total_rows": int(total),
                    "resolved_rows": int(resolved),
                    "unresolved_rows": int(total - resolved),
                    "last_write_ts": str(last_ts) if last_ts else None,
                }
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001
        out["layers"]["agent_memory"] = {"available": False, "error": str(exc)[:120]}

    # 2) Decision Memory (Story 249) — singleton
    try:
        from src.services.decision_memory import get_decision_memory
        dm = get_decision_memory()
        st = dm.summary() if hasattr(dm, "summary") else {}
        out["layers"]["decision_memory"] = {"available": True, **st}
    except Exception as exc:  # noqa: BLE001
        out["layers"]["decision_memory"] = {"available": False, "error": str(exc)[:80]}

    # 3) Signal Outcome Memory
    try:
        from src.services.signal_outcome_memory import get_signal_outcome_memory
        som = get_signal_outcome_memory()
        st = som.summary() if hasattr(som, "summary") else {}
        out["layers"]["signal_outcome_memory"] = {"available": True, **st}
    except Exception as exc:  # noqa: BLE001
        out["layers"]["signal_outcome_memory"] = {"available": False, "error": str(exc)[:80]}

    # 4) Role Working Memory
    try:
        from src.services.role_working_memory import get_role_working_memory
        rwm = get_role_working_memory()
        st = rwm.summary() if hasattr(rwm, "summary") else {}
        out["layers"]["role_working_memory"] = {"available": True, **st}
    except Exception as exc:  # noqa: BLE001
        out["layers"]["role_working_memory"] = {"available": False, "error": str(exc)[:80]}

    # 5) Cycle Conversation Memory
    try:
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        ccm = get_cycle_conversation_memory()
        st = ccm.summary() if hasattr(ccm, "summary") else {}
        out["layers"]["cycle_conversation_memory"] = {"available": True, **st}
    except Exception as exc:  # noqa: BLE001
        out["layers"]["cycle_conversation_memory"] = {"available": False, "error": str(exc)[:80]}

    # 6) Vault Context (módulo + presença de vault)
    try:
        from src.services import vault_context  # noqa: F401
        from pathlib import Path
        vp = Path.home() / "Documents" / "mekka-trading-obsidian"
        notes_count = 0
        if vp.exists():
            notes_count = sum(1 for _ in vp.rglob("*.md")
                              if not any(p in _.parts for p in (".obsidian", ".trash")))
        out["layers"]["vault_context"] = {
            "available": True,
            "vault_present": vp.exists(),
            "notes_count": notes_count,
            "vault_path": str(vp),
        }
    except Exception as exc:  # noqa: BLE001
        out["layers"]["vault_context"] = {"available": False, "error": str(exc)[:80]}

    # Saúde geral: quantas camadas estão OK
    out["layers_healthy"] = sum(1 for layer in out["layers"].values() if layer.get("available"))
    out["layers_total"] = len(out["layers"])

    # Bridge metadata
    bridge = _load_bridge()
    out["bridge"] = {
        "improvements_with_before": sum(1 for v in bridge.values() if v.get("before")),
        "improvements_with_after": sum(1 for v in bridge.values() if v.get("after")),
        "improvements_tracked": len(bridge),
    }

    return out

"""
src/services/agent_learning_journal.py
======================================
Diário de Aprendizado por Agente — cada agente escreve e relê suas próprias
lições, de forma incremental e SEM esquecer.

Arquitetura (decisão 2026-06-02, com o operador):
  - **SQLite** (`agent_learnings`) = FONTE DA VERDADE. Durável, deduplicado por
    hash, com contador de "reforço" (relição não duplica — reforça).
  - **Obsidian** = espelho LEGÍVEL, append-only, em
    `20 - Areas/Agentes IA/Aprendizados/{Agente}.md` — a "área separada" de
    cada agente. A máquina NUNCA toca na nota de identidade curada.

Princípios:
  - **Não esquecer:** append-only no vault + SQLite durável. Dedup por hash →
    relição vira reforço (count++), nunca apaga.
  - **Só consultivo:** as lições são injetadas no CONTEXTO do agente para ele
    considerar. NÃO ajustam parâmetros de risco — o único caminho de
    auto-ajuste continua sendo o Mentor (tighten-only). Ver [[mentor_applier]].
  - **Fail-silent:** nenhuma falha de disco/DB quebra um ciclo de trading.
  - **Recall ordenado** por relevância = recência × reforço × confiança, então
    lições antigas mas reforçadas sobrevivem.

Uso:
    from src.services.agent_learning_journal import record, recall

    record("Superman", "RSI < 20 em 1h costuma reverter em alta volatilidade",
           category="indicador", confidence=0.7)
    lessons = recall("Superman", query="RSI", limit=5)

Ou via BaseAgent (async, não bloqueia o loop):
    await self.learn("…", category="…", confidence=0.7)
    lessons = await self.recall_learnings(query="RSI")
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("mekka.agent_learning")

_REPO = Path(__file__).resolve().parents[2]
_DB_PATH = _REPO / "data" / "mekka_trading.db"
_DEFAULT_VAULT = Path.home() / "Documents" / "mekka-trading-obsidian"
_LEARNINGS_SUBDIR = "20 - Areas/Agentes IA/Aprendizados"

# Rate limit de escritas no vault por agente (SQLite não é limitado).
_MAX_VAULT_WRITES_PER_HOUR = int(os.environ.get("AGENT_LEARNING_VAULT_WRITES_PER_HOUR", "30"))

# Tamanho máximo de uma lição (evita prompts/notas gigantes).
_MAX_LESSON_CHARS = 400


# ---------------------------------------------------------------------------
# Config / paths
# ---------------------------------------------------------------------------

def get_vault_path() -> Path:
    """Resolve o vault (env MEKKA_VAULT_PATH tem precedência)."""
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw).expanduser() if raw else _DEFAULT_VAULT


def vault_mirror_enabled() -> bool:
    """Espelho no Obsidian ligado por default (o operador quer os agentes
    escrevendo lá). Desligue com AGENT_LEARNING_VAULT_DISABLED=true."""
    return os.environ.get("AGENT_LEARNING_VAULT_DISABLED", "false").lower() not in (
        "1", "true", "yes", "on"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _hash(agent: str, lesson: str) -> str:
    norm = " ".join(lesson.lower().split())
    return hashlib.sha256(f"{agent}::{norm}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Rate limiter (por agente, em memória)
# ---------------------------------------------------------------------------

_vault_writes: dict[str, deque] = {}


def _allow_vault_write(agent: str) -> bool:
    import time
    now = time.monotonic()
    dq = _vault_writes.setdefault(agent, deque())
    while dq and now - dq[0] > 3600.0:
        dq.popleft()
    if len(dq) >= _MAX_VAULT_WRITES_PER_HOUR:
        return False
    dq.append(now)
    return True


# ---------------------------------------------------------------------------
# SQLite (fonte da verdade)
# ---------------------------------------------------------------------------

def _connect() -> Optional[sqlite3.Connection]:
    try:
        conn = sqlite3.connect(str(_DB_PATH), timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:
        logger.debug("[agent_learning] connect failed: %s", exc)
        return None


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            lesson TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            evidence TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.5,
            tags TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            reinforced_count INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(agent, content_hash)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_learnings_agent "
        "ON agent_learnings(agent)"
    )


# ---------------------------------------------------------------------------
# Public API — escrita
# ---------------------------------------------------------------------------

def record(
    agent: str,
    lesson: str,
    *,
    category: str = "general",
    evidence: str = "",
    confidence: float = 0.5,
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Registra uma lição do agente. Idempotente por (agente, conteúdo):
    relição reforça (count++) em vez de duplicar.

    Returns dict com status: 'new' | 'reinforced' | 'skipped' | 'error'.
    Nunca levanta exceção.
    """
    lesson = (lesson or "").strip()
    if not agent or not lesson:
        return {"status": "skipped", "reason": "empty agent/lesson"}
    if len(lesson) > _MAX_LESSON_CHARS:
        lesson = lesson[:_MAX_LESSON_CHARS].rstrip() + "…"
    confidence = max(0.0, min(1.0, float(confidence)))
    tags_str = ",".join(t.strip() for t in (tags or []) if t.strip())
    chash = _hash(agent, lesson)
    now = _now_iso()

    conn = _connect()
    if conn is None:
        return {"status": "error", "reason": "no db"}

    status = "error"
    reinforced_count = 1
    try:
        with conn:
            _ensure_schema(conn)
            cur = conn.execute(
                "SELECT id, reinforced_count, confidence FROM agent_learnings "
                "WHERE agent=? AND content_hash=?",
                (agent, chash),
            )
            row = cur.fetchone()
            if row is not None:
                # Reforça: count++, confiança = máx, updated_at = agora.
                conn.execute(
                    "UPDATE agent_learnings SET reinforced_count=reinforced_count+1, "
                    "confidence=MAX(confidence, ?), updated_at=? WHERE id=?",
                    (confidence, now, row["id"]),
                )
                status = "reinforced"
                reinforced_count = int(row["reinforced_count"]) + 1
            else:
                conn.execute(
                    "INSERT INTO agent_learnings "
                    "(agent, lesson, category, evidence, confidence, tags, "
                    " content_hash, reinforced_count, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,1,?,?)",
                    (agent, lesson, category, evidence, confidence, tags_str,
                     chash, now, now),
                )
                status = "new"
    except sqlite3.Error as exc:
        logger.debug("[agent_learning] record db error: %s", exc)
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "error", "reason": str(exc)}
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    # Espelho no vault — só em lição NOVA (reforço não duplica linha).
    if status == "new" and vault_mirror_enabled():
        try:
            _append_to_vault(agent, lesson, category, evidence, confidence)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[agent_learning] vault mirror failed: %s", exc)

    return {
        "status": status, "agent": agent, "hash": chash,
        "reinforced_count": reinforced_count,
    }


def _append_to_vault(
    agent: str, lesson: str, category: str, evidence: str, confidence: float,
) -> None:
    """Append append-only na nota de aprendizado do agente. Fail-silent.
    Cria a nota (com frontmatter + link p/ identidade) na primeira lição."""
    if not _allow_vault_write(agent):
        return
    vault = get_vault_path()
    if not vault.exists():
        return
    note_dir = vault / _LEARNINGS_SUBDIR
    note_dir.mkdir(parents=True, exist_ok=True)
    note = note_dir / f"{agent}.md"

    if not note.exists():
        header = (
            f"---\n"
            f"title: Aprendizados — {agent}\n"
            f"type: agente-aprendizado\n"
            f"tags: [agente, aprendizado, {agent.lower().replace(' ', '-')}]\n"
            f"codename: {agent}\n"
            f"created: {_today()}\n"
            f"---\n"
            f"# 🧠 Aprendizados — {agent}\n\n"
            f"> Diário append-only escrito pelo próprio agente. Fonte da verdade: "
            f"tabela `agent_learnings` (SQLite). Identidade curada: "
            f"[[{agent}]].\n\n"
            f"## Lições\n\n"
        )
        note.write_text(header, encoding="utf-8")

    conf_pct = f"{confidence * 100:.0f}%"
    ev = f" — _evidência: {evidence}_" if evidence else ""
    block = f"- `{_today()}` **[{category}]** {lesson} _(confiança {conf_pct})_{ev}\n"
    existing = note.read_text(encoding="utf-8")
    note.write_text(existing + block, encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API — leitura (recall)
# ---------------------------------------------------------------------------

def recall(
    agent: str,
    query: Optional[str] = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retorna as lições mais relevantes do agente, ordenadas por
    reforço × confiança e recência. Filtro opcional por substring (query).
    Nunca levanta exceção."""
    conn = _connect()
    if conn is None:
        return []
    try:
        with conn:
            _ensure_schema(conn)
            sql = (
                "SELECT lesson, category, evidence, confidence, reinforced_count, "
                "       created_at, updated_at "
                "FROM agent_learnings WHERE agent=?"
            )
            params: list[Any] = [agent]
            if query:
                sql += " AND lesson LIKE ?"
                params.append(f"%{query}%")
            # relevância: reforço × confiança, depois recência
            sql += (
                " ORDER BY (reinforced_count * confidence) DESC, updated_at DESC "
                "LIMIT ?"
            )
            params.append(max(1, int(limit)))
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.debug("[agent_learning] recall error: %s", exc)
        return []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def build_context_snippet(agent: str, lessons: list[dict[str, Any]]) -> str:
    """Formata lições para injeção no prompt/contexto do agente. Vazio se nenhuma."""
    if not lessons:
        return ""
    lines = [f"🧠 Aprendizados anteriores de {agent}:"]
    for ls in lessons:
        conf = f"{float(ls.get('confidence', 0)) * 100:.0f}%"
        reinf = int(ls.get("reinforced_count", 1))
        rtag = f" ×{reinf}" if reinf > 1 else ""
        lines.append(f"- [{conf}{rtag}] {ls.get('lesson', '')}")
    return "\n".join(lines)


def stats() -> dict[str, Any]:
    """Resumo para dashboard/diagnóstico: total de lições por agente."""
    conn = _connect()
    if conn is None:
        return {"available": False, "by_agent": {}}
    try:
        with conn:
            _ensure_schema(conn)
            rows = conn.execute(
                "SELECT agent, COUNT(*) AS n, SUM(reinforced_count) AS reinforced "
                "FROM agent_learnings GROUP BY agent ORDER BY n DESC"
            ).fetchall()
            return {
                "available": True,
                "vault_mirror": vault_mirror_enabled(),
                "by_agent": {
                    r["agent"]: {"lessons": r["n"], "reinforced": r["reinforced"]}
                    for r in rows
                },
            }
    except sqlite3.Error:
        return {"available": False, "by_agent": {}}
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

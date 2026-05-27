"""
src/services/improvement_vault_writer.py
==========================================
Write-back loop do Time de Melhorias → segundo cérebro.

Garante que tudo que o time de melhorias produz vire **conhecimento
persistido** no vault canônico (`~/Documents/mekka-trading-obsidian/`)
seguindo a política `30 - Resources/Fontes de Verdade.md`.

3 funções públicas, todas fail-silent, opt-in via flag, throttled:

  - ``append_accepted_daily(rec)`` → 1 nota por dia em `60 - Daily/`
    listando tudo que foi aceito naquele dia (batch agregado).

  - ``write_merged_review(rec, before_kpis, after_kpis)`` → cria uma
    nota de review em `30 - Resources/Reviews/IMP-xxxxxx.md` quando
    uma IMP é mergeada, usando o `Template - Aprendizado.md`.

  - ``write_handoff_summary(handoff_path)`` → quando uma sessão grande
    gera HANDOFF-*.md em `docs/`, extrai TL;DR + decisões e cria
    resumo em `60 - Daily/YYYY-MM-DD.md` (append-safe).

Hard rules
----------
- Opt-in via ``IMPROVEMENT_VAULT_WRITER_ENABLED=true`` (default OFF).
- Vault canônico (não `docs/obsidian/`). Respeita `MEKKA_VAULT_PATH`.
- Throttled: 20 escritas/hora máximo, append-safe atomic.
- Fail-silent: nunca propaga exceção pro caller.
- Boundary: escreve só em `60 - Daily/` e `30 - Resources/Reviews/`.
- Sem secrets no payload — payload é sanitizado.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_DEFAULT_VAULT_PATH = Path.home() / "Documents" / "mekka-trading-obsidian"
_DAILY_SUBDIR = "60 - Daily"
_REVIEWS_SUBDIR = "30 - Resources/Reviews"
_DAILY_BATCH_SUFFIX = "-improvements-accepted.md"

MAX_WRITES_PER_HOUR = int(os.environ.get("IMPROVEMENT_VAULT_WRITES_PER_HOUR", "20"))


def is_writer_enabled() -> bool:
    """Flag explícita — default OFF."""
    return os.environ.get("IMPROVEMENT_VAULT_WRITER_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def get_vault_path() -> Path:
    """
    Vault path canônico. Honra ``MEKKA_VAULT_PATH`` se definido.
    Não cria o vault — apenas reporta o caminho esperado.
    """
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw).expanduser() if raw else _DEFAULT_VAULT_PATH


# ---------------------------------------------------------------------------
# Throttler local
# ---------------------------------------------------------------------------


class _HourlyThrottle:
    def __init__(self, max_events: int, window_s: float = 3600.0) -> None:
        self.max = max_events
        self.window = window_s
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._events and now - self._events[0] > self.window:
            self._events.popleft()
        if len(self._events) >= self.max:
            return False
        self._events.append(now)
        return True


_throttle = _HourlyThrottle(MAX_WRITES_PER_HOUR)


# ---------------------------------------------------------------------------
# Helpers — comuns
# ---------------------------------------------------------------------------


def _today_str() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Chaves do brief/rec que podem virar prosa no vault — sem secrets.
_SAFE_REC_KEYS = {
    "id", "rec_id", "title", "area", "impact", "priority",
    "domain", "description", "evidence", "rationale", "decision",
    "source", "success_kpi",
}


def _safe_rec(rec: dict[str, Any]) -> dict[str, Any]:
    """Sanitiza um rec do council: só chaves whitelist."""
    out = {}
    for k in _SAFE_REC_KEYS:
        v = rec.get(k)
        if v is None:
            continue
        # Trunca strings longas pra não inflar a nota.
        if isinstance(v, str) and len(v) > 600:
            v = v[:600].rstrip() + "…"
        out[k] = v
    return out


def _atomic_append(target: Path, block: str) -> Optional[Path]:
    """
    Append append-safe com atomic replace.

    Returns: Path em caso de sucesso, None em falha (fail-silent).
    """
    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(existing + block, encoding="utf-8")
        os.replace(tmp, target)
        return target
    except OSError as exc:
        logger.debug(f"[improvement_vault_writer] atomic_append failed: {exc}")
        try:
            tmp = target.with_suffix(target.suffix + ".tmp")
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return None


# ---------------------------------------------------------------------------
# Boundary check — defense-in-depth contra escritas fora dos paths permitidos
# ---------------------------------------------------------------------------


_ALLOWED_PREFIXES = (_DAILY_SUBDIR, _REVIEWS_SUBDIR)


def _is_within_allowed(target: Path, vault: Path) -> bool:
    try:
        rel = target.relative_to(vault)
    except ValueError:
        return False
    rel_str = str(rel).replace("\\", "/")
    return any(rel_str.startswith(p + "/") or rel_str == p for p in _ALLOWED_PREFIXES)


# ---------------------------------------------------------------------------
# F1 — append_accepted_daily
# ---------------------------------------------------------------------------


def _daily_batch_path(vault: Path) -> Path:
    return vault / _DAILY_SUBDIR / f"{_today_str()}{_DAILY_BATCH_SUFFIX}"


def _ensure_daily_batch_header(target: Path) -> bool:
    """Cria header da daily-batch se ainda não existir."""
    if target.exists():
        return True
    header = f"""---
title: "Melhorias Aceitas — {_today_str()}"
type: daily-improvements
tags: [improvements, daily, second-brain, mekka-trading]
date: {_today_str()}
auto_generated: true
---

# Melhorias Aceitas — {_today_str()}

> Arquivo gerado automaticamente pelo `improvement_vault_writer` quando o
> operador aceita uma melhoria via dashboard. Cada bloco abaixo é uma IMP
> que entrou na fila do dev-squad neste dia.
>
> **Política:** este arquivo é vault-only e não volta para `docs/obsidian/`
> (ver [[Fontes de Verdade]] §60-Daily).

"""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(header, encoding="utf-8")
        return True
    except OSError as exc:
        logger.debug(f"[improvement_vault_writer] header create failed: {exc}")
        return False


def _format_accepted_block(rec: dict[str, Any]) -> str:
    """Bloco markdown compacto para uma IMP aceita."""
    safe = _safe_rec(rec)
    rec_id = str(safe.get("rec_id") or safe.get("id") or "?")
    title = str(safe.get("title") or "(sem título)")
    area = str(safe.get("area") or "?")
    impact = str(safe.get("impact") or "?")
    priority = str(safe.get("priority") or "?")
    source = str(safe.get("source") or "?")
    description = str(safe.get("description") or "").strip()

    description_block = (
        f"> {description}\n" if description else "> _(sem descrição)_\n"
    )

    return f"""
## IMP-{rec_id} — {title}

- **Área:** `{area}` · **Impacto:** `{impact}` · **Prioridade:** `{priority}`
- **Origem:** `{source}` · **Aceito em:** {_now_iso()}
- **Brief:** [[IMP-{rec_id}|brief no repo]]

{description_block}
"""


def append_accepted_daily(rec: dict[str, Any]) -> Optional[Path]:
    """
    Append um bloco compacto da IMP aceita no arquivo diário de melhorias.

    Cria o arquivo se for a primeira aceitação do dia. Fail-silent + throttled.
    """
    if not is_writer_enabled():
        return None
    if not _throttle.allow():
        logger.debug("[improvement_vault_writer] throttled (accepted_daily)")
        return None

    vault = get_vault_path()
    if not vault.exists() or not vault.is_dir():
        logger.debug(f"[improvement_vault_writer] vault ausente: {vault}")
        return None

    target = _daily_batch_path(vault)
    if not _is_within_allowed(target, vault):
        logger.warning(
            f"[improvement_vault_writer] target outside allowed dirs: {target}"
        )
        return None
    if not _ensure_daily_batch_header(target):
        return None

    block = _format_accepted_block(rec)
    return _atomic_append(target, block)


# ---------------------------------------------------------------------------
# F2 — write_merged_review (usa Template - Aprendizado)
# ---------------------------------------------------------------------------


def _safe_filename_fragment(s: str, maxlen: int = 60) -> str:
    """Slug minimalista pra não criar paths inválidos no macOS/Linux."""
    s = re.sub(r"[^\w\s\-]", "", s or "", flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "-", s).lower()
    return s[:maxlen] or "imp"


def _format_kpis(kpis: Optional[dict[str, Any]]) -> str:
    if not kpis:
        return "_(sem snapshot — Sage indisponível no momento)_"
    return "```json\n" + json.dumps(kpis, indent=2, default=str) + "\n```"


def _format_merged_review(
    rec: dict[str, Any],
    before_kpis: Optional[dict[str, Any]],
    after_kpis: Optional[dict[str, Any]],
    pr_number: Optional[int] = None,
    commit_sha: Optional[str] = None,
) -> str:
    """Renderiza o markdown da nota de review usando estrutura inspirada em
    Template - Aprendizado.md mas adaptada ao ciclo de IMPs."""
    safe = _safe_rec(rec)
    rec_id = str(safe.get("rec_id") or safe.get("id") or "?")
    title = str(safe.get("title") or "(sem título)")
    area = str(safe.get("area") or "?")
    impact = str(safe.get("impact") or "?")
    description = str(safe.get("description") or "_(sem descrição)_").strip()
    rationale = str(safe.get("rationale") or "_(sem rationale)_").strip()
    success_kpi = str(safe.get("success_kpi") or "_(sem KPI definido no brief)_")

    pr_line = f"PR `#{pr_number}`" if pr_number else "_(sem PR registrado)_"
    commit_line = f"commit `{commit_sha[:8]}`" if commit_sha else "_(sem commit linkado)_"

    return f"""---
title: "Review IMP-{rec_id} — {title}"
type: review-improvement
tags: [improvement, review, second-brain, mekka-trading, {area}]
rec_id: {rec_id}
area: {area}
impact: {impact}
date: {_today_str()}
auto_generated: true
---

# Review IMP-{rec_id} — {title}

> Nota gerada automaticamente quando esta melhoria foi mergeada. Estrutura
> inspirada em [[Template - Aprendizado]] mas com snapshots Sage antes/depois
> para attribution de impacto.

## O que mudou

{description}

**Vínculos:** [[IMP-{rec_id}|brief original]] · {pr_line} · {commit_line}

## Por que importa

{rationale}

## Success KPI declarado no brief

`{success_kpi}`

## Métricas — Antes

{_format_kpis(before_kpis)}

## Métricas — Depois

{_format_kpis(after_kpis)}

## Como aplicar / lições

> _(operador preenche manualmente quando revisita esta nota — o que
> ficou claro depois do merge? Mudaria algo?)_

## Contexto

- **Área impactada:** `{area}`
- **Impacto declarado:** `{impact}`
- **Mergeado em:** {_now_iso()}
- **Notas relacionadas:** [[Departamento de Melhoria Contínua]], [[Beast]]
"""


def write_merged_review(
    rec: dict[str, Any],
    before_kpis: Optional[dict[str, Any]] = None,
    after_kpis: Optional[dict[str, Any]] = None,
    pr_number: Optional[int] = None,
    commit_sha: Optional[str] = None,
) -> Optional[Path]:
    """
    Cria nota de review em `30 - Resources/Reviews/IMP-xxxxxx-titulo.md`.

    Idempotente: se a nota já existe (mesmo rec_id), não sobrescreve —
    deixa o operador editar livremente depois.
    """
    if not is_writer_enabled():
        return None
    if not _throttle.allow():
        logger.debug("[improvement_vault_writer] throttled (merged_review)")
        return None

    vault = get_vault_path()
    if not vault.exists() or not vault.is_dir():
        return None

    rec_id = str(rec.get("rec_id") or rec.get("id") or "").strip()
    if not rec_id:
        logger.debug("[improvement_vault_writer] merged_review: missing rec_id")
        return None

    title_frag = _safe_filename_fragment(str(rec.get("title") or "untitled"))
    fname = f"IMP-{rec_id}-{title_frag}.md"
    target = vault / _REVIEWS_SUBDIR / fname

    if not _is_within_allowed(target, vault):
        logger.warning(
            f"[improvement_vault_writer] review target outside allowed: {target}"
        )
        return None

    if target.exists():
        logger.debug(f"[improvement_vault_writer] review já existe: {target.name}")
        return target

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        body = _format_merged_review(
            rec, before_kpis, after_kpis,
            pr_number=pr_number, commit_sha=commit_sha,
        )
        target.write_text(body, encoding="utf-8")
        return target
    except OSError as exc:
        logger.debug(f"[improvement_vault_writer] review write failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# F3 — write_handoff_summary
# ---------------------------------------------------------------------------


_HANDOFF_TLDR_RE = re.compile(r"^##\s+(?:⚡\s+)?TL;DR\s*\n+(.*?)(?=\n##\s+|\Z)",
                              re.MULTILINE | re.DOTALL)


def _extract_handoff_tldr(text: str) -> str:
    """Extrai a seção TL;DR de um HANDOFF-*.md. Fail-silent → ''."""
    try:
        m = _HANDOFF_TLDR_RE.search(text)
        if not m:
            return ""
        tldr = m.group(1).strip()
        # Trunca pra 2000 chars (suficiente pra resumo no daily).
        if len(tldr) > 2000:
            tldr = tldr[:2000].rstrip() + "…"
        return tldr
    except Exception:  # noqa: BLE001
        return ""


def write_handoff_summary(handoff_path: str | Path) -> Optional[Path]:
    """
    Lê um HANDOFF-*.md, extrai o TL;DR e adiciona um resumo no daily do
    vault canônico (`60 - Daily/YYYY-MM-DD.md`). Append-safe — múltiplos
    handoffs no mesmo dia coexistem em blocos separados.
    """
    if not is_writer_enabled():
        return None
    if not _throttle.allow():
        logger.debug("[improvement_vault_writer] throttled (handoff_summary)")
        return None

    src = Path(handoff_path)
    if not src.exists() or not src.is_file():
        logger.debug(f"[improvement_vault_writer] handoff path inválido: {src}")
        return None

    try:
        text = src.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        logger.debug(f"[improvement_vault_writer] handoff read failed: {exc}")
        return None

    tldr = _extract_handoff_tldr(text)
    if not tldr:
        logger.debug(f"[improvement_vault_writer] handoff sem TL;DR: {src.name}")
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None

    daily_path = vault / _DAILY_SUBDIR / f"{_today_str()}.md"
    if not _is_within_allowed(daily_path, vault):
        return None

    if not daily_path.exists():
        # Cria header básico do daily se não existir.
        header = f"""---
title: "{_today_str()}"
type: daily
tags: [daily, mekka-trading]
date: {_today_str()}
auto_generated: true
---

# {_today_str()}

"""
        try:
            daily_path.parent.mkdir(parents=True, exist_ok=True)
            daily_path.write_text(header, encoding="utf-8")
        except OSError as exc:
            logger.debug(f"[improvement_vault_writer] daily header failed: {exc}")
            return None

    block = f"""
## 🤝 HANDOFF — {src.name}

{tldr}

**Arquivo completo:** `{src}`

---
"""
    return _atomic_append(daily_path, block)


# ---------------------------------------------------------------------------
# Stats — para o dashboard / debugging
# ---------------------------------------------------------------------------


def stats() -> dict[str, Any]:
    """Snapshot leve para o dashboard."""
    vault = get_vault_path()
    return {
        "enabled": is_writer_enabled(),
        "vault_path": str(vault),
        "vault_available": vault.exists(),
        "writes_in_window": len(_throttle._events),
        "max_per_hour": MAX_WRITES_PER_HOUR,
        "allowed_subdirs": list(_ALLOWED_PREFIXES),
    }

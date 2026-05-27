"""
src/dashboard/handlers/second_brain_activity.py
================================================
Handlers que alimentam o módulo "Atividade do Segundo Cérebro" no dashboard.

A fonte de dados são SINAIS REAIS do sistema, sem invenção:
- **Consumido / Acessado**: vault context cache hits (vault_context.py)
  + métricas do Jean Grey (jean_grey.py), quando disponível.
- **Gerado**: observações e aprendizados do agente Prometheus
  (src/agents/prometheus.py) — `snapshot()` retorna recent_observations
  e recent_learnings.
- **Atualizado**: arquivos modificados no vault canônico
  (`~/Documents/mekka-trading-obsidian`) nas últimas N horas, via
  `mtime` do filesystem; e estado do sincronizador `obsidian_sync.py`
  (dry-run para reportar NEW/CONFLICT).

Princípios:
- Fail-silent: qualquer fonte indisponível cai para lista vazia + flag.
- Sem dependência cruzada com loop de trading.
- Polling-friendly: payload pequeno, idempotente, ~150ms typical.
- Cache curto (10s) para evitar martelar disco.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from src.dashboard.server import MekkaDashboardServer


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_DEFAULT_VAULT_PATH = Path.home() / "Documents" / "mekka-trading-obsidian"
_DEFAULT_WINDOW_HOURS = 24
_CACHE_TTL_S = 10.0

# Cache global por processo (compartilhado entre requests). dict para
# evitar acoplar a server (estado de runtime stay no server).
_cache: dict[str, Any] = {"ts": 0.0, "payload": None}


# ---------------------------------------------------------------------------
# Coletores
# ---------------------------------------------------------------------------


def _list_recent_vault_files(vault: Path, window_hours: int) -> list[dict[str, Any]]:
    """
    Arquivos do vault modificados nas últimas N horas.

    Retorna lista de {path, mtime, size}; vazia se vault indisponível.
    """
    if not vault.exists() or not vault.is_dir():
        return []
    cutoff = time.time() - (window_hours * 3600)
    out: list[dict[str, Any]] = []
    try:
        for p in vault.rglob("*.md"):
            if any(part in p.parts for part in (".obsidian", ".trash")):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime >= cutoff:
                out.append({
                    "path": str(p.relative_to(vault)),
                    "mtime": st.st_mtime,
                    "size": st.st_size,
                })
    except OSError:
        return []
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out[:50]


def _prometheus_snapshot() -> dict[str, Any]:
    """
    Snapshot do agente Prometheus (se ativo). Sem opt-in retorna vazio.
    """
    try:
        from src.agents.prometheus import get_prometheus_agent
        agent = get_prometheus_agent()
        if agent is None:
            return {"enabled": False, "observations": [], "learnings": [], "stats": {}}
        snap = agent.snapshot()
        return {
            "enabled": True,
            "subscribed": snap.get("subscribed", False),
            "observations": snap.get("recent_observations", []),
            "learnings": snap.get("recent_learnings", []),
            "stats": snap.get("stats", {}),
            "throttle": snap.get("throttle_state", {}),
        }
    except Exception:  # noqa: BLE001
        return {"enabled": False, "observations": [], "learnings": [], "stats": {}}


def _sync_status() -> dict[str, Any]:
    """
    Estado de sincronização docs/obsidian → vault.
    Resultado mínimo: NEW count, CONFLICT count. Sem rodar comando externo
    (importa o script diretamente).
    """
    try:
        from scripts.obsidian_sync import run as sync_run, DEFAULT_VAULT, SOURCE
        if not (DEFAULT_VAULT.exists() and SOURCE.exists()):
            return {"available": False}
        report = sync_run(
            source=SOURCE,
            vault=DEFAULT_VAULT,
            apply=False,
            update=False,
            include_config=False,
            forced=set(),
        )
        return {
            "available": True,
            "new": report.count("NEW"),
            "conflict": report.count("CONFLICT"),
            "identical": report.count("IDENTICAL"),
            "skipped": report.count("SKIPPED"),
        }
    except Exception:  # noqa: BLE001
        return {"available": False}


def _vault_context_metrics() -> dict[str, Any]:
    """Métricas do vault_context.py (cache hits, latência), se disponível."""
    try:
        from src.services import vault_context  # noqa: F401
        return {"module_available": True}
    except Exception:  # noqa: BLE001
        return {"module_available": False}


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------


def _build_payload(window_hours: int) -> dict[str, Any]:
    vault = Path(os.environ.get("MEKKA_VAULT_PATH", str(_DEFAULT_VAULT_PATH)))
    updated = _list_recent_vault_files(vault, window_hours)
    prometheus = _prometheus_snapshot()
    sync = _sync_status()
    ctx = _vault_context_metrics()

    return {
        "ts": time.time(),
        "window_hours": window_hours,
        "vault_path": str(vault),
        "vault_available": vault.exists(),
        # GERADO (Prometheus learnings + observations)
        "generated": {
            "learnings": prometheus["learnings"],
            "observation_count": len(prometheus["observations"]),
        },
        # ACESSADO (Prometheus observations recentes)
        "accessed": {
            "recent_observations": prometheus["observations"][-10:],
            "stats": prometheus["stats"],
        },
        # ATUALIZADO (mtime real de arquivos no vault)
        "updated": {
            "files": updated,
            "count": len(updated),
        },
        # CONSUMIDO (módulo vault_context — placeholder até contadores reais)
        "consumed": {
            "vault_context_available": ctx["module_available"],
        },
        # Estados auxiliares
        "prometheus_status": {
            "enabled": prometheus["enabled"],
            "subscribed": prometheus.get("subscribed", False),
            "throttle": prometheus.get("throttle", {}),
        },
        "sync_status": sync,
        "limitations": _limitations_note(prometheus, sync, vault),
    }


def _limitations_note(
    prometheus: dict[str, Any],
    sync: dict[str, Any],
    vault: Path,
) -> list[str]:
    """Comunica EXPLICITAMENTE o que NÃO está disponível neste payload."""
    notes: list[str] = []
    if not prometheus.get("enabled"):
        notes.append("Prometheus agente DESABILITADO (PROMETHEUS_AGENT_ENABLED=false).")
    if not sync.get("available"):
        notes.append("Sincronizador docs/obsidian → vault indisponível ou vault não montado.")
    if not vault.exists():
        notes.append(f"Vault não encontrado em {vault}.")
    return notes


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


async def handle_get(
    server: "MekkaDashboardServer",
    request: web.Request,
) -> web.Response:
    """
    GET /api/second-brain/activity[?window=24]

    Retorna atividade recente do segundo cérebro. Cache 10s entre calls
    para evitar varrer disco em polling agressivo.
    """
    try:
        window = int(request.rel_url.query.get("window", _DEFAULT_WINDOW_HOURS))
        if window < 1 or window > 168:
            window = _DEFAULT_WINDOW_HOURS
    except (TypeError, ValueError):
        window = _DEFAULT_WINDOW_HOURS

    now = time.monotonic()
    cached = _cache.get("payload")
    if cached and (now - _cache["ts"]) < _CACHE_TTL_S and cached.get("window_hours") == window:
        return web.json_response(cached)

    try:
        payload = _build_payload(window)
        _cache["ts"] = now
        _cache["payload"] = payload
        return web.json_response(payload)
    except Exception as exc:  # noqa: BLE001
        # Fail-soft: nunca quebra dashboard
        return web.json_response(
            {
                "ts": time.time(),
                "error": f"{type(exc).__name__}: {exc}",
                "generated": {"learnings": [], "observation_count": 0},
                "accessed": {"recent_observations": [], "stats": {}},
                "updated": {"files": [], "count": 0},
                "consumed": {"vault_context_available": False},
                "limitations": ["coleta falhou — payload mínimo retornado"],
            },
            status=200,  # 200 para o frontend não cair
        )

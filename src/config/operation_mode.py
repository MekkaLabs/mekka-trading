"""
src/config/operation_mode.py
============================
Modo de Operação — switch RAIZ que governa quem aprova as ações do sistema.

Dois modos, um único switch:

  manual     — o OPERADOR aprova cada trade E cada melhoria via Telegram.
               Gate humano LIGADO em todas as superfícies. (default — seguro)
  automatic  — o SISTEMA aprova sozinho, da melhor forma possível.
               Gate humano DESLIGADO. Trades auto-executam e melhorias
               auto-aplicam.

IMPORTANTE — invariantes de segurança preservadas em AMBOS os modos:
  - O double-gate (paper_trading/live_trading_confirmed) continua valendo.
  - Os gates do Batman (drawdown, exposição, kill-switch, daily-loss) continuam.
  - O clamp tighten-only do auto-apply continua: 'automatic' NUNCA afrouxa
    risco automaticamente — só aperta. Afrouxar exige operador manual.

  O modo 'automatic' remove apenas a camada de aprovação HUMANA — nunca os
  guard-rails determinísticos.

Fonte da verdade
----------------
  1. Default vem de ``settings.operation_mode`` (lido do .env, default 'manual').
  2. Override em runtime persistido em ``data/operation_mode.json`` — permite
     trocar o modo via Telegram/dashboard sem reiniciar o sistema. A troca
     entra em vigor no próximo ciclo.

Uso
---
    from src.config.operation_mode import (
        get_operation_mode, set_operation_mode,
        is_manual, is_automatic,
        requires_trade_approval, improvements_auto_apply,
    )

    if requires_trade_approval():        # manual → True
        await ask_operator(...)
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

_log = logging.getLogger("mekka.operation_mode")

OperationMode = Literal["manual", "automatic"]

VALID_OPERATION_MODES: tuple[str, ...] = ("manual", "automatic")
DEFAULT_OPERATION_MODE: OperationMode = "manual"  # seguro: operador no comando

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_MODE_FILE = _DATA_DIR / "operation_mode.json"

# ---------------------------------------------------------------------------
# In-memory singleton (thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_current_mode: OperationMode | None = None
_loaded: bool = False


def _default_from_settings() -> OperationMode:
    """Lê o default do .env via settings. Lazy/fail-safe para evitar ciclos
    de import e nunca quebrar em ambiente sem settings carregadas."""
    try:
        from src.config.settings import settings  # noqa: WPS433
        raw = str(getattr(settings, "operation_mode", DEFAULT_OPERATION_MODE)).lower()
        if raw in VALID_OPERATION_MODES:
            return raw  # type: ignore[return-value]
        _log.warning(
            "[OperationMode] valor inválido em settings.operation_mode=%r — usando %s",
            raw, DEFAULT_OPERATION_MODE,
        )
    except Exception as exc:  # noqa: BLE001
        _log.debug("[OperationMode] settings indisponível (%s) — usando default", exc)
    return DEFAULT_OPERATION_MODE


def _load_from_disk() -> None:
    """Lê o override de runtime do disco (uma vez, no primeiro acesso).
    Se o arquivo não existe ou é inválido, cai para o default das settings."""
    global _current_mode, _loaded
    mode: OperationMode = _default_from_settings()
    if _MODE_FILE.exists():
        try:
            data = json.loads(_MODE_FILE.read_text(encoding="utf-8"))
            disk_mode = str(data.get("mode", mode)).lower()
            if disk_mode in VALID_OPERATION_MODES:
                mode = disk_mode  # type: ignore[assignment]
            else:
                _log.warning(
                    "[OperationMode] modo desconhecido '%s' no arquivo — usando %s",
                    disk_mode, mode,
                )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "[OperationMode] não consegui ler %s: %s — usando %s",
                _MODE_FILE, exc, mode,
            )
    _current_mode = mode
    _loaded = True


def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        with _lock:
            if not _loaded:
                _load_from_disk()


# ---------------------------------------------------------------------------
# Public API — leitura
# ---------------------------------------------------------------------------

def get_operation_mode() -> OperationMode:
    """Retorna o modo de operação ativo ('manual' ou 'automatic')."""
    _ensure_loaded()
    assert _current_mode is not None  # _ensure_loaded garante
    return _current_mode


def is_manual() -> bool:
    """True quando o operador deve aprovar trades e melhorias."""
    return get_operation_mode() == "manual"


def is_automatic() -> bool:
    """True quando o sistema aprova sozinho (gate humano desligado)."""
    return get_operation_mode() == "automatic"


# ---------------------------------------------------------------------------
# Public API — decisões derivadas (consumidas pelos gates)
# ---------------------------------------------------------------------------

def requires_trade_approval() -> bool:
    """Se um trade aprovado pelo Batman precisa de confirmação humana
    (Telegram) antes do IronMan executar.

    manual → True (operador confirma) · automatic → False (auto-executa).
    """
    return is_manual()


def improvements_auto_apply() -> bool:
    """Se melhorias (Mentor overrides + Implementer worker) podem ser
    aplicadas automaticamente, sem aprovação do operador.

    manual → False (operador aprova) · automatic → True (auto-aplica).

    NB: o clamp tighten-only do mentor_applier continua valendo mesmo aqui —
    'automatic' nunca AFROUXA risco automaticamente.
    """
    return is_automatic()


def snapshot() -> dict[str, Any]:
    """Snapshot atômico do modo + decisões derivadas. Use em loops de
    orquestração para consistência mid-cycle."""
    _ensure_loaded()
    with _lock:
        mode = _current_mode
    return {
        "mode": mode,
        "requires_trade_approval": mode == "manual",
        "improvements_auto_apply": mode == "automatic",
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Public API — escrita
# ---------------------------------------------------------------------------

def set_operation_mode(mode: str) -> OperationMode:
    """Troca o modo de operação e persiste em disco. A troca entra em vigor
    no próximo ciclo, sem reiniciar.

    Raises:
        ValueError: para modos desconhecidos.
    """
    global _current_mode
    norm = str(mode).strip().lower()
    if norm not in VALID_OPERATION_MODES:
        raise ValueError(
            f"Modo de operação desconhecido '{mode}'. Válidos: {list(VALID_OPERATION_MODES)}"
        )

    with _lock:
        _current_mode = norm  # type: ignore[assignment]
        _loaded = True
        _persist()

    _log.info("[OperationMode] modo alterado → %s", norm)
    return norm  # type: ignore[return-value]


def _persist() -> None:
    """Grava o modo atual em disco (chamado dentro do _lock)."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _MODE_FILE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                {
                    "mode": _current_mode,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(_MODE_FILE)
    except Exception as exc:  # noqa: BLE001
        _log.error("[OperationMode] não consegui persistir o modo: %s", exc)


def _reset_for_tests() -> None:
    """Reseta o singleton em memória — uso EXCLUSIVO de testes."""
    global _current_mode, _loaded
    with _lock:
        _current_mode = None
        _loaded = False

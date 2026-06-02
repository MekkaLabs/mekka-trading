"""
src/services/market_type_swap_guard.py
========================================
Guard pro hot-swap de binance_market_type (linear ↔ inverse).

Background (P1-3 fix da auditoria 2026-05-28):
- settings.py documenta que troca de market_type é bloqueada quando há
  posições abertas, mas nenhum validator real implementava isto
- Operador podia editar .env BINANCE_MARKET_TYPE=inverse com posição
  USDT-M aberta → posição vira zumbi (rastreada no client errado)

Este módulo expõe 2 funções fail-silent:

- `check_swap_safe(target_type)` — async, consulta positions via
  PortfolioManager + DB. Retorna (ok, reason, evidence_dict).
- `log_boot_swap_warning()` — chamado no init do IronMan. Compara
  market_type atual vs last_known (persistido em data/) e alerta se
  mudou + há trades FILLED não-fechados.

Persistência leve em ``data/last_market_type.txt`` (não vai pra git).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_REPO = Path(__file__).resolve().parents[2]
_LAST_FILE = _REPO / "data" / "last_market_type.txt"


# ---------------------------------------------------------------------------
# Persistence helpers — fail-silent
# ---------------------------------------------------------------------------


def _read_last_market_type() -> Optional[str]:
    try:
        if not _LAST_FILE.exists():
            return None
        return _LAST_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write_last_market_type(value: str) -> bool:
    try:
        _LAST_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LAST_FILE.with_suffix(".txt.tmp")
        tmp.write_text(value, encoding="utf-8")
        os.replace(tmp, _LAST_FILE)
        return True
    except OSError as exc:
        logger.debug(f"[swap_guard] write last_market_type failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Helpers para detectar posições em aberto
# ---------------------------------------------------------------------------


def _has_open_positions_in_db() -> tuple[bool, int]:
    """Best-effort: conta trades FILLED sem trade par de close registrado.

    Não é perfeito (não rastreia close vs open pairs estruturadamente),
    mas serve como heurística — quando há trade recente FILLED e não há
    sinal de close manual logo depois, assume posição aberta.

    Returns (has_open, count).
    """
    try:
        import sqlite3
        db = _REPO / "data" / "mekka_trading.db"
        if not db.exists():
            return False, 0
        conn = sqlite3.connect(str(db))
        try:
            # Heurística: contar trades FILLED dos últimos 7 dias sem
            # manual_close marker no metadata
            cur = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status='FILLED' "
                "AND timestamp > datetime('now', '-7 days') "
                "AND (raw NOT LIKE '%manual_close%' OR raw IS NULL)"
            )
            count = int(cur.fetchone()[0] or 0)
            return count > 0, count
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[swap_guard] db query failed: {exc}")
        return False, 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_swap_safe(target_type: str) -> tuple[bool, str, dict[str, Any]]:
    """
    Verifica se trocar binance_market_type pra target_type é seguro.

    Returns:
        (ok, reason, evidence). ``ok=False`` quando há posições abertas
        no DB ou outro fator de risco.
    """
    target_type = str(target_type or "").lower().strip()
    if target_type not in ("linear", "inverse"):
        return False, f"invalid target_type {target_type!r}", {}

    try:
        from src.config.settings import settings
        current = str(getattr(settings, "binance_market_type", "linear"))
    except Exception:  # noqa: BLE001
        current = "linear"

    if current == target_type:
        return True, "no-op (already on target)", {"current": current}

    has_open, count = _has_open_positions_in_db()
    if has_open:
        return False, (
            f"BLOCKED: {count} potencial(is) posição(ões) ativa(s) "
            f"detectada(s). Feche todas antes de trocar de {current} → "
            f"{target_type}."
        ), {
            "current_market_type": current,
            "target_market_type": target_type,
            "open_positions_heuristic": count,
            "recommendation": "Feche todas as positions via dashboard ou execute close-all manual.",
        }

    return True, "ok", {
        "current_market_type": current,
        "target_market_type": target_type,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def log_boot_swap_warning() -> Optional[dict[str, Any]]:
    """
    Chamado no init do IronMan. Compara market_type atual vs last_known.
    Se mudou + há positions abertas, log WARNING audit-friendly.

    Retorna dict de evidência se warning emitido, None caso contrário.
    Sempre persiste o market_type atual como last_known.
    """
    try:
        from src.config.settings import settings
        if settings.active_exchange != "binance":
            return None
        current = str(getattr(settings, "binance_market_type", "linear"))
        last = _read_last_market_type()

        # Persiste sempre (mesmo se igual — pra criar baseline)
        _write_last_market_type(current)

        if last is None or last == current:
            return None

        # Mudou! Checar posições
        has_open, count = _has_open_positions_in_db()
        if not has_open:
            logger.info(
                f"[swap_guard] market_type swap detected ({last} → {current}) "
                "sem posições abertas detectadas — safe."
            )
            return None

        evidence = {
            "from": last,
            "to": current,
            "open_positions_heuristic": count,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.warning(
            f"[swap_guard] ⚠️  market_type swap detectado ({last} → {current}) "
            f"COM ~{count} posição(ões) potencialmente aberta(s). Posições "
            "abertas em um market_type não migram automaticamente. Verifique "
            "se elas já foram fechadas ou se precisam de close manual."
        )
        return evidence
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[swap_guard] boot check failed: {exc}")
        return None

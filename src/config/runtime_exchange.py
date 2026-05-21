"""
src/config/runtime_exchange.py
==============================
Runtime Exchange Switch — troca a corretora ativa sem editar o .env.

A corretora ativa (``hyperliquid`` | ``bybit`` | ``binance``) normalmente vem
de ``ACTIVE_EXCHANGE`` no .env. Este módulo permite trocá-la em runtime pela UI
do dashboard: muta ``settings.active_exchange`` em memória (os agentes leem esse
campo a cada ciclo) e persiste a escolha em ``data/runtime_exchange.json`` para
sobreviver a um restart.

Segurança
---------
  • Só troca para uma corretora que tenha credenciais configuradas.
  • Nunca mexe no double-gate de live trading nem nos flags de testnet.
  • A troca entra em vigor no próximo ciclo / próxima ação, sem reinício.

Uso
---
    from src.config.runtime_exchange import set_exchange, summary, apply_to_settings

    apply_to_settings()        # no boot: aplica override persistido
    set_exchange("binance")    # troca + persiste
    summary()                  # estado de todas as corretoras (para a UI)
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

EXCHANGES: list[str] = ["hyperliquid", "bybit", "binance"]

_LABELS: dict[str, str] = {
    "hyperliquid": "Hyperliquid",
    "bybit": "Bybit",
    "binance": "Binance",
}

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_FILE = _DATA_DIR / "runtime_exchange.json"

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Credential + network helpers
# ---------------------------------------------------------------------------

def credentials_present(ex: str) -> bool:
    """True when the exchange has the credentials it needs to be active."""
    from src.config.settings import settings

    if ex == "hyperliquid":
        return bool(settings.hyperliquid_private_key and settings.hyperliquid_wallet_address)
    if ex == "bybit":
        return bool(settings.bybit_api_key and settings.bybit_api_secret)
    if ex == "binance":
        return bool(settings.binance_api_key and settings.binance_api_secret)
    return False


def network_for(ex: str) -> str:
    """Return 'testnet' or 'mainnet' for the exchange's current config."""
    from src.config.settings import settings

    if ex == "hyperliquid":
        return "mainnet" if settings.is_mainnet else "testnet"
    if ex == "bybit":
        return "testnet" if getattr(settings, "bybit_testnet", False) else "mainnet"
    if ex == "binance":
        return "testnet" if getattr(settings, "binance_testnet", False) else "mainnet"
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_exchange() -> str:
    """Return the currently active exchange (live settings value)."""
    from src.config.settings import settings

    return settings.active_exchange


def set_exchange(ex: str) -> dict[str, Any]:
    """Switch the active exchange in memory and persist the choice.

    Raises ValueError for unknown exchanges or missing credentials.
    """
    if ex not in EXCHANGES:
        raise ValueError(f"Corretora desconhecida '{ex}'. Válidas: {EXCHANGES}")
    if not credentials_present(ex):
        raise ValueError(
            f"Corretora '{ex}' sem credenciais configuradas no .env — "
            f"não é possível ativar. Configure as chaves primeiro."
        )

    from src.config.settings import settings

    with _lock:
        settings.active_exchange = ex  # type: ignore[assignment]
        _persist(ex)

    _log.info(f"[RuntimeExchange] active exchange → {ex} ({network_for(ex)})")
    return {"active": ex, "network": network_for(ex)}


def apply_to_settings() -> None:
    """At startup: apply a persisted exchange override onto live settings.

    Called once on boot, after settings load. Silently ignores a missing or
    invalid override, or one whose credentials are absent (falls back to the
    .env value).
    """
    if not _FILE.exists():
        return
    try:
        data = json.loads(_FILE.read_text())
        ex = data.get("active_exchange")
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"[RuntimeExchange] could not read {_FILE}: {exc}")
        return

    if ex not in EXCHANGES:
        return
    if not credentials_present(ex):
        _log.warning(
            f"[RuntimeExchange] persisted exchange '{ex}' has no credentials — "
            f"ignoring override, using .env value."
        )
        return

    from src.config.settings import settings

    if settings.active_exchange != ex:
        settings.active_exchange = ex  # type: ignore[assignment]
        _log.info(f"[RuntimeExchange] applied persisted override → {ex} ({network_for(ex)})")


def _persist(ex: str) -> None:
    """Write the active exchange to disk (called inside _lock)."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps({"active_exchange": ex}, indent=2))
    except Exception as exc:  # noqa: BLE001
        _log.error(f"[RuntimeExchange] could not persist exchange: {exc}")


def summary() -> dict[str, Any]:
    """Full state for the dashboard selector: active + per-exchange metadata."""
    active = get_exchange()
    return {
        "active": active,
        "exchanges": [
            {
                "id": ex,
                "label": _LABELS.get(ex, ex.title()),
                "active": ex == active,
                "credentials_present": credentials_present(ex),
                "network": network_for(ex),
            }
            for ex in EXCHANGES
        ],
    }

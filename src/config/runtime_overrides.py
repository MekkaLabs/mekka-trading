"""
src/config/runtime_overrides.py
================================
Runtime overrides — toggles UI persistidos em data/runtime_settings.json
que aplicam OVER do Modo Global (runtime_mode.py).

Histórico do bug (2026-05-25, sessão de verificação dos Modos de Trading):
- UI tinha 2 toggles ("🚀 Super Agressivo" + "🪙 Altcoins") que diziam
  "força size mínimo 5% e leverage 10x" e "expande universo de ativos"
- Mas ZERO agentes (Batman/Vision/NickFury) liam o runtime_settings.json
- Toggles só afetavam `_handle_trade_analyze` (botão TradeNow manual)
- Loop autônomo IGNORAVA os toggles → UI mentia ao operador

Este módulo centraliza a leitura e expõe API limpa para o loop honrar.

Convenções:
- Fail-silent: arquivo ausente / JSON corrompido → defaults seguros (toggles OFF)
- Hot-reload: lê do disco a cada chamada (não cachea)
- Idempotente: chamar 2x retorna mesmo resultado

Uso:
    from src.config.runtime_overrides import get_runtime_overrides, ALTCOINS

    ov = get_runtime_overrides()
    if ov["super_aggressive"]:
        # apertar mínimos no Batman, etc.
    if ov["altcoins_enabled"]:
        # NickFury expande trading_assets com ALTCOINS
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_RUNTIME_SETTINGS = _DATA_DIR / "runtime_settings.json"

# Universo de altcoins ativadas pelo toggle. Mantido em sync com o
# _ALTCOINS literal em src/dashboard/server.py:5439 (TradeNow handler).
# Se mudar aqui, atualizar lá também.
ALTCOINS: list[str] = ["ETH", "SOL", "AVAX", "BNB", "LINK"]

# Valores quando super_aggressive ON. Forçam mínimo (não cap).
# Espelham a UI: "Posição mínima 5% do capital · Leverage 10x".
SUPER_AGGRESSIVE_MIN_SIZE_PCT = 0.05  # 5% — mínimo, não cap
SUPER_AGGRESSIVE_MIN_LEVERAGE = 10    # 10x — mínimo, não cap

_DEFAULT_OVERRIDES: dict[str, Any] = {
    "super_aggressive": False,
    "altcoins_enabled": False,
}


def get_runtime_overrides() -> dict[str, Any]:
    """Lê data/runtime_settings.json e retorna dict com toggles.

    Fail-silent: arquivo ausente, JSON corrompido, ou erro de I/O
    retornam os defaults (todos OFF) — o sistema NUNCA aumenta risco
    silenciosamente por erro de leitura.
    """
    if not _RUNTIME_SETTINGS.exists():
        return dict(_DEFAULT_OVERRIDES)
    try:
        data = json.loads(_RUNTIME_SETTINGS.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(_DEFAULT_OVERRIDES)
        out = dict(_DEFAULT_OVERRIDES)
        out["super_aggressive"] = bool(data.get("super_aggressive", False))
        out["altcoins_enabled"] = bool(data.get("altcoins_enabled", False))
        return out
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.debug(f"[runtime_overrides] read failed (using defaults): {exc}")
        return dict(_DEFAULT_OVERRIDES)


def apply_super_aggressive_to_size_lev(
    size_pct: float, leverage: int, max_size_pct: float, max_leverage: int
) -> tuple[float, int]:
    """Se super_aggressive ON: aplica mínimos 5%/10x, respeitando os caps
    do Modo Global (max_size_pct / max_leverage) como teto absoluto.

    Returns (new_size_pct, new_leverage).
    """
    ov = get_runtime_overrides()
    if not ov["super_aggressive"]:
        return size_pct, leverage
    new_size = max(size_pct, SUPER_AGGRESSIVE_MIN_SIZE_PCT)
    new_lev = max(int(leverage), SUPER_AGGRESSIVE_MIN_LEVERAGE)
    # Respeita o teto do Modo Global — super_aggressive aperta mínimo mas
    # NUNCA ultrapassa cap. Se Modo Global = conservative (max 2x), super
    # aggressive ainda fica em 2x. Operador deve mudar Modo Global pra
    # liberar mais.
    new_size = min(new_size, float(max_size_pct))
    new_lev = min(new_lev, int(max_leverage))
    return new_size, new_lev


def expand_assets_with_altcoins(base_assets: list[str]) -> list[str]:
    """Se altcoins_enabled ON: adiciona ALTCOINS à lista de assets
    (preservando ordem original + dedup). Senão retorna lista original."""
    ov = get_runtime_overrides()
    if not ov["altcoins_enabled"]:
        return list(base_assets)
    seen = set(s.upper() for s in base_assets)
    out = list(base_assets)
    for sym in ALTCOINS:
        if sym.upper() not in seen:
            out.append(sym)
            seen.add(sym.upper())
    return out
